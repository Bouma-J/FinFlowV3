export type ProductNature = "RESOLD" | "MANUFACTURED" | "SERVICE";

export const PRODUCT_NATURES: { value: ProductNature; label: string }[] = [
  { value: "RESOLD", label: "Revendu" },
  { value: "MANUFACTURED", label: "Fabriqué" },
  { value: "SERVICE", label: "Service" },
];

export const PRODUCTION_IDENTITY: { key: string; label: string }[] = [
  { key: "production_main_products", label: "Produits fabriqués" },
  { key: "production_process", label: "Procédé" },
  { key: "production_capacity", label: "Capacité installée" },
  { key: "production_utilization", label: "Capacité réellement utilisée" },
  { key: "production_main_material", label: "Matière ou intrant principal" },
  { key: "production_other_inputs", label: "Autres intrants critiques" },
  { key: "production_workshop", label: "Atelier, lieu et équipement principal" },
  { key: "production_workforce", label: "Main-d'œuvre de production" },
  { key: "production_quality", label: "Qualité, rebuts et conformité" },
  { key: "production_comment", label: "Réserves sur la production" },
];

export const PRODUCTION_STOCKS: { key: string; label: string }[] = [
  { key: "production_stock_materials", label: "Stock de matières premières" },
  { key: "production_stock_wip", label: "Stock d'en-cours" },
  { key: "production_stock_finished", label: "Stock de produits finis" },
];

export function productNature(row: { nature?: string }): ProductNature {
  if (row.nature === "MANUFACTURED" || row.nature === "SERVICE") return row.nature;
  return "RESOLD";
}

export function productAmount(value: string | undefined): number | null {
  if (value == null || value.trim() === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

export interface ProductFigures {
  sales: number | null;
  cost: number | null;
  unitCost: number | null;
  margin: number | null;
  produced: number | null;
  sold: number | null;
  unsold: number | null;
}

export function retainedActivityMargin(products: unknown, turnover: unknown, expenses: unknown): { value: number | null; source: "sheet" | "activity" | "" } {
  if (Array.isArray(products) && products.length > 0) {
    const figures = products.map((row) => productFigures((row ?? {}) as Record<string, string>));
    if (figures.every((item) => item.margin != null)) {
      return { value: figures.reduce((total, item) => total + (item.margin ?? 0), 0), source: "sheet" };
    }
  }
  const sales = productAmount(turnover == null ? undefined : String(turnover));
  const charges = productAmount(expenses == null ? undefined : String(expenses));
  if (sales == null || charges == null) return { value: null, source: "" };
  return { value: sales - charges, source: "activity" };
}

export function productFigures(row: Record<string, string | undefined>): ProductFigures {
  const nature = productNature(row);
  const sold = productAmount(row.quantity);
  const price = productAmount(row.sale_price);
  const sales = sold != null && price != null ? sold * price : null;
  const produced = nature === "MANUFACTURED" ? productAmount(row.quantity_produced) : null;
  let unitCost: number | null = null;
  let cost: number | null = null;
  if (nature === "MANUFACTURED") {
    const material = productAmount(row.material_cost);
    const labor = productAmount(row.direct_labor);
    const other = productAmount(row.other_production_cost);
    if (produced != null && produced > 0 && material != null && labor != null && other != null) {
      unitCost = (material + labor + other) / produced;
    }
    cost = unitCost != null && sold != null ? unitCost * sold : null;
  } else if (nature === "SERVICE") {
    unitCost = productAmount(row.unit_cost);
    cost = sold == null ? null : unitCost == null ? 0 : unitCost * sold;
  } else {
    unitCost = productAmount(row.unit_cost);
    cost = sold != null && unitCost != null ? sold * unitCost : null;
  }
  return {
    sales,
    cost,
    unitCost,
    margin: sales != null && cost != null ? sales - cost : null,
    produced,
    sold,
    unsold: produced != null && sold != null ? produced - sold : null,
  };
}
