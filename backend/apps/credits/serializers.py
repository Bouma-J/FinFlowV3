import json
from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from rest_framework import serializers

from apps.common.storage_urls import presign_file_fields

from .fees import build_fees_breakdown, parse_extra_fees, sync_extra_fees
from .models import (
    AnalysisThreshold,
    CreditApplication,
    CreditApplicationFee,
    CreditDocument,
    ExternalBankAccount,
    CreditInstructionPolicy,
    FieldVisit,
    FieldVisitPhoto,
    FinancialAnalysis,
    FinancialDocument,
    Installment,
    Loan,
    StockPhoto,
)


class AnalysisThresholdSerializer(serializers.ModelSerializer):
    def validate(self, attrs):
        from apps.configuration.governance import assert_legacy_configuration_write_allowed
        assert_legacy_configuration_write_allowed()
        return attrs

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
    def validate(self, attrs):
        from apps.configuration.governance import assert_legacy_configuration_write_allowed
        assert_legacy_configuration_write_allowed()
        return attrs

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
            "require_credit_contracts", "require_credit_signed_contracts",
            "require_surety_contracts", "require_setup_request", "require_setup_four_eyes",
            "risk_mode", "approval_validity_days", "max_analysis_age_days",
            "require_final_review", "recheck_kyc_on_setup", "require_verified_documents",
            "setup_execution_role", "require_setup_authorizer_separation",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "require_final_review"]


class FinancialDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = FinancialDocument
        fields = ["id", "file", "label"]

    def to_representation(self, instance):
        return presign_file_fields(super().to_representation(instance), instance, "file")


