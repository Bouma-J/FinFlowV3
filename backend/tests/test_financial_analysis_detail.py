"""Régressions : périodes, bilan et reconstitution des engagements."""
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.exceptions import ValidationError

from apps.common.tenancy import tenant_context
from apps.credits.analysis_details import apply_reference_statement, validate_details, detail_metrics
from apps.credits.models import CreditApplication, FinancialAnalysis, AnalysisThreshold, FinancialDocument
from apps.credits.analytics import compute_metrics
from apps.credits.serializers import FinancialAnalysisSerializer
from django.http import QueryDict
from unittest.mock import patch


@pytest.mark.parametrize("value", [
    {"stocks": [{"quantity": "10", "unit_cost": "20", "impaired_value": "201"}]},
    {"debts": [{"monthly_payment": "NaN"}]},
    {"cashflow": [{"month": "2026-01"}, {"month": "2026-01"}]},
    {"products": [{"quantity": "-1"}]},
])
def test_reject_invalid_reconstitution(value):
    with pytest.raises(ValidationError):
        validate_details(value)


def test_signed_history_and_seasonal_deficit():
    details = validate_details({
        "history": [{"net_result": "-100"}],
        "cashflow": [{"month": "2026-01", "inflows": "100", "outflows": "150"}],
    })
    analysis = FinancialAnalysis(analysis_details=details)
    assert detail_metrics(analysis)["forecast_lowest_flow"] == Decimal("-50")
    assert detail_metrics(analysis)["forecast_lowest_balance"] is None
    assert detail_metrics(analysis)["forecast_deficit_months"] == 1


@pytest.mark.django_db
def test_monthly_capacity_and_weighted_income(tenant_a, client_a, product_a):
    with tenant_context(tenant_a.id):
        app = CreditApplication.objects.create(
            tenant=tenant_a, client=client_a, product=product_a,
            reference="FA-PERIOD", amount_requested=100000, duration_months=12,
        )
        analysis = FinancialAnalysis.objects.create(
            tenant=tenant_a, application=app, reference_period="ANNUAL",
            salary_income=1200000, other_income=120000, food_expense=240000,
            informal_income_weight=50, existing_debt_monthly=5000,
        )
        assert analysis.repayment_capacity == Decimal("80000")
        assert analysis.disposable_income == Decimal("85000")
        metrics = compute_metrics(analysis, AnalysisThreshold.for_tenant(tenant_a.id))
        assert metrics["weighted_income"] == Decimal("105000")
        analysis.food_expense = 360000
        analysis.save(update_fields=["food_expense"])
        analysis.refresh_from_db()
        assert analysis.repayment_capacity == Decimal("70000")


def test_long_term_debt_is_part_of_total():
    analysis = FinancialAnalysis(
        ongoing_credit_balance=1000, long_term_debt=700,
        supplier_debt=100, tax_social_debt=50, shareholder_debt=20,
    )
    assert analysis.total_debts == Decimal("1170")
    serializer = FinancialAnalysisSerializer()
    with pytest.raises(ValidationError):
        serializer.validate({"long_term_debt": Decimal("1001"), "ongoing_credit_balance": Decimal("1000")})


def test_tpe_reconstitution_retains_observed_days_and_cash_gap():
    details = validate_details({
        "sales_method": "THREE_DAYS",
        "activity_days_per_month": "26",
        "sales_observations": [
            {"kind": "Observé", "label": "Jour 1", "amount": "10000"},
            {"kind": "Observé", "label": "Jour 2", "amount": "20000"},
            {"kind": "Observé", "label": "Jour 3", "amount": "30000"},
            {"kind": "Hypothèse", "label": "Jour excellent", "amount": "40000"},
        ],
        "purchase_method": "COST_RATE",
        "products": [
            {"quantity": "1", "sale_price": "100", "unit_cost": "60"},
        ],
        "last_purchase_date": "2026-11-01",
        "cash_control_date": "2026-11-11",
        "cash_at_last_purchase": "100000",
        "charges_paid_in_window": "50000",
        "other_outflows_in_window": "10000",
        "observed_cash": "240000",
        "safety_provision_pct": "30",
    })
    analysis = FinancialAnalysis(
        client_type="INDIVIDUAL", reference_period="MONTHLY", has_side_activity=True,
        activity_turnover=Decimal("520000"), activity_purchases=Decimal("312000"),
        analysis_details=details,
    )
    metrics = detail_metrics(analysis)
    assert metrics["tpe_observed_daily_average"] == Decimal("20000.00")
    assert metrics["tpe_retained_daily_sales"] == Decimal("20000.00")
    assert metrics["tpe_monthly_sales"] == Decimal("520000.00")
    assert metrics["tpe_sales_aligned"] is True
    assert metrics["tpe_margin_rate_pct"] == Decimal("40.00")
    assert metrics["tpe_monthly_purchases"] == Decimal("312000.00")
    assert metrics["tpe_purchases_aligned"] is True
    assert metrics["tpe_cash_days"] == 10
    assert metrics["tpe_cash_theoretical"] == Decimal("240000.00")
    assert metrics["tpe_cash_conclusion"] == "COHERENT"
    assert metrics["tpe_cash_charges_basis"] == "OBSERVED"
    metrics["repayment_capacity"] = Decimal("100000")
    metrics["installment"] = Decimal("70000")
    from apps.credits.analysis_details import apply_tpe_safety
    apply_tpe_safety(metrics, analysis)
    assert metrics["tpe_safety_provision"] == Decimal("30000.00")
    assert metrics["tpe_safety_available"] == Decimal("70000.00")
    assert metrics["tpe_safety_ok"] is True


