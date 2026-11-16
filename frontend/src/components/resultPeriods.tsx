import { purchaseLineAmount } from "@/components/purchaseHistory";
import { productAmount } from "@/components/productLine";
import { salesPeriodReading } from "@/components/salesPeriods";
import { supplierPaymentReading } from "@/components/supplierPayments";
import { formatDate, formatMoney } from "@/components/ui";

type Row = Record<string, unknown>;

export type ResultPeriodBounds = { start: string; end: string };

type Span = { start: string; end: string; amount: number };

function text(row: Row, key: string): string {
  const value = row[key];
  return value == null ? "" : String(value);
}

function spanDays(start: string, end: string): number {
  const startMatch = /^(\d{4})-(\d{2})-(\d{2})$/.exec(start);
  const endMatch = /^(\d{4})-(\d{2})-(\d{2})$/.exec(end);
  if (!startMatch || !endMatch || end < start) return Number.MAX_SAFE_INTEGER;
  const startUtc = Date.UTC(Number(startMatch[1]), Number(startMatch[2]) - 1, Number(startMatch[3]));
  const endUtc = Date.UTC(Number(endMatch[1]), Number(endMatch[2]) - 1, Number(endMatch[3]));
  return Math.round((endUtc - startUtc) / 86400000) + 1;
}

function inWindow(start: string, end: string, bounds?: ResultPeriodBounds): boolean {
  if (!bounds?.start || !bounds.end || bounds.end < bounds.start) return true;
  return start >= bounds.start && end <= bounds.end;
}

function sameSpan(left: Span, right: Span): boolean {
  return left.start === right.start && left.end === right.end;
}

function contains(outer: Span, inner: Span): boolean {
  return inner.start >= outer.start && inner.end <= outer.end;
}

function moneySpan(row: Row, mode: string, amountKey: string, bounds?: ResultPeriodBounds, windowed = true): Span | null {
  const periodMode = mode === "WEEK" || mode === "MONTH";
  const amount = productAmount(text(row, periodMode ? amountKey : "amount"));
  if (periodMode) {
    const start = text(row, "start");
    const end = text(row, "end");
    if (!start || !end || end < start || amount == null || (windowed && !inWindow(start, end, bounds))) return null;
    return { start, end, amount };
  }
  const day = text(row, "date");
  const dayAmount = amountKey === "amount" ? amount : productAmount(text(row, "amount"));
  if (!day || dayAmount == null || (windowed && !inWindow(day, day, bounds))) return null;
  return { start: day, end: day, amount: dayAmount };
}

function purchaseSpan(row: Row, mode: string, bounds?: ResultPeriodBounds): Span | null {
  if (mode === "WEEK" || mode === "MONTH") return moneySpan(row, mode, "amount", bounds);
  const day = text(row, "date");
  const amount = purchaseLineAmount({
    quantity: text(row, "quantity"),
    unit_price: text(row, "unit_price"),
  });
  if (!day || amount == null || !inWindow(day, day, bounds)) return null;
  return { start: day, end: day, amount };
}

function columnsFrom(spans: Span[]): Span[] {
  const unique: Span[] = [];
  spans.forEach((span) => {
    if (!unique.some((item) => sameSpan(item, span))) unique.push({ start: span.start, end: span.end, amount: 0 });
  });
  const kept = unique.filter((span) => !unique.some((other) => contains(other, span) && !sameSpan(other, span)));
  kept.sort((left, right) => left.start.localeCompare(right.start) || left.end.localeCompare(right.end));
  return kept;
}

function place(spans: Span[], columns: Span[]): Array<number | null> {
  const totals = columns.map(() => null as number | null);
  spans.forEach((span) => {
    let best = -1;
    let bestDays = Number.MAX_SAFE_INTEGER;
    columns.forEach((column, index) => {
      if (!contains(column, span)) return;
      const days = spanDays(column.start, column.end);
      if (days < bestDays || (days === bestDays && column.start > (columns[best]?.start || ""))) {
        best = index;
        bestDays = days;
      }
    });
    if (best < 0) return;
    totals[best] = (totals[best] ?? 0) + span.amount;
  });
  return totals;
}

function difference(sales: Array<number | null>, purchases: Array<number | null>): Array<number | null> {
  return sales.map((sale, index) => (sale == null || purchases[index] == null ? null : Math.round((sale - (purchases[index] ?? 0)) * 100) / 100));
}

