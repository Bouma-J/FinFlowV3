import { purchaseLineAmount } from "@/components/purchaseHistory";
import { productAmount } from "@/components/productLine";
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

function shown(value: number | null, currency: string, percent = false): string {
  if (value == null) return "—";
  if (percent) return `${new Intl.NumberFormat("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value)} %`;
  return formatMoney(value, currency);
}

function roundMoney(value: number): number {
  return Math.round(value * 100) / 100;
}

export type MonthComparison = {
  charges: number | null;
  otherActivities: number;
  household: number;
  family: number;
  installments: number | null;
  weight: number;
  activityCounted: boolean;
  activityInformal: boolean;
  stable: number;
  informal: number;
  otherRetained: number;
  showHouseholdHaircut: boolean;
  showOther: boolean;
  otherHaircut: boolean;
  dependents: number | null;
  showCapacity: boolean;
};

type ComparisonRow = { label: string; cells: Array<number | null>; strong: boolean; percent?: boolean };

function monthRows(sales: Array<number | null>, purchases: Array<number | null>, includePurchases: boolean, month: MonthComparison): ComparisonRow[] {
  const nets = sales.map((sale, index) => {
    if (sale == null || month.charges == null) return null;
    if (includePurchases && purchases[index] == null) return null;
    return roundMoney(sale - (includePurchases ? purchases[index] ?? 0 : 0) - month.charges);
  });
  const margins = nets.map((net, index) => {
    const sale = sales[index];
    return net == null || sale == null || sale === 0 ? null : (net / sale) * 100;
  });
  const activityRetained = nets.map((net) => {
    if (net == null || !month.activityCounted) return null;
    return month.activityInformal && net > 0 ? roundMoney(net * month.weight / 100) : net;
  });
  const retained = nets.map((net, index) => net == null ? null : roundMoney(month.stable + month.informal * month.weight / 100 + (activityRetained[index] ?? 0) + month.otherRetained));
  const disposable = nets.map((net, index) => {
    if (net == null || retained[index] == null) return null;
    const declared = month.household + net + month.otherActivities;
    const base = Math.abs(declared - retained[index]) > 0.5 ? retained[index] : declared;
    return roundMoney(base - month.family - (month.installments ?? 0));
  });
  const repeat = (value: number | null) => sales.map(() => value);
  const weightLabel = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 2 }).format(month.weight);
  const rows: ComparisonRow[] = [
    { label: "Charges d'exploitation hors achats", cells: repeat(month.charges), strong: false },
    { label: "Résultat de l'activité", cells: nets, strong: true },
    { label: "Marge de l'activité", cells: margins, strong: false, percent: true },
  ];
  if (!month.showCapacity) return rows;
  rows.push(
    { label: "Autres activités", cells: repeat(month.otherActivities), strong: false },
    { label: "Revenus du ménage", cells: repeat(month.household), strong: false },
    { label: "Charges familiales", cells: repeat(month.family), strong: false },
  );
  if (month.showHouseholdHaircut) {
    rows.push({ label: `Retenue ${weightLabel} % · revenus du ménage`, cells: repeat(roundMoney(month.informal * month.weight / 100)), strong: false });
  }
  if (month.activityInformal && month.activityCounted) {
    rows.push({
      label: `Retenue ${weightLabel} % · activité`,
      cells: nets.map((net, index) => net != null && net > 0 ? activityRetained[index] : null),
      strong: false,
    });
  }
  if (month.showOther) {
    rows.push({
      label: month.otherHaircut ? `Retenue ${weightLabel} % · autres activités` : "Autres activités retenues",
      cells: repeat(month.otherRetained),
      strong: false,
    });
  }
  if (month.showHouseholdHaircut || (month.activityInformal && month.activityCounted) || (month.showOther && month.otherHaircut)) {
    rows.push({ label: "Revenus retenus après pondération", cells: retained, strong: true });
  }
  rows.push(
    { label: "Mensualités déjà en cours", cells: repeat(month.installments), strong: false },
    { label: "Reste à vivre avant la nouvelle échéance", cells: disposable, strong: true },
  );
  if (month.dependents != null) {
    rows.push({
      label: `Reste à vivre / personne (${month.dependents + 1})`,
      cells: disposable.map((value) => value == null ? null : value / (month.dependents! + 1)),
      strong: false,
    });
  }
  return rows;
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
  monthComparison,
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
  monthComparison?: MonthComparison;
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
  const periodRows: ComparisonRow[] = [
    { label: "Chiffre d'affaires", cells: salesCells, strong: false },
    { label: "Achats", cells: purchaseCells, strong: false },
    { label: "Encaissements", cells: collectionCells, strong: false },
    { label: "Paiements fournisseurs", cells: paymentCells, strong: false },
    ...(includePurchases ? [{ label: "Résultat avant charges hors achats", cells: beforeCharges, strong: true }] : []),
    ...(mode === "MONTH" && monthComparison ? monthRows(salesCells, purchaseCells, includePurchases, monthComparison) : []),
  ];
  return (
    <div className="table-scroll result-period-table">
      <table className="table">
        <thead>
          <tr>
            <th scope="col">Rubrique</th>
            {columns.map((column) => <th scope="col" key={`${column.start}:${column.end}`}>{columnLabel(column)}</th>)}
          </tr>
        </thead>
        <tbody>
          {periodRows.map((row) => (
            <tr key={row.label}>
              <th scope="row">{row.strong ? <strong>{row.label}</strong> : row.label}</th>
              {row.cells.map((value, index) => <td className="num" key={index}>{shown(value, currency, row.percent)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
