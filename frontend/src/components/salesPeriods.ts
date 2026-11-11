import { productAmount } from "@/components/productLine";

export const SALES_PERIODS = [
  { value: "DAY", label: "Journalière" },
  { value: "WEEK", label: "Hebdomadaire" },
  { value: "MONTH", label: "Mensuelle" },
  { value: "SEMESTER", label: "Semestrielle" },
];

export const ANALYSIS_GRAINS = [
  { value: "DAY", label: "Jour" },
  { value: "WEEK", label: "Semaine" },
  { value: "MONTH", label: "Mois" },
];

export const SALES_APPRECIATIONS = [
  { value: "FAIBLE", label: "Faible" },
  { value: "MOYENNE", label: "Moyenne" },
  { value: "BONNE", label: "Bonne" },
];

const PERIOD_MODES = new Set(["DAY", "WEEK", "MONTH", "SEMESTER"]);

export const SALES_PERIOD_KEYS = ["date", "start", "end", "amount", "appreciation"] as const;

export function readSalesPeriodRows(value: unknown): Record<string, string>[] {
  if (!Array.isArray(value)) return [];
  return value.map((row) => {
    const source = (row ?? {}) as Record<string, unknown>;
    return Object.fromEntries(SALES_PERIOD_KEYS.map((key) => [key, source[key] == null ? "" : String(source[key])]));
  });
}

function money(value: number): string {
  return (Math.round(value * 100) / 100).toFixed(2);
}

function inclusiveDays(start: string, end: string): number | null {
  const startMatch = /^(\d{4})-(\d{2})-(\d{2})$/.exec(start);
  const endMatch = /^(\d{4})-(\d{2})-(\d{2})$/.exec(end);
  if (!startMatch || !endMatch || end < start) return null;
  const startUtc = Date.UTC(Number(startMatch[1]), Number(startMatch[2]) - 1, Number(startMatch[3]));
  const endUtc = Date.UTC(Number(endMatch[1]), Number(endMatch[2]) - 1, Number(endMatch[3]));
  const days = Math.round((endUtc - startUtc) / 86400000) + 1;
  return days > 0 ? days : null;
}

export type SalesPeriodSpan = { start: string; end: string; amount: string };

export type SalesPeriodReading = {
  count: number | null;
  total: string | null;
  average: string | null;
  days: number | null;
  monthly: string | null;
  high: SalesPeriodSpan | null;
  low: SalesPeriodSpan | null;
  appreciation: string;
};

export function salesPeriodReading(
  rows: Record<string, string>[],
  mode: string,
  bounds?: { start: string; end: string },
): SalesPeriodReading {
  const empty: SalesPeriodReading = {
    count: null, total: null, average: null, days: null, monthly: null,
    high: null, low: null, appreciation: "",
  };
  if (mode && !PERIOD_MODES.has(mode)) return empty;
  const bounded = Boolean(bounds?.start && bounds?.end && bounds.end >= bounds.start);
  const inside = (start: string, end: string) => !bounded || (start >= (bounds?.start || "") && end <= (bounds?.end || ""));
  const lines = rows.flatMap((row) => {
    const amount = productAmount(row.amount);
    if (amount == null) return [];
    if (mode === "DAY") {
      if (!row.date || !inside(row.date, row.date)) return [];
      return [{ start: row.date, end: row.date, days: 1, amount, appreciation: row.appreciation || "" }];
    }
    const days = inclusiveDays(row.start, row.end);
    if (days == null || !inside(row.start, row.end)) return [];
    return [{ start: row.start, end: row.end, days, amount, appreciation: row.appreciation || "" }];
  });
  if (!lines.length) return empty;
  const total = lines.reduce((sum, line) => sum + line.amount, 0);
  const covered = lines.reduce((sum, line) => sum + line.days, 0);
  const labels: Record<string, string> = { FAIBLE: "Faible", MOYENNE: "Moyenne", BONNE: "Bonne" };
  const counts: Record<string, number> = {};
  const order: string[] = [];
  lines.forEach((line) => {
    if (!labels[line.appreciation]) return;
    if (counts[line.appreciation] == null) {
      counts[line.appreciation] = 0;
      order.push(line.appreciation);
    }
    counts[line.appreciation] += 1;
  });
  const appreciation = order.length
    ? labels[order.reduce((best, item) => (counts[item] > counts[best] ? item : best))]
    : "";
  let highIndex = 0;
  let lowIndex = 0;
  lines.forEach((line, index) => {
    if (line.amount > lines[highIndex].amount) highIndex = index;
    if (line.amount < lines[lowIndex].amount) lowIndex = index;
  });
  const span = (index: number): SalesPeriodSpan => ({
    start: lines[index].start,
    end: lines[index].end,
    amount: money(lines[index].amount),
  });
  return {
    count: lines.length,
    total: money(total),
    average: money(total / lines.length),
    days: covered,
    monthly: covered > 0 ? money((total / covered) * 30) : null,
    high: span(highIndex),
    low: span(lowIndex),
    appreciation,
  };
}
