export const SALES_RHYTHMS = [
  { value: "DAY", label: "Jour" },
  { value: "WEEK", label: "Semaine" },
  { value: "MONTH", label: "Mois" },
];

function money(value: number): string {
  return (Math.round(value * 100) / 100).toFixed(2);
}

export function rhythmMonthly(rhythm: string, amount: string, days: string): string | null {
  if (amount.trim() === "") return null;
  const value = Number(amount);
  if (!Number.isFinite(value)) return null;
  if (rhythm === "MONTH") return money(value);
  if (rhythm === "WEEK") return money(value * 4);
  if (rhythm === "DAY") {
    if (days.trim() === "") return null;
    const count = Number(days);
    if (!Number.isFinite(count) || count <= 0 || count > 31) return null;
    return money(value * count);
  }
  return null;
}

export function observedDailyAverage(rows: Record<string, string>[]): string | null {
  const observed = rows.filter((row) => (row.kind || "Observé") === "Observé" && Object.values(row).some((value) => value));
  if (!observed.length || observed.some((row) => row.amount == null || row.amount === "")) return null;
  const total = observed.reduce((sum, row) => sum + Number(row.amount), 0);
  return money(total / observed.length);
}
