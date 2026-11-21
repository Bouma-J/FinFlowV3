"""Services métier : formalisation / constitution juridique des garanties.

Une garantie n'est active qu'une fois sa formalisation clôturée.
La politique filiale ``require_formalization_before_disbursement`` peut en
plus bloquer la mise en place via ``missing_formalizations_for_disbursement``.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.workflow.models import WorkflowDefinition
from apps.workflow.services import WorkflowError, start_workflow

from .models import (
    FormalizationFee,
    Guarantee,
    GuaranteeFormalizationRequest,
    GuaranteeMovement,
)
from .process_services import ProcessError, _next_reference

_OPEN_FORM_STATUSES = (
    GuaranteeFormalizationRequest.Status.DRAFT,
    GuaranteeFormalizationRequest.Status.IN_PROGRESS,
    GuaranteeFormalizationRequest.Status.IN_APPROVAL,
    GuaranteeFormalizationRequest.Status.RETURNED,
    GuaranteeFormalizationRequest.Status.APPROVED,
)

# Types de garanties typiquement soumis à publicité / formalisation juridique.
_FORMALIZABLE_TYPES = (
    Guarantee.GuaranteeType.MORTGAGE,
    Guarantee.GuaranteeType.PLEDGE,
    Guarantee.GuaranteeType.LIEN,
)


def missing_formalizations_for_disbursement(application) -> list[str]:
    """
    Références des garanties encore non formalisées pour un dossier.
    Retourne [] si aucune garantie formalisable n'est rattachée.
    """
    qs = Guarantee.objects.filter(
        application_id=application.pk,
        guarantee_type__in=_FORMALIZABLE_TYPES,
        formalized_at__isnull=True,
        status__in=(
            Guarantee.Status.PENDING,
            Guarantee.Status.ACTIVE,
        ),
    )
    return [
        g.reference or str(g.pk)
        for g in qs.only("id", "reference")
    ]

_EDITABLE_STATUSES = (
    GuaranteeFormalizationRequest.Status.DRAFT,
    GuaranteeFormalizationRequest.Status.IN_PROGRESS,
    GuaranteeFormalizationRequest.Status.RETURNED,
)

def _awaiting_formalization():
    """Garantie pas encore active : la formalisation n'est pas clôturée."""
    return Q(formalized_at__isnull=True) & Q(
        status__in=(Guarantee.Status.PENDING, Guarantee.Status.ACTIVE)
    )


_LEGAL_STAGE_ORDER = [
    GuaranteeFormalizationRequest.LegalStage.NOT_SENT,
    GuaranteeFormalizationRequest.LegalStage.AT_NOTARY,
    GuaranteeFormalizationRequest.LegalStage.AWAITING_SIGNATURE,
    GuaranteeFormalizationRequest.LegalStage.SIGNED,
    GuaranteeFormalizationRequest.LegalStage.PENDING_REGISTRATION,
    GuaranteeFormalizationRequest.LegalStage.REGISTERED,
    GuaranteeFormalizationRequest.LegalStage.DONE,
]


def ensure_formalization_document_categories(tenant) -> int:
    from apps.documents.category_seed import ensure_document_categories

    return ensure_document_categories(
        tenant,
        (
            ("FORM_PROJET_ACTE", "Projet d'acte de constitution"),
            ("FORM_ACTE_SIGNE", "Acte de constitution signé"),
            ("FORM_ENREGISTREMENT", "Preuve d'enregistrement / publicité"),
            ("FORM_EXPERTISE", "Expertise / évaluation"),
            ("FORM_TITRE", "Titre / pièce du bien"),
            ("FORM_ID", "Pièce d'identité / quitus"),
            ("FORM_OTHER", "Autre pièce formalisation"),
        ),
    )


def formalization_documents(request: GuaranteeFormalizationRequest):
    from django.contrib.contenttypes.models import ContentType

    from apps.documents.models import Document

    ct = ContentType.objects.get_for_model(GuaranteeFormalizationRequest)
    return Document.objects.filter(
        content_type=ct, object_id=request.id
    ).select_related("category", "uploaded_by")


def _assert_form_editable(request: GuaranteeFormalizationRequest):
    if request.status not in _EDITABLE_STATUSES:
        raise ProcessError(
            "Seuls les dossiers brouillon, en cours ou retournés peuvent être modifiés."
        )


