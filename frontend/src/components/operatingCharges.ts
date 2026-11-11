export const OPERATING_CHARGES = [
  { key: "activity_charge_place", label: "Loyer ou droit de place" },
  { key: "activity_charge_staff", label: "Personnel et aides" },
  { key: "activity_charge_transport", label: "Transport" },
  { key: "activity_charge_utilities", label: "Eau et électricité" },
  { key: "activity_charge_telecom", label: "Téléphone" },
  { key: "activity_charge_maintenance", label: "Entretien et réparations" },
  { key: "activity_charge_fees", label: "Taxes et redevances" },
  { key: "activity_charge_supplies", label: "Emballages et consommables" },
] as const;

function amount(value: unknown): number | null {
  if (value == null || String(value).trim() === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

export function operatingChargesExcludingPurchases(details: Record<string, unknown> | undefined): number | null {
  if (!details) return null;
  const amounts = OPERATING_CHARGES.map((item) => amount(details[item.key]));
  const extras = Array.isArray(details.activity_extra_charges) ? details.activity_extra_charges : [];
  extras.forEach((row) => {
    const source = (row ?? {}) as Record<string, unknown>;
    amounts.push(amount(source.amount));
  });
  if (amounts.every((item) => item == null)) return null;
  return amounts.reduce<number>((sum, item) => sum + (item ?? 0), 0);
}

export function activityExpensesFromOperating(excluding: number | null, purchases: string): string | null {
  if (excluding == null) return null;
  const base = purchases.trim() === "" ? 0 : Number(purchases);
  if (!Number.isFinite(base)) return null;
  return (Math.round((excluding + base) * 100) / 100).toFixed(2);
}
