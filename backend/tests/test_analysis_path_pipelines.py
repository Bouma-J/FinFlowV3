"""Chaque parcours traverse le pipeline de l'écran : saisie, enregistrement, ratios, réponse API."""
from decimal import Decimal

import pytest

from apps.catalog.models import CreditProduct, ProductCategory
from apps.clients.models import Client
from apps.common.tenancy import tenant_context
from apps.credits.analysis_validation import _purpose_test_failures
from apps.credits.analytics import compute_metrics
from apps.credits.models import AnalysisThreshold, CreditApplication, FinancialAnalysis
from apps.credits.serializers import FinancialAnalysisSerializer

pytestmark = pytest.mark.django_db

D = Decimal


def _statement(**income):
    return {
        "id": "a" * 32,
        "label": "2024",
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
        "nature": "CLOSED",
        "prepared_by": "EXPERT",
        "certified": "yes",
        "comment": "",
        "income": income,
        "balance": {},
        "cashflow": {},
        "notes": {},
        "documents": {},
    }


def _products():
    return [
        {
            "name": "Riz",
            "nature": "RESOLD",
            "quantity": "2",
            "unit_cost": "5",
            "sale_price": "12",
        },
        {
            "name": "Savon",
            "nature": "MANUFACTURED",
            "quantity_produced": "10",
            "quantity": "4",
            "material_cost": "30",
            "direct_labor": "20",
            "other_production_cost": "10",
            "sale_price": "20",
        },
        {"name": "Livraison", "nature": "SERVICE", "quantity": "3", "sale_price": "10"},
    ]


def _cash():
    return {
        "minimal_cash_open": "yes",
        "minimal_cash_opening": "100",
        "minimal_cash_inflows": "50",
        "minimal_cash_outflows": "20",
        "minimal_cash_closing": "140",
        "minimal_cash_label": "Janvier",
        "minimal_cash_start": "2026-01-01",
        "minimal_cash_end": "2026-01-31",
    }


@pytest.fixture
def zero_product(tenant_a):
    with tenant_context(tenant_a.id):
        category = ProductCategory.objects.create(tenant=tenant_a, code="PIPE", label="Pipeline")
        return CreditProduct.objects.create(
            tenant=tenant_a, code="PIPE", label="Pipeline", category=category,
            amount_min=D("1000"), amount_max=D("10000000"), interest_rate=D("0"),
        )


def _client(tenant, *, kind, ref):
    fields = {
        "tenant": tenant,
        "reference": ref,
        "client_type": kind,
        "kyc_status": Client.KycStatus.VALIDATED,
    }
    if kind == Client.ClientType.INDIVIDUAL:
        fields.update(first_name="Awa", last_name=ref)
    else:
        fields["company_name"] = ref
    return Client.objects.create(**fields)


def _save(tenant, client, product, ref, **payload):
    application = CreditApplication.objects.create(
        tenant=tenant, client=client, product=product, reference=ref,
        amount_requested=D("120000"), duration_months=12,
    )
    serializer = FinancialAnalysisSerializer(data={"application": str(application.id), **payload})
    assert serializer.is_valid(), serializer.errors
    analysis = serializer.save()
    analysis.refresh_from_db()
    live = compute_metrics(analysis, AnalysisThreshold.for_application(application, individual_profile=analysis.individual_profile))
    shown = FinancialAnalysisSerializer(analysis).data
    return analysis, live, shown


def _same(shown, live, key):
    value = shown.get(key)
    expected = live.get(key)
    if expected is None:
        assert value is None
    else:
        assert D(str(value)) == expected


def _screen_matches_engine(analysis, live, shown):
    assert analysis.repayment_capacity == live["repayment_capacity"]
    stored_ratio = live["solvency_ratio"] if analysis.is_corporate else live["debt_ratio"]
    assert analysis.debt_ratio == stored_ratio
    _same(shown, live, "repayment_capacity")
    _same(shown, {"debt_ratio": stored_ratio}, "debt_ratio")
    recorded = shown["recorded_indicators"]
    assert D(str(recorded["repayment_capacity"])) == live["repayment_capacity"]
    shown_dscr = live.get("global_dscr")
    if analysis.is_individual:
        assert analysis.dscr is None
    else:
        assert analysis.dscr == shown_dscr
    if shown_dscr is None:
        assert shown["dscr"] is None
    else:
        assert D(str(shown["dscr"])) == shown_dscr