def _parse_date(value, label="date"):
    if isinstance(value, str) and value.strip():
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError as exc:
            raise ProcessError(f"{label} invalide.") from exc
    if value:
        return value
    return None


def _create_fee_lines(request: GuaranteeFormalizationRequest, fees):
    if not fees:
        return
    if not isinstance(fees, list):
        raise ProcessError("fees doit être une liste.")
    for item in fees:
        if not isinstance(item, dict):
            raise ProcessError("Chaque frais doit être un objet.")
        try:
            amount = Decimal(str(item.get("amount")))
        except (InvalidOperation, TypeError) as exc:
            raise ProcessError("Le montant du frais est obligatoire.") from exc
        fee_type = (item.get("fee_type") or FormalizationFee.FeeType.OTHER).strip()
        if fee_type not in FormalizationFee.FeeType.values:
            fee_type = FormalizationFee.FeeType.OTHER
        payer = (item.get("payer") or FormalizationFee.Payer.CLIENT).strip()
        if payer not in FormalizationFee.Payer.values:
            payer = FormalizationFee.Payer.CLIENT
        label = (item.get("label") or "").strip()
        if not label:
            label = dict(FormalizationFee.FeeType.choices).get(fee_type, "Frais")
        FormalizationFee.objects.create(
            tenant_id=request.tenant_id,
            formalization=request,
            fee_type=fee_type,
            label=label,
            amount=amount,
            payer=payer,
            fee_date=item.get("fee_date") or None,
            recoverable=bool(item.get("recoverable", True)),
            notes=(item.get("notes") or "").strip(),
        )


@transaction.atomic
def initiate_formalization_request(
    *,
    guarantee: Guarantee,
    user,
    comment="",
    notary_name="",
    notary_reference="",
    fees=None,
    as_draft=True,
):
    """
    Ouvre un dossier de formalisation sur une garantie encore non active,
    rattachée à un dossier de crédit.

    La garantie reste en attente : elle ne devient active qu'à la clôture.
    """
    if guarantee.formalized_at:
        raise ProcessError("Cette garantie est déjà formalisée.")
    if guarantee.status not in (
        Guarantee.Status.PENDING,
        Guarantee.Status.ACTIVE,
    ):
        raise ProcessError(
            "Seule une garantie en attente de formalisation peut "
            "faire l'objet d'une formalisation."
        )
    if not guarantee.application_id:
        raise ProcessError(
            "La formalisation ne concerne que les garanties attachées "
            "à un dossier de crédit."
        )
    from .busy import guarantee_busy

    busy = guarantee_busy(guarantee)
    if busy:
        raise ProcessError(busy["message"])
    if guarantee.status != Guarantee.Status.PENDING:
        guarantee.status = Guarantee.Status.PENDING
        guarantee.save(update_fields=["status", "updated_at"])

    ensure_formalization_document_categories(guarantee.tenant)
    req = GuaranteeFormalizationRequest(
        guarantee=guarantee,
        application_id=guarantee.application_id,
        agency_id=guarantee.agency_id,
        status=GuaranteeFormalizationRequest.Status.DRAFT,
        legal_stage=GuaranteeFormalizationRequest.LegalStage.NOT_SENT,
        notary_name=(notary_name or "").strip(),
        notary_reference=(notary_reference or "").strip(),
        comment=comment or "",
        created_by=user,
        updated_by=user,
    )
    req.reference = _next_reference(
        "FORM", GuaranteeFormalizationRequest, guarantee.tenant_id
    )
    req.save()
    _create_fee_lines(req, fees or [])
    req.apply_fees_snapshot(persist=True)
    if as_draft:
        return req
    return start_formalization_progress(req, user=user)


