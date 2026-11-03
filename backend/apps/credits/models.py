"""Dossiers de crédit et cycle de vie associé."""
import math
from dateutil.relativedelta import relativedelta
from datetime import timedelta
from decimal import Decimal

from django.contrib.contenttypes.fields import GenericRelation
from django.db import models
from django.utils import timezone

from apps.common.files import safe_filename
from apps.common.models import AuthoredModel, TenantScopedModel
from apps.common.tenancy import get_current_tenant_id


def credit_file_path(instance, filename):
    """Chemin de stockage des pièces jointes d'un dossier (lettre, photos)."""
    app_id = getattr(instance, "application_id", None) or instance.id
    return f"credits/{instance.tenant_id}/{app_id}/{safe_filename(filename)}"


class Periodicity(models.TextChoices):
    DAILY = "DAILY", "Journalier"
    WEEKLY = "WEEKLY", "Hebdomadaire"
    BIMONTHLY = "BIMONTHLY", "Bimensuelle"
    MONTHLY = "MONTHLY", "Mensuelle"
    QUARTERLY = "QUARTERLY", "Trimestrielle"
    SEMIANNUAL = "SEMIANNUAL", "Semestrielle"
    ANNUAL = "ANNUAL", "Annuelle"


class RepaymentMechanism(models.TextChoices):
    DEGRESSIVE = "DEGRESSIVE", "Amortissement dégressif"
    IN_FINE = "IN_FINE", "In fine (capital à terme)"
    BULLET = "BULLET", "Remboursement unique (bullet)"
    # Conservé pour les dossiers historiques (plus proposé à la saisie).
    CONSTANT = "CONSTANT", "Échéances constantes (historique)"


class TaxRegime(models.TextChoices):
    SYNTHETIC = "SYNTHETIC", "Impôt synthétique"
    REAL = "REAL", "Régime réel"
    SPECIFIC_EXEMPTION = "SPECIFIC_EXEMPTION", "Exonérations spécifiques"
    INFORMAL = "INFORMAL", "Secteur informel"


class CatchmentArea(models.TextChoices):
    LOCAL = "LOCAL", "Local"
    NATIONAL = "NATIONAL", "National"
    EXPORT = "EXPORT", "Export"


class PremisesStatus(models.TextChoices):
    OWNER = "OWNER", "Propriétaire"
    TENANT = "TENANT", "Locataire"


class PurposeType(models.TextChoices):
    WORKING_CAPITAL = "WORKING_CAPITAL", "Fonds de roulement"
    EQUIPMENT = "EQUIPMENT", "Investissement / équipement"
    STOCK = "STOCK", "Achat de stock"
    REAL_ESTATE = "REAL_ESTATE", "Immobilier"
    TREASURY = "TREASURY", "Trésorerie"
    CONSUMPTION = "CONSUMPTION", "Consommation"
    OTHER = "OTHER", "Autre"


class ContractType(models.TextChoices):
    CDI = "CDI", "CDI"
    CDD = "CDD", "CDD"
    CIVIL_SERVANT = "CIVIL_SERVANT", "Fonctionnaire"
    INDEPENDENT = "INDEPENDENT", "Indépendant"
    RETIRED = "RETIRED", "Retraité"
    OTHER = "OTHER", "Autre"


class RiskClass(models.TextChoices):
    A = "A", "A — Excellent"
    B = "B", "B — Bon"
    C = "C", "C — Moyen"
    D = "D", "D — Faible"
    E = "E", "E — Très risqué"


# ---- Analyse sectorielle & environnementale/sociale (E&S) ----
class RiskLevel(models.TextChoices):
    LOW = "LOW", "Faible"
    MEDIUM = "MEDIUM", "Moyen"
    HIGH = "HIGH", "Élevé"


class QualityLevel(models.TextChoices):
    GOOD = "GOOD", "Satisfaisante"
    IMPROVE = "IMPROVE", "À améliorer"
    BAD = "BAD", "Problématique"


class ActivitySector(models.TextChoices):
    AGRICULTURE = "AGRICULTURE", "Agriculture / élevage / pêche"
    COMMERCE = "COMMERCE", "Commerce / négoce"
    INDUSTRY = "INDUSTRY", "Industrie / transformation"
    CONSTRUCTION = "CONSTRUCTION", "BTP / construction"
    TRANSPORT = "TRANSPORT", "Transport / logistique"
    SERVICES = "SERVICES", "Services"
    CRAFTS = "CRAFTS", "Artisanat"
    ICT = "ICT", "TIC / numérique"
    TOURISM = "TOURISM", "Tourisme / hôtellerie / restauration"
    HEALTH = "HEALTH", "Santé"
    EDUCATION = "EDUCATION", "Éducation"
    ENERGY = "ENERGY", "Énergie / mines"
    OTHER = "OTHER", "Autre"


class ValueChainPosition(models.TextChoices):
    INPUTS = "INPUTS", "Intrants / approvisionnement"
    PRODUCTION = "PRODUCTION", "Production"
    PROCESSING = "PROCESSING", "Transformation"
    DISTRIBUTION = "DISTRIBUTION", "Distribution / commerce"
    SERVICES = "SERVICES", "Services"


class MarketDynamic(models.TextChoices):
    GROWTH = "GROWTH", "En croissance"
    MATURE = "MATURE", "Mature / stable"
    DECLINE = "DECLINE", "En déclin"


class ESCategory(models.TextChoices):
    A = "A", "A — Risque élevé"
    B = "B", "B — Risque moyen"
    C = "C", "C — Risque faible"


# Nombre de périodes de remboursement par an, par périodicité.
_PERIODS_PER_YEAR = {
    Periodicity.DAILY: 360,
    Periodicity.WEEKLY: 52,
    Periodicity.BIMONTHLY: 24,
    Periodicity.MONTHLY: 12,
    Periodicity.QUARTERLY: 4,
    Periodicity.SEMIANNUAL: 2,
    Periodicity.ANNUAL: 1,
}


def compute_last_due_date(first_due_date, periodicity, duration_months, tenant_id=None):
    """Calcule la date de dernière échéance selon la périodicité et la durée."""
    if not (first_due_date and periodicity and duration_months):
        return None
    per_year = _PERIODS_PER_YEAR.get(periodicity)
    if tenant_id is not None:
        from apps.catalog.cbs_resolve import resolve_periodicity_periods_per_year

        per_year = resolve_periodicity_periods_per_year(
            tenant_id, periodicity, default=per_year or 12
        )
    if not per_year:
        return None
    count = max(1, math.ceil(duration_months / 12 * per_year))
    steps = count - 1
    if periodicity == Periodicity.DAILY:
        return first_due_date + timedelta(days=steps)
    if periodicity == Periodicity.WEEKLY:
        return first_due_date + timedelta(weeks=steps)
    if periodicity == Periodicity.BIMONTHLY:
        # Deux échéances par mois ≈ 15 jours calendaires.
        return first_due_date + timedelta(days=15 * steps)
    months_map = {
        Periodicity.MONTHLY: 1,
        Periodicity.QUARTERLY: 3,
        Periodicity.SEMIANNUAL: 6,
        Periodicity.ANNUAL: 12,
    }
    months = months_map.get(periodicity)
    if months is None:
        months = max(1, round(12 / int(per_year)))
    return first_due_date + relativedelta(months=months * steps)


