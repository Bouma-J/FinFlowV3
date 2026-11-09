import { formatMoney } from "@/components/ui";
import type { FinancialDocument } from "@/api/types";
import {
  BALANCE_GROUPS,
  CASHFLOW_LINES,
  INCOME_GROUPS,
  NOTE_AMOUNT_LINES,
  STATEMENT_PIECES,
  amount,
  balanceTotals,
  blankStatement,
  incomeTotals,
  monthSpan,
  noteGap,
  referenceStatement,
  statementComparisons,
  type FinancialStatement,
  type StatementGroup,
  type StatementLine,
  type StatementPiece,
} from "@/components/financialStatements";

function Amounts({
  lines,
  source,
  onChange,
}: {
  lines: StatementLine[];
  source: Record<string, string>;
  onChange: (key: string, value: string) => void;
}) {
  return (
    <div className="form-grid two-col">
      {lines.map((line) => (
        <label className="field" key={line.key}>
          <span>{line.label}</span>
          <input
            type="number"
            step="any"
            value={source[line.key] ?? ""}
            onChange={(event) => onChange(line.key, event.target.value)}
          />
        </label>
      ))}
    </div>
  );
}

function Groups({
  groups,
  source,
  onChange,
}: {
  groups: StatementGroup[];
  source: Record<string, string>;
  onChange: (key: string, value: string) => void;
}) {
  return (
    <>
      {groups.map((group) => (
        <div key={group.title}>
          <p className="subsection-label">{group.title}</p>
          <Amounts lines={group.lines} source={source} onChange={onChange} />
        </div>
      ))}
    </>
  );
}

function Figure({ label, value, currency }: { label: string; value: number | null; currency: string }) {
  return (
    <div className="statement-figure">
      <span>{label}</span>
      <strong>{value == null ? "—" : formatMoney(value, currency)}</strong>
    </div>
  );
}

function PieceFile({
  label,
  existing,
  pending,
  onChange,
}: {
  label: string;
  existing?: FinancialDocument;
  pending?: File;
  onChange: (file: File | null) => void;
}) {
  return (
    <label className="field file-field statement-file">
      <span>{label}</span>
      {existing && (
        <a className="doc-chip" href={existing.file} target="_blank" rel="noreferrer">
          {existing.label || "Document enregistré"}
        </a>
      )}
      <input
        type="file"
        accept="image/*,application/pdf"
        onChange={(event) => onChange(event.target.files?.[0] ?? null)}
      />
      {pending && <span className="muted small">{existing ? `Remplace le document : ${pending.name}` : pending.name}</span>}
    </label>
  );
}

