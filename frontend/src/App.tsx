import { BrowserRouter, Routes, Route, Navigate, useParams } from "react-router-dom";
import { AuthProvider, useAuth } from "./hooks/useAuth";
import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";
import AppShell from "./components/AppShell";
import DashboardPage from "./pages/DashboardPage";
import IngestionPage from "./pages/IngestionPage";
import ReviewQueuePage from "./pages/ReviewQueuePage";
import AuditPage from "./pages/AuditPage";
import SourcesPage from "./pages/SourcesPage";

// 1. Updated PrivateRoute to inspect localStorage tokens as a backup during state transitions
function PrivateRoute({ children }: { children: React.ReactNode }) {
  const { user, isLoading } = useAuth();

  // If context is loading, show spinner
  if (isLoading) {
    return (
      <div style={{ display: "flex", height: "100vh", alignItems: "center", justifyContent: "center", background: "#0f1117" }}>
        <div className="spinner" />
      </div>
    );
  }

  // Check if a token exists in localStorage as a fallback to prevent the state race condition
  const hasToken = !!localStorage.getItem("access_token"); // <-- Replace with your actual tokenStore key (e.g., 'access_token' or 'token')

  if (!user && !hasToken) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}

// 2. Updated RootRedirect to look at localStorage fallback if context hasn't filled yet
function RootRedirect() {
  const { activeTenant } = useAuth();
  const savedSlug = localStorage.getItem("active_tenant");
  const slug = activeTenant?.tenant?.slug || savedSlug;

  if (slug) {
    return <Navigate to={`/tenant/${slug}/dashboard`} replace />;
  }
  return <Navigate to="/login" replace />;
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          {/* Prevent logged-in users from visiting /login manually */}
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />

          <Route
            path="/*"
            element={
              <PrivateRoute>
                <AppShell>
                  <Routes>
                    <Route path="/" element={<RootRedirect />} />

                    <Route path="/tenant/:slug/dashboard" element={<DashboardPage />} />
                    <Route path="/tenant/:slug/ingest" element={<IngestionPage />} />
                    <Route path="/tenant/:slug/queue" element={<ReviewQueuePage />} />
                    <Route path="/tenant/:slug/audit" element={<AuditPage />} />
                    <Route path="/tenant/:slug/sources" element={<SourcesPage />} />

                    <Route path="/dashboard" element={<RootRedirect />} />
                    {/* Fallback for completely unmatched paths */}
                    <Route path="*" element={<RootRedirect />} />
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