def formalization_compose_context(*, client=None, application=None) -> dict:
    """
    Contexte pour composer une formalisation :
    recherche par client ou par dossier de crédit → garanties attachées.
    """
    from apps.credits.models import CreditApplication
    from apps.guarantees.serializers import GuaranteeSerializer

    if application is None and client is None:
        raise ProcessError("Indiquez un client ou un dossier de crédit.")

    if application is not None:
        client = application.client
        apps_qs = CreditApplication.objects.filter(pk=application.pk)
        guarantees_qs = Guarantee.objects.filter(
            application_id=application.pk,
        ).filter(_awaiting_formalization())
    else:
        apps_qs = CreditApplication.objects.filter(client_id=client.pk)
        guarantees_qs = Guarantee.objects.filter(
            client_id=client.pk,
            application_id__isnull=False,
        ).filter(_awaiting_formalization())

    from .busy import busy_map

    guarantees_qs = guarantees_qs.select_related(
        "application", "agency", "client"
    ).order_by("-created_at")
    occupied = busy_map(list(guarantees_qs.values_list("id", flat=True)))

    # Dossiers ayant au moins une garantie attachée (ou le dossier ciblé).
    if application is None:
        app_ids_with_gar = set(
            Guarantee.objects.filter(
                client_id=client.pk,
                application_id__isnull=False,
            )
            .filter(_awaiting_formalization())
            .values_list("application_id", flat=True)
        )
        apps_qs = apps_qs.filter(pk__in=app_ids_with_gar)

    apps = apps_qs.select_related("product").order_by("-created_at")
    gar_count_by_app: dict = {}
    for g in guarantees_qs:
        if g.application_id:
            gar_count_by_app[g.application_id] = (
                gar_count_by_app.get(g.application_id, 0) + 1
            )

    credits = []
    for app in apps:
        credits.append(
            {
                "application_id": str(app.pk),
                "application_reference": app.reference,
                "application_status": app.status,
                "application_status_display": app.get_status_display(),
                "product_label": (
                    getattr(app.product, "label", "") if app.product_id else ""
                ),
                "amount": str(app.amount_requested or 0),
                "currency": getattr(app, "currency", None) or "XOF",
                "guarantees_count": gar_count_by_app.get(app.pk, 0),
            }
        )

    guarantees_data = GuaranteeSerializer(guarantees_qs, many=True).data
    for row in guarantees_data:
        info = occupied.get(str(row["id"]))
        row["process_busy"] = info
        row["formalization_busy"] = bool(info)

    return {
        "client_id": str(client.pk),
        "client_display": getattr(client, "display_name", str(client)),
        "application_id": str(application.pk) if application else None,
        "application_reference": (
            application.reference if application else None
        ),
        "credits": credits,
        "guarantees": guarantees_data,
    }


@transaction.atomic
def start_formalization_progress(request: GuaranteeFormalizationRequest, *, user=None):
    """Passe de brouillon à en cours (suivi juridique)."""
    if request.status not in (
        GuaranteeFormalizationRequest.Status.DRAFT,
        GuaranteeFormalizationRequest.Status.RETURNED,
    ):
        raise ProcessError("Ce dossier ne peut pas être démarré.")
    request.status = GuaranteeFormalizationRequest.Status.IN_PROGRESS
    if user is not None:
        request.updated_by = user
    request.save(
        update_fields=["status", "updated_by", "updated_at"]
        if user
        else ["status", "updated_at"]
    )
    return request


@transaction.atomic
def update_formalization_request(request: GuaranteeFormalizationRequest, *, user=None, **fields):
    _assert_form_editable(request)
    for key in (
        "comment",
        "notary_name",
        "notary_reference",
        "registration_number",
        "registration_authority",
    ):
        if key in fields and fields[key] is not None:
            setattr(request, key, str(fields[key]).strip())
    if "sent_to_notary_at" in fields:
        request.sent_to_notary_at = _parse_date(
            fields["sent_to_notary_at"], "Date transmission notaire"
        )
    if "expected_return_date" in fields:
        request.expected_return_date = _parse_date(
            fields["expected_return_date"], "Date retour prévu"
        )
    if "registration_date" in fields:
        request.registration_date = _parse_date(
            fields["registration_date"], "Date d'enregistrement"
        )
    if user is not None:
        request.updated_by = user
    request.save()
    return request