export function FinancialStatementsEditor({
  statements,
  onChange,
  files,
  onFile,
  documents,
  currency,
}: {
  statements: FinancialStatement[];
  onChange: (next: FinancialStatement[]) => void;
  files: Record<string, File>;
  onFile: (exerciseId: string, piece: StatementPiece, file: File | null) => void;
  documents: FinancialDocument[];
  currency: string;
}) {
  const reference = referenceStatement(statements);
  const known = new Map(documents.map((document) => [document.id, document]));
  function update(index: number, patch: Partial<FinancialStatement>) {
    onChange(statements.map((row, rowIndex) => rowIndex === index ? { ...row, ...patch } : row));
  }
  function updateMap(index: number, piece: "income" | "balance" | "cashflow" | "notes", key: string, value: string) {
    const row = statements[index];
    update(index, { [piece]: { ...row[piece], [key]: value } });
  }
  return (
    <div className="statement-list">
      {statements.map((row, index) => {
        const income = incomeTotals(row.income);
        const balance = balanceTotals(row.balance);
        const opening = amount(row.cashflow.opening_cash);
        const closing = amount(row.cashflow.closing_cash);
        const cashGap = opening != null && closing != null && amount(row.cashflow.cash_change_read) != null
          ? Math.round((closing - opening - (amount(row.cashflow.cash_change_read) as number)) * 100) / 100
          : null;
        const span = monthSpan(row.start_date, row.end_date);
        return (
          <article className="external-credit statement-exercise" key={row.id}>
            <div className="external-credit-head">
              <h4>{row.label.trim() || `Exercice ${index + 1}`}</h4>
              {reference?.id === row.id && <span className="statement-badge">Exercice retenu</span>}
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => onChange(statements.filter((item) => item.id !== row.id))}
              >
                Retirer
              </button>
            </div>
            <div className="form-grid two-col">
              <label className="field">
                <span>Intitulé</span>
                <input value={row.label} onChange={(event) => update(index, { label: event.target.value })} />
              </label>
              <label className="field">
                <span>Nature</span>
                <select value={row.nature} onChange={(event) => update(index, { nature: event.target.value as FinancialStatement["nature"] })}>
                  <option value="">— Sélectionner —</option>
                  <option value="CLOSED">Exercice clos</option>
                  <option value="INTERIM">Situation intermédiaire</option>
                </select>
              </label>
              <label className="field">
                <span>Date de début</span>
                <input type="date" value={row.start_date} onChange={(event) => update(index, { start_date: event.target.value })} />
              </label>
              <label className="field">
                <span>Date de fin / arrêté</span>
                <input type="date" value={row.end_date} onChange={(event) => update(index, { end_date: event.target.value })} />
              </label>
              <label className="field">
                <span>Établi par</span>
                <select value={row.prepared_by} onChange={(event) => update(index, { prepared_by: event.target.value as FinancialStatement["prepared_by"] })}>
                  <option value="">— Sélectionner —</option>
                  <option value="EXPERT">Expert-comptable</option>
                  <option value="FIRM">Cabinet</option>
                  <option value="CLIENT">Client</option>
                </select>
              </label>
              <label className="field checkbox-field">
                <span className="checkbox-inline">
                  <input
                    type="checkbox"
                    checked={row.certified === "yes"}
                    onChange={(event) => update(index, { certified: event.target.checked ? "yes" : "no" })}
                  />
                  Visé ou certifié
                </span>
              </label>
            </div>
            {span != null && <p className="muted small">Durée : {span} mois.</p>}
            <label className="field">
              <span>Commentaire de l'exercice</span>
              <textarea rows={2} value={row.comment} onChange={(event) => update(index, { comment: event.target.value })} />
            </label>

            <details className="statement-piece" open>
              <summary>Compte de résultat</summary>
              <p className="muted small">Saisissez le signe imprimé sur l'état. Une augmentation de stock se saisit en négatif sur la ligne de variation. Une case vide reste vide et n'entre pas dans le sous-total.</p>
              <Groups groups={INCOME_GROUPS} source={row.income} onChange={(key, value) => updateMap(index, "income", key, value)} />
              <div className="statement-figures">
                <Figure label="Marge commerciale" value={income.commercialMargin} currency={currency} />
                <Figure label="Chiffre d'affaires" value={income.turnover} currency={currency} />
                <Figure label="Valeur ajoutée" value={income.valueAdded} currency={currency} />
                <Figure label="Excédent brut d'exploitation" value={income.ebe} currency={currency} />
                <Figure label="Résultat d'exploitation" value={income.operatingResult} currency={currency} />
                <Figure label="Résultat financier" value={income.financialResult} currency={currency} />
                <Figure label="Résultat des activités ordinaires" value={income.ordinaryResult} currency={currency} />
                <Figure label="Résultat hors activités ordinaires" value={income.haoResult} currency={currency} />
                <Figure label="Résultat net calculé" value={income.netResult} currency={currency} />
                <Figure label="Écart avec le résultat net lu" value={income.netGap} currency={currency} />
              </div>
              <PieceFile
                label="Document du compte de résultat"
                existing={known.get(row.documents.income)}
                pending={files[`${row.id}:income`]}
                onChange={(file) => onFile(row.id, "income", file)}
              />
            </details>

            <details className="statement-piece" open>
              <summary>Bilan</summary>
              <p className="muted small">Montants nets imprimés au bilan. Le brut et les amortissements se saisissent dans les notes.</p>
              <Groups groups={BALANCE_GROUPS} source={row.balance} onChange={(key, value) => updateMap(index, "balance", key, value)} />
              <div className="statement-figures">
                <Figure label="Total actif immobilisé" value={balance.fixed} currency={currency} />
                <Figure label="Total actif circulant" value={balance.current} currency={currency} />
                <Figure label="Total général actif" value={balance.assets} currency={currency} />
                <Figure label="Total capitaux propres" value={balance.equity} currency={currency} />
                <Figure label="Total ressources stables" value={balance.stable} currency={currency} />
                <Figure label="Total général passif" value={balance.liabilities} currency={currency} />
                <Figure label="Écart actif − passif" value={balance.balanceGap} currency={currency} />
                <Figure label="Écart sur capitaux propres" value={balance.equityGap} currency={currency} />
              </div>
              <PieceFile
                label="Document du bilan"
                existing={known.get(row.documents.balance)}
                pending={files[`${row.id}:balance`]}
                onChange={(file) => onFile(row.id, "balance", file)}
              />
            </details>

            <details className="statement-piece" open>
              <summary>Tableau des flux de trésorerie</summary>
              <Amounts lines={CASHFLOW_LINES} source={row.cashflow} onChange={(key, value) => updateMap(index, "cashflow", key, value)} />
              <div className="statement-figures">
                <Figure label="Variation calculée (clôture − ouverture)" value={opening != null && closing != null ? Math.round((closing - opening) * 100) / 100 : null} currency={currency} />
                <Figure label="Écart avec la variation lue" value={cashGap} currency={currency} />
              </div>
              <PieceFile
                label="Document du tableau des flux"
                existing={known.get(row.documents.cashflow)}
                pending={files[`${row.id}:cashflow`]}
                onChange={(file) => onFile(row.id, "cashflow", file)}
              />
            </details>

            <details className="statement-piece" open>
              <summary>Notes annexes</summary>
              <Amounts lines={NOTE_AMOUNT_LINES} source={row.notes} onChange={(key, value) => updateMap(index, "notes", key, value)} />
              <div className="statement-figures">
                <Figure label="Écart net des immobilisations" value={noteGap(row.notes.fixed_gross, row.notes.fixed_depreciation, row.notes.fixed_net)} currency={currency} />
                <Figure label="Écart net des stocks" value={noteGap(row.notes.stock_gross, row.notes.stock_impairment, row.notes.stock_net)} currency={currency} />
                <Figure label="Écart net des créances" value={noteGap(row.notes.receivable_gross, row.notes.receivable_impairment, row.notes.receivable_net)} currency={currency} />
              </div>
              <div className="form-grid two-col">
                <label className="field">
                  <span>Effectif moyen</span>
                  <input
                    type="number"
                    min={0}
                    step={1}
                    value={row.notes.headcount ?? ""}
                    onChange={(event) => updateMap(index, "notes", "headcount", event.target.value)}
                  />
                </label>
              </div>
              <label className="field">
                <span>Engagements hors bilan : cautions, crédits-bails, hypothèques, nantissements</span>
                <textarea rows={3} value={row.notes.off_balance ?? ""} onChange={(event) => updateMap(index, "notes", "off_balance", event.target.value)} />
              </label>
              <label className="field">
                <span>Commentaire : méthodes, périmètre, événements après la clôture</span>
                <textarea rows={3} value={row.notes.comment ?? ""} onChange={(event) => updateMap(index, "notes", "comment", event.target.value)} />
              </label>
              <PieceFile
                label="Document des notes"
                existing={known.get(row.documents.notes)}
                pending={files[`${row.id}:notes`]}
                onChange={(file) => onFile(row.id, "notes", file)}
              />
            </details>
          </article>
        );
      })}
      <StatementComparisonTable statements={statements} currency={currency} />
      <button type="button" className="btn btn-ghost" onClick={() => onChange([...statements, blankStatement()])}>
        Ajouter un exercice
      </button>
    </div>
  );
}

