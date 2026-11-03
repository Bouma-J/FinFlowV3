import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Calculator,
  CalendarClock,
  FileDown,
  Info,
  PiggyBank,
  Play,
  RotateCcw,
} from "lucide-react";
import { useMemo, useState, type FormEvent, type ReactNode } from "react";

import { api } from "@/api/client";
import {
  CREDIT_LABELS,
  type CbsCatalogItem,
  type Paginated,
  type SimulationResult,
} from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { Card, PageHeader, formatMoney } from "@/components/ui";
import { useTenantBranding } from "@/hooks/useTenantBranding";
import { exportSimulationPdf } from "@/utils/exportSimulationPdf";

function formatDueDate(value: string) {
  if (!value) return "—";
  // Dates ISO (YYYY-MM-DD) : éviter le décalage fuseau de Date.parse
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  if (m) {
    return `${m[3]}/${m[2]}/${m[1]}`;
  }
  return new Date(value).toLocaleDateString("fr-FR");
}

/** Arrondi à la dizaine — même règle que le moteur backend. */
function roundStep(n: number) {
  return Math.round(n / 10) * 10;
}

const PERIODICITY_FALLBACK = Object.keys(CREDIT_LABELS.periodicity);
/** Mécanismes proposés à la saisie (CONSTANT conservé en lecture seule historique). */
const MECHANISM_FALLBACK = ["DEGRESSIVE", "IN_FINE", "BULLET"] as const;

