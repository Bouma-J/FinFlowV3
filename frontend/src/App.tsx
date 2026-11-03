import { Navigate, Route, Routes } from "react-router-dom";

import {
  PERM_ADMIN_AGENCIES,
  PERM_ADMIN_ALERTS,
  PERM_ADMIN_AUDIT,
  PERM_ADMIN_CBS_REF,
  PERM_ADMIN_CIRCUITS,
  PERM_ADMIN_CONNECTORS,
  PERM_ADMIN_CONTRACTS,
  PERM_ADMIN_DELEGATIONS,
  PERM_ADMIN_POLICY,
  PERM_ADMIN_PRODUCTS,
  PERM_ADMIN_REFERENTIALS,
  PERM_ADMIN_ROLES,
  PERM_ADMIN_USERS,
  PERM_AFTER_SALES,
  PERM_CLIENTS,
  PERM_CLIENTS_CHANGE,
  PERM_COLLECTIONS,
  PERM_CREDIT_CREATE,
  PERM_CREDITS,
  PERM_CREDITS_CHANGE,
  PERM_DASHBOARD,
  PERM_DATIONS,
  PERM_DOCUMENTS,
  PERM_FORMALIZATIONS,
  PERM_GUARANTEES,
  PERM_GUARANTEES_ADD,
  PERM_GUARANTEES_CHANGE,
  PERM_LEGAL_PARTIES,
  PERM_LITIGATION,
  PERM_PRODUCTS,
  PERM_RELEASES,
  PERM_SIMULATOR,
  PERM_SURETIES,
  PERM_TASKS,
  homePath,
} from "@/auth/routePerms";
import { useAuth } from "@/auth/AuthContext";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { AdminRoute } from "@/components/AdminRoute";
import { PermissionRoute } from "@/components/PermissionRoute";
import { Layout } from "@/components/Layout";
import { AuditPage } from "@/pages/AuditPage";
import { ClientDetailPage } from "@/pages/ClientDetailPage";
import { ClientEditPage } from "@/pages/ClientEditPage";
import { ClientsPage } from "@/pages/ClientsPage";
import { CreditApplicationDetailPage } from "@/pages/CreditApplicationDetailPage";
import { CreditApplicationEditPage } from "@/pages/CreditApplicationEditPage";
import { FinancialAnalysisPage } from "@/pages/FinancialAnalysisPage";
import { CreditApplicationNewPage } from "@/pages/CreditApplicationNewPage";
import { CreditApplicationsPage } from "@/pages/CreditApplicationsPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { DocumentsPage } from "@/pages/DocumentsPage";
import { GroupConsolidationPage } from "@/pages/GroupConsolidationPage";
import { GuaranteeAddPage } from "@/pages/GuaranteeAddPage";
import { LoansPage } from "@/pages/LoansPage";
import { GuaranteeDetailPage } from "@/pages/GuaranteeDetailPage";
import { GuaranteeEditPage } from "@/pages/GuaranteeEditPage";
import { GuaranteesPage } from "@/pages/GuaranteesPage";
import {
  GuaranteeReleaseDetailPage,
  GuaranteeReleaseNewPage,
  GuaranteeReleasesPage,
} from "@/pages/GuaranteeReleasesPage";
import {
  DationDetailPage,
  DationNewPage,
  DationsPage,
} from "@/pages/DationsPage";
import {
  FormalizationDetailPage,
  FormalizationNewPage,
  FormalizationsPage,
} from "@/pages/FormalizationsPage";
import { CollectionsPage } from "@/pages/CollectionsPage";
import { AfterSalesHubPage } from "@/pages/AfterSalesHubPage";
import { CollectionCaseDetailPage } from "@/pages/CollectionCaseDetailPage";
import { LegalPartiesPage } from "@/pages/admin/LegalPartiesPage";
import { LitigationDetailPage } from "@/pages/LitigationDetailPage";
import { SuretyEngagementAddPage } from "@/pages/SuretyEngagementAddPage";
import { LoginPage } from "@/pages/LoginPage";
import { ForceChangePasswordPage } from "@/pages/ForceChangePasswordPage";
import { ProfilePage } from "@/pages/ProfilePage";
import { ProductsPage } from "@/pages/ProductsPage";
import { SimulatorPage } from "@/pages/SimulatorPage";
import { SuretiesPage } from "@/pages/SuretiesPage";
import { SuretyDetailPage } from "@/pages/SuretyDetailPage";
import { SuretyEditPage } from "@/pages/SuretyEditPage";
import { TasksPage } from "@/pages/TasksPage";
import { AdminAgenciesPage } from "@/pages/admin/AgenciesPage";
import { AdminTenantsPage } from "@/pages/admin/TenantsPage";
import { AdminBusinessReferentialsPage } from "@/pages/admin/BusinessReferentialsPage";
import { AdminConnectorsPage } from "@/pages/admin/ConnectorsPage";
import { AdminContractsPage } from "@/pages/admin/ContractsAdminPage";
import { AdminNotificationsPage } from "@/pages/admin/NotificationsPage";
import { AdminCollectionEscalationRulesPage } from "@/pages/admin/CollectionEscalationRulesPage";
import { AdminCollectionTranchesPage } from "@/pages/admin/CollectionTranchesPage";
import { AdminCreditPolicyPage } from "@/pages/admin/CreditPolicyPage";
import { AdminDelegationsPage } from "@/pages/admin/DelegationsPage";
import { AdminProductsPage } from "@/pages/admin/ProductsAdminPage";
import { AdminCbsReferentialsPage } from "@/pages/admin/CbsReferentialsPage";
import { AdminCbsSituationProbePage } from "@/pages/admin/CbsSituationProbePage";
import { AdminRolesPage } from "@/pages/admin/RolesPage";
import { AdminUsersPage } from "@/pages/admin/UsersPage";
import { AdminWorkflowPage } from "@/pages/admin/WorkflowPage";

