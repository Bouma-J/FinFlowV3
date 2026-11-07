export type StatementPiece = "income" | "balance" | "cashflow" | "notes";

export interface StatementLine {
  key: string;
  label: string;
}

export interface StatementGroup {
  title: string;
  lines: StatementLine[];
}

export interface FinancialStatement {
  id: string;
  label: string;
  start_date: string;
  end_date: string;
  nature: "" | "CLOSED" | "INTERIM";
  prepared_by: "" | "EXPERT" | "FIRM" | "CLIENT";
  certified: "" | "yes" | "no";
  comment: string;
  income: Record<string, string>;
  balance: Record<string, string>;
  cashflow: Record<string, string>;
  notes: Record<string, string>;
  documents: Record<StatementPiece, string>;
}

export const STATEMENT_PIECES: { key: StatementPiece; label: string }[] = [
  { key: "income", label: "Compte de résultat" },
  { key: "balance", label: "Bilan" },
  { key: "cashflow", label: "Tableau des flux de trésorerie" },
  { key: "notes", label: "Notes annexes" },
];

export const INCOME_GROUPS: StatementGroup[] = [
  { title: "Activité commerciale", lines: [
    { key: "sales_goods", label: "Ventes de marchandises" },
    { key: "purchases_goods", label: "Achats de marchandises" },
    { key: "variation_goods", label: "Variation de stocks de marchandises" },
  ] },
  { title: "Production et services", lines: [
    { key: "sales_manufactured", label: "Ventes de produits fabriqués" },
    { key: "sales_services", label: "Travaux et services vendus" },
    { key: "accessory_products", label: "Produits accessoires" },
    { key: "stored_production", label: "Production stockée ou déstockage" },
    { key: "capitalized_production", label: "Production immobilisée" },
    { key: "operating_subsidies", label: "Subventions d'exploitation" },
    { key: "other_operating_products", label: "Autres produits" },
    { key: "operating_charge_transfers", label: "Transferts de charges d'exploitation" },
  ] },
  { title: "Consommations", lines: [
    { key: "purchases_materials", label: "Achats de matières premières et fournitures liées" },
    { key: "variation_materials", label: "Variation de stocks de matières premières" },
    { key: "other_purchases", label: "Autres achats" },
    { key: "variation_supplies", label: "Variation de stocks d'autres approvisionnements" },
    { key: "transport", label: "Transports" },
    { key: "external_services", label: "Services extérieurs" },
    { key: "taxes", label: "Impôts et taxes" },
    { key: "other_operating_charges", label: "Autres charges" },
    { key: "personnel", label: "Charges de personnel" },
  ] },
  { title: "Exploitation, financier et hors activités ordinaires", lines: [
    { key: "operating_reversals", label: "Reprises d'amortissements, de provisions et de dépréciations" },
    { key: "operating_depreciation", label: "Dotations aux amortissements, aux provisions et aux dépréciations" },
    { key: "financial_income", label: "Revenus financiers" },
    { key: "financial_reversals", label: "Reprises financières" },
    { key: "financial_charge_transfers", label: "Transferts de charges financières" },
    { key: "financial_expenses", label: "Frais financiers" },
    { key: "financial_depreciation", label: "Dotations financières" },
    { key: "disposal_proceeds", label: "Produits de cession d'immobilisations" },
    { key: "other_hao_income", label: "Autres produits hors activités ordinaires" },
    { key: "disposal_book_value", label: "Valeurs comptables des immobilisations cédées" },
    { key: "other_hao_charges", label: "Autres charges hors activités ordinaires" },
    { key: "employee_participation", label: "Participation des travailleurs" },
    { key: "income_tax", label: "Impôts sur le résultat" },
    { key: "net_result_read", label: "Résultat net lu sur l'état" },
  ] },
];

