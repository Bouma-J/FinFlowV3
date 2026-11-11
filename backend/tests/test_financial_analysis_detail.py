"""Régressions : périodes, bilan et reconstitution des engagements."""
from datetime import date
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.exceptions import ValidationError

from apps.common.tenancy import tenant_context
from apps.credits.analysis_details import (
    apply_reference_statement, validate_details, detail_metrics,
    purchase_history_indicators, purchase_period_total, purchase_monthly_total, supplier_payment_indicators,
    sales_monthly_total, collection_monthly_total, sales_period_indicators, collection_period_indicators,
    operating_charges_excluding_purchases, activity_expenses_with_purchases,
    activity_balance_reading, household_patrimony_total, net_patrimony,
)
from apps.credits.models import CreditApplication, FinancialAnalysis, AnalysisThreshold, FinancialDocument
from apps.credits.analytics import compute_metrics
from apps.credits.serializers import CreditApplicationSerializer, FinancialAnalysisSerializer
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


@pytest.mark.django_db
def test_formal_activity_is_retained_in_full_and_extra_income_is_weighted(tenant_a, client_a, product_a):
    with tenant_context(tenant_a.id):
        app = CreditApplication.objects.create(
            tenant=tenant_a, client=client_a, product=product_a,
            reference="FA-MIX-WEIGHT", amount_requested=100000, duration_months=12,
        )
        analysis = FinancialAnalysis.objects.create(
            tenant=tenant_a, application=app, reference_period="MONTHLY",
            individual_profile="MIXTE", has_side_activity=True,
            salary_income=100000, activity_turnover=100000, activity_expenses=0,
            informal_income_weight=70, turnover_prev=80000, net_result_prev=50000,
            analysis_details={"extra_income": [{"label": "Bourse", "amount": "10000"}]},
        )
        metrics = compute_metrics(analysis, AnalysisThreshold.for_tenant(tenant_a.id))
        assert metrics["weighted_income"] == Decimal("177000.00")
        assert metrics["turnover_growth"] == Decimal("25.00")
        assert metrics["result_growth"] == Decimal("100.00")
        analysis.activity_is_formal = True
        analysis.save(update_fields=["activity_is_formal"])
        retained = compute_metrics(analysis, AnalysisThreshold.for_tenant(tenant_a.id))
        assert retained["weighted_income"] == Decimal("207000.00")
        assert retained["debt_ratio"] != metrics["debt_ratio"]


@pytest.mark.django_db
def test_campaign_replaces_the_ordinary_activity_and_keeps_another(tenant_a, client_a, product_a):
    with tenant_context(tenant_a.id):
        app = CreditApplication.objects.create(
            tenant=tenant_a, client=client_a, product=product_a,
            reference="FA-CAMP", amount_requested=100000, duration_months=12,
        )
        analysis = FinancialAnalysis.objects.create(
            tenant=tenant_a, application=app, reference_period="MONTHLY",
            individual_profile="INDEPENDANT", has_side_activity=True,
            activity_turnover=0, informal_income_weight=100,
            analysis_details={
                "campaign_open": "yes",
                "campaign_revenue": "120000",
                "campaign_charges": "0",
                "extra_activities": [{"label": "Boutique", "turnover": "50000", "expenses": "20000"}],
            },
        )
        metrics = compute_metrics(analysis, AnalysisThreshold.for_tenant(tenant_a.id), recalculate_installment=True)
        assert metrics["weighted_income"] == Decimal("40000.00")
        assert metrics["campaign_monthly_surplus"] == Decimal("10000.00")
        assert metrics["debt_ratio"] == (metrics["installment"] / Decimal("40000") * Decimal("100")).quantize(Decimal("0.01"))


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