class CreditApplication(TenantScopedModel, AuthoredModel):
    """Demande de crédit et son suivi tout au long du cycle de vie."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Brouillon"
        SUBMITTED = "SUBMITTED", "Soumis"
        IN_APPROVAL = "IN_APPROVAL", "En cours d'approbation"
        APPROVED = "APPROVED", "Approuvé"
        REJECTED = "REJECTED", "Rejeté"
        RETURNED = "RETURNED", "Retourné pour correction"
        CONTRACT_GENERATED = "CONTRACT_GENERATED", "Contrat généré"
        DISBURSEMENT_PENDING = (
            "DISBURSEMENT_PENDING",
            "Décaissement en attente de validation",
        )
        DISBURSED = "DISBURSED", "Décaissé"
        CLOSED = "CLOSED", "Clôturé"
        CANCELLED = "CANCELLED", "Annulé"

    reference = models.CharField("référence dossier", max_length=30, blank=True, db_index=True)
    client = models.ForeignKey(
        "clients.Client",
        on_delete=models.PROTECT,
        related_name="credit_applications",
        verbose_name="client",
    )
    product = models.ForeignKey(
        "catalog.CreditProduct",
        on_delete=models.PROTECT,
        related_name="credit_applications",
        verbose_name="produit (type de crédit)",
    )
    agency = models.ForeignKey(
        "tenants.Agency",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="credit_applications",
        verbose_name="agence",
    )

    # ------------------------------------------------------------------ #
    # Conditions du crédit
    # ------------------------------------------------------------------ #
    amount_requested = models.DecimalField("montant demandé", max_digits=18, decimal_places=2)
    amount_proposed = models.DecimalField(
        "montant proposé", max_digits=18, decimal_places=2, null=True, blank=True
    )
    fees_rate = models.DecimalField(
        "frais de dossier (%)", max_digits=6, decimal_places=3, null=True, blank=True
    )
    mandatory_savings_rate = models.DecimalField(
        "taux d'épargne obligatoire (%)", max_digits=6, decimal_places=3,
        null=True, blank=True,
        help_text="% du capital prélevé en épargne à chaque échéance (0 = non applicable).",
    )
    periodicity = models.CharField(
        "périodicité",
        max_length=32,
        default=Periodicity.MONTHLY,
        help_text="Code du référentiel LoanPeriodicity (ex. MONTHLY).",
    )
    duration_months = models.PositiveIntegerField("durée (mois)")
    first_due_date = models.DateField("date de première échéance", null=True, blank=True)
    last_due_date = models.DateField(
        "date de dernière échéance", null=True, blank=True,
        help_text="Calculée automatiquement.",
    )
    repayment_mechanism = models.CharField(
        "mécanisme de remboursement",
        max_length=32,
        blank=True,
        help_text="Code du référentiel RepaymentMethod (ex. DEGRESSIVE).",
    )
    currency = models.CharField(
        "devise",
        max_length=8,
        default="XOF",
        help_text="Code du référentiel Currency (ex. XOF).",
    )
    purpose_type = models.CharField(
        "objet du financement", max_length=20, choices=PurposeType.choices, blank=True
    )
    purpose = models.TextField("détails de la demande", blank=True)
    request_letter_scan = models.FileField(
        "scan de la lettre de demande", upload_to=credit_file_path,
        max_length=255, blank=True,
    )

    # ------------------------------------------------------------------ #
    # Plan de financement
    # ------------------------------------------------------------------ #
    project_total_cost = models.DecimalField(
        "coût total du projet", max_digits=18, decimal_places=2,
        null=True, blank=True,
    )
    personal_contribution = models.DecimalField(
        "apport personnel", max_digits=18, decimal_places=2,
        null=True, blank=True,
    )
    financed_quota = models.DecimalField(
        "quotité financée (%)", max_digits=6, decimal_places=2,
        null=True, blank=True,
        help_text="Calculée automatiquement : montant de référence / coût total.",
    )

    # ------------------------------------------------------------------ #
    # Activité du client (contexte opérationnel — le diagnostic sectoriel
    # et concurrentiel est porté par l'analyse financière)
    # ------------------------------------------------------------------ #
    activity_start_date = models.DateField(
        "date de création de l'activité", null=True, blank=True
    )
    exact_address = models.CharField("adresse exacte", max_length=255, blank=True)
    clientele = models.CharField("clientèle", max_length=255, blank=True)
    tax_regime = models.CharField(
        "régime fiscal", max_length=20, choices=TaxRegime.choices, blank=True
    )
    avg_client_payment_days = models.PositiveIntegerField(
        "délai moyen de paiement clients (jours)", null=True, blank=True
    )
    avg_supplier_payment_days = models.PositiveIntegerField(
        "délai moyen de paiement fournisseurs (jours)", null=True, blank=True
    )

    # ------------------------------------------------------------------ #
    # Environnement commercial
    # ------------------------------------------------------------------ #
    catchment_area = models.CharField(
        "zone de chalandise", max_length=15, choices=CatchmentArea.choices, blank=True
    )

    # ------------------------------------------------------------------ #
    # Patrimoine et engagements financiers
    # ------------------------------------------------------------------ #
    premises_status = models.CharField(
        "statut d'occupation des locaux", max_length=15,
        choices=PremisesStatus.choices, blank=True,
    )

    # ------------------------------------------------------------------ #
    # Demandeur & emploi (surtout particulier)
    # ------------------------------------------------------------------ #
    employer_name = models.CharField("employeur", max_length=200, blank=True)
    contract_type = models.CharField(
        "type de contrat", max_length=20, choices=ContractType.choices, blank=True
    )
    salary_domiciliation = models.BooleanField(
        "domiciliation du salaire dans l'institution", default=False
    )
    dependents_count = models.PositiveIntegerField(
        "nombre de personnes à charge", null=True, blank=True
    )

    # ------------------------------------------------------------------ #
    # Relation bancaire
    # ------------------------------------------------------------------ #
    client_account_number = models.CharField(
        "numéro de compte dans l'institution", max_length=50, blank=True
    )
    relationship_start_date = models.DateField(
        "début de la relation", null=True, blank=True
    )
    avg_monthly_credit_movements = models.DecimalField(
        "mouvements créditeurs mensuels moyens", max_digits=18, decimal_places=2,
        null=True, blank=True,
    )

    # ------------------------------------------------------------------ #
    # Assurance
    # ------------------------------------------------------------------ #
    has_credit_insurance = models.BooleanField(
        "assurance décès-invalidité (ADI)", default=False
    )
    insurance_company = models.CharField(
        "compagnie d'assurance", max_length=200, blank=True
    )
    insurance_premium = models.DecimalField(
        "prime d'assurance", max_digits=18, decimal_places=2, null=True, blank=True
    )

    # ------------------------------------------------------------------ #
    # Conditions particulières
    # ------------------------------------------------------------------ #
    special_conditions = models.TextField("conditions particulières", blank=True)
    suspensive_conditions = models.TextField(
        "conditions suspensives (avant décaissement)", blank=True
    )

    # ------------------------------------------------------------------ #
    # Conformité (LBC-FT)
    # ------------------------------------------------------------------ #
    beneficial_owner = models.CharField(
        "bénéficiaire effectif", max_length=200, blank=True
    )
    is_pep = models.BooleanField("personne politiquement exposée (PPE)", default=False)
    funds_origin = models.CharField("origine des fonds / apport", max_length=255, blank=True)

    # ------------------------------------------------------------------ #
    # Complétude documentaire (checklist des pièces)
    # ------------------------------------------------------------------ #
    document_checklist = models.JSONField(
        "pièces du dossier", default=list, blank=True,
        help_text="Liste [{label, provided}] des pièces obligatoires.",
    )

    status = models.CharField(
        max_length=32, choices=Status.choices, default=Status.DRAFT, db_index=True
    )

    # Niveau de risque dérivé de l'analyse de référence à la soumission (1-5)
    risk_level = models.PositiveIntegerField(
        "niveau de risque (1-5)", null=True, blank=True,
        help_text="Dérivé de l'analyse financière de référence à la soumission.",
    )

    # Décision
    amount_approved = models.DecimalField(
        "montant approuvé", max_digits=18, decimal_places=2, null=True, blank=True
    )
    interest_rate = models.DecimalField(
        "taux d'intérêt (%)", max_digits=6, decimal_places=3, null=True, blank=True
    )
    decision_date = models.DateField("date de décision", null=True, blank=True)

    submitted_at = models.DateTimeField("soumis le", null=True, blank=True)
    submitted_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="soumis par",
    )
    disbursed_at = models.DateTimeField("décaissé le", null=True, blank=True)
    disbursement_requested_at = models.DateTimeField(
        "décaissement demandé le", null=True, blank=True
    )
    disbursement_requested_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="décaissement demandé par",
    )
    disbursement_previous_status = models.CharField(
        "statut avant demande de décaissement",
        max_length=32,
        blank=True,
        default="",
    )
    # Références CBS après décaissement réussi (crd/simple)
    cbs_demande_number = models.CharField(
        "n° demande CBS (numDemande)", max_length=100, blank=True, default=""
    )
    cbs_demande_ref = models.CharField(
        "réf. demande CBS (refDemande)", max_length=100, blank=True, default=""
    )
    cbs_contract_number = models.CharField(
        "n° contrat CBS (numContrat)", max_length=100, blank=True, default=""
    )
    cbs_operation_date = models.DateField(
        "date opération CBS (dateOperation)", null=True, blank=True
    )

    workflow_instances = GenericRelation(
        "workflow.WorkflowInstance",
        content_type_field="content_type",
        object_id_field="object_id",
    )

    class Meta:
        verbose_name = "dossier de crédit"
        verbose_name_plural = "dossiers de crédit"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["tenant", "-created_at"]),
            models.Index(fields=["tenant", "reference"]),
        ]
        permissions = [
            (
                "disburse_creditapplication",
                "Peut valider / exécuter le décaissement d'un dossier",
            ),
            (
                "initiate_disburse_creditapplication",
                "Peut initier une demande de décaissement",
            ),
        ]

    def __str__(self):
        return self.reference or f"Dossier {self.pk}"

    @property
    def current_workflow(self):
        return self.workflow_instances.order_by("-created_at").first()

    def _generate_reference(self):
        """Génère une référence unique par filiale (ex. CR-2026-00001)."""
        base = f"CR-{timezone.now().year}-"
        existing = CreditApplication.all_tenants.filter(
            tenant_id=self.tenant_id, reference__startswith=base
        ).count()
        seq = existing + 1
        ref = f"{base}{seq:05d}"
        while CreditApplication.all_tenants.filter(
            tenant_id=self.tenant_id, reference=ref
        ).exists():
            seq += 1
            ref = f"{base}{seq:05d}"
        return ref

    def save(self, *args, **kwargs):
        if self.tenant_id is None:
            current = get_current_tenant_id()
            if current is not None:
                self.tenant_id = current
        if not self.reference:
            self.reference = self._generate_reference()
        # La dernière échéance est toujours dérivée des conditions.
        self.last_due_date = compute_last_due_date(
            self.first_due_date,
            self.periodicity,
            self.duration_months,
            tenant_id=self.tenant_id,
        )
        # Quotité financée = montant de référence / coût total du projet.
        from .amounts import reference_amount

        base = reference_amount(self)
        if self.project_total_cost and self.project_total_cost > 0 and base:
            quota = Decimal(base) / Decimal(self.project_total_cost) * Decimal("100")
            self.financed_quota = min(quota, Decimal("9999.99"))
        else:
            self.financed_quota = None
        super().save(*args, **kwargs)


class CreditApplicationFee(TenantScopedModel):
    """Frais additionnels rattachés à un dossier (hors frais de dossier %)."""

    class Mode(models.TextChoices):
        PERCENT = "PERCENT", "Pourcentage"
        AMOUNT = "AMOUNT", "Montant"

    application = models.ForeignKey(
        CreditApplication,
        on_delete=models.CASCADE,
        related_name="extra_fees",
        verbose_name="dossier",
    )
    label = models.CharField("intitulé", max_length=150)
    mode = models.CharField(
        "mode", max_length=10, choices=Mode.choices, default=Mode.AMOUNT
    )
    value = models.DecimalField(
        "valeur",
        max_digits=18,
        decimal_places=3,
        help_text="Pourcentage du montant proposé, ou montant fixe.",
    )
    sort_order = models.PositiveIntegerField("ordre", default=0)

    class Meta:
        verbose_name = "frais de dossier additionnel"
        verbose_name_plural = "frais de dossier additionnels"
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.label


class StockPhoto(TenantScopedModel):
    """Photo du stock d'un client, rattachée à un dossier de crédit."""

    application = models.ForeignKey(
        CreditApplication,
        on_delete=models.CASCADE,
        related_name="stock_photos",
        verbose_name="dossier",
    )
    image = models.ImageField(
        "photo du stock", upload_to=credit_file_path, max_length=255
    )
    caption = models.CharField("légende", max_length=150, blank=True)

    class Meta:
        verbose_name = "photo de stock"
        verbose_name_plural = "photos de stock"
        ordering = ["created_at"]

    def __str__(self):
        return self.caption or f"Photo {self.pk}"


