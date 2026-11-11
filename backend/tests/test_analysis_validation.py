"""Gates d'exhaustivité de l'analyse avant soumission."""
from decimal import Decimal

import pytest

from apps.catalog.models import CreditProduct
from apps.clients.models import Client
from apps.common.tenancy import tenant_context
from apps.credits.analysis_validation import (
    assert_analysis_ready_for_submission,
    refresh_reference_analysis,
)
from apps.credits.models import CreditApplication, FinancialAnalysis
from apps.guarantees.models import Guarantee
from apps.workflow.services import WorkflowError

pytestmark = pytest.mark.django_db


def _app(tenant, client, product, *, ref="D-AV"):
    return CreditApplication.objects.create(
        tenant=tenant,
        reference=ref,
        client=client,
        product=product,
        amount_requested=Decimal("500000"),
        duration_months=12,
        risk_level=1,
    )


def test_blocks_without_reference_analysis(tenant_a, product_a, client_a):
    with tenant_context(tenant_a.id):
        application = _app(tenant_a, client_a, product_a)
        with pytest.raises(WorkflowError, match="analyse financière"):
            assert_analysis_ready_for_submission(application)


def test_blocks_without_recommendation(tenant_a, product_a, client_a):
    with tenant_context(tenant_a.id):
        application = _app(tenant_a, client_a, product_a)
        FinancialAnalysis.objects.create(
            tenant=tenant_a,
            application=application,
            is_reference=True,
            salary_income=Decimal("200000"),
            client_type="INDIVIDUAL",
        )
        with pytest.raises(WorkflowError, match="recommandation"):
            assert_analysis_ready_for_submission(application)


def test_individual_requires_income(tenant_a, product_a, client_a):
    with tenant_context(tenant_a.id):
        application = _app(tenant_a, client_a, product_a, ref="D-INC")
        FinancialAnalysis.objects.create(
            tenant=tenant_a,
            application=application,
            is_reference=True,
            recommendation=FinancialAnalysis.Recommendation.FAVORABLE,
            client_type="INDIVIDUAL",
        )
        with pytest.raises(WorkflowError, match="revenus"):
            assert_analysis_ready_for_submission(application)


def test_side_activity_requires_turnover(tenant_a, product_a, client_a):
    with tenant_context(tenant_a.id):
        application = _app(tenant_a, client_a, product_a, ref="D-ACT")
        FinancialAnalysis.objects.create(
            tenant=tenant_a,
            application=application,
            is_reference=True,
            recommendation=FinancialAnalysis.Recommendation.FAVORABLE,
            client_type="INDIVIDUAL",
            salary_income=Decimal("100000"),
            has_side_activity=True,
            activity_turnover=Decimal("0"),
        )
        with pytest.raises(WorkflowError, match="activité"):
            assert_analysis_ready_for_submission(application)


def test_groupement_requires_members_and_capacity(tenant_a, product_a):
    with tenant_context(tenant_a.id):
        group = Client.objects.create(
            tenant=tenant_a,
            reference="CLI-G",
            client_type=Client.ClientType.PROFESSIONAL,
            company_name="GIE Test",
            kyc_status=Client.KycStatus.VALIDATED,
        )
        application = _app(tenant_a, group, product_a, ref="D-GRP")
        FinancialAnalysis.objects.create(
            tenant=tenant_a,
            application=application,
            is_reference=True,
            recommendation=FinancialAnalysis.Recommendation.FAVORABLE,
            client_type="PROFESSIONAL",
            members_count=5,
        )
        with pytest.raises(WorkflowError, match="cotisations|activité commune"):
            assert_analysis_ready_for_submission(application)

        analysis = application.financial_analyses.get()
        analysis.collective_contributions = Decimal("50000")
        analysis.save(update_fields=["collective_contributions", "updated_at"])
        assert assert_analysis_ready_for_submission(application) is not None


def test_requires_guarantee_blocks_without_collateral(tenant_a, client_a):
    with tenant_context(tenant_a.id):
        from apps.catalog.models import ProductCategory

        cat = ProductCategory.objects.create(
            tenant=tenant_a, code="CG", label="Cat G"
        )
        product = CreditProduct.objects.create(
            tenant=tenant_a,
            code="PG",
            label="Produit garanti",
            category=cat,
            amount_min=Decimal("1000"),
            amount_max=Decimal("10000000"),
            interest_rate=Decimal("10"),
            requires_guarantee=True,
        )
        application = _app(tenant_a, client_a, product, ref="D-GAR")
        FinancialAnalysis.objects.create(
            tenant=tenant_a,
            application=application,
            is_reference=True,
            recommendation=FinancialAnalysis.Recommendation.FAVORABLE,
            salary_income=Decimal("200000"),
            client_type="INDIVIDUAL",
        )
        with pytest.raises(WorkflowError, match="garantie ou une caution"):
            assert_analysis_ready_for_submission(application)

        Guarantee.objects.create(
            tenant=tenant_a,
            client=client_a,
            application=application,
            guarantee_type=Guarantee.GuaranteeType.MORTGAGE,
            description="Terrain",
            expertise_value=Decimal("800000"),
            current_value=Decimal("800000"),
            status=Guarantee.Status.ACTIVE,
            reference="GAR-AV-1",
        )
        assert assert_analysis_ready_for_submission(application) is not None