def test_several_purchase_methods_keep_one_amount_each():
    details = validate_details({
        "purchase_methods": [{"method": "INVOICES"}, {"method": "LEDGER"}, {"method": "OTHER"}],
        "purchase_average": "10000",
        "purchase_frequency": "2",
        "purchase_comment": "Saison sèche, prix du marché de gros.",
        "suppliers": [
            {"name": "Grossiste Ada", "place": "Adjamé", "product": "Riz", "share": "60", "amount": "400000", "payment_mode": "CREDIT", "delay_days": "7"},
            {"name": "", "place": "", "product": "", "share": "", "amount": "", "payment_mode": "", "delay_days": ""},
        ],
    })
    assert details["purchase_comment"] == "Saison sèche, prix du marché de gros."
    assert len(details["suppliers"]) == 1
    analysis = FinancialAnalysis(
        client_type="INDIVIDUAL", reference_period="MONTHLY",
        activity_purchases=Decimal("500000"), analysis_details=details,
    )
    metrics = detail_metrics(analysis)
    assert metrics["tpe_purchases_invoices"] == Decimal("20000.00")
    assert metrics["tpe_purchases_ledger"] == Decimal("20000.00")
    assert metrics["tpe_monthly_purchases"] is None
    assert "tpe_purchases_cost_rate" not in metrics
    assert analysis.activity_purchases == Decimal("500000")
    single = validate_details({
        "purchase_methods": [{"method": "INVOICES"}],
        "purchase_average": "10000",
        "purchase_frequency": "2",
    })
    single_metrics = detail_metrics(FinancialAnalysis(
        client_type="INDIVIDUAL", reference_period="MONTHLY",
        activity_purchases=Decimal("20000"), analysis_details=single,
    ))
    assert single_metrics["tpe_monthly_purchases"] == Decimal("20000.00")
    assert "tpe_purchases_invoices" not in single_metrics
    with pytest.raises(ValidationError):
        validate_details({"purchase_methods": [{"method": "INVOICES"}, {"method": "INVOICES"}]})
    with pytest.raises(ValidationError):
        validate_details({"suppliers": [{"share": "101", "payment_mode": "CASH"}]})
    with pytest.raises(ValidationError):
        validate_details({"suppliers": [{"payment_mode": "WIRE", "delay_days": "1.5"}]})


def test_analysis_period_drives_sales_collections_and_monthly_purchases():
    details = validate_details({
        "analysis_period_start": "2026-10-01",
        "analysis_period_end": "2026-10-31",
        "analysis_period_mode": "DAY",
        "sales_period_mode": "WEEK",
        "collection_period_mode": "MONTH",
        "sales_periods": [
            {"date": "2026-10-02", "amount": "10000"},
            {"date": "2026-10-03", "amount": "0"},
            {"date": "2026-11-01", "amount": "50000"},
        ],
        "purchase_history": [
            {"date": "2026-10-05", "product": "Riz", "supplier": "Ada", "quantity": "10", "unit": "kg", "unit_price": "400"},
            {"date": "2026-10-18", "product": "Tomate", "supplier": "Marché", "quantity": "4", "unit": "kg", "unit_price": "250"},
            {"date": "2026-10-18", "product": "Oignon", "supplier": "Marché", "quantity": "2", "unit": "kg", "unit_price": "300"},
            {"date": "2026-09-20", "product": "Huile", "supplier": "Ada", "quantity": "2", "unit": "bidon", "unit_price": "5000"},
        ],
    })
    assert details["sales_period_mode"] == "DAY"
    assert details["collection_period_mode"] == "DAY"
    assert details["purchase_period_start"] == "2026-10-01"
    assert details["purchase_period_end"] == "2026-10-31"
    assert sales_period_indicators(details)["count"] == 2
    assert sales_period_indicators(details)["monthly"] == Decimal("150000.00")
    assert purchase_period_total(details) == Decimal("5600.00")
    assert purchase_monthly_total(details) == Decimal("5419.35")
    assert purchase_monthly_total({"purchase_period_start": "2026-10-01", "purchase_period_end": "2026-10-31"}) is None
    with pytest.raises(ValidationError):
        validate_details({"analysis_period_start": "2026-10-31", "analysis_period_end": "2026-10-01"})