class CreditDocument(TenantScopedModel):
    """Pièce scannée rattachée à un dossier de crédit (checklist des pièces)."""

    application = models.ForeignKey(
        CreditApplication,
        on_delete=models.CASCADE,
        related_name="documents",
        verbose_name="dossier",
    )
    file = models.FileField(
        "fichier scanné", upload_to=credit_file_path, max_length=255
    )
    label = models.CharField("libellé de la pièce", max_length=150, blank=True)

    class Meta:
        verbose_name = "pièce du dossier"
        verbose_name_plural = "pièces du dossier"
        ordering = ["created_at"]

    def __str__(self):
        return self.label or f"Pièce {self.pk}"


# Seuils standards utilisés pour les drapeaux d'alerte.
MAX_DEBT_RATIO = Decimal("40")      # taux d'endettement max (particulier), en %
MIN_DSCR = Decimal("1.2")           # couverture minimale du service de la dette
MAX_LEVERAGE_RATIO = Decimal("70")  # ratio d'endettement max (entreprise), en %


def _dec(value):
    """Convertit en Decimal en tolérant None."""
    return Decimal(value) if value is not None else Decimal("0")


# Valeurs par défaut des seuils normatifs (paramétrables par filiale).
DEFAULT_THRESHOLDS = {
    "max_debt_ratio": Decimal("40"),
    "min_dscr": Decimal("1.2"),
    "max_leverage_ratio": Decimal("70"),
    "min_living_wage_per_capita": Decimal("0"),
    "min_interest_coverage": Decimal("3"),
    "max_gearing": Decimal("1.5"),
    "min_financial_autonomy": Decimal("20"),
    "min_current_ratio": Decimal("1"),
    "min_guarantee_coverage": Decimal("100"),
    "stress_pct": Decimal("20"),
    "transferable_quota_fraction": Decimal("33.33"),
    "informal_income_weight": Decimal("70"),
    # Haircuts filiale (% retranché de la valeur brute retenue).
    "haircut_mortgage": Decimal("0"),
    "haircut_vehicle": Decimal("30"),
    "haircut_jewelry": Decimal("20"),
    "haircut_financial_deposit": Decimal("0"),
    "haircut_financial_security": Decimal("10"),
    "haircut_other": Decimal("20"),
}


