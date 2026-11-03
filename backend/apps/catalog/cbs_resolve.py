"""Résolution des codes CBS depuis les référentiels catalogue."""
from __future__ import annotations


def _lookup(model, tenant_id, code: str):
    if not tenant_id or not code:
        return None
    return (
        model.all_tenants.filter(
            tenant_id=tenant_id, code=str(code).strip(), is_active=True
        )
        .order_by("sort_order", "label")
        .first()
    )


def resolve_ref(model, tenant_id, code: str) -> dict:
    """Retourne ``{code, label, cbs_code, periods_per_year?}`` ou dict vide."""
    row = _lookup(model, tenant_id, code)
    if row is None:
        return {}
    data = {
        "code": row.code,
        "label": row.label,
        "cbs_code": (row.cbs_code or "").strip(),
    }
    if hasattr(row, "periods_per_year"):
        data["periods_per_year"] = row.periods_per_year
    return data


def resolve_periodicity_cbs(
    tenant_id, code: str, *, fallback_map: dict | None = None
) -> str:
    from .models import LoanPeriodicity

    row = _lookup(LoanPeriodicity, tenant_id, code)
    if row and (row.cbs_code or "").strip():
        return row.cbs_code.strip()
    if fallback_map and code in fallback_map:
        return fallback_map[code]
    return str(code or "").strip()


def resolve_periodicity_periods_per_year(
    tenant_id, code: str, default: int = 12
) -> int:
    from .models import LoanPeriodicity

    row = _lookup(LoanPeriodicity, tenant_id, code)
    if row and row.periods_per_year:
        return int(row.periods_per_year)
    return int(default)


def resolve_repayment_cbs(tenant_id, code: str) -> str:
    from .models import RepaymentMethod

    row = _lookup(RepaymentMethod, tenant_id, code)
    if row and (row.cbs_code or "").strip():
        return row.cbs_code.strip()
    return ""


def resolve_currency_cbs(tenant_id, code: str, *, fallback: str = "XOF") -> str:
    from .models import Currency

    row = _lookup(Currency, tenant_id, code)
    if row:
        return (row.cbs_code or row.code or fallback).strip().upper()
    return str(code or fallback).strip().upper()


def resolve_financing_object_cbs(
    tenant_id,
    purpose_type: str,
    *,
    purpose_map: dict | None = None,
    default: str = "",
) -> str:
    """Résout ``idObjetFinancement`` : catalogue CBS d'abord, puis purpose_map syncé."""
    from .models import FinancingObject

    pt = str(purpose_type or "").strip()
    if tenant_id and pt:
        row = (
            FinancingObject.all_tenants.filter(
                tenant_id=tenant_id,
                purpose_type=pt,
                is_active=True,
            )
            .exclude(cbs_code="")
            .order_by("sort_order", "label")
            .first()
        )
        if row is None:
            row = (
                FinancingObject.all_tenants.filter(
                    tenant_id=tenant_id,
                    code__iexact=pt,
                    is_active=True,
                )
                .exclude(cbs_code="")
                .order_by("sort_order", "label")
                .first()
            )
        if row is not None:
            return (row.cbs_code or "").strip()

    mapped = str((purpose_map or {}).get(pt) or "").strip()
    if mapped and mapped != pt:
        # Accepte un id Vision déjà syncé dans purpose_map, ignore les libellés legacy
        # du type CONSOMMATION si un catalogue actif existe pour ce purpose.
        if tenant_id:
            if FinancingObject.all_tenants.filter(
                tenant_id=tenant_id, cbs_code=mapped, is_active=True
            ).exists():
                return mapped
            has_catalog = FinancingObject.all_tenants.filter(
                tenant_id=tenant_id, is_active=True
            ).exclude(cbs_code="").exists()
            if has_catalog and not mapped.isdigit():
                mapped = ""
        if mapped:
            return mapped

    default_val = str(default or "").strip()
    if default_val:
        return default_val

    # Dernier recours hors catalogue CBS : map Perfect historique (démo / seeds)
    if tenant_id:
        has_catalog = FinancingObject.all_tenants.filter(
            tenant_id=tenant_id, is_active=True
        ).exclude(cbs_code="").exists()
        if has_catalog:
            return ""
    from apps.corebanking.perfect_defaults import PURPOSE_CBS

    return str(PURPOSE_CBS.get(pt) or "").strip()


