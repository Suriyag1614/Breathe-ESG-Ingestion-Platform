import { useEffect, useState } from "react";
import { tenantApi, type RawEmissionRow, type ValidationIssue } from "../lib/api";
import { useAuth } from "../hooks/useAuth";

const SEV_STYLE: Record<string, string> = {
  ERROR: "sev-error",
  WARNING: "sev-warning",
  INFO: "sev-info",
};

function IssueItem({ issue }: { issue: ValidationIssue }) {
  return (
    <div className={`issue-item ${issue.severity.toLowerCase()}`}>
      <div className="issue-header">
        <span className={`sev-tag ${SEV_STYLE[issue.severity]}`}>{issue.severity}</span>
        <span className="issue-code">{issue.rule_code}</span>
      </div>
      <div className="issue-msg">{issue.message}</div>
      {issue.field_name && (
        <div className="issue-field">Field: <code>{issue.field_name}</code> = <code>{issue.field_value}</code></div>
      )}
    </div>
  );
}

function RowDetailPanel({ row, slug, onAction, onClose }: {
  row: RawEmissionRow;
  slug: string;
  onAction: () => void;
  onClose: () => void;
}) {
  const [comment, setComment] = useState("");
  const [loading, setLoading] = useState(false);
  const [detail, setDetail] = useState<RawEmissionRow | null>(null);

  useEffect(() => {
    tenantApi.getRow(slug, row.id).then(setDetail);
  }, [row.id, slug]);

  const canApprove = !row.has_errors;

  const doApprove = async () => {
    setLoading(true);
    try { await tenantApi.approveRow(slug, row.id, comment); onAction(); onClose(); }
    catch (e: any) { alert(e.body?.detail ?? "Failed to approve"); }
    finally { setLoading(false); }
  };

  const doReject = async () => {
    setLoading(true);
    try { await tenantApi.rejectRow(slug, row.id, comment); onAction(); onClose(); }
    catch { alert("Failed to reject"); }
    finally { setLoading(false); }
  };

  return (
    <div className="detail-panel">
      <div className="detail-panel-header">
        <span className="detail-title">Row #{row.row_index} · {row.source_type}</span>
        <div className="detail-actions">
          <button className="btn btn-primary" onClick={doApprove} disabled={!canApprove || loading}>
            ✓ Approve
          </button>
          <button className="btn btn-danger" onClick={doReject} disabled={loading}>
            ✕ Reject
          </button>
          <button className="btn" onClick={onClose}>✕</button>
        </div>
      </div>
      <div className="detail-body">
        <div className="detail-col">
          <div className="detail-section-title">Raw Source Data</div>
          {detail ? (
            Object.entries(detail.raw_data ?? {}).map(([k, v]) => (
              <div key={k} className="field-row">
                <span className="field-key">{k}</span>
                <span className="field-val">{String(v ?? "—")}</span>
              </div>
            ))
          ) : <div className="spinner" />}
        </div>
        <div className="detail-col">
          <div className="detail-section-title">
            Validation Issues ({detail?.validation_issues?.length ?? row.issue_count})
          </div>
          {(detail?.validation_issues ?? []).map((iss) => (
            <IssueItem key={iss.id} issue={iss} />
          ))}
          {(detail?.validation_issues?.length ?? 0) === 0 && (
            <div style={{ color: "#22c55e", fontSize: 13 }}>✓ No issues — row is clean</div>
          )}
          <div style={{ marginTop: 12 }}>
            <label className="form-label">Analyst note</label>
            <textarea
              className="textarea"
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="Explain your decision…"
              rows={3}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

export default function ReviewQueuePage() {
  const { activeTenant } = useAuth();
  const slug = activeTenant?.tenant.slug ?? "";
  const [rows, setRows] = useState<RawEmissionRow[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [selectedRow, setSelectedRow] = useState<RawEmissionRow | null>(null);
  const [filters, setFilters] = useState({ status: "", source_type: "", scope: "" });

  const load = () => {
    if (!slug) return;
    setLoading(true);
    const params: Record<string, string> = {};
    if (filters.status) params.status = filters.status;
    if (filters.source_type) params.source_type = filters.source_type;
    if (filters.scope) params.scope = filters.scope;
    tenantApi.listRows(slug, params)
      .then((r) => { setRows(r.results); setTotal(r.count); })
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [slug, filters]);

  const setFilter = (key: string, val: string) =>
    setFilters((f) => ({ ...f, [key]: val }));

  const statusColor: Record<string, string> = {
    APPROVED: "#22c55e",
    REJECTED: "#ef4444",
    NEEDS_REVIEW: "#3b82f6",
    PENDING: "#f59e0b",
  };

  return (
    <div className="page">
      <div className="page-header">
        <h1 className="page-title">Review Queue</h1>
        <span className="page-subtitle">{total} rows</span>
      </div>

      <div className="filter-bar">
        <select value={filters.status} onChange={(e) => setFilter("status", e.target.value)}>
          <option value="">All statuses</option>
          <option value="NEEDS_REVIEW">Needs Review</option>
          <option value="PENDING">Pending</option>
          <option value="APPROVED">Approved</option>
          <option value="REJECTED">Rejected</option>
        </select>
        <select value={filters.source_type} onChange={(e) => setFilter("source_type", e.target.value)}>
          <option value="">All sources</option>
          <option value="SAP_FLAT_FILE">SAP Fuel</option>
          <option value="UTILITY_CSV">Utility</option>
          <option value="TRAVEL_CONCUR">Travel</option>
        </select>
        <select value={filters.scope} onChange={(e) => setFilter("scope", e.target.value)}>
          <option value="">All scopes</option>
          <option value="1">Scope 1</option>
          <option value="2">Scope 2</option>
          <option value="3">Scope 3</option>
        </select>
      </div>

      {loading ? (
        <div className="page-loading"><div className="spinner" /></div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>Source</th>
                <th>Scope</th>
                <th>Batch</th>
                <th>Ingested</th>
                <th>Issues</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && (
                <tr><td colSpan={8} style={{ textAlign: "center", color: "#64748b", padding: 24 }}>No rows match your filters</td></tr>
              )}
              {rows.map((row) => (
                <tr
                  key={row.id}
                  className={selectedRow?.id === row.id ? "selected" : ""}
                  onClick={() => setSelectedRow(row)}
                  style={{ cursor: "pointer" }}
                >
                  <td className="mono">{row.row_index}</td>
                  <td><span className="chip">{row.source_type.replace("_FLAT_FILE", "").replace("_CSV", "").replace("_CONCUR", "")}</span></td>
                  <td>{row.scope}</td>
                  <td className="mono" style={{ fontSize: 11, color: "#64748b" }}>{row.batch_filename?.slice(0, 20) || row.batch.slice(0, 8)}</td>
                  <td>{new Date(row.ingested_at).toLocaleDateString()}</td>
                  <td>
                    {row.has_errors ? (
                      <span style={{ color: "#ef4444" }}>● {row.issue_count} error{row.issue_count !== 1 ? "s" : ""}</span>
                    ) : row.issue_count > 0 ? (
                      <span style={{ color: "#f59e0b" }}>◐ {row.issue_count} warn</span>
                    ) : (
                      <span style={{ color: "#22c55e" }}>✓ Clean</span>
                    )}
                  </td>
                  <td>
                    <span className="status-badge" style={{ background: statusColor[row.status] + "22", color: statusColor[row.status] }}>
                      {row.status_display}
                    </span>
                  </td>
                  <td onClick={(e) => e.stopPropagation()}>
                    <button
                      className="btn-sm"
                      onClick={() => tenantApi.approveRow(slug, row.id).then(load)}
                      disabled={row.has_errors || row.status === "APPROVED"}
                      title="Approve"
                    >✓</button>
                    <button
                      className="btn-sm btn-sm-danger"
                      onClick={() => tenantApi.rejectRow(slug, row.id).then(load)}
                      disabled={row.status === "REJECTED"}
                      title="Reject"
                    >✕</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {selectedRow && (
        <RowDetailPanel
          row={selectedRow}
          slug={slug}
          onAction={load}
          onClose={() => setSelectedRow(null)}
        />
      )}
    </div>
  );
}