class AnalysisThreshold(TenantScopedModel):
    """Seuils normatifs d'analyse financière, paramétrables par filiale."""

    max_debt_ratio = models.DecimalField(
        "taux d'endettement max — particulier (%)", max_digits=6, decimal_places=2,
        default=DEFAULT_THRESHOLDS["max_debt_ratio"],
    )
    min_dscr = models.DecimalField(
        "DSCR minimum", max_digits=6, decimal_places=2,
        default=DEFAULT_THRESHOLDS["min_dscr"],
    )
    max_leverage_ratio = models.DecimalField(
        "ratio d'endettement max — entreprise (%)", max_digits=6, decimal_places=2,
        default=DEFAULT_THRESHOLDS["max_leverage_ratio"],
    )
    min_living_wage_per_capita = models.DecimalField(
        "reste à vivre minimum par personne", max_digits=18, decimal_places=2,
        default=DEFAULT_THRESHOLDS["min_living_wage_per_capita"],
    )
    min_interest_coverage = models.DecimalField(
        "couverture minimale des charges financières (x)", max_digits=6,
        decimal_places=2, default=DEFAULT_THRESHOLDS["min_interest_coverage"],
    )
    max_gearing = models.DecimalField(
        "gearing max (dettes fin. / capitaux propres)", max_digits=6,
        decimal_places=2, default=DEFAULT_THRESHOLDS["max_gearing"],
    )
    min_financial_autonomy = models.DecimalField(
        "autonomie financière minimale (%)", max_digits=6, decimal_places=2,
        default=DEFAULT_THRESHOLDS["min_financial_autonomy"],
    )
    min_current_ratio = models.DecimalField(
        "liquidité générale minimale", max_digits=6, decimal_places=2,
        default=DEFAULT_THRESHOLDS["min_current_ratio"],
    )
    min_guarantee_coverage = models.DecimalField(
        "couverture minimale par les garanties (%)", max_digits=6,
        decimal_places=2, default=DEFAULT_THRESHOLDS["min_guarantee_coverage"],
    )
    stress_pct = models.DecimalField(
        "baisse appliquée au stress test (%)", max_digits=6, decimal_places=2,
        default=DEFAULT_THRESHOLDS["stress_pct"],
    )
    transferable_quota_fraction = models.DecimalField(
        "quotité cessible du salaire (%)", max_digits=6, decimal_places=2,
        default=DEFAULT_THRESHOLDS["transferable_quota_fraction"],
    )
    informal_income_weight = models.DecimalField(
        "pondération des revenus informels (%)", max_digits=6, decimal_places=2,
        default=DEFAULT_THRESHOLDS["informal_income_weight"],
    )
    haircut_mortgage = models.DecimalField(
        "haircut hypothèque (%)", max_digits=6, decimal_places=2,
        default=DEFAULT_THRESHOLDS["haircut_mortgage"],
    )
    haircut_vehicle = models.DecimalField(
        "haircut véhicule (%)", max_digits=6, decimal_places=2,
        default=DEFAULT_THRESHOLDS["haircut_vehicle"],
    )
    haircut_jewelry = models.DecimalField(
        "haircut bijoux / objets (%)", max_digits=6, decimal_places=2,
        default=DEFAULT_THRESHOLDS["haircut_jewelry"],
    )
    haircut_financial_deposit = models.DecimalField(
        "haircut DAT / épargne (%)", max_digits=6, decimal_places=2,
        default=DEFAULT_THRESHOLDS["haircut_financial_deposit"],
    )
    haircut_financial_security = models.DecimalField(
        "haircut titres (%)", max_digits=6, decimal_places=2,
        default=DEFAULT_THRESHOLDS["haircut_financial_security"],
    )
    haircut_other = models.DecimalField(
        "haircut autres garanties (%)", max_digits=6, decimal_places=2,
        default=DEFAULT_THRESHOLDS["haircut_other"],
    )

    class Meta:
        verbose_name = "seuils d'analyse financière"
        verbose_name_plural = "seuils d'analyse financière"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant"], name="unique_analysis_threshold_per_tenant"
            )
        ]

    def __str__(self):
        return f"Seuils d'analyse — {self.tenant_id}"

    @classmethod
    def for_tenant(cls, tenant_id):
        """Renvoie les seuils de la filiale, ou des seuils par défaut non persistés."""
        obj = cls.all_tenants.filter(tenant_id=tenant_id).first()
        if obj is not None:
            return obj
        return cls(tenant_id=tenant_id, **DEFAULT_THRESHOLDS)


class CreditInstructionPolicy(TenantScopedModel):
    """Politique d'instruction crédit paramétrable par filiale.

    Les défauts reproduisent le comportement historique (souple) :
    alertes sans blocage couverture, visite optionnelle, analyse
    défavorable soumissible, etc.
    """

    class CoverageMode(models.TextChoices):
        ALERT = "ALERT", "Alerte uniquement"
        BLOCK_SUBMIT = "BLOCK_SUBMIT", "Bloquer la soumission"
        BLOCK_APPROVE = "BLOCK_APPROVE", "Bloquer l'approbation finale"

    class AmountApprovedMode(models.TextChoices):
        ALLOW = "ALLOW", "Saisissable dès l'instruction"
        FORBID = "FORBID", "Uniquement à la décision du circuit"

    class KycGate(models.TextChoices):
        ON_SUBMIT = "ON_SUBMIT", "À la soumission uniquement"
        ON_CREATE = "ON_CREATE", "Dès la création du dossier"

    class BoundsGate(models.TextChoices):
        ON_SUBMIT = "ON_SUBMIT", "À la soumission uniquement"
        ON_SAVE = "ON_SAVE", "À chaque enregistrement"

    collateral_coverage_mode = models.CharField(
        "contrôle couverture garanties",
        max_length=20,
        choices=CoverageMode.choices,
        default=CoverageMode.ALERT,
    )
    require_field_visit = models.BooleanField(
        "visite terrain obligatoire avant soumission",
        default=False,
    )
    allow_unfavorable_analysis_submit = models.BooleanField(
        "autoriser la soumission si analyse défavorable",
        default=True,
    )
    require_product_checklist = models.BooleanField(
        "exiger les pièces obligatoires du produit",
        default=False,
    )
    match_product_client_type = models.BooleanField(
        "contrôler la cohérence type client / produit",
        default=False,
    )
    kyc_gate = models.CharField(
        "exigence KYC",
        max_length=20,
        choices=KycGate.choices,
        default=KycGate.ON_SUBMIT,
    )
    product_bounds_gate = models.CharField(
        "contrôle bornes produit (montant / durée)",
        max_length=20,
        choices=BoundsGate.choices,
        default=BoundsGate.ON_SUBMIT,
    )
    amount_approved_mode = models.CharField(
        "saisie du montant approuvé",
        max_length=20,
        choices=AmountApprovedMode.choices,
        default=AmountApprovedMode.ALLOW,
    )
    show_readiness_checklist = models.BooleanField(
        "afficher la checklist de readiness avant soumission",
        default=True,
    )
    enable_cancel_status = models.BooleanField(
        "autoriser l'annulation formelle du dossier (CANCELLED)",
        default=False,
    )
    allow_collateral_during_approval = models.BooleanField(
        "autoriser le rattachement de garanties pendant le circuit",
        default=False,
    )
    require_surety_signed_contracts = models.BooleanField(
        "exiger un contrat de cautionnement signé avant décaissement",
        default=True,
        help_text=(
            "Si le dossier a des engagements de caution actifs, chaque caution "
            "doit avoir un contrat SURETY généré et signé avant décaissement."
        ),
    )
    require_formalization_before_disbursement = models.BooleanField(
        "exiger la formalisation des garanties avant décaissement",
        default=False,
        help_text=(
            "Si activé, les garanties hypothécaires / gages / nantissements "
            "rattachés au dossier doivent être formalisées (formalized_at) "
            "avant décaissement. Désactivé par défaut (processus parallèle)."
        ),
    )

    class Meta:
        verbose_name = "politique d'instruction crédit"
        verbose_name_plural = "politiques d'instruction crédit"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant"],
                name="unique_credit_instruction_policy_per_tenant",
            )
        ]

    def __str__(self):
        return f"Politique instruction — {self.tenant_id}"

    @classmethod
    def for_tenant(cls, tenant_id):
        """Politique persistée de la filiale, ou défauts non persistés."""
        if not tenant_id:
            return cls()
        obj = cls.all_tenants.filter(tenant_id=tenant_id).first()
        if obj is not None:
            return obj
        return cls(tenant_id=tenant_id)


