"""Filtrage des données selon le périmètre utilisateur (agence / propre / filiale)."""
from django.db.models import Q


class DataScope:
    OWN = "OWN"
    AGENCY = "AGENCY"
    TENANT = "TENANT"


def get_user_agency_ids(user):
    """Identifiants des agences accessibles à l'utilisateur."""
    if not user or not user.is_authenticated:
        return []
    if getattr(user, "is_group_level", False):
        return []
    agency_ids = set(user.agencies.values_list("id", flat=True))
    if user.agency_id:
        agency_ids.add(user.agency_id)
    return list(agency_ids)


# Ces profils voient toute la filiale, même si le compte est encore marqué Agence.
FILIALE_WIDE_PACK_CODES = frozenset({
    "tenant_admin",
    "operations_manager",
    "credit_risk_manager",
    "credit_analyst",
})


def sees_whole_filiale(user):
    """Vrai pour l'administrateur filiale et les rôles d'instruction à périmètre filiale."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_group_level", False) or not getattr(user, "tenant_id", None):
        return False
    from apps.accounts.models import TenantRole

    return TenantRole.objects.filter(
        tenant_id=user.tenant_id,
        group__in=user.groups.all(),
        pack_code__in=FILIALE_WIDE_PACK_CODES,
    ).exists()


def effective_data_scope(user):
    if sees_whole_filiale(user):
        return DataScope.TENANT
    return getattr(user, "data_scope", DataScope.AGENCY)


def user_has_agency_access(user, agency_id):
    if not agency_id:
        return True
    if getattr(user, "is_group_level", False):
        return True
    # TENANT means the full branch, including agency records. Keep this
    # consistent with apply_data_scope(); callers still validate that the
    # agency belongs to the active tenant before relying on this check.
    if effective_data_scope(user) == DataScope.TENANT:
        return True
    return agency_id in get_user_agency_ids(user)


def apply_data_scope(qs, user, agency_field="agency", owner_field="created_by"):
    """
    Restreint un queryset selon ``user.data_scope`` :
    - TENANT : toute la filiale (filtrage tenant déjà appliqué) ;
    - AGENCY : enregistrements des agences de l'utilisateur ;
    - OWN : enregistrements créés par l'utilisateur.
    """
    if not user or not user.is_authenticated:
        return qs.none()
    if getattr(user, "is_group_level", False):
        return qs

    scope = effective_data_scope(user)
    if scope == DataScope.TENANT:
        return qs

    if scope == DataScope.AGENCY:
        agency_ids = get_user_agency_ids(user)
        if not agency_ids:
            return qs.none()
        if agency_field and agency_field in {
            f.name for f in qs.model._meta.get_fields()
        }:
            return qs.filter(**{f"{agency_field}_id__in": agency_ids})
        return qs

    if scope == DataScope.OWN:
        if owner_field and owner_field in {
            f.name for f in qs.model._meta.get_fields()
        }:
            return qs.filter(**{owner_field: user})
        return qs.none()

    return qs


def apply_related_data_scope(qs, user, agency_lookup):
    """Filtre via une relation (ex. ``application__agency``)."""
    if not user or not user.is_authenticated:
        return qs.none()
    if getattr(user, "is_group_level", False):
        return qs

    scope = effective_data_scope(user)
    if scope == DataScope.TENANT:
        return qs

    if scope == DataScope.AGENCY:
        agency_ids = get_user_agency_ids(user)
        if not agency_ids:
            return qs.none()
        return qs.filter(**{f"{agency_lookup}__in": agency_ids})

    if scope == DataScope.OWN:
        owner_lookup = agency_lookup.replace("agency", "created_by")
        if owner_lookup in {f.name for f in qs.model._meta.get_fields()}:
            return qs.filter(**{owner_lookup: user})
        base = agency_lookup.rsplit("__", 1)[0]
        return qs.filter(Q(**{f"{base}__created_by": user}))

    return qs


def apply_workflow_credit_scope(qs, user, *, prefix=""):
    """Applique aussi le périmètre crédit aux liens génériques des circuits."""
    from django.contrib.contenttypes.models import ContentType
    from apps.credits.models import CreditApplication

    if not user or not user.is_authenticated:
        return qs.none()
    if user.is_group_level or effective_data_scope(user) == DataScope.TENANT:
        return qs
    credit_type = ContentType.objects.get_for_model(CreditApplication)
    visible = apply_data_scope(CreditApplication.objects.all(), user).values("pk")
    return qs.filter(
        ~Q(**{f"{prefix}content_type": credit_type})
        | Q(**{f"{prefix}content_type": credit_type, f"{prefix}object_id__in": visible})
    )
