"""Politique d'instruction crédit — contrôles paramétrables par filiale."""
from __future__ import annotations

from apps.workflow.services import WorkflowError

from .models import CreditInstructionPolicy, FinancialAnalysis


def get_instruction_policy(tenant_id) -> CreditInstructionPolicy:
    return CreditInstructionPolicy.for_tenant(tenant_id)


def _checklist_provided(application) -> set[str]:
    raw = application.document_checklist or []
    labels: set[str] = set()
    if not isinstance(raw, list):
        return labels
    for item in raw:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip().lower()
        if label and item.get("provided") is True:
            labels.add(label)
    return labels


def _product_client_type_ok(application) -> bool:
    product = application.product
    client = application.client
    if not product or not client:
        return True
    allowed = getattr(product, "client_type", "") or "ALL"
    if allowed == "ALL":
        return True
    # Produit « entreprise » : entreprises et groupements (entité morale).
    if allowed == "CORPORATE":
        return bool(getattr(client, "is_legal_entity", False))
    return client.client_type == allowed


def _coverage_ok(application) -> bool | None:
    """True/False si mesurable, None si non applicable (pas de montant)."""
    from .collateral import build_collateral_summary
    from .models import AnalysisThreshold

    summary = build_collateral_summary(
        application, AnalysisThreshold.for_tenant(application.tenant_id)
    )
    ok = summary.get("guarantee_ok")
    if ok is None:
        return None
    return bool(ok)