def test_purchase_history_sets_period_total_and_last_purchase():
    details = validate_details({
        "purchase_period_start": "2026-10-01",
        "purchase_period_end": "2026-10-31",
        "purchase_history": [
            {"date": "2026-09-20", "product": "Huile", "supplier": "Ada", "quantity": "2", "unit": "bidon", "unit_price": "5000"},
            {"date": "2026-10-05", "product": "Riz", "supplier": "Ada", "quantity": "10", "unit": "kg", "unit_price": "400"},
            {"date": "2026-10-18", "product": "Tomate", "supplier": "Marché", "quantity": "4", "unit": "kg", "unit_price": "250"},
            {"date": "2026-10-18", "product": "Oignon", "supplier": "Marché", "quantity": "2", "unit": "kg", "unit_price": "300"},
            {"date": "", "product": "", "supplier": "", "quantity": "", "unit": "", "unit_price": ""},
            {"date": "2026-10-12", "product": "Sel", "supplier": "Ada", "quantity": "", "unit": "kg", "unit_price": "100"},
        ],
        "last_purchase_date": "2026-01-01",
        "last_purchase_amount": "1",
    })
    assert len(details["purchase_history"]) == 5
    assert details["last_purchase_date"] == "2026-10-18"
    assert Decimal(details["last_purchase_amount"]) == Decimal("1600.00")
    assert purchase_period_total(details) == Decimal("5600.00")
    indicators = purchase_history_indicators(details)
    assert indicators["count"] == 3
    assert indicators["average"] == Decimal("1866.67")
    assert indicators["per_month"] == Decimal("2.90")
    assert indicators["last_date"] == "2026-10-18"
    assert indicators["last_amount"] == Decimal("1600.00")
    assert indicators["supplier_count"] == 2
    assert indicators["main_supplier"] == "Ada"
    assert indicators["main_share"] == Decimal("71.43")
    assert purchase_period_total({"purchase_method": "INVOICES"}) is None
    with pytest.raises(ValidationError):
        validate_details({"purchase_period_start": "2026-10-31", "purchase_period_end": "2026-10-01"})


def test_supplier_payments_summarize_complete_lines_without_touching_debt():
    details = validate_details({
        "observed_supplier_payment_days": "7",
        "supplier_payments": [
            {"date": "2026-10-05", "supplier": "Ada", "amount": "4000", "payment_mode": "CASH"},
            {"date": "2026-10-18", "supplier": "Marché", "amount": "1000", "payment_mode": "MOBILE"},
            {"date": "2026-10-18", "supplier": "Ada", "amount": "600", "payment_mode": "CASH"},
            {"date": "", "supplier": "", "amount": "", "payment_mode": ""},
            {"date": "2026-10-12", "supplier": "Ada", "amount": "", "payment_mode": "CASH"},
            {"date": "2026-10-02", "supplier": "Ada", "amount": "0", "payment_mode": "CASH"},
        ],
    })
    assert len(details["supplier_payments"]) == 5
    assert details["observed_supplier_payment_days"] == "7"
    assert "activity_supplier_debt" not in details
    paid = supplier_payment_indicators(details)
    assert paid["count"] == 4
    assert paid["total"] == Decimal("5600.00")
    assert paid["average"] == Decimal("1400.00")
    assert paid["last_date"] == "2026-10-18"
    assert paid["last_amount"] == Decimal("1600.00")
    assert supplier_payment_indicators({})["total"] is None
    with pytest.raises(ValidationError):
        validate_details({"supplier_payments": [{"payment_mode": "CREDIT", "amount": "10", "date": "2026-10-01"}]})


