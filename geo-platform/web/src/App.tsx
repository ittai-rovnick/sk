import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "./auth/AuthProvider";
import { AppLayout } from "./components/layout/AppLayout";
import { DatabasesPage } from "./pages/DatabasesPage";
import { LayersPage } from "./pages/LayersPage";
import { LayerDetailPage } from "./pages/LayerDetailPage";
import { PermissionsPage } from "./pages/PermissionsPage";
import { UsersPage } from "./pages/UsersPage";
import { GroupsPage } from "./pages/GroupsPage";
import { AuditLogPage } from "./pages/AuditLogPage";
import { SyncConflictsPage } from "./pages/SyncConflictsPage";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 30_000 },
  },
});

export default function App() {
  return (
    <AuthProvider>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <Routes>
            <Route element={<AppLayout />}>
              <Route index element={<Navigate to="/databases" replace />} />
              <Route path="/databases" element={<DatabasesPage />} />
              <Route path="/layers" element={<LayersPage />} />
              <Route path="/layers/:id" element={<LayerDetailPage />} />
              <Route path="/permissions" element={<PermissionsPage />} />
              <Route path="/users" element={<UsersPage />} />
              <Route path="/groups" element={<GroupsPage />} />
              <Route path="/audit" element={<AuditLogPage />} />
              <Route path="/conflicts" element={<SyncConflictsPage />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </QueryClientProvider>
    </AuthProvider>
  );
}
