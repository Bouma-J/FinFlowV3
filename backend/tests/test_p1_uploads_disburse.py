"""P1 — validation uploads + décaissement sous verrou."""
from datetime import date
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.exceptions import ValidationError

from apps.common.tenancy import tenant_context
from apps.common.upload_validation import assert_upload_meta, validate_uploaded_file
from apps.credits.models import CreditApplication, Loan
from apps.credits.services import disburse_application

pytestmark = pytest.mark.django_db


def test_reject_exe_upload():
    f = SimpleUploadedFile(
        "malware.exe",
        b"MZ\x90\x00fake-exe",
        content_type="application/octet-stream",
    )
    with pytest.raises(ValidationError):
        validate_uploaded_file(f, check_quota=False)


def test_reject_pdf_extension_with_jpeg_magic():
    f = SimpleUploadedFile(
        "fake.pdf",
        b"\xff\xd8\xff\xe0" + b"\x00" * 20,
        content_type="application/pdf",
    )
    with pytest.raises(ValidationError, match="contenu"):
        validate_uploaded_file(f, check_quota=False)


def test_accept_real_pdf_header():
    f = SimpleUploadedFile(
        "contrat.pdf",
        b"%PDF-1.4\n%fake",
        content_type="application/pdf",
    )
    out = validate_uploaded_file(f, check_quota=False)
    assert out.name.endswith(".pdf")


def test_assert_upload_meta_presign():
    name = assert_upload_meta(filename="../../evil.pdf", size=100)
    assert name == "evil.pdf"
    with pytest.raises(ValidationError):
        assert_upload_meta(filename="x.exe")
    with pytest.raises(ValidationError):
        assert_upload_meta(filename="big.pdf", size=30 * 1024 * 1024)


def test_disburse_idempotent_under_lock(tenant_a, product_a, client_a, monkeypatch):
    with tenant_context(tenant_a.id):
        app = CreditApplication.objects.create(
            tenant=tenant_a,
            client=client_a,
            product=product_a,
            reference="P1-DISB-1",
            amount_requested=Decimal("100000"),
            amount_approved=Decimal("100000"),
            duration_months=12,
            interest_rate=Decimal("10"),
            status=CreditApplication.Status.APPROVED,
            currency="XOF",
        )

    monkeypatch.setattr(
        "apps.credits.services._assert_disbursement_prerequisites",
        lambda _a: None,
    )

    with tenant_context(tenant_a.id):
        loan1 = disburse_application(app, disburse_date=date.today(), skip_cbs=True)
        loan2 = disburse_application(app, disburse_date=date.today(), skip_cbs=True)
        assert loan1.id == loan2.id
        assert Loan.objects.filter(application=app).count() == 1
        app.refresh_from_db()
        assert app.status == CreditApplication.Status.DISBURSED
