"""Règles d'accès pour les contributions au dossier (analyses, visites).

Une contribution (analyse financière, visite terrain) peut être ajoutée par :
- l'initiateur du dossier tant que celui-ci n'est pas clôturé ;
- toute personne ayant une tâche en cours (PENDING) à l'étape courante du
  circuit d'approbation du dossier.

Modification / suppression : auteur **et** encore contributeur
(ou super-administrateur).
"""
from django.contrib.contenttypes.models import ContentType

from apps.workflow.models import ApprovalTask, WorkflowInstance

from .models import CreditApplication

# Statuts dans lesquels l'initiateur peut encore contribuer.
_OPEN_STATUSES = {
    CreditApplication.Status.DRAFT,
    CreditApplication.Status.SUBMITTED,
    CreditApplication.Status.IN_APPROVAL,
    CreditApplication.Status.RETURNED,
}

# Plus d'ajout / modification d'analyse financière après décaissement.
ANALYSIS_LOCKED_STATUSES = {
    CreditApplication.Status.DISBURSED,
    CreditApplication.Status.CLOSED,
    CreditApplication.Status.CANCELLED,
    CreditApplication.Status.REJECTED,
}

# Statuts autorisant le rattachement / modification de garanties & cautions.
COLLATERAL_ATTACH_STATUSES = {
    CreditApplication.Status.DRAFT,
    CreditApplication.Status.RETURNED,
    CreditApplication.Status.APPROVED,
    CreditApplication.Status.CONTRACT_GENERATED,
    CreditApplication.Status.DISBURSEMENT_PENDING,
}


def has_pending_task(application, user):
    """L'utilisateur a-t-il une tâche en attente sur le circuit actif du dossier ?"""
    if not user or not user.is_authenticated:
        return False
    group_ids = set(user.groups.values_list("id", flat=True))
    if not group_ids:
        return False
    content_type = ContentType.objects.get_for_model(application.__class__)
    return ApprovalTask.all_tenants.filter(
        instance__content_type=content_type,
        instance__object_id=application.pk,
        instance__status__in=[
            WorkflowInstance.Status.IN_PROGRESS,
            WorkflowInstance.Status.AWAITING_CONDITIONS,
        ],
        status=ApprovalTask.Status.PENDING,
        step__required_group_id__in=group_ids,
    ).exists()


def can_contribute(application, user):
    """Droit d'ajouter une analyse / visite sur le dossier."""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    is_initiator = user.id in {application.created_by_id, application.submitted_by_id}
    if is_initiator and application.status in _OPEN_STATUSES:
        return True
    return has_pending_task(application, user)


def can_add_financial_analysis(application, user):
    """Droit d'ajouter une analyse financière (fermé après décaissement)."""
    if application is not None and application.status in ANALYSIS_LOCKED_STATUSES:
        return False
    return can_contribute(application, user)


def is_controle_permanent(user):
    """Responsable / assistant contrôle interne (lecture + sortie terrain)."""
    from apps.accounts.models import TenantRole
    from apps.accounts.services import (
        ASSISTANT_CONTROLE_INTERNE_ROLE_NAME,
        RESP_CONTROLE_INTERNE_ROLE_NAME,
    )

    if not user or not user.is_authenticated:
        return False
    return TenantRole.objects.filter(
        group__in=user.groups.all(),
        name__in=(
            RESP_CONTROLE_INTERNE_ROLE_NAME,
            ASSISTANT_CONTROLE_INTERNE_ROLE_NAME,
        ),
    ).exists()


def can_add_field_visit(application, user):
    """Visite terrain : contributeur habituel, ou contrôle permanent."""
    if can_contribute(application, user):
        return True
    return is_controle_permanent(user)


def can_mutate_contribution(application, user):
    """Droit de modifier / supprimer une contribution (fenêtre encore ouverte)."""
    return can_contribute(application, user)


def can_attach_collateral(application, user=None):
    """Le dossier accepte-t-il encore le rattachement de garanties / cautions ?"""
    if application is None:
        return True
    if user is not None and getattr(user, "is_superuser", False):
        return True
    allowed = set(COLLATERAL_ATTACH_STATUSES)
    try:
        from .instruction_policy import get_instruction_policy

        policy = get_instruction_policy(application.tenant_id)
        if policy.allow_collateral_during_approval:
            allowed.add(CreditApplication.Status.IN_APPROVAL)
            allowed.add(CreditApplication.Status.SUBMITTED)
    except Exception:  # noqa: BLE001
        pass
    return application.status in allowed