def test_sales_rhythm_becomes_the_monthly_turnover():
    day = validate_details({
        "sales_rhythm": "DAY",
        "sales_amount": "10000",
        "activity_days_per_month": "20",
        "collection_rhythm": "WEEK",
        "collection_amount": "5000",
    })
    assert sales_monthly_total(day) == Decimal("200000.00")
    assert collection_monthly_total(day) == Decimal("20000.00")
    assert sales_monthly_total({"sales_rhythm": "WEEK", "sales_amount": "100"}) == Decimal("400.00")
    assert sales_monthly_total({"sales_rhythm": "MONTH", "sales_amount": "1800000"}) == Decimal("1800000.00")
    assert sales_monthly_total({"sales_rhythm": "MONTH", "sales_amount": "0"}) == Decimal("0.00")
    assert sales_monthly_total({"sales_rhythm": "DAY", "sales_amount": "100"}) is None
    assert sales_monthly_total({"sales_rhythm": "MONTH"}) is None
    with pytest.raises(ValidationError):
        validate_details({"sales_rhythm": "YEAR"})


def test_sales_periods_set_the_monthly_turnover():
    weeks = validate_details({
        "sales_period_mode": "WEEK",
        "sales_periods": [
            {"start": "2026-10-01", "end": "2026-10-07", "amount": "70000", "appreciation": "BONNE"},
            {"start": "2026-10-08", "end": "2026-10-14", "amount": "80000", "appreciation": "BONNE"},
            {"start": "2026-10-15", "end": "2026-10-21", "amount": "90000", "appreciation": "MOYENNE"},
            {"start": "2026-10-22", "end": "2026-10-28", "amount": "60000", "appreciation": "FAIBLE"},
            {"amount": ""},
        ],
        "sales_rhythm": "MONTH",
        "sales_amount": "1800000",
    })
    assert weeks["sales_periods"] == [
        {"start": "2026-10-01", "end": "2026-10-07", "amount": "70000", "appreciation": "BONNE"},
        {"start": "2026-10-08", "end": "2026-10-14", "amount": "80000", "appreciation": "BONNE"},
        {"start": "2026-10-15", "end": "2026-10-21", "amount": "90000", "appreciation": "MOYENNE"},
        {"start": "2026-10-22", "end": "2026-10-28", "amount": "60000", "appreciation": "FAIBLE"},
    ]
    reading = sales_period_indicators(weeks)
    assert reading["count"] == 4
    assert reading["total"] == Decimal("300000.00")
    assert reading["average"] == Decimal("75000.00")
    assert reading["days"] == 28
    assert reading["monthly"] == Decimal("321428.57")
    assert reading["high_label"] == "2026-10-15 – 2026-10-21"
    assert reading["high_amount"] == Decimal("90000.00")
    assert reading["low_amount"] == Decimal("60000.00")
    assert reading["appreciation"] == "Bonne"
    assert sales_monthly_total(weeks) == Decimal("321428.57")
    daily = validate_details({
        "sales_period_mode": "DAY",
        "sales_periods": [
            {"date": "2026-10-05", "amount": "10000"},
            {"date": "2026-10-06", "amount": "0"},
            {"start": "2026-10-01", "end": "2026-10-31", "amount": "1800000"},
        ],
    })
    assert sales_monthly_total(daily) == Decimal("150000.00")
    assert sales_monthly_total({"sales_periods": [], "sales_rhythm": "MONTH", "sales_amount": "1800000"}) is None
    with pytest.raises(ValidationError):
        validate_details({"sales_periods": [{"start": "2026-10-31", "end": "2026-10-01", "amount": "100"}]})
    with pytest.raises(ValidationError):
        validate_details({"sales_periods": [{"amount": "100", "appreciation": "EXCELLENT"}]})
    with pytest.raises(ValidationError):
        validate_details({"sales_period_mode": "YEAR"})