def test_conditional_requires_conditions_text(tenant_a, product_a, client_a):
    with tenant_context(tenant_a.id):
        application = _app(tenant_a, client_a, product_a, ref="D-COND")
        FinancialAnalysis.objects.create(
            tenant=tenant_a,
            application=application,
            is_reference=True,
            recommendation=FinancialAnalysis.Recommendation.CONDITIONAL,
            salary_income=Decimal("200000"),
            client_type="INDIVIDUAL",
        )
        with pytest.raises(WorkflowError, match="conditions"):
            assert_analysis_ready_for_submission(application)


def test_purpose_changes_the_required_test_without_a_new_form(tenant_a, product_a, client_a):
    with tenant_context(tenant_a.id):
        application = _app(tenant_a, client_a, product_a, ref="D-PURPOSE")
        application.purpose_type = "CONSUMPTION"
        application.save(update_fields=["purpose_type", "updated_at"])
        analysis = FinancialAnalysis.objects.create(
            tenant=tenant_a,
            application=application,
            is_reference=True,
            recommendation=FinancialAnalysis.Recommendation.FAVORABLE,
            client_type="INDIVIDUAL",
            individual_profile=FinancialAnalysis.IndividualProfile.SALARIE,
            salary_income=Decimal("200000"),
        )
        assert assert_analysis_ready_for_submission(application) is not None

        analysis.analysis_details = {"stress_assumptions": "Le revenu du foyer baisse de 20 %."}
        analysis.salary_income = Decimal("0")
        analysis.pension_income = Decimal("80000")
        analysis.save(update_fields=["analysis_details", "salary_income", "pension_income", "updated_at"])
        with pytest.raises(WorkflowError, match="quotité"):
            assert_analysis_ready_for_submission(application)

        analysis.salary_income = Decimal("200000")
        analysis.save(update_fields=["salary_income", "updated_at"])
        assert assert_analysis_ready_for_submission(application) is not None

        application.purpose_type = "TREASURY"
        application.save(update_fields=["purpose_type", "updated_at"])
        analysis.individual_profile = FinancialAnalysis.IndividualProfile.INDEPENDANT
        analysis.activity_turnover = Decimal("300000")
        analysis.analysis_details = {"stress_assumptions": "Les ventes baissent."}
        analysis.save(update_fields=["individual_profile", "activity_turnover", "analysis_details", "updated_at"])
        with pytest.raises(WorkflowError, match="créances|stock"):
            assert_analysis_ready_for_submission(application)

        analysis.analysis_details = {
            "stress_assumptions": "Les ventes baissent.",
            "receivable_delay_days": "0",
            "stock_risks": "Stock vu sur place, pas d'écart à signaler.",
        }
        analysis.save(update_fields=["analysis_details", "updated_at"])
        assert assert_analysis_ready_for_submission(application) is not None

        application.purpose_type = "EQUIPMENT"
        application.save(update_fields=["purpose_type", "updated_at"])
        analysis.individual_profile = FinancialAnalysis.IndividualProfile.SALARIE
        analysis.has_side_activity = False
        analysis.activity_turnover = Decimal("0")
        analysis.salary_income = Decimal("200000")
        analysis.projected_monthly_inflows = Decimal("0")
        analysis.projected_monthly_outflows = Decimal("0")
        analysis.analysis_details = {}
        analysis.save(update_fields=[
            "individual_profile", "has_side_activity", "activity_turnover", "salary_income",
            "projected_monthly_inflows", "projected_monthly_outflows", "analysis_details", "updated_at",
        ])
        with pytest.raises(WorkflowError, match="prévision de trésorerie est vide"):
            assert_analysis_ready_for_submission(application)
        analysis.projected_monthly_inflows = Decimal("1000")
        analysis.save(update_fields=["projected_monthly_inflows", "updated_at"])
        with pytest.raises(WorkflowError, match="ne couvre pas l'échéance"):
            assert_analysis_ready_for_submission(application)
        analysis.projected_monthly_inflows = Decimal("500000")
        analysis.save(update_fields=["projected_monthly_inflows", "updated_at"])
        assert assert_analysis_ready_for_submission(application) is not None

        application.purpose_type = "OTHER"
        application.save(update_fields=["purpose_type", "updated_at"])
        analysis.comment = ""
        analysis.projected_monthly_inflows = Decimal("0")
        analysis.save(update_fields=["comment", "projected_monthly_inflows", "updated_at"])
        with pytest.raises(WorkflowError, match="avis de synthèse"):
            assert_analysis_ready_for_submission(application)
        analysis.comment = "L'épreuve retenue est la stabilité du salaire sur six mois."
        analysis.save(update_fields=["comment", "updated_at"])
        assert assert_analysis_ready_for_submission(application) is not None


