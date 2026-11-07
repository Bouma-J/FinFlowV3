import type { AnalysisDetails, FinancialAnalysis } from "@/api/types";

export type YesNo = "" | "yes" | "no";

export type ExternalCredit = {
  institution: string;
  grant_date: string;
  final_due_date: string;
  initial_amount: string;
  monthly_payment: string;
  outstanding: string;
  max_days_late: string;
  bureau_checked: YesNo;
  bureau_date: string;
  incidents: YesNo;
  incidents_detail: string;
};

export type DerivedExternalDebt = {
  rows: ExternalCredit[];
  error: string;
  institution: string;
  initial_amount: string;
  monthly: string;
  count: string;
  max_days_late: string;
  bureau_checked: boolean;
  bureau_date: string;
  incidents: boolean;
  comment: string;
};

const FIELDS: (keyof ExternalCredit)[] = [
  "institution", "grant_date", "final_due_date", "initial_amount", "monthly_payment",
  "outstanding", "max_days_late", "bureau_checked", "bureau_date", "incidents", "incidents_detail",
];

export function blankExternalCredit(): ExternalCredit {
  return {
    institution: "", grant_date: "", final_due_date: "", initial_amount: "",
    monthly_payment: "", outstanding: "", max_days_late: "", bureau_checked: "",
    bureau_date: "", incidents: "", incidents_detail: "",
  };
}

function text(value: unknown) {
  return typeof value === "string" ? value : "";
}

function choice(value: unknown): YesNo {
  return value === "yes" || value === "no" ? value : "";
}

function rowFrom(source: Record<string, string>): ExternalCredit {
  return {
    institution: text(source.institution),
    grant_date: text(source.grant_date),
    final_due_date: text(source.final_due_date),
    initial_amount: text(source.initial_amount),
    monthly_payment: text(source.monthly_payment),
    outstanding: text(source.outstanding),
    max_days_late: text(source.max_days_late),
    bureau_checked: choice(source.bureau_checked),
    bureau_date: text(source.bureau_date),
    incidents: choice(source.incidents),
    incidents_detail: text(source.incidents_detail),
  };
}

export function savedExternalCredits(details?: AnalysisDetails): ExternalCredit[] {
  const raw = details?.external_credits;
  if (!Array.isArray(raw)) return [];
  return raw.map((row) => rowFrom(row));
}

export function initialExternalCredits(analysis?: FinancialAnalysis): ExternalCredit[] {
  const saved = savedExternalCredits(analysis?.analysis_details);
  if (saved.length) return saved;
  if (!analysis) return [blankExternalCredit()];
  const institution = analysis.existing_debt_institution || "";
  const initial = Number(analysis.existing_debt_initial_amount) > 0 ? analysis.existing_debt_initial_amount : "";
  const monthly = Number(analysis.existing_debt_monthly) > 0 ? analysis.existing_debt_monthly : "";
  const outstanding = Number(analysis.ongoing_credit_balance) > 0 ? analysis.ongoing_credit_balance : "";
  const delay = analysis.max_days_late ? String(analysis.max_days_late) : "";
  const detail = analysis.incidents_comment || "";
  const hasLegacy = Boolean(
    institution.trim() || initial || monthly || delay || detail
    || analysis.credit_bureau_checked || analysis.has_payment_incidents,
  );
  if (!hasLegacy) return [blankExternalCredit()];
  return [{
    ...blankExternalCredit(),
    institution,
    initial_amount: initial,
    monthly_payment: monthly,
    outstanding,
    max_days_late: delay,
    bureau_checked: analysis.credit_bureau_checked ? "yes" : "no",
    bureau_date: analysis.credit_bureau_date || "",
    incidents: analysis.has_payment_incidents ? "yes" : "no",
    incidents_detail: detail,
  }];
}

function filled(row: ExternalCredit) {
  return FIELDS.some((key) => row[key].trim() !== "");
}

function money(value: number) {
  return (Math.round(value * 100) / 100).toFixed(2);
}

export function deriveExternalDebt(rows: ExternalCredit[]): DerivedExternalDebt {
  const kept = rows.filter(filled);
  let error = "";
  kept.forEach((row, index) => {
    if (error) return;
    const number = index + 1;
    if (row.bureau_checked === "yes" && !row.bureau_date) {
      error = `Crédit ${number} : indiquez la date de consultation de la centrale des risques.`;
    } else if (row.grant_date && row.final_due_date && row.final_due_date < row.grant_date) {
      error = `Crédit ${number} : la dernière échéance est antérieure à la date d'octroi.`;
    } else if (row.max_days_late.trim() && !/^\d+$/.test(row.max_days_late.trim())) {
      error = `Crédit ${number} : le retard maximum se saisit en jours entiers.`;
    }
  });
  const sum = (key: "initial_amount" | "monthly_payment") => kept.reduce((total, row) => total + (Number(row[key]) || 0), 0);
  const delays = kept.map((row) => row.max_days_late.trim()).filter((value) => /^\d+$/.test(value)).map(Number);
  const dates = kept.filter((row) => row.bureau_checked === "yes").map((row) => row.bureau_date).filter(Boolean).sort();
  return {
    rows: kept,
    error,
    institution: kept.map((row) => row.institution.trim()).filter(Boolean).join(" ; ").slice(0, 200),
    initial_amount: money(sum("initial_amount")),
    monthly: money(sum("monthly_payment")),
    count: String(kept.length),
    max_days_late: delays.length ? String(Math.max(...delays)) : "",
    bureau_checked: kept.some((row) => row.bureau_checked === "yes"),
    bureau_date: dates[dates.length - 1] || "",
    incidents: kept.some((row) => row.incidents === "yes"),
    comment: kept.map((row) => {
      const detail = row.incidents_detail.trim();
      if (!detail) return "";
      const name = row.institution.trim();
      return name ? `${name} — ${detail}` : detail;
    }).filter(Boolean).join("\n\n"),
  };
}