export const BALANCE_GROUPS: StatementGroup[] = [
  { title: "Actif immobilisé", lines: [
    { key: "intangible_development", label: "Frais de développement et de prospection" },
    { key: "intangible_rights", label: "Brevets, licences, logiciels et droits similaires" },
    { key: "intangible_goodwill", label: "Fonds commercial et droit au bail" },
    { key: "intangible_other", label: "Autres immobilisations incorporelles" },
    { key: "intangible_in_progress", label: "Immobilisations incorporelles en cours" },
    { key: "intangible_advances", label: "Avances et acomptes sur immobilisations incorporelles" },
    { key: "land", label: "Terrains" },
    { key: "buildings", label: "Bâtiments" },
    { key: "fixtures", label: "Aménagements, agencements et installations" },
    { key: "equipment", label: "Matériel, mobilier et actifs biologiques" },
    { key: "transport_equipment", label: "Matériel de transport" },
    { key: "tangible_advances", label: "Avances et acomptes sur immobilisations corporelles" },
    { key: "investments", label: "Titres de participation" },
    { key: "other_financial_assets", label: "Autres immobilisations financières" },
  ] },
  { title: "Actif circulant", lines: [
    { key: "hao_assets", label: "Actif circulant hors activités ordinaires" },
    { key: "stock_goods", label: "Marchandises" },
    { key: "stock_materials", label: "Matières premières et autres approvisionnements" },
    { key: "stock_wip", label: "En-cours" },
    { key: "stock_finished", label: "Produits fabriqués" },
    { key: "supplier_advances", label: "Fournisseurs, avances versées" },
    { key: "customers", label: "Clients" },
    { key: "other_receivables", label: "Autres créances" },
  ] },
  { title: "Trésorerie-actif", lines: [
    { key: "marketable_securities", label: "Titres de placement" },
    { key: "instruments_receivable", label: "Valeurs à encaisser" },
    { key: "cash_and_banks", label: "Banques, chèques postaux, caisse et assimilés" },
    { key: "translation_asset", label: "Écart de conversion-actif" },
  ] },
  { title: "Capitaux propres", lines: [
    { key: "capital", label: "Capital" },
    { key: "share_premium", label: "Primes liées au capital" },
    { key: "revaluation", label: "Écarts de réévaluation" },
    { key: "reserves", label: "Réserves" },
    { key: "retained_earnings", label: "Report à nouveau" },
    { key: "period_result", label: "Résultat net de l'exercice" },
    { key: "investment_grants", label: "Subventions d'investissement" },
    { key: "regulated_provisions", label: "Provisions réglementées" },
  ] },
  { title: "Dettes financières", lines: [
    { key: "borrowings", label: "Emprunts" },
    { key: "lease_debt", label: "Dettes de crédit-bail et contrats assimilés" },
    { key: "other_financial_debt", label: "Dettes financières diverses" },
    { key: "financial_provisions", label: "Provisions financières pour risques et charges" },
  ] },
  { title: "Passif circulant et trésorerie-passif", lines: [
    { key: "hao_liabilities", label: "Dettes circulantes hors activités ordinaires" },
    { key: "customer_advances", label: "Clients, avances reçues" },
    { key: "suppliers", label: "Fournisseurs d'exploitation" },
    { key: "tax_social", label: "Dettes fiscales et sociales" },
    { key: "other_liabilities", label: "Autres dettes" },
    { key: "short_provisions", label: "Provisions pour risques à court terme" },
    { key: "translation_liability", label: "Écart de conversion-passif" },
    { key: "discount_credit", label: "Banques, crédits d'escompte" },
    { key: "treasury_credit", label: "Banques, crédits de trésorerie" },
    { key: "bank_overdraft", label: "Banques, découverts" },
  ] },
];

export const CASHFLOW_LINES: StatementLine[] = [
  { key: "cafg", label: "Capacité d'autofinancement globale" },
  { key: "operating_bfr_change", label: "Variation du besoin en fonds de roulement d'exploitation" },
  { key: "operating_flow", label: "Flux de trésorerie des activités opérationnelles" },
  { key: "investing_flow", label: "Flux de trésorerie des activités d'investissement" },
  { key: "financing_flow", label: "Flux de trésorerie des activités de financement" },
  { key: "cash_change_read", label: "Variation de trésorerie lue sur l'état" },
  { key: "opening_cash", label: "Trésorerie d'ouverture" },
  { key: "closing_cash", label: "Trésorerie de clôture" },
];