class FinancialAnalysis(TenantScopedModel, AuthoredModel):
    """Analyse financière complète rattachée à un dossier de crédit.

    Un seul modèle couvre le particulier (revenus/charges du ménage) et
    l'entreprise (compte d'exploitation + bilan simplifié). Le type est
    déduit automatiquement du client et détermine les blocs pertinents.
    Les indicateurs clés sont recalculés à chaque enregistrement.
    """

    class ReferencePeriod(models.TextChoices):
        MONTHLY = "MONTHLY", "Mensuelle"
        QUARTERLY = "QUARTERLY", "Trimestrielle"
        ANNUAL = "ANNUAL", "Annuelle"

    class Recommendation(models.TextChoices):
        FAVORABLE = "FAVORABLE", "Favorable"
        CONDITIONAL = "CONDITIONAL", "Favorable sous conditions"
        UNFAVORABLE = "UNFAVORABLE", "Défavorable"

    class IndividualProfile(models.TextChoices):
        SALARIE = "SALARIE", "Salarié"
        INDEPENDANT = "INDEPENDANT", "Indépendant"
        MIXTE = "MIXTE", "Mixte (salarié + activité)"

    application = models.ForeignKey(
        CreditApplication,
        on_delete=models.CASCADE,
        related_name="financial_analyses",
        verbose_name="dossier",
    )
    author_role = models.CharField(
        "profil de l'auteur", max_length=150, blank=True,
        help_text="Rôle/profil de l'auteur figé au moment de l'analyse.",
    )
    is_reference = models.BooleanField(
        "analyse de référence",
        default=False,
        help_text="Une seule analyse de référence par dossier (score, risque, comité).",
    )
    client_type = models.CharField(
        "type de client", max_length=20, blank=True,
        help_text="Renseigné automatiquement d'après le client.",
    )
    individual_profile = models.CharField(
        "profil particulier",
        max_length=20,
        choices=IndividualProfile.choices,
        blank=True,
        help_text=(
            "Salarié, indépendant ou mixte — oriente les blocs de l'analyse "
            "pour les personnes physiques."
        ),
    )
    reference_period = models.CharField(
        "période de référence", max_length=15,
        choices=ReferencePeriod.choices, default=ReferencePeriod.MONTHLY,
    )
    analysis_date = models.DateField("date de l'analyse", null=True, blank=True)

    # ------------------------------------------------------------------ #
    # PARTICULIER — revenus du ménage (période de référence)
    # ------------------------------------------------------------------ #
    salary_income = models.DecimalField(
        "salaire net", max_digits=18, decimal_places=2, default=0
    )
    spouse_income = models.DecimalField(
        "revenus du conjoint", max_digits=18, decimal_places=2, default=0
    )
    rental_income = models.DecimalField(
        "revenus locatifs / rente", max_digits=18, decimal_places=2, default=0
    )
    other_activity_income = models.DecimalField(
        "revenus d'activité (hors bloc dédié)", max_digits=18, decimal_places=2, default=0
    )
    other_income = models.DecimalField(
        "autres revenus", max_digits=18, decimal_places=2, default=0
    )

    # PARTICULIER — charges du ménage
    rent_expense = models.DecimalField(
        "loyer / logement", max_digits=18, decimal_places=2, default=0
    )
    food_expense = models.DecimalField(
        "alimentation", max_digits=18, decimal_places=2, default=0
    )
    utilities_expense = models.DecimalField(
        "eau / électricité / téléphone", max_digits=18, decimal_places=2, default=0
    )
    transport_expense = models.DecimalField(
        "transport", max_digits=18, decimal_places=2, default=0
    )
    education_expense = models.DecimalField(
        "scolarité / éducation", max_digits=18, decimal_places=2, default=0
    )
    health_expense = models.DecimalField(
        "santé", max_digits=18, decimal_places=2, default=0
    )
    other_household_expenses = models.DecimalField(
        "autres charges du ménage", max_digits=18, decimal_places=2, default=0
    )

    # PARTICULIER — charges informelles complémentaires
    tontine_expense = models.DecimalField(
        "tontines / cotisations d'épargne", max_digits=18, decimal_places=2,
        default=0,
    )
    social_contributions = models.DecimalField(
        "cotisations sociales / assurances", max_digits=18, decimal_places=2,
        default=0,
    )
    family_support_expense = models.DecimalField(
        "soutien familial / transferts", max_digits=18, decimal_places=2,
        default=0,
    )

    # PARTICULIER — stabilité & quotité cessible (salarié / fonctionnaire)
    net_salary = models.DecimalField(
        "salaire net (base quotité cessible)", max_digits=18, decimal_places=2,
        default=0,
    )
    salary_deductions = models.DecimalField(
        "retenues déjà prélevées à la source", max_digits=18, decimal_places=2,
        default=0,
    )
    employment_seniority_months = models.PositiveIntegerField(
        "ancienneté dans l'emploi / l'activité (mois)", null=True, blank=True
    )
    informal_income_weight = models.DecimalField(
        "pondération appliquée aux revenus informels (%)", max_digits=6,
        decimal_places=2, null=True, blank=True,
        help_text="Laisser vide pour utiliser le seuil de la filiale.",
    )

    # ------------------------------------------------------------------ #
    # ENTREPRISE — compte d'exploitation (période de référence)
    # ------------------------------------------------------------------ #
    turnover = models.DecimalField(
        "chiffre d'affaires", max_digits=18, decimal_places=2, default=0
    )
    cogs = models.DecimalField(
        "coût d'achat des marchandises vendues", max_digits=18, decimal_places=2,
        default=0,
    )
    op_rent = models.DecimalField(
        "loyer", max_digits=18, decimal_places=2, default=0
    )
    op_salaries = models.DecimalField(
        "salaires", max_digits=18, decimal_places=2, default=0
    )
    op_utilities = models.DecimalField(
        "eau / électricité", max_digits=18, decimal_places=2, default=0
    )
    op_transport = models.DecimalField(
        "transport / carburant", max_digits=18, decimal_places=2, default=0
    )
    op_telecom = models.DecimalField(
        "téléphone / internet", max_digits=18, decimal_places=2, default=0
    )
    op_taxes = models.DecimalField(
        "impôts & patente", max_digits=18, decimal_places=2, default=0
    )
    op_maintenance = models.DecimalField(
        "entretien", max_digits=18, decimal_places=2, default=0
    )
    op_other = models.DecimalField(
        "autres charges d'exploitation", max_digits=18, decimal_places=2, default=0
    )
    depreciation = models.DecimalField(
        "amortissements", max_digits=18, decimal_places=2, default=0
    )
    financial_charges = models.DecimalField(
        "charges financières", max_digits=18, decimal_places=2, default=0
    )

    # ENTREPRISE — bilan simplifié
    stock_value = models.DecimalField(
        "stock", max_digits=18, decimal_places=2, default=0
    )
    receivables = models.DecimalField(
        "créances clients", max_digits=18, decimal_places=2, default=0
    )
    cash_available = models.DecimalField(
        "trésorerie (caisse + banque)", max_digits=18, decimal_places=2, default=0
    )
    fixed_assets = models.DecimalField(
        "immobilisations", max_digits=18, decimal_places=2, default=0
    )
    supplier_debt = models.DecimalField(
        "dettes fournisseurs", max_digits=18, decimal_places=2, default=0
    )
    ongoing_credit_balance = models.DecimalField(
        "encours crédits en cours (dettes financières)", max_digits=18,
        decimal_places=2, default=0,
    )
    short_term_debt = models.DecimalField(
        "autres dettes court terme (fiscales, sociales…)", max_digits=18,
        decimal_places=2, default=0,
    )

    # ENTREPRISE — période précédente (N-1) pour l'analyse de tendance
    turnover_prev = models.DecimalField(
        "chiffre d'affaires N-1", max_digits=18, decimal_places=2, default=0
    )
    net_result_prev = models.DecimalField(
        "résultat net N-1", max_digits=18, decimal_places=2, default=0
    )

    # ------------------------------------------------------------------ #
    # Trésorerie prévisionnelle (sur la période de référence)
    # ------------------------------------------------------------------ #
    projected_monthly_inflows = models.DecimalField(
        "encaissements prévisionnels", max_digits=18, decimal_places=2, default=0
    )
    projected_monthly_outflows = models.DecimalField(
        "décaissements prévisionnels", max_digits=18, decimal_places=2, default=0
    )
    cashflow_comment = models.TextField(
        "commentaire sur la trésorerie prévisionnelle", blank=True
    )

    # ------------------------------------------------------------------ #
    # Commun
    # ------------------------------------------------------------------ #
    existing_debt_institution = models.CharField(
        "institution du crédit en cours", max_length=200, blank=True
    )
    existing_debt_initial_amount = models.DecimalField(
        "montant initial du crédit en cours", max_digits=18, decimal_places=2,
        default=0,
    )
    existing_debt_monthly = models.DecimalField(
        "mensualités des crédits en cours (total consolidé)", max_digits=18,
        decimal_places=2, default=0,
    )

    # ------------------------------------------------------------------ #
    # Endettement consolidé & centrale des risques (contre-analyse)
    # ------------------------------------------------------------------ #
    active_loans_count = models.PositiveIntegerField(
        "nombre de crédits actifs (tous prêteurs)", default=0
    )
    credit_bureau_checked = models.BooleanField(
        "centrale des risques / BIC consultée", default=False
    )
    credit_bureau_date = models.DateField(
        "date de consultation centrale des risques", null=True, blank=True
    )
    has_payment_incidents = models.BooleanField(
        "incidents de paiement recensés", default=False
    )
    max_days_late = models.PositiveIntegerField(
        "retard maximum constaté (jours)", null=True, blank=True
    )
    incidents_comment = models.TextField(
        "détails des incidents / engagements externes", blank=True
    )

    # ------------------------------------------------------------------ #
    # Historique interne de remboursement (client déjà emprunteur)
    # ------------------------------------------------------------------ #
    prior_loans_count = models.PositiveIntegerField(
        "nombre de crédits antérieurs dans l'institution", default=0
    )
    prior_repayment_rate = models.DecimalField(
        "taux de remboursement historique (%)", max_digits=6, decimal_places=2,
        null=True, blank=True,
    )
    prior_max_delay_days = models.PositiveIntegerField(
        "retard maximum historique interne (jours)", null=True, blank=True
    )

    # Indicateurs recalculés automatiquement
    new_installment = models.DecimalField(
        "échéance institution (hors épargne)", max_digits=18, decimal_places=2,
        null=True, blank=True,
    )
    repayment_capacity = models.DecimalField(
        "capacité de remboursement", max_digits=18, decimal_places=2,
        null=True, blank=True,
    )
    debt_ratio = models.DecimalField(
        "taux d'endettement (%)", max_digits=8, decimal_places=2,
        null=True, blank=True,
    )
    dscr = models.DecimalField(
        "couverture du service de la dette (DSCR)", max_digits=8, decimal_places=2,
        null=True, blank=True,
    )
    # Sensibilité (stress test) recalculée automatiquement
    debt_ratio_stress = models.DecimalField(
        "taux d'endettement sous stress (%)", max_digits=8, decimal_places=2,
        null=True, blank=True,
    )
    dscr_stress = models.DecimalField(
        "DSCR sous stress", max_digits=8, decimal_places=2, null=True, blank=True
    )
    guarantee_coverage = models.DecimalField(
        "couverture par les garanties (%)", max_digits=8, decimal_places=2,
        null=True, blank=True,
    )

    # ------------------------------------------------------------------ #
    # Analyse sectorielle
    # ------------------------------------------------------------------ #
    sector = models.CharField(
        "secteur d'activité", max_length=20, choices=ActivitySector.choices,
        blank=True,
    )
    sub_sector = models.CharField(
        "sous-secteur / filière", max_length=200, blank=True
    )
    value_chain_position = models.CharField(
        "position dans la chaîne de valeur", max_length=20,
        choices=ValueChainPosition.choices, blank=True,
    )
    market_dynamic = models.CharField(
        "dynamique du marché", max_length=10, choices=MarketDynamic.choices,
        blank=True,
    )
    seasonality_level = models.CharField(
        "intensité de la saisonnalité", max_length=10,
        choices=RiskLevel.choices, blank=True,
    )
    competition_intensity = models.CharField(
        "intensité concurrentielle", max_length=10, choices=RiskLevel.choices,
        blank=True,
    )
    supplier_dependency = models.CharField(
        "dépendance aux fournisseurs", max_length=10, choices=RiskLevel.choices,
        blank=True,
    )
    client_concentration = models.CharField(
        "concentration de la clientèle", max_length=10,
        choices=RiskLevel.choices, blank=True,
    )
    input_price_sensitivity = models.CharField(
        "sensibilité au prix des intrants", max_length=10,
        choices=RiskLevel.choices, blank=True,
    )
    fx_exposure = models.CharField(
        "exposition aux devises / importations", max_length=10,
        choices=RiskLevel.choices, blank=True,
    )
    regulatory_sensitivity = models.CharField(
        "sensibilité réglementaire / fiscale", max_length=10,
        choices=RiskLevel.choices, blank=True,
    )
    climate_sensitivity = models.CharField(
        "sensibilité climatique", max_length=10, choices=RiskLevel.choices,
        blank=True,
    )
    sector_risk_level = models.CharField(
        "niveau de risque sectoriel", max_length=10, choices=RiskLevel.choices,
        blank=True,
    )
    sector_outlook = models.TextField("perspectives du secteur", blank=True)
    sector_comment = models.TextField("commentaire sectoriel", blank=True)

    # ------------------------------------------------------------------ #
    # Analyse environnementale & sociale (E&S)
    # ------------------------------------------------------------------ #
    es_category = models.CharField(
        "catégorie de risque E&S", max_length=1, choices=ESCategory.choices,
        blank=True,
    )
    exclusion_list_ok = models.BooleanField(
        "activité hors liste d'exclusion", default=True
    )
    env_permit_required = models.BooleanField(
        "autorisation environnementale requise", default=False
    )
    env_permit_obtained = models.BooleanField(
        "autorisation environnementale obtenue", default=False
    )
    permit_reference = models.CharField(
        "référence de l'autorisation", max_length=150, blank=True
    )
    eia_required = models.BooleanField(
        "étude d'impact environnemental requise", default=False
    )
    eia_done = models.BooleanField(
        "étude d'impact environnemental réalisée", default=False
    )
    es_regulatory_compliance = models.BooleanField(
        "conformité réglementaire E&S", default=True
    )
    # Impacts environnementaux
    waste_management = models.CharField(
        "gestion des déchets / effluents", max_length=10,
        choices=QualityLevel.choices, blank=True,
    )
    resource_use = models.CharField(
        "usage de l'eau / énergie", max_length=10, choices=QualityLevel.choices,
        blank=True,
    )
    chemicals_pesticides = models.CharField(
        "usage produits chimiques / pesticides", max_length=10,
        choices=QualityLevel.choices, blank=True,
    )
    nuisances_emissions = models.CharField(
        "nuisances / émissions / pollution", max_length=10,
        choices=QualityLevel.choices, blank=True,
    )
    # Impacts sociaux
    working_conditions = models.CharField(
        "conditions de travail", max_length=10, choices=QualityLevel.choices,
        blank=True,
    )
    occupational_safety = models.CharField(
        "sécurité & santé au travail", max_length=10,
        choices=QualityLevel.choices, blank=True,
    )
    child_forced_labor_risk = models.CharField(
        "risque travail des enfants / forcé", max_length=10,
        choices=RiskLevel.choices, blank=True,
    )
    community_impact = models.CharField(
        "impact sur les communautés riveraines", max_length=10,
        choices=QualityLevel.choices, blank=True,
    )
    land_resettlement_risk = models.CharField(
        "enjeux fonciers / réinstallation", max_length=10,
        choices=RiskLevel.choices, blank=True,
    )
    jobs_created = models.PositiveIntegerField(
        "emplois créés", null=True, blank=True
    )
    jobs_maintained = models.PositiveIntegerField(
        "emplois maintenus", null=True, blank=True
    )
    jobs_women = models.PositiveIntegerField(
        "dont emplois féminins", null=True, blank=True
    )
    jobs_youth = models.PositiveIntegerField(
        "dont emplois jeunes", null=True, blank=True
    )
    workforce_count = models.PositiveIntegerField(
        "effectif actuel (nombre d'employés)", null=True, blank=True
    )
    es_mitigation_plan = models.TextField(
        "plan d'action / mesures d'atténuation (PGES)", blank=True
    )
    es_action_required = models.BooleanField(
        "plan d'action E&S exigé", default=False
    )
    es_insurance = models.BooleanField(
        "assurances E&S (pollution / RC)", default=False
    )
    es_risk_level = models.CharField(
        "niveau de risque E&S global", max_length=10, choices=RiskLevel.choices,
        blank=True,
    )
    es_comment = models.TextField("commentaire E&S", blank=True)

    # ------------------------------------------------------------------ #
    # Personne physique — activité génératrice de revenus
    # ------------------------------------------------------------------ #
    has_side_activity = models.BooleanField(
        "exerce une activité génératrice de revenus", default=False
    )
    activity_turnover = models.DecimalField(
        "CA / recettes activité", max_digits=18, decimal_places=2,
        default=0,
    )
    activity_expenses = models.DecimalField(
        "charges activité", max_digits=18, decimal_places=2, default=0,
    )
    activity_comment = models.TextField("commentaire activité", blank=True)

    # ------------------------------------------------------------------ #
    # Groupement (PROFESSIONAL)
    # ------------------------------------------------------------------ #
    members_count = models.PositiveIntegerField(
        "nombre de membres", null=True, blank=True
    )
    active_contributing_members = models.PositiveIntegerField(
        "membres cotisants actifs", null=True, blank=True
    )
    solidarity_commitment = models.BooleanField(
        "engagement de solidarité entre membres", default=False
    )
    collective_contributions = models.DecimalField(
        "cotisations périodiques collectées", max_digits=18, decimal_places=2,
        default=0,
    )
    collective_savings = models.DecimalField(
        "épargne du groupement", max_digits=18, decimal_places=2, default=0,
    )
    collective_other_income = models.DecimalField(
        "autres recettes collectives", max_digits=18, decimal_places=2, default=0,
    )
    collective_operating_expenses = models.DecimalField(
        "charges de fonctionnement collectives", max_digits=18, decimal_places=2,
        default=0,
    )
    group_activity_turnover = models.DecimalField(
        "CA activité commune (si applicable)", max_digits=18, decimal_places=2,
        default=0,
    )
    group_activity_expenses = models.DecimalField(
        "charges activité commune", max_digits=18, decimal_places=2, default=0,
    )
    group_comment = models.TextField("commentaire groupement", blank=True)

    # Décision & synthèse structurée
    internal_score = models.DecimalField(
        "score interne (/100)", max_digits=6, decimal_places=2, null=True, blank=True
    )
    score_breakdown = models.JSONField(
        "détail du score", default=dict, blank=True
    )
    strengths = models.TextField("points forts", blank=True)
    weaknesses = models.TextField("points de vigilance", blank=True)
    recommended_conditions = models.TextField(
        "conditions / recommandations proposées", blank=True
    )
    recommendation = models.CharField(
        "recommandation", max_length=15, choices=Recommendation.choices, blank=True
    )
    comment = models.TextField("avis / commentaire de l'analyste", blank=True)

    class Meta:
        verbose_name = "analyse financière"
        verbose_name_plural = "analyses financières"
        ordering = ["created_at"]

    def __str__(self):
        return f"Analyse {self.application}"

    # -------------------- valeurs dérivées (particulier) --------------- #
    @property
    def total_income(self):
        base = (
            _dec(self.salary_income) + _dec(self.spouse_income)
            + _dec(self.rental_income) + _dec(self.other_activity_income)
            + _dec(self.other_income)
        )
        if self.has_side_activity:
            base += _dec(self.activity_turnover) - _dec(self.activity_expenses)
        return base

    @property
    def activity_net(self):
        return _dec(self.activity_turnover) - _dec(self.activity_expenses)

    @property
    def collective_capacity(self):
        """Capacité nette d'un groupement (hors service dette existant)."""
        return (
            _dec(self.collective_contributions)
            + _dec(self.collective_other_income)
            + _dec(self.group_activity_turnover)
            - _dec(self.collective_operating_expenses)
            - _dec(self.group_activity_expenses)
        )

    @property
    def total_household_charges(self):
        return (
            _dec(self.rent_expense) + _dec(self.food_expense)
            + _dec(self.utilities_expense) + _dec(self.transport_expense)
            + _dec(self.education_expense) + _dec(self.health_expense)
            + _dec(self.other_household_expenses)
            + _dec(self.tontine_expense) + _dec(self.social_contributions)
            + _dec(self.family_support_expense)
        )

    @property
    def disposable_income(self):
        return (
            self.total_income - self.total_household_charges
            - _dec(self.existing_debt_monthly)
        )

    @property
    def dependents_count(self):
        app = self.application
        return getattr(app, "dependents_count", None) if app else None

    @property
    def disposable_per_capita(self):
        """Reste à vivre par personne du ménage (demandeur + personnes à charge)."""
        count = self.dependents_count
        if count is None:
            return None
        return self.disposable_income / (Decimal(count) + Decimal("1"))

    @property
    def projected_monthly_surplus(self):
        return (
            _dec(self.projected_monthly_inflows)
            - _dec(self.projected_monthly_outflows)
        )

    # -------------------- valeurs dérivées (entreprise) ---------------- #
    @property
    def gross_margin(self):
        return _dec(self.turnover) - _dec(self.cogs)

    @property
    def total_operating_expenses(self):
        return (
            _dec(self.op_rent) + _dec(self.op_salaries) + _dec(self.op_utilities)
            + _dec(self.op_transport) + _dec(self.op_telecom) + _dec(self.op_taxes)
            + _dec(self.op_maintenance) + _dec(self.op_other)
        )

    @property
    def ebe(self):
        return self.gross_margin - self.total_operating_expenses

    @property
    def net_result(self):
        return self.ebe - _dec(self.depreciation) - _dec(self.financial_charges)

    @property
    def cash_flow(self):
        return self.net_result + _dec(self.depreciation)

    @property
    def total_assets(self):
        return (
            _dec(self.stock_value) + _dec(self.receivables)
            + _dec(self.cash_available) + _dec(self.fixed_assets)
        )

    @property
    def total_debts(self):
        return (
            _dec(self.supplier_debt)
            + _dec(self.ongoing_credit_balance)
            + _dec(self.short_term_debt)
        )

    @property
    def equity(self):
        return self.total_assets - self.total_debts

    @property
    def bfr(self):
        return _dec(self.stock_value) + _dec(self.receivables) - _dec(self.supplier_debt)

    @property
    def gross_margin_pct(self):
        t = _dec(self.turnover)
        return (self.gross_margin / t * Decimal("100")) if t else None

    @property
    def net_margin_pct(self):
        t = _dec(self.turnover)
        return (self.net_result / t * Decimal("100")) if t else None

    @property
    def is_corporate(self):
        return self.client_type == "CORPORATE"

    @property
    def is_groupement(self):
        return self.client_type == "PROFESSIONAL"

    @property
    def is_individual(self):
        return self.client_type == "INDIVIDUAL" or (
            self.client_type not in ("CORPORATE", "PROFESSIONAL")
        )

    def _compute_new_installment(self):
        """Échéance institution (principal + intérêt), hors épargne obligatoire."""
        from apps.credits.amounts import reference_amount
        from apps.credits.services import compute_amortization_schedule

        app = self.application
        amount = reference_amount(app)
        rate = app.interest_rate
        if rate is None and app.product_id:
            rate = getattr(app.product, "interest_rate", None)
        months = app.duration_months
        if not (amount and months):
            return None
        try:
            schedule = compute_amortization_schedule(
                amount,
                rate or 0,
                months,
                periodicity=app.periodicity or "MONTHLY",
                first_due_date=app.first_due_date,
                savings_rate=0,
                mechanism=app.repayment_mechanism or "DEGRESSIVE",
                tenant_id=app.tenant_id,
            )
        except Exception:
            return None
        if not schedule:
            return None
        # Hors épargne : ce qui revient à l'institution.
        return schedule[0].get("institution_due", schedule[0]["principal"] + schedule[0]["interest"])

    @staticmethod
    def _clamp(value, max_digits, decimal_places):
        """Borne une valeur pour respecter les contraintes du champ."""
        if value is None:
            return None
        limit = Decimal(10) ** (max_digits - decimal_places) - Decimal(1)
        value = Decimal(value)
        if value > limit:
            return limit
        if value < -limit:
            return -limit
        return value

    def save(self, *args, **kwargs):
        # Affecte tôt le tenant pour récupérer les bons seuils.
        if self.tenant_id is None:
            from apps.common.tenancy import get_current_tenant_id

            current = get_current_tenant_id()
            if current is not None:
                self.tenant_id = current

        # Type de client : toujours celui de la fiche client du dossier.
        if self.application_id:
            live_type = getattr(self.application.client, "client_type", "") or ""
            if live_type:
                self.client_type = live_type

        # Profil particulier : heuristique si non renseigné.
        if self.is_individual and not self.individual_profile:
            has_salary = _dec(self.salary_income) > 0 or _dec(self.net_salary) > 0
            has_activity = self.has_side_activity or _dec(self.activity_turnover) > 0
            if has_salary and has_activity:
                self.individual_profile = self.IndividualProfile.MIXTE
            elif has_activity:
                self.individual_profile = self.IndividualProfile.INDEPENDANT
            elif has_salary:
                self.individual_profile = self.IndividualProfile.SALARIE

        # Aligner has_side_activity sur le profil (indépendant / mixte).
        if self.individual_profile in (
            self.IndividualProfile.INDEPENDANT,
            self.IndividualProfile.MIXTE,
        ):
            self.has_side_activity = True

        # Période de référence : défaut selon le type de client.
        if not self.reference_period:
            if self.client_type == "CORPORATE":
                self.reference_period = self.ReferencePeriod.ANNUAL
            else:
                self.reference_period = self.ReferencePeriod.MONTHLY

        # Un seul salaire net saisi : synchronise la base quotité.
        if _dec(self.salary_income) and not _dec(self.net_salary):
            self.net_salary = self.salary_income
        elif _dec(self.salary_income):
            self.net_salary = self.salary_income

        self.new_installment = self._compute_new_installment()
        installment = _dec(self.new_installment)
        existing = _dec(self.existing_debt_monthly)

        if self.is_corporate:
            cash_flow = self.cash_flow
            self.repayment_capacity = cash_flow - existing
            self.dscr = (cash_flow / installment) if installment else None
            assets = self.total_assets
            self.debt_ratio = (
                (self.total_debts / assets * Decimal("100")) if assets else None
            )
        elif self.is_groupement:
            self.repayment_capacity = self.collective_capacity - existing
            income = (
                _dec(self.collective_contributions)
                + _dec(self.collective_other_income)
                + _dec(self.group_activity_turnover)
            )
            self.debt_ratio = (
                ((existing + installment) / income * Decimal("100"))
                if income else None
            )
            self.dscr = None
        else:
            self.repayment_capacity = self.disposable_income
            income = self.total_income
            self.debt_ratio = (
                ((existing + installment) / income * Decimal("100"))
                if income else None
            )
            self.dscr = None

        # Bornage pour respecter les contraintes de colonnes.
        self.debt_ratio = self._clamp(self.debt_ratio, 8, 2)
        self.dscr = self._clamp(self.dscr, 8, 2)
        self.repayment_capacity = self._clamp(self.repayment_capacity, 18, 2)
        self.new_installment = self._clamp(self.new_installment, 18, 2)

        # Contre-analyse : stress test, couverture garanties et scoring pondéré.
        try:
            from .analytics import compute_metrics, compute_score

            th = AnalysisThreshold.for_tenant(self.tenant_id)
            metrics = compute_metrics(self, th)
            if self.is_corporate:
                self.dscr_stress = self._clamp(metrics.get("dscr_stress"), 8, 2)
                self.debt_ratio_stress = None
            else:
                self.debt_ratio_stress = self._clamp(
                    metrics.get("debt_ratio_stress"), 8, 2
                )
                self.dscr_stress = None
            self.guarantee_coverage = self._clamp(
                metrics.get("guarantee_coverage"), 8, 2
            )
            score, breakdown = compute_score(self, metrics, th)
            self.internal_score = self._clamp(score, 6, 2)
            self.score_breakdown = breakdown
        except Exception:
            # La contre-analyse ne doit jamais bloquer l'enregistrement.
            pass

        super().save(*args, **kwargs)

        # Une seule analyse de référence par dossier.
        if self.is_reference and self.application_id:
            type(self).objects.filter(application_id=self.application_id).exclude(
                pk=self.pk
            ).update(is_reference=False)
        elif self.application_id and not type(self).objects.filter(
            application_id=self.application_id, is_reference=True
        ).exists():
            type(self).objects.filter(pk=self.pk).update(is_reference=True)
            self.is_reference = True