def test_minimal_cash_gap_requires_a_comment(tenant_a, product_a, client_a):
    with tenant_context(tenant_a.id):
        application = _app(tenant_a, client_a, product_a, ref="D-CASH")
        analysis = FinancialAnalysis.objects.create(
            tenant=tenant_a,
            application=application,
            is_reference=True,
            recommendation=FinancialAnalysis.Recommendation.FAVORABLE,
            client_type="INDIVIDUAL",
            individual_profile=FinancialAnalysis.IndividualProfile.SALARIE,
            salary_income=Decimal("200000"),
            analysis_details={
                "minimal_cash_open": "yes",
                "minimal_cash_opening": "100",
                "minimal_cash_inflows": "50",
                "minimal_cash_outflows": "20",
                "minimal_cash_closing": "140",
            },
        )
        with pytest.raises(WorkflowError, match="trésorerie minimale"):
            assert_analysis_ready_for_submission(application)
        analysis.analysis_details["minimal_cash_comment"] = "La clôture compte un encaissement hors période."
        analysis.save(update_fields=["analysis_details", "updated_at"])
        assert assert_analysis_ready_for_submission(application) is not None


def test_creation_drops_past_turnover_and_requires_the_forecast(tenant_a, product_a, client_a):
    with tenant_context(tenant_a.id):
        application = _app(tenant_a, client_a, product_a, ref="D-CREATE")
        analysis = FinancialAnalysis.objects.create(
            tenant=tenant_a,
            application=application,
            is_reference=True,
            recommendation=FinancialAnalysis.Recommendation.FAVORABLE,
            client_type="INDIVIDUAL",
            individual_profile=FinancialAnalysis.IndividualProfile.INDEPENDANT,
            analysis_details={"activity_creation": "yes"},
        )
        with pytest.raises(WorkflowError, match="prévision"):
            assert_analysis_ready_for_submission(application)
        analysis.projected_monthly_inflows = Decimal("150000")
        analysis.save(update_fields=["projected_monthly_inflows", "updated_at"])
        assert assert_analysis_ready_for_submission(application) is not None


def test_groupement_uses_collective_capacity_and_live_client_type(
    tenant_a, product_a,
):
    with tenant_context(tenant_a.id):
        group = Client.objects.create(
            tenant=tenant_a,
            reference="CLI-G-CAP",
            client_type=Client.ClientType.PROFESSIONAL,
            company_name="GIE Capacite",
            kyc_status=Client.KycStatus.VALIDATED,
        )
        application = _app(tenant_a, group, product_a, ref="D-GRP-CAP")
        analysis = FinancialAnalysis.objects.create(
            tenant=tenant_a,
            application=application,
            is_reference=True,
            client_type="INDIVIDUAL",
            salary_income=Decimal("200000"),
            collective_contributions=Decimal("80000"),
            collective_operating_expenses=Decimal("10000"),
            existing_debt_monthly=Decimal("5000"),
        )
        analysis.refresh_from_db()
        assert analysis.client_type == Client.ClientType.PROFESSIONAL
        assert analysis.is_groupement
        assert analysis.collective_capacity == Decimal("70000")
        assert analysis.repayment_capacity == Decimal("65000")


def test_refresh_reference_analysis_after_amount_change(
    tenant_a, product_a, client_a
):
    with tenant_context(tenant_a.id):
        application = _app(tenant_a, client_a, product_a, ref="D-C3")
        analysis = FinancialAnalysis.objects.create(
            tenant=tenant_a,
            application=application,
            is_reference=True,
            recommendation=FinancialAnalysis.Recommendation.FAVORABLE,
            salary_income=Decimal("300000"),
            client_type="INDIVIDUAL",
        )
        before = analysis.new_installment
        assert before is not None
        application.amount_requested = Decimal("2000000")
        application.amount_proposed = Decimal("2000000")
        application.save(update_fields=["amount_requested", "amount_proposed", "updated_at"])
        refreshed = refresh_reference_analysis(application)
        assert refreshed is not None
        assert refreshed.new_installment is not None
        assert refreshed.new_installment != before
        assert refreshed.new_installment > before