class FinancialAnalysisSerializer(serializers.ModelSerializer):
    is_reference = serializers.BooleanField(required=False)
    new_installment = serializers.SerializerMethodField()
    internal_score = serializers.SerializerMethodField()
    score_breakdown = serializers.SerializerMethodField()
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
        from apps.accounts.capabilities import is_tenant_administrator

        if user.is_superuser or is_tenant_administrator(user):
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

    def _current_metrics(self, obj):
        from .analytics import compute_metrics
        from .models import AnalysisThreshold

        cache = getattr(self, "_current_metrics_cache", {})
        if obj.pk not in cache:
            th = AnalysisThreshold.for_application(obj.application, individual_profile=obj.individual_profile)
            cache[obj.pk] = compute_metrics(obj, th, recalculate_installment=True)
            self._current_metrics_cache = cache
        return cache[obj.pk]

    def get_metrics(self, obj):
        return self._to_plain(self._current_metrics(obj))

    def get_new_installment(self, obj):
        return self._to_plain(self._current_metrics(obj).get("contractual_installment"))

    def _configured_score(self, obj):
        from .analytics import compute_score

        cache = getattr(self, "_configured_scores", {})
        key = str(obj.pk)
        if key not in cache:
            th = AnalysisThreshold.for_application(obj.application, individual_profile=obj.individual_profile)
            cache[key] = compute_score(obj, self._current_metrics(obj), th)
            self._configured_scores = cache
        return cache[key]

    def get_internal_score(self, obj):
        score, _ = self._configured_score(obj)
        return str(score) if score is not None else None

    def get_score_breakdown(self, obj):
        _, breakdown = self._configured_score(obj)
        return self._to_plain(breakdown)

    def get_thresholds(self, obj):
        from decimal import Decimal

        from .models import AnalysisThreshold

        th = AnalysisThreshold.for_application(obj.application, individual_profile=obj.individual_profile)
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
            "reference_period", "analysis_date", "analysis_details", "custom_fields",
            # Cadre, fiabilité et vérification
            "information_quality", "financial_statement_date",
            "bank_statement_months", "financial_documents_verified",
            "field_visit_confirmed", "stock_count_verified",
            "cash_position_verified", "verification_comment",
            "primary_repayment_source",
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
            "other_operating_income",
            # Entreprise — bilan
            "stock_value", "receivables", "cash_available", "fixed_assets",
            "supplier_debt", "ongoing_credit_balance", "short_term_debt",
            "cash_in_hand", "bank_balance", "other_current_assets",
            "land_building_value", "equipment_value", "vehicle_value",
            "other_fixed_assets", "tax_social_debt", "other_current_debt",
            "long_term_debt", "shareholder_debt",
            # Entreprise — N-1 (tendance)
            "turnover_prev", "net_result_prev",
            # Particulier — charges informelles & stabilité
            "tontine_expense", "social_contributions", "family_support_expense",
            "net_salary", "salary_deductions", "employment_seniority_months",
            "informal_income_weight", "employment_type", "employer_name",
            "employer_sector", "salary_paid_through_bank", "salary_verified",
            "variable_income", "pension_income", "other_monthly_obligations",
            "personal_savings", "personal_real_estate_value",
            "personal_vehicle_value", "personal_productive_assets",
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
            "activity_comment", "activity_name", "activity_business_age_months",
            "activity_sales_days", "activity_purchases", "activity_stock_value",
            "activity_receivables", "activity_cash_available",
            "activity_fixed_assets", "activity_supplier_debt",
            "activity_is_formal", "activity_records_available",
            # Groupement
            "members_count", "active_contributing_members",
            "solidarity_commitment", "collective_contributions",
            "collective_savings", "collective_other_income",
            "collective_operating_expenses", "group_activity_turnover",
            "group_activity_expenses", "group_comment", "group_age_months",
            "members_with_arrears", "group_records_verified",
            "collective_savings_locked",
            # Décision & synthèse
            "internal_score", "score_breakdown",
            "strengths", "weaknesses", "recommended_conditions",
            "recommendation", "comment",
            "flags", "documents", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "author_role", "created_by", "created_by_display", "can_edit",
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
        if "analysis_details" in attrs:
            from .analysis_details import apply_reference_statement
            application = attrs.get("application", getattr(self.instance, "application", None))
            client = getattr(application, "client", None) if application is not None else None
            apply_reference_statement(attrs, client_type=getattr(client, "client_type", None))
        errors = {}
        for name, value in attrs.items():
            if isinstance(value, Decimal) and name not in ("net_result_prev",) and value < 0:
                errors[name] = "Le montant doit être positif ou nul."
        for name in ("informal_income_weight", "prior_repayment_rate"):
            if attrs.get(name) is not None and attrs[name] > 100:
                errors[name] = "Le pourcentage doit être compris entre 0 et 100."
        def current(name):
            return attrs.get(name, getattr(self.instance, name, None))
        application = attrs.get("application", getattr(self.instance, "application", None))
        if application and "custom_fields" in attrs:
            from apps.configuration.forms_catalog import validate_custom_values
            from apps.configuration.services import application_configuration
            from django.core.exceptions import ValidationError as DjangoValidationError
            configuration = application_configuration(application, individual_profile=current("individual_profile"))
            try:
                attrs["custom_fields"] = validate_custom_values(
                    configuration["forms"]["analysis_fields"], attrs["custom_fields"],
                    previous=getattr(self.instance, "custom_fields", {}) or {}, require=False,
                )
            except DjangoValidationError as exc:
                raise serializers.ValidationError({"custom_fields": exc.messages}) from exc
        frozen = getattr(application, "configuration_snapshot", None) or {}
        if (application and application.status not in {"DRAFT", "RETURNED"}
                and frozen and "individual_profile" in attrs
                and attrs["individual_profile"] != frozen.get("context", {}).get("individual_profile")):
            errors["individual_profile"] = "Le profil de clientèle est conservé avec les règles soumises. Faites retourner ou réexaminer le dossier avant de le changer."
        if (current("long_term_debt") or 0) > (current("ongoing_credit_balance") or 0):
            errors["long_term_debt"] = "La part long terme ne peut dépasser l'encours financier total."
        for name in ("active_contributing_members", "members_with_arrears"):
            if current(name) is not None and current("members_count") is not None:
                if current(name) > current("members_count"):
                    errors[name] = "Le nombre ne peut dépasser l'effectif du groupement."
        if current("credit_bureau_checked") and not current("credit_bureau_date"):
            errors["credit_bureau_date"] = "Précisez la date de consultation."
        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    def validate_analysis_details(self, value):
        from .analysis_details import validate_details

        return validate_details(value)

    def get_flags(self, obj):
        """Indicateurs de conformité aux seuils de la filiale."""
        return self._current_metrics(obj).get("flags", {})

    def to_representation(self, instance):
        """Toutes les cartes courantes partagent le même calcul et les mêmes seuils.

        Les anciennes valeurs enregistrées restent identifiées séparément ;
        une lecture ne réécrit jamais l'analyse ni la décision historique.
        """
        from apps.configuration.services import application_configuration
        from apps.credits.amounts import reference_amount, reference_amount_label
        from django.utils import timezone

        data = super().to_representation(instance)
        metrics = self._current_metrics(instance)
        names = ("new_installment", "repayment_capacity", "debt_ratio", "dscr", "dscr_stress", "debt_ratio_stress", "guarantee_coverage", "internal_score")
        data["recorded_indicators"] = {
            "updated_at": instance.updated_at,
            **{name: self._to_plain(getattr(instance, name)) for name in names},
        }
        mapping = {"new_installment": "contractual_installment", "repayment_capacity": "repayment_capacity",
                   "debt_ratio": "solvency_ratio" if instance.is_corporate else "debt_ratio",
                   "dscr": "global_dscr", "dscr_stress": "dscr_stress", "debt_ratio_stress": "debt_ratio_stress",
                   "guarantee_coverage": "guarantee_coverage"}
        data.update({name: self._to_plain(metrics.get(key)) for name, key in mapping.items()})
        config = application_configuration(instance.application, individual_profile=instance.individual_profile)
        data["calculation_context"] = self._to_plain({
            "calculated_at": timezone.now().isoformat(), "amount": reference_amount(instance.application),
            "amount_label": reference_amount_label(instance.application), "currency": instance.application.currency,
            "periodicity": instance.application.periodicity, "duration_months": instance.application.duration_months,
            "mechanism": instance.application.repayment_mechanism or "DEGRESSIVE", "frozen": bool(config.get("frozen")),
            "legacy": bool(config.get("legacy")), "captured_at": config.get("captured_at"),
            "application_status": instance.application.status,
            "sources": config.get("sources", []), "rates": metrics.get("calculation_rates", {}),
            "project_total_cost": instance.application.project_total_cost,
            "personal_contribution": instance.application.personal_contribution,
            "financed_quota": instance.application.financed_quota,
            "activity_start_date": instance.application.activity_start_date.isoformat() if instance.application.activity_start_date else None,
            "purpose_type": instance.application.purpose_type,
        })
        data["custom_field_definitions"] = config.get("forms", {}).get("analysis_fields", [])
        return data

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
        self._save_statement_documents(analysis, request)
        self._save_minimal_cash_document(analysis, request)

    def _save_statement_documents(self, analysis, request):
        from apps.credits.analysis_details import STATEMENT_PIECES

        details = analysis.analysis_details or {}
        rows = details.get("financial_statements")
        if not isinstance(rows, list):
            return
        from apps.common.upload_validation import validate_uploaded_file

        titles = {
            "income": "Compte de résultat",
            "balance": "Bilan",
            "cashflow": "Tableau des flux",
            "notes": "Notes annexes",
        }
        changed = False
        for row in rows:
            if not isinstance(row, dict):
                continue
            exercise_id = str(row.get("id") or "")
            documents = row.get("documents")
            if not isinstance(documents, dict):
                documents = {}
                row["documents"] = documents
            exercise_label = str(row.get("label") or "Exercice")[:40]
            for piece in STATEMENT_PIECES:
                uploaded = request.FILES.get(f"statement_file__{exercise_id}__{piece}")
                if uploaded is None:
                    continue
                validate_uploaded_file(uploaded, tenant=analysis.tenant, check_quota=True)
                previous = documents.get(piece) or ""
                document = FinancialDocument.objects.create(
                    analysis=analysis,
                    tenant_id=analysis.tenant_id,
                    file=uploaded,
                    label=f"{titles[piece]} · {exercise_label}"[:150],
                )
                documents[piece] = str(document.id)
                changed = True
                if previous:
                    FinancialDocument.objects.filter(analysis=analysis, pk=previous).delete()
        if changed:
            analysis.analysis_details = details
            analysis.save(update_fields=["analysis_details", "updated_at"])

    def _save_minimal_cash_document(self, analysis, request):
        uploaded = request.FILES.get("minimal_cash_file")
        if uploaded is None:
            return
        details = analysis.analysis_details or {}
        if details.get("minimal_cash_open") != "yes":
            return
        from apps.common.upload_validation import validate_uploaded_file

        validate_uploaded_file(uploaded, tenant=analysis.tenant, check_quota=True)
        previous = str(details.get("minimal_cash_document") or "")
        period = str(details.get("minimal_cash_label") or "").strip()
        label = "Trésorerie minimale" + (f" · {period}" if period else "")
        document = FinancialDocument.objects.create(
            analysis=analysis,
            tenant_id=analysis.tenant_id,
            file=uploaded,
            label=label[:150],
        )
        details["minimal_cash_document"] = str(document.id)
        analysis.analysis_details = details
        analysis.save(update_fields=["analysis_details", "updated_at"])
        if previous:
            FinancialDocument.objects.filter(analysis=analysis, pk=previous).delete()

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


class FieldVisitPhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model = FieldVisitPhoto
        fields = ["id", "image"]
        read_only_fields = fields

    def to_representation(self, instance):
        return presign_file_fields(super().to_representation(instance), instance, "image")


class VisitPlaceListField(serializers.Field):
    CODES = {choice for choice, _label in FieldVisit.Place.choices}

    def to_internal_value(self, data):
        if isinstance(data, str):
            raw = data.strip()
            if not raw:
                return []
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise serializers.ValidationError("Indiquez les lieux visités.") from exc
        if data in (None, ""):
            return []
        if not isinstance(data, list):
            raise serializers.ValidationError("Indiquez les lieux visités.")
        clean = []
        for item in data:
            code = str(item).strip()
            if code not in self.CODES:
                raise serializers.ValidationError("Lieu visité inconnu.")
            if code not in clean:
                clean.append(code)
        return clean

    def to_representation(self, value):
        return list(value or [])


class FieldVisitSerializer(serializers.ModelSerializer):
    visited_by_display = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()
    visited_places = VisitPlaceListField(required=False)
    photos = FieldVisitPhotoSerializer(many=True, read_only=True)

    def get_visited_by_display(self, obj):
        return str(obj.visited_by) if obj.visited_by_id else ""

    def get_can_edit(self, obj):
        from .access import can_mutate_contribution

        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        user = request.user
        from apps.accounts.capabilities import is_tenant_administrator

        if user.is_superuser or is_tenant_administrator(user):
            return True
        if obj.visited_by_id != user.id:
            return False
        return can_mutate_contribution(obj.application, user)

    class Meta:
        model = FieldVisit
        fields = [
            "id", "application", "visit_date", "visited_by",
            "visited_by_display", "visitor_role", "can_edit",
            "geo_coordinates", "visited_places", "person_met", "conclusion",
            "report", "minutes", "photos", "created_at",
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
        visit = super().create(validated_data)
        self._save_photos(visit)
        return visit

    def _save_photos(self, visit):
        request = self.context.get("request")
        if not request:
            return
        from apps.common.upload_validation import validate_uploaded_file

        for image in request.FILES.getlist("photos"):
            validate_uploaded_file(image, tenant=visit.tenant, check_quota=True)
            FieldVisitPhoto.objects.create(
                visit=visit,
                tenant_id=visit.tenant_id,
                image=image,
            )

    def validate_minutes(self, value):
        if not value:
            return value
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
                        "Impossible de réaffecter la visite à un autre dossier."
                    )
                }
            )
        return attrs

    def to_representation(self, instance):
        return presign_file_fields(
            super().to_representation(instance), instance, "minutes",
        )


class ExternalBankAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExternalBankAccount
        fields = [
            "id", "institution_name", "opened_on", "account_number",
            "credit_movement_count", "credit_movement_volume", "statement",
        ]
        read_only_fields = fields

    def to_representation(self, instance):
        return presign_file_fields(
            super().to_representation(instance), instance, "statement"
        )


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


class EmptyAsNullIntegerField(serializers.IntegerField):
    def to_internal_value(self, data):
        if data is None or data == "":
            return None
        return super().to_internal_value(data)


class EmptyAsNullBooleanField(serializers.BooleanField):
    def to_internal_value(self, data):
        if data is None or data == "":
            return None
        return super().to_internal_value(data)


class EmptyAsNullDateField(serializers.DateField):
    def to_internal_value(self, data):
        if data is None or data == "":
            return None
        return super().to_internal_value(data)


SPOUSE_WRITE_FIELDS = ("spouse_first_name", "spouse_phone", "spouse_profession")


class CreditApplicationSerializer(serializers.ModelSerializer):
    children_count = EmptyAsNullIntegerField(allow_null=True, required=False, min_value=0)
    housing_seniority_months = EmptyAsNullIntegerField(allow_null=True, required=False, min_value=0)
    job_seniority_months = EmptyAsNullIntegerField(allow_null=True, required=False, min_value=0)
    career_seniority_months = EmptyAsNullIntegerField(allow_null=True, required=False, min_value=0)
    spouse_has_income = EmptyAsNullBooleanField(allow_null=True, required=False)
    activity_start_date = EmptyAsNullDateField(allow_null=True, required=False)
    contract_end_date = EmptyAsNullDateField(allow_null=True, required=False)
    spouse_first_name = serializers.CharField(required=False, allow_blank=True, write_only=True)
    spouse_phone = serializers.CharField(required=False, allow_blank=True, write_only=True)
    spouse_profession = serializers.CharField(required=False, allow_blank=True, write_only=True)
    interest_rate = serializers.DecimalField(max_digits=6, decimal_places=3, min_value=Decimal("0"), required=False, allow_null=True)
    fees_rate = serializers.DecimalField(max_digits=6, decimal_places=3, min_value=Decimal("0"), max_value=Decimal("100"), required=False, allow_null=True)
    mandatory_savings_rate = serializers.DecimalField(max_digits=6, decimal_places=3, min_value=Decimal("0"), max_value=Decimal("100"), required=False, allow_null=True)
    pricing_quote = serializers.SerializerMethodField()
    client_display = serializers.CharField(source="client.display_name", read_only=True)
    client_reference = serializers.CharField(source="client.reference", read_only=True)
    client_type = serializers.CharField(source="client.client_type", read_only=True)
    product_label = serializers.CharField(source="product.label", read_only=True)
    agency_display = serializers.SerializerMethodField()
    can_add_financial_analysis = serializers.SerializerMethodField()
    can_add_field_visit = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    stock_photos = StockPhotoSerializer(many=True, read_only=True)
    external_accounts = ExternalBankAccountSerializer(many=True, read_only=True)
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

    def _request_user(self):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return None
        return user

    def get_can_add_financial_analysis(self, obj):
        from .access import can_add_financial_analysis

        user = self._request_user()
        return bool(
            user
            and user.has_perm("credits.add_financialanalysis")
            and can_add_financial_analysis(obj, user)
        )

    def get_can_add_field_visit(self, obj):
        from .access import can_add_field_visit

        user = self._request_user()
        return bool(
            user
            and user.has_perm("credits.add_fieldvisit")
            and can_add_field_visit(obj, user)
        )

    def get_fees_breakdown(self, obj):
        return self.get_pricing_quote(obj)["fees"]

    def get_pricing_quote(self, obj):
        from .pricing import quote_pricing
        if not hasattr(self, "_pricing_quotes"):
            self._pricing_quotes = {}
        if obj.pk not in self._pricing_quotes:
            self._pricing_quotes[obj.pk] = quote_pricing(obj)
        return self._pricing_quotes[obj.pk]

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
            "can_add_financial_analysis", "can_add_field_visit",
            # Conditions
            "amount_requested", "amount_proposed", "interest_rate", "fees_rate",
            "mandatory_savings_rate",
            "extra_fees", "fees_breakdown", "pricing_quote",
            "periodicity", "periodicity_label",
            "duration_months", "first_due_date", "last_due_date",
            "repayment_mechanism", "repayment_mechanism_label",
            "purpose_type", "financing_object", "purpose",
            "request_letter_scan", "currency", "currency_label",
            "cbs_refs",
            # Plan de financement
            "project_total_cost", "personal_contribution", "financed_quota",
            # Activité (contexte opérationnel)
            "activity_start_date", "exact_address", "clientele",
            "tax_regime",
            "avg_client_payment_days", "avg_supplier_payment_days",
            "stock_photos", "documents", "external_accounts",
            # Environnement commercial
            "catchment_area",
            # Patrimoine
            "premises_status",
            # Demandeur & emploi
            "employer_name", "contract_type", "contract_end_date",
            "salary_domiciliation", "dependents_count",
            "earning_path", "marital_regime", "spouse_has_income", "children_count",
            "housing_status", "housing_seniority_months",
            "employer_address", "employer_phone", "employer_sector",
            "employment_profession", "job_title",
            "job_seniority_months", "career_seniority_months",
            "activity_name", "activity_trade", "activity_sector",
            "activity_premises_status", "activity_ifu",
            "spouse_first_name", "spouse_phone", "spouse_profession",
            # Relation bancaire
            "client_account_number", "relationship_start_date",
            "avg_monthly_credit_movements",
            # Assurance
            "has_credit_insurance", "insurance_company", "insurance_premium", "insurance_policy_number", "insurance_expiry_date",
            # Conditions particulières
            "special_conditions", "suspensive_conditions",
            # Conformité
            "beneficial_owner", "is_pep", "pep_details", "funds_origin",
            # Complétude documentaire
            "document_checklist",
            # Suivi
            "status", "status_display", "risk_level",
            "amount_approved", "decision_date", "submitted_at", "disbursed_at",
            "approval_snapshot", "approval_fingerprint", "setup_review", "setup_authorization", "configuration_snapshot",
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
            "approval_snapshot", "approval_fingerprint", "setup_review", "setup_authorization", "configuration_snapshot",
            "risk_level",
            "submitted_at", "disbursed_at",
            "disbursement_requested_at", "disbursement_requested_by",
            "cbs_demande_number", "cbs_demande_ref", "cbs_contract_number",
            "cbs_operation_date",
            "submitted_by",
            "submitted_by_display", "created_by", "created_by_display",
            "created_at", "updated_at",
            "extra_fees", "fees_breakdown", "pricing_quote",
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
            merged.agency_id = getattr(attrs.get("agency"), "pk", None) or getattr(
                getattr(self.context.get("request"), "user", None), "agency_id", None)
            merged.amount_requested = attrs.get("amount_requested")
            merged.duration_months = attrs.get("duration_months")
            merged.amount_approved = attrs.get("amount_approved")
        else:
            for key, val in attrs.items():
                setattr(merged, key, val)

        policy = get_instruction_policy(getattr(merged, "tenant_id", None), application=merged)

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
        request = self.context.get("request")
        if request and "extra_fees" in request.data:
            try:
                parse_extra_fees(request.data.get("extra_fees"))
            except ValueError as exc:
                raise serializers.ValidationError({"extra_fees": str(exc)}) from exc
        contract_type = attrs.get(
            "contract_type",
            getattr(self.instance, "contract_type", "") if self.instance else "",
        )
        if contract_type != "CDD":
            attrs["contract_end_date"] = None
        is_pep = attrs.get(
            "is_pep",
            getattr(self.instance, "is_pep", False) if self.instance else False,
        )
        if not is_pep:
            attrs["pep_details"] = ""
        client = attrs.get("client") or (self.instance.client if self.instance else None)
        if getattr(client, "client_type", None) == "INDIVIDUAL":
            attrs["beneficial_owner"] = ""
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
        if (self.instance is None or "financing_object" in attrs) and not attrs.get("financing_object"):
            from apps.corebanking.disbursement import requires_financing_object

            if requires_financing_object(tenant_id):
                errors["financing_object"] = "Sélectionnez l'objet de financement CBS exact dans le référentiel importé."
        if attrs.get("financing_object") is not None:
            obj = attrs["financing_object"]
            if str(obj.tenant_id) != str(tenant_id) or not obj.is_active or not obj.cbs_code.strip():
                errors["financing_object"] = "Sélectionnez un objet CBS actif importé pour cette filiale."
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
        children = attrs.get("children_count", getattr(self.instance, "children_count", None) if self.instance else None)
        dependents = attrs.get("dependents_count", getattr(self.instance, "dependents_count", None) if self.instance else None)
        if children is not None and dependents is not None and children > dependents:
            raise serializers.ValidationError({
                "children_count": "Le nombre d'enfants ne peut pas dépasser le nombre de personnes à charge.",
            })

    def _save_external_accounts(self, application):
        request = self.context.get("request")
        if not request or "external_accounts" not in request.data:
            return
        raw = request.data.get("external_accounts")
        try:
            rows = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError as exc:
            raise serializers.ValidationError({
                "external_accounts": "La liste des comptes hors institution est illisible.",
            }) from exc
        if not isinstance(rows, list):
            raise serializers.ValidationError({
                "external_accounts": "La liste des comptes hors institution est illisible.",
            })
        if len(rows) > 20:
            raise serializers.ValidationError({
                "external_accounts": "Vingt comptes hors institution au maximum.",
            })
        from apps.common.upload_validation import validate_uploaded_file

        kept = []
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                raise serializers.ValidationError({
                    "external_accounts": "Chaque compte doit être un ensemble de champs.",
                })
            institution = str(row.get("institution_name") or "").strip()
            account_number = str(row.get("account_number") or "").strip()
            opened_raw = str(row.get("opened_on") or "").strip()
            count_raw = str(row.get("credit_movement_count") or "").strip()
            volume_raw = str(row.get("credit_movement_volume") or "").strip()
            upload = request.FILES.get(f"external_statement__{index}")
            existing = None
            row_id = str(row.get("id") or "").strip()
            if row_id:
                existing = application.external_accounts.filter(pk=row_id).first()
            if not any((
                institution, account_number, opened_raw, count_raw, volume_raw, upload,
                existing and existing.statement,
            )):
                continue
            opened_on = None
            if opened_raw:
                try:
                    opened_on = date.fromisoformat(opened_raw)
                except ValueError as exc:
                    raise serializers.ValidationError({
                        "external_accounts": "La date d'ouverture d'un compte est invalide.",
                    }) from exc
            count = None
            if count_raw:
                try:
                    count = int(count_raw)
                except ValueError as exc:
                    raise serializers.ValidationError({
                        "external_accounts": "Le nombre de mouvements créditeurs doit être un entier.",
                    }) from exc
                if count < 0:
                    raise serializers.ValidationError({
                        "external_accounts": "Le nombre de mouvements créditeurs ne peut pas être négatif.",
                    })
            volume = None
            if volume_raw:
                try:
                    volume = Decimal(volume_raw)
                except InvalidOperation as exc:
                    raise serializers.ValidationError({
                        "external_accounts": "Le volume des mouvements créditeurs est invalide.",
                    }) from exc
            account = existing or ExternalBankAccount(
                application=application, tenant_id=application.tenant_id,
            )
            account.institution_name = institution[:200]
            account.opened_on = opened_on
            account.account_number = account_number[:50]
            account.credit_movement_count = count
            account.credit_movement_volume = volume
            if upload:
                account.statement = validate_uploaded_file(
                    upload, tenant=application.tenant, check_quota=True,
                )
            elif row.get("remove_statement"):
                account.statement = None
            account.save()
            kept.append(account.pk)
        application.external_accounts.exclude(pk__in=kept).delete()

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

    def _save_spouse(self, application, spouse):
        if application.client.client_type != "INDIVIDUAL":
            return
        updates = []
        for key in SPOUSE_WRITE_FIELDS:
            if key not in spouse:
                continue
            setattr(application.client, key, spouse[key] or "")
            updates.append(key)
        if updates:
            application.client.save(update_fields=updates)

    @transaction.atomic
    def create(self, validated_data):
        spouse = {key: validated_data.pop(key) for key in SPOUSE_WRITE_FIELDS if key in validated_data}
        application = super().create(validated_data)
        self._save_spouse(application, spouse)
        self._save_stock_photos(application)
        self._save_external_accounts(application)
        self._save_extra_fees(application)
        return application

    @transaction.atomic
    def update(self, instance, validated_data):
        spouse = {key: validated_data.pop(key) for key in SPOUSE_WRITE_FIELDS if key in validated_data}
        application = super().update(instance, validated_data)
        self._save_spouse(application, spouse)
        self._save_stock_photos(application)
        self._save_external_accounts(application)
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
        max_digits=6, decimal_places=3, min_value=Decimal("0"), required=False, allow_null=True
    )
    months = serializers.IntegerField(min_value=1, max_value=600)
    periodicity = serializers.CharField(required=False, default="MONTHLY")
    first_due_date = serializers.DateField(required=False, allow_null=True)
    simulation_date = serializers.DateField(required=False, allow_null=True)
    savings_rate = serializers.DecimalField(
        max_digits=6, decimal_places=3, min_value=Decimal("0"),
        required=False, allow_null=True,
    )
    mechanism = serializers.CharField(required=False, default="DEGRESSIVE")
    product = serializers.UUIDField(required=False, allow_null=True)
    agency = serializers.UUIDField(required=False, allow_null=True)
    client_type = serializers.ChoiceField(choices=["", "INDIVIDUAL", "CORPORATE", "PROFESSIONAL"], required=False, default="")
    individual_profile = serializers.ChoiceField(choices=["", "SALARIE", "INDEPENDANT", "MIXTE"], required=False, default="")
    fees_rate = serializers.DecimalField(max_digits=6, decimal_places=3, min_value=Decimal("0"), max_value=Decimal("100"), required=False, allow_null=True)
    extra_fees = serializers.JSONField(required=False)
    currency = serializers.RegexField(r"^[A-Z]{3}$", required=False)

    def validate(self, attrs):
        from apps.catalog.cbs_resolve import active_codes
        from apps.catalog.models import LoanPeriodicity, RepaymentMethod
        from apps.common.tenancy import get_current_tenant_id

        tenant_id = get_current_tenant_id()
        if not tenant_id:
            raise serializers.ValidationError("Sélectionnez une filiale.")
        if attrs.get("savings_rate") is not None and attrs["savings_rate"] > 100:
            raise serializers.ValidationError({"savings_rate": "Le taux d'épargne doit être au plus égal à 100 %."})
        from django.utils import timezone
        attrs["simulation_date"] = attrs.get("simulation_date") or timezone.localdate()
        if attrs.get("first_due_date") and attrs["first_due_date"] <= attrs["simulation_date"]:
            raise serializers.ValidationError({"first_due_date": "La première échéance doit suivre la date de simulation."})
        if "extra_fees" in attrs:
            try:
                attrs["extra_fees"] = parse_extra_fees(attrs["extra_fees"])
            except ValueError as exc:
                raise serializers.ValidationError({"extra_fees": str(exc)}) from exc
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