function FallbackHome() {
  const { user } = useAuth();
  return <Navigate to={homePath(user)} replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/login/:tenantCode" element={<LoginPage />} />
      <Route
        path="/changer-mot-de-passe"
        element={
          <ProtectedRoute>
            <ForceChangePasswordPage />
          </ProtectedRoute>
        }
      />
      <Route
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route
          path="/"
          element={
            <PermissionRoute anyOf={PERM_DASHBOARD}>
              <DashboardPage />
            </PermissionRoute>
          }
        />
        <Route path="/profil" element={<ProfilePage />} />
        <Route
          path="/clients"
          element={
            <PermissionRoute anyOf={PERM_CLIENTS}>
              <ClientsPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/clients/:id"
          element={
            <PermissionRoute anyOf={PERM_CLIENTS}>
              <ClientDetailPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/clients/:id/modifier"
          element={
            <PermissionRoute anyOf={PERM_CLIENTS_CHANGE}>
              <ClientEditPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/dossiers"
          element={
            <PermissionRoute anyOf={PERM_CREDITS}>
              <CreditApplicationsPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/prets"
          element={
            <PermissionRoute anyOf={PERM_CREDITS}>
              <LoansPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/dossiers/nouveau"
          element={
            <PermissionRoute anyOf={PERM_CREDIT_CREATE}>
              <CreditApplicationNewPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/dossiers/:id"
          element={
            <PermissionRoute anyOf={PERM_CREDITS}>
              <CreditApplicationDetailPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/dossiers/:id/modifier"
          element={
            <PermissionRoute anyOf={PERM_CREDITS_CHANGE}>
              <CreditApplicationEditPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/dossiers/:id/analyse-financiere"
          element={
            <PermissionRoute anyOf={PERM_CREDITS}>
              <FinancialAnalysisPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/dossiers/:id/analyse-financiere/:analysisId"
          element={
            <PermissionRoute anyOf={PERM_CREDITS}>
              <FinancialAnalysisPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/dossiers/:id/garanties/nouvelle"
          element={
            <PermissionRoute anyOf={PERM_GUARANTEES_ADD}>
              <GuaranteeAddPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/dossiers/:appId/garanties/:id"
          element={
            <PermissionRoute anyOf={PERM_GUARANTEES}>
              <GuaranteeDetailPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/dossiers/:appId/cautions/:id"
          element={
            <PermissionRoute anyOf={PERM_SURETIES}>
              <SuretyDetailPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/dossiers/:id/cautions/nouvelle"
          element={
            <PermissionRoute anyOf={PERM_SURETIES}>
              <SuretyEngagementAddPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/taches"
          element={
            <PermissionRoute anyOf={PERM_TASKS}>
              <TasksPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/produits"
          element={
            <PermissionRoute anyOf={PERM_PRODUCTS}>
              <ProductsPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/cautions"
          element={
            <PermissionRoute anyOf={PERM_SURETIES}>
              <SuretiesPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/cautions/:id"
          element={
            <PermissionRoute anyOf={PERM_SURETIES}>
              <SuretyDetailPage manageable />
            </PermissionRoute>
          }
        />
        <Route
          path="/cautions/:id/modifier"
          element={
            <PermissionRoute anyOf={PERM_SURETIES}>
              <SuretyEditPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/garanties"
          element={
            <PermissionRoute anyOf={PERM_GUARANTEES}>
              <GuaranteesPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/garanties/:id"
          element={
            <PermissionRoute anyOf={PERM_GUARANTEES}>
              <GuaranteeDetailPage manageable />
            </PermissionRoute>
          }
        />
        <Route
          path="/garanties/:id/modifier"
          element={
            <PermissionRoute anyOf={PERM_GUARANTEES_CHANGE}>
              <GuaranteeEditPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/apres-vente"
          element={
            <PermissionRoute anyOf={PERM_AFTER_SALES}>
              <AfterSalesHubPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/mains-levees"
          element={
            <PermissionRoute anyOf={PERM_RELEASES}>
              <GuaranteeReleasesPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/mains-levees/nouvelle"
          element={
            <PermissionRoute
              anyOf={["guarantees.initiate_guaranteereleaserequest"]}
            >
              <GuaranteeReleaseNewPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/mains-levees/:id"
          element={
            <PermissionRoute anyOf={PERM_RELEASES}>
              <GuaranteeReleaseDetailPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/dations"
          element={
            <PermissionRoute anyOf={PERM_DATIONS}>
              <DationsPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/dations/nouvelle"
          element={
            <PermissionRoute anyOf={["guarantees.initiate_dationrequest"]}>
              <DationNewPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/dations/:id"
          element={
            <PermissionRoute anyOf={PERM_DATIONS}>
              <DationDetailPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/formalisations"
          element={
            <PermissionRoute anyOf={PERM_FORMALIZATIONS}>
              <FormalizationsPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/formalisations/nouvelle"
          element={
            <PermissionRoute
              anyOf={["guarantees.initiate_guaranteeformalizationrequest"]}
            >
              <FormalizationNewPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/formalisations/:id"
          element={
            <PermissionRoute anyOf={PERM_FORMALIZATIONS}>
              <FormalizationDetailPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/documents"
          element={
            <PermissionRoute anyOf={PERM_DOCUMENTS}>
              <DocumentsPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/recouvrement"
          element={
            <PermissionRoute anyOf={PERM_COLLECTIONS}>
              <CollectionsPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/recouvrement/:id"
          element={
            <PermissionRoute anyOf={PERM_COLLECTIONS}>
              <CollectionCaseDetailPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/recouvrement/:caseId/contentieux/:litId"
          element={
            <PermissionRoute anyOf={PERM_LITIGATION}>
              <LitigationDetailPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/intervenants-juridiques"
          element={<Navigate to="/admin/intervenants-juridiques" replace />}
        />
        <Route
          path="/simulateur"
          element={
            <PermissionRoute anyOf={PERM_SIMULATOR}>
              <SimulatorPage />
            </PermissionRoute>
          }
        />
        <Route path="/audit" element={<Navigate to="/admin/audit" replace />} />
        <Route
          path="/admin/filiales"
          element={
            <AdminRoute>
              <AdminTenantsPage />
            </AdminRoute>
          }
        />
        <Route
          path="/admin/consolidation"
          element={
            <AdminRoute>
              <PermissionRoute anyOf={PERM_DASHBOARD}>
                <GroupConsolidationPage />
              </PermissionRoute>
            </AdminRoute>
          }
        />
        <Route
          path="/admin/agences"
          element={
            <AdminRoute>
              <PermissionRoute anyOf={PERM_ADMIN_AGENCIES}>
                <AdminAgenciesPage />
              </PermissionRoute>
            </AdminRoute>
          }
        />
        <Route
          path="/admin/utilisateurs"
          element={
            <AdminRoute>
              <PermissionRoute anyOf={PERM_ADMIN_USERS}>
                <AdminUsersPage />
              </PermissionRoute>
            </AdminRoute>
          }
        />
        <Route
          path="/admin/roles"
          element={
            <AdminRoute>
              <PermissionRoute anyOf={PERM_ADMIN_ROLES}>
                <AdminRolesPage />
              </PermissionRoute>
            </AdminRoute>
          }
        />
        <Route
          path="/admin/produits"
          element={
            <AdminRoute>
              <PermissionRoute anyOf={PERM_ADMIN_PRODUCTS}>
                <AdminProductsPage />
              </PermissionRoute>
            </AdminRoute>
          }
        />
        <Route
          path="/admin/referentiels-cbs"
          element={
            <AdminRoute>
              <PermissionRoute anyOf={PERM_ADMIN_CBS_REF}>
                <AdminCbsReferentialsPage />
              </PermissionRoute>
            </AdminRoute>
          }
        />
        <Route
          path="/admin/referentiels-metier"
          element={
            <AdminRoute>
              <PermissionRoute anyOf={PERM_ADMIN_REFERENTIALS}>
                <AdminBusinessReferentialsPage />
              </PermissionRoute>
            </AdminRoute>
          }
        />
        <Route
          path="/admin/intervenants-juridiques"
          element={
            <PermissionRoute anyOf={PERM_LEGAL_PARTIES}>
              <LegalPartiesPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/admin/circuits"
          element={
            <AdminRoute>
              <PermissionRoute anyOf={PERM_ADMIN_CIRCUITS}>
                <AdminWorkflowPage />
              </PermissionRoute>
            </AdminRoute>
          }
        />
        <Route
          path="/admin/delegations"
          element={
            <AdminRoute>
              <PermissionRoute anyOf={PERM_ADMIN_DELEGATIONS}>
                <AdminDelegationsPage />
              </PermissionRoute>
            </AdminRoute>
          }
        />
        <Route
          path="/admin/contrats"
          element={
            <AdminRoute>
              <PermissionRoute anyOf={PERM_ADMIN_CONTRACTS}>
                <AdminContractsPage />
              </PermissionRoute>
            </AdminRoute>
          }
        />
        <Route
          path="/admin/connecteurs"
          element={
            <AdminRoute>
              <PermissionRoute anyOf={PERM_ADMIN_CONNECTORS}>
                <AdminConnectorsPage />
              </PermissionRoute>
            </AdminRoute>
          }
        />
        <Route
          path="/admin/verification-situation"
          element={
            <AdminRoute>
              <AdminCbsSituationProbePage />
            </AdminRoute>
          }
        />
        <Route
          path="/admin/alertes"
          element={
            <AdminRoute>
              <PermissionRoute anyOf={PERM_ADMIN_ALERTS}>
                <AdminNotificationsPage />
              </PermissionRoute>
            </AdminRoute>
          }
        />
        <Route
          path="/admin/politique-credit"
          element={
            <AdminRoute>
              <PermissionRoute anyOf={PERM_ADMIN_POLICY}>
                <AdminCreditPolicyPage />
              </PermissionRoute>
            </AdminRoute>
          }
        />
        <Route
          path="/admin/tranches-recouvrement"
          element={
            <AdminRoute>
              <AdminCollectionTranchesPage />
            </AdminRoute>
          }
        />
        <Route
          path="/admin/regles-escalade"
          element={
            <AdminRoute>
              <AdminCollectionEscalationRulesPage />
            </AdminRoute>
          }
        />
        <Route
          path="/admin/audit"
          element={
            <AdminRoute>
              <PermissionRoute anyOf={PERM_ADMIN_AUDIT}>
                <AuditPage />
              </PermissionRoute>
            </AdminRoute>
          }
        />
      </Route>
      <Route path="*" element={<FallbackHome />} />
    </Routes>
  );
}