function todayISO() {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

const DEFAULT_FORM = {
  amount: "1000000",
  annual_rate: "12.5",
  months: "12",
  periodicity: "MONTHLY",
  mechanism: "DEGRESSIVE",
  include_savings: false,
  savings_rate: "5",
  simulation_date: todayISO(),
  first_due_date: "",
};

type SimForm = typeof DEFAULT_FORM;

function Metric({
  label,
  value,
  tone,
}: {
  label: string;
  value: ReactNode;
  tone?: "ok" | "warn";
}) {
  return (
    <div className={`metric${tone ? ` metric-${tone}` : ""}`}>
      <span className="metric-label">{label}</span>
      <span className="metric-value">{value}</span>
    </div>
  );
}

function num(v: string | number | null | undefined) {
  if (v === null || v === undefined || v === "") return 0;
  return typeof v === "number" ? v : Number(v);
}

/** Affiche les espaces milliers pendant la saisie (ex. 1 000 000). */
function formatAmountInput(raw: string) {
  const digits = raw.replace(/\D/g, "");
  if (!digits) return "";
  return digits.replace(/\B(?=(\d{3})+(?!\d))/g, "\u00A0");
}

function parseAmountInput(display: string) {
  return display.replace(/\D/g, "");
}

export function SimulatorPage() {
  const [form, setForm] = useState<SimForm>(DEFAULT_FORM);
  const { tenantName, branding } = useTenantBranding();
  const { activeTenant } = useAuth();

  const { data: periodicities } = useQuery({
    queryKey: ["loan-periodicities", activeTenant],
    queryFn: async () =>
      (
        await api.get<Paginated<CbsCatalogItem>>("/loan-periodicities/", {
          params: { is_active: true, page_size: 100 },
        })
      ).data,
  });
  const { data: repaymentMethods } = useQuery({
    queryKey: ["repayment-methods", activeTenant],
    queryFn: async () =>
      (
        await api.get<Paginated<CbsCatalogItem>>("/repayment-methods/", {
          params: { is_active: true, page_size: 100 },
        })
      ).data,
  });

  const periodicityOptions = useMemo(() => {
    const rows = periodicities?.results ?? [];
    if (!rows.length) {
      return PERIODICITY_FALLBACK.map((key) => ({
        value: key,
        label: CREDIT_LABELS.periodicity[key] || key,
      }));
    }
    return rows.map((r) => ({
      value: r.code,
      label: r.cbs_code ? `${r.label} (${r.cbs_code})` : r.label,
    }));
  }, [periodicities]);

  const mechanismOptions = useMemo(() => {
    const rows = repaymentMethods?.results ?? [];
    if (!rows.length) {
      return MECHANISM_FALLBACK.map((key) => ({
        value: key,
        label: CREDIT_LABELS.repayment_mechanism[key] || key,
      }));
    }
    return rows.map((r) => ({
      value: r.code,
      label: r.cbs_code ? `${r.label} → ${r.cbs_code}` : r.label,
    }));
  }, [repaymentMethods]);

  const sim = useMutation({
    mutationFn: async () => {
      const savingsRate =
        form.include_savings && num(form.savings_rate) > 0
          ? form.savings_rate
          : "0";
      const payload: Record<string, string | number | null> = {
        amount: form.amount,
        annual_rate: form.annual_rate,
        months: Number(form.months),
        periodicity: form.periodicity,
        mechanism: form.mechanism,
        savings_rate: savingsRate,
        simulation_date: form.simulation_date || todayISO(),
      };
      if (form.first_due_date) {
        payload.first_due_date = form.first_due_date;
      }
      return (
        await api.post<SimulationResult>("/credit-applications/simulate/", payload)
      ).data;
    },
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    sim.mutate();
  }

  function reset() {
    setForm({ ...DEFAULT_FORM, simulation_date: todayISO() });
    sim.reset();
  }

  const savingsPerInstallment = useMemo(() => {
    if (!form.include_savings) return 0;
    const principal = num(form.amount);
    const rate = num(form.savings_rate);
    if (!principal || rate <= 0) return 0;
    return roundStep((principal * rate) / 100);
  }, [form.amount, form.include_savings, form.savings_rate]);

  const result = sim.data;
  const hasSavings = Boolean(result && num(result.total_savings) > 0);
  const periodLabel =
    periodicityOptions.find((o) => o.value === form.periodicity)?.label ||
    CREDIT_LABELS.periodicity[form.periodicity] ||
    form.periodicity;
  const mechanismLabel =
    mechanismOptions.find((o) => o.value === form.mechanism)?.label ||
    CREDIT_LABELS.repayment_mechanism[form.mechanism] ||
    form.mechanism;

  const installmentLabel = useMemo(() => {
    if (form.mechanism === "BULLET") return "Échéance unique (institution)";
    if (form.mechanism === "IN_FINE") return "1ʳᵉ échéance (intérêts)";
    return `Échéance institution (${periodLabel.toLowerCase()})`;
  }, [form.mechanism, periodLabel]);

  function exportPdf() {
    if (!result) return;
    exportSimulationPdf(result, {
      amount: form.amount,
      annualRate: form.annual_rate,
      months: form.months,
      periodicityLabel: periodLabel,
      mechanismLabel,
      savingsRate: form.include_savings ? form.savings_rate : 0,
      firstDueDate: form.first_due_date || undefined,
      simulationDate: form.simulation_date || undefined,
      tenantName,
      brandPrimary: branding?.brand_primary,
      brandSecondary: branding?.brand_secondary,
      brandAccent: branding?.brand_accent,
    });
  }

  return (
    <div className="page-shell simulator-page">
      <PageHeader
        icon={Calculator}
        title="Simulateur d'amortissement"
        subtitle="Même moteur que les dossiers de crédit — ACT/365, convention CBS"
        actions={
          result ? (
            <button type="button" className="btn btn-ghost" onClick={exportPdf}>
              <FileDown size={16} />
              Exporter PDF
            </button>
          ) : undefined
        }
      />

      <div className="detail-row">
        <Card title="Paramètres du crédit">
          <form onSubmit={submit} className="stack">
            <div className="form-grid two-col">
              <label className="field">
                <span>Montant du crédit (XOF)</span>
                <input
                  type="text"
                  inputMode="numeric"
                  autoComplete="off"
                  required
                  value={formatAmountInput(form.amount)}
                  onChange={(e) =>
                    setForm({ ...form, amount: parseAmountInput(e.target.value) })
                  }
                />
              </label>
              <label className="field">
                <span>Taux d'intérêt annuel (%)</span>
                <input
                  type="number"
                  min={0}
                  step="0.001"
                  required
                  value={form.annual_rate}
                  onChange={(e) =>
                    setForm({ ...form, annual_rate: e.target.value })
                  }
                />
              </label>
              <label className="field">
                <span>Durée (mois)</span>
                <input
                  type="number"
                  min={1}
                  max={600}
                  required
                  value={form.months}
                  onChange={(e) => setForm({ ...form, months: e.target.value })}
                />
              </label>
              <label className="field">
                <span>Périodicité</span>
                <select
                  value={form.periodicity}
                  onChange={(e) =>
                    setForm({ ...form, periodicity: e.target.value })
                  }
                >
                  {periodicityOptions.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>Mécanisme de remboursement</span>
                <select
                  value={form.mechanism}
                  onChange={(e) =>
                    setForm({ ...form, mechanism: e.target.value })
                  }
                >
                  {mechanismOptions.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>Date de simulation</span>
                <input
                  type="date"
                  required
                  value={form.simulation_date}
                  onChange={(e) =>
                    setForm({ ...form, simulation_date: e.target.value })
                  }
                />
              </label>
              <label className="field">
                <span>Date de 1ʳᵉ échéance (optionnel)</span>
                <input
                  type="date"
                  value={form.first_due_date}
                  min={form.simulation_date || undefined}
                  onChange={(e) =>
                    setForm({ ...form, first_due_date: e.target.value })
                  }
                />
              </label>
            </div>

            <div
              className={`simulator-savings${form.include_savings ? " is-on" : ""}`}
            >
              <label className="checkbox-inline simulator-savings-toggle">
                <input
                  type="checkbox"
                  checked={form.include_savings}
                  onChange={(e) =>
                    setForm({ ...form, include_savings: e.target.checked })
                  }
                />
                <PiggyBank size={16} />
                <span>Inclure l'épargne obligatoire</span>
              </label>

              {form.include_savings && (
                <div className="simulator-savings-fields">
                  <label className="field">
                    <span>Taux d'épargne obligatoire (%)</span>
                    <input
                      type="number"
                      min={0.001}
                      step="0.001"
                      required
                      value={form.savings_rate}
                      onChange={(e) =>
                        setForm({ ...form, savings_rate: e.target.value })
                      }
                    />
                  </label>
                  <p className="muted small">
                    Montant fixe par échéance :{" "}
                    <strong>
                      {savingsPerInstallment > 0
                        ? formatMoney(savingsPerInstallment)
                        : "—"}
                    </strong>{" "}
                    (= capital × taux, arrondi à la dizaine). Hors ratios
                    institution — colonne séparée dans le tableau.
                  </p>
                </div>
              )}
            </div>

            <div className="simulator-actions">
              <button
                type="submit"
                className="btn btn-primary"
                disabled={sim.isPending}
              >
                <Play size={16} />
                {sim.isPending ? "Calcul…" : "Simuler l'échéancier"}
              </button>
              <button
                type="button"
                className="btn btn-ghost"
                onClick={reset}
                disabled={sim.isPending}
              >
                <RotateCcw size={16} />
                Réinitialiser
              </button>
            </div>

            {sim.isError && (
              <p className="form-error">
                Impossible de calculer l'échéancier. Vérifiez les paramètres.
              </p>
            )}
          </form>
        </Card>

        <Card
          title={
            <span className="simulator-card-title">
              <CalendarClock size={18} />
              Synthèse
            </span>
          }
        >
          {!result ? (
            <p className="muted">
              Renseignez les paramètres puis lancez la simulation pour obtenir
              l'échéancier prévisionnel.
            </p>
          ) : (
            <>
              <div className="simulator-meta">
                <span>
                  {mechanismLabel} · {periodLabel} · {result.schedule.length}{" "}
                  échéance{result.schedule.length > 1 ? "s" : ""}
                </span>
              </div>
              <div className="metric-grid">
                <Metric
                  label={installmentLabel}
                  value={formatMoney(result.installment ?? result.monthly_payment)}
                />
                {hasSavings && (
                  <Metric
                    label="1ʳᵉ échéance client (avec épargne)"
                    value={formatMoney(result.client_total_first)}
                  />
                )}
                <Metric
                  label="Nombre d'échéances"
                  value={result.schedule.length}
                />
                <Metric
                  label="Intérêts totaux"
                  value={formatMoney(result.total_interest)}
                  tone="warn"
                />
                {hasSavings && (
                  <Metric
                    label="Épargne totale"
                    value={formatMoney(result.total_savings)}
                  />
                )}
                {hasSavings && (
                  <Metric
                    label="Total institution"
                    value={formatMoney(
                      result.total_institution ??
                        num(result.total_repayment) - num(result.total_savings),
                    )}
                  />
                )}
                <Metric
                  label={
                    hasSavings
                      ? "Total à rembourser (client)"
                      : "Total à rembourser"
                  }
                  value={formatMoney(result.total_repayment)}
                  tone="ok"
                />
              </div>
            </>
          )}
        </Card>

        {result && (
          <Card
            title={
              <span className="simulator-schedule-head">
                <span className="simulator-card-title">
                  <CalendarClock size={18} />
                  Tableau d'amortissement
                </span>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={exportPdf}
                >
                  <FileDown size={15} />
                  Exporter PDF
                </button>
              </span>
            }
          >
            <div className="table-scroll">
              <table className="table">
                <thead>
                  <tr>
                    <th>N°</th>
                    <th>Date</th>
                    <th className="num">Capital</th>
                    <th className="num">Intérêt</th>
                    {hasSavings && <th className="num">Épargne</th>}
                    <th className="num">Échéance institution</th>
                    {hasSavings && <th className="num">Total client</th>}
                    <th className="num">Capital restant</th>
                  </tr>
                </thead>
                <tbody>
                  {result.schedule.map((row) => (
                    <tr key={row.number}>
                      <td>{row.number}</td>
                      <td>{formatDueDate(row.due_date)}</td>
                      <td className="num">{formatMoney(row.principal)}</td>
                      <td className="num">{formatMoney(row.interest)}</td>
                      {hasSavings && (
                        <td className="num">{formatMoney(row.savings)}</td>
                      )}
                      <td className="num">
                        {formatMoney(row.institution_due ?? num(row.principal) + num(row.interest))}
                      </td>
                      {hasSavings && (
                        <td className="num">{formatMoney(row.total)}</td>
                      )}
                      <td className="num">{formatMoney(row.balance)}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr>
                    <td colSpan={2}>Totaux</td>
                    <td className="num">
                      {formatMoney(
                        result.schedule.reduce((s, r) => s + num(r.principal), 0),
                      )}
                    </td>
                    <td className="num">{formatMoney(result.total_interest)}</td>
                    {hasSavings && (
                      <td className="num">{formatMoney(result.total_savings)}</td>
                    )}
                    <td className="num">
                      {formatMoney(
                        result.total_institution ??
                          num(result.total_repayment) - num(result.total_savings),
                      )}
                    </td>
                    {hasSavings && (
                      <td className="num">{formatMoney(result.total_repayment)}</td>
                    )}
                    <td className="num">—</td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </Card>
        )}

        <div className="notice-info simulator-basis">
          <Info size={18} />
          <div>
            <strong>Base de calcul (core banking)</strong>
            <ul>
              <li>
                Intérêts jour / jour : taux journalier = taux annuel ÷ 365
                (ACT/365).
              </li>
              <li>
                Dégressif (CBS) : échéance institution constante ; intérêts ↓,
                capital ↑. Le 1ʳᵉ intérêt porte sur une période théorique
                pleine depuis la date de simulation (ex. +1 mois), même si la
                1ʳᵉ échéance est anticipée ou reportée.
              </li>
              <li>
                Montants (capital, intérêts, épargne, échéance) arrondis à la
                dizaine de F CFA.
              </li>
              <li>
                Échéances intermédiaires tombant un week-end reportées au lundi
                (1ʳᵉ et dernière échéance inchangées).
              </li>
              <li>
                Épargne obligatoire : colonne séparée ; l'échéance institution =
                capital + intérêts (hors épargne).
              </li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
