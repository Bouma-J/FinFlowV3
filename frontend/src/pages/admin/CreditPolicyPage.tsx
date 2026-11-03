import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ClipboardCheck, Save, ShieldCheck, SlidersHorizontal } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";

import { api } from "@/api/client";
import type { CreditInstructionPolicy, Paginated, Tenant } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { ErrorState, PageHeader, Spinner } from "@/components/ui";

const EMPTY: CreditInstructionPolicy = {
  id: "",
  collateral_coverage_mode: "ALERT",
  require_field_visit: false,
  allow_unfavorable_analysis_submit: true,
  require_product_checklist: false,
  match_product_client_type: false,
  kyc_gate: "ON_SUBMIT",
  product_bounds_gate: "ON_SUBMIT",
  amount_approved_mode: "ALLOW",
  show_readiness_checklist: true,
  enable_cancel_status: false,
  allow_collateral_during_approval: false,
  require_surety_signed_contracts: true,
  require_formalization_before_disbursement: false,
};

/** Preset banque stricte — B2 maturité. */
const STRICT_BANK: Omit<
  CreditInstructionPolicy,
  "id" | "created_at" | "updated_at"
> = {
  collateral_coverage_mode: "BLOCK_SUBMIT",
  require_field_visit: true,
  allow_unfavorable_analysis_submit: false,
  require_product_checklist: true,
  match_product_client_type: true,
  kyc_gate: "ON_CREATE",
  product_bounds_gate: "ON_SAVE",
  amount_approved_mode: "FORBID",
  show_readiness_checklist: true,
  enable_cancel_status: false,
  allow_collateral_during_approval: false,
  require_surety_signed_contracts: true,
  require_formalization_before_disbursement: true,
};