def test_salary_keeps_household_figures_and_ignores_the_other_paths(tenant_a, zero_product):
    with tenant_context(tenant_a.id):
        client = _client(tenant_a, kind=Client.ClientType.INDIVIDUAL, ref="PIPE-SAL")
        analysis, live, shown = _save(
            tenant_a, client, zero_product, "PIPE-SAL",
            individual_profile="SALARIE",
            has_side_activity=False,
            reference_period="MONTHLY",
            salary_income="200000",
            activity_turnover="500000",
            activity_expenses="100000",
            informal_income_weight="70",
            analysis_details={
                "statement_basis": "STATEMENTS",
                "financial_statements": [_statement(sales_goods="9000000")],
                "campaign_open": "yes",
                "campaign_revenue": "999999",
                "activity_creation": "yes",
                "group_has_activity": "yes",
                **_cash(),
            },
        )
        _screen_matches_engine(analysis, live, shown)
        assert analysis.client_type == "INDIVIDUAL"
        assert analysis.individual_profile == "SALARIE"
        assert analysis.has_side_activity is False
        assert analysis.activity_turnover == D("500000.00")
        assert analysis.turnover == D("0.00")
        assert live["repayment_capacity"] == D("200000.00")
        assert live["weighted_income"] == D("200000.00")
        assert "campaign_monthly_surplus" not in live
        assert live.get("dscr_basis") != "forecast"
        assert live["minimal_cash_surplus"] == D("30.00")
        assert live["minimal_cash_gap"] == D("10.00")
        assert shown["dscr"] is None


def test_side_activity_and_mixed_profile_share_the_same_pipeline(tenant_a, zero_product):
    with tenant_context(tenant_a.id):
        for profile, flag, ref in (
            ("SALARIE", True, "PIPE-SIDE"),
            ("MIXTE", False, "PIPE-MIX"),
        ):
            client = _client(tenant_a, kind=Client.ClientType.INDIVIDUAL, ref=ref)
            analysis, live, shown = _save(
                tenant_a, client, zero_product, ref,
                individual_profile=profile,
                has_side_activity=flag,
                reference_period="MONTHLY",
                salary_income="100000",
                activity_turnover="100000",
                activity_expenses="0",
                informal_income_weight="70",
                analysis_details={
                    "statement_basis": "STATEMENTS",
                    "financial_statements": [_statement(sales_goods="9000000", personnel="1000")],
                    "products": _products(),
                    **_cash(),
                },
            )
            _screen_matches_engine(analysis, live, shown)
            assert analysis.individual_profile == profile
            assert analysis.has_side_activity is True
            assert analysis.activity_turnover == D("100000.00")
            assert analysis.salary_income == D("100000.00")
            assert analysis.turnover == D("0.00")
            assert live["weighted_income"] == D("170000.00")
            assert live["repayment_capacity"] == D("170000.00")
            assert live["reconstituted_sales"] == D("134.00")
            assert live["reconstituted_margin"] == D("100.00")
            assert live["minimal_cash_surplus"] == D("30.00")
            assert live["repayment_capacity"] != live["minimal_cash_surplus"]