def build_readiness(application) -> dict:
    """Checklist de readiness pour l'UI (et diagnostic API)."""
    from apps.clients.models import Client
    from apps.guarantees.models import Guarantee
    from apps.sureties.models import SuretyEngagement

    from .models import FieldVisit

    policy = get_instruction_policy(application.tenant_id)
    checks: list[dict] = []

    def add(key, label, ok, *, blocking=True, message=""):
        checks.append(
            {
                "key": key,
                "label": label,
                "ok": bool(ok),
                "blocking": blocking,
                "message": message,
            }
        )

    client = application.client
    add(
        "client",
        "Client rattaché",
        client is not None,
        message="" if client else "Sélectionnez un client.",
    )
    if client is not None:
        kyc_ok = client.kyc_status == Client.KycStatus.VALIDATED
        add(
            "kyc",
            "KYC client validé",
            kyc_ok,
            blocking=True,
            message="" if kyc_ok else "Validez le KYC du client avant soumission.",
        )

    product = application.product
    add(
        "product",
        "Produit de crédit",
        product is not None and getattr(product, "is_active", True),
        message=""
        if product and getattr(product, "is_active", True)
        else "Produit manquant ou inactif.",
    )

    if product and policy.match_product_client_type:
        ok = _product_client_type_ok(application)
        add(
            "client_type",
            "Cohérence type client / produit",
            ok,
            message="" if ok else "Le type de client ne correspond pas au produit.",
        )

    amount = application.amount_requested
    duration = application.duration_months
    bounds_ok = True
    bounds_msg = ""
    if product and amount is not None:
        if product.amount_min is not None and amount < product.amount_min:
            bounds_ok = False
            bounds_msg = f"Montant < minimum produit ({product.amount_min})."
        if product.amount_max is not None and amount > product.amount_max:
            bounds_ok = False
            bounds_msg = f"Montant > maximum produit ({product.amount_max})."
    if product and duration is not None:
        if (
            duration < product.duration_min_months
            or duration > product.duration_max_months
        ):
            bounds_ok = False
            bounds_msg = (
                f"Durée hors bornes ({product.duration_min_months}–"
                f"{product.duration_max_months} mois)."
            )
    add(
        "product_bounds",
        "Montant et durée dans les bornes produit",
        amount is not None and duration is not None and bounds_ok,
        message=bounds_msg
        or (
            ""
            if amount is not None and duration is not None
            else "Montant ou durée manquant."
        ),
    )

    reference = (
        application.financial_analyses.filter(is_reference=True).first()
        or application.financial_analyses.order_by("-created_at").first()
    )
    analysis_ok = reference is not None and bool(reference.recommendation)
    add(
        "analysis",
        "Analyse financière de référence avec recommandation",
        analysis_ok,
        message=""
        if analysis_ok
        else "Ajoutez une analyse de référence avec recommandation.",
    )

    if reference and not policy.allow_unfavorable_analysis_submit:
        fav_ok = (
            reference.recommendation
            != FinancialAnalysis.Recommendation.UNFAVORABLE
        )
        add(
            "analysis_favorable",
            "Recommandation non défavorable",
            fav_ok,
            message=""
            if fav_ok
            else "La politique filiale refuse la soumission d'une analyse défavorable.",
        )

    if product and getattr(product, "requires_guarantee", False):
        has_g = application.guarantees.filter(
            status=Guarantee.Status.ACTIVE
        ).exists()
        has_s = SuretyEngagement.objects.filter(
            application=application,
            status=SuretyEngagement.Status.ACTIVE,
        ).exists()
        add(
            "collateral_presence",
            "Garantie ou caution active (exigée par le produit)",
            has_g or has_s,
            message=""
            if has_g or has_s
            else "Rattachez au moins une garantie ou caution active.",
        )

    coverage = _coverage_ok(application)
    coverage_blocking = (
        policy.collateral_coverage_mode
        == CreditInstructionPolicy.CoverageMode.BLOCK_SUBMIT
    )
    if coverage is not None:
        add(
            "collateral_coverage",
            "Couverture garanties ≥ seuil filiale",
            coverage,
            blocking=coverage_blocking,
            message=""
            if coverage
            else (
                "Couverture insuffisante par rapport au seuil filiale."
                + (
                    " Soumission bloquée."
                    if coverage_blocking
                    else " (alerte)"
                )
            ),
        )

    if policy.require_field_visit:
        has_visit = FieldVisit.objects.filter(application=application).exists()
        add(
            "field_visit",
            "Au moins une visite terrain",
            has_visit,
            message="" if has_visit else "Enregistrez une visite terrain.",
        )

    if policy.require_product_checklist and product:
        from apps.catalog.models import ChecklistItem

        mandatory = list(
            ChecklistItem.objects.filter(
                product=product, is_mandatory=True
            ).values_list("label", flat=True)
        )
        provided = _checklist_provided(application)
        missing = [
            label
            for label in mandatory
            if label.strip().lower() not in provided
        ]
        add(
            "checklist",
            "Pièces obligatoires du produit",
            not missing,
            message=""
            if not missing
            else "Pièces manquantes : " + ", ".join(missing),
        )

    # Mapping CBS (référentiels) — informatif / alerte avant décaissement
    from apps.catalog.cbs_resolve import application_cbs_refs

    cbs = application_cbs_refs(application)
    cbs_ok = bool(cbs.get("ready_for_cbs"))
    cbs_msg = ""
    if cbs.get("warnings"):
        cbs_msg = " ; ".join(cbs["warnings"][:3])
        if len(cbs["warnings"]) > 3:
            cbs_msg += f" (+{len(cbs['warnings']) - 3})"
    add(
        "cbs_mapping",
        "Références CBS (périodicité, produit, devise, adhérent…)",
        cbs_ok,
        blocking=False,
        message="" if cbs_ok else cbs_msg,
    )

    # Contrats de cautionnement — informatif avant décaissement
    active_sureties = SuretyEngagement.objects.filter(
        application=application,
        status=SuretyEngagement.Status.ACTIVE,
    ).count()
    if active_sureties:
        from apps.contracts.services import missing_surety_signed_contracts

        surety_missing = missing_surety_signed_contracts(application)
        surety_ok = not surety_missing
        add(
            "surety_contracts",
            "Contrats de cautionnement signés",
            surety_ok,
            blocking=False,
            message=""
            if surety_ok
            else (
                "Avant décaissement : "
                + " ; ".join(surety_missing)
                + (
                    " — exigé par la politique filiale."
                    if policy.require_surety_signed_contracts
                    else ""
                )
            ),
        )

    blocking_failed = [c for c in checks if c["blocking"] and not c["ok"]]
    return {
        "ready": len(blocking_failed) == 0,
        "show_checklist": policy.show_readiness_checklist,
        "checks": checks,
        "cbs_refs": cbs,
        "policy": {
            "collateral_coverage_mode": policy.collateral_coverage_mode,
            "require_field_visit": policy.require_field_visit,
            "allow_unfavorable_analysis_submit": (
                policy.allow_unfavorable_analysis_submit
            ),
            "require_product_checklist": policy.require_product_checklist,
            "match_product_client_type": policy.match_product_client_type,
            "kyc_gate": policy.kyc_gate,
            "product_bounds_gate": policy.product_bounds_gate,
            "amount_approved_mode": policy.amount_approved_mode,
            "show_readiness_checklist": policy.show_readiness_checklist,
            "enable_cancel_status": policy.enable_cancel_status,
            "allow_collateral_during_approval": (
                policy.allow_collateral_during_approval
            ),
            "require_surety_signed_contracts": (
                policy.require_surety_signed_contracts
            ),
        },
    }


