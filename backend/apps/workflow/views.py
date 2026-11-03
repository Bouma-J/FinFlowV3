from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.catalog.models import RejectReason
from apps.common.viewsets import (
    TenantScopedReadOnlyViewSet,
    TenantScopedViewSet,
)

from .models import (
    ApprovalCondition,
    ApprovalStep,
    ApprovalTask,
    WorkflowDefinition,
    WorkflowInstance,
)
from .serializers import (
    ApprovalConditionSerializer,
    ApprovalStepSerializer,
    ApprovalTaskSerializer,
    ConditionActionSerializer,
    DecisionSerializer,
    WorkflowDefinitionSerializer,
    WorkflowInstanceSerializer,
)
from .services import (
    WorkflowError,
    assert_decision_coverage,
    clone_workflow_definition,
    compute_decision_gaps,
    effective_group_ids,
    ensure_definition_editable,
    lift_condition,
    process_decision,
    return_lift,
    validate_condition,
)


class WorkflowDefinitionViewSet(TenantScopedViewSet):
    queryset = WorkflowDefinition.objects.select_related(
        "product", "product_category"
    ).prefetch_related("steps").all()
    serializer_class = WorkflowDefinitionSerializer
    filterset_fields = ["target_type", "is_active"]
    search_fields = ["code", "name"]
    action_perms = {
        "clone": ["workflow.add_workflowdefinition"],
    }

    def perform_update(self, serializer):
        """Interdit d'activer un circuit laissant des montants sans décideur.

        L'activation est le moment où le circuit devient opposable aux
        dossiers : c'est là que le contrôle a un sens. Un circuit inactif reste
        librement modifiable pendant sa construction. Les critères de
        sélection (montant / produit) ne sont modifiables que si le circuit
        n'a pas encore servi.
        """
        criteria_keys = {
            "min_amount",
            "max_amount",
            "product",
            "product_category",
        }
        if criteria_keys.intersection(serializer.validated_data.keys()):
            try:
                ensure_definition_editable(serializer.instance)
            except WorkflowError as exc:
                raise ValidationError(str(exc))

        activating = (
            serializer.validated_data.get("is_active") is True
            and not serializer.instance.is_active
        )
        if activating:
            try:
                assert_decision_coverage(serializer.instance)
            except WorkflowError as exc:
                raise ValidationError(str(exc))
        super().perform_update(serializer)

    @action(detail=True, methods=["post"])
    def clone(self, request, pk=None):
        """Duplique le circuit en version N+1 (étapes incluses)."""
        source = self.get_object()
        deactivate = request.data.get("deactivate_source", True)
        if isinstance(deactivate, str):
            deactivate = deactivate.lower() not in ("0", "false", "no")
        try:
            clone = clone_workflow_definition(
                source,
                user=request.user,
                deactivate_source=bool(deactivate),
            )
        except WorkflowError as exc:
            raise ValidationError(str(exc))
        return Response(
            WorkflowDefinitionSerializer(clone, context={"request": request}).data,
            status=201,
        )


class ApprovalStepViewSet(TenantScopedViewSet):
    queryset = ApprovalStep.objects.select_related("definition", "required_group").all()
    serializer_class = ApprovalStepSerializer
    filterset_fields = ["definition"]

    def _guard_editable(self, definition):
        try:
            ensure_definition_editable(definition)
        except WorkflowError as exc:
            raise ValidationError(str(exc))

    def _guard_no_new_gap(self, definition, write):
        """Applique `write` en refusant qu'il ouvre un trou de décision.

        On compare la couverture avant et après : un circuit déjà troué reste
        modifiable (il est en construction, et le diagnostic est exposé par
        l'API), mais un circuit actif et sain ne peut pas être dégradé.

        Un circuit encore sans étape compte comme en construction, sans quoi
        l'ajout de sa première étape consultative serait refusé.
        """
        existing = list(definition.steps.all())
        had_gaps = not existing or bool(
            compute_decision_gaps(definition, steps=existing)
        )
        with transaction.atomic():
            write()
            if definition.is_active and not had_gaps:
                try:
                    assert_decision_coverage(definition)
                except WorkflowError as exc:
                    raise ValidationError(str(exc))

    def perform_create(self, serializer):
        definition = serializer.validated_data["definition"]
        self._guard_editable(definition)
        parent = super()
        self._guard_no_new_gap(definition, lambda: parent.perform_create(serializer))

    def perform_update(self, serializer):
        definition = serializer.instance.definition
        self._guard_editable(definition)
        parent = super()
        self._guard_no_new_gap(definition, lambda: parent.perform_update(serializer))

    def perform_destroy(self, instance):
        definition = instance.definition
        self._guard_editable(definition)
        self._guard_no_new_gap(definition, instance.delete)