def test_tpe_cash_prorata_does_not_treat_missing_charges_as_zero():
    details = validate_details({
        "sales_method": "THREE_DAYS",
        "sales_observations": [{"kind": "Observé", "amount": "20000"}],
        "last_purchase_date": "2026-11-01",
        "cash_control_date": "2026-11-11",
        "cash_at_last_purchase": "100000",
        "observed_cash": "200000",
    })
    bare = detail_metrics(FinancialAnalysis(client_type="INDIVIDUAL", reference_period="MONTHLY", analysis_details=details))
    assert bare["tpe_cash_incomplete"] is True
    assert "tpe_cash_conclusion" not in bare
    with_rent = FinancialAnalysis(
        client_type="INDIVIDUAL", reference_period="MONTHLY", rent_expense=Decimal("300000"),
        analysis_details=details,
    )
    checked = detail_metrics(with_rent)
    assert checked["tpe_cash_charges_basis"] == "PRORATA"
    assert checked["tpe_cash_prorata_warning"] is True
    assert checked["tpe_cash_charges"] == Decimal("100000.00")
    assert checked["tpe_cash_conclusion"] == "COHERENT"


@pytest.mark.parametrize("value", [
    {"sales_method": "NOPE"},
    {"activity_days_per_month": "32"},
    {"last_purchase_date": "2026-11-10", "cash_control_date": "2026-11-01"},
    {"sales_observations": [{"kind": "Autre", "amount": "10"}]},
    {"references": [{"kind": "Ami", "name": "Awa"}]},
])
def test_reject_invalid_tpe_details(value):
    with pytest.raises(ValidationError):
        validate_details(value)


def test_external_credit_keeps_each_loan_separate():
    saved = validate_details({"external_credits": [{
        "institution": "Banque A",
        "grant_date": "2024-01-15",
        "final_due_date": "2026-01-15",
        "initial_amount": "1000000",
        "monthly_payment": "50000",
        "outstanding": "400000",
        "max_days_late": "12",
        "bureau_checked": "yes",
        "bureau_date": "2026-03-01",
        "incidents": "no",
        "incidents_detail": "Aucun incident sur ce crédit.",
    }]})
    assert saved["external_credits"][0]["institution"] == "Banque A"


@pytest.mark.parametrize("value", [
    {"external_credits": [{"bureau_checked": "yes"}]},
    {"external_credits": [{"grant_date": "2026-02-01", "final_due_date": "2026-01-01"}]},
    {"external_credits": [{"max_days_late": "1.5"}]},
    {"external_credits": [{"incidents": "maybe"}]},
])
def test_reject_invalid_external_credit(value):
    with pytest.raises(ValidationError):
        validate_details(value)


def test_details_decode_from_multipart_form():
    serializer = FinancialAnalysisSerializer()
    data = QueryDict("analysis_details=%7B%22products%22%3A%5B%7B%22quantity%22%3A%222%22%7D%5D%7D")
    field = serializer.fields["analysis_details"]
    assert field.run_validation(field.get_value(data)) == {"products": [{"quantity": "2"}]}


@pytest.mark.django_db
def test_in_fine_retains_final_installment(tenant_a, client_a, product_a):
    with tenant_context(tenant_a.id):
        app = CreditApplication.objects.create(
            tenant=tenant_a, client=client_a, product=product_a,
            reference="FA-BULLET", amount_requested=1000, duration_months=12,
        )
        analysis = FinancialAnalysis(tenant=tenant_a, application=app)
        with patch("apps.credits.services.compute_amortization_schedule", return_value=[
            {"principal": Decimal("0"), "interest": Decimal("100")},
            {"principal": Decimal("1000"), "interest": Decimal("100")},
        ]):
            assert analysis._compute_new_installment() == Decimal("1100")