def test_activity_balance_compares_only_known_years():
    current = {"stock": "350000", "receivables": "", "cash": "80000", "fixed": "150000", "debt": "200000"}
    empty = {"stock": "", "receivables": "", "cash": "", "fixed": "", "debt": ""}
    bare = activity_balance_reading(current, empty)
    assert bare["assets"] == Decimal("580000.00")
    assert bare["bfr"] == Decimal("150000.00")
    assert bare["net"] == Decimal("380000.00")
    assert bare["assets_prev"] is None
    assert bare["assets_variation"] is None
    previous = {"stock": "300000", "receivables": "", "cash": "", "fixed": "", "debt": "100000"}
    compared = activity_balance_reading(current, previous)
    assert compared["assets_prev"] == Decimal("300000.00")
    assert compared["assets_variation"] == Decimal("280000.00")
    assert compared["assets_rate"] == Decimal("93.33")
    assert compared["bfr_prev"] == Decimal("200000.00")
    assert compared["bfr_variation"] == Decimal("-50000.00")
    assert compared["net_prev"] == Decimal("200000.00")
    household = validate_details({
        "household_assets": [{"label": "Or", "amount": "40000"}, {"label": "", "amount": ""}],
    })
    assert household_patrimony_total(household, "10000", "", None, "0") == Decimal("50000.00")
    assert household_patrimony_total({}, "", "", "", "") is None
    assert net_patrimony(Decimal("380000.00"), None) == Decimal("380000.00")
    assert net_patrimony(None, None) is None
    with pytest.raises(ValidationError):
        validate_details({"household_assets": [{"label": "Or"}]})


def test_operating_charges_add_to_purchases_without_replacing_an_empty_detail():
    detailed = validate_details({
        "activity_charge_place": "50000",
        "activity_charge_staff": "0",
        "activity_charge_transport": "20000",
        "activity_extra_charges": [
            {"label": "Glace", "amount": "5000"},
            {"label": "", "amount": ""},
        ],
    })
    assert operating_charges_excluding_purchases(detailed) == Decimal("75000.00")
    assert activity_expenses_with_purchases(detailed, "1050000") == Decimal("1125000.00")
    assert activity_expenses_with_purchases(detailed, None) == Decimal("75000.00")
    assert operating_charges_excluding_purchases({}) is None
    assert activity_expenses_with_purchases({}, "1050000") is None
    with pytest.raises(ValidationError):
        validate_details({"activity_extra_charges": [{"label": "Glace"}]})


def test_collection_periods_month_does_not_become_a_receivable():
    weeks = validate_details({
        "collection_period_mode": "WEEK",
        "collection_periods": [
            {"start": "2026-10-01", "end": "2026-10-07", "amount": "1000", "appreciation": "BONNE"},
            {"start": "2026-10-08", "end": "2026-10-14", "amount": "2000", "appreciation": "BONNE"},
            {"start": "2026-10-15", "end": "2026-10-21", "amount": "3000", "appreciation": "MOYENNE"},
            {"start": "2026-10-22", "end": "2026-10-28", "amount": "0", "appreciation": "FAIBLE"},
            {"amount": ""},
        ],
        "collection_rhythm": "MONTH",
        "collection_amount": "50000",
    })
    reading = collection_period_indicators(weeks)
    assert reading["count"] == 4
    assert reading["total"] == Decimal("6000.00")
    assert reading["days"] == 28
    assert reading["monthly"] == Decimal("6428.57")
    assert reading["appreciation"] == "Bonne"
    assert collection_monthly_total(weeks) == Decimal("6428.57")
    assert "activity_receivables" not in weeks
    daily = validate_details({
        "collection_period_mode": "DAY",
        "collection_periods": [
            {"date": "2026-10-05", "amount": "4000"},
            {"date": "2026-10-06", "amount": "0"},
            {"start": "2026-10-01", "end": "2026-10-07", "amount": "9000"},
        ],
    })
    assert collection_monthly_total(daily) == Decimal("60000.00")
    assert collection_monthly_total({"collection_periods": [], "collection_rhythm": "WEEK", "collection_amount": "5000"}) is None
    assert collection_monthly_total({
        "collection_periods": [{"start": "2026-10-01", "end": "2026-10-07", "amount": "7000"}],
    }) == Decimal("30000.00")
    with pytest.raises(ValidationError):
        validate_details({"collection_periods": [{"start": "2026-10-31", "end": "2026-10-01", "amount": "100"}]})
    with pytest.raises(ValidationError):
        validate_details({"collection_period_mode": "YEAR"})


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


