import type { AnalysisDetails } from "@/api/types";
import { PRODUCT_NATURES, PRODUCTION_STOCKS, productAmount, productFigures, productNature, type ProductNature } from "@/components/productLine";
import { formatMoney } from "@/components/ui";

type ProductRow = Record<string, string>;

export function ProductSheetTable({ value, onChange, currency }: {
  value: AnalysisDetails;
  onChange: (next: AnalysisDetails) => void;
  currency: string;
}) {
  const rows: ProductRow[] = Array.isArray(value.products) ? value.products : [];
  const manufactures = rows.some((row) => productNature(row) === "MANUFACTURED")
    || PRODUCTION_STOCKS.some((stock) => typeof value[stock.key] === "string" && value[stock.key] !== "");

  function update(index: number, key: string, content: string) {
    onChange({ ...value, products: rows.map((row, rowIndex) => rowIndex === index ? { ...row, [key]: content } : row) });
  }
  function setNature(index: number, nature: ProductNature) {
    update(index, "nature", nature);
  }

  return <div className="product-sheet">
    <p className="muted small">
      Chaque ligne est revendue, fabriquée ou un service. Une case vide reste vide.
      Les salaires, le loyer, le transport et les autres charges de la période restent dans les charges : ils ne se ressaisissent pas ici.
    </p>
    <div className="product-line-list">
      {rows.length === 0 && <p className="muted">Aucune ligne. Ajoutez un article, un produit fabriqué ou un service.</p>}
      {rows.map((row, index) => {
        const nature = productNature(row);
        const figures = productFigures(row);
        const scrap = productAmount(row.quantity_scrapped);
        return <article className="product-line" key={index}>
          <div className="external-credit-head">
            <h4>Ligne {index + 1} — {PRODUCT_NATURES.find((item) => item.value === nature)?.label}</h4>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => onChange({ ...value, products: rows.filter((_, rowIndex) => rowIndex !== index) })}>Retirer</button>
          </div>
          <div className="form-grid two-col">
            <label className="field">
              <span>Nature</span>
              <select aria-label={`Nature, ligne ${index + 1}`} value={row.nature === "MANUFACTURED" || row.nature === "SERVICE" ? row.nature : "RESOLD"} onChange={(event) => setNature(index, event.target.value as ProductNature)}>
                {PRODUCT_NATURES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
              </select>
            </label>
            <label className="field">
              <span>Unité</span>
              <input aria-label={`Unité, ligne ${index + 1}`} type="text" value={row.unit ?? ""} placeholder="pièce, kg, litre, prestation" onChange={(event) => update(index, "unit", event.target.value)} />
            </label>
            <label className="field">
              <span>{nature === "SERVICE" ? "Prestation" : "Article ou produit"}</span>
              <input aria-label={`Article ou produit, ligne ${index + 1}`} type="text" value={row.name ?? ""} onChange={(event) => update(index, "name", event.target.value)} />
            </label>
            {nature === "MANUFACTURED" && <>
              <NumberField label="Quantité produite" name={`Quantité produite, ligne ${index + 1}`} value={row.quantity_produced} onChange={(content) => update(index, "quantity_produced", content)} />
              <NumberField label="Quantité vendue" name={`Quantité vendue, ligne ${index + 1}`} value={row.quantity} onChange={(content) => update(index, "quantity", content)} />
              <NumberField label="Pertes et rebuts (quantité)" name={`Pertes et rebuts, ligne ${index + 1}`} value={row.quantity_scrapped} onChange={(content) => update(index, "quantity_scrapped", content)} />
              <NumberField label="Coût des matières de cette production" name={`Coût des matières, ligne ${index + 1}`} value={row.material_cost} onChange={(content) => update(index, "material_cost", content)} />
              <NumberField label="Main-d'œuvre directe de cette production" name={`Main-d'œuvre directe, ligne ${index + 1}`} value={row.direct_labor} onChange={(content) => update(index, "direct_labor", content)} />
              <NumberField label="Autres coûts directs de production" name={`Autres coûts de production, ligne ${index + 1}`} value={row.other_production_cost} onChange={(content) => update(index, "other_production_cost", content)} />
              <NumberField label="Prix de vente unitaire" name={`Prix de vente, ligne ${index + 1}`} value={row.sale_price} onChange={(content) => update(index, "sale_price", content)} />
            </>}
            {nature === "RESOLD" && <>
              <NumberField label="Quantité vendue" name={`Quantité, ligne ${index + 1}`} value={row.quantity} onChange={(content) => update(index, "quantity", content)} />
              <NumberField label="Prix d'achat unitaire" name={`Prix de revient, ligne ${index + 1}`} value={row.unit_cost} onChange={(content) => update(index, "unit_cost", content)} />
              <NumberField label="Prix de vente unitaire" name={`Prix de vente, ligne ${index + 1}`} value={row.sale_price} onChange={(content) => update(index, "sale_price", content)} />
            </>}
            {nature === "SERVICE" && <>
              <NumberField label="Quantité vendue" name={`Quantité, ligne ${index + 1}`} value={row.quantity} onChange={(content) => update(index, "quantity", content)} />
              <NumberField label="Coût direct unitaire, s'il existe" name={`Coût direct, ligne ${index + 1}`} value={row.unit_cost} onChange={(content) => update(index, "unit_cost", content)} />
              <NumberField label="Prix de vente unitaire" name={`Prix de vente, ligne ${index + 1}`} value={row.sale_price} onChange={(content) => update(index, "sale_price", content)} />
            </>}
          </div>
          <div className="finance-recap">
            <div className="recap-item"><span className="recap-label">Chiffre d'affaires retenu</span><span className="recap-value">{formatMoney(figures.sales, currency)}</span></div>
            <div className="recap-item"><span className="recap-label">{nature === "MANUFACTURED" ? "Coût de revient unitaire" : nature === "SERVICE" ? "Coût direct unitaire" : "Prix d'achat unitaire"}</span><span className="recap-value">{nature === "SERVICE" && productAmount(row.unit_cost) == null ? "Aucun" : formatMoney(figures.unitCost, currency)}</span></div>
            <div className="recap-item"><span className="recap-label">Coût des quantités vendues</span><span className="recap-value">{nature === "SERVICE" && productAmount(row.unit_cost) == null && figures.sales != null ? "Aucun" : formatMoney(figures.cost, currency)}</span></div>
            <div className="recap-item strong"><span className="recap-label">Marge</span><span className="recap-value">{formatMoney(figures.margin, currency)}</span></div>
            {nature === "MANUFACTURED" && <div className="recap-item"><span className="recap-label">Production non vendue</span><span className="recap-value">{figures.unsold == null ? "—" : figures.unsold.toLocaleString("fr-FR")}</span></div>}
            {nature === "MANUFACTURED" && scrap != null && <div className="recap-item"><span className="recap-label">Pertes et rebuts</span><span className="recap-value">{scrap.toLocaleString("fr-FR")}</span></div>}
          </div>
          {nature === "MANUFACTURED" && <p className="muted small">Le chiffre d'affaires retenu est la quantité vendue multipliée par le prix de vente. Le coût unitaire est la somme des matières, de la main-d'œuvre directe et des autres coûts directs, divisée par la quantité produite. Les rebuts restent dans ce coût : ils ne sont pas déduits une seconde fois.</p>}
          {nature === "SERVICE" && <p className="muted small">Laisser le coût direct vide s'il n'y en a pas. La marge est alors égale au chiffre d'affaires. Le champ n'est pas remplacé par zéro.</p>}
          {nature === "MANUFACTURED" && figures.unsold != null && figures.unsold < 0 && <p className="form-error">Les ventes dépassent la production de la période. Le surplus vient d'un stock déjà constitué, ou l'écart est à expliquer dans le commentaire.</p>}
          <label className="field">
            <span>Commentaire : fournisseur, qualité, saison, source du prix</span>
            <textarea rows={2} aria-label={`Commentaire, ligne ${index + 1}`} value={row.comment ?? ""} onChange={(event) => update(index, "comment", event.target.value)} />
          </label>
        </article>;
      })}
    </div>
    {rows.length < 120 && <button type="button" className="btn btn-ghost product-sheet-add" onClick={() => onChange({ ...value, products: [...rows, { nature: "RESOLD" }] })}>Ajouter une ligne</button>}
    {manufactures && <div className="product-line">
      <h4>Stocks de production à la date d'arrêté</h4>
      <p className="muted small">Matières, en-cours et produits finis. Ces valeurs ne sont pas ajoutées au chiffre d'affaires. Les charges de période restent dans les charges.</p>
      <div className="form-grid two-col">
        {PRODUCTION_STOCKS.map((stock) => (
          <NumberField
            key={stock.key}
            label={stock.label}
            name={stock.label}
            value={typeof value[stock.key] === "string" ? value[stock.key] as string : ""}
            onChange={(content) => onChange({ ...value, [stock.key]: content })}
          />
        ))}
      </div>
    </div>}
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

function NumberField({ label, name, value, onChange }: { label: string; name: string; value?: string; onChange: (value: string) => void }) {
  return <label className="field">
    <span>{label}</span>
    <input aria-label={name} type="number" step="any" min={0} value={value ?? ""} onChange={(event) => onChange(event.target.value)} />
  </label>;
}