@pytest.mark.django_db
def test_corporate_capacity_annual_to_monthly(tenant_a, client_a, product_a):
    with tenant_context(tenant_a.id):
        client_a.client_type = "CORPORATE"
        client_a.save(update_fields=["client_type"])
        app = CreditApplication.objects.create(
            tenant=tenant_a, client=client_a, product=product_a,
            reference="FA-CORP", amount_requested=100000, duration_months=12,
        )
        analysis = FinancialAnalysis.objects.create(
            tenant=tenant_a, application=app, reference_period="ANNUAL",
            turnover=2400000, cogs=1200000, existing_debt_monthly=10000,
            projected_monthly_inflows=100000, projected_monthly_outflows=20000,
        )
        assert analysis.repayment_capacity == Decimal("70000")
        metrics = compute_metrics(analysis, AnalysisThreshold.for_tenant(tenant_a.id))
        assert metrics["monthly_cash_flow"] == Decimal("100000")
        assert metrics["repayment_cash_flow"] == Decimal("80000")
        assert analysis.dscr.quantize(Decimal("0.01")) == metrics["global_dscr"]


def _statement(exercise_id, **patch):
    row = {
        "id": exercise_id,
        "label": "2024",
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
        "nature": "CLOSED",
        "prepared_by": "EXPERT",
        "certified": "yes",
        "comment": "",
        "income": {},
        "balance": {},
        "cashflow": {},
        "notes": {},
        "documents": {},
    }
    row.update(patch)
    return row


def test_financial_statement_keeps_each_exercise_and_feeds_the_latest():
    details = validate_details({"financial_statements": [
        _statement("a" * 32, label="2023", start_date="2023-01-01", end_date="2023-12-31",
                   income={"sales_goods": "800", "net_result_read": "-20"}),
        _statement("b" * 32, income={"sales_goods": "1000", "purchases_goods": "400", "personnel": "100"},
                   balance={"stock_goods": "50", "customers": "20", "cash_and_banks": "10", "suppliers": "30", "borrowings": "40", "capital": "15"},
                   notes={"debt_noncurrent": "25", "headcount": "3", "off_balance": "Caution donnée."}),
    ]})
    attrs = {"analysis_details": details, "turnover": Decimal("1"), "op_rent": Decimal("9"), "long_term_debt": Decimal("0")}
    details["statement_basis"] = "STATEMENTS"
    apply_reference_statement(attrs)
    assert attrs["turnover"] == Decimal("1000")
    assert attrs["cogs"] == Decimal("400")
    assert attrs["op_salaries"] == Decimal("100")
    assert attrs["op_rent"] == Decimal("0")
    assert attrs["stock_value"] == Decimal("50")
    assert attrs["bank_balance"] == Decimal("10")
    assert attrs["ongoing_credit_balance"] == Decimal("40")
    assert attrs["long_term_debt"] == Decimal("25")
    assert attrs["turnover_prev"] == Decimal("800")
    assert attrs["net_result_prev"] == Decimal("-20")
    assert details["declared_equity"] == "15"
    assert details["cash_detail_mode"] == "DETAIL"


def test_individual_statements_stay_beside_the_household():
    details = validate_details({"statement_basis": "STATEMENTS", "financial_statements": [
        _statement("c" * 32, income={"sales_goods": "9000", "net_result_read": "1000"},
                   balance={"cash_and_banks": "400", "capital": "500"}),
    ]})
    attrs = {
        "analysis_details": details,
        "activity_turnover": Decimal("300"),
        "salary_income": Decimal("200"),
        "turnover": Decimal("1"),
    }
    apply_reference_statement(attrs, client_type="INDIVIDUAL")
    assert attrs["activity_turnover"] == Decimal("300")
    assert attrs["salary_income"] == Decimal("200")
    assert attrs["turnover"] == Decimal("1")
    assert "cogs" not in attrs
    assert details["statement_basis"] == "STATEMENTS"


def test_reconstituted_basis_keeps_statement_figures_out_of_ratios():
    details = validate_details({"statement_basis": "RECONSTITUTED", "financial_statements": [
        _statement("h" * 32, income={"sales_goods": "1000"}),
    ]})
    attrs = {"analysis_details": details, "turnover": Decimal("1")}
    apply_reference_statement(attrs)
    assert attrs["turnover"] == Decimal("1")