function columnLabel(column: Span): string {
  return column.start === column.end ? formatDate(column.start) : `${formatDate(column.start)} – ${formatDate(column.end)}`;
}

function shown(value: number | null, currency: string): string {
  return value == null ? "—" : formatMoney(value, currency);
}

export function ResultPeriodTable({
  mode,
  bounds,
  salesRows,
  collectionRows,
  purchaseRows,
  paymentRows,
  includePurchases,
  currency,
  salesRetained,
  purchasesRetained,
  tailRows,
  whenPeriods = false,
}: {
  mode: string;
  bounds?: ResultPeriodBounds;
  salesRows: Row[];
  collectionRows: Row[];
  purchaseRows: Row[];
  paymentRows: Row[];
  includePurchases: boolean;
  currency: string;
  salesRetained: string;
  purchasesRetained: string;
  tailRows: { label: string; value: string; strong?: boolean }[];
  whenPeriods?: boolean;
}) {
  const sales = salesRows.flatMap((row) => {
    const span = moneySpan(row, mode, "amount", bounds);
    return span ? [span] : [];
  });
  const collections = collectionRows.flatMap((row) => {
    const span = moneySpan(row, mode, "amount", bounds);
    return span ? [span] : [];
  });
  const purchases = includePurchases
    ? purchaseRows.flatMap((row) => {
      const span = purchaseSpan(row, mode, bounds);
      return span ? [span] : [];
    })
    : [];
  const payments = paymentRows.flatMap((row) => {
    const span = moneySpan(row, mode, "period_amount", bounds, mode === "WEEK" || mode === "MONTH");
    return span ? [span] : [];
  });
  const columns = columnsFrom([...sales, ...collections, ...purchases, ...payments]);
  if (whenPeriods && columns.length === 0) return null;
  const salesCells = place(sales, columns);
  const purchaseCells = place(purchases, columns);
  const collectionCells = place(collections, columns);
  const paymentCells = place(payments, columns);
  const beforeCharges = difference(salesCells, purchaseCells);
  const collectionReading = salesPeriodReading(
    collectionRows.map((row) => Object.fromEntries(Object.entries(row).map(([key, value]) => [key, value == null ? "" : String(value)]))),
    mode,
    bounds,
  );
  const paymentReading = supplierPaymentReading(
    paymentRows.map((row) => Object.fromEntries(Object.entries(row).map(([key, value]) => [key, value == null ? "" : String(value)]))),
    mode,
    bounds?.start || "",
    bounds?.end || "",
  );
  const periodRows = [
    { label: "Chiffre d'affaires", cells: salesCells, retained: salesRetained, strong: false },
    { label: "Achats", cells: purchaseCells, retained: purchasesRetained, strong: false },
    { label: "Encaissements", cells: collectionCells, retained: collectionReading.monthly == null ? "—" : formatMoney(collectionReading.monthly, currency), strong: false },
    { label: "Paiements fournisseurs", cells: paymentCells, retained: paymentReading.total == null ? "—" : formatMoney(paymentReading.total, currency), strong: false },
    ...(includePurchases ? [{ label: "Résultat avant charges hors achats", cells: beforeCharges, retained: "—", strong: true }] : []),
  ];
  return (
    <div className="table-scroll result-period-table">
      <table className="table">
        <thead>
          <tr>
            <th scope="col">Rubrique</th>
            {columns.map((column) => <th scope="col" key={`${column.start}:${column.end}`}>{columnLabel(column)}</th>)}
            <th scope="col">Mois retenu</th>
          </tr>
        </thead>
        <tbody>
          {periodRows.map((row) => (
            <tr key={row.label}>
              <th scope="row">{row.strong ? <strong>{row.label}</strong> : row.label}</th>
              {row.cells.map((value, index) => <td className="num" key={index}>{shown(value, currency)}</td>)}
              <td className="num">{row.retained}</td>
            </tr>
          ))}
          {tailRows.map((row) => (
            <tr key={row.label}>
              <th scope="row">{row.strong ? <strong>{row.label}</strong> : row.label}</th>
              {columns.map((column) => <td className="num" key={`${row.label}:${column.start}:${column.end}`}>—</td>)}
              <td className="num">{row.value}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