@pytest.mark.django_db
def test_conclusion_file_keeps_the_typed_label(tenant_a, client_a, product_a):
    upload = SimpleUploadedFile("bulletin.pdf", b"%PDF-1.4\n", content_type="application/pdf")

    class Files(dict):
        def getlist(self, key):
            return [upload] if key == "documents" else []

    data = QueryDict(mutable=True)
    data.appendlist("document_labels", "Bulletin de mars")

    class Request:
        FILES = Files()

    request = Request()
    request.data = data

    with tenant_context(tenant_a.id):
        app = CreditApplication.objects.create(
            tenant=tenant_a, client=client_a, product=product_a,
            reference="FA-PIECE", amount_requested=1000, duration_months=12,
        )
        serializer = FinancialAnalysisSerializer(
            data={"application": str(app.id), "salary_income": "100000"},
            context={"request": request},
        )
        assert serializer.is_valid(), serializer.errors
        analysis = serializer.save(tenant=tenant_a)
        document = analysis.documents.get()
        assert document.label == "Bulletin de mars"

        request.data = QueryDict(mutable=True)
        refused = FinancialAnalysisSerializer(
            data={"application": str(app.id), "salary_income": "100000"},
            context={"request": request},
        )
        assert refused.is_valid(), refused.errors
        with pytest.raises(ValidationError):
            refused.save(tenant=tenant_a)
        assert FinancialAnalysis.objects.filter(application=app).count() == 1


@pytest.mark.django_db
def test_dossier_profile_drives_the_analysis(tenant_a, client_a, product_a):
    with tenant_context(tenant_a.id):
        app = CreditApplication.objects.create(
            tenant=tenant_a, client=client_a, product=product_a,
            reference="FA-PROFILE", amount_requested=100000, duration_months=12,
            earning_path="MIXTE", employer_name="Atelier Nord",
            employer_sector="Bâtiment", contract_type="DAILY",
            job_seniority_months=18, salary_domiciliation=True,
            activity_name="Couture", tax_regime="INFORMAL",
            activity_start_date=date(2024, 1, 15),
        )
        analysis = FinancialAnalysis.objects.create(
            tenant=tenant_a, application=app, reference_period="MONTHLY",
            individual_profile="SALARIE", has_side_activity=False,
            employer_name="Ancien", salary_income=100000, activity_turnover=50000,
        )
        assert analysis.individual_profile == "MIXTE"
        assert analysis.has_side_activity is True
        assert analysis.employer_name == "Atelier Nord"
        assert analysis.employer_sector == "Bâtiment"
        assert analysis.employment_type == "DAILY"
        assert analysis.employment_seniority_months == 18
        assert analysis.salary_paid_through_bank is True
        assert analysis.activity_name == "Couture"
        assert analysis.activity_is_formal is False
        assert analysis.activity_business_age_months > 0

        app.earning_path = "SALARIE"
        app.save(update_fields=["earning_path"])
        analysis.individual_profile = "MIXTE"
        analysis.has_side_activity = True
        analysis.save()
        assert analysis.individual_profile == "SALARIE"
        assert analysis.has_side_activity is False

        app.earning_path = ""
        app.save(update_fields=["earning_path"])
        analysis.employer_name = "Saisi dans l'analyse"
        analysis.save()
        assert analysis.employer_name == "Saisi dans l'analyse"

        serializer = CreditApplicationSerializer(
            app,
            data={"children_count": "3", "dependents_count": "1", "spouse_first_name": "Awa"},
            partial=True,
        )
        assert not serializer.is_valid()
        assert "children_count" in serializer.errors
        serializer = CreditApplicationSerializer(
            app,
            data={"children_count": "1", "dependents_count": "2", "spouse_first_name": "Awa", "spouse_phone": "0700", "spouse_profession": "Couture"},
            partial=True,
        )
        assert serializer.is_valid(), serializer.errors
        kept_name = client_a.spouse_last_name
        serializer.save()
        client_a.refresh_from_db()
        assert client_a.spouse_first_name == "Awa"
        assert client_a.spouse_phone == "0700"
        assert client_a.spouse_profession == "Couture"
        assert client_a.spouse_last_name == kept_name


