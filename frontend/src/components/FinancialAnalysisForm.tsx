import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Briefcase,
  Building2,
  Calculator,
  ExternalLink,
  Factory,
  FileText,
  Gauge,
  Images,
  Landmark,
  Leaf,
  ReceiptText,
  Shield,
  Store,
  UploadCloud,
  Users,
  Wallet,
  type LucideIcon,
} from "lucide-react";
import {
  createContext,
  useContext,
  Children,
  Fragment,
  isValidElement,
  useEffect,
  useMemo,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import { Link } from "react-router-dom";

import { api } from "@/api/client";
import { DETAIL_TABLE_LABELS, type EffectiveConfiguration } from "@/api/configuration";
import {
  FINANCE_LABELS,
  type CreditApplication,
  type FinancialAnalysis,
  type AnalysisDetails,
} from "@/api/types";
import { FinancialAnalysisDetails } from "@/components/FinancialAnalysisDetails";
import { PRODUCTION_IDENTITY, retainedActivityMargin } from "@/components/productLine";
import { ProductSheetTable } from "@/components/ProductSheetTable";
import { ActivityStatementReading, FinancialStatementsEditor } from "@/components/FinancialStatementsSection";
import {
  groupActivityOpen,
  pathLabel,
  purposeTestText,
  resolveAnalysisPath,
  resolveStatementBasis,
  sectionAllowed,
  type AnalysisPath,
} from "@/components/analysisPath";
import {
  readStatements,
  referenceFieldOverrides,
  statementError,
  type FinancialStatement,
  type StatementPiece,
} from "@/components/financialStatements";
import {
  blankExternalCredit,
  deriveExternalDebt,
  initialExternalCredits,
  type ExternalCredit,
  type DerivedExternalDebt,
} from "@/components/externalCredits";
import { TpeReconstitution } from "@/components/TpeReconstitution";
import { FinancialAnalysisSupplements } from "@/components/FinancialAnalysisSupplements";
import { formatDate, formatMoney } from "@/components/ui";
import { CollateralSummaryCard } from "@/components/CollateralSummaryCard";
import { CustomFields } from "@/components/CustomFields";

const AnalysisLayoutContext = createContext<{ id: string; visible: boolean }[]>([]);
const AnalysisPathContext = createContext<AnalysisPath>("RECONSTITUTED");

const toOptions = (m: Record<string, string>) =>
  Object.entries(m).map(([value, label]) => ({ value, label }));

const NUMERIC_KEYS = [
  // Particulier — revenus
  "salary_income", "spouse_income", "rental_income",
  "other_activity_income", "other_income",
  // Particulier — charges
  "rent_expense", "food_expense", "utilities_expense", "transport_expense",
  "education_expense", "health_expense", "other_household_expenses",
  "tontine_expense", "social_contributions", "family_support_expense",
  // Particulier — stabilité & quotité
  "salary_deductions", "employment_seniority_months",
  "informal_income_weight", "variable_income", "pension_income",
  "other_monthly_obligations", "personal_savings",
  "personal_real_estate_value", "personal_vehicle_value",
  "personal_productive_assets",
  // Cadre de l'analyse
  "bank_statement_months",
  // Entreprise — exploitation
  "turnover", "cogs", "op_rent", "op_salaries", "op_utilities",
  "op_transport", "op_telecom", "op_taxes", "op_maintenance", "op_other",
  "depreciation", "financial_charges", "other_operating_income",
  // Entreprise — bilan
  "stock_value", "receivables", "cash_available", "fixed_assets",
  "supplier_debt", "ongoing_credit_balance", "short_term_debt",
  "cash_in_hand", "bank_balance", "other_current_assets",
  "land_building_value", "equipment_value", "vehicle_value",
  "other_fixed_assets", "tax_social_debt", "other_current_debt",
  "long_term_debt", "shareholder_debt",
  // Entreprise — N-1
  "turnover_prev", "net_result_prev",
  // Trésorerie prévisionnelle
  "projected_monthly_inflows", "projected_monthly_outflows",
  // Commun — endettement existant & consolidé
  "existing_debt_initial_amount", "existing_debt_monthly",
  "active_loans_count", "max_days_late",
  // Historique interne
  "prior_loans_count", "prior_repayment_rate", "prior_max_delay_days",
  // E&S — emplois
  "jobs_created", "jobs_maintained", "jobs_women", "jobs_youth",
  "workforce_count",
  // Activité génératrice de revenus / groupement
  "activity_turnover", "activity_expenses",
  "activity_business_age_months", "activity_sales_days", "activity_purchases",
  "activity_stock_value", "activity_receivables", "activity_cash_available",
  "activity_fixed_assets", "activity_supplier_debt",
  "members_count", "active_contributing_members",
  "collective_contributions", "collective_savings",
  "collective_other_income", "collective_operating_expenses",
  "group_activity_turnover", "group_activity_expenses", "group_age_months",
  "members_with_arrears",
] as const;

type IndividualProfile = "SALARIE" | "INDEPENDANT" | "MIXTE";

const INDIVIDUAL_PROFILES: { value: IndividualProfile; label: string }[] = [
  { value: "SALARIE", label: "Salarié" },
  { value: "INDEPENDANT", label: "Indépendant" },
  { value: "MIXTE", label: "Mixte (salarié + activité)" },
];

function inferIndividualProfile(
  initial?: FinancialAnalysis,
): IndividualProfile {
  const stored = initial?.individual_profile;
  if (stored === "SALARIE" || stored === "INDEPENDANT" || stored === "MIXTE") {
    return stored;
  }
  const salary = Number(initial?.salary_income || initial?.net_salary || 0);
  const activity =
    Boolean(initial?.has_side_activity) ||
    Number(initial?.activity_turnover || 0) > 0;
  if (salary > 0 && activity) return "MIXTE";
  if (activity) return "INDEPENDANT";
  return "SALARIE";
}

const ES_STR_KEYS = [
  "sector", "sub_sector", "value_chain_position", "market_dynamic",
  "seasonality_level", "competition_intensity", "supplier_dependency",
  "client_concentration", "input_price_sensitivity", "fx_exposure",
  "regulatory_sensitivity", "climate_sensitivity", "sector_risk_level",
  "sector_outlook", "sector_comment",
  "es_category", "permit_reference", "waste_management", "resource_use",
  "chemicals_pesticides", "nuisances_emissions", "working_conditions",
  "occupational_safety", "child_forced_labor_risk", "community_impact",
  "land_resettlement_risk", "es_mitigation_plan", "es_risk_level", "es_comment",
] as const;

const ES_BOOL_KEYS = [
  "exclusion_list_ok", "env_permit_required", "env_permit_obtained",
  "eia_required", "eia_done", "es_regulatory_compliance", "es_action_required",
  "es_insurance",
] as const;

const ES_BOOL_DEFAULTS: Record<string, boolean> = {
  exclusion_list_ok: true,
  es_regulatory_compliance: true,
};

const ANALYSIS_STR_KEYS = [
  "information_quality", "financial_statement_date", "primary_repayment_source",
  "verification_comment", "employment_type", "employer_name", "employer_sector",
  "activity_name",
] as const;

const ANALYSIS_STR_DEFAULTS: Record<string, string> = {
  information_quality: "DECLARED",
};

const ANALYSIS_BOOL_KEYS = [
  "financial_documents_verified", "field_visit_confirmed", "stock_count_verified",
  "cash_position_verified", "salary_paid_through_bank", "salary_verified",
  "activity_is_formal", "activity_records_available", "group_records_verified",
  "collective_savings_locked",
] as const;

const INFORMATION_QUALITY = [
  { value: "DECLARED", label: "Déclarée par le client" },
  { value: "PARTIALLY_VERIFIED", label: "Partiellement vérifiée" },
  { value: "VERIFIED", label: "Vérifiée sur pièces / visite" },
  { value: "AUDITED", label: "Comptes certifiés / audités" },
];

const EMPLOYMENT_TYPES = [
  { value: "PERMANENT", label: "CDI / fonctionnaire" },
  { value: "FIXED_TERM", label: "CDD / contrat à terme" },
  { value: "RETIRED", label: "Retraité" },
  { value: "DAILY", label: "Journalier / intermittent" },
  { value: "OTHER", label: "Autre situation" },
];

type NumericKey = (typeof NUMERIC_KEYS)[number];
type NumericState = Record<NumericKey, string>;

const RECOMMENDATIONS = [
  { value: "FAVORABLE", label: "Favorable" },
  { value: "CONDITIONAL", label: "Favorable sous conditions" },
  { value: "UNFAVORABLE", label: "Défavorable" },
];
const PERIODS = [
  { value: "MONTHLY", label: "Mensuelle" },
  { value: "QUARTERLY", label: "Trimestrielle" },
  { value: "ANNUAL", label: "Annuelle" },
];

const FIELD_LABELS: Record<string, string> = {
  application: "Dossier",
  turnover: "Chiffre d'affaires",
  reference_period: "Période de référence",
  individual_profile: "Profil particulier",
  salary_income: "Salaire net",
  activity_turnover: "CA / recettes activité",
};

function num(v: string | null | undefined): string {
  if (v === null || v === undefined) return "";
  const n = Number(v);
  return n === 0 ? "" : String(v);
}

function buildInitialNumeric(initial?: FinancialAnalysis): NumericState {
  const state = Object.fromEntries(
    NUMERIC_KEYS.map((k) => [k, ""]),
  ) as NumericState;

  if (initial) {
    for (const key of NUMERIC_KEYS) {
      state[key] = num((initial as unknown as Record<string, string>)[key]);
    }
  }
  return state;
}

export interface FinancialAnalysisFormProps {
  mode: "create" | "edit";
  analysisId?: string;
  initial?: FinancialAnalysis;
  application: CreditApplication;
  backTo: string;
  onSaved: () => void;
}

export function FinancialAnalysisForm({
  mode,
  analysisId,
  initial,
  application,
  backTo,
  onSaved,
}: FinancialAnalysisFormProps) {
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [details, setDetails] = useState<AnalysisDetails>(initial?.analysis_details || {});
  const [statements, setStatements] = useState<FinancialStatement[]>(() => readStatements(initial?.analysis_details));
  const [statementFiles, setStatementFiles] = useState<Record<string, File>>({});
  const [minimalCashFile, setMinimalCashFile] = useState<File | null>(null);
  const [customFields, setCustomFields] = useState<Record<string, unknown>>((initial as FinancialAnalysis & { custom_fields?: Record<string, unknown> })?.custom_fields || {});
  const detailText = (key: string, label: string) => (
    <label className="field"><span>{label}</span><textarea rows={2}
      value={typeof details[key] === "string" ? details[key] as string : ""}
      onChange={(event) => setDetails((previous) => ({ ...previous, [key]: event.target.value }))}
    /></label>
  );
  const detailTable = (name: string) => <FinancialAnalysisDetails name={name} value={details} onChange={setDetails} />;
  const supplements = (names: string[], required: string[] = []) => <FinancialAnalysisSupplements names={names} value={details} onChange={setDetails} required={required} />;
  const cur = application.currency || "XOF";
  const clientType =
    (initial?.client_type ||
      application.client_type ||
      "INDIVIDUAL") as string;
  const isCorporate = clientType === "CORPORATE";
  const isGroupement = clientType === "PROFESSIONAL";
  const isIndividual = !isCorporate && !isGroupement;

  const [numbers, setNumbers] = useState<NumericState>(() =>
    buildInitialNumeric(initial),
  );
  const [externalCredits, setExternalCredits] = useState<ExternalCredit[]>(() => initialExternalCredits(initial));
  const [period, setPeriod] = useState(
    initial?.reference_period ||
      (clientType === "CORPORATE" ? "ANNUAL" : "MONTHLY"),
  );
  const [isReference, setIsReference] = useState(
    initial?.is_reference ?? mode === "create",
  );
  const [recommendation, setRecommendation] = useState(
    initial?.recommendation || "",
  );
  const [analysisDate, setAnalysisDate] = useState(
    initial?.analysis_date || "",
  );
  const [comment, setComment] = useState(initial?.comment || "");
  const [cashflowComment, setCashflowComment] = useState(
    initial?.cashflow_comment || "",
  );
  const [strengths, setStrengths] = useState(initial?.strengths || "");
  const [weaknesses, setWeaknesses] = useState(initial?.weaknesses || "");
  const [conditions, setConditions] = useState(
    initial?.recommended_conditions || "",
  );
  const [esStr, setEsStr] = useState<Record<string, string>>(() => {
    const src = initial as unknown as Record<string, string> | undefined;
    const o: Record<string, string> = {};
    for (const k of ES_STR_KEYS) o[k] = src?.[k] ?? "";
    return o;
  });
  const [esBool, setEsBool] = useState<Record<string, boolean>>(() => {
    const src = initial as unknown as Record<string, boolean> | undefined;
    const o: Record<string, boolean> = {};
    for (const k of ES_BOOL_KEYS)
      o[k] = initial ? Boolean(src?.[k]) : (ES_BOOL_DEFAULTS[k] ?? false);
    return o;
  });
  const [analysisStr, setAnalysisStr] = useState<Record<string, string>>(() => {
    const src = initial as unknown as Record<string, string> | undefined;
    const o: Record<string, string> = {};
    for (const k of ANALYSIS_STR_KEYS) {
      o[k] = src?.[k] ?? ANALYSIS_STR_DEFAULTS[k] ?? "";
    }
    return o;
  });
  const [analysisBool, setAnalysisBool] = useState<Record<string, boolean>>(() => {
    const src = initial as unknown as Record<string, boolean> | undefined;
    const o: Record<string, boolean> = {};
    for (const k of ANALYSIS_BOOL_KEYS) o[k] = Boolean(src?.[k]);
    return o;
  });
  const setStr = (k: string) => (v: string) =>
    setEsStr((p) => ({ ...p, [k]: v }));
  const toggle = (k: string) => (v: boolean) =>
    setEsBool((p) => ({ ...p, [k]: v }));
  const setAnalysis = (k: string) => (v: string) =>
    setAnalysisStr((p) => ({ ...p, [k]: v }));
  const toggleAnalysis = (k: string) => (v: boolean) =>
    setAnalysisBool((p) => ({ ...p, [k]: v }));
  const [docs, setDocs] = useState<File[]>([]);
  const dependents = application.dependents_count;

  const [hasSideActivity, setHasSideActivity] = useState(
    Boolean((initial as { has_side_activity?: boolean } | undefined)?.has_side_activity),
  );
  const [individualProfile, setIndividualProfile] = useState<IndividualProfile>(
    () => inferIndividualProfile(initial),
  );
  const configuration = useQuery({
    queryKey: ["credit-configuration", application.id, individualProfile],
    queryFn: async () => (await api.get<EffectiveConfiguration>(`/credit-applications/${application.id}/configuration/`, {
      params: { individual_profile: isIndividual ? individualProfile : "" },
    })).data,
  });
  const showSalaryBlock =
    isIndividual &&
    (individualProfile === "SALARIE" || individualProfile === "MIXTE");
  const showActivityBlock =
    isIndividual &&
    (individualProfile === "INDEPENDANT" ||
      individualProfile === "MIXTE" ||
      (individualProfile === "SALARIE" && hasSideActivity));
  const showStabilityBlock = showSalaryBlock;

  function setProfile(next: IndividualProfile) {
    setIndividualProfile(next);
    if (next === "INDEPENDANT") {
      setNumbers((previous) => ({ ...previous, salary_income: "", salary_deductions: "" }));
    }
    if (next === "INDEPENDANT" || next === "MIXTE") {
      setHasSideActivity(true);
    } else if (next === "SALARIE") {
      // Activité optionnelle : on ne force pas, on conserve le choix utilisateur.
    }
  }

  const [solidarity, setSolidarity] = useState(
    Boolean(
      (initial as { solidarity_commitment?: boolean } | undefined)
        ?.solidarity_commitment,
    ),
  );
  const [activityComment, setActivityComment] = useState(
    (initial as { activity_comment?: string } | undefined)?.activity_comment ||
      "",
  );
  const [groupComment, setGroupComment] = useState(
    (initial as { group_comment?: string } | undefined)?.group_comment || "",
  );

  const groupHasActivity = isGroupement && groupActivityOpen(details, numbers.group_activity_turnover, numbers.group_activity_expenses);
  const enteredAmount = (value: string | undefined) => {
    if (value == null || value.trim() === "") return null;
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  };
  const contributionParts = [numbers.collective_contributions, numbers.collective_other_income, numbers.collective_operating_expenses].map(enteredAmount);
  const groupContributions = contributionParts.every((item) => item == null) ? null : (contributionParts[0] ?? 0) + (contributionParts[1] ?? 0) - (contributionParts[2] ?? 0);
  const activityParts = [numbers.group_activity_turnover, numbers.group_activity_expenses].map(enteredAmount);
  const groupActivityMargin = !groupHasActivity || activityParts.every((item) => item == null) ? null : (activityParts[0] ?? 0) - (activityParts[1] ?? 0);
  const groupSavings = enteredAmount(numbers.collective_savings);
  const groupRepaymentSource = groupContributions == null && groupActivityMargin == null ? null : (groupContributions ?? 0) + (groupActivityMargin ?? 0);
  const statementBasis = isCorporate || showActivityBlock || isGroupement ? resolveStatementBasis(details as { statement_basis?: unknown; financial_statements?: unknown }) : "RECONSTITUTED";
  const path = resolveAnalysisPath({
    clientType,
    individualProfile,
    hasSideActivity,
    statementBasis: isCorporate ? statementBasis : "RECONSTITUTED",
  });
  const cycleAllowed = path !== "SALARY";
  const campaignOpen = cycleAllowed && details.campaign_open === "yes";
  const creationOpen = cycleAllowed && details.activity_creation === "yes";
  const campaignAmount = (key: string) => {
    const value = details[key];
    if (typeof value !== "string" && typeof value !== "number") return null;
    if (String(value).trim() === "") return null;
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  };
  const campaignRevenue = campaignAmount("campaign_revenue");
  const campaignCharges = campaignAmount("campaign_charges");
  const campaignSurplus = campaignRevenue == null && campaignCharges == null ? null : (campaignRevenue ?? 0) - (campaignCharges ?? 0);
  const campaignMonthly = campaignSurplus == null || !application.duration_months ? null : campaignSurplus / application.duration_months;
  const reconstitutedActivity = path === "RECONSTITUTED" || ((path === "ACTIVITY" || path === "MIXED" || (path === "GROUP" && groupHasActivity)) && statementBasis !== "STATEMENTS");
  const purposeText = purposeTestText(application.purpose_type, reconstitutedActivity);
  const operatingPurpose = application.purpose_type === "WORKING_CAPITAL" || application.purpose_type === "TREASURY" || application.purpose_type === "STOCK";
  const investmentPurpose = application.purpose_type === "EQUIPMENT" || application.purpose_type === "REAL_ESTATE";
  const minimalCashVisible = statementBasis !== "STATEMENTS" && (isCorporate || showActivityBlock || groupHasActivity);
  const minimalCashOpen = minimalCashVisible && details.minimal_cash_open === "yes";
  const cashNumber = (key: string) => {
    const value = details[key];
    if (typeof value !== "string" && typeof value !== "number") return null;
    if (String(value).trim() === "") return null;
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  };
  const minimalOpening = cashNumber("minimal_cash_opening");
  const minimalInflows = cashNumber("minimal_cash_inflows");
  const minimalOutflows = cashNumber("minimal_cash_outflows");
  const minimalClosing = cashNumber("minimal_cash_closing");
  const minimalSurplus = minimalInflows == null && minimalOutflows == null ? null : (minimalInflows ?? 0) - (minimalOutflows ?? 0);
  const minimalTheoretical = minimalOpening == null && minimalInflows == null && minimalOutflows == null ? null : (minimalOpening ?? 0) + (minimalInflows ?? 0) - (minimalOutflows ?? 0);
  const minimalGap = minimalTheoretical == null || minimalClosing == null ? null : minimalClosing - minimalTheoretical;

  const navSections = useMemo(
    () =>
      [
        { id: "fa-params", icon: Gauge, label: "Contexte", show: true },
        { id: "fa-quality", icon: Shield, label: "Fiabilité des données", show: true },
        { id: "fa-debt", icon: Landmark, label: "Endettement", show: true },
        { id: "fa-income", icon: Wallet, label: "Revenus du ménage", show: isIndividual },
        { id: "fa-stability", icon: Landmark, label: "Stabilité salariale", show: showStabilityBlock },
        { id: "fa-group", icon: Users, label: "Groupement", show: isGroupement },
        { id: "fa-business", icon: Store, label: "Stock et ventes", show: isCorporate || (groupHasActivity && statementBasis !== "STATEMENTS") },
        { id: "fa-statements", icon: FileText, label: "États financiers", show: isCorporate || showActivityBlock || (groupHasActivity && statementBasis === "STATEMENTS") },
        {
          id: "fa-activity",
          icon: Store,
          label:
            individualProfile === "INDEPENDANT"
              ? "Activité"
              : "Activité génératrice de revenus",
          show: isIndividual && (showActivityBlock || individualProfile === "SALARIE"),
        },
        { id: "fa-exploitation", icon: ReceiptText, label: "Charges et résultat", show: isCorporate },
        { id: "fa-charges", icon: ReceiptText, label: "Charges du ménage", show: isIndividual },
        { id: "fa-cycle", icon: Briefcase, label: "Campagne et création", show: isCorporate || isGroupement || showActivityBlock },
        { id: "fa-treasury", icon: Wallet, label: "Capacité et retenue", show: true },
        { id: "fa-balance", icon: Building2, label: "Bilan reconstitué", show: isCorporate },
        { id: "fa-minimal", icon: UploadCloud, label: "Trésorerie minimale", show: minimalCashVisible },
        { id: "fa-trend", icon: Gauge, label: "Caisse et tendance N-1", show: isCorporate || showActivityBlock },
        { id: "fa-collateral", icon: Shield, label: "Garanties et références", show: true },
        { id: "fa-sector", icon: Factory, label: "Analyse sectorielle", show: isCorporate || isGroupement || showActivityBlock },
        { id: "fa-es", icon: Leaf, label: "Analyse E&S", show: isCorporate || isGroupement || showActivityBlock },
        { id: "fa-conclusion", icon: Calculator, label: "Conclusion", show: true },
      ].filter((s) => sectionAllowed(s.id, path) && (s.show || configuration.data?.protected_analysis_sections?.includes(s.id)) && configuration.data?.forms?.analysis_sections.find((item) => item.id === s.id)?.visible !== false)
       .sort((left, right) => { const sections = configuration.data?.forms?.analysis_sections || []; if (!sections.length) return 0;
         const position = (id: string) => { const index = sections.findIndex((item) => item.id === id); return index < 0 ? sections.length : index; }; return position(left.id) - position(right.id); }),
    [
      isCorporate,
      isIndividual,
      isGroupement,
      individualProfile,
      showActivityBlock,
      showStabilityBlock,
      groupHasActivity,
      statementBasis,
      path,
      minimalCashVisible,
      configuration.data,
    ],
  );

  const [activeSection, setActiveSection] = useState("fa-params");

  useEffect(() => {
    const els = Array.from(
      document.querySelectorAll<HTMLElement>(".form-section"),
    );
    if (els.length === 0) return;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio);
        if (visible[0]) setActiveSection(visible[0].target.id);
      },
      { rootMargin: "-15% 0px -70% 0px", threshold: [0, 0.25, 0.5, 1] },
    );
    els.forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, [navSections.length]);

  function scrollToSection(id: string) {
    document
      .getElementById(id)
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  const set = (key: NumericKey) => (value: string) =>
    setNumbers((prev) => ({ ...prev, [key]: value }));
  const val = (key: NumericKey) => Number(numbers[key] || 0);

  // Récapitulatif calculé en direct (le backend recalcule à l'enregistrement).
  const recap = useMemo(() => {
    // Entreprise
    const gross = val("turnover") - val("cogs");
    const opex =
      val("op_rent") + val("op_salaries") + val("op_utilities") +
      val("op_transport") + val("op_telecom") + val("op_taxes") +
      val("op_maintenance") + val("op_other");
    const ebe = gross + val("other_operating_income") - opex;
    const extra = (key: string) => Number(details[key] || 0);
    const net = ebe - val("depreciation") - val("financial_charges") - extra("income_tax_expense")
      - extra("provision_expense") + extra("provision_reversal") + extra("exceptional_income") - extra("exceptional_expense");
    const cashFlow = net + val("depreciation") + extra("provision_expense") - extra("provision_reversal");
    const detailedCash = val("cash_in_hand") + val("bank_balance");
    const detailedFixedAssets =
      val("land_building_value") + val("equipment_value") +
      val("vehicle_value") + val("other_fixed_assets");
    const assets =
      val("stock_value") + val("receivables") +
      (details.cash_detail_mode === "DETAIL" ? detailedCash : details.cash_detail_mode === "LEGACY" ? val("cash_available") : detailedCash || val("cash_available")) + val("other_current_assets") +
      (details.fixed_assets_detail_mode === "DETAIL" ? detailedFixedAssets : details.fixed_assets_detail_mode === "LEGACY" ? val("fixed_assets") : detailedFixedAssets || val("fixed_assets"));
    const debts =
      val("supplier_debt") + val("ongoing_credit_balance") +
      val("short_term_debt") + val("tax_social_debt") +
      val("other_current_debt") +
      val("shareholder_debt");
    // Particulier
    let income =
      val("salary_income") + val("spouse_income") + val("rental_income") +
      val("other_activity_income") + val("other_income") +
      val("variable_income") + val("pension_income");
    if (
      individualProfile === "INDEPENDANT" ||
      individualProfile === "MIXTE" ||
      hasSideActivity
    ) {
      income += val("activity_turnover") - val("activity_expenses");
    }
    const charges =
      val("rent_expense") + val("food_expense") + val("utilities_expense") +
      val("transport_expense") + val("education_expense") +
      val("health_expense") + val("other_household_expenses") +
      val("tontine_expense") + val("social_contributions") +
      val("family_support_expense") + val("other_monthly_obligations");
    const monthlyFactor = period === "ANNUAL" ? 1 / 12 : period === "QUARTERLY" ? 1 / 3 : 1;
    const externalMonthly = externalCredits.reduce((total, row) => total + (Number(row.monthly_payment) || 0), 0);
    const disposable = (income - charges) * monthlyFactor - externalMonthly;
    return {
      gross, opex, ebe, net, cashFlow,
      equity: assets - debts,
       bfr:
         val("stock_value") + val("receivables") + val("other_current_assets") -
         val("supplier_debt") - val("tax_social_debt") - val("other_current_debt"),
      income,
      charges,
      disposable,
      perCapita:
        dependents !== null && dependents !== undefined
          ? disposable / (dependents + 1)
          : null,
      surplus:
        val("projected_monthly_inflows") - val("projected_monthly_outflows"),
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [numbers, isCorporate, dependents, individualProfile, hasSideActivity, period, details, externalCredits]);

  const mutation = useMutation({
    mutationFn: async (derived: DerivedExternalDebt) => {
      const fd = new FormData();
      const applied = path === "STATEMENTS" ? referenceFieldOverrides(statements) : { numbers: {}, details: {} };
      const rest = { ...details } as AnalysisDetails & { financial_statements?: unknown; statement_basis?: string };
      delete rest.financial_statements;
      if (isCorporate || showActivityBlock || isGroupement) rest.statement_basis = statementBasis;
      else delete rest.statement_basis;
      fd.append("analysis_details", JSON.stringify({
        ...rest,
        ...applied.details,
        external_credits: derived.rows,
        financial_statements: statements,
      }));
      fd.append("custom_fields", JSON.stringify(customFields));
      if (mode === "create") fd.append("application", application.id);
      for (const key of NUMERIC_KEYS) {
        const v = (applied.numbers[key] ?? numbers[key]).trim();
        const nullable = ["employment_seniority_months", "informal_income_weight", "max_days_late", "prior_repayment_rate", "prior_max_delay_days", "jobs_created", "jobs_maintained", "jobs_women", "jobs_youth", "workforce_count", "members_count", "active_contributing_members", "bank_statement_months", "activity_business_age_months", "activity_sales_days", "group_age_months", "members_with_arrears"].includes(key);
        fd.append(key, v || (nullable ? "" : "0"));
      }
      fd.set("existing_debt_initial_amount", derived.initial_amount);
      fd.set("existing_debt_monthly", derived.monthly);
      fd.set("active_loans_count", derived.count);
      fd.set("max_days_late", derived.max_days_late);
      fd.append("reference_period", period);
      fd.append("is_reference", String(isReference));
      fd.append("existing_debt_institution", derived.institution);
      fd.append("cashflow_comment", cashflowComment);
      fd.append("credit_bureau_checked", String(derived.bureau_checked));
      fd.append("credit_bureau_date", derived.bureau_date);
      fd.append("has_payment_incidents", String(derived.incidents));
      fd.append("incidents_comment", derived.comment);
      fd.append("has_side_activity", String(
        individualProfile === "INDEPENDANT" ||
          individualProfile === "MIXTE" ||
          hasSideActivity,
      ));
      if (isIndividual) {
        fd.append("individual_profile", individualProfile);
      }
      fd.append("activity_comment", activityComment);
      fd.append("solidarity_commitment", String(solidarity));
      fd.append("group_comment", groupComment);
      fd.append("strengths", strengths);
      fd.append("weaknesses", weaknesses);
      fd.append("recommended_conditions", conditions);
      for (const k of ES_STR_KEYS) {
        const v = (esStr[k] ?? "").trim();
        fd.append(k, v);
      }
      for (const k of ES_BOOL_KEYS) fd.append(k, String(esBool[k]));
      for (const k of ANALYSIS_STR_KEYS) {
        const v = (analysisStr[k] ?? "").trim();
        fd.append(k, v);
      }
      for (const k of ANALYSIS_BOOL_KEYS) {
        fd.append(k, String(analysisBool[k]));
      }
      fd.append("recommendation", recommendation);
      fd.append("analysis_date", analysisDate);
      fd.append("comment", comment);
      for (const d of docs) fd.append("documents", d);
      for (const [key, file] of Object.entries(statementFiles)) {
        const separator = key.indexOf(":");
        fd.append(`statement_file__${key.slice(0, separator)}__${key.slice(separator + 1)}`, file);
      }
      if (minimalCashOpen && minimalCashFile) fd.append("minimal_cash_file", minimalCashFile);
      if (mode === "edit" && analysisId) {
        return (await api.patch(`/financial-analyses/${analysisId}/`, fd)).data;
      }
      return (await api.post("/financial-analyses/", fd)).data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["financial-analysis"] });
      qc.invalidateQueries({ queryKey: ["credit-application"] });
      qc.invalidateQueries({ queryKey: ["credit-readiness"] });
      qc.invalidateQueries({ queryKey: ["credit-configuration"] });
      onSaved();
    },
    onError: (e: unknown) => {
      const resp = (e as { response?: { status?: number; data?: unknown } })
        ?.response;
      const data = resp?.data;
      const errors =
        data && typeof data === "object" && "errors" in data
          ? (data as { errors: unknown }).errors
          : data;
      if (errors && typeof errors === "object" && !Array.isArray(errors)) {
        setError(
          Object.entries(errors as Record<string, unknown>)
            .map(([k, v]) => {
              const label = FIELD_LABELS[k] ?? k;
              const msg = Array.isArray(v) ? v.join(", ") : String(v);
              return `${label} : ${msg}`;
            })
            .join(" · "),
        );
        return;
      }
      const status = resp?.status;
      if (status === 413)
        setError("Les documents joints sont trop volumineux.");
      else if (status && status >= 500)
        setError("Erreur serveur lors de l'enregistrement.");
      else if (!resp)
        setError("Connexion au serveur impossible. Vérifiez votre réseau.");
      else setError("Enregistrement impossible. Vérifiez les champs.");
    },
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    const derived = deriveExternalDebt(externalCredits);
    if (derived.error) {
      setError(derived.error);
      scrollToSection("fa-debt");
      return;
    }
    const statementIssue = path === "STATEMENTS" || (showActivityBlock && statementBasis === "STATEMENTS") || (groupHasActivity && statementBasis === "STATEMENTS") ? statementError(statements) : null;
    if (statementIssue) {
      setError(statementIssue);
      scrollToSection("fa-statements");
      return;
    }
    setError(null);
    mutation.mutate(derived);
  }

  function updateExternalCredit(index: number, patch: Partial<ExternalCredit>) {
    setExternalCredits((rows) => rows.map((row, rowIndex) => rowIndex === index ? { ...row, ...patch } : row));
  }

  return (
    <AnalysisLayoutContext.Provider value={configuration.data?.forms?.analysis_sections || []}>
    <AnalysisPathContext.Provider value={path}>
    <form className="credit-form" onSubmit={submit}>
      <aside className="credit-form-nav">
        <div className="credit-form-nav-inner">
          <p className="credit-form-nav-title">Sections</p>
          {navSections.map((s) => (
            <button
              key={s.id}
              type="button"
              className={`credit-nav-item${activeSection === s.id ? " active" : ""}`}
              onClick={() => scrollToSection(s.id)}
            >
              <s.icon size={15} />
              <span>{s.label}</span>
            </button>
          ))}
        </div>
      </aside>

      <AnalysisContent>
        {configuration.data && <div className="card" style={{ order: -100 }}><div className="card-body">
          <strong>Exigences applicables à cette analyse</strong>
          <p className="muted">{configuration.data.sources.map((source) => `${source.name} v${source.version}`).join(" → ") || "Politique de la filiale"}
            {configuration.data.frozen ? " — règles conservées à la soumission" : " — règles courantes"}</p>
          {!!configuration.data.analysis.minimum_bank_statement_months && <p>Relevés examinés : au moins {configuration.data.analysis.minimum_bank_statement_months} mois.</p>}
          {!!configuration.data.analysis.required_fields.length && <p>Champs et vérifications requis : {configuration.data.analysis.required_fields.map((key) => configuration.data?.required_labels?.[key] || key).join(", ")}.</p>}
          {!!configuration.data.analysis.required_detail_tables.length && <p>Tableaux requis : {configuration.data.analysis.required_detail_tables.map((key) => DETAIL_TABLE_LABELS[key] || key).join(", ")}.</p>}
          <p className="muted small">Ces exigences sont contrôlées à la soumission du dossier. Vous pouvez enregistrer une analyse en cours.</p>
          <p className="muted small">Scoring : {configuration.data.scoring.grid.engine === "CUSTOM" ? "grille personnalisée" : "grille existante"}.
            {configuration.data.scoring.grid.missing_data === "BLOCK_SUBMIT" && " Tous les indicateurs de la grille doivent être disponibles avant soumission."}
            {configuration.data.eligibility.rules.length > 0 && ` ${configuration.data.eligibility.rules.length} condition(s) d'éligibilité sont également contrôlées selon l'étape prévue.`}</p>
        </div></div>}
        {configuration.isError && <p className="form-error" role="alert">Impossible de charger les exigences configurées. Rechargez la page ; la soumission restera contrôlée par le serveur.</p>}
        <FormSection
          id="fa-params"
          icon={Gauge}
          title="Contexte de l'analyse"
          description="Période de référence et date de l'analyse."
        >
          <div className={`profile-banner ${isCorporate ? "corp" : "indiv"}`}>
            {isCorporate ? (
              <Store size={16} />
            ) : isGroupement ? (
              <Users size={16} />
            ) : (
              <Briefcase size={16} />
            )}
            <span>
              Profil :{" "}
              <strong>
                {isCorporate
                  ? "Personne morale"
                  : isGroupement
                    ? "Groupement"
                    : "Personne physique"}
              </strong>
              {application.client_display
                ? ` — ${application.client_display}`
                : ""}
            </span>
          </div>
          <p className="profile-banner">Parcours retenu : <strong>{pathLabel(path)}</strong>. Les autres rubriques restent enregistrées et n'alimentent pas les ratios.</p>
          {isCorporate && (
            <Checkbox
              label="Le client dispose d'états financiers établis"
              checked={statementBasis === "STATEMENTS"}
              onChange={(checked) => setDetails((current) => ({ ...current, statement_basis: checked ? "STATEMENTS" : "RECONSTITUTED" }))}
            />
          )}
          {isIndividual && individualProfile === "SALARIE" && (
            <Checkbox
              label="Exerce aussi une activité génératrice de revenus"
              checked={hasSideActivity}
              onChange={setHasSideActivity}
            />
          )}
          {isIndividual && (
            <Select
              label="Situation professionnelle"
              value={individualProfile}
              onChange={(v) => {
                if (
                  v === "SALARIE" ||
                  v === "INDEPENDANT" ||
                  v === "MIXTE"
                ) {
                  setProfile(v);
                }
              }}
              options={INDIVIDUAL_PROFILES}
            />
          )}
          <div className="form-grid two-col">
            <Select
              label="Période de référence"
              value={period}
              onChange={setPeriod}
              options={PERIODS}
            />
            <Money label="Date de l'analyse" type="date" value={analysisDate} onChange={setAnalysisDate} />
          </div>
          <Checkbox
            label="Analyse de référence du dossier (score, risque, comité)"
            checked={isReference}
            onChange={setIsReference}
          />
          <p className="muted small">Une seule analyse fait référence. Ce choix remplace la référence précédente ; la première analyse du dossier devient automatiquement référence.</p>
          <p className="muted small" style={{ marginBottom: 0 }}>
            Les revenus et charges d'exploitation sont saisis sur la période (
            {FINANCE_LABELS.reference_period[period]}). Défaut :{" "}
            {isCorporate
              ? "annuelle (personne morale)"
              : isGroupement
                ? "mensuelle (groupement)"
                : "mensuelle (personne physique)"}
            . Les bilans et patrimoines sont des soldes à la date d'arrêté.
            Les mensualités de dettes et prévisions de trésorerie restent mensuelles.
          </p>
        </FormSection>

        <FormSection
          id="fa-quality"
          icon={Shield}
          title="Fiabilité des informations et contre-analyse"
          description="Source des données, pièces consultées et écarts entre déclaratif, documents et visite."
        >
          <div className="form-grid two-col">
            <Select
              label="Niveau de fiabilité retenu"
              value={analysisStr.information_quality}
              onChange={setAnalysis("information_quality")}
              options={INFORMATION_QUALITY}
            />
            <label className="field">
              <span>Date d'arrêté des données financières</span>
              <input
                type="date"
                value={analysisStr.financial_statement_date}
                onChange={(e) => setAnalysis("financial_statement_date")(e.target.value)}
              />
            </label>
            <Money
              label="Mois de relevés bancaires / mobile money examinés"
              value={numbers.bank_statement_months}
              onChange={set("bank_statement_months")}
            />
            <Text
              label="Source principale de remboursement"
              value={analysisStr.primary_repayment_source}
              onChange={setAnalysis("primary_repayment_source")}
            />
          </div>
          <div className="form-grid two-col">
            <Checkbox
              label="Pièces financières vérifiées"
              checked={analysisBool.financial_documents_verified}
              onChange={toggleAnalysis("financial_documents_verified")}
            />
            <Checkbox
              label="Visite terrain prise en compte"
              checked={analysisBool.field_visit_confirmed}
              onChange={toggleAnalysis("field_visit_confirmed")}
            />
            {(isCorporate || showActivityBlock) && (
              <Checkbox
                label="Stock vérifié / inventorié"
                checked={analysisBool.stock_count_verified}
                onChange={toggleAnalysis("stock_count_verified")}
              />
            )}
            {(isCorporate || showActivityBlock) && (
              <Checkbox
                label="Caisse et banques vérifiées"
                checked={analysisBool.cash_position_verified}
                onChange={toggleAnalysis("cash_position_verified")}
              />
            )}
          </div>
          <label className="field">
            <span>Écarts constatés, méthodes de reconstitution et réserves</span>
            <textarea
              rows={3}
              value={analysisStr.verification_comment}
              onChange={(e) => setAnalysis("verification_comment")(e.target.value)}
              placeholder="Préciser les éléments déclaratifs, les contrôles effectués et les ajustements retenus."
            />
          </label>
        </FormSection>

      {isCorporate ? (
        <>
          <FormSection id="fa-business" icon={Store} title="Reconstitution de l'activité" description="Produits revendus, produits fabriqués, services, ventes et organisation économique.">
            <ProductSheetTable value={details} onChange={setDetails} currency={cur} />
            {detailText("business_model", "Modèle économique : clientèle, fournisseurs et approvisionnements")}
            {detailText("sales_verification", "Rapprochement du CA : ventes, achats, caisse, banque et mobile money")}
            <TpeReconstitution details={details} onChange={setDetails} currency={cur} part="sales" />
          </FormSection>
          <FormSection
            id="fa-statements"
            icon={FileText}
            title="États financiers établis"
            description="Un exercice par bloc. L'exercice dont la date de fin est la plus récente alimente les ratios. Chaque pièce a son document."
          >
            <p className="muted small">Une case vide reste vide. Les comptes courants d'associés se saisissent dans les autres dettes. La part à plus d'un an vient des notes : si elle est vide, elle ne reste pas sur l'exercice retenu. Le loyer, l'eau, le téléphone et l'entretien séparés sont remis à zéro dès que l'état porte les charges, pour ne pas les compter deux fois.</p>
            <label className="check-row">
              <input
                type="checkbox"
                checked={details.manufactures === "yes"}
                onChange={(event) => setDetails((current) => ({ ...current, manufactures: event.target.checked ? "yes" : "no" }))}
              />
              Cette entreprise fabrique ou transforme
            </label>
            {details.manufactures === "yes" && <div className="product-line">
              <h4>Identité de la production</h4>
              <p className="muted small">Les montants de production sont déjà dans les états : ventes de produits fabriqués, production stockée, achats de matières et stocks. Cette fiche ne les ressaisit pas. La main-d'œuvre est décrite ici ; son montant reste dans les charges de personnel.</p>
              {PRODUCTION_IDENTITY.map((field) => detailText(field.key, field.label))}
            </div>}
            <FinancialStatementsEditor
              statements={statements}
              onChange={setStatements}
              files={statementFiles}
              onFile={(exerciseId: string, piece: StatementPiece, file: File | null) => {
                setStatementFiles((current) => {
                  const next = { ...current };
                  const key = `${exerciseId}:${piece}`;
                  if (file) next[key] = file;
                  else delete next[key];
                  return next;
                });
              }}
              documents={initial?.documents || []}
              currency={cur}
            />
          </FormSection>
          <FormSection
            id="fa-exploitation"
            icon={ReceiptText}
            title="Activité et compte de résultat reconstitué"
            description="Ventes, achats, charges et résultat sur la période de référence."
          >
            {creationOpen && <p className="muted small">Activité en création : ce chiffre d&apos;affaires passé n&apos;est pas exigé. La prévision de trésorerie porte le DSCR.</p>}
            <div className="form-grid two-col">
              <Money label="Chiffre d'affaires" value={numbers.turnover} onChange={set("turnover")} cur={cur} />
              <Money label="Autres produits d'exploitation" value={numbers.other_operating_income} onChange={set("other_operating_income")} cur={cur} />
              <Money label="Coût d'achat des marchandises (CAMV)" value={numbers.cogs} onChange={set("cogs")} cur={cur} />
              <Money label="Loyer" value={numbers.op_rent} onChange={set("op_rent")} cur={cur} />
              <Money label="Salaires" value={numbers.op_salaries} onChange={set("op_salaries")} cur={cur} />
              <Money label="Eau / électricité" value={numbers.op_utilities} onChange={set("op_utilities")} cur={cur} />
              <Money label="Transport / carburant" value={numbers.op_transport} onChange={set("op_transport")} cur={cur} />
              <Money label="Téléphone / internet" value={numbers.op_telecom} onChange={set("op_telecom")} cur={cur} />
              <Money label="Impôts & patente" value={numbers.op_taxes} onChange={set("op_taxes")} cur={cur} />
              <Money label="Entretien" value={numbers.op_maintenance} onChange={set("op_maintenance")} cur={cur} />
              <Money label="Autres charges d'exploitation" value={numbers.op_other} onChange={set("op_other")} cur={cur} />
              <Money label="Amortissements" value={numbers.depreciation} onChange={set("depreciation")} cur={cur} />
              <Money label="Charges financières" value={numbers.financial_charges} onChange={set("financial_charges")} cur={cur} />
            </div>
            <div className="finance-recap">
              <RecapItem label="Marge brute" value={formatMoney(recap.gross, cur)} />
              <RecapItem label="EBE" value={formatMoney(recap.ebe, cur)} />
              <RecapItem label="Résultat net" value={formatMoney(recap.net, cur)} strong />
              <RecapItem label="Cash-flow" value={formatMoney(recap.cashFlow, cur)} />
            </div>
            <details><summary>Compléments comptables et flux disponibles</summary>
              <p className="muted small">Montants sur la période de référence. Les charges fixes et variables décomposent les charges d'exploitation déjà saisies : elles ne sont pas soustraites une seconde fois. Le flux avant dette retire les éléments exceptionnels, la variation du BFR et les investissements de maintien.</p>
              {supplements(["income_tax_expense", "provision_expense", "provision_reversal", "exceptional_income", "exceptional_expense", "fixed_operating_costs", "variable_operating_costs", "bfr_change", "maintenance_investment"])}
            </details>
          </FormSection>

          <FormSection
            id="fa-balance"
            icon={Building2}
            title="Bilan reconstitué"
            description="Actifs d'exploitation, trésorerie, immobilisations et passifs à la date d'arrêté."
          >
            <p className="subsection-label">Actifs courants</p>
            <div className="form-grid two-col">{([ ["cash_detail_mode", "Source de trésorerie"], ["fixed_assets_detail_mode", "Source des immobilisations"] ] as const).map(([key, label]) => <label className="field" key={key}>
              <span>{label}</span><select value={typeof details[key] === "string" ? details[key] : ""} onChange={(event) => setDetails({ ...details, [key]: event.target.value })}>
                <option value="">Historique : détail non nul, sinon agrégat</option><option value="DETAIL">Détail, y compris si vérifié nul</option><option value="LEGACY">Agrégat historique</option>
              </select></label>)}</div>
            {(Number(initial?.cash_available) > 0 || Number(initial?.fixed_assets) > 0) && <div className="form-grid two-col">
              <Money label="Trésorerie globale historique (repli si détail nul)" value={numbers.cash_available} onChange={set("cash_available")} cur={cur} />
              <Money label="Immobilisations globales historiques (repli si détail nul)" value={numbers.fixed_assets} onChange={set("fixed_assets")} cur={cur} />
            </div>}
            <div className="form-grid two-col">
              <Money label="Stock" value={numbers.stock_value} onChange={set("stock_value")} cur={cur} />
              <Money label="Créances clients" value={numbers.receivables} onChange={set("receivables")} cur={cur} />
              <Money label="Caisse" value={numbers.cash_in_hand} onChange={set("cash_in_hand")} cur={cur} />
              <Money label="Solde bancaire disponible" value={numbers.bank_balance} onChange={set("bank_balance")} cur={cur} />
              <Money label="Autres actifs courants" value={numbers.other_current_assets} onChange={set("other_current_assets")} cur={cur} />
            </div>
            <p className="subsection-label">Immobilisations</p>
            <div className="form-grid two-col">
              <Money label="Terrains et bâtiments" value={numbers.land_building_value} onChange={set("land_building_value")} cur={cur} />
              <Money label="Matériel et équipements" value={numbers.equipment_value} onChange={set("equipment_value")} cur={cur} />
              <Money label="Véhicules d'exploitation" value={numbers.vehicle_value} onChange={set("vehicle_value")} cur={cur} />
              <Money label="Autres immobilisations" value={numbers.other_fixed_assets} onChange={set("other_fixed_assets")} cur={cur} />
            </div>
            <p className="subsection-label">Passifs et structure financière</p>
            <div className="form-grid two-col">
              <Money label="Dettes fournisseurs" value={numbers.supplier_debt} onChange={set("supplier_debt")} cur={cur} />
              <Money label="Dettes fiscales et sociales" value={numbers.tax_social_debt} onChange={set("tax_social_debt")} cur={cur} />
              <Money label="Autres dettes d'exploitation" value={numbers.other_current_debt} onChange={set("other_current_debt")} cur={cur} />
              <Money label="Autres dettes court terme" value={numbers.short_term_debt} onChange={set("short_term_debt")} cur={cur} />
              <Money label="Encours financier total (court et long terme)" value={numbers.ongoing_credit_balance} onChange={set("ongoing_credit_balance")} cur={cur} />
              <Money label="Dont part long terme de l'encours financier total" value={numbers.long_term_debt} onChange={set("long_term_debt")} cur={cur} />
              <Money label="Comptes courants d'associés" value={numbers.shareholder_debt} onChange={set("shareholder_debt")} cur={cur} />
            </div>
            <div className="finance-recap">
              <RecapItem label="Capitaux propres" value={formatMoney(recap.equity, cur)} strong />
              <RecapItem label="BFR" value={formatMoney(recap.bfr, cur)} />
            </div>
            {detailText("receivables_quality", "Créances : ancienneté, impayés, concentration, recouvrabilité")}
            {detailText("asset_ownership", "Immobilisations : propriété, valeur nette, état, sûretés")}
            <details><summary>Soldes d'ouverture et rapprochement comptable</summary>
              {supplements(["period_purchases", "opening_stock", "opening_receivables", "opening_supplier_debt", "declared_equity"])}
            </details>
          </FormSection>

        </>
      ) : isGroupement ? (
        <>
        <FormSection
          id="fa-group"
          icon={Users}
          title="Analyse groupement"
          description="Gouvernance, régularité des cotisations, épargne et capacité collective."
        >
          <div className="form-grid two-col">
            <Money
              label="Nombre de membres"
              type="number"
              value={numbers.members_count}
              onChange={set("members_count")}
            />
            <Money
              label="Membres cotisants actifs"
              type="number"
              value={numbers.active_contributing_members}
              onChange={set("active_contributing_members")}
            />
            <Money
              label="Membres en retard de cotisation"
              type="number"
              value={numbers.members_with_arrears}
              onChange={set("members_with_arrears")}
            />
            <Money
              label="Ancienneté du groupement (mois)"
              type="number"
              value={numbers.group_age_months}
              onChange={set("group_age_months")}
            />
            <Money
              label="Cotisations périodiques"
              value={numbers.collective_contributions}
              onChange={set("collective_contributions")}
              cur={cur}
            />
            <Money
              label="Épargne du groupement"
              value={numbers.collective_savings}
              onChange={set("collective_savings")}
              cur={cur}
            />
            <Money
              label="Autres recettes collectives"
              value={numbers.collective_other_income}
              onChange={set("collective_other_income")}
              cur={cur}
            />
            <Money
              label="Charges de fonctionnement"
              value={numbers.collective_operating_expenses}
              onChange={set("collective_operating_expenses")}
              cur={cur}
            />
          </div>
          <p className="muted small">Les cotisations, les autres recettes et les charges de fonctionnement forment la source collective. L'épargne est un stock : elle n'est pas un revenu et n'est pas ajoutée aux cotisations.</p>
          <Checkbox
            label="Le groupement a une activité commune, distincte des cotisations"
            checked={groupHasActivity}
            onChange={(checked) => setDetails((current) => ({ ...current, group_has_activity: checked ? "yes" : "no" }))}
          />
          {groupHasActivity && <label className="field">
            <span>Support de l'activité commune</span>
            <select value={statementBasis === "STATEMENTS" ? "STATEMENTS" : "RECONSTITUTED"} onChange={(event) => setDetails((current) => ({ ...current, statement_basis: event.target.value }))}>
              <option value="RECONSTITUTED">Reconstituer l'activité</option>
              <option value="STATEMENTS">États financiers établis ou à constituer</option>
            </select>
          </label>}
          <div className="finance-recap">
            <RecapItem label="Cotisations nettes" value={formatMoney(groupContributions, cur)} />
            <RecapItem label="Marge de l'activité commune" value={groupHasActivity && !campaignOpen ? formatMoney(groupActivityMargin, cur) : "Non retenue"} />
            <RecapItem label="Source de remboursement" value={formatMoney(groupHasActivity && !campaignOpen ? groupRepaymentSource : groupContributions, cur)} strong />
            <RecapItem label="Épargne, hors revenu" value={formatMoney(groupSavings, cur)} />
          </div>
          {campaignOpen && <p className="muted small">La campagne est ouverte. La marge d&apos;activité n&apos;entre pas dans la capacité : le surplus de campagne, réparti sur la durée du crédit, la remplace. Les cotisations nettes restent. L&apos;épargne ne s&apos;ajoute pas.</p>}
          <label className="check-row" style={{ marginTop: "0.75rem" }}>
            <input
              type="checkbox"
              checked={solidarity}
              onChange={(e) => setSolidarity(e.target.checked)}
            />
            Engagement de solidarité entre membres
          </label>
          <div className="form-grid two-col" style={{ marginTop: "0.75rem" }}>
            <Checkbox
              label="Registres, cotisations et épargne vérifiés"
              checked={analysisBool.group_records_verified}
              onChange={toggleAnalysis("group_records_verified")}
            />
            <Checkbox
              label="Épargne collective mobilisable ou nantie"
              checked={analysisBool.collective_savings_locked}
              onChange={toggleAnalysis("collective_savings_locked")}
            />
          </div>
          <label className="field" style={{ marginTop: "0.75rem" }}>
            <span>Commentaire groupement</span>
            <textarea
              rows={3}
              value={groupComment}
              onChange={(e) => setGroupComment(e.target.value)}
            />
          </label>
        </FormSection>
        {groupHasActivity && statementBasis !== "STATEMENTS" && <FormSection
          id="fa-business"
          icon={Store}
          title="Activité commune reconstituée"
          description="Fiches, ventes et charges de l'activité. Les cotisations restent dans le groupement."
        >
          <p className="muted small">Le chiffre d'affaires saisi ici est celui de l'activité commune. Il n'inclut pas les cotisations, les autres recettes ni l'épargne. La marge retenue pour la source est ce chiffre d'affaires moins les charges de l'activité. Les fiches servent à le rapprocher.</p>
          <ProductSheetTable value={details} onChange={setDetails} currency={cur} />
          <TpeReconstitution details={details} onChange={setDetails} currency={cur} part="sales" />
          <TpeReconstitution details={details} onChange={setDetails} currency={cur} part="cash" />
          {detailText("group_activity_description", "Activité commune : ce qui est vendu, à qui, et la saison")}
          <div className="form-grid two-col">
            <Money label="Chiffre d'affaires de l'activité commune" value={numbers.group_activity_turnover} onChange={set("group_activity_turnover")} cur={cur} />
            <Money label="Charges de l'activité commune" value={numbers.group_activity_expenses} onChange={set("group_activity_expenses")} cur={cur} />
          </div>
          <div className="finance-recap">
            <RecapItem label="Marge retenue, hors cotisations" value={formatMoney(groupActivityMargin, cur)} strong />
            <RecapItem label="Marge des fiches" value={retainedActivityMargin(details.products, numbers.group_activity_turnover, numbers.group_activity_expenses).source === "sheet" ? formatMoney(retainedActivityMargin(details.products, numbers.group_activity_turnover, numbers.group_activity_expenses).value, cur) : "—"} />
          </div>
        </FormSection>}
        {groupHasActivity && statementBasis === "STATEMENTS" && <FormSection
          id="fa-statements"
          icon={FileText}
          title="États financiers de l'activité commune"
          description="États établis ou à constituer. Les cotisations et l'épargne restent dans le groupement."
        >
          <p className="muted small">Même pièces que pour l'entreprise : résultat, bilan, flux et notes, un document par pièce. Ces états ne remplacent pas les cotisations et n'ajoutent pas l'épargne au revenu.</p>
          <FinancialStatementsEditor
            statements={statements}
            onChange={setStatements}
            files={statementFiles}
            onFile={(exerciseId: string, piece: StatementPiece, file: File | null) => {
              setStatementFiles((current) => {
                const next = { ...current };
                const key = `${exerciseId}:${piece}`;
                if (file) next[key] = file;
                else delete next[key];
                return next;
              });
            }}
            documents={initial?.documents || []}
            currency={cur}
          />
          <ActivityStatementReading statements={statements} margin={retainedActivityMargin(details.products, numbers.group_activity_turnover, numbers.group_activity_expenses)} currency={cur} audience="group" />
        </FormSection>}
        </>
      ) : (
        <>
          <FormSection
            id="fa-income"
            icon={Wallet}
            title="Revenus du ménage"
            description={
              individualProfile === "INDEPENDANT"
                ? "Revenus du foyer hors activité principale (conjoint, locatif, autres)."
                : "Ensemble des revenus perçus par le foyer."
            }
          >
            <div className="form-grid two-col">
              {showSalaryBlock && (
                <Money
                  label="Salaire net (demandeur)"
                  value={numbers.salary_income}
                  onChange={set("salary_income")}
                  cur={cur}
                />
              )}
              <Money label="Revenus du conjoint" value={numbers.spouse_income} onChange={set("spouse_income")} cur={cur} />
              <Money label="Revenus locatifs / rente" value={numbers.rental_income} onChange={set("rental_income")} cur={cur} />
              <Money label="Pension / retraite" value={numbers.pension_income} onChange={set("pension_income")} cur={cur} />
              <Money label="Primes et revenus variables récurrents" value={numbers.variable_income} onChange={set("variable_income")} cur={cur} />
              <Money label="Autres revenus" value={numbers.other_income} onChange={set("other_income")} cur={cur} />
              {!showStabilityBlock && <Money label="Pondération des revenus informels (%) — vide : seuil établissement" value={numbers.informal_income_weight} onChange={set("informal_income_weight")} />}
            </div>
            <div className="finance-recap">
              <RecapItem label="Total revenus" value={formatMoney(recap.income, cur)} strong />
            </div>
            {detailText("household_income_evidence", "Justificatifs : régularité, part du conjoint disponible, loyers nets et revenus retenus")}
          </FormSection>

          <FormSection
            id="fa-activity"
            icon={Store}
            title={
              individualProfile === "INDEPENDANT"
                ? "Activité génératrice de revenus"
                : individualProfile === "MIXTE"
                  ? "Activité génératrice de revenus"
                  : "Activité génératrice de revenus (optionnelle)"
            }
            description={
              individualProfile === "INDEPENDANT"
                ? "Activité principale du demandeur (CA et charges)."
                : individualProfile === "MIXTE"
                  ? "Activité exercée en plus du salaire."
                  : "Si le demandeur exerce une activité indépendante en plus du salaire."
            }
          >
            {showActivityBlock && (
              <>
                <ProductSheetTable value={details} onChange={setDetails} currency={cur} />
                <TpeReconstitution details={details} onChange={setDetails} currency={cur} part="sales" />
                {detailText("business_model", "Modèle économique : clientèle, fournisseurs et approvisionnements")}
                {detailText("sales_verification", "Reconstitution des ventes : recettes journalières, cahier de caisse et mobile money")}
                {creationOpen && <p className="muted small">Activité en création : ces recettes passées ne sont pas exigées. Elles ne sont pas recopiées dans la prévision.</p>}
                <div className="form-grid two-col" style={{ marginTop: "0.75rem" }}>
                  <Text
                    label="Activité principale / produit ou service"
                    value={analysisStr.activity_name}
                    onChange={setAnalysis("activity_name")}
                  />
                  <Money
                    label="Ancienneté de l'activité (mois)"
                    value={numbers.activity_business_age_months}
                    onChange={set("activity_business_age_months")}
                  />
                  <Money
                    label="Jours de vente sur la période"
                    value={numbers.activity_sales_days}
                    onChange={set("activity_sales_days")}
                  />
                  <Money
                    label="CA / recettes activité"
                    value={numbers.activity_turnover}
                    onChange={set("activity_turnover")}
                    cur={cur}
                  />
                  <Money
                    label="Charges totales d'activité (achats inclus)"
                    value={numbers.activity_expenses}
                    onChange={set("activity_expenses")}
                    cur={cur}
                  />
                  <Money
                    label="dont achats / approvisionnements"
                    value={numbers.activity_purchases}
                    onChange={set("activity_purchases")}
                    cur={cur}
                  />
                </div>
                <div className="form-grid two-col">
                  <Checkbox
                    label="Activité formalisée"
                    checked={analysisBool.activity_is_formal}
                    onChange={toggleAnalysis("activity_is_formal")}
                  />
                  <Checkbox
                    label="Cahier de caisse ou pièces d'activité disponibles"
                    checked={analysisBool.activity_records_available}
                    onChange={toggleAnalysis("activity_records_available")}
                  />
                </div>
                <label className="field">
                  <span>Commentaire activité : charges, prélèvements du ménage et absence de double comptage</span>
                  <textarea
                    rows={2}
                    value={activityComment}
                    onChange={(e) => setActivityComment(e.target.value)}
                  />
                </label>
              </>
            )}
          </FormSection>

          {showActivityBlock && <FormSection
            id="fa-statements"
            icon={FileText}
            title="États financiers de l'activité"
            description="À ajouter quand l'activité a des états, ou quand ils doivent être constitués. Le ménage et l'activité restent."
          >
            <Checkbox
              label="Cette activité a des états financiers, ou ils sont à constituer"
              checked={statementBasis === "STATEMENTS"}
              onChange={(checked) => setDetails((current) => ({ ...current, statement_basis: checked ? "STATEMENTS" : "RECONSTITUTED" }))}
            />
            <p className="muted small">Le compte de résultat, le bilan, le tableau des flux et les notes sont les mêmes que pour l'entreprise. Un document par pièce, plusieurs exercices. L'auteur et la certification distinguent un état reçu d'un état constitué ici. Ces montants ne remplacent ni le salaire, ni le chiffre d'affaires de l'activité, ni les charges du foyer.</p>
            {statementBasis === "STATEMENTS" && <>
              <FinancialStatementsEditor
                statements={statements}
                onChange={setStatements}
                files={statementFiles}
                onFile={(exerciseId: string, piece: StatementPiece, file: File | null) => {
                  setStatementFiles((current) => {
                    const next = { ...current };
                    const key = `${exerciseId}:${piece}`;
                    if (file) next[key] = file;
                    else delete next[key];
                    return next;
                  });
                }}
                documents={initial?.documents || []}
                currency={cur}
              />
              <ActivityStatementReading statements={statements} margin={retainedActivityMargin(details.products, numbers.activity_turnover, numbers.activity_expenses)} currency={cur} />
            </>}
          </FormSection>}

          <FormSection
            id="fa-charges"
            icon={ReceiptText}
            title="Charges, obligations et patrimoine du ménage"
            description="Dépenses récurrentes, engagements non bancaires et actifs du foyer."
          >
            <div className="form-grid two-col">
              <Money label="Loyer / logement" value={numbers.rent_expense} onChange={set("rent_expense")} cur={cur} />
              <Money label="Alimentation" value={numbers.food_expense} onChange={set("food_expense")} cur={cur} />
              <Money label="Eau / électricité / téléphone" value={numbers.utilities_expense} onChange={set("utilities_expense")} cur={cur} />
              <Money label="Transport" value={numbers.transport_expense} onChange={set("transport_expense")} cur={cur} />
              <Money label="Scolarité / éducation" value={numbers.education_expense} onChange={set("education_expense")} cur={cur} />
              <Money label="Santé" value={numbers.health_expense} onChange={set("health_expense")} cur={cur} />
              <Money label="Tontines / cotisations d'épargne" value={numbers.tontine_expense} onChange={set("tontine_expense")} cur={cur} />
              <Money label="Cotisations sociales / assurances" value={numbers.social_contributions} onChange={set("social_contributions")} cur={cur} />
              <Money label="Soutien familial / transferts" value={numbers.family_support_expense} onChange={set("family_support_expense")} cur={cur} />
              <Money label="Autres obligations récurrentes" value={numbers.other_monthly_obligations} onChange={set("other_monthly_obligations")} cur={cur} />
              <Money label="Autres charges" value={numbers.other_household_expenses} onChange={set("other_household_expenses")} cur={cur} />
            </div>
            <div className="finance-recap">
              <RecapItem label="Total charges" value={formatMoney(recap.charges, cur)} />
              <RecapItem label="Reste à vivre mensuel (avant nouvelle échéance)" value={formatMoney(recap.disposable, cur)} strong />
              {recap.perCapita !== null && (
                <RecapItem
                  label={`Reste à vivre / personne (${(dependents ?? 0) + 1})`}
                  value={formatMoney(recap.perCapita, cur)}
                />
              )}
            </div>
            <p className="subsection-label">Patrimoine déclaré du ménage</p>
            <div className="form-grid two-col">
              <Money label="Épargne disponible" value={numbers.personal_savings} onChange={set("personal_savings")} cur={cur} />
              <Money label="Valeur immobilière nette" value={numbers.personal_real_estate_value} onChange={set("personal_real_estate_value")} cur={cur} />
              <Money label="Valeur des véhicules" value={numbers.personal_vehicle_value} onChange={set("personal_vehicle_value")} cur={cur} />
              <Money label="Actifs productifs" value={numbers.personal_productive_assets} onChange={set("personal_productive_assets")} cur={cur} />
            </div>
          </FormSection>

          {showStabilityBlock && (
          <FormSection
            id="fa-stability"
            icon={Landmark}
            title="Stabilité salariale et quotité cessible"
            description="Employeur, traçabilité du salaire, ancienneté et retenues à la source."
          >
            {detailText("employment_outlook", "Contrat, échéance du CDD, retraite, régularité de paiement et stabilité de l'employeur")}
            <div className="form-grid two-col">
              <Select label="Type d'emploi" value={analysisStr.employment_type} onChange={setAnalysis("employment_type")} options={EMPLOYMENT_TYPES} />
              <Text label="Employeur" value={analysisStr.employer_name} onChange={setAnalysis("employer_name")} />
              <Text label="Secteur de l'employeur" value={analysisStr.employer_sector} onChange={setAnalysis("employer_sector")} />
              <Money label="Retenues déjà prélevées à la source" value={numbers.salary_deductions} onChange={set("salary_deductions")} cur={cur} />
              <Money label="Ancienneté emploi / activité (mois)" value={numbers.employment_seniority_months} onChange={set("employment_seniority_months")} />
              <Money label="Pondération revenus informels (%)" value={numbers.informal_income_weight} onChange={set("informal_income_weight")} />
            </div>
            <div className="form-grid two-col">
              <Checkbox label="Salaire domicilié ou traçable en banque" checked={analysisBool.salary_paid_through_bank} onChange={toggleAnalysis("salary_paid_through_bank")} />
              <Checkbox label="Salaire vérifié sur bulletin ou relevé" checked={analysisBool.salary_verified} onChange={toggleAnalysis("salary_verified")} />
            </div>
            <p className="muted small">
              La base quotité cessible reprend le salaire net du demandeur
              (revenus du ménage). Pour un salarié/fonctionnaire, la quotité
              disponible est comparée à l&apos;échéance institution (hors
              épargne). Laisser la pondération vide pour le seuil filiale.
            </p>
          </FormSection>
          )}
        </>
      )}

        <FormSection
          id="fa-debt"
          icon={Landmark}
          title="Endettement dans une autre institution"
          description="Un crédit par institution ou banque. Ajoutez un bloc pour chaque crédit supplémentaire."
        >
        <div className="external-credit-list">
          {externalCredits.map((credit, index) => (
            <article className="external-credit" key={index}>
              <div className="external-credit-head">
                <h4>Crédit {index + 1}</h4>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={() => setExternalCredits((rows) => rows.filter((_, rowIndex) => rowIndex !== index))}
                >
                  Retirer
                </button>
              </div>
              <div className="form-grid two-col">
                <Text label="Institution de crédit" value={credit.institution} onChange={(value) => updateExternalCredit(index, { institution: value })} />
                <Money label="Date d'octroi" type="date" value={credit.grant_date} onChange={(value) => updateExternalCredit(index, { grant_date: value })} />
                <Money label="Date de la dernière échéance" type="date" value={credit.final_due_date} onChange={(value) => updateExternalCredit(index, { final_due_date: value })} />
                <Money label="Montant initial du crédit" value={credit.initial_amount} onChange={(value) => updateExternalCredit(index, { initial_amount: value })} cur={cur} />
                <Money label="Mensualité" value={credit.monthly_payment} onChange={(value) => updateExternalCredit(index, { monthly_payment: value })} cur={cur} />
                <Money label="Encours restant" value={credit.outstanding} onChange={(value) => updateExternalCredit(index, { outstanding: value })} cur={cur} />
                <Money label="Retard maximum constaté (jours)" value={credit.max_days_late} onChange={(value) => updateExternalCredit(index, { max_days_late: value })} />
                <Money label="Date de consultation" type="date" value={credit.bureau_date} onChange={(value) => updateExternalCredit(index, { bureau_date: value })} />
              </div>
              <div className="external-credit-checks">
                <Checkbox
                  label="Centrale des risques / BIC consultée"
                  checked={credit.bureau_checked === "yes"}
                  onChange={(checked) => updateExternalCredit(index, { bureau_checked: checked ? "yes" : "no" })}
                />
                <Checkbox
                  label="Incidents de paiement recensés"
                  checked={credit.incidents === "yes"}
                  onChange={(checked) => updateExternalCredit(index, { incidents: checked ? "yes" : "no" })}
                />
              </div>
              <label className="field">
                <span>Détails des incidents / engagements externes</span>
                <textarea
                  rows={2}
                  value={credit.incidents_detail}
                  onChange={(event) => updateExternalCredit(index, { incidents_detail: event.target.value })}
                />
              </label>
            </article>
          ))}
        </div>
        <button
          type="button"
          className="btn btn-ghost"
          onClick={() => setExternalCredits((rows) => [...rows, blankExternalCredit()])}
        >
          Ajouter un crédit
        </button>
        </FormSection>

        <FormSection
          id="fa-cycle"
          icon={Briefcase}
          title="Campagne et création"
          description="Deux cases sur l'activité déjà analysée. Ni un nouveau type de client, ni un second compte de résultat."
        >
          <Checkbox
            label="Cette activité suit une campagne (agriculture, élevage ou saison), pas un mois de vente ordinaire"
            checked={campaignOpen}
            onChange={(checked) => setDetails((current) => ({ ...current, campaign_open: checked ? "yes" : "no" }))}
          />
          {campaignOpen && <>
            <p className="muted small">Le surplus est les recettes de la campagne moins ses charges. Il est réparti sur la durée du crédit et devient la capacité retenue à la place d&apos;un mois de vente ordinaire. Les stocks ne sont pas des recettes. Une case vide reste vide ; si une seule des deux sommes est saisie, l&apos;autre compte pour zéro.</p>
            <div className="form-grid two-col">
              <Text label="Nom de la campagne" value={typeof details.campaign_name === "string" ? details.campaign_name : ""} onChange={(value) => setDetails((current) => ({ ...current, campaign_name: value }))} />
              <Text label="Culture, élevage ou transformation" value={typeof details.campaign_production === "string" ? details.campaign_production : ""} onChange={(value) => setDetails((current) => ({ ...current, campaign_production: value }))} />
              <Text label="Surface, cheptel ou volume" value={typeof details.campaign_scale === "string" ? details.campaign_scale : ""} onChange={(value) => setDetails((current) => ({ ...current, campaign_scale: value }))} />
              <Text label="Mois où l'argent entre" value={typeof details.campaign_inflow_months === "string" ? details.campaign_inflow_months : ""} onChange={(value) => setDetails((current) => ({ ...current, campaign_inflow_months: value }))} />
            </div>
            {detailText("campaign_calendar", "Calendrier : quand les intrants sont payés, quand la récolte est vendue, et quels mois restent sans entrée")}
            {detailText("campaign_sales", "Débouchés et prix : acheteurs, marché, prix retenu et ce qui le justifie")}
            <div className="form-grid two-col">
              <Money label="Stock d'intrants" value={typeof details.campaign_input_stock === "string" ? details.campaign_input_stock : ""} onChange={(value) => setDetails((current) => ({ ...current, campaign_input_stock: value }))} cur={cur} />
              <Money label="Stock de récolte" value={typeof details.campaign_harvest_stock === "string" ? details.campaign_harvest_stock : ""} onChange={(value) => setDetails((current) => ({ ...current, campaign_harvest_stock: value }))} cur={cur} />
              <Money label="Recettes de la campagne" value={typeof details.campaign_revenue === "string" ? details.campaign_revenue : ""} onChange={(value) => setDetails((current) => ({ ...current, campaign_revenue: value }))} cur={cur} />
              <Money label="Charges de la campagne" value={typeof details.campaign_charges === "string" ? details.campaign_charges : ""} onChange={(value) => setDetails((current) => ({ ...current, campaign_charges: value }))} cur={cur} />
            </div>
            {detailText("campaign_comment", "Pertes, invendus, climat, prix et ce qui peut empêcher le surplus d'arriver")}
            <div className="finance-recap">
              <RecapItem label="Surplus de la campagne" value={formatMoney(campaignSurplus, cur)} />
              <RecapItem label="Durée du crédit" value={application.duration_months ? `${application.duration_months} mois` : "—"} />
              <RecapItem label="Surplus retenu par mois" value={formatMoney(campaignMonthly, cur)} strong />
              <RecapItem label="Stock d'intrants, hors revenu" value={formatMoney(campaignAmount("campaign_input_stock"), cur)} />
              <RecapItem label="Stock de récolte, hors revenu" value={formatMoney(campaignAmount("campaign_harvest_stock"), cur)} />
            </div>
            <p className="muted small">Le taux d&apos;endettement continue de lire le revenu déjà observé. Seule la capacité de remboursement retient ce surplus mensuel. Pour un groupement, il s&apos;ajoute aux cotisations nettes et remplace la marge d&apos;activité. L&apos;épargne collective n&apos;est pas ajoutée.</p>
          </>}
          <Checkbox
            label="Activité en création : pas d'historique d'exploitation à exiger"
            checked={creationOpen}
            onChange={(checked) => setDetails((current) => ({ ...current, activity_creation: checked ? "yes" : "no" }))}
          />
          {creationOpen && <>
            <p className="muted small">Le coût du projet, l&apos;apport et la quotité sont ceux du dossier. Ils ne sont pas ressaisis ici. Le chiffre d&apos;affaires passé n&apos;est pas exigé. Le DSCR s&apos;appuie sur les encaissements et les sorties prévisionnels, pas sur cet historique.</p>
            <div className="finance-recap">
              <RecapItem label="Coût total du projet" value={application.project_total_cost == null || application.project_total_cost === "" ? "—" : formatMoney(application.project_total_cost, cur)} />
              <RecapItem label="Apport personnel" value={application.personal_contribution == null || application.personal_contribution === "" ? "—" : formatMoney(application.personal_contribution, cur)} />
              <RecapItem label="Montant du dossier" value={formatMoney(application.amount_proposed || application.amount_requested, cur)} />
              <RecapItem label="Quotité financée" value={application.financed_quota == null || application.financed_quota === "" ? "—" : `${application.financed_quota} %`} />
              <RecapItem label="Date de création de l'activité" value={application.activity_start_date ? formatDate(application.activity_start_date) : "—"} />
            </div>
            {detailText("creation_activity", "Ce qui est créé : activité, investissement, lieu et ce qui existe déjà")}
            {detailText("creation_ramp", "Délai avant les premières recettes, et comment les échéances sont couvertes pendant ce délai")}
            {detailText("creation_assumptions", "Hypothèses de la prévision : volumes, prix, charges et ce qui les rend tenables")}
          </>}
        </FormSection>

        <FormSection
          id="fa-treasury"
          icon={Wallet}
          title="Capacité et retenue de prudence"
          description="La capacité est comparée au service de la dette. La retenue vient ensuite, sans remplacer le taux d'endettement."
        >
        {(isCorporate || showActivityBlock) && <TpeReconstitution details={details} onChange={setDetails} currency={cur} part="safety" />}
        {creationOpen && <p className="muted small">Activité en création : ce solde prévisionnel porte le DSCR. Le chiffre d&apos;affaires passé ne le remplace pas. Sans encaissement ni sortie, l&apos;enregistrement du dossier est refusé.</p>}
        <div className="form-grid two-col">
          <Money label="Encaissements prévisionnels mensuels" value={numbers.projected_monthly_inflows} onChange={set("projected_monthly_inflows")} cur={cur} />
          <Money label="Sorties de trésorerie prévisionnelles mensuelles" value={numbers.projected_monthly_outflows} onChange={set("projected_monthly_outflows")} cur={cur} />
        </div>
        <div className="finance-recap">
          <RecapItem label="Solde de trésorerie prévisionnel mensuel" value={formatMoney(recap.surplus, cur)} strong />
        </div>
        <label className="field">
          <span>Commentaire sur les hypothèses de trésorerie (flux hors service de la dette)</span>
          <textarea
            rows={2}
            value={cashflowComment}
            onChange={(e) => setCashflowComment(e.target.value)}
          />
        </label>
        {detailTable("cashflow")}
        {supplements(["opening_cash_balance"])}
        <p className="muted small">Le solde d'ouverture est celui précédant le premier mois saisi. Renseignez tous les mois successifs pour obtenir une trésorerie cumulée. Les sorties et services de dette détaillés doivent correspondre aux échéances réelles, épargne obligatoire comprise.</p>
        {purposeText && <p className="muted small">{purposeText}</p>}
        {supplements(["purchase_stress_pct", ...((isCorporate || operatingPurpose) ? ["receivable_delay_days"] : [])], operatingPurpose ? ["receivable_delay_days"] : [])}
        {investmentPurpose && path !== "RECONSTITUTED" && supplements(["maintenance_investment"])}
        {detailText("seasonality", "Saisonnalité : mois creux, récoltes, campagnes et remboursement adapté")}
        {detailText("stress_assumptions", "Scénarios défavorables : baisse des revenus, hausse des achats, retards clients et mesures d'atténuation")}
        {detailText("project_cost", "Coût du projet : besoins, investissements et justificatifs / devis")}
        {detailText("own_contribution", "Apport propre : montant, origine et disponibilité vérifiée")}
        {detailText("financing_plan", "Plan de financement : besoins, ressources et adéquation durée / objet")}
        </FormSection>

        {minimalCashVisible && <FormSection
          id="fa-minimal"
          icon={UploadCloud}
          title="Trésorerie minimale"
          description="Document court, à part des états financiers et de la reconstitution des ventes."
        >
          <p className="muted small">Une période, un document. Quatre lignes : trésorerie d&apos;ouverture, entrées, sorties, trésorerie de clôture. Ce document ne remplace pas les fiches, la caisse depuis le dernier achat, ni les états. Il n&apos;alimente pas les ratios. Une case vide reste vide.</p>
          <Checkbox
            label="Ce client n'a qu'un suivi de trésorerie minimale"
            checked={minimalCashOpen}
            onChange={(checked) => setDetails((current) => ({ ...current, minimal_cash_open: checked ? "yes" : "no" }))}
          />
          {minimalCashOpen && <>
            <div className="form-grid two-col">
              <Text label="Intitulé de la période" value={typeof details.minimal_cash_label === "string" ? details.minimal_cash_label : ""} onChange={(value) => setDetails((current) => ({ ...current, minimal_cash_label: value }))} />
              <label className="field">
                <span>Début</span>
                <input type="date" value={typeof details.minimal_cash_start === "string" ? details.minimal_cash_start : ""} onChange={(event) => setDetails((current) => ({ ...current, minimal_cash_start: event.target.value }))} />
              </label>
              <label className="field">
                <span>Fin</span>
                <input type="date" value={typeof details.minimal_cash_end === "string" ? details.minimal_cash_end : ""} onChange={(event) => setDetails((current) => ({ ...current, minimal_cash_end: event.target.value }))} />
              </label>
            </div>
            <div className="form-grid two-col">
              <Money label="Trésorerie d'ouverture" value={typeof details.minimal_cash_opening === "string" ? details.minimal_cash_opening : ""} onChange={(value) => setDetails((current) => ({ ...current, minimal_cash_opening: value }))} cur={cur} signed />
              <Money label="Entrées" value={typeof details.minimal_cash_inflows === "string" ? details.minimal_cash_inflows : ""} onChange={(value) => setDetails((current) => ({ ...current, minimal_cash_inflows: value }))} cur={cur} />
              <Money label="Sorties" value={typeof details.minimal_cash_outflows === "string" ? details.minimal_cash_outflows : ""} onChange={(value) => setDetails((current) => ({ ...current, minimal_cash_outflows: value }))} cur={cur} />
              <Money label="Trésorerie de clôture" value={typeof details.minimal_cash_closing === "string" ? details.minimal_cash_closing : ""} onChange={(value) => setDetails((current) => ({ ...current, minimal_cash_closing: value }))} cur={cur} signed />
            </div>
            <div className="finance-recap">
              <RecapItem label="Surplus de la période" value={formatMoney(minimalSurplus, cur)} strong />
              <RecapItem label="Clôture calculée" value={formatMoney(minimalTheoretical, cur)} />
              <RecapItem label="Écart, clôture lue − clôture calculée" value={formatMoney(minimalGap, cur)} />
            </div>
            {minimalGap != null && minimalGap !== 0 && <p className="form-error">L&apos;écart doit être expliqué dans le commentaire avant la soumission du dossier. Il ne corrige pas les lignes.</p>}
            {detailText("minimal_cash_comment", "Commentaire : ce que couvre la période, et l'écart s'il y en a un")}
            <label className="field">
              <span>Document unique de la période</span>
              <input type="file" onChange={(event) => setMinimalCashFile(event.target.files?.[0] ?? null)} />
              {typeof details.minimal_cash_document === "string" && details.minimal_cash_document && <small className="muted">Un document est déjà joint. Un nouveau fichier le remplace.</small>}
            </label>
          </>}
        </FormSection>}

        {(isCorporate || showActivityBlock) && (
        <FormSection
          id="fa-trend"
          icon={Gauge}
          title="Bilan, caisse et tendance N-1"
          description="Patrimoine, contrôle depuis le dernier achat, puis comparaison avec la période précédente."
        >
          {!isCorporate && (
            <>
              <p className="subsection-label">Bilan de l'activité</p>
              <div className="form-grid two-col">
                <Money label="Stock" value={numbers.activity_stock_value} onChange={set("activity_stock_value")} cur={cur} />
                <Money label="Créances clients" value={numbers.activity_receivables} onChange={set("activity_receivables")} cur={cur} />
                <Money label="Trésorerie disponible" value={numbers.activity_cash_available} onChange={set("activity_cash_available")} cur={cur} />
                <Money label="Actifs productifs" value={numbers.activity_fixed_assets} onChange={set("activity_fixed_assets")} cur={cur} />
                <Money label="Dettes fournisseurs" value={numbers.activity_supplier_debt} onChange={set("activity_supplier_debt")} cur={cur} />
              </div>
            </>
          )}
          <TpeReconstitution details={details} onChange={setDetails} currency={cur} part="cash" />
          <div className="form-grid two-col">
            <Money label="Chiffre d'affaires N-1" value={numbers.turnover_prev} onChange={set("turnover_prev")} cur={cur} />
            <Money label="Résultat net N-1" value={numbers.net_result_prev} onChange={set("net_result_prev")} cur={cur} signed />
          </div>
          {detailTable("history")}
          <p className="muted small">Les variations sont calculées sur des périodes de même durée. Pour une activité, le bilan ci-dessus est celui de l'exploitation ; le bilan d'entreprise reste dans sa section dédiée.</p>
        </FormSection>
        )}

        <FormSection
          id="fa-collateral"
          icon={Shield}
          title="Garanties et cautions"
          description="Couverture, qualité et formalisation des piliers de sûreté."
        >
          <CollateralSummaryCard
            applicationId={application.id}
            currency={cur}
          />
          {detailTable("references")}
        </FormSection>

        {(isCorporate || isGroupement || showActivityBlock || configuration.data?.protected_analysis_sections?.includes("fa-sector")) && (
        <FormSection
          id="fa-sector"
          icon={Factory}
          title="Analyse sectorielle"
          description="Positionnement, marché et facteurs de risque du secteur (informatif)."
        >
        <div className="form-grid two-col">
          <Select label="Secteur d'activité" value={esStr.sector} onChange={setStr("sector")} options={toOptions(FINANCE_LABELS.sector)} />
          <Text label="Sous-secteur / filière" value={esStr.sub_sector} onChange={setStr("sub_sector")} />
          <Select label="Position dans la chaîne de valeur" value={esStr.value_chain_position} onChange={setStr("value_chain_position")} options={toOptions(FINANCE_LABELS.value_chain_position)} />
          <Select label="Dynamique du marché" value={esStr.market_dynamic} onChange={setStr("market_dynamic")} options={toOptions(FINANCE_LABELS.market_dynamic)} />
          <Select label="Intensité de la saisonnalité" value={esStr.seasonality_level} onChange={setStr("seasonality_level")} options={toOptions(FINANCE_LABELS.risk_level)} />
          <Select label="Intensité concurrentielle" value={esStr.competition_intensity} onChange={setStr("competition_intensity")} options={toOptions(FINANCE_LABELS.risk_level)} />
          <Select label="Dépendance aux fournisseurs" value={esStr.supplier_dependency} onChange={setStr("supplier_dependency")} options={toOptions(FINANCE_LABELS.risk_level)} />
          <Select label="Concentration de la clientèle" value={esStr.client_concentration} onChange={setStr("client_concentration")} options={toOptions(FINANCE_LABELS.risk_level)} />
          <Select label="Sensibilité au prix des intrants" value={esStr.input_price_sensitivity} onChange={setStr("input_price_sensitivity")} options={toOptions(FINANCE_LABELS.risk_level)} />
          <Select label="Exposition aux devises / imports" value={esStr.fx_exposure} onChange={setStr("fx_exposure")} options={toOptions(FINANCE_LABELS.risk_level)} />
          <Select label="Sensibilité réglementaire / fiscale" value={esStr.regulatory_sensitivity} onChange={setStr("regulatory_sensitivity")} options={toOptions(FINANCE_LABELS.risk_level)} />
          <Select label="Sensibilité climatique" value={esStr.climate_sensitivity} onChange={setStr("climate_sensitivity")} options={toOptions(FINANCE_LABELS.risk_level)} />
          <Select label="Niveau de risque sectoriel global" value={esStr.sector_risk_level} onChange={setStr("sector_risk_level")} options={toOptions(FINANCE_LABELS.risk_level)} />
        </div>
        <label className="field">
          <span>Perspectives du secteur</span>
          <textarea rows={2} value={esStr.sector_outlook} onChange={(e) => setStr("sector_outlook")(e.target.value)} />
        </label>
        <label className="field">
          <span>Commentaire sectoriel</span>
          <textarea rows={2} value={esStr.sector_comment} onChange={(e) => setStr("sector_comment")(e.target.value)} />
        </label>
        </FormSection>
        )}

        {(isCorporate || isGroupement || showActivityBlock || configuration.data?.protected_analysis_sections?.includes("fa-es")) && (
        <FormSection
          id="fa-es"
          icon={Leaf}
          title="Analyse environnementale & sociale (E&S)"
          description="Conformité, impacts environnementaux et sociaux (informatif)."
        >
        <div className="form-grid two-col">
          <Select label="Catégorie de risque E&S" value={esStr.es_category} onChange={setStr("es_category")} options={toOptions(FINANCE_LABELS.es_category)} />
          <Text label="Référence de l'autorisation" value={esStr.permit_reference} onChange={setStr("permit_reference")} />
        </div>
        <p className="subsection-label">Conformité & autorisations</p>
        <div className="form-grid two-col">
          <Checkbox label="Activité hors liste d'exclusion" checked={esBool.exclusion_list_ok} onChange={toggle("exclusion_list_ok")} />
          <Checkbox label="Conformité réglementaire E&S" checked={esBool.es_regulatory_compliance} onChange={toggle("es_regulatory_compliance")} />
          <Checkbox label="Autorisation environnementale requise" checked={esBool.env_permit_required} onChange={toggle("env_permit_required")} />
          <Checkbox label="Autorisation obtenue" checked={esBool.env_permit_obtained} onChange={toggle("env_permit_obtained")} />
          <Checkbox label="Étude d'impact (EIE) requise" checked={esBool.eia_required} onChange={toggle("eia_required")} />
          <Checkbox label="Étude d'impact (EIE) réalisée" checked={esBool.eia_done} onChange={toggle("eia_done")} />
        </div>
        <p className="subsection-label">Impacts environnementaux</p>
        <div className="form-grid two-col">
          <Select label="Gestion des déchets / effluents" value={esStr.waste_management} onChange={setStr("waste_management")} options={toOptions(FINANCE_LABELS.quality_level)} />
          <Select label="Usage eau / énergie" value={esStr.resource_use} onChange={setStr("resource_use")} options={toOptions(FINANCE_LABELS.quality_level)} />
          <Select label="Produits chimiques / pesticides" value={esStr.chemicals_pesticides} onChange={setStr("chemicals_pesticides")} options={toOptions(FINANCE_LABELS.quality_level)} />
          <Select label="Nuisances / émissions / pollution" value={esStr.nuisances_emissions} onChange={setStr("nuisances_emissions")} options={toOptions(FINANCE_LABELS.quality_level)} />
        </div>
        <p className="subsection-label">Impacts sociaux</p>
        <div className="form-grid two-col">
          <Select label="Conditions de travail" value={esStr.working_conditions} onChange={setStr("working_conditions")} options={toOptions(FINANCE_LABELS.quality_level)} />
          <Select label="Sécurité & santé au travail" value={esStr.occupational_safety} onChange={setStr("occupational_safety")} options={toOptions(FINANCE_LABELS.quality_level)} />
          <Select label="Risque travail des enfants / forcé" value={esStr.child_forced_labor_risk} onChange={setStr("child_forced_labor_risk")} options={toOptions(FINANCE_LABELS.risk_level)} />
          <Select label="Impact sur les communautés" value={esStr.community_impact} onChange={setStr("community_impact")} options={toOptions(FINANCE_LABELS.quality_level)} />
          <Select label="Enjeux fonciers / réinstallation" value={esStr.land_resettlement_risk} onChange={setStr("land_resettlement_risk")} options={toOptions(FINANCE_LABELS.risk_level)} />
        </div>
        <p className="subsection-label">Emplois & impact social</p>
        <div className="form-grid two-col">
          <Money label="Effectif actuel (nb employés)" value={numbers.workforce_count} onChange={set("workforce_count")} />
          <Money label="Emplois créés" value={numbers.jobs_created} onChange={set("jobs_created")} />
          <Money label="Emplois maintenus" value={numbers.jobs_maintained} onChange={set("jobs_maintained")} />
          <Money label="dont emplois féminins" value={numbers.jobs_women} onChange={set("jobs_women")} />
          <Money label="dont emplois jeunes" value={numbers.jobs_youth} onChange={set("jobs_youth")} />
        </div>
        <p className="subsection-label">Atténuation & synthèse</p>
        <div className="form-grid two-col">
          <Checkbox label="Plan d'action E&S exigé" checked={esBool.es_action_required} onChange={toggle("es_action_required")} />
          <Checkbox label="Assurances E&S (pollution / RC)" checked={esBool.es_insurance} onChange={toggle("es_insurance")} />
          <Select label="Niveau de risque E&S global" value={esStr.es_risk_level} onChange={setStr("es_risk_level")} options={toOptions(FINANCE_LABELS.risk_level)} />
        </div>
        <label className="field">
          <span>Plan d'action / mesures d'atténuation (PGES)</span>
          <textarea rows={2} value={esStr.es_mitigation_plan} onChange={(e) => setStr("es_mitigation_plan")(e.target.value)} />
        </label>
        <label className="field">
          <span>Commentaire E&S</span>
          <textarea rows={2} value={esStr.es_comment} onChange={(e) => setStr("es_comment")(e.target.value)} />
        </label>
        </FormSection>
        )}

        <FormSection
          id="fa-conclusion"
          icon={Calculator}
          title="Conclusion de l'analyste"
          description="Recommandation, synthèse structurée et pièces justificatives."
        >
        <div className="form-grid two-col">
          <Select
            label="Recommandation (obligatoire pour soumettre)"
            value={recommendation}
            onChange={setRecommendation}
            options={RECOMMENDATIONS}
          />
        </div>
        <div className="form-grid two-col">
          <label className="field">
            <span>Points forts</span>
            <textarea
              rows={3}
              value={strengths}
              onChange={(e) => setStrengths(e.target.value)}
              placeholder="Atouts du dossier (capacité, garanties, historique…)"
            />
          </label>
          <label className="field">
            <span>Points de vigilance</span>
            <textarea
              rows={3}
              value={weaknesses}
              onChange={(e) => setWeaknesses(e.target.value)}
              placeholder="Risques identifiés, faiblesses…"
            />
          </label>
        </div>
        <label className="field">
          <span>Conditions / recommandations proposées</span>
          <textarea
            rows={2}
            value={conditions}
            onChange={(e) => setConditions(e.target.value)}
            placeholder="Garanties additionnelles, plafond, périodicité…"
          />
        </label>
        {application.purpose_type === "OTHER" && <p className="muted small">{purposeTestText("OTHER")}</p>}
        <label className="field">
          <span>Avis / commentaire de synthèse</span>
          <textarea
            rows={4}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder={application.purpose_type === "OTHER" ? "Épreuve retenue pour cet objet, et conclusion" : "Conclusion générale de l'analyste…"}
          />
        </label>
        <p className="muted small">
          Le score interne (/100) est calculé automatiquement à partir de la
          grille de notation pondérée (capacité, endettement, structure,
          garanties, historique).
        </p>
        {detailText("monitoring_plan", "Suivi proposé : pièces à actualiser, fréquence des visites, indicateurs et engagements à surveiller")}
        <MultiFileField
          label="Pièces justificatives (bulletins, états financiers, relevés…)"
          files={docs}
          onChange={setDocs}
          existing={initial?.documents}
        />
        </FormSection>

        {!!configuration.data?.forms?.analysis_fields.length && <FormSection id="fa-custom" icon={FileText} title="Informations complémentaires"><CustomFields definitions={configuration.data.forms.analysis_fields} value={customFields} onChange={setCustomFields} /></FormSection>}
        {error && <div className="form-error" style={{ order: 100000 }}>{error}</div>}
        <div className="credit-form-actions" style={{ order: 100001 }}>
          <Link className="btn btn-ghost" to={backTo}>
            Annuler
          </Link>
          <button className="btn btn-primary" disabled={mutation.isPending}>
            {mutation.isPending
              ? "Enregistrement…"
              : mode === "edit"
                ? "Enregistrer les modifications"
                : "Enregistrer l'analyse"}
          </button>
        </div>
      </AnalysisContent>
    </form>
    </AnalysisPathContext.Provider>
    </AnalysisLayoutContext.Provider>
  );
}

