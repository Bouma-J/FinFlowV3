import { CREDIT_LABELS, type FinancialAnalysis } from "@/api/types";
import type { ReactNode } from "react";
import { formatDate, formatMoney } from "@/components/ui";
import { FINANCIAL_SUPPLEMENTS } from "@/components/FinancialAnalysisSupplements";
import { savedExternalCredits } from "@/components/externalCredits";
import { FinancialStatementsReadout, ActivityStatementReading } from "@/components/FinancialStatementsSection";
import { PRODUCT_NATURES, PRODUCTION_IDENTITY, PRODUCTION_STOCKS, productAmount, productFigures, productNature, retainedActivityMargin } from "@/components/productLine";
import { readStatements } from "@/components/financialStatements";
import { groupActivityOpen, purposeTestText, resolveAnalysisPath, resolveStatementBasis, themeAllowed } from "@/components/analysisPath";
import { ANALYSIS_TABLES, FinancialAnalysisDetails } from "@/components/FinancialAnalysisDetails";

type Field = [keyof FinancialAnalysis, string, ("money" | "text" | "count" | "bool" | "percent")?];
const INCOME: Field[] = [["salary_income", "Salaire net"], ["spouse_income", "Revenus du conjoint"], ["rental_income", "Loyers / rentes"], ["pension_income", "Pension"], ["variable_income", "Primes / revenus variables"], ["other_activity_income", "Revenus d'activité hors bloc dédié"], ["other_income", "Autres revenus"]];
const HOUSEHOLD: Field[] = [["rent_expense", "Logement"], ["food_expense", "Alimentation"], ["utilities_expense", "Eau / électricité / téléphone"], ["transport_expense", "Transport"], ["education_expense", "Scolarité"], ["health_expense", "Santé"], ["tontine_expense", "Tontines"], ["social_contributions", "Cotisations / assurances"], ["family_support_expense", "Soutien familial"], ["other_monthly_obligations", "Autres obligations sur la période"]];
const RESULT: Field[] = [["turnover", "Chiffre d'affaires"], ["cogs", "Coût des marchandises vendues"], ["gross_margin", "Marge brute"], ["other_operating_income", "Autres produits d'exploitation"], ["op_rent", "Loyer"], ["op_salaries", "Salaires"], ["op_utilities", "Eau / électricité"], ["op_transport", "Transport"], ["op_telecom", "Télécoms"], ["op_taxes", "Impôts d'exploitation / patente"], ["op_maintenance", "Entretien"], ["op_other", "Autres charges d'exploitation"], ["total_operating_expenses", "Total charges d'exploitation"], ["ebe", "EBE reconstitué"], ["depreciation", "Amortissements"], ["financial_charges", "Charges financières"], ["net_result", "Résultat reconstitué"], ["cash_flow", "Résultat + charges non décaissées nettes"]];
const ASSETS: Field[] = [["stock_value", "Stock"], ["receivables", "Créances clients"], ["cash_in_hand", "Caisse"], ["bank_balance", "Banque disponible"], ["cash_available", "Ancien agrégat de trésorerie"], ["other_current_assets", "Autres actifs courants"], ["land_building_value", "Terrains / bâtiments"], ["equipment_value", "Équipements"], ["vehicle_value", "Véhicules"], ["other_fixed_assets", "Autres immobilisations"], ["fixed_assets", "Ancien agrégat d'immobilisations"], ["total_assets", "Total de l'actif retenu"]];
const DEBTS: Field[] = [["supplier_debt", "Dettes fournisseurs"], ["tax_social_debt", "Dettes fiscales et sociales"], ["other_current_debt", "Autres dettes d'exploitation"], ["short_term_debt", "Autres dettes court terme (hors postes précédents)"], ["ongoing_credit_balance", "Encours financier total"], ["long_term_debt", "Dont part long terme (déjà incluse)"], ["shareholder_debt", "Comptes courants d'associés"], ["total_debts", "Total dettes"], ["equity", "Fonds propres reconstitués (actif − dettes)"]];
const ACTIVITY: Field[] = [["activity_name", "Activité", "text"], ["activity_business_age_months", "Ancienneté (mois)", "count"], ["activity_sales_days", "Jours de vente sur la période", "count"], ["activity_turnover", "CA / recettes"], ["activity_expenses", "Charges totales, achats inclus"], ["activity_purchases", "Dont achats (déjà inclus)"], ["activity_stock_value", "Stock"], ["activity_receivables", "Créances clients"], ["activity_cash_available", "Trésorerie"], ["activity_fixed_assets", "Actifs productifs"], ["activity_supplier_debt", "Fournisseurs"], ["activity_is_formal", "Activité formalisée", "bool"], ["activity_records_available", "Cahier / pièces disponibles", "bool"]];
const GROUP: Field[] = [["members_count", "Membres", "count"], ["active_contributing_members", "Cotisants actifs", "count"], ["members_with_arrears", "Membres en retard", "count"], ["group_age_months", "Ancienneté (mois)", "count"], ["collective_contributions", "Cotisations"], ["collective_other_income", "Autres recettes"], ["group_activity_turnover", "CA commun"], ["collective_operating_expenses", "Fonctionnement"], ["group_activity_expenses", "Charges de l'activité"], ["collective_savings", "Épargne (solde, pas un revenu)"], ["collective_savings_locked", "Épargne mobilisable / nantie", "bool"], ["group_records_verified", "Registres / épargne vérifiés", "bool"], ["solidarity_commitment", "Engagement de solidarité", "bool"]];

function numeric(value: unknown): number | null {
  if (value === null || value === undefined || value === "" || typeof value === "boolean") return null;
  if (typeof value !== "string" && typeof value !== "number") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}
function Theme({ title, children }: { title: string; children: ReactNode }) {
  return <section className="analysis-theme"><h3 className="analysis-chapter-title">{title}</h3>{children}</section>;
}

function Note({ label, text }: { label: string; text: string }) {
  if (!text.trim()) return null;
  return <div className="analysis-note"><p className="subsection-label">{label}</p><p className="prose">{text}</p></div>;
}

function ForecastChart({ rows, currency }: { rows: Record<string, unknown>[]; currency: string }) {
  const flows = rows.map((row) => numeric(row.net_flow));
  const balances = rows.map((row) => numeric(row.closing));
  const values = [...flows, ...balances].filter((value): value is number => value != null);
  const low = Math.min(0, ...values);
  const high = Math.max(0, ...values);
  const span = high - low || 1;
  const x = (index: number) => 44 + (index + 0.5) * 560 / rows.length;
  const y = (value: number) => 20 + (high - value) * 130 / span;
  const width = Math.max(1, Math.min(30, 400 / rows.length));
  const closingKnown = balances.every((value) => value != null);
  return <figure style={{ margin: "16px 0" }}>
    <svg viewBox="0 0 640 190" role="img" aria-label="Flux mensuels en barres et trésorerie cumulée de clôture en courbe lorsqu'elle est connue" style={{ width: "100%", maxHeight: 240 }}>
      <line x1="40" y1={y(0)} x2="610" y2={y(0)} stroke="currentColor" opacity="0.3" />
      {flows.map((flow, index) => flow == null ? null : <rect key={index} x={x(index) - width / 2} y={Math.min(y(0), y(flow))} width={width} height={Math.max(1, Math.abs(y(flow) - y(0)))} fill={flow < 0 ? "var(--danger, #b91c1c)" : "var(--brand)"} opacity="0.75"><title>{`${rows[index].month} : flux ${formatMoney(flow, currency)}`}</title></rect>)}
      {closingKnown && <polyline points={balances.map((value, index) => `${x(index)},${y(value!)}`).join(" ")} fill="none" stroke="var(--accent)" strokeWidth="2.5" />}
      {closingKnown && balances.map((value, index) => <circle key={index} cx={x(index)} cy={y(value!)} r="3" fill="var(--accent)"><title>{`${rows[index].month} : clôture ${formatMoney(value, currency)}`}</title></circle>)}
      {rows.map((row, index) => index % Math.max(1, Math.ceil(rows.length / 8)) === 0 ? <text key={index} x={x(index)} y="176" textAnchor="middle" fill="currentColor" fontSize="10">{String(row.month || "—")}</text> : null)}
      <text x="4" y="16" fill="currentColor" fontSize="10">{formatMoney(high, currency)}</text><text x="4" y="154" fill="currentColor" fontSize="10">{formatMoney(low, currency)}</text>
    </svg>
    <figcaption className="muted small">Barres : flux mensuels (rouge si négatifs). {closingKnown ? "Courbe accent : trésorerie cumulée de clôture." : "Solde cumulé non tracé : données d'ouverture ou mois manquants."} Les montants exacts figurent dans le tableau.</figcaption>
  </figure>;
}

type DetailRow = Record<string, string>;