class FinancialDocument(TenantScopedModel):
    """Pièce justificative rattachée à une analyse financière."""

    analysis = models.ForeignKey(
        FinancialAnalysis,
        on_delete=models.CASCADE,
        related_name="documents",
        verbose_name="analyse",
    )
    file = models.FileField(
        "fichier", upload_to=credit_file_path, max_length=255
    )
    label = models.CharField("libellé", max_length=150, blank=True)

    class Meta:
        verbose_name = "pièce justificative (analyse)"
        verbose_name_plural = "pièces justificatives (analyse)"
        ordering = ["created_at"]

    def __str__(self):
        return self.label or f"Document {self.pk}"


class FieldVisit(TenantScopedModel):
    """Compte rendu de visite terrain."""

    application = models.ForeignKey(
        CreditApplication,
        on_delete=models.CASCADE,
        related_name="field_visits",
        verbose_name="dossier",
    )
    visit_date = models.DateField("date de visite")
    visited_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="field_visits",
    )
    visitor_role = models.CharField(
        "profil de l'auteur", max_length=150, blank=True,
        help_text="Rôle/profil de l'auteur figé au moment de la visite.",
    )
    geo_coordinates = models.CharField(
        "coordonnées géographiques",
        max_length=120,
        blank=True,
        help_text="Ex. 5.359952, -4.008256 (collé depuis Maps).",
    )
    report = models.TextField("compte rendu", blank=True)

    class Meta:
        verbose_name = "visite terrain"
        verbose_name_plural = "visites terrain"
        ordering = ["-visit_date"]

    def __str__(self):
        return f"Visite {self.application} — {self.visit_date}"