def test_activity_campaign_replaces_only_the_capacity(tenant_a, zero_product):
    with tenant_context(tenant_a.id):
        client = _client(tenant_a, kind=Client.ClientType.INDIVIDUAL, ref="PIPE-IND")
        analysis, ordinary, shown = _save(
            tenant_a, client, zero_product, "PIPE-IND",
            individual_profile="INDEPENDANT",
            reference_period="MONTHLY",
            salary_income="0",
            activity_turnover="400000",
            activity_expenses="100000",
            informal_income_weight="100",
            projected_monthly_inflows="200000",
            projected_monthly_outflows="50000",
            analysis_details={
                "statement_basis": "RECONSTITUTED",
                "financial_statements": [_statement(sales_goods="9000000")],
                "products": _products(),
                "campaign_open": "no",
                "campaign_revenue": "240000",
                "activity_creation": "yes",
                **_cash(),
            },
        )
        _screen_matches_engine(analysis, ordinary, shown)
        assert analysis.has_side_activity is True
        assert analysis.activity_turnover == D("400000.00")
        assert ordinary["repayment_capacity"] == D("300000.00")
        assert ordinary["debt_ratio"] == (analysis.new_installment / D("300000") * D("100")).quantize(D("0.01"))
        assert ordinary["reconstituted_sales"] == D("134.00")
        assert ordinary["dscr_basis"] == "forecast"
        assert ordinary["repayment_capacity"] == D("300000.00")
        assert shown["dscr"] == float(ordinary["global_dscr"])
        assert analysis.dscr is None

        updated = FinancialAnalysisSerializer(analysis, data={
            "analysis_details": {**analysis.analysis_details, "campaign_open": "yes"},
        }, partial=True)
        assert updated.is_valid(), updated.errors
        updated.save()
        analysis.refresh_from_db()
        campaign = compute_metrics(analysis, AnalysisThreshold.for_application(analysis.application))
        assert campaign["campaign_monthly_surplus"] == D("20000.00")
        assert campaign["repayment_capacity"] == D("20000.00")
        assert campaign["weighted_income"] == D("20000.00")
        assert campaign["debt_ratio"] == (analysis.new_installment / D("20000") * D("100")).quantize(D("0.01"))
        assert campaign["debt_ratio"] != ordinary["debt_ratio"]
        assert campaign["minimal_cash_gap"] == D("10.00")
        assert analysis.activity_turnover == D("400000.00")


def test_corporate_reconstituted_keeps_typed_figures_beside_statements(tenant_a, zero_product):
    with tenant_context(tenant_a.id):
        client = _client(tenant_a, kind=Client.ClientType.CORPORATE, ref="PIPE-REC")
        analysis, live, shown = _save(
            tenant_a, client, zero_product, "PIPE-REC",
            reference_period="MONTHLY",
            turnover="1200000",
            cogs="0",
            analysis_details={
                "statement_basis": "RECONSTITUTED",
                "financial_statements": [_statement(sales_goods="1", personnel="1")],
                "products": _products(),
                "manufactures": "yes",
                **_cash(),
            },
        )
        _screen_matches_engine(analysis, live, shown)
        assert analysis.turnover == D("1200000.00")
        assert analysis.op_salaries == D("0.00")
        assert live["repayment_capacity"] == D("1200000.00")
        assert live["repayment_cash_flow"] == D("1200000.00")
        assert live["reconstituted_sales"] == D("134.00")
        assert live["reconstituted_margin"] == D("100.00")
        assert live["minimal_cash_theoretical_closing"] == D("130.00")
        assert live["solvency_ratio"] == shown["debt_ratio"] or shown["debt_ratio"] == float(live["solvency_ratio"])


def test_corporate_statements_replace_only_the_corporate_ratios(tenant_a, zero_product):
    with tenant_context(tenant_a.id):
        client = _client(tenant_a, kind=Client.ClientType.CORPORATE, ref="PIPE-STA")
        analysis, live, shown = _save(
            tenant_a, client, zero_product, "PIPE-STA",
            reference_period="MONTHLY",
            turnover="1",
            op_rent="77",
            activity_turnover="400000",
            salary_income="200000",
            projected_monthly_inflows="200000",
            projected_monthly_outflows="50000",
            analysis_details={
                "statement_basis": "STATEMENTS",
                "financial_statements": [_statement(sales_goods="500000", purchases_goods="200000", personnel="100000")],
                "activity_creation": "yes",
                "campaign_open": "yes",
                "campaign_revenue": "240000",
                "campaign_charges": "0",
            },
        )
        _screen_matches_engine(analysis, live, shown)
        assert analysis.turnover == D("500000.00")
        assert analysis.cogs == D("200000.00")
        assert analysis.op_salaries == D("100000.00")
        assert analysis.op_rent == D("0.00")
        assert analysis.salary_income == D("200000.00")
        assert live["campaign_monthly_surplus"] == D("20000.00")
        assert live["repayment_capacity"] == D("20000.00")
        assert live["repayment_cash_flow"] == D("150000.00")
        assert live["dscr_basis"] == "forecast"
        assert live["global_dscr"] == (D("150000") / analysis.new_installment).quantize(D("0.01"))
        assert shown["dscr"] == float(live["global_dscr"])

        again = FinancialAnalysisSerializer(analysis, data={
            "turnover": "9",
            "op_rent": "40",
            "analysis_details": analysis.analysis_details,
        }, partial=True)
        assert again.is_valid(), again.errors
        again.save()
        analysis.refresh_from_db()
        assert analysis.turnover == D("500000.00")
        assert analysis.op_rent == D("0.00")


