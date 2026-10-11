import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { AdminRoute } from "@/components/AdminRoute";
import { UploadQueueProvider } from "@/context/UploadQueueContext";
import { PipelineProgressProvider } from "@/context/PipelineProgressContext";
import { LoginPage } from "@/pages/LoginPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { UploadPage } from "@/pages/UploadPage";
import { HistoryPage } from "@/pages/HistoryPage";
import { EntriesPage } from "@/pages/EntriesPage";
import { InvoiceDetailPage } from "@/pages/InvoiceDetailPage";
import { AdminPage } from "@/pages/AdminPage";
import { ProfilePage } from "@/pages/ProfilePage";

export function App() {
  return (
    // La file d'import vit au-dessus des routes : naviguer vers un autre
    // onglet puis revenir sur "Import" ne doit pas faire perdre le suivi
    // des factures en cours de traitement (voir UploadQueueContext).
    <PipelineProgressProvider>
      <UploadQueueProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route element={<ProtectedRoute />}>
            <Route element={<Layout />}>
              <Route path="/" element={<DashboardPage />} />
              <Route path="/upload" element={<UploadPage />} />
              <Route path="/historique" element={<HistoryPage />} />
              <Route path="/ecritures" element={<EntriesPage />} />
              <Route path="/factures/:id" element={<InvoiceDetailPage />} />
              <Route path="/profil" element={<ProfilePage />} />
              <Route element={<AdminRoute />}>
                <Route path="/admin" element={<AdminPage />} />
              </Route>
            </Route>
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </UploadQueueProvider>
    </PipelineProgressProvider>
  );
}