def test_extra_household_lines_enter_the_totals():
    details = validate_details({
        "extra_income": [
            {"label": " Bourse ", "amount": "15000"},
            {"label": "", "amount": ""},
        ],
        "extra_charges": [{"label": "Garde d'enfants", "amount": "8000"}],
    })
    assert details["extra_income"] == [{"label": "Bourse", "amount": "15000"}]
    analysis = FinancialAnalysis(
        analysis_details=details,
        salary_income=Decimal("100000"),
        rent_expense=Decimal("20000"),
    )
    assert analysis.total_income == Decimal("115000")
    assert analysis.total_household_charges == Decimal("28000")
    with pytest.raises(ValidationError):
        validate_details({"extra_charges": [{"label": "Loyer école", "amount": ""}]})


@pytest.mark.django_db
def test_second_activity_takes_the_same_turnover_stress(tenant_a, client_a, product_a):
    with tenant_context(tenant_a.id):
        app = CreditApplication.objects.create(
            tenant=tenant_a, client=client_a, product=product_a,
            reference="FA-STRESS-2", amount_requested=Decimal("100000"), duration_months=12,
        )
        analysis = FinancialAnalysis.objects.create(
            tenant=tenant_a, application=app, reference_period="MONTHLY",
            individual_profile="INDEPENDANT", has_side_activity=True,
            activity_turnover=Decimal("1800000"), activity_expenses=Decimal("1300000"),
            informal_income_weight=Decimal("70"), new_installment=Decimal("1"),
            analysis_details={
                "extra_activities": [{"label": "Recharge", "turnover": "120000", "expenses": "80000"}],
            },
        )
        metrics = compute_metrics(analysis, AnalysisThreshold.for_tenant(tenant_a.id))
        assert metrics["weighted_income"] == Decimal("378000.00")
        stressed_income = (
            metrics["stress_residual"]
            + metrics["household_charges_monthly"]
            + metrics["total_cash_effort"]
        )
        assert stressed_income == Decimal("109200.00")


@pytest.mark.django_db
def test_uncovered_capacity_blocks_the_submission_checklist(tenant_a, client_a, product_a):
    from apps.credits.analysis_validation import capacity_blocks_submission
    from apps.credits.instruction_policy import build_readiness

    with tenant_context(tenant_a.id):
        app = CreditApplication.objects.create(
            tenant=tenant_a, client=client_a, product=product_a,
            reference="FA-CAP-BLOCK", amount_requested=Decimal("5000000"),
            duration_months=12, interest_rate=Decimal("0"),
        )
        reference = FinancialAnalysis.objects.create(
            tenant=tenant_a, application=app, is_reference=True,
            recommendation=FinancialAnalysis.Recommendation.FAVORABLE,
            individual_profile="INDEPENDANT", has_side_activity=True,
            activity_turnover=Decimal("100000"), activity_expenses=Decimal("0"),
            informal_income_weight=Decimal("100"),
        )
        assert capacity_blocks_submission(app, reference)
        ready = build_readiness(app)
        capacity = next(item for item in ready["checks"] if item["key"] == "repayment_capacity")
        assert capacity["ok"] is False
        assert capacity["blocking"] is True
        assert ready["ready"] is False