export const NOTE_AMOUNT_LINES: StatementLine[] = [
  { key: "fixed_gross", label: "Immobilisations — brut" },
  { key: "fixed_depreciation", label: "Immobilisations — amortissements et dépréciations" },
  { key: "fixed_net", label: "Immobilisations — net lu" },
  { key: "fixed_acquisitions", label: "Immobilisations — acquisitions de l'exercice" },
  { key: "fixed_disposals", label: "Immobilisations — cessions de l'exercice" },
  { key: "stock_gross", label: "Stocks — brut" },
  { key: "stock_impairment", label: "Stocks — dépréciations" },
  { key: "stock_net", label: "Stocks — net lu" },
  { key: "receivable_gross", label: "Créances — brut" },
  { key: "receivable_impairment", label: "Créances — dépréciations" },
  { key: "receivable_net", label: "Créances — net lu" },
  { key: "debt_current", label: "Dettes à moins d'un an" },
  { key: "debt_noncurrent", label: "Dettes à plus d'un an" },
];

const INCOME_KEYS = INCOME_GROUPS.flatMap((group) => group.lines.map((line) => line.key));
const BALANCE_KEYS = BALANCE_GROUPS.flatMap((group) => group.lines.map((line) => line.key));
const CASHFLOW_KEYS = CASHFLOW_LINES.map((line) => line.key);
const NOTE_KEYS = [...NOTE_AMOUNT_LINES.map((line) => line.key), "headcount", "off_balance", "comment"];
const CHARGE_KEYS = ["personnel", "transport", "external_services", "taxes", "other_operating_charges", "operating_depreciation", "financial_expenses", "financial_depreciation"];
const NET_TERMS: [string, number][] = [
  ["sales_goods", 1], ["purchases_goods", -1], ["variation_goods", -1],
  ["sales_manufactured", 1], ["sales_services", 1], ["accessory_products", 1],
  ["stored_production", 1], ["capitalized_production", 1], ["operating_subsidies", 1],
  ["other_operating_products", 1], ["operating_charge_transfers", 1],
  ["purchases_materials", -1], ["variation_materials", -1], ["other_purchases", -1],
  ["variation_supplies", -1], ["transport", -1], ["external_services", -1],
  ["taxes", -1], ["other_operating_charges", -1], ["personnel", -1],
  ["operating_reversals", 1], ["operating_depreciation", -1],
  ["financial_income", 1], ["financial_reversals", 1], ["financial_charge_transfers", 1],
  ["financial_expenses", -1], ["financial_depreciation", -1],
  ["disposal_proceeds", 1], ["other_hao_income", 1], ["disposal_book_value", -1],
  ["other_hao_charges", -1], ["employee_participation", -1], ["income_tax", -1],
];

function blank(keys: string[]): Record<string, string> {
  return Object.fromEntries(keys.map((key) => [key, ""]));
}

function text(value: unknown): string {
  return typeof value === "string" || typeof value === "number" ? String(value) : "";
}

export function blankStatement(): FinancialStatement {
  const id = crypto.randomUUID().replace(/-/g, "");
  return {
    id,
    label: "",
    start_date: "",
    end_date: "",
    nature: "",
    prepared_by: "",
    certified: "no",
    comment: "",
    income: blank(INCOME_KEYS),
    balance: blank(BALANCE_KEYS),
    cashflow: blank(CASHFLOW_KEYS),
    notes: blank(NOTE_KEYS),
    documents: { income: "", balance: "", cashflow: "", notes: "" },
  };
}

function readMap(source: unknown, keys: string[]): Record<string, string> {
  const record = source && typeof source === "object" ? source as Record<string, unknown> : {};
  return Object.fromEntries(keys.map((key) => [key, text(record[key])]));
}

function oneOf<T extends string>(value: unknown, allowed: readonly T[]): T | "" {
  return typeof value === "string" && (allowed as readonly string[]).includes(value) ? value as T : "";
}