function ExtraMoneyLines({
  details,
  name,
  currency,
}: {
  details: FinancialAnalysis["analysis_details"];
  name: string;
  currency: string;
}) {
  const rows = detailRows(details, name).flatMap((row, index) => {
    const label = String(row.label || "").trim();
    const amount = numeric(row.amount);
    if (!label || amount == null) return [];
    return [<div key={`${name}-${index}`}><dt>{label}</dt><dd>{formatMoney(amount, currency)}</dd></div>];
  });
  if (rows.length === 0) return null;
  return <dl className="def-list two">{rows}</dl>;
}

function detailRows(details: FinancialAnalysis["analysis_details"], key: string): DetailRow[] {
  const value = details?.[key];
  return Array.isArray(value) ? value : [];
}

function moneyCell(value: number | null, currency: string) {
  return value == null ? "—" : formatMoney(value, currency);
}

function variation(current: number | null, previous: number | null) {
  if (current == null || previous == null || previous === 0) return "—";
  const percent = ((current - previous) / Math.abs(previous)) * 100;
  const text = percent.toLocaleString("fr-FR", { maximumFractionDigits: 1 });
  return `${percent > 0 ? "+" : ""}${text} %`;
}

function spread(current: number | null, previous: number | null) {
  return current == null || previous == null ? null : current - previous;
}

function ReadTable({ caption, headers, rows }: { caption: string; headers: string[]; rows: string[][] }) {
  if (!rows.length) return null;
  return <div className="table-scroll">
    <table className="table">
      <caption>{caption}</caption>
      <thead><tr>{headers.map((label, index) => <th scope="col" key={`${label}-${index}`}>{label}</th>)}</tr></thead>
      <tbody>{rows.map((row, index) => <tr key={index}>{row.map((cell, cellIndex) => <td key={cellIndex} className={cellIndex ? "num" : undefined}>{cell}</td>)}</tr>)}</tbody>
    </table>
  </div>;
}

function ComparativeTables({ analysis: a, currency, only }: { analysis: FinancialAnalysis; currency: string; only: "statement" | "history" | "sales" | "cash" | "products" | "stocks" }) {
  const details = a.analysis_details;
  const metric = (key: string) => numeric(a.metrics[key]);
  const currentTurnover = numeric(a.turnover);
  const previousTurnover = numeric(a.turnover_prev);
  const currentResult = numeric(a.net_result);
  const previousResult = numeric(a.net_result_prev);
  const statement = [
    currentTurnover != null || previousTurnover != null
      ? ["Chiffre d'affaires", moneyCell(currentTurnover, currency), moneyCell(previousTurnover, currency), moneyCell(spread(currentTurnover, previousTurnover), currency), variation(currentTurnover, previousTurnover)]
      : null,
    currentResult != null || previousResult != null
      ? ["Résultat net", moneyCell(currentResult, currency), moneyCell(previousResult, currency), moneyCell(spread(currentResult, previousResult), currency), variation(currentResult, previousResult)]
      : null,
  ].filter((row): row is string[] => row != null);

  const history = detailRows(details, "history");
  let priorTurnover: number | null = null;
  let priorResult: number | null = null;
  const historyRows = history.map((row) => {
    const turnover = numeric(row.turnover);
    const result = numeric(row.net_result);
    const line = [row.period || "—", moneyCell(turnover, currency), variation(turnover, priorTurnover), moneyCell(result, currency), variation(result, priorResult), moneyCell(numeric(row.cashflow), currency), moneyCell(numeric(row.equity), currency)];
    priorTurnover = turnover;
    priorResult = result;
    return line;
  });
  const latest = history[history.length - 1];
  const historyTurnover = latest ? numeric(latest.turnover) : null;
  const historyResult = latest ? numeric(latest.net_result) : null;
  const historyConflict = (historyTurnover != null && previousTurnover != null && Math.abs(historyTurnover - previousTurnover) > 0.5)
    || (historyResult != null && previousResult != null && Math.abs(historyResult - previousResult) > 0.5);

  const declared = metric("tpe_declared_monthly_sales");
  const retained = metric("tpe_monthly_sales");
  const control = numeric(details?.sales_control_monthly);
  const againstRetained = (amount: number | null) => {
    const gap = spread(retained, amount);
    return [moneyCell(gap, currency), variation(retained, amount)];
  };
  const method = ({ CAHIER: "cahier ou factures", BANK: "relevés ou Mobile Money", THREE_DAYS: "trois jours observés", HYPOTHESIS: "trois hypothèses", STOCK: "inventaire", OTHER: "autre" } as Record<string, string>)[String(details?.sales_method || "")] || "méthode retenue";
  const salesRows = retained == null && control == null ? [] : [
    declared != null ? ["Déclaré, ramené au mois", moneyCell(declared, currency), ...againstRetained(declared)] : null,
    retained != null ? [`Retenu — ${method}`, moneyCell(retained, currency), "—", "—"] : null,
    control != null ? ["Contrôle", moneyCell(control, currency), ...againstRetained(control)] : null,
  ].filter((row): row is string[] => row != null);

  const opening = numeric(details?.cash_at_last_purchase);
  const collected = metric("tpe_cash_collected");
  const charges = metric("tpe_cash_charges");
  const other = metric("tpe_cash_other_outflows");
  const theoretical = metric("tpe_cash_theoretical");
  const observed = metric("tpe_cash_observed");
  const cashGap = metric("tpe_cash_gap");
  const cashRows = [
    ["Caisse au dernier achat", moneyCell(opening, currency)],
    ["Encaissements de la fenêtre", moneyCell(collected, currency)],
    ["Charges payées", moneyCell(charges, currency)],
    ["Autres sorties", moneyCell(other, currency)],
    ["Trésorerie théorique", moneyCell(theoretical, currency)],
    ["Trésorerie constatée", moneyCell(observed, currency)],
    ["Écart", moneyCell(cashGap, currency)],
    ["Tolérance", metric("tpe_cash_tolerance_pct") == null ? "—" : `${metric("tpe_cash_tolerance_pct")} %`],
    ["Conclusion", ({ COHERENT: "Cohérent", TO_JUSTIFY: "À justifier", INCOHERENT: "Incohérent" } as Record<string, string>)[String(a.metrics.tpe_cash_conclusion || "")] || "—"],
  ].filter((row) => row[1] !== "—");

  const products = detailRows(details, "products").filter((row) => row.name || row.sale_price || row.unit_cost || row.quantity || row.quantity_produced || row.material_cost || row.nature === "MANUFACTURED" || row.nature === "SERVICE");
  const productRows = products.map((row) => {
    const figures = productFigures(row);
    const nature = productNature(row);
    const directCost = nature === "SERVICE" && productAmount(row.unit_cost) == null ? "Aucun" : moneyCell(figures.unitCost, currency);
    return [
      PRODUCT_NATURES.find((item) => item.value === nature)?.label || "Revendu",
      row.name || "—",
      row.unit || "—",
      nature === "MANUFACTURED" && figures.produced != null ? figures.produced.toLocaleString("fr-FR") : "—",
      figures.sold == null ? "—" : figures.sold.toLocaleString("fr-FR"),
      directCost,
      moneyCell(numeric(row.sale_price), currency),
      moneyCell(figures.sales, currency),
      moneyCell(figures.margin, currency),
    ];
  });
  const productionOverrun = products.some((row) => {
    const figures = productFigures(row);
    return productNature(row) === "MANUFACTURED" && figures.unsold != null && figures.unsold < 0;
  });
  const stocks = detailRows(details, "stocks").filter((row) => row.name || row.quantity || row.unit_cost);
  const stockRows = stocks.map((row) => {
    const quantity = numeric(row.quantity);
    const cost = numeric(row.unit_cost);
    const impairment = numeric(row.impaired_value);
    const gross = quantity != null && cost != null ? quantity * cost : null;
    return [row.name || "—", quantity == null ? "—" : quantity.toLocaleString("fr-FR"), moneyCell(cost, currency), moneyCell(impairment, currency), moneyCell(gross != null && impairment != null ? gross - impairment : null, currency)];
  });

  if (only === "statement") return <ReadTable caption="Compte de résultat — période en cours et période précédente" headers={["Rubrique", "Période en cours", "Période précédente", "Écart", "Variation"]} rows={statement} />;
  if (only === "history") return <>
    <ReadTable caption="Historique — variation par rapport à la ligne précédente" headers={["Période", "Chiffre d'affaires", "Variation", "Résultat", "Variation", "Cash-flow", "Capitaux propres"]} rows={historyRows} />
    {historyConflict && <p className="form-error">La dernière ligne de l'historique ne correspond pas au chiffre d'affaires N-1 ou au résultat N-1 saisi à part. Les deux sources restent affichées.</p>}
  </>;
  if (only === "sales") return <ReadTable caption="Chiffre d'affaires retenu — écart avec le montant retenu" headers={["Source", "Montant", "Écart avec le retenu", "Écart"]} rows={salesRows} />;
  if (only === "cash") return <ReadTable caption="Trésorerie depuis le dernier achat" headers={["Poste", "Montant"]} rows={cashRows} />;
  if (only === "products") return <>
    <ReadTable caption="Fiches produits — le chiffre d'affaires retenu est la quantité vendue" headers={["Nature", "Article", "Unité", "Produite", "Vendue", "Coût unitaire", "Prix de vente", "CA retenu", "Marge"]} rows={productRows} />
    {productionOverrun && <p className="form-error">Des ventes dépassent la production de la période. Le surplus vient d'un stock déjà constitué, ou l'écart reste à expliquer.</p>}
  </>;
  return <ReadTable caption="Stock — valeur nette, quantité × coût moins dépréciation" headers={["Article", "Quantité", "Coût unitaire", "Dépréciation", "Valeur nette"]} rows={stockRows} />;
}

