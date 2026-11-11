import { productAmount } from "@/components/productLine";

export type SupplierPaymentReading = {
  total: string | null;
  count: number | null;
  average: string | null;
  lastDate: string;
  lastAmount: string;
};

function money(value: number): string {
  return (Math.round(value * 100) / 100).toFixed(2);
}

export function supplierPaymentReading(rows: Record<string, string>[]): SupplierPaymentReading {
  const complete = rows.flatMap((row) => {
    const amount = productAmount(row.amount);
    if (!row.date || amount == null) return [];
    return [{ date: row.date, amount }];
  });
  let lastDate = "";
  let lastTotal = 0;
  for (const line of complete) {
    if (!lastDate || line.date > lastDate) {
      lastDate = line.date;
      lastTotal = line.amount;
    } else if (line.date === lastDate) {
      lastTotal += line.amount;
    }
  }
  const total = complete.reduce((sum, line) => sum + line.amount, 0);
  return {
    total: complete.length ? money(total) : null,
    count: complete.length ? complete.length : null,
    average: complete.length ? money(total / complete.length) : null,
    lastDate,
    lastAmount: lastDate ? money(lastTotal) : "",
  };
}