class WorkflowInstanceViewSet(TenantScopedReadOnlyViewSet):
    queryset = WorkflowInstance.objects.prefetch_related("tasks").all()
    serializer_class = WorkflowInstanceSerializer
    filterset_fields = ["status", "definition"]


class ApprovalConditionViewSet(TenantScopedReadOnlyViewSet):
    queryset = ApprovalCondition.objects.select_related(
        "application", "task", "task__step",
        "issued_by", "lifted_by", "validated_by",
    ).all()
    serializer_class = ApprovalConditionSerializer
    # Décisions métier (émetteur / initiateur) contrôlées dans les services.
    action_perms = {
        "lift": [],
        "validate": [],
        "return_lift": [],
    }
    filterset_fields = ["application", "status", "task"]

    @action(detail=True, methods=["post"])
    def lift(self, request, pk=None):
        condition = self.get_object()
        payload = ConditionActionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            lift_condition(
                condition,
                request.user,
                comment=payload.validated_data.get("comment", ""),
            )
        except WorkflowError as exc:
            raise ValidationError(str(exc))
        condition.refresh_from_db()
        return Response(
            ApprovalConditionSerializer(condition, context={"request": request}).data
        )

    @action(detail=True, methods=["post"])
    def validate(self, request, pk=None):
        condition = self.get_object()
        payload = ConditionActionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            validate_condition(
                condition,
                request.user,
                comment=payload.validated_data.get("comment", ""),
            )
        except WorkflowError as exc:
            raise ValidationError(str(exc))
        condition.refresh_from_db()
        return Response(
            ApprovalConditionSerializer(condition, context={"request": request}).data
        )

    @action(detail=True, methods=["post"])
    def return_lift(self, request, pk=None):
        """Renvoie la levée au chargé de dossier pour complément (émetteur)."""
        condition = self.get_object()
        payload = ConditionActionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            return_lift(
                condition,
                request.user,
                comment=payload.validated_data.get("comment", ""),
            )
        except WorkflowError as exc:
            raise ValidationError(str(exc))
        condition.refresh_from_db()
        return Response(
            ApprovalConditionSerializer(condition, context={"request": request}).data
        )