function AnalysisContent({ children }: { children: ReactNode }) {
  const sections = useContext(AnalysisLayoutContext);
  const flattened: ReactNode[] = [];
  function flatten(nodes: ReactNode) {
    Children.forEach(nodes, (child) => {
      if (isValidElement<{ children?: ReactNode }>(child) && child.type === Fragment) flatten(child.props.children);
      else if (child != null && child !== false) flattened.push(child);
    });
  }
  flatten(children);
  if (!sections.length) return <div className="credit-form-main stack">{children}</div>;
  const sectionId = (child: ReactNode) => isValidElement<{ id?: string }>(child) && child.type === FormSection ? child.props.id : undefined;
  const first = flattened.findIndex((child) => sectionId(child));
  const ordered = flattened.map((child, index) => ({ child, index })).sort((left, right) => {
    const rank = (entry: { child: ReactNode; index: number }) => {
      const id = sectionId(entry.child);
      if (!id) return entry.index < first ? -1000 + entry.index : 10000 + entry.index;
      const position = sections.findIndex((section) => section.id === id);
      return position < 0 ? sections.length : position;
    };
    return rank(left) - rank(right);
  });
  return <div className="credit-form-main stack">{ordered.map(({ child, index }) => <Fragment key={sectionId(child) || `extra-${index}`}>{child}</Fragment>)}</div>;
}

