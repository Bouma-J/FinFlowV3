from decimal import Decimal

from rest_framework import serializers

from .models import (
    ApprovalCondition,
    ApprovalStep,
    ApprovalTask,
    WorkflowDefinition,
    WorkflowInstance,
)


class ApprovalStepSerializer(serializers.ModelSerializer):
    class Meta:
        model = ApprovalStep
        fields = [
            "id", "definition", "name", "order", "required_group", "mode",
            "step_kind", "min_amount", "max_amount", "min_risk_level",
            "sla_hours", "allow_return",
        ]
        read_only_fields = ["id"]


class WorkflowDefinitionSerializer(serializers.ModelSerializer):
    steps = ApprovalStepSerializer(many=True, read_only=True)
    is_used = serializers.SerializerMethodField()
    decision_gaps = serializers.SerializerMethodField()
    product_label = serializers.SerializerMethodField()
    product_category_label = serializers.SerializerMethodField()
    specificity_score = serializers.SerializerMethodField()

    class Meta:
        model = WorkflowDefinition
        fields = [
            "id",
            "code",
            "name",
            "target_type",
            "version",
            "is_active",
            "is_used",
            "decision_gaps",
            "min_amount",
            "max_amount",
            "product",
            "product_label",
            "product_category",
            "product_category_label",
            "specificity_score",
            "steps",
        ]
        read_only_fields = [
            "id",
            "is_used",
            "decision_gaps",
            "product_label",
            "product_category_label",
            "specificity_score",
        ]

    def get_is_used(self, obj):
        from .services import definition_is_used

        return definition_is_used(obj)

    def get_product_label(self, obj):
        return obj.product.label if obj.product_id else None

    def get_product_category_label(self, obj):
        return obj.product_category.label if obj.product_category_id else None

    def get_specificity_score(self, obj):
        return obj.specificity_score()

    def validate(self, attrs):
        min_amount = attrs.get(
            "min_amount", getattr(self.instance, "min_amount", None)
        )
        max_amount = attrs.get(
            "max_amount", getattr(self.instance, "max_amount", None)
        )
        if (
            min_amount is not None
            and max_amount is not None
            and min_amount > max_amount
        ):
            raise serializers.ValidationError(
                {"max_amount": "Le plafond doit être supérieur ou égal au plancher."}
            )

        product = attrs.get("product", getattr(self.instance, "product", None))
        category = attrs.get(
            "product_category", getattr(self.instance, "product_category", None)
        )
        if product is not None and category is not None:
            if product.category_id != category.id:
                raise serializers.ValidationError(
                    {
                        "product": (
                            "Le produit n'appartient pas à la famille sélectionnée."
                        )
                    }
                )
        return attrs

    def get_decision_gaps(self, obj):
        """Tranches de montant sans décideur, ou `null` si le circuit est sain.

        `obj.steps.all()` exploite le prefetch de la vue : pas de requête par
        circuit dans la liste.
        """
        from .services import compute_decision_gaps, format_decision_gaps

        gaps = compute_decision_gaps(obj, steps=obj.steps.all())
        if not gaps:
            return None
        return {
            "label": format_decision_gaps(gaps),
            "ranges": [
                {"from": str(low), "to": None if high is None else str(high)}
                for low, high in gaps
            ],
        }


class ApprovalTaskSerializer(serializers.ModelSerializer):
    step_name = serializers.CharField(source="step.name", read_only=True)
    step_order = serializers.IntegerField(source="step.order", read_only=True)
    step_kind = serializers.CharField(source="step.step_kind", read_only=True)
    allow_return = serializers.BooleanField(source="step.allow_return", read_only=True)
    acted_by_display = serializers.SerializerMethodField()
    opinion_display = serializers.CharField(
        source="get_opinion_display", read_only=True
    )
    application = serializers.SerializerMethodField()
    target_meta = serializers.SerializerMethodField()

    def get_acted_by_display(self, obj):
        return str(obj.acted_by) if obj.acted_by_id else ""

    class Meta:
        model = ApprovalTask
        fields = [
            "id", "instance", "step", "step_name", "step_order", "step_kind",
            "allow_return", "status", "opinion", "opinion_display",
            "decision_comment", "reject_reason", "proposed_amount",
            "acted_by", "acted_by_display", "acted_at", "due_at", "application",
            "target_meta",
        ]
        read_only_fields = fields

    def get_target_meta(self, obj):
        target = obj.instance.target
        if target is None:
            return None
        from apps.credits.models import CreditApplication
        from apps.guarantees.models import (
            DationRequest,
            GuaranteeFormalizationRequest,
            GuaranteeReleaseRequest,
        )

        if isinstance(target, CreditApplication):
            return {
                "kind": "CREDIT",
                "id": str(target.id),
                "reference": target.reference,
                "detail_path": f"/dossiers/{target.id}",
            }
        if isinstance(target, GuaranteeReleaseRequest):
            return {
                "kind": "MAIN_LEVEE",
                "id": str(target.id),
                "reference": target.reference,
                "detail_path": f"/mains-levees/{target.id}",
            }
        if isinstance(target, DationRequest):
            return {
                "kind": "DATION",
                "id": str(target.id),
                "reference": target.reference,
                "detail_path": f"/dations/{target.id}",
            }
        if isinstance(target, GuaranteeFormalizationRequest):
            return {
                "kind": "FORMALISATION",
                "id": str(target.id),
                "reference": target.reference,
                "detail_path": f"/formalisations/{target.id}",
            }
        return {
            "kind": target.__class__.__name__,
            "id": str(target.pk),
            "reference": getattr(target, "reference", ""),
            "detail_path": None,
        }

    def get_application(self, obj):
        target = obj.instance.target
        from apps.credits.models import CreditApplication

        if not isinstance(target, CreditApplication):
            return None
        client = target.client
        return {
            "id": str(target.id),
            "reference": target.reference,
            "client_display": getattr(client, "display_name", str(client)),
            "amount_requested": str(target.amount_requested),
            "amount_proposed": (
                str(target.amount_proposed)
                if target.amount_proposed is not None
                else None
            ),
            "currency": target.currency,
        }