class Loan(TenantScopedModel):
    """Prêt mis en place après décaissement d'un dossier approuvé."""

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "En cours"
        CLOSED = "CLOSED", "Soldé"
        DEFAULTED = "DEFAULTED", "Passé en perte / défaut"

    application = models.OneToOneField(
        CreditApplication,
        on_delete=models.PROTECT,
        related_name="loan",
        verbose_name="dossier",
    )
    principal = models.DecimalField("capital", max_digits=18, decimal_places=2)
    interest_rate = models.DecimalField("taux (%)", max_digits=6, decimal_places=3)
    mandatory_savings_rate = models.DecimalField(
        "taux d'épargne obligatoire (%)", max_digits=6, decimal_places=3, default=0
    )
    duration_months = models.PositiveIntegerField("durée (mois)")
    disbursed_at = models.DateField("date de décaissement")
    first_due_date = models.DateField("première échéance")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)

    # Référence dans le Core Banking de la filiale
    core_banking_reference = models.CharField(max_length=100, blank=True)
    cbs_external_id = models.CharField(
        "identifiant externe CBS (externalId)", max_length=100, blank=True
    )
    cbs_demande_number = models.CharField(
        "n° demande CBS (numDemande)", max_length=100, blank=True
    )
    cbs_demande_ref = models.CharField(
        "réf. demande CBS (refDemande)", max_length=100, blank=True
    )
    cbs_contract_number = models.CharField(
        "n° contrat CBS (numContrat)", max_length=100, blank=True
    )
    cbs_disbursement_status = models.CharField(
        "statut décaissement CBS",
        max_length=40,
        blank=True,
        default="",
        help_text="SUBMITTED / CONFIRMED / FAILED / … (callbacks Perfect).",
    )
    cbs_disbursement_payload = models.JSONField(
        "dernier payload CBS décaissement", default=dict, blank=True
    )

    class Meta:
        verbose_name = "prêt"
        verbose_name_plural = "prêts"

    def __str__(self):
        return f"Prêt {self.application}"