function FormSection({
  id,
  icon: Icon,
  title,
  description,
  children,
}: {
  id: string;
  icon: LucideIcon;
  title: string;
  description?: string;
  children: ReactNode;
}) {
  const sections = useContext(AnalysisLayoutContext);
  const path = useContext(AnalysisPathContext);
  if (!sectionAllowed(id, path)) return null;
  const index = sections.findIndex((section) => section.id === id);
  if (index >= 0 && !sections[index].visible) return null;
  const fallbackOrder: Record<string, number> = {
    "fa-params": 10, "fa-quality": 20, "fa-debt": 30, "fa-income": 40, "fa-stability": 50,
    "fa-group": 60, "fa-business": 70, "fa-statements": 85, "fa-activity": 80, "fa-exploitation": 90,
    "fa-charges": 100, "fa-cycle": 105, "fa-treasury": 110, "fa-balance": 120, "fa-minimal": 125, "fa-trend": 130,
    "fa-collateral": 140, "fa-sector": 150, "fa-es": 160, "fa-conclusion": 170,
  };
  return (
    <section id={id} className="card form-section" style={sections.length ? undefined : { order: fallbackOrder[id] ?? 0 }}>
      <div className="card-title form-section-head">
        <span className="form-section-icon">
          <Icon size={18} />
        </span>
        <div className="form-section-heading">
          <span className="form-section-title">{title}</span>
          {description && (
            <span className="form-section-desc">{description}</span>
          )}
        </div>
      </div>
      <div className="card-body">{children}</div>
    </section>
  );
}