def test_group_activity_stays_beside_contributions_and_statements(tenant_a, zero_product):
    with tenant_context(tenant_a.id):
        client = _client(tenant_a, kind=Client.ClientType.PROFESSIONAL, ref="PIPE-GRP")
        analysis, closed, shown = _save(
            tenant_a, client, zero_product, "PIPE-GRP",
            reference_period="MONTHLY",
            members_count=10,
            active_contributing_members=8,
            collective_contributions="100000",
            collective_operating_expenses="20000",
            collective_savings="900000",
            group_activity_turnover="80000",
            group_activity_expenses="30000",
            analysis_details={
                "group_has_activity": "no",
                "statement_basis": "STATEMENTS",
                "financial_statements": [_statement(sales_goods="9000000", personnel="1000")],
                "products": _products(),
                "campaign_open": "yes",
                "campaign_revenue": "120000",
                **_cash(),
            },
        )
        _screen_matches_engine(analysis, closed, shown)
        assert analysis.client_type == "PROFESSIONAL"
        assert analysis.uses_group_activity is False
        assert closed["collective_income"] == D("100000.00")
        assert closed["campaign_monthly_surplus"] == D("10000.00")
        assert closed["repayment_capacity"] == D("90000.00")
        assert closed["global_dscr"] == D("8.00")
        assert closed["minimal_cash_surplus"] == D("30.00")
        assert analysis.group_activity_turnover == D("80000.00")

        opened = FinancialAnalysisSerializer(analysis, data={
            "analysis_details": {**analysis.analysis_details, "group_has_activity": "yes", "statement_basis": "RECONSTITUTED"},
        }, partial=True)
        assert opened.is_valid(), opened.errors
        opened.save()
        analysis.refresh_from_db()
        live = compute_metrics(analysis, AnalysisThreshold.for_application(analysis.application))
        assert analysis.uses_group_activity is True
        assert analysis.group_activity_turnover == D("80000.00")
        assert live["collective_income"] == D("180000.00")
        assert live["repayment_capacity"] == D("90000.00")
        assert live["global_dscr"] == D("13.00")
        assert live["campaign_monthly_surplus"] == D("10000.00")
        assert live["reconstituted_sales"] == D("134.00")
        assert live["minimal_cash_surplus"] == D("30.00")
        assert live["debt_ratio"] == (analysis.new_installment / D("180000") * D("100")).quantize(D("0.01"))

        stated = FinancialAnalysisSerializer(analysis, data={
            "analysis_details": {**analysis.analysis_details, "statement_basis": "STATEMENTS", "campaign_open": "no"},
            "group_activity_turnover": "1",
        }, partial=True)
        assert stated.is_valid(), stated.errors
        stated.save()
        analysis.refresh_from_db()
        after = compute_metrics(analysis, AnalysisThreshold.for_application(analysis.application))
        assert analysis.group_activity_turnover == D("1.00")
        assert analysis.turnover == D("0.00")
        assert after["repayment_capacity"] == D("50001.00")
        assert after["collective_income"] == D("100001.00")
        assert "campaign_monthly_surplus" not in after


def test_purpose_gates_do_not_move_the_ratios(tenant_a, zero_product):
    with tenant_context(tenant_a.id):
        client = _client(tenant_a, kind=Client.ClientType.INDIVIDUAL, ref="PIPE-OBJ")
        analysis, before, _shown = _save(
            tenant_a, client, zero_product, "PIPE-OBJ",
            individual_profile="SALARIE",
            reference_period="MONTHLY",
            salary_income="200000",
            analysis_details={},
        )
        application = analysis.application
        application.purpose_type = "CONSUMPTION"
        application.save(update_fields=["purpose_type"])
        after = compute_metrics(analysis, AnalysisThreshold.for_application(application))
        assert after["repayment_capacity"] == before["repayment_capacity"]
        assert after["debt_ratio"] == before["debt_ratio"]
        failures = _purpose_test_failures(application, analysis, after)
        assert failures == []
        application.purpose_type = "TREASURY"
        failures = _purpose_test_failures(application, analysis, after)
        assert any("créances" in item for item in failures)
        assert not any("baisse des ventes" in item for item in failures)
        assert after["repayment_capacity"] == D("200000.00")
