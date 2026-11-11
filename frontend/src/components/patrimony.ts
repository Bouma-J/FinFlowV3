export type BalanceSide = {
  stock: unknown;
  receivables: unknown;
  cash: unknown;
  fixed: unknown;
  debt: unknown;
};

export type BalanceReading = {
  assets: number | null;
  assetsPrev: number | null;
  assetsVariation: number | null;
  assetsRate: number | null;
  bfr: number | null;
  bfrPrev: number | null;
  bfrVariation: number | null;
  bfrRate: number | null;
  net: number | null;
  netPrev: number | null;
  netVariation: number | null;
};

function money(value: number): number {
  return Math.round(value * 100) / 100;
}

export function presentAmount(value: unknown): number | null {
  if (value == null || String(value).trim() === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function sumPresent(values: Array<number | null>): number | null {
  if (values.every((item) => item == null)) return null;
  return money(values.reduce<number>((total, item) => total + (item ?? 0), 0));
}

function variation(current: number | null, previous: number | null): number | null {
  if (current == null || previous == null) return null;
  return money(current - previous);
}

function variationRate(current: number | null, previous: number | null): number | null {
  if (current == null || previous == null || previous === 0) return null;
  return money(((current - previous) / Math.abs(previous)) * 100);
}

export function activityBalanceReading(current: BalanceSide, previous: BalanceSide): BalanceReading {
  const assets = sumPresent([
    presentAmount(current.stock), presentAmount(current.receivables),
    presentAmount(current.cash), presentAmount(current.fixed),
  ]);
  const assetsPrev = sumPresent([
    presentAmount(previous.stock), presentAmount(previous.receivables),
    presentAmount(previous.cash), presentAmount(previous.fixed),
  ]);
  const bfrParts = [presentAmount(current.stock), presentAmount(current.receivables), presentAmount(current.debt)];
  const bfrPrevParts = [presentAmount(previous.stock), presentAmount(previous.receivables), presentAmount(previous.debt)];
  const bfr = bfrParts.every((item) => item == null) ? null : money((bfrParts[0] ?? 0) + (bfrParts[1] ?? 0) - (bfrParts[2] ?? 0));
  const bfrPrev = bfrPrevParts.every((item) => item == null) ? null : money((bfrPrevParts[0] ?? 0) + (bfrPrevParts[1] ?? 0) - (bfrPrevParts[2] ?? 0));
  const debt = presentAmount(current.debt);
  const debtPrev = presentAmount(previous.debt);
  const net = assets == null && debt == null ? null : money((assets ?? 0) - (debt ?? 0));
  const netPrev = assetsPrev == null && debtPrev == null ? null : money((assetsPrev ?? 0) - (debtPrev ?? 0));
  return {
    assets, assetsPrev, assetsVariation: variation(assets, assetsPrev), assetsRate: variationRate(assets, assetsPrev),
    bfr, bfrPrev, bfrVariation: variation(bfr, bfrPrev), bfrRate: variationRate(bfr, bfrPrev),
    net, netPrev, netVariation: variation(net, netPrev),
  };
}

export function householdPatrimonyTotal(details: Record<string, unknown> | undefined, values: unknown[]): number | null {
  const amounts = values.map(presentAmount);
  const extras = Array.isArray(details?.household_assets) ? details.household_assets : [];
  extras.forEach((row) => {
    const source = (row ?? {}) as Record<string, unknown>;
    amounts.push(presentAmount(source.amount));
  });
  return sumPresent(amounts);
}

export function netPatrimony(activityNet: number | null, household: number | null): number | null {
  if (activityNet == null && household == null) return null;
  return money((activityNet ?? 0) + (household ?? 0));
}
