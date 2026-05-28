import { useEffect, useState } from "react";
import { tenantApi, type DashboardSummary, type IngestionBatch } from "../lib/api";
import { useAuth } from "../hooks/useAuth";

function MetricCard({ label, value, sub, variant }: {
  label: string; value: string | number; sub?: string; variant?: "danger" | "warning" | "success";
}) {
  return (
    <div className={`metric-card ${variant ?? ""}`}>
      <div className="metric-label">{label}</div>
      <div className={`metric-value ${variant ?? ""}`}>{value}</div>
      {sub && <div className="metric-sub">{sub}</div>}
    </div>
  );
}

function ScopeBar({ label, value, total, color }: { label: string; value: number; total: number; color: string }) {
  const pct = total > 0 ? Math.round((value / total) * 100) : 0;
  return (
    <div className="scope-card">
      <div className="scope-header">
        <span className="scope-label">{label}</span>
        <span className="scope-value">{value.toLocaleString()} t CO₂e</span>
      </div>
      <div className="scope-bar-track">
        <div className="scope-bar-fill" style={{ width: `${pct}%`, background: color }} />
      </div>
      <div className="scope-pct">{pct}% of total</div>
    </div>
  );
}

const STATUS_COLORS: Record<string, string> = {
  COMPLETED: "#22c55e",
  PROCESSING: "#f59e0b",
  FAILED: "#ef4444",
  PENDING: "#94a3b8",
  SUPERSEDED: "#64748b",
};

export default function DashboardPage() {
  const { activeTenant } = useAuth();
  const [data, setData] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!activeTenant) return;
    setLoading(true);
    tenantApi.dashboard(activeTenant.tenant.slug)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [activeTenant?.tenant.slug]);

  if (!activeTenant) return <div className="page-empty">No tenant selected.</div>;
  if (loading) return <div className="page-loading"><div className="spinner" /></div>;
  if (error) return <div className="page-error">Failed to load dashboard: {error}</div>;
  if (!data) return null;

  const totalCo2e = data.scope1_co2e_t + data.scope2_co2e_t + data.scope3_co2e_t;

  return (
    <div className="page">
      <div className="page-header">
        <h1 className="page-title">Dashboard</h1>
        <span className="page-subtitle">{activeTenant.tenant.name} · FY{activeTenant.tenant.reporting_year ?? new Date().getFullYear()}</span>
      </div>

      <div className="metrics-row">
        <MetricCard label="Total Records" value={data.total_records.toLocaleString()} sub="ingested this period" />
        <MetricCard label="Pending Review" value={data.pending_review} sub="in analyst queue" variant="warning" />
        <MetricCard label="Validation Errors" value={data.validation_errors} sub="blocking approval" variant="danger" />
        <MetricCard label="Approved" value={data.approved.toLocaleString()} sub={`${data.approval_rate_pct}% of total`} variant="success" />
      </div>

      <div className="section-title" style={{ marginTop: 28, marginBottom: 12 }}>Emissions by Scope (approved data)</div>
      <div className="scope-row">
        <ScopeBar label="Scope 1 — Direct" value={data.scope1_co2e_t} total={totalCo2e} color="#22c55e" />
        <ScopeBar label="Scope 2 — Grid Electricity" value={data.scope2_co2e_t} total={totalCo2e} color="#3b82f6" />
        <ScopeBar label="Scope 3 — Business Travel" value={data.scope3_co2e_t} total={totalCo2e} color="#f59e0b" />
      </div>

      <div className="section-title" style={{ marginTop: 28, marginBottom: 12 }}>Recent Batches</div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>File</th>
              <th>Source</th>
              <th>Uploaded</th>
              <th>Rows</th>
              <th>Valid</th>
              <th>Failed</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {data.recent_batches.length === 0 && (
              <tr><td colSpan={7} style={{ textAlign: "center", color: "#64748b" }}>No batches yet</td></tr>
            )}
            {data.recent_batches.map((b) => (
              <tr key={b.id}>
                <td className="mono">{b.source_filename || "—"}</td>
                <td><span className="chip">{b.source_type}</span></td>
                <td>{new Date(b.uploaded_at).toLocaleDateString()}</td>
                <td>{b.row_count_raw ?? "—"}</td>
                <td style={{ color: "#22c55e" }}>{b.row_count_valid ?? "—"}</td>
                <td style={{ color: b.row_count_failed ? "#ef4444" : "inherit" }}>{b.row_count_failed ?? "—"}</td>
                <td>
                  <span className="status-dot" style={{ background: STATUS_COLORS[b.status] ?? "#94a3b8" }} />
                  {b.status_display}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
