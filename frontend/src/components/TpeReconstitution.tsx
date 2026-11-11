import type { AnalysisDetails } from "@/api/types";
import { FinancialAnalysisDetails } from "@/components/FinancialAnalysisDetails";
import { productFigures } from "@/components/productLine";
import { formatMoney } from "@/components/ui";

const SALES_METHODS = [
  ["", "Non utilisée"],
  ["CAHIER", "Cahier de ventes ou factures"],
  ["BANK", "Relevés bancaires ou Mobile Money"],
  ["THREE_DAYS", "Trois derniers jours observés"],
  ["HYPOTHESIS", "Trois hypothèses (excellent, moyen, faible)"],
  ["STOCK", "Inventaire du stock"],
  ["OTHER", "Autre méthode"],
];
const PURCHASE_METHODS = [
  ["", "Non utilisée"],
  ["INVOICES", "Factures fournisseurs"],
  ["LEDGER", "Cahier d'achats"],
  ["COST_RATE", "Taux de coût issu de la marge produit"],
  ["OTHER", "Autre méthode"],
];
const PURCHASE_METHOD_ORDER = ["INVOICES", "LEDGER", "COST_RATE", "OTHER"];

export const TPE_DETAIL_KEYS = [
  "sales_method", "purchase_method", "cash_check_comment",
  "last_purchase_date", "cash_control_date", "activity_days_per_month",
  "retained_daily_sales", "sales_control_monthly", "purchase_average",
  "purchase_frequency", "safety_provision_pct", "last_purchase_amount",
  "cash_at_last_purchase", "charges_paid_in_window", "other_outflows_in_window",
  "observed_cash", "cash_tolerance_pct",
];

function text(details: AnalysisDetails, key: string) {
  const value = details[key];
  return typeof value === "string" ? value : "";
}

function setKey(details: AnalysisDetails, key: string, value: string): AnalysisDetails {
  return { ...details, [key]: value };
}

export function selectedPurchaseMethodCodes(details: AnalysisDetails): string[] {
  return selectedPurchaseMethods(details);
}

export function withPurchaseMethods(details: AnalysisDetails, selected: string[]): AnalysisDetails {
  return setPurchaseMethods(details, selected);
}