export function readStatements(details: unknown): FinancialStatement[] {
  const raw = details && typeof details === "object" ? (details as { financial_statements?: unknown }).financial_statements : undefined;
  if (!Array.isArray(raw)) return [];
  return raw.filter((row) => row && typeof row === "object").map((row) => {
    const item = row as Record<string, unknown>;
    const documents = item.documents && typeof item.documents === "object" ? item.documents as Record<string, unknown> : {};
    const nature = oneOf(item.nature, ["CLOSED", "INTERIM"] as const);
    const prepared = oneOf(item.prepared_by, ["EXPERT", "FIRM", "CLIENT"] as const);
    const certified = oneOf(item.certified, ["yes", "no"] as const);
    return {
      id: text(item.id),
      label: text(item.label),
      start_date: text(item.start_date),
      end_date: text(item.end_date),
      nature,
      prepared_by: prepared,
      certified,
      comment: text(item.comment),
      income: readMap(item.income, INCOME_KEYS),
      balance: readMap(item.balance, BALANCE_KEYS),
      cashflow: readMap(item.cashflow, CASHFLOW_KEYS),
      notes: readMap(item.notes, NOTE_KEYS),
      documents: {
        income: text(documents.income),
        balance: text(documents.balance),
        cashflow: text(documents.cashflow),
        notes: text(documents.notes),
      },
    };
  }).filter((row) => /^[a-z0-9]{8,64}$/.test(row.id));
}

export function amount(value: string | undefined): number | null {
  if (value == null || value.trim() === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

export function presentSum(source: Record<string, string>, keys: string[]): number | null {
  const present = keys.map((key) => amount(source[key])).filter((value): value is number => value !== null);
  if (!present.length) return null;
  return Math.round(present.reduce((total, value) => total + value, 0) * 100) / 100;
}

function signedSum(source: Record<string, string>, terms: [string, number][]): number | null {
  const present = terms.filter(([key]) => amount(source[key]) !== null);
  if (!present.length) return null;
  const total = present.reduce((sum, [key, sign]) => sum + (amount(source[key]) as number) * sign, 0);
  return Math.round(total * 100) / 100;
}

export function moneyText(value: number | null): string | undefined {
  if (value == null) return undefined;
  return String(Math.round(value * 100) / 100);
}

export function monthSpan(start: string, end: string): number | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(start) || !/^\d{4}-\d{2}-\d{2}$/.test(end) || end < start) return null;
  const [sy, sm, sd] = start.split("-").map(Number);
  const [ey, em, ed] = end.split("-").map(Number);
  return (ey - sy) * 12 + (em - sm) + (ed >= sd ? 1 : 0);
}

export function orderedStatements(statements: FinancialStatement[]): FinancialStatement[] {
  return statements
    .map((row, index) => ({ row, index }))
    .filter((item) => item.row.end_date)
    .sort((left, right) => right.row.end_date.localeCompare(left.row.end_date) || left.index - right.index)
    .map((item) => item.row);
}

export function referenceStatement(statements: FinancialStatement[]): FinancialStatement | null {
  return orderedStatements(statements)[0] ?? null;
}

export interface IncomeTotals {
  commercialMargin: number | null;
  turnover: number | null;
  valueAdded: number | null;
  ebe: number | null;
  operatingResult: number | null;
  financialResult: number | null;
  ordinaryResult: number | null;
  haoResult: number | null;
  netResult: number | null;
  netGap: number | null;
}

