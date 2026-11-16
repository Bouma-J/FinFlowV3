"""Synthèse collatéral : haircuts et piliers séparés."""
from datetime import date
from decimal import Decimal

import pytest

from apps.common.tenancy import tenant_context
from apps.credits.collateral import build_collateral_summary, retained_value
from apps.credits.models import AnalysisThreshold, CreditApplication
from apps.guarantees.models import Guarantee, PledgeCategory
from apps.sureties.models import Surety, SuretyEngagement

pytestmark = pytest.mark.django_db


def test_retained_value_applies_vehicle_haircut(tenant_a, client_a, product_a):
    with tenant_context(tenant_a.id):
        th = AnalysisThreshold.for_tenant(tenant_a.id)
        th.haircut_vehicle = Decimal("30")
        th.save(update_fields=["haircut_vehicle"])

        application = CreditApplication.objects.create(
            tenant=tenant_a,
            reference="D-COL",
            client=client_a,
            product=product_a,
            amount_requested=Decimal("1000000"),
            duration_months=12,
        )
        g = Guarantee.objects.create(
            tenant=tenant_a,
            client=client_a,
            application=application,
            guarantee_type=Guarantee.GuaranteeType.PLEDGE,
            pledge_category=PledgeCategory.VEHICLE,
            description="Véhicule",
            current_value=Decimal("1000000"),
            status=Guarantee.Status.ACTIVE,
            reference="GAR-VEH",
        )
        assert retained_value(g, th) == Decimal("700000.00")

        summary = build_collateral_summary(application, th)
        assert summary["guarantees_retained_total"] == "700000.00"
        assert summary["guarantee_coverage_pct"] == "70.00"
        assert summary["sureties_total"] == "0"


def test_sureties_are_separate_pillar(tenant_a, client_a, product_a):
    with tenant_context(tenant_a.id):
        th = AnalysisThreshold.for_tenant(tenant_a.id)
        th.haircut_mortgage = Decimal("0")
        th.save(update_fields=["haircut_mortgage"])

        application = CreditApplication.objects.create(
            tenant=tenant_a,
            reference="D-SURE",
            client=client_a,
            product=product_a,
            amount_requested=Decimal("500000"),
            duration_months=12,
        )
        Guarantee.objects.create(
            tenant=tenant_a,
            client=client_a,
            application=application,
            guarantee_type=Guarantee.GuaranteeType.MORTGAGE,
            description="Terrain",
            current_value=Decimal("400000"),
            status=Guarantee.Status.ACTIVE,
            reference="GAR-M",
        )
        surety = Surety.objects.create(
            tenant=tenant_a,
            surety_type=Surety.SuretyType.PHYSICAL,
            first_name="Jean",
            last_name="Caution",
        )
        SuretyEngagement.objects.create(
            tenant=tenant_a,
            surety=surety,
            application=application,
            amount=Decimal("200000"),
            status=SuretyEngagement.Status.ACTIVE,
        )

        summary = build_collateral_summary(application, th)
        assert summary["guarantees_retained_total"] == "400000.00"
        assert summary["sureties_total"] == "200000.00"
        # Couverture garanties ne fusionne pas les cautions.
        assert summary["guarantee_coverage_pct"] == "80.00"
        assert summary["surety_coverage_pct"] == "40.00"


def test_inactive_guarantees_excluded(tenant_a, client_a, product_a):
    with tenant_context(tenant_a.id):
        th = AnalysisThreshold.for_tenant(tenant_a.id)
        application = CreditApplication.objects.create(
            tenant=tenant_a,
            reference="D-INACT",
            client=client_a,
            product=product_a,
            amount_requested=Decimal("500000"),
            duration_months=12,
        )
        Guarantee.objects.create(
            tenant=tenant_a,
            client=client_a,
            application=application,
            guarantee_type=Guarantee.GuaranteeType.MORTGAGE,
            description="Inactif",
            current_value=Decimal("900000"),
            status=Guarantee.Status.RELEASED,
            reference="GAR-D",
        )
        summary = build_collateral_summary(application, th)
        assert summary["guarantees_retained_total"] == "0"
        assert summary["guarantees"] == []


