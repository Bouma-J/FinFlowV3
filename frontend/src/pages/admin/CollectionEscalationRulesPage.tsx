import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Save, Timer, Trash2 } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";

import { api } from "@/api/client";
import type { CollectionEscalationRule, Paginated } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { isFinflowAdmin } from "@/auth/routePerms";
import { EmptyState, ErrorState, PageHeader, Spinner } from "@/components/ui";
import { apiErrorMessage } from "@/utils/apiError";

const STAGES = [
  { value: "AMICABLE", label: "Amiable" },
  { value: "PRECONTENTIOUS", label: "Précontentieux" },
  { value: "LITIGATION", label: "Contentieux" },
] as const;

type DraftRule = {
  id?: string;
  key: string;
  min_days_overdue: string;
  target_stage: (typeof STAGES)[number]["value"];
  label: string;
  is_active: boolean;
};

function toDraft(rows: CollectionEscalationRule[]): DraftRule[] {
  return rows.map((row) => ({
    id: row.id,
    key: row.id,
    min_days_overdue: String(row.min_days_overdue),
    target_stage: row.target_stage,
    label: row.label,
    is_active: row.is_active,
  }));
}

export function AdminCollectionEscalationRulesPage() {
  const { user, activeTenant } = useAuth();
  const qc = useQueryClient();
  const needsTenant = Boolean(user?.is_group_level && !activeTenant);
  const canManage = isFinflowAdmin(user);
  const [rows, setRows] = useState<DraftRule[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const query = useQuery({
    queryKey: ["collection-escalation-rules", activeTenant, user?.tenant],
    queryFn: async () =>
      (
        await api.get<Paginated<CollectionEscalationRule>>(
          "/collection-escalation-rules/",
          { params: { page_size: 50, ordering: "min_days_overdue" } },
        )
      ).data,
    enabled: canManage && !needsTenant,
  });

  useEffect(() => {
    if (query.data?.results) setRows(toDraft(query.data.results));
  }, [query.data]);

  const save = useMutation({
    mutationFn: async () => {
      const existing = query.data?.results ?? [];
      const keepIds = new Set(rows.map((row) => row.id).filter(Boolean));
      for (const old of existing) {
        if (!keepIds.has(old.id)) {
          await api.delete(`/collection-escalation-rules/${old.id}/`);
        }
      }
      const savedRows: CollectionEscalationRule[] = [];
      for (const row of rows) {
        const payload = {
          min_days_overdue: Number(row.min_days_overdue),
          target_stage: row.target_stage,
          label: row.label.trim(),
          is_active: row.is_active,
        };
        const res = row.id
          ? await api.patch<CollectionEscalationRule>(
              `/collection-escalation-rules/${row.id}/`,
              payload,
            )
          : await api.post<CollectionEscalationRule>(
              "/collection-escalation-rules/",
              payload,
            );
        savedRows.push(res.data);
      }
      return savedRows;
    },
    onSuccess: (data) => {
      setSaved(true);
      setError(null);
      setRows(toDraft(data));
      qc.invalidateQueries({ queryKey: ["collection-escalation-rules"] });
      qc.invalidateQueries({ queryKey: ["collection-cases"] });
    },
    onError: (err: unknown) => {
      setSaved(false);
      setError(
        apiErrorMessage(
          err,
          "Enregistrement impossible. Vérifiez les seuils et vos droits.",
        ),
      );
    },
  });

  function updateRow(key: string, patch: Partial<DraftRule>) {
    setSaved(false);
    setRows((current) =>
      current.map((row) => (row.key === key ? { ...row, ...patch } : row)),
    );
  }

  function addRow() {
    setSaved(false);
    setRows((current) => {
      const last = current[current.length - 1];
      const nextMin = last ? Number(last.min_days_overdue) + 30 : 31;
      return [
        ...current,
        {
          key: `new-${crypto.randomUUID()}`,
          min_days_overdue: String(Number.isFinite(nextMin) ? nextMin : 31),
          target_stage: "PRECONTENTIOUS",
          label: "",
          is_active: true,
        },
      ];
    });
  }

  function removeRow(key: string) {
    setSaved(false);
    setRows((current) => current.filter((row) => row.key !== key));
  }

  if (!canManage) {
    return (
      <EmptyState message="Paramétrage réservé aux administrateurs filiale et groupe." />
    );
  }
  if (needsTenant) {
    return (
      <div className="page-shell">
        <PageHeader
          icon={Timer}
          title="Règles d'escalade"
          subtitle="Sélectionnez une filiale"
        />
        <p className="muted">
          Choisissez une filiale dans la barre supérieure pour paramétrer les
          délais de stade (précontentieux / contentieux).
        </p>
      </div>
    );
  }

  return (
    <div className="page-shell">
      <PageHeader
        icon={Timer}
        title="Règles d'escalade"
        subtitle="Délais de passage en précontentieux et contentieux"
      />

      {query.isLoading ? (
        <Spinner />
      ) : query.isError ? (
        <ErrorState
          message="Impossible de charger les règles."
          onRetry={() => query.refetch()}
        />
      ) : (
        <form
          className="tenant-compose-form"
          onSubmit={(e: FormEvent) => {
            e.preventDefault();
            save.mutate();
          }}
        >
          <p className="muted" style={{ marginBottom: 16 }}>
            Dès que le retard atteint un seuil, le dossier passe au stade cible
            (jamais en descente). Les tranches gèrent l&apos;affectation ; ces
            règles pilotent le stade amiable / précontentieux / contentieux.
          </p>

          {error && (
            <div className="notice-error" role="alert" style={{ marginBottom: 16 }}>
              {error}
            </div>
          )}
          {saved && !error && (
            <div className="form-success" style={{ marginBottom: 16 }}>
              Règles enregistrées. Le prochain recalcul des retards les
              appliquera.
            </div>
          )}

          <div className="card" style={{ padding: 0, overflow: "auto" }}>
            <table className="table">
              <thead>
                <tr>
                  <th>Seuil (j)</th>
                  <th>Stade cible</th>
                  <th>Libellé</th>
                  <th>Active</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.key}>
                    <td>
                      <input
                        type="number"
                        min={1}
                        value={row.min_days_overdue}
                        onChange={(e) =>
                          updateRow(row.key, {
                            min_days_overdue: e.target.value,
                          })
                        }
                        required
                      />
                    </td>
                    <td>
                      <select
                        value={row.target_stage}
                        onChange={(e) =>
                          updateRow(row.key, {
                            target_stage: e.target
                              .value as DraftRule["target_stage"],
                          })
                        }
                      >
                        {STAGES.map((opt) => (
                          <option key={opt.value} value={opt.value}>
                            {opt.label}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td>
                      <input
                        value={row.label}
                        onChange={(e) =>
                          updateRow(row.key, { label: e.target.value })
                        }
                        placeholder="Précontentieux dès 31 j"
                      />
                    </td>
                    <td>
                      <input
                        type="checkbox"
                        checked={row.is_active}
                        onChange={(e) =>
                          updateRow(row.key, { is_active: e.target.checked })
                        }
                      />
                    </td>
                    <td>
                      <button
                        type="button"
                        className="btn btn-ghost btn-sm"
                        onClick={() => removeRow(row.key)}
                        aria-label="Supprimer la règle"
                      >
                        <Trash2 size={14} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="credit-form-actions" style={{ marginTop: 16 }}>
            <button type="button" className="btn btn-ghost" onClick={addRow}>
              <Plus size={16} /> Ajouter une règle
            </button>
            <button
              type="submit"
              className="btn btn-primary"
              disabled={save.isPending}
            >
              <Save size={16} />
              {save.isPending ? "Enregistrement…" : "Enregistrer"}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
