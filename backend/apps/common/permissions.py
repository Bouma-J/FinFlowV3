"""Permissions réutilisables (RBAC)."""
from rest_framework.permissions import BasePermission, SAFE_METHODS


class IsGroupLevel(BasePermission):
    """Autorise uniquement les utilisateurs de niveau Groupe."""

    message = "Accès réservé aux utilisateurs de niveau Groupe."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "is_group_level", False)
        )


class MustChangePasswordGate(BasePermission):
    """
    Tant que ``must_change_password`` est vrai, n'autorise que le profil,
    le changement de mot de passe et la déconnexion.
    """

    message = (
        "Vous devez changer votre mot de passe avant d'accéder à l'application."
    )

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return True
        if not getattr(user, "must_change_password", False):
            return True
        if request.method == "OPTIONS":
            return True

        action = getattr(view, "action", None)
        view_name = (getattr(view, "__class__", type(view)).__name__ or "").lower()

        if action in {"me", "change_password"}:
            return True
        if action == "create" and "logout" in view_name:
            return True
        # Vues JWT logout non-viewset
        path = (request.path or "").rstrip("/") + "/"
        if path.endswith("/auth/logout/") or path.endswith("/users/me/"):
            return True
        if path.endswith("/users/me/change-password/"):
            return True
        return False


class HasDashboardPermission(BasePermission):
    """Consulter le tableau de bord opérationnel (reporting.view_dashboard)."""

    message = "Droit insuffisant pour consulter le tableau de bord."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if user.is_superuser:
            return True
        return user.has_perm("reporting.view_dashboard")


class HasModelPermission(BasePermission):
    """
    Contrôle d'accès basé sur les permissions Django (RBAC).

    Ordre d'évaluation :
    1. Superutilisateur → autorisé
    2. `view.action_perms[action]` si défini (liste de codenames ; [] = authentifié)
    3. `view.required_perms` (liste statique)
    4. Si `view.enforce_model_permissions` : mappe la méthode HTTP
       vers view/add/change/delete du modèle du queryset
    5. Sinon → autorisé (compatibilité vues non migrées)
    """

    message = "Droit insuffisant pour cette action."

    _METHOD_TO_ACTION = {
        "GET": "view",
        "HEAD": "view",
        "OPTIONS": "view",
        "POST": "add",
        "PUT": "change",
        "PATCH": "change",
        "DELETE": "delete",
    }

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        # Même si une vue omet MustChangePasswordGate dans permission_classes.
        if not MustChangePasswordGate().has_permission(request, view):
            self.message = MustChangePasswordGate.message
            return False
        if user.is_superuser:
            return True

        action = getattr(view, "action", None)
        action_perms = getattr(view, "action_perms", None) or {}
        if action is not None and action in action_perms:
            required = action_perms[action]
            if not required:
                return True
            return user.has_perms(required)

        required = getattr(view, "required_perms", None)
        if required:
            return user.has_perms(required)

        if not getattr(view, "enforce_model_permissions", False):
            return True

        model = self._model_from_view(view)
        if model is None:
            return True

        verb = self._METHOD_TO_ACTION.get(request.method.upper())
        if verb is None:
            return False
        # Lecture seule via SAFE_METHODS si la vue le souhaite
        if request.method in SAFE_METHODS and verb != "view":
            verb = "view"

        perm = f"{model._meta.app_label}.{verb}_{model._meta.model_name}"
        return user.has_perm(perm)

    @staticmethod
    def _model_from_view(view):
        queryset = getattr(view, "queryset", None)
        if queryset is not None:
            return queryset.model
        get_queryset = getattr(view, "get_queryset", None)
        if callable(get_queryset):
            try:
                return get_queryset().model
            except Exception:  # noqa: BLE001
                return None
        return None
