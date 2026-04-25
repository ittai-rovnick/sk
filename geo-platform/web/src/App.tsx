import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth/AuthContext";
import { AppLayout } from "./components/layout/AppLayout";
import { LoginPage } from "./pages/LoginPage";
import { DatabasesPage } from "./pages/DatabasesPage";
import { LayersPage } from "./pages/LayersPage";
import { LayerDetailPage } from "./pages/LayerDetailPage";
import { PermissionsPage } from "./pages/PermissionsPage";
import { UsersPage } from "./pages/UsersPage";
import { GroupsPage } from "./pages/GroupsPage";
import { AuditLogPage } from "./pages/AuditLogPage";
import { SyncConflictsPage } from "./pages/SyncConflictsPage";
import { MapPage } from "./pages/MapPage";
import { MapsPage } from "./pages/MapsPage";
import type { ReactNode } from "react";

function RequireAuth({ children }: { children: ReactNode }) {
  const { token } = useAuth();
  if (!token) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route
            element={
              <RequireAuth>
                <AppLayout />
              </RequireAuth>
            }
          >
            <Route index element={<Navigate to="/databases" replace />} />
            <Route path="/databases" element={<DatabasesPage />} />
            <Route path="/layers" element={<LayersPage />} />
            <Route path="/layers/:id" element={<LayerDetailPage />} />
            <Route path="/permissions" element={<PermissionsPage />} />
            <Route path="/users" element={<UsersPage />} />
            <Route path="/groups" element={<GroupsPage />} />
            <Route path="/audit" element={<AuditLogPage />} />
            <Route path="/conflicts" element={<SyncConflictsPage />} />
            <Route path="/map" element={<MapPage />} />
            <Route path="/maps-admin" element={<MapsPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