def test_observed_payment_delays_stay_whole_days_and_follow_the_analysis():
    from types import SimpleNamespace
    from apps.credits.dossier_pdf import _observed_payment_delays

    assert validate_details({
        "observed_client_payment_days": "0",
        "observed_supplier_payment_days": "7",
    })["observed_client_payment_days"] == "0"
    assert validate_details({"observed_supplier_payment_days": ""})["observed_supplier_payment_days"] == ""
    with pytest.raises(ValidationError):
        validate_details({"observed_client_payment_days": "1.5"})

    application = SimpleNamespace(
        client=SimpleNamespace(client_type="INDIVIDUAL"),
        avg_client_payment_days=0,
        avg_supplier_payment_days=7,
    )
    assert _observed_payment_delays(application, SimpleNamespace(analysis_details={})) == [
        ("Délai moyen paiement clients", "0 j"),
        ("Délai moyen paiement fournisseurs", "7 j"),
    ]
    assert _observed_payment_delays(application, SimpleNamespace(analysis_details={
        "observed_client_payment_days": "4",
        "observed_supplier_payment_days": "",
    })) == [("Délai moyen paiement clients", "4 j")]
    company = SimpleNamespace(
        client=SimpleNamespace(client_type="CORPORATE"),
        avg_client_payment_days=3,
        avg_supplier_payment_days=9,
    )
    assert _observed_payment_delays(company, SimpleNamespace(analysis_details={})) == []


@pytest.mark.django_db
def test_informal_activity_drops_registration_files(tenant_a, client_a, product_a):
    from django.core.files.uploadedfile import SimpleUploadedFile

    with tenant_context(tenant_a.id):
        app = CreditApplication.objects.create(
            tenant=tenant_a, client=client_a, product=product_a,
            reference="FA-REG-SCAN", amount_requested=Decimal("100000"), duration_months=12,
            tax_regime="SYNTHETIC", activity_ifu="IFU-1",
        )
        app.activity_ifu_scan = SimpleUploadedFile("ifu.pdf", b"%PDF-1.4")
        app.save()
        app.refresh_from_db()
        assert app.activity_ifu == "IFU-1"
        assert app.activity_ifu_scan.name
        app.tax_regime = "INFORMAL"
        app.save()
        app.refresh_from_db()
        assert app.activity_ifu == ""
        assert not app.activity_ifu_scan.name


def test_informal_activity_quality_score_follows_the_level():
    from types import SimpleNamespace
    from apps.credits.analytics import _information_quality_score

    analysis = SimpleNamespace(
        information_quality="DECLARED",
        financial_documents_verified=True,
        field_visit_confirmed=True,
        stock_count_verified=True,
        cash_position_verified=True,
        is_corporate=False,
        is_individual=True,
        has_side_activity=True,
        individual_profile="INDEPENDANT",
        application=SimpleNamespace(tax_regime="INFORMAL"),
    )
    assert _information_quality_score(analysis) == Decimal("30")
    analysis.information_quality = "VERIFIED"
    assert _information_quality_score(analysis) == Decimal("80")


def test_inventory_stock_value_counts_complete_lines():
    from apps.credits.analysis_details import inventory_stock_value

    assert inventory_stock_value({"products": [
        {"quantity": "10", "unit_cost": "100"},
        {"quantity": "2", "unit_cost": ""},
    ]}) == Decimal("1000.00")
    assert inventory_stock_value({"products": []}) is None
    assert inventory_stock_value({}) is None


def test_consulted_document_flags_stay_empty_or_yes():
    saved = validate_details({
        "consulted_sales_book": "yes",
        "consulted_sales_invoices": "",
        "consulted_bank_statements": "yes",
    })
    assert saved["consulted_sales_book"] == "yes"
    assert saved["consulted_sales_invoices"] == ""
    assert saved["consulted_bank_statements"] == "yes"
    with pytest.raises(ValidationError):
        validate_details({"consulted_sales_book": "no"})
