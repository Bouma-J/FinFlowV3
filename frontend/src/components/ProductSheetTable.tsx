import type { AnalysisDetails } from "@/api/types";
import { formatMoney } from "@/components/ui";

type ProductRow = Record<string, string>;

function amount(value: string | undefined): number | null {
  if (value == null || value.trim() === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

export function ProductSheetTable({ value, onChange, currency }: {
  value: AnalysisDetails;
  onChange: (next: AnalysisDetails) => void;
  currency: string;
}) {
  const rows: ProductRow[] = Array.isArray(value.products) ? value.products : [];
  function update(index: number, key: string, content: string) {
    onChange({ ...value, products: rows.map((row, rowIndex) => rowIndex === index ? { ...row, [key]: content } : row) });
  }
  return <div className="product-sheet">
    <div className="table-scroll">
      <table className="table">
        <caption>Fiches produits / services — période de référence</caption>
        <thead>
          <tr>
            <th scope="col">Articles / produits</th>
            <th scope="col">Quantité</th>
            <th scope="col">Prix de revient</th>
            <th scope="col">Prix de vente</th>
            <th scope="col">Valeur totale</th>
            <th scope="col">Marge brute prévisionnelle</th>
            <th scope="col">Retirer</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && <tr><td colSpan={7} className="muted">Aucune ligne. Ajoutez un article ou un produit.</td></tr>}
          {rows.map((row, index) => {
            const quantity = amount(row.quantity);
            const cost = amount(row.unit_cost);
            const sale = amount(row.sale_price);
            const total = quantity != null && sale != null ? quantity * sale : null;
            const margin = quantity != null && sale != null && cost != null ? quantity * (sale - cost) : null;
            return <tr key={index}>
              <td><input aria-label={`Article ou produit, ligne ${index + 1}`} type="text" value={row.name ?? ""} onChange={(event) => update(index, "name", event.target.value)} /></td>
              <td><input aria-label={`Quantité, ligne ${index + 1}`} type="number" step="any" min={0} value={row.quantity ?? ""} onChange={(event) => update(index, "quantity", event.target.value)} /></td>
              <td><input aria-label={`Prix de revient, ligne ${index + 1}`} type="number" step="any" min={0} value={row.unit_cost ?? ""} onChange={(event) => update(index, "unit_cost", event.target.value)} /></td>
              <td><input aria-label={`Prix de vente, ligne ${index + 1}`} type="number" step="any" min={0} value={row.sale_price ?? ""} onChange={(event) => update(index, "sale_price", event.target.value)} /></td>
              <td className="num">{formatMoney(total, currency)}</td>
              <td className="num">{formatMoney(margin, currency)}</td>
              <td><button type="button" className="btn btn-ghost btn-sm" onClick={() => onChange({ ...value, products: rows.filter((_, rowIndex) => rowIndex !== index) })}>Retirer</button></td>
            </tr>;
          })}
        </tbody>
      </table>
    </div>
    {rows.length < 120 && <button type="button" className="btn btn-ghost product-sheet-add" onClick={() => onChange({ ...value, products: [...rows, {}] })}>Ajouter une ligne</button>}
    <label className="field product-sheet-comment">
      <span>Commentaire sur le stock</span>
      <textarea
        rows={3}
        value={typeof value.stock_risks === "string" ? value.stock_risks : ""}
        onChange={(event) => onChange({ ...value, stock_risks: event.target.value })}
      />
    </label>
  </div>;
}
