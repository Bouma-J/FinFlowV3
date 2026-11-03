from decimal import Decimal

from django.core.exceptions import ObjectDoesNotExist
from rest_framework import serializers

from apps.common.storage_urls import presign_file_fields

from .fees import build_fees_breakdown, sync_extra_fees
from .models import (
    AnalysisThreshold,
    CreditApplication,
    CreditApplicationFee,
    CreditDocument,
    CreditInstructionPolicy,
    FieldVisit,
    FinancialAnalysis,
    FinancialDocument,
    Installment,
    Loan,
    StockPhoto,
)


class AnalysisThresholdSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnalysisThreshold
        fields = [
            "id",
            "max_debt_ratio", "min_dscr", "max_leverage_ratio",
            "min_living_wage_per_capita", "min_interest_coverage", "max_gearing",
            "min_financial_autonomy", "min_current_ratio",
            "min_guarantee_coverage", "stress_pct",
            "transferable_quota_fraction", "informal_income_weight",
            "haircut_mortgage", "haircut_vehicle", "haircut_jewelry",
            "haircut_financial_deposit", "haircut_financial_security",
            "haircut_other",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class CreditInstructionPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = CreditInstructionPolicy
        fields = [
            "id",
            "collateral_coverage_mode",
            "require_field_visit",
            "allow_unfavorable_analysis_submit",
            "require_product_checklist",
            "match_product_client_type",
            "kyc_gate",
            "product_bounds_gate",
            "amount_approved_mode",
            "show_readiness_checklist",
            "enable_cancel_status",
            "allow_collateral_during_approval",
            "require_surety_signed_contracts",
            "require_formalization_before_disbursement",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class FinancialDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = FinancialDocument
        fields = ["id", "file", "label"]

    def to_representation(self, instance):
        return presign_file_fields(super().to_representation(instance), instance, "file")


class FinancialAnalysisSerializer(serializers.ModelSerializer):
    client_type = serializers.CharField(read_only=True)
    client_type_source = serializers.CharField(
        source="application.client.client_type", read_only=True
    )
    documents = FinancialDocumentSerializer(many=True, read_only=True)
    created_by_display = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()
    metrics = serializers.SerializerMethodField()
    thresholds = serializers.SerializerMethodField()

    def get_created_by_display(self, obj):
        return str(obj.created_by) if obj.created_by_id else ""

    def get_can_edit(self, obj):
        from .access import ANALYSIS_LOCKED_STATUSES, can_mutate_contribution

        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        if obj.application_id and obj.application.status in ANALYSIS_LOCKED_STATUSES:
            return False
        user = request.user
        if user.is_superuser:
            return True
        if obj.created_by_id != user.id:
            return False
        return can_mutate_contribution(obj.application, user)

    @staticmethod
    def _to_plain(value):
        from decimal import Decimal

        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, dict):
            return {
                k: FinancialAnalysisSerializer._to_plain(v)
                for k, v in value.items()
            }
        if isinstance(value, list):
            return [FinancialAnalysisSerializer._to_plain(v) for v in value]
        return value

    def get_metrics(self, obj):
        from .analytics import compute_metrics
        from .models import AnalysisThreshold

        th = AnalysisThreshold.for_tenant(obj.tenant_id)
        return self._to_plain(compute_metrics(obj, th))

    def get_thresholds(self, obj):
        from decimal import Decimal

        from .models import AnalysisThreshold

        th = AnalysisThreshold.for_tenant(obj.tenant_id)
        keys = [
            "max_debt_ratio", "min_dscr", "max_leverage_ratio",
            "min_living_wage_per_capita", "min_interest_coverage", "max_gearing",
            "min_financial_autonomy", "min_current_ratio",
            "min_guarantee_coverage", "stress_pct",
            "transferable_quota_fraction", "informal_income_weight",
            "haircut_mortgage", "haircut_vehicle", "haircut_jewelry",
            "haircut_financial_deposit", "haircut_financial_security",
            "haircut_other",
        ]
        out = {}
        for k in keys:
            v = getattr(th, k, None)
            out[k] = float(v) if isinstance(v, Decimal) else v
        return out

    # Valeurs dérivées (particulier)
    total_income = serializers.ReadOnlyField()
    total_household_charges = serializers.ReadOnlyField()
    disposable_income = serializers.ReadOnlyField()
    # Valeurs dérivées (entreprise)
    gross_margin = serializers.ReadOnlyField()
    total_operating_expenses = serializers.ReadOnlyField()
    ebe = serializers.ReadOnlyField()
    net_result = serializers.ReadOnlyField()
    cash_flow = serializers.ReadOnlyField()
    total_assets = serializers.ReadOnlyField()
    total_debts = serializers.ReadOnlyField()
    equity = serializers.ReadOnlyField()
    bfr = serializers.ReadOnlyField()
    gross_margin_pct = serializers.ReadOnlyField()
    net_margin_pct = serializers.ReadOnlyField()
    dependents_count = serializers.ReadOnlyField()
    disposable_per_capita = serializers.ReadOnlyField()
    projected_monthly_surplus = serializers.ReadOnlyField()
    collective_capacity = serializers.ReadOnlyField()
    # Drapeaux d'alerte
    flags = serializers.SerializerMethodField()

    class Meta:
        model = FinancialAnalysis
        fields = [
            "id", "application", "author_role", "created_by",
            "created_by_display", "can_edit",
            "is_reference",
            "client_type", "client_type_source",
            "individual_profile",
            "reference_period", "analysis_date",
            # Particulier
            "salary_income", "spouse_income", "rental_income",
            "other_activity_income", "other_income",
            "rent_expense", "food_expense", "utilities_expense",
            "transport_expense", "education_expense", "health_expense",
            "other_household_expenses",
            # Entreprise — exploitation
            "turnover", "cogs", "op_rent", "op_salaries", "op_utilities",
            "op_transport", "op_telecom", "op_taxes", "op_maintenance",
            "op_other", "depreciation", "financial_charges",
            # Entreprise — bilan
            "stock_value", "receivables", "cash_available", "fixed_assets",
            "supplier_debt", "ongoing_credit_balance", "short_term_debt",
            # Entreprise — N-1 (tendance)
            "turnover_prev", "net_result_prev",
            # Particulier — charges informelles & stabilité
            "tontine_expense", "social_contributions", "family_support_expense",
            "net_salary", "salary_deductions", "employment_seniority_months",
            "informal_income_weight",
            # Commun — endettement existant & consolidé
            "existing_debt_institution", "existing_debt_initial_amount",
            "existing_debt_monthly",
            "active_loans_count", "credit_bureau_checked", "credit_bureau_date",
            "has_payment_incidents", "max_days_late", "incidents_comment",
            "prior_loans_count", "prior_repayment_rate", "prior_max_delay_days",
            # Trésorerie prévisionnelle
            "projected_monthly_inflows", "projected_monthly_outflows",
            "projected_monthly_surplus", "cashflow_comment",
            # Indicateurs calculés
            "new_installment", "repayment_capacity", "debt_ratio", "dscr",
            "debt_ratio_stress", "dscr_stress", "guarantee_coverage",
            "metrics", "thresholds",
            # Dérivées
            "total_income", "total_household_charges", "disposable_income",
            "dependents_count", "disposable_per_capita",
            "gross_margin", "total_operating_expenses", "ebe", "net_result",
            "cash_flow", "total_assets", "total_debts", "equity", "bfr",
            "gross_margin_pct", "net_margin_pct",
            "collective_capacity",
            # Analyse sectorielle
            "sector", "sub_sector", "value_chain_position", "market_dynamic",
            "seasonality_level", "competition_intensity", "supplier_dependency",
            "client_concentration", "input_price_sensitivity", "fx_exposure",
            "regulatory_sensitivity", "climate_sensitivity", "sector_risk_level",
            "sector_outlook", "sector_comment",
            # Analyse environnementale & sociale (E&S)
            "es_category", "exclusion_list_ok", "env_permit_required",
            "env_permit_obtained", "permit_reference", "eia_required",
            "eia_done", "es_regulatory_compliance", "waste_management",
            "resource_use", "chemicals_pesticides", "nuisances_emissions",
            "working_conditions", "occupational_safety", "child_forced_labor_risk",
            "community_impact", "land_resettlement_risk", "jobs_created",
            "jobs_maintained", "jobs_women", "jobs_youth", "workforce_count",
            "es_mitigation_plan",
            "es_action_required", "es_insurance", "es_risk_level", "es_comment",
            # Personne physique — activité génératrice de revenus
            "has_side_activity", "activity_turnover", "activity_expenses",
            "activity_comment",
            # Groupement
            "members_count", "active_contributing_members",
            "solidarity_commitment", "collective_contributions",
            "collective_savings", "collective_other_income",
            "collective_operating_expenses", "group_activity_turnover",
            "group_activity_expenses", "group_comment",
            # Décision & synthèse
            "internal_score", "score_breakdown",
            "strengths", "weaknesses", "recommended_conditions",
            "recommendation", "comment",
            "flags", "documents", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "author_role", "created_by", "created_by_display", "can_edit",
            "is_reference",
            "client_type", "new_installment", "repayment_capacity",
            "debt_ratio", "dscr", "debt_ratio_stress", "dscr_stress",
            "guarantee_coverage", "internal_score", "score_breakdown",
            "metrics", "thresholds", "created_at", "updated_at",
        ]

    def validate(self, attrs):
        from apps.common.upload_validation import validate_attrs_uploads

        attrs = validate_attrs_uploads(attrs, self.context, check_quota=True)
        if (
            self.instance is not None
            and "application" in attrs
            and attrs["application"] != self.instance.application
        ):
            raise serializers.ValidationError(
                {"application": "Impossible de réaffecter l'analyse à un autre dossier."}
            )
        return attrs

    def get_flags(self, obj):
        """Indicateurs de conformité aux seuils de la filiale."""
        from .analytics import compute_metrics
        from .models import AnalysisThreshold

        th = AnalysisThreshold.for_tenant(obj.tenant_id)
        metrics = compute_metrics(obj, th)
        return metrics.get("flags", {})

    def _save_documents(self, analysis):
        request = self.context.get("request")
        if not request:
            return
        from apps.common.upload_validation import validate_uploaded_file

        for f in request.FILES.getlist("documents"):
            validate_uploaded_file(f, tenant=analysis.tenant, check_quota=True)
            FinancialDocument.objects.create(
                analysis=analysis,
                tenant_id=analysis.tenant_id,
                file=f,
            )

    def create(self, validated_data):
        application = validated_data.get("application")
        if (
            application is not None
            and getattr(application.client, "client_type", "") == "CORPORATE"
            and "reference_period" not in self.initial_data
        ):
            validated_data["reference_period"] = FinancialAnalysis.ReferencePeriod.ANNUAL
        elif (
            application is not None
            and getattr(application.client, "client_type", "") != "CORPORATE"
            and "reference_period" not in self.initial_data
        ):
            validated_data["reference_period"] = FinancialAnalysis.ReferencePeriod.MONTHLY
        analysis = super().create(validated_data)
        self._save_documents(analysis)
        return analysis

    def update(self, instance, validated_data):
        analysis = super().update(instance, validated_data)
        self._save_documents(analysis)
        return analysis


class FieldVisitSerializer(serializers.ModelSerializer):
    visited_by_display = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()

    def get_visited_by_display(self, obj):
        return str(obj.visited_by) if obj.visited_by_id else ""

    def get_can_edit(self, obj):
        from .access import can_mutate_contribution

        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        user = request.user
        if user.is_superuser:
            return True
        if obj.visited_by_id != user.id:
            return False
        return can_mutate_contribution(obj.application, user)

    class Meta:
        model = FieldVisit
        fields = [
            "id", "application", "visit_date", "visited_by",
            "visited_by_display", "visitor_role", "can_edit",
            "geo_coordinates", "report", "created_at",
        ]
        read_only_fields = [
            "id", "visited_by", "visited_by_display", "visitor_role",
            "can_edit", "created_at",
        ]

    def create(self, validated_data):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            from apps.accounts.utils import user_role_label

            validated_data["visited_by"] = request.user
            validated_data["visitor_role"] = user_role_label(request.user)
        return super().create(validated_data)

    def validate(self, attrs):
        if (
            self.instance is not None
            and "application" in attrs
            and attrs["application"] != self.instance.application
        ):
            raise serializers.ValidationError(
                {
                    "application": (
                        "Impossible de réaffecter la visite à un autre dossier."
                    )
                }
            )
        return attrs


class StockPhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockPhoto
        fields = ["id", "image", "caption"]

    def to_representation(self, instance):
        return presign_file_fields(super().to_representation(instance), instance, "image")


class CreditDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = CreditDocument
        fields = ["id", "application", "file", "label", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate_file(self, value):
        from apps.common.upload_validation import (
            resolve_tenant_from_context,
            validate_uploaded_file,
        )

        return validate_uploaded_file(
            value,
            tenant=resolve_tenant_from_context(self.context),
            check_quota=True,
        )

    def validate(self, attrs):
        if (
            self.instance is not None
            and "application" in attrs
            and attrs["application"] != self.instance.application
        ):
            raise serializers.ValidationError(
                {
                    "application": (
                        "Impossible de réaffecter la pièce à un autre dossier."
                    )
                }
            )
        return attrs

    def to_representation(self, instance):
        return presign_file_fields(super().to_representation(instance), instance, "file")


class CreditApplicationFeeSerializer(serializers.ModelSerializer):
    mode_display = serializers.CharField(source="get_mode_display", read_only=True)

    class Meta:
        model = CreditApplicationFee
        fields = ["id", "label", "mode", "mode_display", "value", "sort_order"]
        read_only_fields = ["id", "mode_display"]


class CreditApplicationListSerializer(serializers.ModelSerializer):
    """Liste allégée — sans documents, photos ni détail des frais."""

    client_display = serializers.CharField(source="client.display_name", read_only=True)
    client_reference = serializers.CharField(source="client.reference", read_only=True)
    product_label = serializers.CharField(source="product.label", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    agency_display = serializers.SerializerMethodField()
    submitted_by_display = serializers.SerializerMethodField()
    collection_case_id = serializers.SerializerMethodField()
    collection_stage_display = serializers.SerializerMethodField()

    class Meta:
        model = CreditApplication
        fields = [
            "id", "reference", "client", "client_display", "client_reference",
            "product", "product_label", "agency", "agency_display",
            "amount_requested", "amount_proposed", "amount_approved",
            "currency", "status", "status_display", "risk_level",
            "submitted_by", "submitted_by_display",
            "collection_case_id", "collection_stage_display",
            "created_at", "updated_at", "submitted_at",
        ]
        read_only_fields = fields

    def get_agency_display(self, obj):
        agency = getattr(obj, "agency", None)
        if agency is None:
            return ""
        return agency.name or agency.code or ""

    def get_submitted_by_display(self, obj):
        user = getattr(obj, "submitted_by", None)
        if user is None:
            return ""
        full = (user.get_full_name() or "").strip()
        return full or str(user)

    def get_collection_case_id(self, obj):
        return _collection_snapshot(_loan_of_application(obj))[0]

    def get_collection_stage_display(self, obj):
        return _collection_snapshot(_loan_of_application(obj))[2]


def _loan_of_application(application):
    try:
        return application.loan
    except (ObjectDoesNotExist, AttributeError):
        return None


def _collection_snapshot(loan):
    if loan is None:
        return None, "", ""
    try:
        case = loan.collection_case
    except (ObjectDoesNotExist, AttributeError):
        return None, "", ""
    if case is None:
        return None, "", ""
    return str(case.id), case.stage, case.get_stage_display()


class CreditApplicationSerializer(serializers.ModelSerializer):
    client_display = serializers.CharField(source="client.display_name", read_only=True)
    client_reference = serializers.CharField(source="client.reference", read_only=True)
    client_type = serializers.CharField(source="client.client_type", read_only=True)
    product_label = serializers.CharField(source="product.label", read_only=True)
    agency_display = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    stock_photos = StockPhotoSerializer(many=True, read_only=True)
    documents = CreditDocumentSerializer(many=True, read_only=True)
    extra_fees = CreditApplicationFeeSerializer(many=True, read_only=True)
    fees_breakdown = serializers.SerializerMethodField()
    submitted_by_display = serializers.SerializerMethodField()
    created_by_display = serializers.SerializerMethodField()
    cbs_refs = serializers.SerializerMethodField()
    periodicity_label = serializers.SerializerMethodField()
    repayment_mechanism_label = serializers.SerializerMethodField()
    currency_label = serializers.SerializerMethodField()
    collection_case_id = serializers.SerializerMethodField()
    collection_stage = serializers.SerializerMethodField()
    collection_stage_display = serializers.SerializerMethodField()
    loan_id = serializers.SerializerMethodField()

    def get_submitted_by_display(self, obj):
        return str(obj.submitted_by) if obj.submitted_by_id else ""

    def get_created_by_display(self, obj):
        return str(obj.created_by) if obj.created_by_id else ""

    def get_agency_display(self, obj):
        agency = getattr(obj, "agency", None)
        if agency is None:
            return ""
        return agency.name or agency.code or ""

    def get_fees_breakdown(self, obj):
        return build_fees_breakdown(obj)

    def get_cbs_refs(self, obj):
        cached = getattr(obj, "_cbs_refs_cache", None)
        if cached is None:
            from apps.catalog.cbs_resolve import application_cbs_refs

            cached = application_cbs_refs(obj)
            obj._cbs_refs_cache = cached
        return cached

    def get_periodicity_label(self, obj):
        refs = self.get_cbs_refs(obj)
        return (refs.get("periodicity") or {}).get("label") or obj.periodicity

    def get_repayment_mechanism_label(self, obj):
        refs = self.get_cbs_refs(obj)
        return (refs.get("repayment_method") or {}).get("label") or (
            obj.repayment_mechanism or ""
        )

    def get_currency_label(self, obj):
        refs = self.get_cbs_refs(obj)
        return (refs.get("currency") or {}).get("label") or obj.currency

    def get_collection_case_id(self, obj):
        return _collection_snapshot(_loan_of_application(obj))[0]

    def get_collection_stage(self, obj):
        return _collection_snapshot(_loan_of_application(obj))[1]

    def get_collection_stage_display(self, obj):
        return _collection_snapshot(_loan_of_application(obj))[2]

    def get_loan_id(self, obj):
        loan = _loan_of_application(obj)
        return str(loan.id) if loan is not None else None

    def to_representation(self, instance):
        return presign_file_fields(
            super().to_representation(instance), instance, "request_letter_scan"
        )

    class Meta:
        model = CreditApplication
        fields = [
            "id", "reference", "client", "client_display", "client_reference",
            "client_type", "product", "product_label", "agency", "agency_display",
            # Conditions
            "amount_requested", "amount_proposed", "interest_rate", "fees_rate",
            "mandatory_savings_rate",
            "extra_fees", "fees_breakdown",
            "periodicity", "periodicity_label",
            "duration_months", "first_due_date", "last_due_date",
            "repayment_mechanism", "repayment_mechanism_label",
            "purpose_type", "purpose",
            "request_letter_scan", "currency", "currency_label",
            "cbs_refs",
            # Plan de financement
            "project_total_cost", "personal_contribution", "financed_quota",
            # Activité (contexte opérationnel)
            "activity_start_date", "exact_address", "clientele",
            "tax_regime",
            "avg_client_payment_days", "avg_supplier_payment_days",
            "stock_photos", "documents",
            # Environnement commercial
            "catchment_area",
            # Patrimoine
            "premises_status",
            # Demandeur & emploi
            "employer_name", "contract_type",
            "salary_domiciliation", "dependents_count",
            # Relation bancaire
            "client_account_number", "relationship_start_date",
            "avg_monthly_credit_movements",
            # Assurance
            "has_credit_insurance", "insurance_company", "insurance_premium",
            # Conditions particulières
            "special_conditions", "suspensive_conditions",
            # Conformité
            "beneficial_owner", "is_pep", "funds_origin",
            # Complétude documentaire
            "document_checklist",
            # Suivi
            "status", "status_display", "risk_level",
            "amount_approved", "decision_date", "submitted_at", "disbursed_at",
            "disbursement_requested_at", "disbursement_requested_by",
            "cbs_demande_number", "cbs_demande_ref", "cbs_contract_number",
            "cbs_operation_date",
            "submitted_by", "submitted_by_display",
            "created_by", "created_by_display",
            "collection_case_id", "collection_stage", "collection_stage_display",
            "loan_id",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "reference", "last_due_date", "financed_quota", "status",
            "risk_level",
            "submitted_at", "disbursed_at",
            "disbursement_requested_at", "disbursement_requested_by",
            "cbs_demande_number", "cbs_demande_ref", "cbs_contract_number",
            "cbs_operation_date",
            "submitted_by",
            "submitted_by_display", "created_by", "created_by_display",
            "created_at", "updated_at",
            "extra_fees", "fees_breakdown",
            "cbs_refs", "periodicity_label", "repayment_mechanism_label",
            "currency_label", "agency_display",
            "collection_case_id", "collection_stage", "collection_stage_display",
            "loan_id",
        ]

    def validate(self, attrs):
        from apps.common.tenancy import get_current_tenant_id
        from apps.workflow.services import WorkflowError

        from .instruction_policy import (
            amount_approved_writable,
            assert_kyc_validated,
            assert_product_bounds,
            get_instruction_policy,
        )
        from .models import CreditInstructionPolicy

        instance = getattr(self, "instance", None)
        merged = instance
        if instance is None:
            # Objet transitoire pour les contrôles create
            class _Tmp:
                pass

            merged = _Tmp()
            merged.tenant_id = get_current_tenant_id()
            merged.status = CreditApplication.Status.DRAFT
            merged.client = attrs.get("client")
            merged.product = attrs.get("product")
            merged.amount_requested = attrs.get("amount_requested")
            merged.duration_months = attrs.get("duration_months")
            merged.amount_approved = attrs.get("amount_approved")
        else:
            for key, val in attrs.items():
                setattr(merged, key, val)

        policy = get_instruction_policy(getattr(merged, "tenant_id", None))

        if "amount_approved" in attrs and attrs["amount_approved"] is not None:
            if instance is None or not amount_approved_writable(instance):
                if (
                    policy.amount_approved_mode
                    == CreditInstructionPolicy.AmountApprovedMode.FORBID
                ):
                    raise serializers.ValidationError(
                        {
                            "amount_approved": (
                                "La politique filiale réserve le montant approuvé "
                                "à la décision du circuit."
                            )
                        }
                    )

        if (
            policy.kyc_gate == CreditInstructionPolicy.KycGate.ON_CREATE
            and instance is None
            and merged.client is not None
        ):
            try:
                assert_kyc_validated(merged)
            except WorkflowError as exc:
                raise serializers.ValidationError({"client": str(exc)}) from exc

        if (
            policy.product_bounds_gate
            == CreditInstructionPolicy.BoundsGate.ON_SAVE
            and merged.product is not None
        ):
            try:
                assert_product_bounds(merged)
            except WorkflowError as exc:
                raise serializers.ValidationError(str(exc)) from exc

        if (
            policy.match_product_client_type
            and merged.product is not None
            and merged.client is not None
        ):
            from .instruction_policy import _product_client_type_ok

            if not _product_client_type_ok(merged):
                raise serializers.ValidationError(
                    {
                        "product": (
                            "Le type de client ne correspond pas à ce produit."
                        )
                    }
                )

        tenant_id = getattr(merged, "tenant_id", None) or get_current_tenant_id()
        self._validate_catalog_refs(attrs, tenant_id)
        from apps.common.upload_validation import validate_attrs_uploads

        attrs = validate_attrs_uploads(attrs, self.context, check_quota=True)
        return attrs

    def _validate_catalog_refs(self, attrs, tenant_id):
        """Valide périodicité / mécanisme / devise contre le référentiel filiale."""
        from apps.catalog.cbs_resolve import active_codes
        from apps.catalog.models import Currency, LoanPeriodicity, RepaymentMethod

        checks = [
            ("periodicity", LoanPeriodicity, "périodicité"),
            ("repayment_mechanism", RepaymentMethod, "méthode de remboursement"),
            ("currency", Currency, "devise"),
        ]
        errors = {}
        for field, model, label in checks:
            if field not in attrs:
                continue
            value = attrs.get(field)
            if value in (None, ""):
                continue
            codes = active_codes(model, tenant_id)
            if codes and str(value) not in codes:
                errors[field] = (
                    f"{label.capitalize()} « {value} » inconnue dans le "
                    f"référentiel filiale. Paramétrez-la dans Administration."
                )
        if errors:
            raise serializers.ValidationError(errors)

    def _save_stock_photos(self, application):
        request = self.context.get("request")
        if not request:
            return
        from apps.common.upload_validation import validate_uploaded_file

        for image in request.FILES.getlist("stock_photos"):
            validate_uploaded_file(image, tenant=application.tenant, check_quota=True)
            StockPhoto.objects.create(
                application=application,
                tenant_id=application.tenant_id,
                image=image,
            )

    def _save_extra_fees(self, application):
        request = self.context.get("request")
        if not request or "extra_fees" not in request.data:
            return
        try:
            sync_extra_fees(application, request.data.get("extra_fees"))
        except ValueError as exc:
            raise serializers.ValidationError({"extra_fees": str(exc)}) from exc

    def create(self, validated_data):
        application = super().create(validated_data)
        self._save_stock_photos(application)
        self._save_extra_fees(application)
        return application

    def update(self, instance, validated_data):
        application = super().update(instance, validated_data)
        self._save_stock_photos(application)
        self._save_extra_fees(application)
        return application


class InstallmentSerializer(serializers.ModelSerializer):
    balance = serializers.DecimalField(
        max_digits=18, decimal_places=2, read_only=True
    )

    class Meta:
        model = Installment
        fields = [
            "id", "loan", "number", "due_date", "principal_due",
            "interest_due", "savings_due", "total_due", "amount_paid",
            "balance", "status",
        ]
        read_only_fields = fields


class LoanListSerializer(serializers.ModelSerializer):
    """Liste légère (sans échéancier)."""

    application_reference = serializers.CharField(
        source="application.reference", read_only=True
    )
    currency = serializers.CharField(
        source="application.currency", read_only=True
    )
    client_display = serializers.SerializerMethodField()
    collection_case_id = serializers.SerializerMethodField()
    collection_stage = serializers.SerializerMethodField()
    collection_stage_display = serializers.SerializerMethodField()

    class Meta:
        model = Loan
        fields = [
            "id",
            "application",
            "application_reference",
            "client_display",
            "currency",
            "principal",
            "interest_rate",
            "duration_months",
            "disbursed_at",
            "first_due_date",
            "status",
            "core_banking_reference",
            "cbs_contract_number",
            "cbs_disbursement_status",
            "collection_case_id",
            "collection_stage",
            "collection_stage_display",
        ]
        read_only_fields = fields

    def get_collection_case_id(self, obj):
        return _collection_snapshot(obj)[0]

    def get_collection_stage(self, obj):
        return _collection_snapshot(obj)[1]

    def get_collection_stage_display(self, obj):
        return _collection_snapshot(obj)[2]

    def get_client_display(self, obj):
        client = getattr(obj.application, "client", None)
        if client is None:
            return ""
        return getattr(client, "display_name", None) or str(client)


class LoanSerializer(serializers.ModelSerializer):
    installments = InstallmentSerializer(many=True, read_only=True)
    fees_breakdown = serializers.SerializerMethodField()
    application_reference = serializers.CharField(
        source="application.reference", read_only=True
    )
    currency = serializers.CharField(
        source="application.currency", read_only=True
    )
    collection_case_id = serializers.SerializerMethodField()
    collection_stage = serializers.SerializerMethodField()
    collection_stage_display = serializers.SerializerMethodField()
    outstanding_principal = serializers.SerializerMethodField()
    restructures = serializers.SerializerMethodField()
    write_offs = serializers.SerializerMethodField()
    financial_ops_frozen = serializers.SerializerMethodField()
    financial_ops_frozen_reason = serializers.SerializerMethodField()

    class Meta:
        model = Loan
        fields = [
            "id", "application", "application_reference", "currency",
            "principal", "interest_rate",
            "mandatory_savings_rate", "duration_months", "disbursed_at",
            "first_due_date", "status", "core_banking_reference",
            "cbs_external_id", "cbs_demande_number", "cbs_demande_ref",
            "cbs_contract_number", "cbs_disbursement_status",
            "installments", "fees_breakdown",
            "collection_case_id", "collection_stage", "collection_stage_display",
            "outstanding_principal", "restructures", "write_offs",
            "financial_ops_frozen", "financial_ops_frozen_reason",
        ]
        read_only_fields = fields

    def get_collection_case_id(self, obj):
        return _collection_snapshot(obj)[0]

    def get_collection_stage(self, obj):
        return _collection_snapshot(obj)[1]

    def get_collection_stage_display(self, obj):
        return _collection_snapshot(obj)[2]

    def get_fees_breakdown(self, obj):
        return build_fees_breakdown(obj.application)

    def get_outstanding_principal(self, obj):
        from apps.collections.services import outstanding_principal

        return str(outstanding_principal(obj))

    def get_restructures(self, obj):
        from apps.collections.serializers import LoanRestructureSerializer

        qs = obj.restructures.select_related("requested_by", "applied_by").all()
        return LoanRestructureSerializer(qs, many=True, context=self.context).data

    def get_write_offs(self, obj):
        from apps.collections.serializers import WriteOffSerializer

        qs = obj.write_offs.select_related("requested_by", "approved_by").all()
        return WriteOffSerializer(qs, many=True, context=self.context).data

    def get_financial_ops_frozen(self, obj):
        from apps.collections.dation_bridge import financial_ops_block_for_loan

        blocked, _, _ = financial_ops_block_for_loan(obj)
        return blocked

    def get_financial_ops_frozen_reason(self, obj):
        from apps.collections.dation_bridge import financial_ops_block_for_loan

        blocked, reason, _ = financial_ops_block_for_loan(obj)
        return reason if blocked else ""


class SimulationSerializer(serializers.Serializer):
    """Entrée d'une simulation de crédit."""

    amount = serializers.DecimalField(
        max_digits=18, decimal_places=2, min_value=Decimal("1")
    )
    annual_rate = serializers.DecimalField(
        max_digits=6, decimal_places=3, min_value=Decimal("0")
    )
    months = serializers.IntegerField(min_value=1, max_value=600)
    periodicity = serializers.CharField(required=False, default="MONTHLY")
    first_due_date = serializers.DateField(required=False, allow_null=True)
    simulation_date = serializers.DateField(required=False, allow_null=True)
    savings_rate = serializers.DecimalField(
        max_digits=6, decimal_places=3, min_value=Decimal("0"),
        required=False, default=Decimal("0"),
    )
    mechanism = serializers.CharField(required=False, default="DEGRESSIVE")

    def validate(self, attrs):
        from apps.catalog.cbs_resolve import active_codes
        from apps.catalog.models import LoanPeriodicity, RepaymentMethod
        from apps.common.tenancy import get_current_tenant_id

        tenant_id = get_current_tenant_id()
        periodicity = attrs.get("periodicity") or "MONTHLY"
        mechanism = attrs.get("mechanism") or "DEGRESSIVE"
        period_codes = active_codes(LoanPeriodicity, tenant_id)
        if period_codes and periodicity not in period_codes:
            raise serializers.ValidationError(
                {
                    "periodicity": (
                        f"Périodicité « {periodicity} » inconnue dans le "
                        f"référentiel filiale."
                    )
                }
            )
        remb_codes = active_codes(RepaymentMethod, tenant_id)
        if remb_codes and mechanism not in remb_codes:
            raise serializers.ValidationError(
                {
                    "mechanism": (
                        f"Mécanisme « {mechanism} » inconnu dans le "
                        f"référentiel filiale."
                    )
                }
            )
        return attrs
