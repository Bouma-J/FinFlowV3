export type AnalysisPath = "STATEMENTS" | "RECONSTITUTED" | "SALARY" | "ACTIVITY" | "MIXED" | "GROUP";

const ALL = "all" as const;

const SECTION_PATHS: Record<string, readonly AnalysisPath[] | typeof ALL> = {
  "fa-params": ALL,
  "fa-quality": ALL,
  "fa-debt": ALL,
  "fa-income": ["SALARY", "ACTIVITY", "MIXED"],
  "fa-stability": ["SALARY", "MIXED"],
  "fa-group": ["GROUP"],
  "fa-business": ["RECONSTITUTED", "GROUP"],
  "fa-statements": ["STATEMENTS", "ACTIVITY", "MIXED", "GROUP"],
  "fa-activity": ["ACTIVITY", "MIXED"],
  "fa-stock-margin": ["ACTIVITY", "MIXED"],
  "fa-purchases": ["ACTIVITY", "MIXED"],
  "fa-sales-calc": ["ACTIVITY", "MIXED"],
  "fa-operating": ["ACTIVITY", "MIXED"],
  "fa-family": ["ACTIVITY", "MIXED"],
  "fa-simplified-result": ["ACTIVITY", "MIXED"],
  "fa-cash-check": ["ACTIVITY", "MIXED"],
  "fa-prior-year": ["ACTIVITY", "MIXED"],
  "fa-patrimony": ["ACTIVITY", "MIXED"],
  "fa-committee": ["ACTIVITY", "MIXED"],
  "fa-exploitation": ["RECONSTITUTED"],
  "fa-charges": ["SALARY", "ACTIVITY", "MIXED"],
  "fa-cycle": ["STATEMENTS", "RECONSTITUTED", "ACTIVITY", "MIXED", "GROUP"],
  "fa-treasury": ALL,
  "fa-balance": ["RECONSTITUTED"],
  "fa-trend": ["RECONSTITUTED", "ACTIVITY", "MIXED", "GROUP"],
  "fa-minimal": ["RECONSTITUTED", "ACTIVITY", "MIXED", "GROUP"],
  "fa-collateral": ALL,
  "fa-sector": ["STATEMENTS", "RECONSTITUTED", "ACTIVITY", "MIXED", "GROUP"],
  "fa-es": ["STATEMENTS", "RECONSTITUTED", "ACTIVITY", "MIXED", "GROUP"],
  "fa-conclusion": ALL,
};

const THEME_SECTIONS: Record<string, readonly string[]> = {
  "États financiers": ["fa-statements"],
  "Compte de résultat": ["fa-exploitation"],
  "Groupement": ["fa-group"],
  "Revenus du ménage": ["fa-income"],
  "Charges du ménage": ["fa-charges"],
  "Emploi et stabilité": ["fa-stability"],
  "Patrimoine du ménage": ["fa-charges"],
  "Activité indépendante": ["fa-activity"],
  "Stock": ["fa-business", "fa-activity"],
  "Ventes et produits": ["fa-business", "fa-activity"],
  "Bilan": ["fa-balance"],
  "Trésorerie depuis le dernier achat": ["fa-trend"],
  "Trésorerie minimale": ["fa-minimal"],
  "Exercice précédent": ["fa-trend"],
  "Engagements": ["fa-debt"],
  "Flux créditeurs": ["fa-treasury"],
  "Prévisions de trésorerie": ["fa-treasury"],
  "Campagne": ["fa-cycle"],
  "Création": ["fa-cycle"],
  "Références": ["fa-collateral"],
  "Projet": ["fa-treasury"],
  "Fiabilité": ["fa-quality"],
};

export function sectionAllowed(id: string, path: AnalysisPath): boolean {
  const allowed = SECTION_PATHS[id];
  if (!allowed) return false;
  return allowed === ALL || allowed.includes(path);
}

export function themeAllowed(title: string, path: AnalysisPath): boolean {
  const sections = THEME_SECTIONS[title];
  if (!sections) return true;
  return sections.some((id) => sectionAllowed(id, path));
}

export function resolveStatementBasis(details: { statement_basis?: unknown; financial_statements?: unknown } | undefined): "STATEMENTS" | "RECONSTITUTED" {
  const value = details?.statement_basis;
  if (value === "STATEMENTS" || value === "RECONSTITUTED") return value;
  return Array.isArray(details?.financial_statements) && details.financial_statements.length > 0 ? "STATEMENTS" : "RECONSTITUTED";
}

export function resolveAnalysisPath(input: {
  clientType?: string;
  individualProfile?: string;
  hasSideActivity?: boolean;
  statementBasis?: string;
}): AnalysisPath {
  if (input.clientType === "PROFESSIONAL") return "GROUP";
  if (input.clientType === "CORPORATE") return input.statementBasis === "STATEMENTS" ? "STATEMENTS" : "RECONSTITUTED";
  const profile = input.individualProfile || "SALARIE";
  const salary = profile === "SALARIE" || profile === "MIXTE";
  const activity = profile === "INDEPENDANT" || profile === "MIXTE" || (profile === "SALARIE" && !!input.hasSideActivity);
  if (salary && activity) return "MIXED";
  if (activity) return "ACTIVITY";
  return "SALARY";
}

export function groupActivityOpen(details: { group_has_activity?: unknown } | undefined, turnover?: unknown, expenses?: unknown): boolean {
  const flag = details?.group_has_activity;
  if (flag === "yes") return true;
  if (flag === "no") return false;
  const sales = turnover == null || String(turnover).trim() === "" ? 0 : Number(turnover);
  const charges = expenses == null || String(expenses).trim() === "" ? 0 : Number(expenses);
  return (Number.isFinite(sales) && sales > 0) || (Number.isFinite(charges) && charges > 0);
}

export function purposeTestText(purpose: string | undefined, reconstituted = false): string {
  if (purpose === "CONSUMPTION") {
    return "Épreuve de cet objet : baisse du revenu du foyer, écrite dans les scénarios défavorables. Sur un parcours salarial, le salaire net doit permettre la quotité cessible.";
  }
  if (purpose === "WORKING_CAPITAL" || purpose === "TREASURY" || purpose === "STOCK") {
    const stock = reconstituted
      ? " L'activité est reconstituée : le stock ou les ventes doivent être rapprochés, ou l'écart écrit dans le commentaire sur le stock."
      : "";
    return `Épreuve de cet objet : baisse des ventes et allongement des créances. Le retard clients se saisit, y compris à zéro.${stock}`;
  }
  if (purpose === "EQUIPMENT" || purpose === "REAL_ESTATE") {
    return "Épreuve de cet objet : le solde prévisionnel mensuel couvre l'échéance. L'investissement de maintien reste visible ; une case vide le reste.";
  }
  if (purpose === "OTHER") {
    return "Épreuve de cet objet : elle s'écrit dans l'avis de synthèse. Une synthèse vide bloque la soumission.";
  }
  return "";
}

export function pathLabel(path: AnalysisPath): string {
  return {
    STATEMENTS: "Entreprise — états financiers établis",
    RECONSTITUTED: "Entreprise — activité à reconstituer",
    SALARY: "Personne physique — salarié",
    ACTIVITY: "Personne physique — activité génératrice de revenus",
    MIXED: "Personne physique — salaire et activité",
    GROUP: "Groupement",
  }[path];
}