def test_mortgage_rank_and_insurance_alert_without_changing_coverage(tenant_a, client_a, product_a):
    with tenant_context(tenant_a.id):
        th = AnalysisThreshold.for_tenant(tenant_a.id)
        th.haircut_mortgage = Decimal("0")
        th.save(update_fields=["haircut_mortgage"])
        application = CreditApplication.objects.create(
            tenant=tenant_a,
            reference="D-RANK",
            client=client_a,
            product=product_a,
            amount_requested=Decimal("1000000"),
            duration_months=12,
            first_due_date=date(2026, 1, 15),
        )
        Guarantee.objects.create(
            tenant=tenant_a,
            client=client_a,
            application=application,
            guarantee_type=Guarantee.GuaranteeType.MORTGAGE,
            description="Maison",
            current_value=Decimal("1000000"),
            status=Guarantee.Status.ACTIVE,
            reference="GAR-R",
            mortgage_rank="2",
            prior_lien_amount=Decimal("200000"),
            is_insured=True,
            insured_amount=Decimal("700000"),
            insurance_end_date=date(2026, 6, 1),
        )
        summary = build_collateral_summary(application, th)
        assert summary["guarantee_coverage_pct"] == "100.00"
        text = " ".join(summary["alerts"])
        assert "2e rang" in text
        assert "inscriptions antérieures" in text
        assert "montant assuré" in text
        assert "avant la fin du crédit" in text


def test_empty_insurance_and_first_rank_stay_quiet(tenant_a, client_a, product_a):
    with tenant_context(tenant_a.id):
        th = AnalysisThreshold.for_tenant(tenant_a.id)
        application = CreditApplication.objects.create(
            tenant=tenant_a,
            reference="D-QUIET",
            client=client_a,
            product=product_a,
            amount_requested=Decimal("500000"),
            duration_months=12,
            first_due_date=date(2026, 1, 15),
        )
        Guarantee.objects.create(
            tenant=tenant_a,
            client=client_a,
            application=application,
            guarantee_type=Guarantee.GuaranteeType.MORTGAGE,
            description="Terrain",
            current_value=Decimal("500000"),
            status=Guarantee.Status.ACTIVE,
            reference="GAR-Q",
            mortgage_rank="1",
            is_insured=True,
        )
        summary = build_collateral_summary(application, th)
        text = " ".join(summary["alerts"])
        assert "rang" not in text
        assert "assurance" not in text
        assert "montant assuré" not in text


def test_surety_charges_reduce_the_twelve_month_income(tenant_a, client_a, product_a):
    with tenant_context(tenant_a.id):
        application = CreditApplication.objects.create(
            tenant=tenant_a,
            reference="D-CAP",
            client=client_a,
            product=product_a,
            amount_requested=Decimal("500000"),
            duration_months=12,
        )
        surety = Surety.objects.create(
            tenant=tenant_a,
            surety_type=Surety.SuretyType.PHYSICAL,
            first_name="Awa",
            last_name="Caution",
            estimated_income=Decimal("100000"),
            monthly_charges=Decimal("40000"),
            existing_monthly_payments=Decimal("20000"),
            commitment_ceiling=Decimal("2000000"),
        )
        engagement = SuretyEngagement.objects.create(
            tenant=tenant_a,
            surety=surety,
            application=application,
            amount=Decimal("500000"),
            status=SuretyEngagement.Status.ACTIVE,
        )
        summary = build_collateral_summary(application)
        assert any("après charges" in item for item in summary["alerts"])
        assert summary["guarantee_coverage_pct"] is None or summary["guarantees_retained_total"] == "0"

        engagement.amount = Decimal("480000")
        engagement.save(update_fields=["amount"])
        quiet = build_collateral_summary(application)
        assert not any("après charges" in item for item in quiet["alerts"])

        surety.estimated_income = None
        surety.save(update_fields=["estimated_income"])
        engagement.amount = Decimal("900000")
        engagement.save(update_fields=["amount"])
        empty_income = build_collateral_summary(application)
        assert not any("revenu" in item for item in empty_income["alerts"])