export function TpeReconstitution({ details, onChange, currency, part = "all", omitLastPurchase = false, omitMethods = [], declaredMonthly = undefined }: {
  details: AnalysisDetails;
  onChange: (next: AnalysisDetails) => void;
  currency: string;
  part?: "all" | "sales" | "purchases" | "turnover" | "safety" | "cash";
  omitLastPurchase?: boolean;
  omitMethods?: string[];
  declaredMonthly?: number | null;
}) {
  const field = (key: string, label: string, type = "number", hint?: string) => (
    <label className="field" key={key}>
      <span>{label}</span>
      <input type={type} step={type === "number" ? "any" : undefined}
        value={text(details, key)} onChange={(event) => onChange(setKey(details, key, event.target.value))} />
      {hint && <small className="muted">{hint}</small>}
    </label>
  );
  const observed = average(details, "Observé");
  const hypothesis = average(details, "Hypothèse");
  const method = text(details, "sales_method");
  const computed = method === "THREE_DAYS" ? observed : method === "HYPOTHESIS" ? hypothesis : null;
  const retained = number(text(details, "retained_daily_sales")) ?? computed;
  const days = number(text(details, "activity_days_per_month"));
  const monthly = retained != null && days != null ? retained * days : null;
  const methods = selectedPurchaseMethods(details);
  const visibleMethodCodes = PURCHASE_METHOD_ORDER.filter((code) => !omitMethods.includes(code));
  const visibleMethods = methods.filter((code) => visibleMethodCodes.includes(code));
  const purchaseAverage = number(text(details, "purchase_average"));
  const purchaseFrequency = number(text(details, "purchase_frequency"));
  const countedPurchases = purchaseAverage != null && purchaseFrequency != null ? purchaseAverage * purchaseFrequency : null;
  const marginRate = sheetMarginRate(details);
  const costRatePurchases = monthly != null && marginRate != null ? monthly * (1 - marginRate) : null;
  const methodAmount = (code: string) => code === "INVOICES" || code === "LEDGER" ? countedPurchases : code === "COST_RATE" ? costRatePurchases : null;

  const sales = part === "all" || part === "sales";
  const safety = part === "all" || part === "safety";
  const cash = part === "all" || part === "cash";

  return <div className="stack">
    {sales && <p className="subsection-label">Reconstitution TPE</p>}
    {sales && <p className="muted small">
      Le chiffre retenu est comparé au chiffre déclaré, ramené au mois.
      La retenue de prudence et le contrôle de caisse viennent après les charges et le bilan.
    </p>}
    {sales && <div className="form-grid two-col">
      <label className="field">
        <span>Méthode de chiffre d'affaires</span>
        <select value={text(details, "sales_method")} onChange={(event) => onChange(setKey(details, "sales_method", event.target.value))}>
          {SALES_METHODS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
      </label>
      <label className="field">
        <span>Méthode d'achats</span>
        <select value={text(details, "purchase_method")} onChange={(event) => onChange(setKey(details, "purchase_method", event.target.value))}>
          {PURCHASE_METHODS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
      </label>
      {field("activity_days_per_month", "Jours d'activité par mois", "number", "De 1 à 31.")}
      {field("retained_daily_sales", "CA journalier retenu, si différent de la moyenne", "number", "Laisser vide pour retenir la moyenne de la méthode choisie.")}
      {field("sales_control_monthly", "CA mensuel de contrôle (relevés)", "number")}
      {field("purchase_average", "Achat moyen", "number", "Utilisé pour les factures et le cahier d'achats.")}
      {field("purchase_frequency", "Approvisionnements par mois", "number")}
    </div>}
    {sales && <FinancialAnalysisDetails name="sales_observations" value={details} onChange={onChange} currency={currency} />}
    {sales && <div className="finance-recap">
      <span>Moyenne observée {money(observed, currency)}</span>
      <span>Moyenne des hypothèses {money(hypothesis, currency)}</span>
      <span>CA mensuel indicatif {money(monthly, currency)}</span>
    </div>}
    {safety && <div className="form-grid two-col">
      {field("safety_provision_pct", "Retenue de prudence (%)", "number", "Souvent 30. Vide : pas de retenue. Elle s'applique à la capacité déjà nette des dettes existantes et ne change pas le taux d'endettement.")}
    </div>}
    {cash && <p className="subsection-label">Contrôle de trésorerie depuis le dernier achat</p>}
    {cash && <p className="muted small">Les charges réellement payées sur la période priment. À défaut, les charges mensuelles hors achats sont étalées sur 30 jours : un loyer payé en une fois peut alors créer un faux écart.</p>}
    {cash && <div className="form-grid two-col">
      {!omitLastPurchase && field("last_purchase_date", "Date du dernier achat", "date")}
      {field("cash_control_date", "Date du contrôle", "date")}
      {!omitLastPurchase && field("last_purchase_amount", "Montant du dernier achat", "number")}
      {field("cash_at_last_purchase", "Trésorerie disponible à cette date", "number", "Caisse, banque et Mobile Money.")}
      {field("charges_paid_in_window", "Charges réellement payées sur la période", "number", "Vide : prorata des charges mensuelles hors achats, seulement si elles sont renseignées.")}
      {field("other_outflows_in_window", "Autres sorties de la période", "number", "Achats complémentaires et remboursements. Vide : zéro.")}
      {field("observed_cash", "Trésorerie constatée au contrôle", "number")}
      {field("cash_tolerance_pct", "Tolérance d'écart (%)", "number", "Vide : 10. Au-delà du double, l'écart est incohérent.")}
    </div>}
    {part === "purchases" && <div className="form-grid two-col purchase-methods-split">
      {!omitLastPurchase && field("last_purchase_date", "Date du dernier achat", "date")}
      {!omitLastPurchase && field("last_purchase_amount", "Montant du dernier achat", "number")}
      <fieldset className="field purchase-methods">
        <legend>Méthodes d&apos;achats</legend>
        <div className="purchase-method-choices">
          {visibleMethodCodes.map((code) => (
            <label className="checkbox-inline" key={code}>
              <input
                type="checkbox"
                checked={methods.includes(code)}
                onChange={(event) => onChange(setPurchaseMethods(details, event.target.checked ? [...methods, code] : methods.filter((item) => item !== code)))}
              />
              {PURCHASE_METHODS.find(([value]) => value === code)?.[1]}
            </label>
          ))}
        </div>
      </fieldset>
    </div>}
    {part === "purchases" && visibleMethods.length > 0 && <div className="finance-recap">
      {visibleMethods.map((code) => (
        <span key={code}>{PURCHASE_METHODS.find(([value]) => value === code)?.[1]} {code === "OTHER" ? "—" : money(methodAmount(code), currency)}</span>
      ))}
      {declaredMonthly !== undefined && <span>Achats déclarés / mois {money(declaredMonthly, currency)}</span>}
    </div>}
    {part === "turnover" && <div className="form-grid two-col">
      <label className="field">
        <span>Méthode de chiffre d'affaires</span>
        <select value={text(details, "sales_method")} onChange={(event) => onChange(setKey(details, "sales_method", event.target.value))}>
          {SALES_METHODS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
      </label>
      {field("activity_days_per_month", "Jours d'activité par mois", "number", "De 1 à 31.")}
      {field("retained_daily_sales", "CA journalier retenu, si différent de la moyenne", "number", "Laisser vide pour retenir la moyenne de la méthode choisie.")}
      {field("sales_control_monthly", "CA mensuel de contrôle (relevés)", "number")}
    </div>}
    {part === "turnover" && <FinancialAnalysisDetails name="sales_observations" value={details} onChange={onChange} currency={currency} />}
    {part === "turnover" && <div className="finance-recap">
      <span>Moyenne observée {money(observed, currency)}</span>
      <span>Moyenne des hypothèses {money(hypothesis, currency)}</span>
      <span>CA mensuel indicatif {money(monthly, currency)}</span>
    </div>}
    {cash && <label className="field">
      <span>Explication de l'écart de trésorerie</span>
      <textarea rows={2} value={text(details, "cash_check_comment")}
        onChange={(event) => onChange(setKey(details, "cash_check_comment", event.target.value))} />
      <small className="muted">Obligatoire avant soumission si le contrôle conclut « à justifier » ou « incohérent ».</small>
    </label>}
  </div>;
}

function selectedPurchaseMethods(details: AnalysisDetails): string[] {
  const rows = details.purchase_methods;
  if (Array.isArray(rows)) {
    return PURCHASE_METHOD_ORDER.filter((code) => rows.some((row) => row.method === code));
  }
  const single = text(details, "purchase_method");
  return PURCHASE_METHOD_ORDER.includes(single) ? [single] : [];
}

function setPurchaseMethods(details: AnalysisDetails, selected: string[]): AnalysisDetails {
  const methods = PURCHASE_METHOD_ORDER.filter((code) => selected.includes(code));
  return {
    ...details,
    purchase_methods: methods.map((method) => ({ method })),
    purchase_method: methods.length === 1 ? methods[0] : "",
  };
}

function sheetMarginRate(details: AnalysisDetails): number | null {
  const rows = details.products;
  if (!Array.isArray(rows) || rows.length === 0) return null;
  const figures = rows.map((row) => productFigures((row ?? {}) as Record<string, string>));
  if (!figures.every((item) => item.sales != null && item.cost != null && item.margin != null)) return null;
  const sales = figures.reduce((total, item) => total + (item.sales ?? 0), 0);
  if (sales === 0) return null;
  return figures.reduce((total, item) => total + (item.margin ?? 0), 0) / sales;
}

function number(value: string): number | null {
  if (!value.trim()) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function average(details: AnalysisDetails, kind: string): number | null {
  const rows = details.sales_observations;
  if (!Array.isArray(rows)) return null;
  const selected = rows.filter((row) => (row.kind || "Observé") === kind && Object.values(row).some((value) => value));
  if (!selected.length || selected.some((row) => row.amount == null || row.amount === "")) return null;
  const total = selected.reduce((sum, row) => sum + Number(row.amount), 0);
  return total / selected.length;
}

function money(value: number | null, currency: string) {
  return value == null ? "—" : formatMoney(value, currency);
}