class Installment(TenantScopedModel):
    """Échéance d'un prêt (échéancier d'amortissement)."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "À échoir"
        PAID = "PAID", "Payée"
        PARTIAL = "PARTIAL", "Partielle"
        OVERDUE = "OVERDUE", "En retard"

    loan = models.ForeignKey(
        Loan,
        on_delete=models.CASCADE,
        related_name="installments",
        verbose_name="prêt",
    )
    number = models.PositiveIntegerField("n° d'échéance")
    due_date = models.DateField("date d'échéance", db_index=True)
    principal_due = models.DecimalField(max_digits=18, decimal_places=2)
    interest_due = models.DecimalField(max_digits=18, decimal_places=2)
    savings_due = models.DecimalField(
        "épargne obligatoire", max_digits=18, decimal_places=2, default=0
    )
    total_due = models.DecimalField(max_digits=18, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True
    )

    class Meta:
        verbose_name = "échéance"
        verbose_name_plural = "échéances"
        ordering = ["loan", "number"]
        constraints = [
            models.UniqueConstraint(
                fields=["loan", "number"], name="unique_installment_number_per_loan"
            )
        ]

    def __str__(self):
        return f"Échéance {self.number} — {self.loan}"

    @property
    def balance(self):
        return self.total_due - self.amount_paid
