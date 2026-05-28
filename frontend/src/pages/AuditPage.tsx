import { useEffect, useState } from "react";
import { tenantApi, type AuditEvent } from "../lib/api";
import { useAuth } from "../hooks/useAuth";

const EVENT_STYLES: Record<string, { color: string; bg: string; symbol: string }> = {
  ROW_APPROVED:    { color: "#22c55e", bg: "#022c2211", symbol: "✓" },
  ROW_REJECTED:    { color: "#ef4444", bg: "#2c021111", symbol: "✕" },
  ROW_EDITED:      { color: "#3b82f6", bg: "#021c2c11", symbol: "✎" },
  BATCH_UPLOADED:  { color: "#f59e0b", bg: "#2c1b0011", symbol: "↑" },
  BATCH_SUPERSEDED:{ color: "#64748b", bg: "#1e2a3a11", symbol: "⟳" },
  ISSUE_RESOLVED:  { color: "#8b5cf6", bg: "#1e0c3a11", symbol: "◉" },
  BULK_APPROVE:    { color: "#22c55e", bg: "#022c2211", symbol: "✓✓" },
  BULK_REJECT:     { color: "#ef4444", bg: "#2c021111", symbol: "✕✕" },
};

const DEFAULT_STYLE = { color: "#94a3b8", bg: "#1e253011", symbol: "·" };

export default function AuditPage() {
  const { activeTenant } = useAuth();
  const slug = activeTenant?.tenant.slug ?? "";
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [filterType, setFilterType] = useState("");

  useEffect(() => {
    if (!slug) return;
    setLoading(true);
    const params: Record<string, string> = {};
    if (filterType) params.event_type = filterType;
    tenantApi.listAudit(slug, params)
      .then((r) => { setEvents(r.results); setTotal(r.count); })
      .finally(() => setLoading(false));
  }, [slug, filterType]);

  return (
    <div className="page">
      <div className="page-header">
        <h1 className="page-title">Audit Trail</h1>
        <span className="page-subtitle">{total} events · append-only</span>
      </div>

      <div className="filter-bar">
        <select value={filterType} onChange={(e) => setFilterType(e.target.value)}>
          <option value="">All event types</option>
          <option value="ROW_APPROVED">Row Approved</option>
          <option value="ROW_REJECTED">Row Rejected</option>
          <option value="ROW_EDITED">Row Edited</option>
          <option value="BATCH_UPLOADED">Batch Uploaded</option>
          <option value="ISSUE_RESOLVED">Issue Resolved</option>
          <option value="BULK_APPROVE">Bulk Approve</option>
        </select>
      </div>

      {loading ? (
        <div className="page-loading"><div className="spinner" /></div>
      ) : (
        <div className="audit-timeline">
          {events.length === 0 && (
            <div className="empty-state">No audit events yet.</div>
          )}
          {events.map((ev) => {
            const style = EVENT_STYLES[ev.event_type] ?? DEFAULT_STYLE;
            const isExpanded = expanded === ev.id;
            return (
              <div key={ev.id} className="audit-entry" onClick={() => setExpanded(isExpanded ? null : ev.id)}>
                <div className="audit-dot" style={{ background: style.bg, color: style.color, border: `1.5px solid ${style.color}33` }}>
                  {style.symbol}
                </div>
                <div className="audit-content">
                  <div className="audit-meta">
                    <span className="audit-event-type" style={{ color: style.color }}>
                      {ev.event_type_display}
                    </span>
                    <span className="audit-time">{new Date(ev.created_at).toLocaleString()}</span>
                  </div>
                  <div className="audit-actor">
                    {ev.actor.email}
                    {ev.actor_ip && <span style={{ color: "#475569", marginLeft: 8 }}>· {ev.actor_ip}</span>}
                  </div>
                  {ev.comment && <div className="audit-comment">"{ev.comment}"</div>}
                  {isExpanded && (
                    <div className="audit-diff">
                      {ev.before_state && (
                        <div>
                          <div className="diff-label">Before</div>
                          <pre className="diff-code">{JSON.stringify(ev.before_state, null, 2)}</pre>
                        </div>
                      )}
                      {ev.after_state && (
                        <div>
                          <div className="diff-label">After</div>
                          <pre className="diff-code">{JSON.stringify(ev.after_state, null, 2)}</pre>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
