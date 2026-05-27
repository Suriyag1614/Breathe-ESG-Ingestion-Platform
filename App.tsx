import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./hooks/useAuth";
import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";
import AppShell from "./components/AppShell";
import DashboardPage from "./pages/DashboardPage";
import IngestionPage from "./pages/IngestionPage";
import ReviewQueuePage from "./pages/ReviewQueuePage";
import AuditPage from "./pages/AuditPage";
import SourcesPage from "./pages/SourcesPage";

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const { user, isLoading } = useAuth();
  if (isLoading) {
    return (
      <div style={{ display: "flex", height: "100vh", alignItems: "center", justifyContent: "center", background: "#0f1117" }}>
        <div className="spinner" />
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route
            path="/*"
            element={
              <PrivateRoute>
                <AppShell>
                  <Routes>
                    <Route path="/" element={<Navigate to="/dashboard" replace />} />
                    <Route path="/dashboard" element={<DashboardPage />} />
                    <Route path="/ingest" element={<IngestionPage />} />
                    <Route path="/queue" element={<ReviewQueuePage />} />
                    <Route path="/audit" element={<AuditPage />} />
                    <Route path="/sources" element={<SourcesPage />} />
                  </Routes>
                </AppShell>
              </PrivateRoute>
            }
          />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
