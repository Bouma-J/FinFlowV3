import { productAmount } from "@/components/productLine";

export function purchaseLineAmount(row: Record<string, string>): number | null {
  const quantity = productAmount(row.quantity);
  const price = productAmount(row.unit_price);
  if (quantity == null || price == null) return null;
  return Math.round(quantity * price * 100) / 100;
}

export type PurchaseHistoryReading = {
  latestDate: string;
  latestAmount: string;
  periodTotal: string | null;
  count: number | null;
  average: string | null;
  perMonth: string | null;
  monthly: string | null;
  periodLastDate: string;
  periodLastAmount: string;
  supplierCount: number | null;
  mainSupplier: string;
  mainShare: string | null;
};

function money(value: number): string {
  return (Math.round(value * 100) / 100).toFixed(2);
}

function periodDays(start: string, end: string): number | null {
  const startMatch = /^(\d{4})-(\d{2})-(\d{2})$/.exec(start);
  const endMatch = /^(\d{4})-(\d{2})-(\d{2})$/.exec(end);
  if (!startMatch || !endMatch) return null;
  const startUtc = Date.UTC(Number(startMatch[1]), Number(startMatch[2]) - 1, Number(startMatch[3]));
  const endUtc = Date.UTC(Number(endMatch[1]), Number(endMatch[2]) - 1, Number(endMatch[3]));
  const days = Math.round((endUtc - startUtc) / 86400000) + 1;
  return days > 0 ? days : null;
}

export function purchaseHistoryReading(rows: Record<string, string>[], start: string, end: string): PurchaseHistoryReading {
  const complete = rows.flatMap((row) => {
    const amount = purchaseLineAmount(row);
    if (!row.date || amount == null) return [];
    return [{ date: row.date, amount, supplier: (row.supplier || "").trim() }];
  });
  let latestDate = "";
  let latestTotal = 0;
  for (const line of complete) {
    if (!latestDate || line.date > latestDate) {
      latestDate = line.date;
      latestTotal = line.amount;
    } else if (line.date === latestDate) {
      latestTotal += line.amount;
    }
  }
  const counted = start && end && start <= end
    ? complete.filter((line) => line.date >= start && line.date <= end)
    : [];
  const total = counted.reduce((sum, line) => sum + line.amount, 0);
  const suppliers = new Map<string, { label: string; amount: number }>();
  let periodLastDate = "";
  let periodLastTotal = 0;
  for (const line of counted) {
    if (!periodLastDate || line.date > periodLastDate) {
      periodLastDate = line.date;
      periodLastTotal = line.amount;
    } else if (line.date === periodLastDate) {
      periodLastTotal += line.amount;
    }
    if (!line.supplier) continue;
    const key = line.supplier.toLocaleLowerCase("fr");
    const current = suppliers.get(key);
    if (current) current.amount += line.amount;
    else suppliers.set(key, { label: line.supplier, amount: line.amount });
  }
  const ranked = [...suppliers.values()].sort((left, right) => right.amount - left.amount);
  const main = ranked[0];
  const days = counted.length ? periodDays(start, end) : null;
  return {
    latestDate,
    latestAmount: latestDate ? money(latestTotal) : "",
    periodTotal: counted.length ? money(total) : null,
    count: counted.length ? counted.length : null,
    average: counted.length ? money(total / counted.length) : null,
    perMonth: days ? money(counted.length / days * 30) : null,
    monthly: days ? money(total / days * 30) : null,
    periodLastDate,
    periodLastAmount: periodLastDate ? money(periodLastTotal) : "",
    supplierCount: suppliers.size ? suppliers.size : null,
    mainSupplier: main?.label || "",
    mainShare: main && total > 0 ? money(main.amount / total * 100) : null,
  };
}