class ApprovalTaskViewSet(TenantScopedReadOnlyViewSet):
    queryset = ApprovalTask.objects.select_related("step", "instance", "acted_by").all()
    serializer_class = ApprovalTaskSerializer
    # decide : groupe d'étape (user_can_act) — pas un codename Django.
    action_perms = {
        "my_pending": ["workflow.view_approvaltask"],
        "my_dossiers": ["workflow.view_approvaltask"],
        "decide": [],
    }
    filterset_fields = ["status", "instance", "step"]

    @action(detail=False, methods=["get"])
    def my_pending(self, request):
        """Tâches en attente pour les rôles de l'utilisateur (y compris délégations)."""
        if request.user.is_superuser or getattr(request.user, "is_group_level", False):
            qs = self.get_queryset().filter(status=ApprovalTask.Status.PENDING)
        else:
            group_ids = effective_group_ids(request.user)
            qs = self.get_queryset().filter(
                status=ApprovalTask.Status.PENDING,
                step__required_group_id__in=group_ids,
            )
        page = self.paginate_queryset(qs)
        serializer = self.get_serializer(page or qs, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def my_dossiers(self, request):
        """Dossiers / processus en circuit visibles pour l'utilisateur.

        Périmètre :
        - Chargé d'affaire : dossiers qu'il a soumis
        - Chef d'agence : dossiers de son / ses agences
        - Autres rôles : circuits dont une étape implique l'un de ses groupes
        - Hors brouillon

        Filtres query :
        - ``queue`` : ``actionable`` (à traiter), ``treated`` (déjà traités),
          ``all`` (tous les visibles)
        - ``actionable=1`` : alias de queue=actionable
        - ``step_role`` / ``step`` : étape courante (rôle ou nom d'étape)
        """
        from apps.accounts.services import (
            CHARGE_AFFAIRE_ROLE_NAME,
            CHEF_AGENCE_ROLE_NAME,
        )
        from apps.collections.access import user_role_names
        from apps.common.access import get_user_agency_ids
        from apps.common.list_filters import query_param
        from apps.common.pagination import DefaultPagination
        from apps.common.tenancy import get_current_tenant_id
        from apps.credits.models import CreditApplication
        from apps.guarantees.models import (
            DationRequest,
            GuaranteeFormalizationRequest,
            GuaranteeReleaseRequest,
        )

        user = request.user
        group_ids = effective_group_ids(user)
        see_all = user.is_superuser or getattr(user, "is_group_level", False)
        role_names = user_role_names(user)
        is_chef = CHEF_AGENCE_ROLE_NAME in role_names
        is_ca = (
            CHARGE_AFFAIRE_ROLE_NAME in role_names
            and not is_chef
            and not see_all
        )
        agency_ids = set(get_user_agency_ids(user)) if is_chef and not see_all else set()

        tenant_id = get_current_tenant_id()
        if not tenant_id:
            instances = WorkflowInstance.objects.none()
        else:
            instances = (
                WorkflowInstance.all_tenants.filter(tenant_id=tenant_id)
                .select_related("definition")
                .prefetch_related(
                    "definition__steps",
                    "definition__steps__required_group",
                    "definition__steps__required_group__tenant_role",
                    "tasks",
                    "tasks__step",
                    "tasks__step__required_group",
                )
                .order_by("-created_at")
            )

        def _target_agency_id(target):
            agency_id = getattr(target, "agency_id", None)
            if agency_id:
                return agency_id
            application = getattr(target, "application", None)
            if application is not None:
                return getattr(application, "agency_id", None)
            guarantee = getattr(target, "guarantee", None)
            if guarantee is not None:
                agency_id = getattr(guarantee, "agency_id", None)
                if agency_id:
                    return agency_id
                app = getattr(guarantee, "application", None)
                if app is not None:
                    return getattr(app, "agency_id", None)
            return None

        def _step_role_name(step):
            if step is None:
                return ""
            group = getattr(step, "required_group", None)
            if group is None:
                return ""
            role = getattr(group, "tenant_role", None)
            if role is not None and getattr(role, "name", None):
                return str(role.name)
            return str(getattr(group, "name", "") or "")

        def _visible(target, steps):
            if see_all:
                return True
            if is_chef:
                aid = _target_agency_id(target)
                return bool(aid and aid in agency_ids)
            if is_ca:
                return getattr(target, "submitted_by_id", None) == user.id
            step_group_ids = {s.required_group_id for s in steps}
            return not group_ids.isdisjoint(step_group_ids)

        rows = []
        seen_keys = set()
        step_options = {}
        for inst in instances:
            target = inst.target
            if target is None:
                continue

            if isinstance(target, CreditApplication):
                target_kind = "CREDIT"
                detail_path = f"/dossiers/{target.id}"
                row_id = str(target.id)
                reference = target.reference
                client = target.client
                amount = str(target.amount_requested)
                amount_proposed = (
                    str(target.amount_proposed)
                    if target.amount_proposed is not None
                    else None
                )
                currency = target.currency
                status = target.status
                status_display = target.get_status_display()
                product_label = (
                    target.product.label if target.product_id else ""
                )
                created_by = target.created_by
                created_at = target.created_at
            elif isinstance(target, GuaranteeReleaseRequest):
                target_kind = "MAIN_LEVEE"
                detail_path = f"/mains-levees/{target.id}"
                row_id = str(target.id)
                reference = target.reference
                client = target.guarantee.client if target.guarantee_id else None
                amount = str(target.cbs_outstanding or 0)
                amount_proposed = None
                currency = target.cbs_currency or "XAF"
                status = target.status
                status_display = target.get_status_display()
                product_label = "Main levée"
                created_by = target.created_by
                created_at = target.created_at
            elif isinstance(target, DationRequest):
                target_kind = "DATION"
                detail_path = f"/dations/{target.id}"
                row_id = str(target.id)
                reference = target.reference
                client = target.client
                amount = str(
                    target.asset_value
                    if target.asset_value is not None
                    else target.cbs_total_outstanding or 0
                )
                amount_proposed = None
                currency = target.cbs_currency or "XAF"
                status = target.status
                status_display = target.get_status_display()
                product_label = "Dation en paiement"
                created_by = target.created_by
                created_at = target.created_at
            elif isinstance(target, GuaranteeFormalizationRequest):
                target_kind = "FORMALISATION"
                detail_path = f"/formalisations/{target.id}"
                row_id = str(target.id)
                reference = target.reference
                client = (
                    target.guarantee.client if target.guarantee_id else None
                )
                amount = str(
                    target.fees_client_total
                    or (
                        target.guarantee.current_value
                        if target.guarantee_id
                        else 0
                    )
                    or 0
                )
                amount_proposed = None
                currency = "XOF"
                status = target.status
                status_display = target.get_status_display()
                product_label = "Formalisation"
                created_by = target.created_by
                created_at = target.created_at
            else:
                continue

            if status == "DRAFT":
                continue

            seen_key = f"{target_kind}:{row_id}"
            if seen_key in seen_keys:
                continue

            steps = list(inst.definition.steps.all())
            if not _visible(target, steps):
                continue

            seen_keys.add(seen_key)

            my_task = None
            for t in inst.tasks.all():
                if see_all:
                    if t.status == ApprovalTask.Status.PENDING:
                        my_task = t
                        break
                    if my_task is None and t.status != ApprovalTask.Status.SKIPPED:
                        my_task = t
                    continue
                if not t.step or t.step.required_group_id not in group_ids:
                    continue
                if t.status == ApprovalTask.Status.PENDING:
                    my_task = t
                    break
                if my_task is None or (
                    (t.acted_at or timezone.now())
                    > (my_task.acted_at or timezone.now())
                ):
                    my_task = t

            current_step = next(
                (s for s in steps if s.order == inst.current_order), None
            )
            step_role = _step_role_name(current_step)
            step_name = current_step.name if current_step else ""
            if step_role or step_name:
                key = step_role or step_name
                step_options[key] = {
                    "value": key,
                    "label": step_role or step_name,
                    "step_name": step_name,
                    "step_role": step_role,
                    "order": getattr(current_step, "order", None),
                }

            is_actionable = bool(
                my_task and my_task.status == ApprovalTask.Status.PENDING
            )
            treated = bool(
                my_task
                and my_task.status
                in (
                    ApprovalTask.Status.APPROVED,
                    ApprovalTask.Status.REJECTED,
                    ApprovalTask.Status.RETURNED,
                )
                and not is_actionable
            )

            rows.append(
                {
                    "id": row_id,
                    "target_kind": target_kind,
                    "detail_path": detail_path,
                    "reference": reference,
                    "client_display": getattr(
                        client, "display_name", str(client) if client else ""
                    ),
                    "client_type": getattr(client, "client_type", "") if client else "",
                    "client_type_display": (
                        client.get_client_type_display()
                        if client and client.client_type
                        else ""
                    ),
                    "amount_requested": amount,
                    "amount_proposed": amount_proposed,
                    "currency": currency,
                    "status": status,
                    "status_display": status_display,
                    "product_label": product_label,
                    "created_by_id": str(created_by.id) if created_by else None,
                    "created_by_display": (
                        (
                            (created_by.get_full_name() or "").strip()
                            or str(created_by)
                        )
                        if created_by
                        else ""
                    ),
                    "created_at": created_at.isoformat() if created_at else None,
                    "definition_name": inst.definition.name,
                    "instance_status": inst.status,
                    "current_step_name": step_name,
                    "current_step_role": step_role,
                    "current_step_label": step_role or step_name,
                    "current_order": inst.current_order,
                    "my_task_status": my_task.status if my_task else None,
                    "my_step_name": (
                        my_task.step.name if my_task and my_task.step else ""
                    ),
                    "my_step_order": (
                        my_task.step.order if my_task and my_task.step else None
                    ),
                    "my_task_due_at": (
                        my_task.due_at.isoformat()
                        if my_task and my_task.due_at
                        else None
                    ),
                    "is_actionable": is_actionable,
                    "is_treated": treated,
                }
            )

        search = query_param(request, "search").lower()
        status_f = query_param(request, "status")
        kind = query_param(request, "target_kind")
        queue = (query_param(request, "queue") or "").strip().lower()
        actionable = query_param(request, "actionable")
        if not queue:
            if actionable == "1":
                queue = "actionable"
            else:
                queue = "all"
        step_f = (
            query_param(request, "step_role")
            or query_param(request, "step")
            or query_param(request, "current_step")
        )
        client_type = query_param(request, "client_type")
        initiator = (
            query_param(request, "gestionnaire")
            or query_param(request, "initiator")
        )
        date_from = query_param(request, "created_after")
        date_to = query_param(request, "created_before")

        def _match(row):
            if kind and row["target_kind"] != kind:
                return False
            if status_f and row["status"] != status_f:
                return False
            if queue == "actionable" and not row["is_actionable"]:
                return False
            if queue == "treated" and not row.get("is_treated"):
                return False
            if step_f:
                needle = step_f.casefold()
                labels = {
                    str(row.get("current_step_role") or "").casefold(),
                    str(row.get("current_step_name") or "").casefold(),
                    str(row.get("current_step_label") or "").casefold(),
                }
                if needle not in labels:
                    return False
            if client_type == "particulier" and row["client_type"] != "INDIVIDUAL":
                return False
            if client_type == "entreprise" and row["client_type"] != "CORPORATE":
                return False
            if client_type == "groupement" and row["client_type"] != "PROFESSIONAL":
                return False
            if client_type in {
                "INDIVIDUAL",
                "CORPORATE",
                "PROFESSIONAL",
            } and row["client_type"] != client_type:
                return False
            if initiator and row.get("created_by_id") != initiator:
                if row.get("created_by_display") != initiator:
                    return False
            created = row.get("created_at") or ""
            if date_from and created[:10] < date_from:
                return False
            if date_to and created[:10] > date_to:
                return False
            if search:
                hay = " ".join(
                    str(row.get(key) or "")
                    for key in (
                        "reference",
                        "client_display",
                        "product_label",
                        "created_by_display",
                        "definition_name",
                        "current_step_name",
                        "current_step_role",
                        "current_step_label",
                        "my_step_name",
                    )
                ).lower()
                if search not in hay:
                    return False
            return True

        actionable_count = sum(1 for row in rows if row["is_actionable"])
        treated_count = sum(1 for row in rows if row.get("is_treated"))
        filtered = [row for row in rows if _match(row)]
        paginator = DefaultPagination()
        page = paginator.paginate_queryset(filtered, request)
        response = paginator.get_paginated_response(page)
        response.data["actionable_count"] = actionable_count
        response.data["treated_count"] = treated_count
        response.data["visible_count"] = len(rows)
        response.data["step_options"] = sorted(
            step_options.values(),
            key=lambda s: (s.get("order") is None, s.get("order") or 0, s["label"]),
        )
        response.data["queue"] = queue
        return response

    @action(detail=True, methods=["post"])
    def decide(self, request, pk=None):
        """Prend une décision sur la tâche (approuver / rejeter / retourner)."""
        task = self.get_object()
        payload = DecisionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        reject_reason = None
        if data.get("reject_reason"):
            reject_reason = RejectReason.objects.filter(
                id=data["reject_reason"]
            ).first()

        try:
            instance = process_decision(
                task=task,
                user=request.user,
                decision=data["decision"],
                comment=data.get("comment", ""),
                reject_reason=reject_reason,
                proposed_amount=data.get("proposed_amount"),
                opinion=data.get("opinion") or None,
                reserves=data.get("reserves"),
                return_to_submitter=data.get("return_to_submitter", False),
            )
        except WorkflowError as exc:
            raise ValidationError(str(exc))

        return Response(WorkflowInstanceSerializer(instance).data)