def active_codes(model, tenant_id) -> set[str]:
    if not tenant_id:
        return set()
    return set(
        model.all_tenants.filter(tenant_id=tenant_id, is_active=True).values_list(
            "code", flat=True
        )
    )


def application_cbs_refs(application) -> dict:
    """
    Snapshot des références CBS utilisées par le dossier
    (affichage UI + diagnostic readiness / décaissement).
    """
    from .models import Currency, LoanPeriodicity, RepaymentMethod

    tenant_id = getattr(application, "tenant_id", None)
    product = getattr(application, "product", None)
    period = resolve_ref(
        LoanPeriodicity, tenant_id, getattr(application, "periodicity", "") or ""
    )
    remb = resolve_ref(
        RepaymentMethod,
        tenant_id,
        getattr(application, "repayment_mechanism", "") or "",
    )
    curr = resolve_ref(
        Currency, tenant_id, getattr(application, "currency", "") or ""
    )

    product_cbs = ""
    product_remb_cbs = ""
    if product is not None:
        product_cbs = (getattr(product, "cbs_product_code", None) or "").strip()
        product_remb_cbs = (
            getattr(product, "cbs_repayment_product_code", None) or ""
        ).strip()

    id_produit_remb = product_remb_cbs or remb.get("cbs_code") or ""
    id_produit_crd = product_cbs or (
        (getattr(product, "code", None) or "").strip() if product else ""
    )

    purpose_type = getattr(application, "purpose_type", "") or ""
    financing = {}
    if purpose_type:
        from .models import FinancingObject

        fo = (
            FinancingObject.all_tenants.filter(
                tenant_id=tenant_id,
                purpose_type=purpose_type,
                is_active=True,
            )
            .exclude(cbs_code="")
            .order_by("sort_order", "label")
            .first()
        )
        if fo is not None:
            financing = {
                "code": fo.code,
                "label": fo.label,
                "cbs_code": (fo.cbs_code or "").strip(),
                "purpose_type": fo.purpose_type,
            }

    manager_cbs = ""
    for actor in (
        getattr(application, "submitted_by", None),
        getattr(application, "created_by", None),
    ):
        if actor is None:
            continue
        manager_cbs = (getattr(actor, "cbs_id", None) or "").strip()
        if manager_cbs:
            break

    client = getattr(application, "client", None)
    adherent = ""
    if client is not None:
        adherent = (
            (getattr(client, "cbs_client_id", None) or "").strip()
            or (getattr(client, "cbs_account_number", None) or "").strip()
            or (getattr(client, "national_id", None) or "").strip()
        )

    agency = getattr(application, "agency", None)
    point_service = ""
    if agency is not None:
        point_service = (
            getattr(agency, "cbs_point_of_service_id", None) or ""
        ).strip()

    warnings: list[str] = []
    if getattr(application, "periodicity", None) and not period.get("cbs_code"):
        warnings.append("Périodicité sans identifiant CBS (référentiel).")
    if not id_produit_remb:
        warnings.append(
            "Produit de remboursement CBS manquant "
            "(méthode de remboursement ou produit)."
        )
    if not id_produit_crd:
        warnings.append("Code produit crédit CBS (idProduitCrd) manquant.")
    if getattr(application, "currency", None) and not (
        curr.get("cbs_code") or curr.get("code")
    ):
        warnings.append("Devise absente du référentiel CBS.")
    if not adherent:
        warnings.append("Identifiant adhérent CBS manquant sur le client.")
    if not manager_cbs:
        warnings.append(
            "ID CBS gestionnaire manquant sur le soumissionnaire "
            "(utilisateur.cbs_id)."
        )
    if not point_service:
        warnings.append(
            "Point de service CBS manquant sur l'agence "
            "(ou défaut connecteur au décaissement)."
        )
    if purpose_type and not financing.get("cbs_code"):
        warnings.append(
            "Objet de financement CBS manquant "
            "(importez ref/object-fin-list et liez PurposeType)."
        )

    return {
        "periodicity": period,
        "repayment_method": remb,
        "currency": curr,
        "financing_object": financing,
        "product_cbs_code": id_produit_crd,
        "product_repayment_cbs_code": id_produit_remb,
        "manager_cbs_id": manager_cbs,
        "client_adherent_id": adherent,
        "point_of_service_id": point_service,
        "warnings": warnings,
        "ready_for_cbs": len(
            [w for w in warnings if "Point de service" not in w]
        )
        == 0,
    }
