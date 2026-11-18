"""Crédits déjà mis en place pour un client, relus dans le CBS quand une référence existe."""
from django.utils import timezone

from apps.corebanking.services import CoreBankingError, get_loan_status, user_message_for_cbs_error
from apps.tenants.currency import tenant_currency

from .amounts import reference_amount
from .models import CreditApplication, Loan

RECEIVED_STATUSES = {
    CreditApplication.Status.DISBURSED,
    CreditApplication.Status.CLOSED,
}
OPEN_EXCLUDED = {
    CreditApplication.Status.CANCELLED,
    CreditApplication.Status.REJECTED,
}


def _loan_reference(application, loan):
    values = []
    if loan is not None:
        values.extend([
            loan.cbs_demande_ref,
            loan.core_banking_reference,
            loan.cbs_contract_number,
            loan.cbs_demande_number,
            loan.cbs_external_id,
        ])
    values.extend([application.cbs_demande_ref, application.cbs_contract_number])
    for value in values:
        text = (value or "").strip()
        if text:
            return text
    return ""


def _client_ids(client):
    return {
        "code_adherent": (getattr(client, "cbs_client_id", None) or "").strip() or None,
        "num_manuel": (getattr(client, "cbs_account_number", None) or "").strip() or None,
        "num_piece_identite": (getattr(client, "national_id", None) or "").strip() or None,
    }


def _verify_cbs(tenant_id, client, application, loan, reference, currency):
    if not reference:
        return {
            "cbs_loan_reference": "",
            "cbs_settled": None,
            "cbs_outstanding": None,
            "cbs_currency": currency,
            "cbs_error": None,
            "cbs_status_label": "Pas de référence CBS",
        }
    try:
        situation = get_loan_status(tenant_id, reference, currency=currency, **_client_ids(client))
    except CoreBankingError as exc:
        return {
            "cbs_loan_reference": reference,
            "cbs_settled": None,
            "cbs_outstanding": None,
            "cbs_currency": currency,
            "cbs_error": user_message_for_cbs_error(exc),
            "cbs_status_label": "Vérification CBS indisponible",
        }
    settled = bool(situation.get("settled"))
    outstanding = situation.get("outstanding")
    return {
        "cbs_loan_reference": reference,
        "cbs_settled": settled,
        "cbs_outstanding": None if outstanding is None else str(outstanding),
        "cbs_currency": situation.get("currency") or currency,
        "cbs_error": None,
        "cbs_status_label": "Soldé au CBS" if settled else "Encore ouvert au CBS",
    }


def received_credits(*, client, tenant_id, exclude_application_id=None):
    """Crédits dont le client a déjà bénéficié, avec la situation CBS de chacun."""
    applications = (
        CreditApplication.all_tenants.filter(tenant_id=tenant_id, client_id=client.pk)
        .select_related("product")
        .order_by("-created_at")
    )
    if exclude_application_id:
        applications = applications.exclude(pk=exclude_application_id)
    loans = {
        loan.application_id: loan
        for loan in Loan.all_tenants.filter(
            tenant_id=tenant_id, application__client_id=client.pk,
        ).select_related("application")
    }
    credits = []
    open_requests = 0
    for application in applications:
        loan = loans.get(application.pk)
        received = loan is not None or application.status in RECEIVED_STATUSES
        if not received:
            if application.status not in OPEN_EXCLUDED:
                open_requests += 1
            continue
        currency = application.currency or tenant_currency(tenant_id)
        reference = _loan_reference(application, loan)
        credits.append({
            "application_id": str(application.pk),
            "application_reference": application.reference,
            "application_status": application.status,
            "application_status_display": application.get_status_display(),
            "product_label": application.product.label if application.product_id else "",
            "amount": str(reference_amount(application) or 0),
            "currency": currency,
            "loan_id": str(loan.pk) if loan else None,
            "loan_status": loan.status if loan else None,
            "loan_status_display": loan.get_status_display() if loan else None,
            "disbursed_at": loan.disbursed_at.isoformat() if loan and loan.disbursed_at else None,
            **_verify_cbs(tenant_id, client, application, loan, reference, currency),
        })

    def _kind(row):
        if row["loan_status"] == Loan.Status.DEFAULTED:
            return "defaulted"
        if row["loan_status"] == Loan.Status.CLOSED or row["application_status"] == CreditApplication.Status.CLOSED:
            return "settled"
        return "active"

    active = sum(1 for row in credits if _kind(row) == "active")
    settled = sum(1 for row in credits if _kind(row) == "settled")
    defaulted = sum(1 for row in credits if _kind(row) == "defaulted")
    return {
        "client_id": str(client.pk),
        "checked_at": timezone.now().isoformat(),
        "received_count": len(credits),
        "active_count": active,
        "settled_count": settled,
        "defaulted_count": defaulted,
        "open_request_count": open_requests,
        "credits": credits,
    }