class ApprovalConditionSerializer(serializers.ModelSerializer):
    issued_by_display = serializers.SerializerMethodField()
    lifted_by_display = serializers.SerializerMethodField()
    validated_by_display = serializers.SerializerMethodField()
    step_name = serializers.CharField(source="task.step.name", read_only=True)
    can_lift = serializers.SerializerMethodField()
    can_validate = serializers.SerializerMethodField()

    def get_issued_by_display(self, obj):
        return str(obj.issued_by) if obj.issued_by_id else ""

    def get_lifted_by_display(self, obj):
        return str(obj.lifted_by) if obj.lifted_by_id else ""

    def get_validated_by_display(self, obj):
        return str(obj.validated_by) if obj.validated_by_id else ""

    class Meta:
        model = ApprovalCondition
        fields = [
            "id", "application", "task", "step_name", "description", "status",
            "issued_by", "issued_by_display", "issued_at",
            "lifted_by", "lifted_by_display", "lifted_at", "lift_comment",
            "validated_by", "validated_by_display", "validated_at",
            "validation_comment", "can_lift", "can_validate", "created_at",
        ]
        read_only_fields = fields

    def get_can_lift(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        user = request.user
        app = obj.application
        if user.is_superuser or getattr(user, "is_group_level", False):
            return obj.status == ApprovalCondition.Status.PENDING
        return (
            obj.status == ApprovalCondition.Status.PENDING
            and user.id in {app.submitted_by_id, app.created_by_id}
        )

    def get_can_validate(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        user = request.user
        if obj.status != ApprovalCondition.Status.LIFTED:
            return False
        return user.is_superuser or obj.issued_by_id == user.id


class WorkflowInstanceSerializer(serializers.ModelSerializer):
    tasks = ApprovalTaskSerializer(many=True, read_only=True)
    definition_code = serializers.CharField(source="definition.code", read_only=True)

    class Meta:
        model = WorkflowInstance
        fields = [
            "id", "definition", "definition_code", "content_type", "object_id",
            "status", "current_order", "amount", "risk_level", "tasks",
            "created_at",
        ]
        read_only_fields = fields


class DecisionSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(
        choices=["APPROVED", "REJECTED", "RETURNED"]
    )
    opinion = serializers.ChoiceField(
        choices=[
            "FAVORABLE",
            "FAVORABLE_SOUS_RESERVE",
            "DEFAVORABLE",
        ],
        required=False,
        allow_blank=True,
    )
    comment = serializers.CharField(required=False, allow_blank=True)
    reserves = serializers.ListField(
        child=serializers.CharField(max_length=2000),
        required=False,
        allow_empty=True,
    )
    reject_reason = serializers.UUIDField(required=False, allow_null=True)
    proposed_amount = serializers.DecimalField(
        max_digits=18, decimal_places=2, required=False, allow_null=True,
        min_value=Decimal("0"),
    )
    # Pour un renvoi (RETURNED) : True = renvoyer directement au soumissionnaire
    # (le dossier repasse en correction) ; False/absent = renvoyer à l'étape
    # inférieure (comportement par défaut).
    return_to_submitter = serializers.BooleanField(required=False, default=False)


class ConditionActionSerializer(serializers.Serializer):
    comment = serializers.CharField(required=False, allow_blank=True, default="")