export function incomeTotals(income: Record<string, string>): IncomeTotals {
  const commercialMargin = signedSum(income, [["sales_goods", 1], ["purchases_goods", -1], ["variation_goods", -1]]);
  const turnover = presentSum(income, ["sales_goods", "sales_manufactured", "sales_services", "accessory_products"]);
  const valueAdded = signedSum(income, [
    ["sales_goods", 1], ["purchases_goods", -1], ["variation_goods", -1],
    ["sales_manufactured", 1], ["sales_services", 1], ["accessory_products", 1],
    ["stored_production", 1], ["capitalized_production", 1], ["operating_subsidies", 1],
    ["other_operating_products", 1], ["operating_charge_transfers", 1],
    ["purchases_materials", -1], ["variation_materials", -1], ["other_purchases", -1],
    ["variation_supplies", -1], ["transport", -1], ["external_services", -1],
    ["taxes", -1], ["other_operating_charges", -1],
  ]);
  const ebe = valueAdded == null && amount(income.personnel) == null ? null : Math.round(((valueAdded ?? 0) - (amount(income.personnel) ?? 0)) * 100) / 100;
  const operatingResult = signedSum(income, [
    ["sales_goods", 1], ["purchases_goods", -1], ["variation_goods", -1],
    ["sales_manufactured", 1], ["sales_services", 1], ["accessory_products", 1],
    ["stored_production", 1], ["capitalized_production", 1], ["operating_subsidies", 1],
    ["other_operating_products", 1], ["operating_charge_transfers", 1],
    ["purchases_materials", -1], ["variation_materials", -1], ["other_purchases", -1],
    ["variation_supplies", -1], ["transport", -1], ["external_services", -1],
    ["taxes", -1], ["other_operating_charges", -1], ["personnel", -1],
    ["operating_reversals", 1], ["operating_depreciation", -1],
  ]);
  const financialResult = signedSum(income, [
    ["financial_income", 1], ["financial_reversals", 1], ["financial_charge_transfers", 1],
    ["financial_expenses", -1], ["financial_depreciation", -1],
  ]);
  const ordinaryResult = operatingResult == null && financialResult == null ? null : Math.round(((operatingResult ?? 0) + (financialResult ?? 0)) * 100) / 100;
  const haoResult = signedSum(income, [
    ["disposal_proceeds", 1], ["other_hao_income", 1], ["disposal_book_value", -1], ["other_hao_charges", -1],
  ]);
  const netResult = signedSum(income, NET_TERMS);
  const read = amount(income.net_result_read);
  return {
    commercialMargin, turnover, valueAdded, ebe, operatingResult, financialResult, ordinaryResult, haoResult, netResult,
    netGap: netResult != null && read != null ? Math.round((netResult - read) * 100) / 100 : null,
  };
}

export interface BalanceTotals {
  fixed: number | null;
  current: number | null;
  treasuryAsset: number | null;
  assets: number | null;
  equity: number | null;
  financialDebt: number | null;
  stable: number | null;
  currentLiabilities: number | null;
  treasuryLiabilities: number | null;
  liabilities: number | null;
  balanceGap: number | null;
  equityGap: number | null;
}

export function balanceTotals(balance: Record<string, string>): BalanceTotals {
  const fixed = presentSum(balance, BALANCE_GROUPS[0].lines.map((line) => line.key));
  const current = presentSum(balance, ["hao_assets", "stock_goods", "stock_materials", "stock_wip", "stock_finished", "supplier_advances", "customers", "other_receivables"]);
  const treasuryAsset = presentSum(balance, ["marketable_securities", "instruments_receivable", "cash_and_banks"]);
  const translationAsset = amount(balance.translation_asset);
  const assets = [fixed, current, treasuryAsset, translationAsset].every((value) => value == null) ? null
    : Math.round(((fixed ?? 0) + (current ?? 0) + (treasuryAsset ?? 0) + (translationAsset ?? 0)) * 100) / 100;
  const equity = presentSum(balance, BALANCE_GROUPS[3].lines.map((line) => line.key));
  const financialDebt = presentSum(balance, BALANCE_GROUPS[4].lines.map((line) => line.key));
  const stable = equity == null && financialDebt == null ? null : Math.round(((equity ?? 0) + (financialDebt ?? 0)) * 100) / 100;
  const currentLiabilities = presentSum(balance, ["hao_liabilities", "customer_advances", "suppliers", "tax_social", "other_liabilities", "short_provisions", "translation_liability"]);
  const treasuryLiabilities = presentSum(balance, ["discount_credit", "treasury_credit", "bank_overdraft"]);
  const liabilities = [stable, currentLiabilities, treasuryLiabilities].every((value) => value == null) ? null
    : Math.round(((stable ?? 0) + (currentLiabilities ?? 0) + (treasuryLiabilities ?? 0)) * 100) / 100;
  const equityByDifference = assets == null || liabilities == null ? null
    : Math.round((assets - (liabilities - (equity ?? 0))) * 100) / 100;
  return {
    fixed, current, treasuryAsset, assets, equity, financialDebt, stable, currentLiabilities, treasuryLiabilities, liabilities,
    balanceGap: assets != null && liabilities != null ? Math.round((assets - liabilities) * 100) / 100 : null,
    equityGap: equityByDifference != null && equity != null ? Math.round((equityByDifference - equity) * 100) / 100 : null,
  };
}