function RecapItem({
  label,
  value,
  strong,
}: {
  label: string;
  value: string;
  strong?: boolean;
}) {
  return (
    <div className={`recap-item${strong ? " strong" : ""}`}>
      <span className="recap-label">{label}</span>
      <span className="recap-value">{value}</span>
    </div>
  );
}

function Money({
  label,
  value,
  onChange,
  type = "number",
  signed = false,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  cur?: string;
  signed?: boolean;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      <input
        type={type}
        min={type === "number" && !signed ? 0 : undefined}
        step={type === "number" ? "any" : undefined}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}

function Text({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}

function Checkbox({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="field checkbox-field">
      <span className="checkbox-inline">
        <input
          type="checkbox"
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
        />
        {label}
      </span>
    </label>
  );
}

function Select({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <label className="field">
      <span>{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">— Sélectionner —</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function MultiFileField({
  label,
  files,
  onChange,
  existing,
}: {
  label: string;
  files: File[];
  onChange: (f: File[]) => void;
  existing?: FinancialAnalysis["documents"];
}) {
  return (
    <label className="field file-field">
      <span>
        <Images size={14} style={{ verticalAlign: "-2px", marginRight: 4 }} />
        {label}
      </span>
      {existing && existing.length > 0 && (
        <div className="doc-row" style={{ marginBottom: 8 }}>
          {existing.map((d) => (
            <a key={d.id} className="doc-chip" href={d.file} target="_blank" rel="noreferrer">
              <ExternalLink size={13} />
              {d.label || "Document"}
            </a>
          ))}
        </div>
      )}
      <div className={`file-drop${files.length ? " has-file" : ""}`}>
        <UploadCloud size={18} />
        <span className="file-name">
          {files.length
            ? `${files.length} fichier(s) sélectionné(s)`
            : "Ajouter des documents…"}
        </span>
        <input
          type="file"
          accept="image/*,application/pdf"
          multiple
          onChange={(e) => onChange(Array.from(e.target.files ?? []))}
        />
      </div>
    </label>
  );
}