def assert_policy_submit_gates(application):
    """Contrôles politiques additionnels à la soumission (après gates de base)."""
    policy = get_instruction_policy(application.tenant_id)

    if policy.match_product_client_type and not _product_client_type_ok(
        application
    ):
        raise WorkflowError(
            "Le type de client ne correspond pas au produit de crédit sélectionné."
        )

    reference = (
        application.financial_analyses.filter(is_reference=True).first()
        or application.financial_analyses.order_by("-created_at").first()
    )
    if (
        reference
        and not policy.allow_unfavorable_analysis_submit
        and reference.recommendation
        == FinancialAnalysis.Recommendation.UNFAVORABLE
    ):
        raise WorkflowError(
            "La politique de la filiale interdit de soumettre un dossier "
            "dont l'analyse de référence est défavorable."
        )

    if policy.require_field_visit:
        from .models import FieldVisit

        if not FieldVisit.objects.filter(application=application).exists():
            raise WorkflowError(
                "Au moins une visite terrain est obligatoire avant soumission "
                "(paramètre filiale)."
            )

    if (
        policy.collateral_coverage_mode
        == CreditInstructionPolicy.CoverageMode.BLOCK_SUBMIT
    ):
        coverage = _coverage_ok(application)
        if coverage is False:
            raise WorkflowError(
                "Couverture des garanties insuffisante par rapport au seuil "
                "filiale : soumission bloquée (paramètre filiale)."
            )

    if policy.require_product_checklist and application.product_id:
        from apps.catalog.models import ChecklistItem

        mandatory = list(
            ChecklistItem.objects.filter(
                product_id=application.product_id, is_mandatory=True
            ).values_list("label", flat=True)
        )
        provided = _checklist_provided(application)
        missing = [
            label
            for label in mandatory
            if label.strip().lower() not in provided
        ]
        if missing:
            raise WorkflowError(
                "Pièces obligatoires manquantes avant soumission : "
                + ", ".join(missing)
            )


def assert_coverage_for_approval(application):
    """Bloque l'approbation finale si la politique l'exige."""
    policy = get_instruction_policy(application.tenant_id)
    if (
        policy.collateral_coverage_mode
        != CreditInstructionPolicy.CoverageMode.BLOCK_APPROVE
    ):
        return
    coverage = _coverage_ok(application)
    if coverage is False:
        raise WorkflowError(
            "Couverture des garanties insuffisante : approbation finale "
            "bloquée (paramètre filiale)."
        )


def assert_product_bounds(application):
    """Contrôle montant / durée vs produit (réutilisable create/update/submit)."""
    product = application.product
    if product is None:
        return
    amount = application.amount_requested
    if amount is not None:
        if product.amount_min is not None and amount < product.amount_min:
            raise WorkflowError(
                f"Le montant demandé ({amount}) est inférieur au minimum du produit "
                f"({product.amount_min})."
            )
        if product.amount_max is not None and amount > product.amount_max:
            raise WorkflowError(
                f"Le montant demandé ({amount}) dépasse le maximum du produit "
                f"({product.amount_max})."
            )
    duration = application.duration_months
    if duration is not None:
        if (
            duration < product.duration_min_months
            or duration > product.duration_max_months
        ):
            raise WorkflowError(
                f"La durée ({duration} mois) doit être entre "
                f"{product.duration_min_months} et {product.duration_max_months} mois "
                f"pour ce produit."
            )


def assert_kyc_validated(application):
    from apps.clients.models import Client

    client = application.client
    if client is None:
        raise WorkflowError("Un client est obligatoire.")
    if client.kyc_status != Client.KycStatus.VALIDATED:
        raise WorkflowError(
            "Le KYC du client doit être validé."
        )


def amount_approved_writable(application) -> bool:
    policy = get_instruction_policy(application.tenant_id)
    if (
        policy.amount_approved_mode
        == CreditInstructionPolicy.AmountApprovedMode.ALLOW
    ):
        return True
    # FORBID : uniquement une fois le dossier déjà décidé / contractualisé
    from .models import CreditApplication

    return application.status in {
        CreditApplication.Status.APPROVED,
        CreditApplication.Status.CONTRACT_GENERATED,
        CreditApplication.Status.DISBURSEMENT_PENDING,
        CreditApplication.Status.DISBURSED,
    }