export function noteGap(gross: string, depreciation: string, read: string): number | null {
  const base = amount(gross);
  const reduction = amount(depreciation);
  const stated = amount(read);
  if (base == null || reduction == null || stated == null) return null;
  return Math.round((base - reduction - stated) * 100) / 100;
}

export function statementError(statements: FinancialStatement[]): string | null {
  for (const [index, row] of statements.entries()) {
    const label = row.label.trim() || `Exercice ${index + 1}`;
    if (row.start_date && row.end_date && row.end_date < row.start_date) {
      return `${label} : la date de fin est antérieure à la date de début.`;
    }
    const headcount = row.notes.headcount?.trim() ?? "";
    if (headcount && (!/^\d+$/.test(headcount))) {
      return `${label} : l'effectif moyen se saisit en nombre entier.`;
    }
  }
  return null;
}

export interface StatementApplication {
  numbers: Record<string, string>;
  details: Record<string, string>;
}

function put(target: Record<string, string>, key: string, value: number | null, allowNegative = false) {
  if (value == null) return;
  target[key] = String(allowNegative ? value : Math.max(0, value));
}

export function referenceFieldOverrides(statements: FinancialStatement[]): StatementApplication {
  const numbers: Record<string, string> = {};
  const details: Record<string, string> = {};
  const ordered = orderedStatements(statements);
  const current = ordered[0];
  if (!current) return { numbers, details };
  const income = current.income;
  put(numbers, "turnover", presentSum(income, ["sales_goods", "sales_manufactured", "sales_services", "accessory_products"]));
  const purchases = presentSum(income, ["purchases_goods", "purchases_materials", "other_purchases"]);
  const hasCharges = CHARGE_KEYS.some((key) => amount(income[key]) != null);
  if (hasCharges) {
    put(numbers, "cogs", purchases ?? 0);
    put(numbers, "op_salaries", amount(income.personnel) ?? 0);
    put(numbers, "op_transport", amount(income.transport) ?? 0);
    put(numbers, "op_taxes", amount(income.taxes) ?? 0);
    put(numbers, "op_other", presentSum(income, ["external_services", "other_operating_charges"]) ?? 0);
    put(numbers, "depreciation", amount(income.operating_depreciation) ?? 0);
    put(numbers, "financial_charges", presentSum(income, ["financial_expenses", "financial_depreciation"]) ?? 0);
    for (const key of ["op_rent", "op_utilities", "op_telecom", "op_maintenance"]) numbers[key] = "0";
  } else {
    put(numbers, "cogs", purchases);
  }
  const otherIncome = presentSum(income, ["stored_production", "capitalized_production", "operating_subsidies", "other_operating_products", "operating_charge_transfers"]);
  if (otherIncome != null) put(numbers, "other_operating_income", otherIncome);
  put(details, "income_tax_expense", amount(income.income_tax));
  put(details, "provision_reversal", presentSum(income, ["operating_reversals", "financial_reversals"]));
  put(details, "exceptional_income", presentSum(income, ["disposal_proceeds", "other_hao_income"]));
  put(details, "exceptional_expense", presentSum(income, ["disposal_book_value", "other_hao_charges", "employee_participation"]));
  const hasBalance = BALANCE_KEYS.some((key) => amount(current.balance[key]) != null);
  if (hasBalance) {
    const balance = current.balance;
    put(numbers, "stock_value", presentSum(balance, ["stock_goods", "stock_materials", "stock_wip", "stock_finished"]) ?? 0);
    put(numbers, "receivables", amount(balance.customers) ?? 0);
    put(numbers, "other_current_assets", presentSum(balance, ["hao_assets", "supplier_advances", "other_receivables", "marketable_securities", "instruments_receivable", "translation_asset"]) ?? 0);
    numbers.cash_in_hand = "0";
    put(numbers, "bank_balance", amount(balance.cash_and_banks) ?? 0);
    details.cash_detail_mode = "DETAIL";
    put(numbers, "land_building_value", presentSum(balance, ["land", "buildings", "fixtures"]) ?? 0);
    put(numbers, "equipment_value", amount(balance.equipment) ?? 0);
    put(numbers, "vehicle_value", amount(balance.transport_equipment) ?? 0);
    put(numbers, "other_fixed_assets", presentSum(balance, [
      "intangible_development", "intangible_rights", "intangible_goodwill", "intangible_other",
      "intangible_in_progress", "intangible_advances", "tangible_advances", "investments", "other_financial_assets",
    ]) ?? 0);
    details.fixed_assets_detail_mode = "DETAIL";
    put(numbers, "supplier_debt", amount(balance.suppliers) ?? 0);
    put(numbers, "tax_social_debt", amount(balance.tax_social) ?? 0);
    put(numbers, "ongoing_credit_balance", presentSum(balance, ["borrowings", "lease_debt", "other_financial_debt", "financial_provisions", "discount_credit", "treasury_credit", "bank_overdraft"]) ?? 0);
    const longTerm = amount(current.notes.debt_noncurrent);
    numbers.long_term_debt = longTerm != null && longTerm >= 0 ? String(longTerm) : "0";
    numbers.shareholder_debt = "0";
    put(numbers, "short_term_debt", presentSum(balance, ["hao_liabilities", "customer_advances", "other_liabilities", "short_provisions", "translation_liability"]) ?? 0);
    const equity = presentSum(balance, ["capital", "share_premium", "revaluation", "reserves", "retained_earnings", "period_result", "investment_grants", "regulated_provisions"]);
    if (equity != null) details.declared_equity = String(equity);
  }
  const previous = ordered[1];
  if (previous) {
    put(numbers, "turnover_prev", presentSum(previous.income, ["sales_goods", "sales_manufactured", "sales_services", "accessory_products"]));
    const read = amount(previous.income.net_result_read);
    const net = read != null ? read : signedSum(previous.income, NET_TERMS);
    if (net != null) numbers.net_result_prev = String(net);
  }
  return { numbers, details };
}

