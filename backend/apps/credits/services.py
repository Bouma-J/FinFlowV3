"""Services métier des dossiers de crédit (simulation, soumission, décaissement)."""
import math
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from dateutil.relativedelta import relativedelta
from django.db import transaction
from django.utils import timezone

from django.contrib.contenttypes.models import ContentType

from apps.workflow.models import ApprovalTask, WorkflowInstance
from apps.workflow.services import WorkflowError, start_workflow

from .models import CreditApplication, Installment, Loan, _PERIODS_PER_YEAR

CENTS = Decimal("0.01")

# Pas d'arrondi des montants du tableau d'amortissement : la dizaine de F CFA
# (base LB SERVICES / CBS sur les montants élevés).
AMOUNT_STEP = Decimal("10")

# Nombre de mois représenté par une période (hors journalier / hebdomadaire).
_PERIOD_MONTHS = {
    "MONTHLY": 1,
    "QUARTERLY": 3,
    "SEMIANNUAL": 6,
    "ANNUAL": 12,
}


def _q(value):
    return Decimal(value).quantize(CENTS, rounding=ROUND_HALF_UP)


def _parse_cbs_operation_date(value):
    """Parse ``dateOperation`` Perfect (YYYY-MM-DD) → date | None."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def apply_cbs_disbursement_refs_to_application(application, cbs_result: dict | None):
    """Copie numDemande / refDemande / numContrat / dateOperation sur le dossier."""
    if not cbs_result:
        return []
    raw = cbs_result.get("raw") if isinstance(cbs_result.get("raw"), dict) else {}
    updates: dict = {}
    num_demande = str(
        cbs_result.get("num_demande") or raw.get("numDemande") or ""
    ).strip()
    ref_demande = str(
        cbs_result.get("ref_demande") or raw.get("refDemande") or ""
    ).strip()
    num_contrat = str(
        cbs_result.get("num_contrat") or raw.get("numContrat") or ""
    ).strip()
    op_date = _parse_cbs_operation_date(
        raw.get("dateOperation") or cbs_result.get("date_operation")
    )
    if num_demande:
        updates["cbs_demande_number"] = num_demande[:100]
    if ref_demande:
        updates["cbs_demande_ref"] = ref_demande[:100]
    if num_contrat:
        updates["cbs_contract_number"] = num_contrat[:100]
    if op_date is not None:
        updates["cbs_operation_date"] = op_date
    for key, value in updates.items():
        setattr(application, key, value)
    return list(updates.keys())


def _round_step(value, step=AMOUNT_STEP):
    """Arrondit au multiple de `step` le plus proche (arrondi commercial).

    Reproduit la présentation du tableau d'amortissement du core banking
    (intérêts / capital arrondis à la dizaine de F CFA).
    """
    step = Decimal(step)
    return (Decimal(value) / step).quantize(Decimal(1), rounding=ROUND_HALF_UP) * step


def _next_business_day(day):
    """Reporte une date tombant un samedi/dimanche au lundi suivant."""
    while day.weekday() >= 5:  # 5 = samedi, 6 = dimanche
        day += timedelta(days=1)
    return day


def _add_periods(base, periodicity, n):
    """Ajoute n périodes à une date selon la périodicité."""
    if periodicity == "DAILY":
        return base + timedelta(days=n)
    if periodicity == "WEEKLY":
        return base + timedelta(weeks=n)
    if periodicity == "BIMONTHLY":
        # Deux échéances par mois ≈ 15 jours calendaires.
        return base + timedelta(days=15 * n)
    return base + relativedelta(months=_PERIOD_MONTHS.get(periodicity, 1) * n)


def period_count(duration_months, periodicity, tenant_id=None):
    """Nombre d'échéances (toujours arrondi à l'entier supérieur)."""
    per_year = _PERIODS_PER_YEAR.get(periodicity)
    if tenant_id is not None:
        from apps.catalog.cbs_resolve import resolve_periodicity_periods_per_year

        per_year = resolve_periodicity_periods_per_year(
            tenant_id, periodicity, default=per_year or 12
        )
    elif per_year is None:
        per_year = 12
    raw = Decimal(duration_months) / Decimal(12) * Decimal(per_year)
    return max(1, math.ceil(raw))


def compute_amortization_schedule(
    principal,
    annual_rate,
    duration_months,
    periodicity="MONTHLY",
    start_date=None,
    first_due_date=None,
    savings_rate=0,
    mechanism="DEGRESSIVE",
    tenant_id=None,
):
    """
    Échéancier d'amortissement aligné sur la base core banking (ACT/365,
    arrondi à la dizaine, report week-end des échéances intermédiaires).

    Mécanismes :
    - DEGRESSIVE : échéance institution constante ; intérêts décroissants,
      capital croissant. Convention CBS : le 1er calcul d'intérêts porte sur
      **une période théorique pleine** depuis ``start_date`` (date d'effet /
      simulation → start_date + 1 période), même si la 1ʳᵉ échéance est
      anticipée ou reportée. Les périodes suivantes utilisent les jours
      calendaires entre échéances nominales.
    - CONSTANT : legacy — annuité fixe, intérêts sur période nominale avant
      la 1ʳᵉ échéance (conservé pour les dossiers historiques).
    - IN_FINE : intérêts seuls puis capital à la dernière échéance
    - BULLET : une seule échéance en fin (capital + intérêts de la durée)

    Épargne obligatoire : colonne séparée (obligation client). Le champ
    ``institution_due`` = principal + intérêt (ce qui revient à l'institution).
    ``total`` = institution_due + savings (flux client global).
    """
    from .models import RepaymentMechanism

    principal = Decimal(principal)
    annual_rate = Decimal(annual_rate or 0)
    savings_rate = Decimal(savings_rate or 0)
    mechanism = (mechanism or RepaymentMechanism.DEGRESSIVE).upper()
    per_year = _PERIODS_PER_YEAR.get(periodicity, 12)
    if tenant_id is not None:
        from apps.catalog.cbs_resolve import resolve_periodicity_periods_per_year

        per_year = resolve_periodicity_periods_per_year(
            tenant_id, periodicity, default=per_year
        )
    count = int(period_count(duration_months, periodicity, tenant_id=tenant_id))
    period_rate = annual_rate / Decimal(100) / Decimal(per_year)
    daily_rate = annual_rate / Decimal(100) / Decimal(365)
    savings_flat = _round_step(principal * savings_rate / Decimal(100))
    origin = start_date or date.today()

    if first_due_date:
        first = first_due_date
    else:
        first = _add_periods(origin, periodicity, 1)

    # Longueur de la 1ʳᵉ période d'intérêts (convention CBS / dégressif).
    first_period_days = max((_add_periods(origin, periodicity, 1) - origin).days, 0)

    def _due(n, nominal, last_n):
        if n == 1 or n == last_n:
            return nominal
        return _next_business_day(nominal)

    def _row(n, due, principal_part, interest, balance):
        institution = principal_part + interest
        return {
            "number": n,
            "due_date": due,
            "principal": principal_part,
            "interest": interest,
            "savings": savings_flat,
            "institution_due": institution,
            "total": institution + savings_flat,
            "balance": balance if balance > 0 else Decimal("0"),
        }

    # ----- BULLET : une échéance au terme ----- #
    if mechanism == RepaymentMechanism.BULLET:
        last_nominal = _add_periods(first, periodicity, count - 1)
        days = max((last_nominal - origin).days, 0)
        interest = _round_step(principal * daily_rate * Decimal(days))
        return [_row(1, last_nominal, principal, interest, Decimal("0"))]

    # Annuité de référence (DEGRESSIVE / CONSTANT)
    if period_rate == 0:
        payment = principal / count
    else:
        factor = (Decimal(1) + period_rate) ** count
        payment = principal * period_rate * factor / (factor - Decimal(1))
    payment = _round_step(payment)

    schedule = []
    balance = principal
    # CONSTANT (legacy) : période nominale avant la 1ʳᵉ échéance.
    # DEGRESSIVE : après la 1ʳᵉ ligne, jours calendaires entre échéances.
    prev_nominal = (
        _add_periods(first, periodicity, -1)
        if mechanism != RepaymentMechanism.DEGRESSIVE
        else first
    )

    for n in range(1, count + 1):
        nominal = _add_periods(first, periodicity, n - 1)
        if mechanism == RepaymentMechanism.DEGRESSIVE and n == 1:
            days = first_period_days
        else:
            days = max((nominal - prev_nominal).days, 0)
        interest = _round_step(balance * daily_rate * Decimal(days))
        is_last = n == count

        if mechanism == RepaymentMechanism.IN_FINE:
            principal_part = balance if is_last else Decimal("0")
        elif mechanism in (
            RepaymentMechanism.DEGRESSIVE,
            RepaymentMechanism.CONSTANT,
        ):
            # Échéance constante : capital = annuité − intérêts (↑), intérêts ↓
            if is_last:
                principal_part = balance
            else:
                principal_part = payment - interest
                if principal_part < 0:
                    principal_part = Decimal("0")
        else:  # filet de sécurité
            principal_part = balance if is_last else Decimal("0")

        balance = balance - principal_part
        schedule.append(
            _row(n, _due(n, nominal, count), principal_part, interest, balance)
        )
        prev_nominal = nominal
    return schedule


@transaction.atomic
def submit_application(application, user):
    """Soumet le dossier et démarre le circuit d'approbation."""
    if application.status not in (
        CreditApplication.Status.DRAFT,
        CreditApplication.Status.RETURNED,
    ):
        raise WorkflowError("Seul un dossier en brouillon ou retourné peut être soumis.")

    from apps.clients.models import Client

    from .analysis_validation import (
        assert_analysis_ready_for_submission,
        refresh_reference_analysis,
    )
    from .instruction_policy import (
        assert_policy_submit_gates,
        assert_product_bounds,
    )
    from .models import FinancialAnalysis
    from .risk import risk_level_from_analysis

    client = application.client
    if client is None:
        raise WorkflowError("Un client est obligatoire avant soumission.")

    # KYC : toujours exigé à la soumission (même si aussi contrôlé à la création).
    if client.kyc_status != Client.KycStatus.VALIDATED:
        raise WorkflowError(
            "Le KYC du client doit être validé avant soumission du dossier."
        )

    product = application.product
    if product is None:
        raise WorkflowError("Un produit de crédit est obligatoire avant soumission.")
    if not getattr(product, "is_active", True):
        raise WorkflowError("Le produit de crédit sélectionné n'est plus actif.")

    amount = application.amount_requested
    if amount is None:
        raise WorkflowError("Le montant demandé est obligatoire.")
    duration = application.duration_months
    if duration is None:
        raise WorkflowError("La durée demandée est obligatoire.")

    assert_product_bounds(application)
    refresh_reference_analysis(application)
    reference = assert_analysis_ready_for_submission(application)
    assert_policy_submit_gates(application)
    if not reference.is_reference:
        # Garantit qu'il existe toujours une référence explicite.
        FinancialAnalysis.objects.filter(application=application).update(
            is_reference=False
        )
        reference.is_reference = True
        reference.save(update_fields=["is_reference", "updated_at"])

    risk_level = risk_level_from_analysis(reference)
    if risk_level is not None:
        application.risk_level = risk_level

    was_returned = application.status == CreditApplication.Status.RETURNED

    from .amounts import reference_amount

    workflow_amount = (
        reference_amount(application) or application.amount_requested
    )
    instance = start_workflow(
        target=application,
        amount=workflow_amount,
        risk_level=application.risk_level,
    )
    application.status = CreditApplication.Status.IN_APPROVAL
    application.submitted_at = timezone.now()
    application.submitted_by = user
    application.save(
        update_fields=[
            "status",
            "submitted_at",
            "submitted_by",
            "risk_level",
            "updated_at",
        ]
    )

    from apps.audit.events import RESUBMITTED, SUBMITTED, log_workflow_event

    log_workflow_event(
        application,
        RESUBMITTED if was_returned else SUBMITTED,
        detail=f"Circuit « {instance.definition.name} »." if instance else "",
        user=user,
    )
    return instance


@transaction.atomic
def cancel_submission(application, user=None):
    """Annule la soumission d'un dossier et le repasse en brouillon.

    Le circuit d'approbation en cours est annulé et ses tâches en attente
    sont ignorées, afin de permettre la modification puis la resoumission.
    Seul l'auteur de la soumission (ou un super-utilisateur) peut l'annuler.
    """
    if application.status != CreditApplication.Status.IN_APPROVAL:
        raise WorkflowError(
            "Seul un dossier en cours d'approbation peut voir sa soumission annulée."
        )

    is_super = getattr(user, "is_superuser", False) if user is not None else True

    if user is not None and not is_super:
        submitter_id = application.submitted_by_id or application.created_by_id
        if submitter_id and submitter_id != user.id:
            raise WorkflowError(
                "Seul le profil ayant soumis le dossier peut annuler la soumission."
            )

    content_type = ContentType.objects.get_for_model(CreditApplication)
    instances = WorkflowInstance.all_tenants.filter(
        content_type=content_type,
        object_id=application.pk,
        status__in=[
            WorkflowInstance.Status.IN_PROGRESS,
            WorkflowInstance.Status.AWAITING_CONDITIONS,
        ],
    )

    # Un soumissionnaire ne peut plus annuler dès qu'une étape a statué sur le
    # dossier (approbation, renvoi, rejet). Dans ce cas, il devra attendre qu'une
    # étape le lui renvoie pour pouvoir le modifier. Le super-admin garde la main.
    if not is_super:
        acted_exists = ApprovalTask.all_tenants.filter(
            instance__in=instances,
            status__in=[
                ApprovalTask.Status.APPROVED,
                ApprovalTask.Status.RETURNED,
                ApprovalTask.Status.REJECTED,
            ],
        ).exists()
        if acted_exists:
            raise WorkflowError(
                "La soumission ne peut plus être annulée : une étape du circuit a "
                "déjà statué sur ce dossier. Il pourra être modifié uniquement s'il "
                "vous est renvoyé par une étape."
            )

    for instance in instances:
        instance.tasks.filter(status=ApprovalTask.Status.PENDING).update(
            status=ApprovalTask.Status.SKIPPED
        )
        instance.status = WorkflowInstance.Status.CANCELLED
        instance.save(update_fields=["status", "updated_at"])

    application.status = CreditApplication.Status.DRAFT
    application.submitted_at = None
    application.save(update_fields=["status", "submitted_at", "updated_at"])

    from apps.audit.events import CANCELLED, log_workflow_event

    log_workflow_event(application, CANCELLED, user=user)
    return application


@transaction.atomic
def cancel_application(application, user=None):
    """Annule formellement un dossier (statut CANCELLED) si la politique l'autorise."""
    from .instruction_policy import get_instruction_policy
    from .models import CreditInstructionPolicy

    policy = get_instruction_policy(application.tenant_id)
    if not policy.enable_cancel_status:
        raise WorkflowError(
            "L'annulation formelle du dossier n'est pas activée pour cette filiale."
        )

    if application.status in (
        CreditApplication.Status.DISBURSED,
        CreditApplication.Status.CLOSED,
        CreditApplication.Status.CANCELLED,
    ):
        raise WorkflowError(
            "Ce dossier ne peut plus être annulé dans son statut actuel."
        )

    # Annule un éventuel circuit en cours.
    content_type = ContentType.objects.get_for_model(CreditApplication)
    instances = WorkflowInstance.all_tenants.filter(
        content_type=content_type,
        object_id=application.pk,
        status__in=[
            WorkflowInstance.Status.IN_PROGRESS,
            WorkflowInstance.Status.AWAITING_CONDITIONS,
        ],
    )
    for instance in instances:
        instance.tasks.filter(status=ApprovalTask.Status.PENDING).update(
            status=ApprovalTask.Status.SKIPPED
        )
        instance.status = WorkflowInstance.Status.CANCELLED
        instance.save(update_fields=["status", "updated_at"])

    application.status = CreditApplication.Status.CANCELLED
    application.save(update_fields=["status", "updated_at"])

    from apps.audit.events import CANCELLED, log_workflow_event

    log_workflow_event(
        application,
        CANCELLED,
        detail="Annulation formelle du dossier.",
        user=user,
    )
    return application


def _assert_disbursement_prerequisites(application):
    """Contrôles communs avant demande ou exécution du décaissement."""
    from apps.contracts.services import (
        missing_required_contracts,
        missing_surety_signed_contracts,
    )
    from apps.credits.instruction_policy import get_instruction_policy
    from apps.guarantees.formalization_services import (
        missing_formalizations_for_disbursement,
    )
    from apps.workflow.services import has_pending_conditions

    if has_pending_conditions(application):
        raise WorkflowError(
            "Le décaissement est impossible : des réserves sont encore "
            "en attente de validation."
        )

    missing = missing_required_contracts(application)
    if missing:
        raise WorkflowError(
            "Le décaissement est impossible : contrats obligatoires non "
            "générés (" + ", ".join(missing) + ")."
        )

    policy = get_instruction_policy(application.tenant_id)
    if policy.require_surety_signed_contracts:
        surety_missing = missing_surety_signed_contracts(application)
        if surety_missing:
            raise WorkflowError(
                "Le décaissement est impossible : contrats de cautionnement "
                "manquants ou non signés (" + ", ".join(surety_missing) + ")."
            )

    if policy.require_formalization_before_disbursement:
        form_missing = missing_formalizations_for_disbursement(application)
        if form_missing:
            raise WorkflowError(
                "Le décaissement est impossible : formalisation de garanties "
                "non clôturée (" + ", ".join(form_missing) + ")."
            )


@transaction.atomic
def request_disbursement(application, user=None):
    """Initie une demande de décaissement (validation par les opérations)."""
    application = (
        CreditApplication.objects.select_for_update()
        .select_related("client", "product")
        .get(pk=application.pk)
    )
    if application.status not in (
        CreditApplication.Status.APPROVED,
        CreditApplication.Status.CONTRACT_GENERATED,
    ):
        raise WorkflowError(
            "Le dossier doit être approuvé (ou contrat généré) pour "
            "demander le décaissement."
        )
    _assert_disbursement_prerequisites(application)

    application.disbursement_previous_status = application.status
    application.status = CreditApplication.Status.DISBURSEMENT_PENDING
    application.disbursement_requested_at = timezone.now()
    application.disbursement_requested_by = user
    application.save(
        update_fields=[
            "status",
            "disbursement_previous_status",
            "disbursement_requested_at",
            "disbursement_requested_by",
            "updated_at",
        ]
    )
    return application


@transaction.atomic
def cancel_disbursement_request(application):
    """Annule une demande de décaissement et restaure le statut précédent."""
    application = (
        CreditApplication.objects.select_for_update()
        .get(pk=application.pk)
    )
    if application.status != CreditApplication.Status.DISBURSEMENT_PENDING:
        raise WorkflowError("Aucune demande de décaissement en attente.")

    previous = application.disbursement_previous_status
    if previous not in (
        CreditApplication.Status.APPROVED,
        CreditApplication.Status.CONTRACT_GENERATED,
    ):
        previous = CreditApplication.Status.CONTRACT_GENERATED

    application.status = previous
    application.disbursement_previous_status = ""
    application.disbursement_requested_at = None
    application.disbursement_requested_by = None
    application.save(
        update_fields=[
            "status",
            "disbursement_previous_status",
            "disbursement_requested_at",
            "disbursement_requested_by",
            "updated_at",
        ]
    )
    return application


def disburse_application(application, disburse_date=None, *, skip_cbs=False):
    """Crée le prêt et l'échéancier après approbation, avec push CBS Perfect.

    Saga courte :
    1. Verrou + prérequis (transaction courte)
    2. Soumission CBS hors transaction (HTTP)
    3. Création Loan + échéancier sous verrou (idempotent si déjà décaissé)
    """
    app_id = application.pk

    with transaction.atomic():
        application = (
            CreditApplication.objects.select_for_update()
            .select_related("client", "product")
            .get(pk=app_id)
        )
        if application.status == CreditApplication.Status.DISBURSED:
            existing = Loan.objects.filter(application_id=app_id).first()
            if existing:
                return existing
        if application.status not in (
            CreditApplication.Status.APPROVED,
            CreditApplication.Status.CONTRACT_GENERATED,
            CreditApplication.Status.DISBURSEMENT_PENDING,
        ):
            raise WorkflowError(
                "Le dossier doit être approuvé ou en attente de validation "
                "du décaissement."
            )
        _assert_disbursement_prerequisites(application)

    cbs_result = None
    if not skip_cbs:
        try:
            from apps.corebanking.disbursement import submit_credit_to_cbs
            from apps.corebanking.services import CoreBankingError

            cbs_result = submit_credit_to_cbs(application)
        except CoreBankingError as exc:
            raise WorkflowError(str(exc)) from exc

    disburse_date = disburse_date or date.today()
    from .amounts import reference_amount

    with transaction.atomic():
        application = (
            CreditApplication.objects.select_for_update()
            .select_related("client", "product")
            .get(pk=app_id)
        )
        existing = Loan.objects.filter(application_id=app_id).first()
        if existing is not None:
            return existing
        if application.status == CreditApplication.Status.DISBURSED:
            existing = Loan.objects.filter(application_id=app_id).first()
            if existing:
                return existing
            raise WorkflowError(
                "Dossier marqué décaissé sans prêt local — intervention requise."
            )
        if application.status not in (
            CreditApplication.Status.APPROVED,
            CreditApplication.Status.CONTRACT_GENERATED,
            CreditApplication.Status.DISBURSEMENT_PENDING,
        ):
            raise WorkflowError(
                "Le statut du dossier a changé pendant l'appel CBS. "
                "Réessayez le décaissement."
            )

        principal = reference_amount(application) or application.amount_requested
        rate = application.interest_rate or application.product.interest_rate
        periodicity = application.periodicity
        savings_rate = application.mandatory_savings_rate or 0
        mechanism = application.repayment_mechanism or "DEGRESSIVE"
        first_due = application.first_due_date or _next_business_day(
            _add_periods(disburse_date, periodicity, 1)
        )

        loan_kwargs = {
            "tenant_id": application.tenant_id,
            "application": application,
            "principal": principal,
            "interest_rate": rate,
            "mandatory_savings_rate": savings_rate,
            "duration_months": application.duration_months,
            "disbursed_at": disburse_date,
            "first_due_date": first_due,
        }
        if cbs_result:
            loan_kwargs.update(
                {
                    "core_banking_reference": (
                        cbs_result.get("num_contrat")
                        or cbs_result.get("ref_demande")
                        or ""
                    )[:100],
                    "cbs_external_id": str(cbs_result.get("external_id") or "")[:100],
                    "cbs_demande_number": str(
                        cbs_result.get("num_demande") or ""
                    )[:100],
                    "cbs_demande_ref": str(cbs_result.get("ref_demande") or "")[:100],
                    "cbs_contract_number": str(
                        cbs_result.get("num_contrat") or ""
                    )[:100],
                    "cbs_disbursement_status": "SUBMITTED",
                    "cbs_disbursement_payload": cbs_result.get("raw") or {},
                }
            )

        loan = Loan.objects.create(**loan_kwargs)

        schedule = compute_amortization_schedule(
            principal, rate, application.duration_months,
            periodicity=periodicity, start_date=disburse_date,
            first_due_date=first_due, savings_rate=savings_rate,
            mechanism=mechanism,
            tenant_id=application.tenant_id,
        )
        Installment.objects.bulk_create([
            Installment(
                loan=loan,
                tenant_id=loan.tenant_id,
                number=row["number"],
                due_date=row["due_date"],
                principal_due=row["principal"],
                interest_due=row["interest"],
                savings_due=row["savings"],
                total_due=row["total"],
            )
            for row in schedule
        ])

        application.status = CreditApplication.Status.DISBURSED
        application.disbursed_at = timezone.now()
        application.disbursement_previous_status = ""
        app_update_fields = [
            "status",
            "disbursed_at",
            "disbursement_previous_status",
            "updated_at",
        ]
        app_update_fields.extend(
            apply_cbs_disbursement_refs_to_application(application, cbs_result)
        )
        application.save(update_fields=list(dict.fromkeys(app_update_fields)))
        return loan
