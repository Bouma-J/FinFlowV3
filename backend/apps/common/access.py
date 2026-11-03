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


def user_has_agency_access(user, agency_id):
    if not agency_id:
        return True
    if getattr(user, "is_group_level", False):
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

    scope = getattr(user, "data_scope", DataScope.AGENCY)
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

    scope = getattr(user, "data_scope", DataScope.AGENCY)
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
