import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, LineChart } from "lucide-react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { api } from "@/api/client";
import type { CreditApplication, FinancialAnalysis } from "@/api/types";
import { FinancialAnalysisForm } from "@/components/FinancialAnalysisForm";
import { FinancialAnalysisReadout } from "@/components/FinancialAnalysisReadout";
import { ErrorState, PageHeader, Spinner } from "@/components/ui";

const ANALYSIS_LOCKED = ["DISBURSED", "CLOSED", "CANCELLED", "REJECTED"];

export function FinancialAnalysisPage() {
  const { id, analysisId } = useParams<{ id: string; analysisId?: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const readOnly = searchParams.get("lecture") === "1";

  const {
    data: app,
    isLoading: loadingApp,
    isError: errorApp,
    refetch: refetchApp,
  } = useQuery({
    queryKey: ["credit-application", id],
    queryFn: async () =>
      (await api.get<CreditApplication>(`/credit-applications/${id}/`)).data,
    enabled: !!id,
  });

  const {
    data: existing,
    isLoading: loadingAnalysis,
    isError: errorAnalysis,
    refetch: refetchAnalysis,
  } = useQuery({
    queryKey: ["financial-analysis-item", analysisId],
    queryFn: async () =>
      (
        await api.get<FinancialAnalysis>(
          `/financial-analyses/${analysisId}/`,
        )
      ).data,
    enabled: !!analysisId,
  });

  if (loadingApp || (analysisId && loadingAnalysis)) {
    return <Spinner />;
  }

  if (errorApp || !app) {
    return (
      <div className="page-shell">
        <PageHeader
          icon={LineChart}
          title="Analyse financière"
          subtitle="Chargement impossible"
          actions={
            <Link
              className="btn btn-ghost"
              to={id ? `/dossiers/${id}` : "/dossiers"}
            >
              <ArrowLeft />
              Retour
            </Link>
          }
        />
        <ErrorState
          message="Impossible de charger le dossier."
          onRetry={() => refetchApp()}
        />
      </div>
    );
  }

  if (analysisId && (errorAnalysis || !existing)) {
    return (
      <div className="page-shell">
        <PageHeader
          icon={LineChart}
          title="Analyse financière"
          subtitle="Chargement impossible"
          actions={
            <Link className="btn btn-ghost" to={`/dossiers/${id}`}>
              <ArrowLeft />
              Retour au dossier
            </Link>
          }
        />
        <ErrorState
          message="Impossible de charger l'analyse financière."
          onRetry={() => refetchAnalysis()}
        />
      </div>
    );
  }

  const backTo = `/dossiers/${id}`;
  const isEdit = !!analysisId;
  const analysisLocked = ANALYSIS_LOCKED.includes(app.status);
  const canContributeWindow = app.can_add_financial_analysis === true;
  const canEditExisting = existing?.can_edit === true && !readOnly;

  if (isEdit && existing && !canEditExisting) {
    return (
      <div className="page-shell">
        <PageHeader
          icon={LineChart}
          title="Consulter l'analyse financière"
          subtitle={`${app.client_display} · dossier ${app.reference || app.id.slice(0, 8)}`}
          actions={
            <Link className="btn btn-ghost" to={backTo}>
              <ArrowLeft />
              Retour au dossier
            </Link>
          }
        />
        <p className="muted small">Lecture seule. La modification et la suppression restent réservées à l&apos;auteur tant que le dossier n&apos;est pas soumis, ou après un retour.</p>
        <FinancialAnalysisReadout analysis={existing} currency={app.currency} part="topics" />
        <FinancialAnalysisReadout analysis={existing} currency={app.currency} part="indicators" />
      </div>
    );
  }

  if (!isEdit && !canContributeWindow) {
    return (
      <div>
        <PageHeader
          icon={LineChart}
          title="Nouvelle analyse financière"
          subtitle="Accès refusé"
          actions={
            <Link className="btn btn-ghost" to={backTo}>
              <ArrowLeft />
              Retour au dossier
            </Link>
          }
        />
        <p className="form-error">
          {analysisLocked
            ? "Ce dossier est mis en place ou clôturé : aucune nouvelle analyse financière ne peut être ajoutée."
            : "Vous n'êtes pas autorisé à ajouter une analyse sur ce dossier."}
        </p>
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        icon={LineChart}
        title={
          isEdit
            ? existing?.is_draft
              ? "Continuer l'analyse financière"
              : "Modifier l'analyse financière"
            : "Nouvelle analyse financière"
        }
        subtitle={`${app.client_display} · dossier ${app.reference || app.id.slice(0, 8)}`}
        actions={
          <Link className="btn btn-ghost" to={backTo}>
            <ArrowLeft />
            Retour au dossier
          </Link>
        }
      />

      <FinancialAnalysisForm
        mode={isEdit ? "edit" : "create"}
        analysisId={analysisId}
        initial={isEdit ? existing : undefined}
        application={app}
        backTo={backTo}
        onSaved={() => navigate(backTo)}
      />
    </div>
  );
}