@transaction.atomic
def advance_legal_stage(
    request: GuaranteeFormalizationRequest,
    legal_stage: str,
    *,
    user=None,
    **extra,
):
    """Met à jour l'étape juridique (notaire → enregistrement)."""
    _assert_form_editable(request)
    if legal_stage not in GuaranteeFormalizationRequest.LegalStage.values:
        raise ProcessError("Étape juridique invalide.")
    if legal_stage == GuaranteeFormalizationRequest.LegalStage.DONE:
        raise ProcessError(
            "Passez par la clôture du dossier pour marquer la formalisation terminée."
        )
    try:
        current_rank = _LEGAL_STAGE_ORDER.index(request.legal_stage)
        target_rank = _LEGAL_STAGE_ORDER.index(legal_stage)
    except ValueError as exc:
        raise ProcessError("Étape juridique invalide.") from exc
    if target_rank < current_rank:
        raise ProcessError("L'étape juridique ne peut pas revenir en arrière.")
    registration_number = extra.get("registration_number", request.registration_number)
    if (
        legal_stage == GuaranteeFormalizationRequest.LegalStage.REGISTERED
        and not str(registration_number or "").strip()
    ):
        raise ProcessError(
            "Indiquez le numéro d'enregistrement pour passer à « Enregistré »."
        )

    request.legal_stage = legal_stage
    if request.status == GuaranteeFormalizationRequest.Status.DRAFT:
        request.status = GuaranteeFormalizationRequest.Status.IN_PROGRESS

    if legal_stage == GuaranteeFormalizationRequest.LegalStage.AT_NOTARY:
        if not request.sent_to_notary_at:
            request.sent_to_notary_at = timezone.localdate()
        if extra.get("notary_name"):
            request.notary_name = str(extra["notary_name"]).strip()
        if extra.get("notary_reference"):
            request.notary_reference = str(extra["notary_reference"]).strip()

    if legal_stage in (
        GuaranteeFormalizationRequest.LegalStage.REGISTERED,
        GuaranteeFormalizationRequest.LegalStage.PENDING_REGISTRATION,
    ):
        if extra.get("registration_number") is not None:
            request.registration_number = str(extra["registration_number"]).strip()
        if "registration_date" in extra:
            request.registration_date = _parse_date(
                extra["registration_date"], "Date d'enregistrement"
            )
        if extra.get("registration_authority") is not None:
            request.registration_authority = str(
                extra["registration_authority"]
            ).strip()

    if user is not None:
        request.updated_by = user
    request.save()
    return request


@transaction.atomic
def add_formalization_fee(request: GuaranteeFormalizationRequest, data: dict, *, user=None):
    _assert_form_editable(request)
    _create_fee_lines(request, [data])
    if user is not None:
        request.updated_by = user
        request.save(update_fields=["updated_by", "updated_at"])
    request.apply_fees_snapshot(persist=True)
    return request.fees.order_by("-created_at").first()


@transaction.atomic
def remove_formalization_fee(request: GuaranteeFormalizationRequest, fee_id, *, user=None):
    _assert_form_editable(request)
    try:
        fee = request.fees.get(pk=fee_id)
    except FormalizationFee.DoesNotExist as exc:
        raise ProcessError("Frais introuvable sur ce dossier.") from exc
    fee.delete()
    if user is not None:
        request.updated_by = user
        request.save(update_fields=["updated_by", "updated_at"])
    request.apply_fees_snapshot(persist=True)
    return request


@transaction.atomic
def submit_formalization_request(request: GuaranteeFormalizationRequest, *, user=None):
    """Soumet au circuit FORMALISATION (validation interne)."""
    if request.status not in (
        GuaranteeFormalizationRequest.Status.DRAFT,
        GuaranteeFormalizationRequest.Status.IN_PROGRESS,
        GuaranteeFormalizationRequest.Status.RETURNED,
    ):
        raise ProcessError("Ce dossier ne peut pas être soumis.")

    amount = (
        request.fees_client_total
        or request.guarantee.current_value
        or request.guarantee.expertise_value
        or 0
    )
    try:
        start_workflow(
            request,
            amount=amount,
            risk_level=None,
            target_type=WorkflowDefinition.TargetType.FORMALISATION,
        )
    except WorkflowError as exc:
        raise ProcessError(str(exc)) from exc

    request.status = GuaranteeFormalizationRequest.Status.IN_APPROVAL
    if user is not None:
        request.updated_by = user
    request.save(
        update_fields=["status", "updated_by", "updated_at"]
        if user
        else ["status", "updated_at"]
    )
    return request


