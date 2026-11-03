import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Briefcase,
  Building2,
  Calculator,
  ExternalLink,
  Factory,
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
  useEffect,
  useMemo,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import { Link } from "react-router-dom";

import { api } from "@/api/client";
import {
  FINANCE_LABELS,
  type CreditApplication,
  type FinancialAnalysis,
} from "@/api/types";
import { formatMoney } from "@/components/ui";
import { CollateralSummaryCard } from "@/components/CollateralSummaryCard";

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
  "informal_income_weight",
  // Entreprise — exploitation
  "turnover", "cogs", "op_rent", "op_salaries", "op_utilities",
  "op_transport", "op_telecom", "op_taxes", "op_maintenance", "op_other",
  "depreciation", "financial_charges",
  // Entreprise — bilan
  "stock_value", "receivables", "cash_available", "fixed_assets",
  "supplier_debt", "ongoing_credit_balance", "short_term_debt",
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
  "members_count", "active_contributing_members",
  "collective_contributions", "collective_savings",
  "collective_other_income", "collective_operating_expenses",
  "group_activity_turnover", "group_activity_expenses",
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
  const [debtInstitution, setDebtInstitution] = useState(
    initial?.existing_debt_institution || "",
  );
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
  const [creditBureauChecked, setCreditBureauChecked] = useState(
    initial?.credit_bureau_checked ?? false,
  );
  const [creditBureauDate, setCreditBureauDate] = useState(
    initial?.credit_bureau_date || "",
  );
  const [hasIncidents, setHasIncidents] = useState(
    initial?.has_payment_incidents ?? false,
  );
  const [incidentsComment, setIncidentsComment] = useState(
    initial?.incidents_comment || "",
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
  const setStr = (k: string) => (v: string) =>
    setEsStr((p) => ({ ...p, [k]: v }));
  const toggle = (k: string) => (v: boolean) =>
    setEsBool((p) => ({ ...p, [k]: v }));
  const [docs, setDocs] = useState<File[]>([]);
  const dependents = application.dependents_count;

  const [hasSideActivity, setHasSideActivity] = useState(
    Boolean((initial as { has_side_activity?: boolean } | undefined)?.has_side_activity),
  );
  const [individualProfile, setIndividualProfile] = useState<IndividualProfile>(
    () => inferIndividualProfile(initial),
  );
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

  const navSections = useMemo(
    () =>
      [
        { id: "fa-params", icon: Gauge, label: "Paramètres", show: true },
        { id: "fa-exploitation", icon: ReceiptText, label: "Compte d'exploitation", show: isCorporate },
        { id: "fa-balance", icon: Building2, label: "Bilan simplifié", show: isCorporate },
        { id: "fa-trend", icon: Gauge, label: "Tendance (N-1)", show: isCorporate },
        { id: "fa-income", icon: Wallet, label: "Revenus du ménage", show: isIndividual },
        {
          id: "fa-activity",
          icon: Store,
          label:
            individualProfile === "INDEPENDANT"
              ? "Activité"
              : "Activité génératrice de revenus",
          show: isIndividual && (showActivityBlock || individualProfile === "SALARIE"),
        },
        { id: "fa-charges", icon: ReceiptText, label: "Charges du ménage", show: isIndividual },
        { id: "fa-stability", icon: Landmark, label: "Stabilité & quotité", show: showStabilityBlock },
        { id: "fa-group", icon: Users, label: "Groupement", show: isGroupement },
        { id: "fa-collateral", icon: Shield, label: "Garanties & cautions", show: true },
        { id: "fa-treasury", icon: Wallet, label: "Trésorerie prévisionnelle", show: true },
        { id: "fa-debt", icon: Landmark, label: "Endettement & historique", show: true },
        { id: "fa-sector", icon: Factory, label: "Analyse sectorielle", show: isCorporate || isGroupement },
        { id: "fa-es", icon: Leaf, label: "Analyse E&S", show: isCorporate || isGroupement },
        { id: "fa-conclusion", icon: Calculator, label: "Conclusion", show: true },
      ].filter((s) => s.show),
    [
      isCorporate,
      isIndividual,
      isGroupement,
      individualProfile,
      showActivityBlock,
      showStabilityBlock,
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
    const ebe = gross - opex;
    const net = ebe - val("depreciation") - val("financial_charges");
    const cashFlow = net + val("depreciation");
    const assets =
      val("stock_value") + val("receivables") + val("cash_available") +
      val("fixed_assets");
    const debts = val("supplier_debt") + val("ongoing_credit_balance");
    // Particulier
    let income =
      val("salary_income") + val("spouse_income") + val("rental_income") +
      val("other_activity_income") + val("other_income");
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
      val("family_support_expense");
    const disposable = income - charges - val("existing_debt_monthly");
    return {
      gross, opex, ebe, net, cashFlow,
      equity: assets - debts,
      bfr: val("stock_value") + val("receivables") - val("supplier_debt"),
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
  }, [numbers, isCorporate, dependents, individualProfile, hasSideActivity]);

  const mutation = useMutation({
    mutationFn: async () => {
      const fd = new FormData();
      if (mode === "create") fd.append("application", application.id);
      for (const key of NUMERIC_KEYS) {
        const v = numbers[key].trim();
        if (v !== "") fd.append(key, v);
      }
      fd.append("reference_period", period);
      fd.append("is_reference", String(isReference));
      fd.append("existing_debt_institution", debtInstitution);
      fd.append("cashflow_comment", cashflowComment);
      fd.append("credit_bureau_checked", String(creditBureauChecked));
      if (creditBureauDate) fd.append("credit_bureau_date", creditBureauDate);
      fd.append("has_payment_incidents", String(hasIncidents));
      fd.append("incidents_comment", incidentsComment);
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
        if (v) fd.append(k, v);
      }
      for (const k of ES_BOOL_KEYS) fd.append(k, String(esBool[k]));
      if (recommendation) fd.append("recommendation", recommendation);
      if (analysisDate) fd.append("analysis_date", analysisDate);
      fd.append("comment", comment);
      for (const d of docs) fd.append("documents", d);
      if (mode === "edit" && analysisId) {
        return (await api.patch(`/financial-analyses/${analysisId}/`, fd)).data;
      }
      return (await api.post("/financial-analyses/", fd)).data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["financial-analysis"] });
      qc.invalidateQueries({ queryKey: ["credit-application"] });
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
    setError(null);
    mutation.mutate();
  }

  return (
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

      <div className="credit-form-main stack">
        <FormSection
          id="fa-params"
          icon={Gauge}
          title="Paramètres de l'analyse"
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
          <p className="muted small" style={{ marginBottom: 0 }}>
            Tous les montants doivent être exprimés sur cette période (
            {FINANCE_LABELS.reference_period[period]}). Défaut :{" "}
            {isCorporate
              ? "annuelle (personne morale)"
              : isGroupement
                ? "mensuelle (groupement)"
                : "mensuelle (personne physique)"}
            .
          </p>
        </FormSection>

      {isCorporate ? (
        <>
          <FormSection
            id="fa-exploitation"
            icon={ReceiptText}
            title="Compte d'exploitation"
            description="Produits et charges d'exploitation de l'entreprise."
          >
            <div className="form-grid two-col">
              <Money label="Chiffre d'affaires" value={numbers.turnover} onChange={set("turnover")} cur={cur} />
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
          </FormSection>

          <FormSection
            id="fa-balance"
            icon={Building2}
            title="Bilan simplifié"
            description="Actifs, dettes court terme et structure financière."
          >
            <div className="form-grid two-col">
              <Money label="Stock" value={numbers.stock_value} onChange={set("stock_value")} cur={cur} />
              <Money label="Créances clients" value={numbers.receivables} onChange={set("receivables")} cur={cur} />
              <Money label="Trésorerie (caisse + banque)" value={numbers.cash_available} onChange={set("cash_available")} cur={cur} />
              <Money label="Immobilisations" value={numbers.fixed_assets} onChange={set("fixed_assets")} cur={cur} />
              <Money label="Dettes fournisseurs" value={numbers.supplier_debt} onChange={set("supplier_debt")} cur={cur} />
              <Money label="Autres dettes court terme (fiscales, sociales…)" value={numbers.short_term_debt} onChange={set("short_term_debt")} cur={cur} />
            </div>
            <div className="finance-recap">
              <RecapItem label="Capitaux propres" value={formatMoney(recap.equity, cur)} strong />
              <RecapItem label="BFR" value={formatMoney(recap.bfr, cur)} />
            </div>
          </FormSection>

          <FormSection
            id="fa-trend"
            icon={Gauge}
            title="Tendance (exercice N-1)"
            description="Comparaison avec l'exercice précédent pour apprécier la dynamique."
          >
            <div className="form-grid two-col">
              <Money label="Chiffre d'affaires N-1" value={numbers.turnover_prev} onChange={set("turnover_prev")} cur={cur} />
              <Money label="Résultat net N-1" value={numbers.net_result_prev} onChange={set("net_result_prev")} cur={cur} />
            </div>
            <p className="muted small">
              Les taux de croissance du CA et du résultat sont calculés
              automatiquement pour apprécier la dynamique de l'activité.
            </p>
          </FormSection>
        </>
      ) : isGroupement ? (
        <FormSection
          id="fa-group"
          icon={Users}
          title="Analyse groupement"
          description="Composition, cotisations, capacité collective et activité commune éventuelle."
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
            <Money
              label="CA activité commune (si applicable)"
              value={numbers.group_activity_turnover}
              onChange={set("group_activity_turnover")}
              cur={cur}
            />
            <Money
              label="Charges activité commune"
              value={numbers.group_activity_expenses}
              onChange={set("group_activity_expenses")}
              cur={cur}
            />
          </div>
          <label className="check-row" style={{ marginTop: "0.75rem" }}>
            <input
              type="checkbox"
              checked={solidarity}
              onChange={(e) => setSolidarity(e.target.checked)}
            />
            Engagement de solidarité entre membres
          </label>
          <label className="field" style={{ marginTop: "0.75rem" }}>
            <span>Commentaire groupement</span>
            <textarea
              rows={3}
              value={groupComment}
              onChange={(e) => setGroupComment(e.target.value)}
            />
          </label>
        </FormSection>
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
              {individualProfile === "SALARIE" && (
                <Money
                  label="Revenus d'activité (hors bloc dédié)"
                  value={numbers.other_activity_income}
                  onChange={set("other_activity_income")}
                  cur={cur}
                />
              )}
              <Money label="Autres revenus" value={numbers.other_income} onChange={set("other_income")} cur={cur} />
            </div>
            <div className="finance-recap">
              <RecapItem label="Total revenus" value={formatMoney(recap.income, cur)} strong />
            </div>
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
            {individualProfile === "SALARIE" && (
              <label className="check-row">
                <input
                  type="checkbox"
                  checked={hasSideActivity}
                  onChange={(e) => setHasSideActivity(e.target.checked)}
                />
                Exerce une activité génératrice de revenus
              </label>
            )}
            {showActivityBlock && (
              <>
                <div className="form-grid two-col" style={{ marginTop: "0.75rem" }}>
                  <Money
                    label="CA / recettes activité"
                    value={numbers.activity_turnover}
                    onChange={set("activity_turnover")}
                    cur={cur}
                  />
                  <Money
                    label="Charges activité"
                    value={numbers.activity_expenses}
                    onChange={set("activity_expenses")}
                    cur={cur}
                  />
                </div>
                <label className="field">
                  <span>Commentaire activité</span>
                  <textarea
                    rows={2}
                    value={activityComment}
                    onChange={(e) => setActivityComment(e.target.value)}
                  />
                </label>
              </>
            )}
          </FormSection>

          <FormSection
            id="fa-charges"
            icon={ReceiptText}
            title="Charges du ménage"
            description="Dépenses récurrentes du foyer et reste à vivre."
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
              <Money label="Autres charges" value={numbers.other_household_expenses} onChange={set("other_household_expenses")} cur={cur} />
            </div>
            <div className="finance-recap">
              <RecapItem label="Total charges" value={formatMoney(recap.charges, cur)} />
              <RecapItem label="Reste à vivre (avant nouvelle échéance)" value={formatMoney(recap.disposable, cur)} strong />
              {recap.perCapita !== null && (
                <RecapItem
                  label={`Reste à vivre / personne (${(dependents ?? 0) + 1})`}
                  value={formatMoney(recap.perCapita, cur)}
                />
              )}
            </div>
          </FormSection>

          {showStabilityBlock && (
          <FormSection
            id="fa-stability"
            icon={Landmark}
            title="Stabilité & quotité cessible"
            description="Ancienneté, revenus informels et fraction saisissable du salaire."
          >
            <div className="form-grid two-col">
              <Money label="Retenues déjà prélevées à la source" value={numbers.salary_deductions} onChange={set("salary_deductions")} cur={cur} />
              <Money label="Ancienneté emploi / activité (mois)" value={numbers.employment_seniority_months} onChange={set("employment_seniority_months")} />
              <Money label="Pondération revenus informels (%)" value={numbers.informal_income_weight} onChange={set("informal_income_weight")} />
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
          id="fa-collateral"
          icon={Shield}
          title="Garanties & cautions"
          description="Synthèse des piliers collatéral (garanties réelles et cautions) — hors mainlevée / dation."
        >
          <CollateralSummaryCard
            applicationId={application.id}
            currency={cur}
          />
        </FormSection>

        <FormSection
          id="fa-treasury"
          icon={Wallet}
          title="Trésorerie prévisionnelle"
          description="Flux prévisionnels et solde de trésorerie attendu."
        >
        <div className="form-grid two-col">
          <Money label="Encaissements prévisionnels" value={numbers.projected_monthly_inflows} onChange={set("projected_monthly_inflows")} cur={cur} />
          <Money label="Décaissements prévisionnels" value={numbers.projected_monthly_outflows} onChange={set("projected_monthly_outflows")} cur={cur} />
        </div>
        <div className="finance-recap">
          <RecapItem label="Solde de trésorerie prévisionnel" value={formatMoney(recap.surplus, cur)} strong />
        </div>
        <label className="field">
          <span>Commentaire sur la trésorerie prévisionnelle</span>
          <textarea
            rows={2}
            value={cashflowComment}
            onChange={(e) => setCashflowComment(e.target.value)}
          />
        </label>
        </FormSection>

        <FormSection
          id="fa-debt"
          icon={Landmark}
          title="Endettement consolidé & centrale des risques"
          description="Engagements en cours, incidents et historique de remboursement."
        >
        <div className="form-grid two-col">
          <label className="field">
            <span>Institution du crédit principal en cours</span>
            <input
              type="text"
              value={debtInstitution}
              onChange={(e) => setDebtInstitution(e.target.value)}
            />
          </label>
          <Money label="Montant initial du crédit" value={numbers.existing_debt_initial_amount} onChange={set("existing_debt_initial_amount")} cur={cur} />
          <Money label="Mensualités en cours (total consolidé, tous prêteurs)" value={numbers.existing_debt_monthly} onChange={set("existing_debt_monthly")} cur={cur} />
          <Money label="Encours restant / dettes financières" value={numbers.ongoing_credit_balance} onChange={set("ongoing_credit_balance")} cur={cur} />
          <Money label="Nombre de crédits actifs (tous prêteurs)" value={numbers.active_loans_count} onChange={set("active_loans_count")} />
          <Money label="Retard maximum constaté (jours)" value={numbers.max_days_late} onChange={set("max_days_late")} />
        </div>
        <div className="form-grid two-col">
          <Checkbox
            label="Centrale des risques / BIC consultée"
            checked={creditBureauChecked}
            onChange={setCreditBureauChecked}
          />
          <Money label="Date de consultation" type="date" value={creditBureauDate} onChange={setCreditBureauDate} />
          <Checkbox
            label="Incidents de paiement recensés"
            checked={hasIncidents}
            onChange={setHasIncidents}
          />
        </div>
        <label className="field">
          <span>Détails des incidents / engagements externes</span>
          <textarea
            rows={2}
            value={incidentsComment}
            onChange={(e) => setIncidentsComment(e.target.value)}
          />
        </label>
        <p className="subsection-label">Historique interne de remboursement</p>
        <div className="form-grid two-col">
          <Money label="Nombre de crédits antérieurs (institution)" value={numbers.prior_loans_count} onChange={set("prior_loans_count")} />
          <Money label="Taux de remboursement historique (%)" value={numbers.prior_repayment_rate} onChange={set("prior_repayment_rate")} />
          <Money label="Retard maximum historique interne (jours)" value={numbers.prior_max_delay_days} onChange={set("prior_max_delay_days")} />
        </div>
        <p className="muted small">
          L'échéance du crédit sollicité et les ratios (taux d'endettement,
          {isCorporate ? " DSCR" : " reste à vivre"}, stress test, couverture
          garanties et score) sont calculés automatiquement à l'enregistrement.
        </p>
        </FormSection>

        {(isCorporate || isGroupement) && (
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

        {(isCorporate || isGroupement) && (
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
        <label className="field">
          <span>Avis / commentaire de synthèse</span>
          <textarea
            rows={4}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="Conclusion générale de l'analyste…"
          />
        </label>
        <p className="muted small">
          Le score interne (/100) est calculé automatiquement à partir de la
          grille de notation pondérée (capacité, endettement, structure,
          garanties, historique).
        </p>
        <MultiFileField
          label="Pièces justificatives (bulletins, états financiers, relevés…)"
          files={docs}
          onChange={setDocs}
          existing={initial?.documents}
        />
        </FormSection>

        {error && <div className="form-error">{error}</div>}
        <div className="credit-form-actions">
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
      </div>
    </form>
  );
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
  return (
    <section id={id} className="card form-section">
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
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  cur?: string;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      <input
        type={type}
        min={type === "number" ? 0 : undefined}
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
