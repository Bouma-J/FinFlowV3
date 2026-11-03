from django.conf import settings
from rest_framework.response import Response

from apps.common.cache_utils import cache_key, cached_get
from apps.common.tenancy import get_current_tenant_id
from apps.common.viewsets import TenantScopedReadOnlyViewSet, TenantScopedViewSet

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
from .serializers import (
    CbsManagerSerializer,
    CbsProfessionSerializer,
    ChecklistItemSerializer,
    CreditProductSerializer,
    CurrencySerializer,
    DecisionMotifSerializer,
    FinancingObjectSerializer,
    FinancingSourceSerializer,
    LoanPeriodicitySerializer,
    ProductCategorySerializer,
    RejectReasonSerializer,
    RepaymentMethodSerializer,
    ServicePointSerializer,
)


class ProductCategoryViewSet(TenantScopedViewSet):
    queryset = ProductCategory.objects.all()
    serializer_class = ProductCategorySerializer
    filterset_fields = ["is_active"]
    search_fields = ["code", "label"]


class CreditProductViewSet(TenantScopedViewSet):
    queryset = CreditProduct.objects.select_related("category").all()
    serializer_class = CreditProductSerializer
    filterset_fields = ["category", "client_type", "currency", "is_active"]
    search_fields = ["code", "label"]

    def list(self, request, *args, **kwargs):
        tenant_id = get_current_tenant_id()
        qs_key = "&".join(
            f"{k}={','.join(request.query_params.getlist(k))}"
            for k in sorted(request.query_params.keys())
        )
        key = cache_key("credit-products", tenant_id, qs_key)
        ttl = getattr(settings, "CATALOG_CACHE_TTL", 120)

        def _produce():
            queryset = self.filter_queryset(self.get_queryset())
            page = self.paginate_queryset(queryset)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data).data
            serializer = self.get_serializer(queryset, many=True)
            return serializer.data

        return Response(cached_get(key, _produce, timeout=ttl))


class RejectReasonViewSet(TenantScopedViewSet):
    queryset = RejectReason.objects.all()
    serializer_class = RejectReasonSerializer
    filterset_fields = ["is_active"]
    search_fields = ["code", "label"]


class LoanPeriodicityViewSet(TenantScopedReadOnlyViewSet):
    """Périodicités : source CBS uniquement (sync Perfect)."""

    queryset = LoanPeriodicity.objects.all()
    serializer_class = LoanPeriodicitySerializer
    filterset_fields = ["is_active"]
    search_fields = ["code", "label", "cbs_code"]
    ordering = ["sort_order", "label"]


class RepaymentMethodViewSet(TenantScopedViewSet):
    queryset = RepaymentMethod.objects.all()
    serializer_class = RepaymentMethodSerializer
    filterset_fields = ["is_active"]
    search_fields = ["code", "label", "cbs_code"]
    ordering = ["sort_order", "label"]


class CurrencyViewSet(TenantScopedReadOnlyViewSet):
    """Devises : source CBS uniquement (sync Perfect)."""

    queryset = Currency.objects.all()
    serializer_class = CurrencySerializer
    filterset_fields = ["is_active"]
    search_fields = ["code", "label", "cbs_code"]
    ordering = ["sort_order", "label"]


class FinancingObjectViewSet(TenantScopedReadOnlyViewSet):
    """Objets de financement : source CBS uniquement (sync Perfect)."""

    queryset = FinancingObject.objects.all()
    serializer_class = FinancingObjectSerializer
    filterset_fields = ["is_active", "purpose_type"]
    search_fields = ["code", "label", "cbs_code", "purpose_type"]
    ordering = ["sort_order", "label"]


class ServicePointViewSet(TenantScopedReadOnlyViewSet):
    """Points de service Perfect : source CBS uniquement."""

    queryset = ServicePoint.objects.all()
    serializer_class = ServicePointSerializer
    filterset_fields = ["is_active"]
    search_fields = ["code", "label", "cbs_code"]
    ordering = ["sort_order", "label"]


class CbsManagerViewSet(TenantScopedReadOnlyViewSet):
    """Gestionnaires Perfect : source CBS uniquement."""

    queryset = CbsManager.objects.all()
    serializer_class = CbsManagerSerializer
    filterset_fields = ["is_active"]
    search_fields = ["code", "label", "cbs_code"]
    ordering = ["sort_order", "label"]


class FinancingSourceViewSet(TenantScopedReadOnlyViewSet):
    """Sources de financement Perfect : source CBS uniquement."""

    queryset = FinancingSource.objects.all()
    serializer_class = FinancingSourceSerializer
    filterset_fields = ["is_active"]
    search_fields = ["code", "label", "cbs_code"]
    ordering = ["sort_order", "label"]


class DecisionMotifViewSet(TenantScopedReadOnlyViewSet):
    """Motifs de décision Perfect : source CBS uniquement."""

    queryset = DecisionMotif.objects.all()
    serializer_class = DecisionMotifSerializer
    filterset_fields = ["is_active"]
    search_fields = ["code", "label", "cbs_code"]
    ordering = ["sort_order", "label"]


class CbsProfessionViewSet(TenantScopedReadOnlyViewSet):
    """Professions Perfect : source CBS uniquement."""

    queryset = CbsProfession.objects.all()
    serializer_class = CbsProfessionSerializer
    filterset_fields = ["is_active"]
    search_fields = ["code", "label", "cbs_code"]
    ordering = ["sort_order", "label"]


class ChecklistItemViewSet(TenantScopedViewSet):
    queryset = ChecklistItem.objects.select_related("product").all()
    serializer_class = ChecklistItemSerializer
    filterset_fields = ["product", "is_mandatory"]
