from django.contrib.auth.models import Group, Permission
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.common.cache_utils import invalidate_prefix
from apps.common.permissions import (
    HasModelPermission,
    IsGroupLevel,
    MustChangePasswordGate,
)
from apps.common.tenancy import get_current_tenant_id, is_group_context
from apps.common.viewsets import TenantContextMixin

from .models import Delegation, TenantRole, User
from .password_services import issue_temporary_password
from .serializers import (
    ChangePasswordSerializer,
    DelegationGiveSerializer,
    DelegationSerializer,
    MeSerializer,
    PermissionSerializer,
    ProvisionFilialeAdminSerializer,
    TenantRoleSerializer,
    UserCreateSerializer,
    UserSerializer,
)


class UserViewSet(TenantContextMixin, viewsets.ModelViewSet):
    """Gestion des utilisateurs, filtrée selon la filiale active."""

    queryset = User.objects.all()
    permission_classes = [
        IsAuthenticated,
        MustChangePasswordGate,
        HasModelPermission,
    ]
    enforce_model_permissions = True
    action_perms = {
        "me": [],
        "change_password": [],
        "officers": [],
        "reset_password": ["accounts.change_user"],
        "provision_filiale_admin": [],  # IsGroupLevel vérifié dans l'action
    }
    filterset_fields = [
        "tenant", "agency", "data_scope", "is_group_level",
        "is_active", "is_staff",
    ]
    search_fields = ["username", "email", "first_name", "last_name", "employee_id"]

    def get_serializer_class(self):
        if self.action == "create":
            return UserCreateSerializer
        if self.action == "provision_filiale_admin":
            return ProvisionFilialeAdminSerializer
        if self.action == "change_password":
            return ChangePasswordSerializer
        return UserSerializer

    def get_queryset(self):
        qs = User.objects.select_related("tenant", "agency").prefetch_related(
            "groups__tenant_role", "agencies"
        )
        if not is_group_context():
            tenant_id = get_current_tenant_id()
            qs = qs.filter(tenant_id=tenant_id) if tenant_id else qs.none()
        else:
            tenant_id = get_current_tenant_id()
            if tenant_id:
                qs = qs.filter(tenant_id=tenant_id)
            else:
                qs = qs.filter(is_group_level=True)
        return qs

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        user = serializer.instance
        headers = self.get_success_headers(serializer.data)
        data = UserCreateSerializer(user, context={"request": request}).data
        email_sent = bool(getattr(user, "_email_sent", False))
        delivery = getattr(user, "_password_delivery", "email")
        data["email_sent"] = email_sent
        data["password_delivery"] = delivery
        if delivery == "manual":
            data["detail"] = (
                "Utilisateur créé. Mot de passe défini manuellement "
                "(changement obligatoire à la première connexion)."
            )
        elif email_sent:
            data["detail"] = (
                "Utilisateur créé. Mot de passe temporaire envoyé par e-mail."
            )
        else:
            data["detail"] = (
                "Utilisateur créé, mais l'e-mail n'a pas pu être envoyé. "
                "Utilisez « Mot de passe » pour le définir manuellement."
            )
        return Response(data, status=status.HTTP_201_CREATED, headers=headers)

    @action(detail=False, methods=["get"])
    def officers(self, request):
        """Liste légère des utilisateurs de la filiale (filtre gestionnaire)."""
        qs = (
            self.get_queryset()
            .filter(is_active=True)
            .order_by("last_name", "first_name", "username")
        )
        results = []
        for user in qs[:300]:
            label = (user.get_full_name() or "").strip() or user.username
            results.append({"id": str(user.pk), "display_name": label})
        return Response({"results": results})

    @action(detail=False, methods=["get", "patch"])
    def me(self, request):
        """Profil de l'utilisateur connecté (lecture / mise à jour limitée)."""
        from django.conf import settings

        from apps.common.cache_utils import cache_key, cached_get

        if request.method == "PATCH":
            allowed = {"first_name", "last_name", "email", "phone"}
            payload = {k: v for k, v in request.data.items() if k in allowed}
            if "email" in payload and not str(payload["email"]).strip():
                raise ValidationError({
                    "email": "L'adresse e-mail ne peut pas être vide."
                })
            if payload:
                for key, value in payload.items():
                    setattr(request.user, key, value)
                request.user.save(update_fields=list(payload.keys()))
            invalidate_prefix("me", request.user.id)
            return Response(
                MeSerializer(request.user, context={"request": request}).data
            )

        data = MeSerializer(request.user, context={"request": request}).data
        # Ne jamais mettre en cache un profil qui force le changement de MDP :
        # sinon l'UI peut rester bloquée / débloquée à tort après reset.
        if data.get("must_change_password"):
            return Response(data)

        key = cache_key("me", request.user.id)
        ttl = getattr(settings, "ME_CACHE_TTL", 60)

        def _produce():
            return MeSerializer(request.user, context={"request": request}).data

        return Response(cached_get(key, _produce, timeout=ttl))

    @action(detail=False, methods=["post"], url_path="me/change-password")
    def change_password(self, request):
        """Changement de mot de passe par l'utilisateur connecté."""
        serializer = ChangePasswordSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        user = request.user
        if not user.check_password(serializer.validated_data["current_password"]):
            raise ValidationError({
                "current_password": "Mot de passe actuel incorrect."
            })
        user.set_password(serializer.validated_data["new_password"])
        user.must_change_password = False
        user.save(update_fields=["password", "must_change_password"])
        invalidate_prefix("me", user.id)
        return Response({
            "detail": "Mot de passe mis à jour.",
            "must_change_password": False,
        })

    @action(detail=True, methods=["post"], url_path="reset-password")
    def reset_password(self, request, pk=None):
        """Régénère un mot de passe (envoi e-mail ou définition manuelle)."""
        from .password_services import (
            PASSWORD_DELIVERY_EMAIL,
            assign_password,
        )
        from .serializers import AdminSetPasswordSerializer

        user = self.get_object()
        serializer = AdminSetPasswordSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        delivery = serializer.validated_data["password_delivery"]

        if delivery == PASSWORD_DELIVERY_EMAIL:
            if not (user.email or "").strip():
                raise ValidationError({
                    "email": (
                        "Cet utilisateur n'a pas d'adresse e-mail. "
                        "Renseignez-en une, ou choisissez la définition manuelle."
                    )
                })
            _, email_sent = issue_temporary_password(
                user, reason="reset", send_email=True
            )
            invalidate_prefix("me", user.id)
            return Response({
                "detail": (
                    "Mot de passe temporaire envoyé par e-mail."
                    if email_sent
                    else (
                        "Mot de passe régénéré, mais l'e-mail n'a pas pu être "
                        "envoyé. Réessayez en mode manuel."
                    )
                ),
                "email_sent": email_sent,
                "password_delivery": delivery,
                "must_change_password": True,
                "user_id": str(user.id),
            })

        try:
            assign_password(
                user,
                serializer.validated_data["password"],
                must_change_password=True,
            )
        except Exception as exc:  # noqa: BLE001 — ValidationError Django
            raise ValidationError({
                "password": list(exc.messages)
                if hasattr(exc, "messages")
                else [str(exc)]
            }) from exc
        invalidate_prefix("me", user.id)
        return Response({
            "detail": (
                "Mot de passe défini manuellement "
                "(changement obligatoire à la prochaine connexion)."
            ),
            "email_sent": False,
            "password_delivery": delivery,
            "must_change_password": True,
            "user_id": str(user.id),
        })

    @action(
        detail=False,
        methods=["post"],
        url_path="provision-filiale-admin",
        permission_classes=[
            IsAuthenticated,
            MustChangePasswordGate,
            IsGroupLevel,
        ],
    )
    def provision_filiale_admin(self, request):
        """
        Crée un administrateur de filiale (réservé au niveau Groupe).

        Le mot de passe temporaire est généré et envoyé par e-mail.
        """
        serializer = ProvisionFilialeAdminSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        try:
            user = serializer.save()
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        created = getattr(user, "_provision_created", True)
        email_sent = bool(getattr(user, "_email_sent", False))
        delivery = getattr(user, "_password_delivery", "email")
        data = UserSerializer(user, context={"request": request}).data
        if not created:
            detail = "Compte existant élevé en administrateur filiale."
        elif delivery == "manual":
            detail = (
                "Administrateur filiale créé. Mot de passe défini manuellement."
            )
        elif email_sent:
            detail = (
                "Administrateur filiale créé. Mot de passe envoyé par e-mail."
            )
        else:
            detail = (
                "Administrateur filiale créé, mais l'e-mail n'a pas pu être envoyé."
            )
        return Response(
            {
                **data,
                "provisioned": True,
                "created": created,
                "email_sent": email_sent,
                "password_delivery": delivery,
                "detail": detail,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    def perform_create(self, serializer):
        serializer.save()


class GroupViewSet(TenantContextMixin, viewsets.ModelViewSet):
    """Rôles filiale (groupes de permissions scopés par filiale)."""

    queryset = TenantRole.objects.all()
    serializer_class = TenantRoleSerializer
    permission_classes = [
        IsAuthenticated,
        MustChangePasswordGate,
        HasModelPermission,
    ]
    enforce_model_permissions = True
    search_fields = ["name"]
    lookup_field = "group_id"
    lookup_url_kwarg = "pk"
    action_perms = {
        "group_level": ["accounts.view_tenantrole"],
    }

    def get_queryset(self):
        qs = TenantRole.objects.select_related("tenant", "group").prefetch_related(
            "group__permissions__content_type"
        )
        if not is_group_context():
            tenant_id = get_current_tenant_id()
            qs = qs.filter(tenant_id=tenant_id) if tenant_id else qs.none()
        else:
            tenant_id = get_current_tenant_id()
            if tenant_id:
                qs = qs.filter(tenant_id=tenant_id)
            else:
                qs = TenantRole.objects.none()
        return qs

    @action(detail=False, methods=["get"], url_path="group-level")
    def group_level(self, request):
        """Rôles transverses Groupe (ex. comité de crédit groupe)."""
        from apps.accounts.services import (
            CREDIT_COMMITTEE_GROUP_ROLE_NAME,
            ensure_group_credit_committee_role,
        )

        group = ensure_group_credit_committee_role()
        return Response(
            [
                {
                    "id": group.id,
                    "group_id": group.id,
                    "name": CREDIT_COMMITTEE_GROUP_ROLE_NAME,
                    "tenant": None,
                    "permissions": [],
                    "is_group_level_role": True,
                }
            ]
        )

    def perform_create(self, serializer):
        if get_current_tenant_id() is None:
            raise ValidationError({
                "detail": "Aucune filiale sélectionnée. Choisissez une filiale "
                          "avant de créer un rôle."
            })
        serializer.save()

    def perform_destroy(self, instance):
        group = instance.group
        instance.delete()
        group.delete()


class PermissionViewSet(viewsets.ReadOnlyModelViewSet):
    """Permissions Django disponibles (pour l'attribution des droits)."""

    queryset = Permission.objects.select_related("content_type").order_by(
        "content_type__app_label", "codename"
    )
    serializer_class = PermissionSerializer
    permission_classes = [
        IsAuthenticated,
        MustChangePasswordGate,
        HasModelPermission,
    ]
    # Lecture réservée aux gestionnaires de rôles filiale (TenantRole).
    action_perms = {
        "list": ["accounts.view_tenantrole"],
        "retrieve": ["accounts.view_tenantrole"],
    }
    pagination_class = None
    search_fields = ["name", "codename", "content_type__app_label"]


class DelegationViewSet(TenantContextMixin, viewsets.ModelViewSet):
    """Délégations de pouvoirs."""

    queryset = Delegation.objects.all()
    serializer_class = DelegationSerializer
    permission_classes = [
        IsAuthenticated,
        MustChangePasswordGate,
        HasModelPermission,
    ]
    enforce_model_permissions = True
    filterset_fields = ["delegator", "delegate", "is_active"]
    # Self-service : tout utilisateur authentifié peut gérer SES délégations.
    action_perms = {
        "mine": [],
        "give": [],
        "revoke": [],
        "colleagues": [],
    }

    def get_queryset(self):
        qs = Delegation.objects.select_related("delegator", "delegate")
        tenant_id = get_current_tenant_id()
        if tenant_id:
            return qs.filter(delegator__tenant_id=tenant_id)
        # Groupe sans filiale sélectionnée : pas de liste cross-tenant.
        return qs.none()

    @action(detail=False, methods=["get"])
    def colleagues(self, request):
        """Utilisateurs actifs de la filiale (hors soi) pour choisir un délégataire."""
        tenant_id = get_current_tenant_id() or getattr(
            request.user, "tenant_id", None
        )
        qs = User.objects.filter(is_active=True).exclude(pk=request.user.pk)
        if tenant_id:
            qs = qs.filter(tenant_id=tenant_id)
        rows = [
            {
                "id": str(u.id),
                "username": u.username,
                "display_name": u.get_full_name() or u.username,
            }
            for u in qs.order_by("last_name", "first_name", "username")[:300]
        ]
        return Response(rows)
    @action(detail=False, methods=["get"])
    def mine(self, request):
        """Délégations données ou reçues par l'utilisateur connecté."""
        from django.db.models import Q

        qs = (
            Delegation.objects.select_related("delegator", "delegate")
            .filter(Q(delegator=request.user) | Q(delegate=request.user))
            .order_by("-start_date")
        )
        return Response(
            DelegationSerializer(qs, many=True, context={"request": request}).data
        )

    @action(detail=False, methods=["post"])
    def give(self, request):
        """Crée une délégation où le délégant = utilisateur connecté."""
        payload = DelegationGiveSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        try:
            delegate = User.objects.get(pk=data["delegate"], is_active=True)
        except User.DoesNotExist as exc:
            raise ValidationError({"delegate": "Utilisateur introuvable."}) from exc
        if delegate.pk == request.user.pk:
            raise ValidationError(
                {"delegate": "Le délégataire doit être distinct du délégant."}
            )
        # Même filiale (sauf Groupe / superuser)
        if (
            not request.user.is_superuser
            and not getattr(request.user, "is_group_level", False)
            and request.user.tenant_id
            and delegate.tenant_id
            and delegate.tenant_id != request.user.tenant_id
        ):
            raise ValidationError(
                {"delegate": "Le délégataire doit appartenir à votre filiale."}
            )
        delegation = Delegation.objects.create(
            delegator=request.user,
            delegate=delegate,
            reason=data.get("reason") or "",
            start_date=data["start_date"],
            end_date=data["end_date"],
            is_active=True,
        )
        return Response(
            DelegationSerializer(delegation, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def revoke(self, request, pk=None):
        """Désactive une délégation (délégant ou admin)."""
        # get_object() respecte get_queryset() (filtre tenant) — anti-IDOR.
        delegation = self.get_object()

        is_owner = delegation.delegator_id == request.user.id
        can_admin = (
            request.user.is_superuser
            or getattr(request.user, "is_group_level", False)
            or request.user.has_perm("accounts.change_delegation")
        )
        if not is_owner and not can_admin:
            raise PermissionDenied(
                "Seul le délégant peut révoquer cette délégation."
            )

        delegation.is_active = False
        delegation.save(update_fields=["is_active"])
        return Response(
            DelegationSerializer(delegation, context={"request": request}).data
        )