export function AdminCreditPolicyPage() {
  const { user, activeTenant } = useAuth();
  const qc = useQueryClient();
  const needsTenant = Boolean(user?.is_group_level && !activeTenant);
  const [form, setForm] = useState<CreditInstructionPolicy>(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const tenants = useQuery({
    queryKey: ["tenants"],
    queryFn: async () =>
      (await api.get<Paginated<Tenant>>("/tenants/")).data,
    enabled: !!user?.is_group_level,
  });

  const policy = useQuery({
    queryKey: ["credit-instruction-policy", activeTenant, user?.tenant],
    queryFn: async () =>
      (
        await api.get<CreditInstructionPolicy>(
          "/credit-instruction-policy/current/",
        )
      ).data,
    enabled: !needsTenant,
  });

  useEffect(() => {
    if (policy.data) setForm({ ...EMPTY, ...policy.data });
  }, [policy.data]);

  const save = useMutation({
    mutationFn: async () =>
      (
        await api.patch<CreditInstructionPolicy>(
          "/credit-instruction-policy/current/",
          {
            collateral_coverage_mode: form.collateral_coverage_mode,
            require_field_visit: form.require_field_visit,
            allow_unfavorable_analysis_submit:
              form.allow_unfavorable_analysis_submit,
            require_product_checklist: form.require_product_checklist,
            match_product_client_type: form.match_product_client_type,
            kyc_gate: form.kyc_gate,
            product_bounds_gate: form.product_bounds_gate,
            amount_approved_mode: form.amount_approved_mode,
            show_readiness_checklist: form.show_readiness_checklist,
            enable_cancel_status: form.enable_cancel_status,
            allow_collateral_during_approval:
              form.allow_collateral_during_approval,
            require_surety_signed_contracts:
              form.require_surety_signed_contracts,
            require_formalization_before_disbursement:
              form.require_formalization_before_disbursement,
          },
        )
      ).data,
    onSuccess: (data) => {
      setForm({ ...EMPTY, ...data });
      setError(null);
      setSaved(true);
      qc.invalidateQueries({ queryKey: ["credit-instruction-policy"] });
      window.setTimeout(() => setSaved(false), 2500);
    },
    onError: () =>
      setError("Enregistrement impossible. Vérifiez vos droits et la filiale."),
  });

  const scopeLabel = user?.is_group_level
    ? tenants.data?.results.find((t) => t.id === activeTenant)?.name ??
      "filiale sélectionnée"
    : user?.tenant_branding?.name ?? "votre filiale";

  if (needsTenant) {
    return (
      <div className="page-shell">
        <PageHeader
          icon={SlidersHorizontal}
          title="Politique crédit"
          subtitle="Sélectionnez une filiale"
        />
        <p className="muted">
          Choisissez une filiale dans la barre supérieure pour paramétrer sa
          politique d&apos;instruction.
        </p>
      </div>
    );
  }

  return (
    <div className="page-shell">
      <PageHeader
        icon={SlidersHorizontal}
        title="Politique d'instruction crédit"
        subtitle={`Règles de soumission et de validation — ${scopeLabel}`}
      />

      {policy.isLoading ? (
        <Spinner />
      ) : policy.isError ? (
        <ErrorState
          message="Impossible de charger la politique crédit."
          onRetry={() => policy.refetch()}
        />
      ) : !policy.data ? (
        <Spinner />
      ) : (
        <form
          className="tenant-compose-form"
          onSubmit={(e: FormEvent) => {
            e.preventDefault();
            save.mutate();
          }}
        >
          <div className="tenant-compose-head">
            <h2>
              <ClipboardCheck size={18} style={{ verticalAlign: "-3px" }} />{" "}
              Garde-fous paramétrables
            </h2>
            <p className="muted">
              Adaptez la rigueur du processus sans modifier le code. Les
              valeurs par défaut conservent le comportement historique
              (souple).
            </p>
            <div style={{ marginTop: 10 }}>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() =>
                  setForm((f) => ({
                    ...f,
                    ...STRICT_BANK,
                  }))
                }
              >
                <ShieldCheck size={14} />
                Appliquer le preset banque stricte
              </button>
            </div>
          </div>

          <section className="tenant-form-block">
            <header className="tenant-form-block-head">
              <div>
                <h3 className="tenant-form-block-title">Soumission</h3>
                <p className="tenant-form-block-desc">
                  Contrôles appliqués avant l&apos;entrée en circuit.
                </p>
              </div>
            </header>
            <div className="tenant-form-block-body form-grid two-col">
              <label className="field">
                <span>Couverture des garanties</span>
                <select
                  value={form.collateral_coverage_mode}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      collateral_coverage_mode: e.target
                        .value as CreditInstructionPolicy["collateral_coverage_mode"],
                    })
                  }
                >
                  <option value="ALERT">Alerte uniquement</option>
                  <option value="BLOCK_SUBMIT">Bloquer la soumission</option>
                  <option value="BLOCK_APPROVE">
                    Bloquer l&apos;approbation finale
                  </option>
                </select>
              </label>
              <label className="field">
                <span>Exigence KYC</span>
                <select
                  value={form.kyc_gate}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      kyc_gate: e.target
                        .value as CreditInstructionPolicy["kyc_gate"],
                    })
                  }
                >
                  <option value="ON_SUBMIT">À la soumission</option>
                  <option value="ON_CREATE">Dès la création du dossier</option>
                </select>
              </label>
              <label className="field">
                <span>Bornes produit (montant / durée)</span>
                <select
                  value={form.product_bounds_gate}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      product_bounds_gate: e.target
                        .value as CreditInstructionPolicy["product_bounds_gate"],
                    })
                  }
                >
                  <option value="ON_SUBMIT">À la soumission</option>
                  <option value="ON_SAVE">À chaque enregistrement</option>
                </select>
              </label>
              <label className="field">
                <span>Montant approuvé</span>
                <select
                  value={form.amount_approved_mode}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      amount_approved_mode: e.target
                        .value as CreditInstructionPolicy["amount_approved_mode"],
                    })
                  }
                >
                  <option value="ALLOW">Saisissable dès l&apos;instruction</option>
                  <option value="FORBID">
                    Uniquement à la décision du circuit
                  </option>
                </select>
              </label>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={form.require_field_visit}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      require_field_visit: e.target.checked,
                    })
                  }
                />
                <span>Visite terrain obligatoire avant soumission</span>
              </label>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={form.allow_unfavorable_analysis_submit}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      allow_unfavorable_analysis_submit: e.target.checked,
                    })
                  }
                />
                <span>Autoriser la soumission si analyse défavorable</span>
              </label>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={form.require_product_checklist}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      require_product_checklist: e.target.checked,
                    })
                  }
                />
                <span>Exiger les pièces obligatoires du produit</span>
              </label>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={form.match_product_client_type}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      match_product_client_type: e.target.checked,
                    })
                  }
                />
                <span>Contrôler cohérence type client / produit</span>
              </label>
            </div>
          </section>

          <section className="tenant-form-block">
            <header className="tenant-form-block-head">
              <div>
                <h3 className="tenant-form-block-title">Circuit &amp; UI</h3>
                <p className="tenant-form-block-desc">
                  Comportement pendant et après la validation.
                </p>
              </div>
            </header>
            <div className="tenant-form-block-body form-grid two-col">
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={form.show_readiness_checklist}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      show_readiness_checklist: e.target.checked,
                    })
                  }
                />
                <span>Afficher la checklist de readiness sur le dossier</span>
              </label>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={form.allow_collateral_during_approval}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      allow_collateral_during_approval: e.target.checked,
                    })
                  }
                />
                <span>
                  Autoriser garanties / cautions pendant le circuit
                </span>
              </label>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={form.enable_cancel_status}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      enable_cancel_status: e.target.checked,
                    })
                  }
                />
                <span>Autoriser l&apos;annulation formelle (CANCELLED)</span>
              </label>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={form.require_surety_signed_contracts}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      require_surety_signed_contracts: e.target.checked,
                    })
                  }
                />
                <span>
                  Exiger un contrat de cautionnement signé avant décaissement
                </span>
              </label>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={form.require_formalization_before_disbursement}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      require_formalization_before_disbursement:
                        e.target.checked,
                    })
                  }
                />
                <span>
                  Exiger la formalisation des garanties (hypothèque / gage /
                  nantissement) avant décaissement
                </span>
              </label>
            </div>
          </section>

          {error && <div className="form-error">{error}</div>}
          {saved && (
            <p className="muted small" style={{ color: "var(--brand)" }}>
              Politique enregistrée.
            </p>
          )}
          <div className="tenant-compose-actions">
            <button
              className="btn btn-primary"
              disabled={save.isPending}
              type="submit"
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
