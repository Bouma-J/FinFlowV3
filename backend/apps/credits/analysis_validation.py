"""Exhaustivité de l'analyse de référence avant soumission du dossier."""
from decimal import Decimal

from apps.workflow.services import WorkflowError


def _dec(value):
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")


def assert_analysis_ready_for_submission(application):
    """
    Bloque la soumission si l'analyse de référence est incomplète.

    - Recommandation obligatoire
    - Sections minimales selon le type de client
    - Produit exigeant une garantie : au moins une garantie ACTIVE ou caution
    """
    from apps.guarantees.models import Guarantee
    from apps.sureties.models import SuretyEngagement

    from .models import FinancialAnalysis

    reference = (
        application.financial_analyses.filter(is_reference=True).first()
        or application.financial_analyses.order_by("-created_at").first()
    )
    if reference is None:
        raise WorkflowError(
            "Une analyse financière de référence est obligatoire avant soumission."
        )

    from apps.configuration.services import analysis_requirement_failures

    failures = analysis_requirement_failures(application, reference)
    if failures:
        raise WorkflowError(" ".join(failures))

    if not reference.recommendation:
        raise WorkflowError(
            "L'analyse de référence doit porter une recommandation "
            "(favorable, sous conditions ou défavorable) avant soumission."
        )

    if (
        reference.recommendation
        == FinancialAnalysis.Recommendation.CONDITIONAL
        and not (reference.recommended_conditions or "").strip()
    ):
        raise WorkflowError(
            "Pour une recommandation sous conditions, précisez les conditions "
            "dans l'analyse de référence."
        )

    ctype = getattr(application.client, "client_type", "") or reference.client_type

    creation = reference.uses_creation
    if ctype == "CORPORATE":
        if _dec(reference.turnover) <= 0 and not creation:
            raise WorkflowError(
                "Analyse entreprise incomplète : le chiffre d'affaires est obligatoire."
            )
    elif ctype == "PROFESSIONAL":
        if not reference.members_count:
            raise WorkflowError(
                "Analyse groupement incomplète : indiquez le nombre de membres."
            )
        if not creation and _dec(reference.collective_contributions) <= 0 and _dec(
            reference.group_activity_turnover
        ) <= 0:
            raise WorkflowError(
                "Analyse groupement incomplète : renseignez les cotisations "
                "ou le CA de l'activité commune."
            )
    else:
        profile = getattr(reference, "individual_profile", "") or ""
        has_salary = (
            _dec(reference.salary_income) > 0 or _dec(reference.net_salary) > 0
            or _dec(reference.pension_income) > 0
        )
        has_activity_ca = _dec(reference.activity_turnover) > 0 or _extra_activity_turnover(reference) > 0
        campaign_instead = _campaign_replaces_turnover(reference)
        if not profile:
            if has_salary and (reference.has_side_activity or has_activity_ca):
                profile = FinancialAnalysis.IndividualProfile.MIXTE
            elif reference.has_side_activity or has_activity_ca:
                profile = FinancialAnalysis.IndividualProfile.INDEPENDANT
            else:
                profile = FinancialAnalysis.IndividualProfile.SALARIE

        if profile in (
            FinancialAnalysis.IndividualProfile.SALARIE,
            FinancialAnalysis.IndividualProfile.MIXTE,
        ):
            if not has_salary:
                raise WorkflowError(
                    "Analyse salarié incomplète : indiquez les revenus de salaire net ou de pension du demandeur."
                )
        if profile in (
            FinancialAnalysis.IndividualProfile.INDEPENDANT,
            FinancialAnalysis.IndividualProfile.MIXTE,
        ):
            if not has_activity_ca and not creation and not campaign_instead:
                raise WorkflowError(
                    "Analyse indépendant incomplète : indiquez le chiffre d'affaires "
                    "/ recettes de l'activité génératrice de revenus, ou les recettes de la campagne."
                )
        elif reference.has_side_activity and not has_activity_ca and not creation and not campaign_instead:
            raise WorkflowError(
                "Activité génératrice de revenus : indiquez le chiffre d'affaires "
                "/ recettes."
            )

        if reference.total_income <= 0 and not creation and not campaign_instead:
            raise WorkflowError(
                "Analyse personne physique incomplète : les revenus du ménage "
                "(ou de l'activité) doivent être renseignés."
            )

    if creation and _dec(reference.projected_monthly_inflows) == 0 and _dec(reference.projected_monthly_outflows) == 0:
        raise WorkflowError(
            "Activité en création : la prévision de trésorerie porte le DSCR. "
            "Renseignez les encaissements ou les sorties. Le chiffre d'affaires passé n'est pas exigé."
        )

    from .analysis_details import detail_metrics

    detailed = detail_metrics(reference)
    if detailed.get("debt_service_reconciled") is False:
        raise WorkflowError(
            "Rapprochez les mensualités des engagements détaillés avec le total consolidé avant soumission."
        )
    if detailed.get("tpe_cash_conclusion") in {"TO_JUSTIFY", "INCOHERENT"} and not str(
        (reference.analysis_details or {}).get("cash_check_comment") or ""
    ).strip():
        raise WorkflowError(
            "Le contrôle de trésorerie depuis le dernier achat présente un écart : "
            "expliquez-le dans le commentaire du contrôle avant soumission."
        )
    if detailed.get("forecast_deficit_months", 0) > 0 and not reference.recommended_conditions.strip():
        raise WorkflowError(
            "Le plan de trésorerie présente des mois déficitaires : précisez les mesures ou conditions proposées."
        )
    purpose_failures = _purpose_test_failures(application, reference, detailed)
    if purpose_failures:
        raise WorkflowError(" ".join(purpose_failures))
    gap = detailed.get("minimal_cash_gap")
    if gap is not None and gap != 0 and not _detail_text(reference, "minimal_cash_comment"):
        raise WorkflowError(
            "Le document de trésorerie minimale présente un écart entre la clôture lue et la clôture calculée : "
            "expliquez-le dans son commentaire."
        )
    product = application.product
    if product and getattr(product, "requires_guarantee", False):
        has_g = application.guarantees.filter(
            status=Guarantee.Status.ACTIVE
        ).exists()
        has_s = SuretyEngagement.objects.filter(
            application=application,
            status=SuretyEngagement.Status.ACTIVE,
        ).exists()
        if not has_g and not has_s:
            raise WorkflowError(
                "Le produit exige une garantie ou une caution : "
                "rattachez-en au moins une avant soumission."
            )

    capacity_message = capacity_blocks_submission(application, reference)
    if capacity_message:
        raise WorkflowError(capacity_message)

    return reference