@transaction.atomic
def complete_formalization_request(request: GuaranteeFormalizationRequest, *, user=None):
    """
    Clôture la formalisation et rend la garantie active.
    """
    if request.status in (
        GuaranteeFormalizationRequest.Status.COMPLETED,
        GuaranteeFormalizationRequest.Status.CANCELLED,
        GuaranteeFormalizationRequest.Status.REJECTED,
    ):
        raise ProcessError("Ce dossier est déjà clôturé.")
    if request.status != GuaranteeFormalizationRequest.Status.APPROVED:
        raise ProcessError(
            "Le circuit doit être approuvé avant de clôturer la formalisation."
        )

    if request.legal_stage not in (
        GuaranteeFormalizationRequest.LegalStage.SIGNED,
        GuaranteeFormalizationRequest.LegalStage.PENDING_REGISTRATION,
        GuaranteeFormalizationRequest.LegalStage.REGISTERED,
        GuaranteeFormalizationRequest.LegalStage.DONE,
    ):
        raise ProcessError(
            "Avancez au moins jusqu'à « Acte signé » (ou enregistrement) "
            "avant de clôturer la formalisation."
        )

    guarantee = request.guarantee
    if guarantee.guarantee_type in _FORMALIZABLE_TYPES:
        if request.legal_stage not in (
            GuaranteeFormalizationRequest.LegalStage.REGISTERED,
            GuaranteeFormalizationRequest.LegalStage.DONE,
        ):
            raise ProcessError(
                "Une hypothèque, un gage ou un nantissement ne devient actif "
                "qu'après enregistrement ou publicité."
            )
        if not (request.registration_number or "").strip():
            raise ProcessError(
                "Le numéro d'enregistrement est obligatoire avant de rendre "
                "cette garantie active."
            )
        has_signed_proof = bool(request.acte_signed_file) or bool(
            request.registration_proof
        )
        if not has_signed_proof:
            has_signed_proof = formalization_documents(request).filter(
                category__code__in=("FORM_ACTE_SIGNE", "FORM_ENREGISTREMENT")
            ).exists()
        if not has_signed_proof:
            raise ProcessError(
                "Déposez l'acte signé ou la preuve d'enregistrement avant "
                "de clôturer la formalisation."
            )
    now = timezone.now()
    if request.registration_number:
        guarantee.registration_number = request.registration_number
    if request.registration_date:
        guarantee.registration_date = request.registration_date
    if request.registration_authority:
        guarantee.registration_authority = request.registration_authority
    guarantee.formalized_at = now
    if guarantee.status not in (
        Guarantee.Status.RELEASED,
        Guarantee.Status.REALIZED,
        Guarantee.Status.TRANSFERRED,
    ):
        guarantee.status = Guarantee.Status.ACTIVE
    guarantee.save(
        update_fields=[
            "registration_number",
            "registration_date",
            "registration_authority",
            "formalized_at",
            "status",
            "updated_at",
        ]
    )

    GuaranteeMovement.objects.create(
        tenant_id=guarantee.tenant_id,
        guarantee=guarantee,
        movement_type=GuaranteeMovement.MovementType.FORMALIZATION,
        movement_date=timezone.localdate(),
        value=guarantee.current_value,
        comment=f"Formalisation {request.reference} clôturée "
        f"(étape {request.get_legal_stage_display()}).",
    )

    request.status = GuaranteeFormalizationRequest.Status.COMPLETED
    request.legal_stage = GuaranteeFormalizationRequest.LegalStage.DONE
    request.completed_at = now
    if user is not None:
        request.updated_by = user
    request.save()
    return request


@transaction.atomic
def cancel_formalization_request(
    request: GuaranteeFormalizationRequest, *, user=None, comment=""
):
    if request.status not in (
        GuaranteeFormalizationRequest.Status.DRAFT,
        GuaranteeFormalizationRequest.Status.IN_PROGRESS,
        GuaranteeFormalizationRequest.Status.RETURNED,
        GuaranteeFormalizationRequest.Status.IN_APPROVAL,
    ):
        raise ProcessError("Ce dossier ne peut plus être annulé.")
    from apps.workflow.services import cancel_active_workflows_for_target

    cancel_active_workflows_for_target(request)
    request.status = GuaranteeFormalizationRequest.Status.CANCELLED
    if comment:
        request.comment = (
            (request.comment + "\n" if request.comment else "") + comment
        )
    if user is not None:
        request.updated_by = user
    request.save()
    return request
