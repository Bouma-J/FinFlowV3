"""À la sélection d'un client, les crédits déjà mis en place sont vérifiés."""
from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth.models import Permission
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.common.tenancy import tenant_context
from apps.credits.client_credits import received_credits
from apps.credits.models import CreditApplication, Loan
from apps.tenants.models import Agency

pytestmark = pytest.mark.django_db


def test_selecting_a_client_checks_credits_already_received(tenant_a, product_a, client_a):
    with tenant_context(tenant_a.pk):
        agency = Agency.objects.create(tenant=tenant_a, code="CRD-A", name="Agence crédits")
        actor = User.objects.create_user(username="credit-history", tenant=tenant_a, data_scope="TENANT")
        actor.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="credits", codename="view_creditapplication",
        ))
        received = CreditApplication.objects.create(
            tenant=tenant_a, product=product_a, client=client_a, agency=agency,
            amount_requested=Decimal("80000"), duration_months=6, currency="XOF",
            status=CreditApplication.Status.DISBURSED, created_by=actor, reference="DOS-RECU",
            cbs_demande_ref="CBS-1",
        )
        Loan.objects.create(
            tenant=tenant_a, application=received, principal=Decimal("80000"),
            interest_rate=Decimal("12"), duration_months=6,
            disbursed_at=date(2026, 1, 15), first_due_date=date(2026, 2, 15),
            status=Loan.Status.ACTIVE, cbs_demande_ref="CBS-1",
        )
        CreditApplication.objects.create(
            tenant=tenant_a, product=product_a, client=client_a, agency=agency,
            amount_requested=Decimal("10000"), duration_months=3, currency="XOF",
            status=CreditApplication.Status.SUBMITTED, created_by=actor, reference="DOS-COURS",
        )
        situation = {"settled": False, "outstanding": Decimal("50000"), "currency": "XOF"}
        with patch("apps.credits.client_credits.get_loan_status", return_value=situation) as checked:
            result = received_credits(client=client_a, tenant_id=tenant_a.pk)
            api = APIClient()
            api.force_authenticate(actor)
            response = api.get("/api/v1/credit-applications/client-credits/", {"client": str(client_a.pk)})
        checked.assert_called()
        assert result["received_count"] == 1
        assert result["active_count"] == 1
        assert result["open_request_count"] == 1
        assert result["credits"][0]["application_reference"] == "DOS-RECU"
        assert result["credits"][0]["cbs_status_label"] == "Encore ouvert au CBS"
        assert result["credits"][0]["cbs_outstanding"] == "50000"
    assert response.status_code == 200, response.content
    assert response.data["received_count"] == 1
    assert response.data["credits"][0]["cbs_loan_reference"] == "CBS-1"