def test_minimal_cash_keeps_an_empty_line_empty_and_rejects_a_reversed_period():
    from apps.credits.analysis_details import detail_metrics

    details = validate_details({
        "minimal_cash_open": "yes",
        "minimal_cash_opening": "100",
        "minimal_cash_inflows": "",
        "minimal_cash_outflows": "20",
        "minimal_cash_start": "2026-01-01",
        "minimal_cash_end": "2026-01-31",
        "minimal_cash_label": "Janvier",
    })
    metrics = detail_metrics(FinancialAnalysis(analysis_details=details))
    assert metrics["minimal_cash_surplus"] == Decimal("-20.00")
    assert metrics["minimal_cash_theoretical_closing"] == Decimal("80.00")
    assert "minimal_cash_gap" not in metrics
    with pytest.raises(ValidationError):
        validate_details({"minimal_cash_inflows": "-1"})
    with pytest.raises(ValidationError):
        validate_details({"minimal_cash_start": "2026-02-01", "minimal_cash_end": "2026-01-01"})
    with pytest.raises(ValidationError):
        validate_details({"minimal_cash_document": "pas-un-uuid"})


@pytest.mark.parametrize("value", [
    {"financial_statements": [_statement("court")]},
    {"financial_statements": [_statement("c" * 32, end_date="2024-01-01", start_date="2024-06-01")]},
    {"financial_statements": [_statement("d" * 32, income={"unknown": "1"})]},
    {"financial_statements": [_statement("e" * 32, notes={"headcount": "1.5"})]},
    {"financial_statements": [_statement("f" * 32), _statement("f" * 32)]},
])
def test_reject_invalid_financial_statement(value):
    with pytest.raises(ValidationError):
        validate_details(value)


@pytest.mark.django_db
def test_statement_document_is_kept_on_its_piece(tenant_a, client_a, product_a):
    exercise = "g" * 32
    class Files(dict):
        def getlist(self, key):
            return []

    upload = SimpleUploadedFile("compte.pdf", b"%PDF-1.4\n", content_type="application/pdf")
    files = Files({f"statement_file__{exercise}__income": upload})

    class Request:
        FILES = files

    with tenant_context(tenant_a.id):
        app = CreditApplication.objects.create(
            tenant=tenant_a, client=client_a, product=product_a,
            reference="FA-ETAT", amount_requested=1000, duration_months=12,
        )
        serializer = FinancialAnalysisSerializer(
            data={
                "application": str(app.id),
                "analysis_details": {"statement_basis": "STATEMENTS", "financial_statements": [_statement(exercise, income={"sales_goods": "5000"})]},
            },
            context={"request": Request()},
        )
        assert serializer.is_valid(), serializer.errors
        analysis = serializer.save(tenant=tenant_a)
        document_id = analysis.analysis_details["financial_statements"][0]["documents"]["income"]
        document = FinancialDocument.objects.get(pk=document_id)
        assert document.analysis_id == analysis.id
        assert document.label.startswith("Compte de résultat")
        assert analysis.turnover == Decimal("0")
        assert analysis.analysis_details["financial_statements"][0]["income"]["sales_goods"] == "5000"


@pytest.mark.django_db
def test_minimal_cash_document_stays_out_of_the_ratios(tenant_a, client_a, product_a):
    class Files(dict):
        def getlist(self, key):
            return []

    upload = SimpleUploadedFile("caisse.pdf", b"%PDF-1.4\n", content_type="application/pdf")
    files = Files({"minimal_cash_file": upload})

    class Request:
        FILES = files

    with tenant_context(tenant_a.id):
        app = CreditApplication.objects.create(
            tenant=tenant_a, client=client_a, product=product_a,
            reference="FA-CAISSE", amount_requested=1000, duration_months=12,
        )
        serializer = FinancialAnalysisSerializer(
            data={
                "application": str(app.id),
                "salary_income": "100000",
                "analysis_details": {
                    "minimal_cash_open": "yes", "minimal_cash_label": "Janvier 2026",
                    "minimal_cash_opening": "100", "minimal_cash_inflows": "50",
                    "minimal_cash_outflows": "20", "minimal_cash_closing": "130",
                },
            },
            context={"request": Request()},
        )
        assert serializer.is_valid(), serializer.errors
        analysis = serializer.save(tenant=tenant_a)
        document = FinancialDocument.objects.get(pk=analysis.analysis_details["minimal_cash_document"])
        assert document.label.startswith("Trésorerie minimale")
        assert analysis.repayment_capacity == Decimal("100000.00")
        assert analysis.turnover == Decimal("0")
        assert analysis.analysis_details["minimal_cash_inflows"] == "50"