export function FinancialAnalysisReadout({ analysis: a, currency, part }: { analysis: FinancialAnalysis; currency: string; part: "topics" | "indicators" }) {
  const m = a.metrics;
  const n = (key: string) => numeric(m[key]);
  const money = (key: string) => formatMoney(n(key), currency);
  const corp = a.client_type === "CORPORATE";
  const group = a.client_type === "PROFESSIONAL";
  const path = resolveAnalysisPath({
    clientType: a.client_type,
    individualProfile: a.individual_profile,
    hasSideActivity: a.has_side_activity,
    statementBasis: corp ? resolveStatementBasis(a.analysis_details) : "RECONSTITUTED",
  });
  const context = a.calculation_context;
  const period = ({ MONTHLY: "mois", QUARTERLY: "trimestre", ANNUAL: "année" } as Record<string, string>)[a.reference_period] || a.reference_period;
  const format = (value: unknown, type = "money") => value == null || value === "" ? "Non renseigné"
    : type === "bool" ? (value ? "Oui" : "Non")
    : type === "text" ? String(value)
    : type === "count" ? String(value)
    : type === "percent" ? `${numeric(value)?.toLocaleString("fr-FR") ?? "—"} %`
    : formatMoney(numeric(value), currency);
  const fields = (items: Field[]) => <dl className="def-list two">{items.map(([key, label, type]) => <div key={key}><dt>{label}</dt><dd>{format(a[key], type)}</dd></div>)}</dl>;
  const card = (label: string, key: string) => <div className="metric" key={key}><span className="metric-label">{label}</span><span className="metric-value">{money(key)}</span></div>;
  const rows = Array.isArray(m.forecast_rows) ? m.forecast_rows as Record<string, unknown>[] : [];
  const warnings: string[] = [];
  if (m.installment_known === false) warnings.push("Échéancier non calculable : les indicateurs dépendant de la nouvelle échéance sont indisponibles. Vérifier les conditions du crédit.");
  if (m.income_positive === false) warnings.push("Revenu retenu nul ou négatif : le taux d'endettement n'est pas interprétable et la capacité ne peut pas être qualifiée favorable.");
  if (a.flags.capacity_ok === false) warnings.push("Les ressources disponibles ne couvrent pas l'effort total du crédit après charges et dettes existantes.");
  if (["FAVORABLE", "CONDITIONAL"].includes(a.recommendation) && (a.flags.capacity_ok === false || a.flags.dscr_ok === false || m.income_positive === false)) warnings.push("Divergence avec l'avis enregistré : l'analyste a donné un avis favorable ou favorable sous conditions, mais le recalcul signale une capacité ou une couverture du service de la dette insuffisante. L'avis enregistré et les résultats recalculés doivent être rapprochés avant une nouvelle décision.");
  if (m.tpe_safety_ok === false) warnings.push("La nouvelle échéance dépasse la capacité restante après retenue de prudence. Le taux d'endettement de la filiale reste le critère de décision.");

  const specs: { key: string; label: string; formula: string; unit?: string; threshold?: string; min?: boolean; flag?: string }[] = corp ? [
    { key: "global_dscr", label: m.dscr_basis === "forecast" ? "DSCR sur la prévision" : "DSCR global", formula: m.dscr_basis === "forecast" ? `${money("forecast_monthly_surplus")} / ${money("global_debt_service")} par mois. Le chiffre d'affaires passé n'est pas la base.` : `${money("repayment_cash_flow")} / ${money("global_debt_service")} par mois`, unit: "×", threshold: "min_dscr", min: true, flag: "dscr_ok" },
    { key: "dscr_stress", label: "DSCR sous stress", formula: "Flux disponible sous baisse du CA, hausse des achats et retard clients / service global", unit: "×", threshold: "min_dscr", min: true, flag: "dscr_stress_ok" },
    { key: "financial_autonomy", label: "Autonomie financière", formula: "Fonds propres reconstitués / actif × 100", unit: "%", threshold: "min_financial_autonomy", min: true, flag: "autonomy_ok" },
    { key: "gearing", label: "Gearing brut", formula: "Encours financier (hors comptes d'associés) / fonds propres positifs", unit: "×", threshold: "max_gearing", flag: "gearing_ok" },
    { key: "current_ratio", label: "Liquidité générale", formula: "Actif courant / passif courant (part financière court terme incluse)", unit: "×", threshold: "min_current_ratio", min: true, flag: "current_ratio_ok" },
    { key: "quick_ratio", label: "Liquidité réduite", formula: "(Actif courant − stocks) / passif courant", unit: "×" },
    { key: "dso_days", label: "Délai clients", formula: "Créances moyennes si ouverture connue, sinon clôture / CA annualisé × 360", unit: "jours" },
    { key: "dpo_days", label: "Délai fournisseurs", formula: "Fournisseurs moyens si ouverture connue, sinon clôture / achats annualisés (CAMV si achats inconnus) × 360", unit: "jours" },
    { key: "dio_days", label: "Rotation stock", formula: "Stock moyen si ouverture connue, sinon clôture / CAMV annualisé × 360", unit: "jours" },
    { key: "break_even_turnover", label: "Seuil de rentabilité sur la période", formula: "(Charges fixes + amortissements + charges financières) / taux de marge sur coûts variables ; nécessite une ventilation rapprochée" },
    { key: "result_growth", label: "Évolution du résultat", formula: "(Résultat N − N-1) / |résultat N-1| × 100 ; permet de distinguer pertes aggravées et amélioration", unit: "%" },
  ] : [
    ...(m.dscr_basis === "forecast" ? [{ key: "global_dscr", label: "DSCR sur la prévision", formula: `${money("forecast_monthly_surplus")} / ${money("global_debt_service")} par mois. Le chiffre d'affaires passé n'est pas la base.`, unit: "×", threshold: "min_dscr", min: true, flag: "dscr_ok" }] : []),
    { key: "debt_ratio", label: "Taux d'endettement", formula: `Service global ${money("global_debt_service")} / ${group ? "recettes collectives" : "revenu retenu"} ${money(group ? "collective_income" : "weighted_income")} × 100`, unit: "%", threshold: "max_debt_ratio", flag: "debt_ratio_ok" },
    { key: "debt_ratio_stress", label: "Taux sous stress", formula: "Service global / revenu positif retenu sous stress × 100", unit: "%", threshold: "max_debt_ratio", flag: "debt_ratio_stress_ok" },
    ...(group ? [{ key: "contribution_concentration", label: "Participation des cotisants", formula: "Cotisants actifs / membres × 100 (ne mesure pas la concentration des montants)", unit: "%" }, { key: "members_arrears_rate", label: "Membres en retard", formula: "Membres en retard / membres × 100", unit: "%" }] : [
      { key: "disposable_per_capita", label: "Reste après crédit par personne / mois", formula: "(Revenu pondéré − charges − dette existante − nouvelle échéance − épargne obligatoire) / (personnes à charge + 1)", threshold: "min_living_wage_per_capita", min: true, flag: "living_wage_ok" },
      ...((path === "SALARY" || path === "MIXED") ? [{ key: "transferable_quota_available", label: "Quotité disponible / mois", formula: "Salaire net mensuel × fraction configurée − retenues salariales mensuelles ; à comparer à l'échéance institution" }] : []),
    ]),
  ];
  specs.push({ key: "guarantee_coverage", label: "Couverture des garanties réelles", formula: "Valeur retenue après décotes / montant de référence × 100 ; cautions séparées", unit: "%", threshold: "min_guarantee_coverage", min: true, flag: "guarantee_ok" });

  const detailText = (key: string) => {
    const value = a.analysis_details?.[key];
    return typeof value === "string" ? value.trim() : "";
  };
  const hasDetail = (key: string) => {
    const value = a.analysis_details?.[key];
    return value != null && value !== "";
  };
  const supplementList = (keys: string[]) => {
    const kept = keys.filter(hasDetail);
    if (!kept.length) return null;
    return <dl className="def-list two">{kept.map((key) => <div key={key}><dt>{FINANCIAL_SUPPLEMENTS[key]}</dt><dd>{format(a.analysis_details?.[key], key.endsWith("_pct") ? "percent" : key.endsWith("_days") ? "count" : "money")}</dd></div>)}</dl>;
  };
  const lineNotes = (table: string, labelKey: string) => detailRows(a.analysis_details, table).flatMap((row, index) => {
    const comment = (row.comment || "").trim();
    return comment ? [<Note key={`${table}-${index}`} label={row[labelKey] || `Ligne ${index + 1}`} text={comment} />] : [];
  });
  const alert = (show: boolean, message: string) => show ? <p className="form-error">{message}</p> : null;
  const shortDate = (value: string) => /^\d{4}-\d{2}-\d{2}/.test(value) ? new Date(`${value.slice(0, 10)}T00:00:00`).toLocaleDateString("fr-FR") : value;
  const blocks: { title: string; body: ReactNode }[] = [];
  const add = (title: string, body: ReactNode, show: boolean) => { if (show && themeAllowed(title, path)) blocks.push({ title, body }); };
  const profileLabel = ({ SALARIE: "Salarié", INDEPENDANT: "Indépendant", MIXTE: "Mixte — salaire et activité" } as Record<string, string>)[a.individual_profile || ""] || "";
  const employmentLabel = ({ PERMANENT: "CDI / fonctionnaire", FIXED_TERM: "CDD", RETIRED: "Retraité", DAILY: "Journalier / intermittent", OTHER: "Autre" } as Record<string, string>)[a.employment_type] || "";
  const showActivity = !corp && !group && (a.has_side_activity || a.individual_profile === "INDEPENDANT" || a.individual_profile === "MIXTE" || !!a.activity_comment || m.tpe_purchases_aligned === false);
  const purchaseAlert = m.tpe_purchases_aligned === false;
  const pnlExtras = supplementList(["income_tax_expense", "provision_expense", "provision_reversal", "exceptional_income", "exceptional_expense", "fixed_operating_costs", "variable_operating_costs", "period_purchases"]);
  const balanceExtras = supplementList(["opening_receivables", "opening_supplier_debt", "declared_equity", "bfr_change", "maintenance_investment"]);
  const stockExtra = supplementList(["opening_stock"]);
  const forecastExtra = supplementList(["opening_cash_balance"]);
  const hasStatement = [a.turnover, a.turnover_prev, a.net_result, a.net_result_prev].some((value) => value != null && value !== "" && Number(value) !== 0);
  const hasHistory = detailRows(a.analysis_details, "history").length > 0;
  const hasSales = detailRows(a.analysis_details, "products").length > 0 || detailRows(a.analysis_details, "sales_observations").length > 0 || n("tpe_monthly_sales") != null || numeric(a.analysis_details?.sales_control_monthly) != null || !!detailText("business_model") || !!detailText("sales_verification") || m.tpe_sales_aligned === false || m.sales_reconciled === false || m.product_details_complete === false;
  const hasProductionStock = PRODUCTION_STOCKS.some((stock) => numeric(a.analysis_details?.[stock.key]) != null);
  const hasStock = detailRows(a.analysis_details, "stocks").length > 0 || !!detailText("stock_risks") || !!stockExtra || hasProductionStock || a.stock_count_verified === true || m.stock_reconciled === false || m.stock_details_complete === false;
  const hasCash = n("tpe_cash_theoretical") != null || n("tpe_cash_observed") != null || numeric(a.analysis_details?.cash_at_last_purchase) != null || !!detailText("last_purchase_date") || !!detailText("cash_check_comment") || m.tpe_cash_incomplete === true;
  const hasBank = detailRows(a.analysis_details, "bank_flows").length > 0;
  const bankBehavior = detailText("banking_behavior");
  const externalCredits = savedExternalCredits(a.analysis_details);
  const hasExistingDebt = !externalCredits.length && (!!a.existing_debt_institution || Number(a.existing_debt_initial_amount) > 0 || Number(a.existing_debt_monthly) > 0 || Number(a.ongoing_credit_balance) > 0);
  const hasBureau = !externalCredits.length && (a.credit_bureau_checked || a.has_payment_incidents || a.active_loans_count > 0 || !!a.incidents_comment || !!detailText("bureau_reference") || !!detailText("bureau_discrepancies"));
  const hasDebts = detailRows(a.analysis_details, "debts").length > 0 || externalCredits.length > 0 || hasExistingDebt || hasBureau || a.prior_loans_count > 0 || m.debt_details_complete === false || m.outstanding_reconciled === false || (!hasBank && !!bankBehavior);
  const hasForecast = n("forecast_opening_balance") != null || !!forecastExtra || rows.length > 0 || detailRows(a.analysis_details, "cashflow").length > 0 || numeric(a.projected_monthly_inflows) != null && Number(a.projected_monthly_inflows) !== 0 || numeric(a.projected_monthly_outflows) != null && Number(a.projected_monthly_outflows) !== 0 || !!a.cashflow_comment || !!detailText("seasonality") || m.forecast_service_reconciled === false;
  const modeSentence = [
    a.analysis_details?.cash_detail_mode === "DETAIL" ? "Trésorerie : détail, zéro compris." : a.analysis_details?.cash_detail_mode === "LEGACY" ? "Trésorerie : agrégat historique." : a.analysis_details?.cash_detail_mode ? "Trésorerie : détail non nul, sinon agrégat historique." : "",
    a.analysis_details?.fixed_assets_detail_mode === "DETAIL" ? "Immobilisations : détail, zéro compris." : a.analysis_details?.fixed_assets_detail_mode === "LEGACY" ? "Immobilisations : agrégat historique." : a.analysis_details?.fixed_assets_detail_mode ? "Immobilisations : détail non nul, sinon agrégat historique." : "",
  ].filter(Boolean).join(" ");

  const savedStatements = readStatements(a.analysis_details);
  const productionIdentity = PRODUCTION_IDENTITY.filter((field) => detailText(field.key));
  const showProductionIdentity = a.analysis_details?.manufactures === "yes" || productionIdentity.length > 0;
  const activityMargin = retainedActivityMargin(a.analysis_details?.products, a.activity_turnover, a.activity_expenses);
  const groupOpen = group && groupActivityOpen(a.analysis_details, a.group_activity_turnover, a.group_activity_expenses);
  const groupStatements = groupOpen && resolveStatementBasis(a.analysis_details) === "STATEMENTS";
  const showIndividualStatements = !corp && !group && (savedStatements.length > 0 || a.analysis_details?.statement_basis === "STATEMENTS");
  if (corp || showIndividualStatements || groupStatements) add("États financiers", <>
    {corp && showProductionIdentity && <div className="product-line">
      <h4>Identité de la production</h4>
      <p className="muted small">Les montants restent ceux des états. Cette fiche identifie l'activité de fabrication.</p>
      {productionIdentity.map((field) => <Note key={field.key} label={field.label} text={detailText(field.key)} />)}
      {a.analysis_details?.manufactures === "yes" && productionIdentity.length === 0 && <p className="muted small">Production déclarée. L'identité n'est pas encore renseignée.</p>}
    </div>}
    {!corp && <ActivityStatementReading statements={savedStatements} margin={group ? retainedActivityMargin(a.analysis_details?.products, a.group_activity_turnover, a.group_activity_expenses) : activityMargin} currency={currency} audience={group ? "group" : "activity"} />}
    <FinancialStatementsReadout statements={savedStatements} documents={a.documents || []} currency={currency} />
  </>, corp ? savedStatements.length > 0 || showProductionIdentity : showIndividualStatements || groupStatements);
  if (corp) add("Compte de résultat", <>
    {fields(RESULT)}
    <p className="muted small">Reconstitution à partir des postes fournis. Les compléments inconnus ne constituent pas une certification de résultat comptable.</p>
    {pnlExtras}
    {alert(m.fixed_costs_reconciled === false, "Écart à expliquer : charges fixes + variables et charges d'exploitation.")}
    {alert(purchaseAlert, "Les achats retenus s'écartent de plus de 10 % des achats déclarés, ramenés au mois.")}
  </>, true);
  if (group) add("Groupement", <>
    {fields(GROUP)}
    <p className="muted small">{groupOpen ? "La source retient les cotisations et les autres recettes, moins les charges de fonctionnement, plus la marge de l'activité commune. L'épargne reste hors revenu." : "La source retient les cotisations et les autres recettes, moins les charges de fonctionnement. L'activité commune n'est pas retenue. L'épargne reste hors revenu."}</p>
    <Note label="Activité commune" text={detailText("group_activity_description")} />
    {!groupOpen && (numeric(a.group_activity_turnover) != null || numeric(a.group_activity_expenses) != null) && <p className="muted small">Un chiffre d'affaires ou des charges d'activité sont enregistrés. Ils ne sont pas retenus tant que l'activité commune est fermée.</p>}
    <Note label="Commentaire sur le groupement" text={a.group_comment || ""} />
    {alert(purchaseAlert, "Les achats retenus s'écartent de plus de 10 % des achats déclarés, ramenés au mois.")}
  </>, true);
  if (!corp && !group) {
    add("Revenus du ménage", <>
      {profileLabel && <p className="muted small">Profil : {profileLabel}.</p>}
      {fields(path === "SALARY" ? INCOME.filter(([key]) => key !== "other_activity_income") : INCOME)}
      <ExtraMoneyLines details={a.analysis_details} name="extra_income" currency={currency} />
      <Note label="Justificatifs des revenus" text={detailText("household_income_evidence")} />
    </>, true);
    add("Charges du ménage", <>
      {fields(HOUSEHOLD)}
      <ExtraMoneyLines details={a.analysis_details} name="extra_charges" currency={currency} />
    </>, true);
    add("Emploi et stabilité", <>
      {fields([["employer_name", "Employeur", "text"], ["employer_sector", "Secteur employeur", "text"], ["employment_seniority_months", "Ancienneté (mois)", "count"], ["salary_deductions", "Retenues déjà prélevées"], ["salary_paid_through_bank", "Salaire domicilié / traçable", "bool"], ["salary_verified", "Salaire vérifié", "bool"]])}
      {employmentLabel && <p>Type d'emploi : {employmentLabel}.</p>}
      <Note label="Perspectives de l'emploi" text={detailText("employment_outlook")} />
    </>, true);
    add("Patrimoine du ménage", <>
      {fields([["personal_savings", "Épargne disponible"], ["personal_real_estate_value", "Immobilier"], ["personal_vehicle_value", "Véhicules"], ["personal_productive_assets", "Actifs productifs"], ["dependents_count", "Personnes à charge, hors demandeur", "count"]])}
      {!showActivity && <Note label="Qualité des créances" text={detailText("receivables_quality")} />}
      <Note label="Propriété des actifs" text={detailText("asset_ownership")} />
    </>, true);
  }
  if (showActivity) add("Activité indépendante", <>
    {fields(ACTIVITY)}
    <Note label="Commentaire sur l'activité" text={a.activity_comment || ""} />
    <Note label="Qualité des créances" text={detailText("receivables_quality")} />
    {alert(purchaseAlert, "Les achats retenus s'écartent de plus de 10 % des achats déclarés, ramenés au mois.")}
  </>, true);

  add("Stock", <>
    {hasProductionStock && <dl className="def-list two">{PRODUCTION_STOCKS.filter((stock) => numeric(a.analysis_details?.[stock.key]) != null).map((stock) => <div key={stock.key}><dt>{stock.label}</dt><dd>{formatMoney(numeric(a.analysis_details?.[stock.key]), currency)}</dd></div>)}</dl>}
    {stockExtra}
    {a.stock_count_verified === true && <p className="muted small">Inventaire vérifié.</p>}
    <ComparativeTables analysis={a} currency={currency} only="stocks" />
    <Note label="Commentaire sur le stock" text={detailText("stock_risks")} />
    {lineNotes("stocks", "name")}
    {alert(m.stock_details_complete === false, "Des lignes de stock sont incomplètes. Le total reste inconnu ; compléter les montants, y compris les zéros vérifiés.")}
    {alert(m.stock_reconciled === false, "Écart à expliquer : inventaire et stock déclaré.")}
  </>, hasStock && !groupStatements);

  add("Ventes et produits", <>
    <ComparativeTables analysis={a} currency={currency} only="products" />
    <Note label="Modèle économique" text={detailText("business_model")} />
    {lineNotes("products", "name")}
    <FinancialAnalysisDetails name="sales_observations" value={a.analysis_details || {}} currency={currency} expanded />
    <ComparativeTables analysis={a} currency={currency} only="sales" />
    <Note label="Vérification du chiffre d'affaires" text={detailText("sales_verification")} />
    {alert(m.product_details_complete === false, "Des fiches produits sont incomplètes. La marge reconstituée reste inconnue ; compléter les montants, y compris les zéros vérifiés.")}
    {alert(m.sales_reconciled === false, "Écart à expliquer : ventes détaillées et chiffre d'affaires.")}
    {alert(m.tpe_sales_aligned === false, "Le chiffre d'affaires retenu s'écarte de plus de 10 % du chiffre déclaré, ramené au mois.")}
  </>, hasSales && !groupStatements);

  if (corp) add("Bilan", <>
    <h5>Actif</h5>{fields(ASSETS)}
    <Note label="Qualité des créances" text={detailText("receivables_quality")} />
    <Note label="Propriété des actifs" text={detailText("asset_ownership")} />
    <h5>Passif et fonds propres</h5>{fields(DEBTS)}
    {balanceExtras}
    {alert(n("equity_gap") != null && n("equity_gap") !== 0, "Les fonds propres déclarés et reconstitués présentent un écart à expliquer.")}
    {modeSentence && <p className="muted small">{modeSentence}</p>}
  </>, true);

  add("Trésorerie depuis le dernier achat", <>
    {(detailText("last_purchase_date") || detailText("cash_control_date")) && <p className="muted small">{detailText("last_purchase_date") ? `Dernier achat : ${shortDate(detailText("last_purchase_date"))}. ` : ""}{detailText("cash_control_date") ? `Contrôle : ${shortDate(detailText("cash_control_date"))}.` : ""}</p>}
    {a.cash_position_verified === true && <p className="muted small">Caisse et banque vérifiées.</p>}
    <ComparativeTables analysis={a} currency={currency} only="cash" />
    {alert(m.tpe_cash_charges_basis === "PRORATA", "Les charges sont étalées sur 30 jours. Un loyer ou une échéance payée en une fois peut expliquer l'écart. Les charges réellement payées lèvent cette estimation.")}
    {m.tpe_cash_long_window === true && <p className="muted small">La période dépasse 31 jours. Le chiffre journalier multiplié par les jours suppose une activité continue.</p>}
    {alert(m.tpe_cash_incomplete === true, "Contrôle incomplet : il faut le chiffre journalier retenu, et soit les charges payées, soit des charges mensuelles hors achats déjà saisies.")}
    {alert(m.tpe_cash_conclusion === "TO_JUSTIFY", "Le contrôle de trésorerie depuis le dernier achat est à justifier.")}
    {alert(m.tpe_cash_conclusion === "INCOHERENT", "Le contrôle de trésorerie depuis le dernier achat est incohérent avec le chiffre journalier retenu.")}
    <Note label="Contrôle de trésorerie" text={detailText("cash_check_comment")} />
  </>, hasCash && !groupStatements);

  const minimalOpen = a.analysis_details?.minimal_cash_open === "yes" && path !== "STATEMENTS" && path !== "SALARY" && !((path === "ACTIVITY" || path === "MIXED" || (path === "GROUP" && groupOpen)) && resolveStatementBasis(a.analysis_details) === "STATEMENTS");
  add("Trésorerie minimale", <>
    <p className="muted small">Document court, distinct des états et de la reconstitution des ventes. Le surplus ne modifie ni le chiffre d&apos;affaires, ni la capacité, ni le DSCR.</p>
    <Note label="Période" text={[detailText("minimal_cash_label"), detailText("minimal_cash_start") && detailText("minimal_cash_end") ? `${shortDate(detailText("minimal_cash_start"))} – ${shortDate(detailText("minimal_cash_end"))}` : ""].filter(Boolean).join(" · ")} />
    <dl className="def-list two">
      {([
        ["minimal_cash_opening", "Trésorerie d'ouverture"],
        ["minimal_cash_inflows", "Entrées"],
        ["minimal_cash_outflows", "Sorties"],
        ["minimal_cash_closing", "Trésorerie de clôture"],
      ] as const).map(([key, label]) => <div key={key}><dt>{label}</dt><dd>{hasDetail(key) ? formatMoney(numeric(a.analysis_details?.[key]), currency) : "—"}</dd></div>)}
      <div><dt>Surplus de la période</dt><dd>{n("minimal_cash_surplus") == null ? "—" : money("minimal_cash_surplus")}</dd></div>
      <div><dt>Clôture calculée</dt><dd>{n("minimal_cash_theoretical_closing") == null ? "—" : money("minimal_cash_theoretical_closing")}</dd></div>
      <div><dt>Écart</dt><dd>{n("minimal_cash_gap") == null ? "—" : money("minimal_cash_gap")}</dd></div>
    </dl>
    {n("minimal_cash_gap") != null && n("minimal_cash_gap") !== 0 && <p className="form-error">Écart entre la clôture lue et la clôture calculée. Il s&apos;explique, il ne corrige pas les lignes.</p>}
    <Note label="Commentaire" text={detailText("minimal_cash_comment")} />
    {detailText("minimal_cash_document") && <p className="muted small">Un document est joint à cette période.</p>}
  </>, minimalOpen);

  add("Exercice précédent", <>
    <p className="muted small">Les deux périodes du compte de résultat doivent avoir la même durée. Une case vide reste vide.</p>
    <ComparativeTables analysis={a} currency={currency} only="statement" />
    <ComparativeTables analysis={a} currency={currency} only="history" />
    {lineNotes("history", "period")}
  </>, hasStatement || hasHistory);

  add("Engagements", <>
    <FinancialAnalysisDetails name="debts" value={a.analysis_details || {}} currency={currency} expanded />
    {externalCredits.map((credit, index) => <article className="external-credit-read" key={`${credit.institution}-${index}`}>
      <h5>{credit.institution || `Crédit ${index + 1}`}</h5>
      <dl className="def-list two">
        {credit.grant_date && <div><dt>Date d'octroi</dt><dd>{shortDate(credit.grant_date)}</dd></div>}
        {credit.final_due_date && <div><dt>Dernière échéance</dt><dd>{shortDate(credit.final_due_date)}</dd></div>}
        {credit.initial_amount && <div><dt>Montant initial</dt><dd>{formatMoney(numeric(credit.initial_amount), currency)}</dd></div>}
        {credit.monthly_payment && <div><dt>Mensualité</dt><dd>{formatMoney(numeric(credit.monthly_payment), currency)}</dd></div>}
        {credit.outstanding && <div><dt>Encours restant</dt><dd>{formatMoney(numeric(credit.outstanding), currency)}</dd></div>}
        {credit.max_days_late && <div><dt>Retard maximum constaté</dt><dd>{credit.max_days_late} j</dd></div>}
        {credit.bureau_checked && <div><dt>Centrale des risques / BIC</dt><dd>{credit.bureau_checked === "yes" ? `Consultée${credit.bureau_date ? ` le ${shortDate(credit.bureau_date)}` : ""}` : "Non consultée"}</dd></div>}
        {credit.incidents && <div><dt>Incidents de paiement</dt><dd>{credit.incidents === "yes" ? "Oui" : "Non"}</dd></div>}
      </dl>
      <Note label="Détails des incidents / engagements externes" text={credit.incidents_detail} />
    </article>)}
    {hasExistingDebt && <dl className="def-list two">
      {a.existing_debt_institution && <div><dt>Institution</dt><dd>{a.existing_debt_institution}</dd></div>}
      {Number(a.existing_debt_initial_amount) > 0 && <div><dt>Montant initial</dt><dd>{formatMoney(a.existing_debt_initial_amount, currency)}</dd></div>}
      {Number(a.existing_debt_monthly) > 0 && <div><dt>Mensualité</dt><dd>{formatMoney(a.existing_debt_monthly, currency)}</dd></div>}
      {Number(a.ongoing_credit_balance) > 0 && <div><dt>Encours restant</dt><dd>{formatMoney(a.ongoing_credit_balance, currency)}</dd></div>}
    </dl>}
    {alert(m.debt_details_complete === false, "Des lignes d'engagements sont incomplètes. Le total reste inconnu ; compléter les montants, y compris les zéros vérifiés.")}
    {alert(m.outstanding_reconciled === false, "Écart à expliquer : engagements détaillés et encours déclaré.")}
    {hasBureau && <dl className="def-list two">
      <div><dt>Centrale des risques / BIC</dt><dd>{a.credit_bureau_checked ? `Consultée${a.credit_bureau_date ? ` le ${shortDate(a.credit_bureau_date)}` : ""}` : "Non consultée"}</dd></div>
      <div><dt>Incidents de paiement</dt><dd>{a.has_payment_incidents ? "Oui" : "Non"}</dd></div>
      {a.max_days_late ? <div><dt>Retard max constaté</dt><dd>{a.max_days_late} j</dd></div> : null}
    </dl>}
    {(a.prior_loans_count > 0 || (a.prior_repayment_rate != null && a.prior_repayment_rate !== "") || !!a.prior_max_delay_days) && <dl className="def-list two">
      {a.prior_loans_count ? <div><dt>Crédits antérieurs, interne</dt><dd>{a.prior_loans_count}</dd></div> : null}
      {a.prior_repayment_rate != null && a.prior_repayment_rate !== "" && <div><dt>Taux de remboursement historique</dt><dd>{Number(a.prior_repayment_rate).toFixed(1)} %</dd></div>}
      {a.prior_max_delay_days ? <div><dt>Retard max historique</dt><dd>{a.prior_max_delay_days} j</dd></div> : null}
    </dl>}
    {!externalCredits.length && <Note label="Incidents" text={a.incidents_comment || ""} />}
    <Note label="Référence BIC" text={detailText("bureau_reference")} />
    <Note label="Écarts BIC" text={detailText("bureau_discrepancies")} />
    {!hasBank && <Note label="Fonctionnement bancaire" text={bankBehavior} />}
  </>, hasDebts);

  add("Flux créditeurs", <>
    <FinancialAnalysisDetails name="bank_flows" value={a.analysis_details || {}} currency={currency} expanded />
    <Note label="Fonctionnement bancaire" text={bankBehavior} />
  </>, hasBank);

  add("Prévisions de trésorerie", <>
    {fields([["projected_monthly_inflows", "Encaissements mensuels synthétiques hors nouveau crédit"], ["projected_monthly_outflows", "Sorties mensuelles synthétiques hors service de dette"]])}
    {forecastExtra}
    {!!rows.length && <>
      <ForecastChart rows={rows} currency={currency} />
      <div className="table-scroll"><table className="table"><caption>Plan mensuel, dette et investissement déduits ; comparaison à l'échéancier simulé sur les mois saisis</caption><thead><tr>{["Mois", "Ouverture", "Flux net", "Clôture", "Nouveau crédit saisi", "Échéancier attendu", "Écart"].map((label, index) => <th scope="col" key={`${label}-${index}`}>{label}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={index}><td>{String(row.month || "Mois manquant")}</td>{["opening", "net_flow", "closing", "new_service", "expected_new_service", "service_gap"].map((key) => <td key={key} className="num">{formatMoney(numeric(row[key]), currency)}</td>)}</tr>)}</tbody></table></div>
      {lineNotes("cashflow", "month")}
    </>}
    {!rows.length && <FinancialAnalysisDetails name="cashflow" value={a.analysis_details || {}} currency={currency} expanded />}
    <Note label="Saisonnalité" text={detailText("seasonality")} />
    <Note label="Commentaire sur la trésorerie" text={a.cashflow_comment || ""} />
    {alert(rows.length > 0 && m.forecast_opening_balance == null, "Trésorerie cumulée indisponible : le solde d'ouverture ou un mois successif manque. Un flux négatif n'est pas nécessairement un solde de trésorerie négatif.")}
    {alert(m.forecast_service_reconciled === false, "Écart à expliquer : prévisions et échéancier du nouveau crédit.")}
  </>, hasForecast);

  add("Références", <FinancialAnalysisDetails name="references" value={a.analysis_details || {}} currency={currency} expanded />, detailRows(a.analysis_details, "references").length > 0);

  const campaignOpen = a.analysis_details?.campaign_open === "yes" && path !== "SALARY";
  const creationOpen = a.analysis_details?.activity_creation === "yes" && path !== "SALARY";
  const detailMoney = (key: string) => {
    const value = a.analysis_details?.[key];
    return value == null || value === "" ? "—" : formatMoney(numeric(value), currency);
  };
  add("Campagne", <>
    <Note label="Nom" text={detailText("campaign_name")} />
    <Note label="Culture, élevage ou transformation" text={detailText("campaign_production")} />
    <Note label="Surface, cheptel ou volume" text={detailText("campaign_scale")} />
    <Note label="Mois où l'argent entre" text={detailText("campaign_inflow_months")} />
    <Note label="Calendrier" text={detailText("campaign_calendar")} />
    <Note label="Débouchés et prix" text={detailText("campaign_sales")} />
    <dl className="def-list two">
      <div><dt>Stock d&apos;intrants, hors revenu</dt><dd>{detailMoney("campaign_input_stock")}</dd></div>
      <div><dt>Stock de récolte, hors revenu</dt><dd>{detailMoney("campaign_harvest_stock")}</dd></div>
      <div><dt>Recettes de la campagne</dt><dd>{detailMoney("campaign_revenue")}</dd></div>
      <div><dt>Charges de la campagne</dt><dd>{detailMoney("campaign_charges")}</dd></div>
      <div><dt>Surplus de la campagne</dt><dd>{n("campaign_surplus") == null ? "—" : money("campaign_surplus")}</dd></div>
      <div><dt>Surplus retenu par mois</dt><dd>{n("campaign_monthly_surplus") == null ? "—" : money("campaign_monthly_surplus")}</dd></div>
    </dl>
    <p className="muted small">{n("campaign_monthly_surplus") == null ? "Le surplus n'est pas encore connu : la capacité reste celle du mois ordinaire." : `La capacité retient ${money("campaign_surplus")} réparti sur ${String(m.campaign_duration_months ?? "—")} mois. Un mois de vente ordinaire n'est plus la base. Le taux d'endettement ne change pas.`}</p>
    <Note label="Réserves" text={detailText("campaign_comment")} />
  </>, campaignOpen);
  add("Création", <>
    <p className="muted small">Le coût, l&apos;apport et la quotité viennent du dossier. Ils ne sont pas ressaisis dans l&apos;analyse. Le chiffre d&apos;affaires passé n&apos;est pas exigé.</p>
    <dl className="def-list two">
      <div><dt>Coût total du projet</dt><dd>{context?.project_total_cost == null ? "—" : formatMoney(context.project_total_cost, currency)}</dd></div>
      <div><dt>Apport personnel</dt><dd>{context?.personal_contribution == null ? "—" : formatMoney(context.personal_contribution, currency)}</dd></div>
      <div><dt>Quotité financée</dt><dd>{context?.financed_quota == null ? "—" : `${context.financed_quota} %`}</dd></div>
      <div><dt>Date de création de l&apos;activité</dt><dd>{context?.activity_start_date ? formatDate(context.activity_start_date) : "—"}</dd></div>
    </dl>
    <Note label="Ce qui est créé" text={detailText("creation_activity")} />
    <Note label="Délai avant les premières recettes" text={detailText("creation_ramp")} />
    <Note label="Hypothèses de la prévision" text={detailText("creation_assumptions")} />
    <p className="muted small">{m.dscr_basis === "forecast" ? "Le DSCR s'appuie sur la prévision de trésorerie." : "La prévision de trésorerie n'est pas encore renseignée : elle doit porter le DSCR."}</p>
  </>, creationOpen);
  add("Projet", <>
    <Note label="Coût du projet" text={detailText("project_cost")} />
    <Note label="Apport propre" text={detailText("own_contribution")} />
    <Note label="Plan de financement" text={detailText("financing_plan")} />
  </>, !!(detailText("project_cost") || detailText("own_contribution") || detailText("financing_plan")));

  const placed = new Set([
    "business_model", "seasonality", "sales_verification", "stock_risks", "receivables_quality", "asset_ownership",
    "household_income_evidence", "employment_outlook", "project_cost", "own_contribution", "financing_plan",
    "stress_assumptions", "monitoring_plan", "bureau_reference", "bureau_discrepancies", "banking_behavior", "cash_check_comment",
    ...Object.keys(FINANCIAL_SUPPLEMENTS), ...Object.keys(ANALYSIS_TABLES),
    "sales_method", "purchase_method", "last_purchase_date", "cash_control_date", "activity_days_per_month",
    "retained_daily_sales", "sales_control_monthly", "purchase_average", "purchase_frequency", "safety_provision_pct",
    "last_purchase_amount", "cash_at_last_purchase", "charges_paid_in_window", "other_outflows_in_window",
    "observed_cash", "cash_tolerance_pct", "cash_detail_mode", "fixed_assets_detail_mode", "statement_basis", "manufactures", "group_has_activity", "group_activity_description",
    "campaign_open", "activity_creation", "campaign_name", "campaign_production", "campaign_scale", "campaign_inflow_months", "campaign_calendar", "campaign_sales", "campaign_comment",
    "campaign_revenue", "campaign_charges", "campaign_input_stock", "campaign_harvest_stock", "creation_activity", "creation_ramp", "creation_assumptions",
    "minimal_cash_open", "minimal_cash_label", "minimal_cash_start", "minimal_cash_end", "minimal_cash_opening", "minimal_cash_inflows", "minimal_cash_outflows", "minimal_cash_closing", "minimal_cash_comment", "minimal_cash_document",
    "extra_income", "extra_charges",
    ...PRODUCTION_IDENTITY.map((field) => field.key), ...PRODUCTION_STOCKS.map((stock) => stock.key),
  ]);
  const leftovers = Object.entries(a.analysis_details || {}).filter(([key, value]) => !placed.has(key) && !key.endsWith("_detail_mode") && typeof value === "string" && value.trim());
  add("Fiabilité", <>
    <dl className="def-list two">
      <div><dt>Fiabilité des informations</dt><dd>{({ DECLARED: "Déclarées", PARTIALLY_VERIFIED: "Partiellement vérifiées", VERIFIED: "Vérifiées", AUDITED: "Comptes audités" } as Record<string, string>)[a.information_quality] || "Non renseignée"}</dd></div>
      {a.financial_statement_date && <div><dt>Date d'arrêté</dt><dd>{shortDate(a.financial_statement_date)}</dd></div>}
      {a.primary_repayment_source && <div><dt>Source de remboursement</dt><dd>{a.primary_repayment_source}</dd></div>}
      <div><dt>Pièces financières vérifiées</dt><dd>{a.financial_documents_verified ? "Oui" : "Non"}</dd></div>
      {a.bank_statement_months != null && <div><dt>Mois de relevés examinés</dt><dd>{a.bank_statement_months}</dd></div>}
      <div><dt>Visite confirmée</dt><dd>{a.field_visit_confirmed ? "Oui" : "Non"}</dd></div>
      {!hasStock && <div><dt>Inventaire vérifié</dt><dd>{a.stock_count_verified ? "Oui" : "Non"}</dd></div>}
      {!hasCash && <div><dt>Caisse / banque vérifiées</dt><dd>{a.cash_position_verified ? "Oui" : "Non"}</dd></div>}
    </dl>
    <Note label="Commentaire de vérification" text={a.verification_comment || ""} />
    {!!Object.keys(a.custom_fields || {}).length && <dl className="def-list two">{Object.entries(a.custom_fields || {}).map(([key, value]) => {
      const definition = a.custom_field_definitions?.find((field) => field.id === key);
      return <div key={key}><dt>{definition?.label || key}</dt><dd>{format(value, definition?.type === "boolean" ? "bool" : "text")}</dd></div>;
    })}</dl>}
    {leftovers.map(([key, value]) => <Note key={key} label={key} text={String(value)} />)}
  </>, true);

  const topics = <>{blocks.map((block) => <Theme key={block.title} title={block.title}>{block.body}</Theme>)}</>;


  const indicators = <>
    <div className="analysis-block">
      <h4 className="subsection-title">Synthèse de capacité — montants mensuels</h4>
      {context && <p className="muted small">{context.legacy ? "Recalcul indicatif d'un dossier historique" : context.frozen ? "Recalcul selon les règles conservées à la soumission" : "Calcul selon les conditions actuelles du dossier"} du {formatDate(context.calculated_at)} · montant {context.amount_label} : {formatMoney(context.amount, currency)} · durée {context.duration_months} mois · {CREDIT_LABELS.periodicity[context.periodicity] || context.periodicity} · {CREDIT_LABELS.repayment_mechanism[context.mechanism] || context.mechanism}.
        {context.rates.interest_rate != null && ` Taux annuel ${context.rates.interest_rate} %, épargne obligatoire ${context.rates.mandatory_savings_rate ?? 0} % du capital par échéance.`}</p>}
      {context?.legacy && <p className="form-error" role="note">Les règles utilisées lors de la décision initiale n'ont pas été archivées pour ce dossier historique. Ce recalcul ne reconstitue pas la décision passée ; les indicateurs enregistrés sont consultables séparément ci-dessous.</p>}
      <div className="metric-grid">
        {corp ? <>
          <div className="metric"><span className="metric-label">CA / {period}</span><span className="metric-value">{formatMoney(a.turnover, currency)}</span></div>
          <div className="metric"><span className="metric-label">{path === "STATEMENTS" ? "Résultat de l'exercice retenu" : "Résultat reconstitué"} / {period}</span><span className="metric-value">{formatMoney(a.net_result, currency)}</span></div>
          <div className={`metric ${a.flags.dscr_ok === true ? "metric-ok" : a.flags.dscr_ok === false ? "metric-warn" : ""}`}><span className="metric-label">DSCR global</span><span className="metric-value">{n("global_dscr") == null ? "—" : `${n("global_dscr")} ×`}</span></div>
        </> : group ? <>
          <div className="metric"><span className="metric-label">Membres / cotisants actifs</span><span className="metric-value">{a.members_count ?? "—"} / {a.active_contributing_members ?? "—"}</span></div>
          {card("Recettes collectives / mois", "collective_income")}
          {card("Charges collectives / mois", "collective_charges")}
        </> : <>{card("Revenus déclarés / mois", "declared_income")}{card("Revenus retenus après pondération / mois", "weighted_income")}{card("Charges du ménage / mois", "household_charges_monthly")}</>}
        {m.dscr_basis === "forecast" && !corp && <div className={`metric ${a.flags.dscr_ok === true ? "metric-ok" : a.flags.dscr_ok === false ? "metric-warn" : ""}`}><span className="metric-label">DSCR sur la prévision</span><span className="metric-value">{n("global_dscr") == null ? "—" : `${n("global_dscr")} ×`}</span></div>}
        {card("Capacité avant nouveau crédit, dette existante déduite", "repayment_capacity")}
        {card("Équivalent mensuel de la nouvelle échéance institution maximale", "installment")}
        {card("Épargne obligatoire — équivalent mensuel", "monthly_savings")}
        {card("Effort total : dettes existantes + nouveau crédit + épargne", "total_cash_effort")}
        <div className={`metric ${a.flags.capacity_ok === true ? "metric-ok" : a.flags.capacity_ok === false ? "metric-warn" : ""}`}><span className="metric-label">{corp || group ? "Marge de trésorerie après crédit" : "Reste à vivre après crédit et épargne"}</span><span className="metric-value">{money("safety_margin")}</span><small>{a.flags.capacity_ok == null ? "Non calculable" : a.flags.capacity_ok ? "Effort couvert" : "Effort non couvert"}</small></div>
        {card("Effort moyen sur la durée (hors dettes existantes)", "average_monthly_cash_payment")}
        {card("Pic d'échéance du nouveau crédit, épargne comprise", "peak_cash_payment")}
      </div>
      {n("campaign_monthly_surplus") != null && <p className="muted small">La capacité retient le surplus de campagne {money("campaign_surplus")} réparti sur {String(m.campaign_duration_months ?? "—")} mois, soit {money("campaign_monthly_surplus")} par mois. Le taux d&apos;endettement reste calculé sur le revenu observé.</p>}
      {!!context?.purpose_type && <p className="muted small">{purposeTestText(context.purpose_type, path === "RECONSTITUTED" || ((path === "ACTIVITY" || path === "MIXED" || (path === "GROUP" && groupOpen && !groupStatements)) && resolveStatementBasis(a.analysis_details) !== "STATEMENTS"))}</p>}
      <p className="muted small">Le pic à financer et l'effort moyen sont distincts. Pour un in fine ou un remboursement saisonnier, vérifier les dates et ressources disponibles à chaque échéance. Les frais initiaux ne sont pas des charges mensuelles ; les prévisions doivent inclure les autres prélèvements réels.</p>
      {n("tpe_safety_pct") != null && <>
        <h5>Retenue de prudence</h5>
        <p className="muted small">Base : capacité avant le nouveau crédit, dettes existantes déjà déduites. Les échéances en cours ne sont pas retirées une seconde fois. Cette retenue n'est pas le taux d'endettement.</p>
        <div className="metric-grid">
          {card("Capacité avant le nouveau crédit", "tpe_safety_base")}
          {card(`Retenue ${n("tpe_safety_pct")} %`, "tpe_safety_provision")}
          {card("Disponible pour la nouvelle échéance", "tpe_safety_available")}
          <div className={`metric ${m.tpe_safety_ok === true ? "metric-ok" : m.tpe_safety_ok === false ? "metric-warn" : ""}`}><span className="metric-label">Couverture de la nouvelle échéance</span><span className="metric-value">{n("tpe_safety_coverage") == null ? "—" : `${n("tpe_safety_coverage")} ×`}</span></div>
        </div>
      </>}
      {corp && <div className="metric-grid">{card("Flux mensuel avant dette, après ajustements renseignés", "cash_before_debt")}{card("Flux mensuel prudent retenu pour le DSCR", "repayment_cash_flow")}{card("Écart fonds propres reconstitués − déclarés", "equity_gap")}</div>}
      {!corp && !group && (a.has_side_activity || a.individual_profile === "INDEPENDANT" || a.individual_profile === "MIXTE") && <div className="metric-grid">{card("Résultat net d'activité / mois avant pondération", "activity_net")}{card("Actif de l'activité", "activity_assets")}{card("BFR simplifié de l'activité", "activity_working_capital_need")}</div>}
      {!corp && !group && <p className="muted small">Pondération retenue sur les revenus variables et le bénéfice d'activité : {n("income_weight") ?? "—"} %. Les pertes d'activité sont retenues intégralement.</p>}
      {(path === "RECONSTITUTED" || path === "ACTIVITY" || path === "MIXED" || (path === "GROUP" && groupOpen && !groupStatements)) && (a.analysis_details?.sales_method || a.analysis_details?.purchase_method || n("tpe_monthly_sales") != null) && <>
        <h5>Reconstitution TPE</h5>
        <p className="muted small">Méthode de ventes : {({ CAHIER: "cahier ou factures", BANK: "relevés ou Mobile Money", THREE_DAYS: "trois jours observés", HYPOTHESIS: "trois hypothèses", STOCK: "inventaire", OTHER: "autre" } as Record<string, string>)[String(a.analysis_details?.sales_method || "")] || "non utilisée"}. Méthode d'achats : {({ INVOICES: "factures", LEDGER: "cahier d'achats", COST_RATE: "taux de coût de la marge", OTHER: "autre" } as Record<string, string>)[String(a.analysis_details?.purchase_method || "")] || "non utilisée"}.</p>
        <div className="metric-grid">
          {card("CA journalier retenu", "tpe_retained_daily_sales")}
          {card("CA mensuel retenu", "tpe_monthly_sales")}
          {card("CA déclaré ramené au mois", "tpe_declared_monthly_sales")}
          {card("Écart de chiffre d'affaires", "tpe_sales_gap")}
          {card("Achats mensuels retenus", "tpe_monthly_purchases")}
          {card("Achats déclarés ramenés au mois", "tpe_declared_monthly_purchases")}
        </div>
        {n("tpe_margin_rate_pct") != null && <p className="muted small">Taux de marge issu des fiches produits : {n("tpe_margin_rate_pct")} %. Taux de coût : {n("tpe_cost_rate_pct") ?? "—"} %.</p>}
        {n("tpe_tmc_total") != null && <div className="metric-grid">{card("TMC total des institutions", "tpe_tmc_total")}{card("Soldes bancaires détaillés", "tpe_bank_balance_total")}{card("Moyenne des TMC mensuels", "tpe_average_tmc")}</div>}
      </>}
      {(path === "RECONSTITUTED" || path === "ACTIVITY" || path === "MIXED" || (path === "GROUP" && groupOpen && !groupStatements)) && <div className="metric-grid">{card("Écart ventes reconstituées − CA déclaré", "sales_gap")}{card("Écart inventaire net − stock déclaré", "stock_gap")}{card("Écart encours détaillés − encours déclaré", "outstanding_gap")}{card("Impayés détaillés", "detailed_debt_arrears")}{card("Marge reconstituée par produits", "reconstituted_margin")}</div>}
      {!!rows.length && <div className="metric-grid">{card("Trésorerie d'ouverture", "forecast_opening_balance")}{card("Plus faible flux mensuel", "forecast_lowest_flow")}{card("Plus faible solde de clôture", "forecast_lowest_balance")}{card("Trésorerie de clôture finale", "forecast_closing_balance")}</div>}
      {!!rows.length && <p className="muted small">Mois à flux négatif : {n("forecast_negative_flow_months") ?? "—"}. Mois à trésorerie de clôture négative : {n("forecast_cash_deficit_months") ?? "Non calculable"}.</p>}
      {warnings.map((warning) => <p className="form-error" role="status" key={warning}>{warning}</p>)}
    </div>
    <div className="analysis-block">
      <h4 className="subsection-title">Formules, seuils et interprétation</h4>
      <p className="muted small">« — » indique une donnée absente, une base non positive ou un calcul non applicable, jamais un zéro implicite. Les seuils sont ceux du dossier.</p>
      <div className="table-scroll"><table className="table"><thead><tr>{["Indicateur", "Valeur", "Base de calcul", "Seuil", "Lecture"].map((label) => <th scope="col" key={label}>{label}</th>)}</tr></thead><tbody>{specs.map((spec) => {
        const value = n(spec.key);
        const threshold = spec.threshold ? a.thresholds[spec.threshold] : undefined;
        const status = spec.flag ? m.flags[spec.flag] : undefined;
        return <tr key={spec.key}><th scope="row">{spec.label}</th><td>{spec.unit ? value == null ? "—" : `${value.toLocaleString("fr-FR", { maximumFractionDigits: 2 })} ${spec.unit}` : formatMoney(value, currency)}</td><td>{spec.formula}</td><td>{threshold == null ? "Non défini" : `${spec.min ? "≥" : "≤"} ${threshold.toLocaleString("fr-FR")} ${spec.unit || currency}`}</td><td>{status === false ? "Non conforme" : status === true ? "Conforme" : value == null ? "Non calculable" : "Informatif"}</td></tr>;
      })}</tbody></table></div>
      <p className="muted small">Sous stress, les charges restent présentes : baisse du CA ou des revenus de {a.thresholds.stress_pct} %, hausse supplémentaire des achats {String(a.analysis_details?.purchase_stress_pct || 0)} %{corp ? ` et décalage clients de ${a.analysis_details?.receivable_delay_days || 0} jours` : ""}.</p>
      {!corp && <p>Reste disponible mensuel sous stress : <strong>{money("stress_residual")}</strong>.</p>}
    </div>
    {a.recorded_indicators && <div className="analysis-block">
      <h4 className="subsection-title">Comparaison avec les derniers indicateurs enregistrés</h4>
      <p className="muted small">Enregistrement du {formatDate(a.recorded_indicators.updated_at)}. La consultation affiche les calculs courants sans réécrire cet historique.</p>
      <div className="table-scroll"><table className="table"><thead><tr><th scope="col">Indicateur</th><th scope="col">Enregistré</th><th scope="col">Calcul courant</th></tr></thead><tbody>{([ ["new_installment", "Échéance institution maximale"], ["repayment_capacity", "Capacité mensuelle avant nouveau crédit"], ["debt_ratio", "Taux d'endettement (%)"], ["dscr", "DSCR global (×)"], ["internal_score", "Score (/100)"] ] as const).filter(([key]) => corp || key !== "dscr" || m.dscr_basis === "forecast").map(([key, label]) => <tr key={key}><th scope="row">{label}</th><td>{format(a.recorded_indicators?.[key], key === "new_installment" || key === "repayment_capacity" ? "money" : "count")}</td><td>{format(a[key], key === "new_installment" || key === "repayment_capacity" ? "money" : "count")}</td></tr>)}</tbody></table></div>
    </div>}
  </>;

  if (part === "topics") return topics;
  return indicators;
}