export interface ComparisonLine {
  label: string;
  current: number | null;
  previous: number | null;
  gap: number | null;
}

export interface StatementComparison {
  currentLabel: string;
  previousLabel: string;
  lines: ComparisonLine[];
}

function durationLabel(row: FinancialStatement): string {
  const months = monthSpan(row.start_date, row.end_date);
  return months == null ? row.label || row.end_date : `${row.label || row.end_date} · ${months} mois`;
}

export function statementComparisons(statements: FinancialStatement[]): StatementComparison[] {
  const ordered = orderedStatements(statements);
  const pairs: StatementComparison[] = [];
  for (let index = 0; index < ordered.length - 1; index += 1) {
    const current = ordered[index];
    const previous = ordered[index + 1];
    const currentIncome = incomeTotals(current.income);
    const previousIncome = incomeTotals(previous.income);
    const currentEquity = balanceTotals(current.balance).equity;
    const previousEquity = balanceTotals(previous.balance).equity;
    const rows = [
      ["Chiffre d'affaires", currentIncome.turnover, previousIncome.turnover],
      ["Résultat net lu", amount(current.income.net_result_read) ?? currentIncome.netResult, amount(previous.income.net_result_read) ?? previousIncome.netResult],
      ["Capitaux propres", currentEquity, previousEquity],
      ["Trésorerie de clôture", amount(current.cashflow.closing_cash), amount(previous.cashflow.closing_cash)],
    ] as const;
    pairs.push({
      currentLabel: durationLabel(current),
      previousLabel: durationLabel(previous),
      lines: rows.map(([label, left, right]) => ({
        label,
        current: left,
        previous: right,
        gap: left != null && right != null ? Math.round((left - right) * 100) / 100 : null,
      })),
    });
  }
  return pairs;
}

export function filledStatementLines(source: Record<string, string>, lines: StatementLine[]): StatementLine[] {
  return lines.filter((line) => amount(source[line.key]) != null || (source[line.key] && line.key === "headcount"));
}
