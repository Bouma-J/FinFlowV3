import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ShieldCheck } from "lucide-react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { api } from "@/api/client";
import type { CreditApplication, Surety } from "@/api/types";
import { GuaranteeForm } from "@/components/GuaranteeForm";
import { RenewGuaranteesPanel } from "@/components/RenewGuaranteesPanel";
import { SuretyForm } from "@/components/SuretyForm";
import { ErrorState, PageHeader, Spinner } from "@/components/ui";

export function GuaranteeAddPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const creatingSurety = params.get("creer") === "caution";

  const { data: app, isLoading, isError, refetch } = useQuery({
    queryKey: ["credit-application", id],
    queryFn: async () =>
      (await api.get<CreditApplication>(`/credit-applications/${id}/`)).data,
    enabled: !!id,
  });

  if (isLoading) return <Spinner />;
  if (isError || !app)
    return (
      <ErrorState
        message="Impossible de charger le dossier de crédit."
        onRetry={() => refetch()}
      />
    );

  const loanAmount = Number(
    app.amount_approved || app.amount_proposed || app.amount_requested || 0,
  );

  return (
    <div className="page-shell">
      <PageHeader
        icon={ShieldCheck}
        title={creatingSurety ? "Créer une caution" : "Ajouter une garantie"}
        subtitle={`Dossier ${app.reference} — ${app.client_display}`}
        actions={
          <Link className="btn btn-ghost" to={`/dossiers/${id}`}>
            <ArrowLeft />
            Retour au dossier
          </Link>
        }
      />
      {creatingSurety ? (
        <SuretyForm
          onSuccess={(surety: Surety) => setParams({ surety: surety.id }, { replace: true })}
          onCancel={() => setParams({}, { replace: true })}
        />
      ) : (
        <>
          <RenewGuaranteesPanel
            applicationId={app.id}
            currency={app.currency || "XOF"}
          />
          <GuaranteeForm
            mode="create"
            clientId={app.client}
            applicationId={app.id}
            loanAmount={loanAmount}
            backTo={`/dossiers/${id}`}
            initialSuretyId={params.get("surety") || ""}
            onCreateSurety={() => setParams({ creer: "caution" })}
            onSaved={() => navigate(`/dossiers/${id}`)}
          />
        </>
      )}
    </div>
  );
}
