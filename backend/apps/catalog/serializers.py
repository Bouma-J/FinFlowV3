from rest_framework import serializers

from .models import (
    CbsManager,
    CbsProfession,
    ChecklistItem,
    CreditProduct,
    Currency,
    DecisionMotif,
    FinancingObject,
    FinancingSource,
    LoanPeriodicity,
    ProductCategory,
    RejectReason,
    RepaymentMethod,
    ServicePoint,
)


class ProductCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductCategory
        fields = ["id", "code", "label", "description", "is_active"]
        read_only_fields = ["id"]


class CreditProductSerializer(serializers.ModelSerializer):
    category_label = serializers.CharField(source="category.label", read_only=True)

    class Meta:
        model = CreditProduct
        fields = [
            "id", "code", "label", "description", "category", "category_label",
            "client_type", "currency", "amount_min", "amount_max",
            "duration_min_months", "duration_max_months", "interest_rate",
            "processing_fee_rate", "requires_guarantee",
            "cbs_product_code", "cbs_repayment_product_code",
            "is_active",
        ]
        read_only_fields = ["id"]

    def validate(self, attrs):
        amount_min = attrs.get("amount_min")
        amount_max = attrs.get("amount_max")
        if amount_min is not None and amount_max is not None and amount_min > amount_max:
            raise serializers.ValidationError(
                "Le montant minimum ne peut excéder le montant maximum."
            )
        return attrs


class RejectReasonSerializer(serializers.ModelSerializer):
    class Meta:
        model = RejectReason
        fields = ["id", "code", "label", "description", "is_active"]
        read_only_fields = ["id"]


class LoanPeriodicitySerializer(serializers.ModelSerializer):
    class Meta:
        model = LoanPeriodicity
        fields = [
            "id", "code", "label", "description", "cbs_code",
            "periods_per_year", "sort_order", "is_active",
        ]
        read_only_fields = fields


class RepaymentMethodSerializer(serializers.ModelSerializer):
    class Meta:
        model = RepaymentMethod
        fields = [
            "id", "code", "label", "description", "cbs_code",
            "sort_order", "is_active",
        ]
        read_only_fields = ["id"]


class CurrencySerializer(serializers.ModelSerializer):
    class Meta:
        model = Currency
        fields = [
            "id", "code", "label", "description", "cbs_code",
            "sort_order", "is_active",
        ]
        read_only_fields = fields


class FinancingObjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = FinancingObject
        fields = [
            "id", "code", "label", "description", "cbs_code",
            "purpose_type", "sort_order", "is_active",
        ]
        read_only_fields = fields


class ServicePointSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServicePoint
        fields = [
            "id", "code", "label", "description", "cbs_code",
            "sort_order", "is_active",
        ]
        read_only_fields = fields


class CbsManagerSerializer(serializers.ModelSerializer):
    class Meta:
        model = CbsManager
        fields = [
            "id", "code", "label", "description", "cbs_code",
            "sort_order", "is_active",
        ]
        read_only_fields = fields


class FinancingSourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = FinancingSource
        fields = [
            "id", "code", "label", "description", "cbs_code",
            "sort_order", "is_active",
        ]
        read_only_fields = fields


class DecisionMotifSerializer(serializers.ModelSerializer):
    class Meta:
        model = DecisionMotif
        fields = [
            "id", "code", "label", "description", "cbs_code",
            "sort_order", "is_active",
        ]
        read_only_fields = fields


class CbsProfessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = CbsProfession
        fields = [
            "id", "code", "label", "description", "cbs_code",
            "sort_order", "is_active",
        ]
        read_only_fields = fields


class ChecklistItemSerializer(serializers.ModelSerializer):
    product_label = serializers.CharField(
        source="product.label", read_only=True, default=""
    )

    class Meta:
        model = ChecklistItem
        fields = [
            "id", "product", "product_label", "label", "is_mandatory", "order",
        ]
        read_only_fields = ["id", "product_label"]