def capacity_blocks_submission(application, reference):
    """La soumission s'arrête si l'effort du crédit n'est pas couvert."""
    if reference is None:
        return ""
    from .analytics import compute_metrics
    from .models import AnalysisThreshold

    metrics = compute_metrics(
        reference,
        AnalysisThreshold.for_tenant(application.tenant_id),
        recalculate_installment=True,
    )
    if metrics.get("flags", {}).get("capacity_ok") is False:
        return (
            "La capacité ne couvre pas l'échéance, l'épargne obligatoire "
            "et les dettes déjà en cours."
        )
    return ""


def _campaign_replaces_turnover(reference):
    if not getattr(reference, "uses_campaign", False):
        return False
    details = reference.analysis_details or {}
    return details.get("campaign_revenue") not in (None, "") or details.get("campaign_charges") not in (None, "")


def _extra_activity_turnover(reference):
    from .analysis_details import extra_activity_net

    return extra_activity_net(reference.analysis_details)


def _detail_text(reference, key):
    return str((reference.analysis_details or {}).get(key) or "").strip()


def _activity_on_statements(reference):
    details = reference.analysis_details or {}
    basis = details.get("statement_basis")
    if basis == "STATEMENTS":
        return True
    if basis == "RECONSTITUTED":
        return False
    return bool(details.get("financial_statements"))


def _reconstituted_activity(reference):
    """L'épreuve de stock ne vise que l'activité reconstituée, pas les états."""
    if reference.is_corporate:
        return not _activity_on_statements(reference)
    if reference.is_groupement:
        return reference.uses_group_activity and not _activity_on_statements(reference)
    if reference.has_activity_path:
        return not _activity_on_statements(reference)
    return False


def _purpose_test_failures(application, reference, detailed):
    """L'objet du dossier impose l'épreuve. Une épreuve vide bloque la soumission.

    Les formules de taux d'endettement, de DSCR et de retenue ne sont pas modifiées.
    """
    purpose = application.purpose_type or ""
    details = reference.analysis_details or {}
    if purpose == "CONSUMPTION":
        failures = []
        if reference.is_individual and reference.individual_profile in {"SALARIE", "MIXTE"}:
            if _dec(reference.salary_income) <= 0 and _dec(reference.net_salary) <= 0:
                failures.append(
                    "Consommation : le parcours salarial exige le salaire net pour calculer la quotité cessible."
                )
        return failures
    if purpose in {"WORKING_CAPITAL", "TREASURY", "STOCK"}:
        failures = []
        if details.get("receivable_delay_days") in (None, ""):
            failures.append(
                "Cet objet exige l'allongement des créances : indiquez le retard clients, y compris zéro s'il n'y en a pas."
            )
        if _reconstituted_activity(reference):
            sales_known = detailed.get("sales_reconciled") is True
            stock_known = detailed.get("stock_reconciled") is True
            gap = detailed.get("sales_reconciled") is False or detailed.get("stock_reconciled") is False
            if gap and not _detail_text(reference, "stock_risks"):
                failures.append(
                    "Le stock ou les ventes reconstituées s'écartent du déclaré : expliquez l'écart dans le commentaire sur le stock."
                )
            elif not sales_known and not stock_known and not _detail_text(reference, "stock_risks"):
                failures.append(
                    "L'activité est reconstituée : rapprochez le stock ou les ventes, ou écrivez le commentaire sur le stock."
                )
        return failures
    if purpose in {"EQUIPMENT", "REAL_ESTATE"}:
        if _dec(reference.projected_monthly_inflows) == 0 and _dec(reference.projected_monthly_outflows) == 0:
            return ["Équipement ou immobilier : la prévision de trésorerie est vide. Elle doit couvrir l'échéance."]
        if reference.new_installment is None:
            return ["Équipement ou immobilier : l'échéance n'est pas calculable, la prévision ne peut pas la couvrir."]
        if reference.projected_monthly_surplus < reference.monthly_new_installment:
            return ["Équipement ou immobilier : le solde prévisionnel mensuel ne couvre pas l'échéance."]
        return []
    if purpose == "OTHER":
        if not (reference.comment or "").strip():
            return ["Objet autre : écrivez l'épreuve retenue dans l'avis de synthèse."]
    return []


def refresh_reference_analysis(application):
    """Recalcule l'analyse de référence à partir des conditions actuelles."""
    if application is None or not getattr(application, "pk", None):
        return None
    reference = (
        application.financial_analyses.filter(is_reference=True).first()
        or application.financial_analyses.order_by("-created_at").first()
    )
    if reference is None:
        return None
    reference.save()
    return reference