export function StatementComparisonTable({ statements, currency }: { statements: FinancialStatement[]; currency: string }) {
  const pairs = statementComparisons(statements);
  if (!pairs.length) return null;
  return (
    <div className="statement-compare">
      {pairs.map((pair) => (
        <table key={`${pair.currentLabel}-${pair.previousLabel}`}>
          <caption>Comparaison {pair.currentLabel} / {pair.previousLabel}</caption>
          <thead>
            <tr>
              <th>Poste</th>
              <th>{pair.currentLabel}</th>
              <th>{pair.previousLabel}</th>
              <th>Écart</th>
            </tr>
          </thead>
          <tbody>
            {pair.lines.map((line) => (
              <tr key={line.label}>
                <td>{line.label}</td>
                <td>{line.current == null ? "—" : formatMoney(line.current, currency)}</td>
                <td>{line.previous == null ? "—" : formatMoney(line.previous, currency)}</td>
                <td>{line.gap == null ? "—" : formatMoney(line.gap, currency)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ))}
    </div>
  );
}

export function FinancialStatementsReadout({
  statements,
  documents,
  currency,
}: {
  statements: FinancialStatement[];
  documents: FinancialDocument[];
  currency: string;
}) {
  if (!statements.length) return null;
  const reference = referenceStatement(statements);
  const known = new Map(documents.map((document) => [document.id, document]));
  const labels = new Map(STATEMENT_PIECES.map((piece) => [piece.key, piece.label]));
  return (
    <>
      {statements.map((row) => {
        const income = incomeTotals(row.income);
        const balance = balanceTotals(row.balance);
        const pieces = [
          ["income", [...INCOME_GROUPS.flatMap((group) => group.lines)]],
          ["balance", [...BALANCE_GROUPS.flatMap((group) => group.lines)]],
          ["cashflow", CASHFLOW_LINES],
          ["notes", NOTE_AMOUNT_LINES],
        ] as const;
        return (
          <article className="external-credit-read" key={row.id}>
            <h5>
              {row.label || "Exercice"}
              {reference?.id === row.id ? " — exercice retenu" : ""}
            </h5>
            <dl className="def-list two">
              {row.nature && <div><dt>Nature</dt><dd>{row.nature === "CLOSED" ? "Exercice clos" : "Situation intermédiaire"}</dd></div>}
              {row.start_date && <div><dt>Début</dt><dd>{row.start_date}</dd></div>}
              {row.end_date && <div><dt>Fin / arrêté</dt><dd>{row.end_date}</dd></div>}
              {row.prepared_by && <div><dt>Établi par</dt><dd>{{ EXPERT: "Expert-comptable", FIRM: "Cabinet", CLIENT: "Client" }[row.prepared_by]}</dd></div>}
              {row.certified && <div><dt>Visé ou certifié</dt><dd>{row.certified === "yes" ? "Oui" : "Non"}</dd></div>}
            </dl>
            {pieces.map(([piece, lines]) => {
              const source = row[piece];
              const filled = lines.filter((line) => amount(source[line.key]) != null);
              const document = known.get(row.documents[piece]);
              if (!filled.length && !document) return null;
              return (
                <div key={piece}>
                  <p className="subsection-label">{labels.get(piece)}</p>
                  {!!filled.length && (
                    <dl className="def-list two">
                      {filled.map((line) => (
                        <div key={line.key}><dt>{line.label}</dt><dd>{formatMoney(amount(source[line.key]), currency)}</dd></div>
                      ))}
                    </dl>
                  )}
                  {document && <a className="doc-chip" href={document.file} target="_blank" rel="noreferrer">{document.label || labels.get(piece)}</a>}
                </div>
              );
            })}
            <div className="statement-figures">
              <Figure label="Chiffre d'affaires" value={income.turnover} currency={currency} />
              <Figure label="Résultat net calculé" value={income.netResult} currency={currency} />
              <Figure label="Écart avec le résultat net lu" value={income.netGap} currency={currency} />
              <Figure label="Total général actif" value={balance.assets} currency={currency} />
              <Figure label="Total général passif" value={balance.liabilities} currency={currency} />
              <Figure label="Écart actif − passif" value={balance.balanceGap} currency={currency} />
            </div>
            {row.notes.headcount && <p>Effectif moyen : {row.notes.headcount}</p>}
            {row.notes.off_balance && <p>{row.notes.off_balance}</p>}
            {row.notes.comment && <p>{row.notes.comment}</p>}
            {row.comment && <p>{row.comment}</p>}
          </article>
        );
      })}
      <StatementComparisonTable statements={statements} currency={currency} />
    </>
  );
}

export function ActivityStatementReading({
  statements,
  margin,
  currency,
  audience = "activity",
}: {
  statements: FinancialStatement[];
  margin: { value: number | null; source: "sheet" | "activity" | "" };
  currency: string;
  audience?: "activity" | "group";
}) {
  const current = referenceStatement(statements);
  const net = current ? amount(current.income.net_result_read) ?? incomeTotals(current.income).netResult : null;
  const equity = current ? balanceTotals(current.balance).equity : null;
  const cash = current ? amount(current.balance.cash_and_banks) : null;
  const gap = net != null && margin.value != null ? Math.round((net - margin.value) * 100) / 100 : null;
  const marginLabel = margin.source === "sheet" ? "Marge des fiches" : audience === "group" ? "Marge de l'activité commune (chiffre d'affaires − charges)" : "Marge de l'activité (chiffre d'affaires − charges)";
  return <div className="product-line">
    <h4>{audience === "group" ? "Lecture à côté des cotisations" : "Lecture à côté de l'activité"}</h4>
    <p className="muted small">{audience === "group"
      ? "Le résultat, les capitaux propres et la trésorerie sont lus sur l'exercice retenu. Ils ne remplacent pas les cotisations et n'ajoutent pas l'épargne au revenu. L'écart n'apparaît que lorsque le résultat et la marge sont tous deux renseignés."
      : "Le résultat, les capitaux propres et la trésorerie sont lus sur l'exercice retenu. Ils ne corrigent pas le salaire, le chiffre d'affaires de l'activité ni les charges du foyer. L'écart n'apparaît que lorsque le résultat et la marge sont tous deux renseignés. Si les deux périodes n'ont pas la même durée, cet écart reste une réserve."}</p>
    {!current && <p className="muted small">Aucun exercice daté. Le résultat, les capitaux propres et la trésorerie restent vides.</p>}
    <div className="finance-recap">
      <div className="recap-item"><span className="recap-label">Résultat net de l'état</span><span className="recap-value">{formatMoney(net, currency)}</span></div>
      <div className="recap-item"><span className="recap-label">{marginLabel}</span><span className="recap-value">{formatMoney(margin.value, currency)}</span></div>
      <div className="recap-item"><span className="recap-label">Écart résultat − marge</span><span className="recap-value">{formatMoney(gap, currency)}</span></div>
      <div className="recap-item"><span className="recap-label">Capitaux propres</span><span className="recap-value">{formatMoney(equity, currency)}</span></div>
      <div className="recap-item"><span className="recap-label">Trésorerie de l'état</span><span className="recap-value">{formatMoney(cash, currency)}</span></div>
    </div>
  </div>;
}
