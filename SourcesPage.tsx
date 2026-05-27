import { useEffect, useState } from "react";
import { tenantApi, type DataSource } from "../lib/api";
import { useAuth } from "../hooks/useAuth";

export default function SourcesPage() {
  const { activeTenant } = useAuth();
  const slug = activeTenant?.tenant.slug ?? "";
  const [sources, setSources] = useState<DataSource[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ name: "", source_type: "SAP_FLAT_FILE", scope: 1 });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!slug) return;
    tenantApi.listSources(slug).then((r) => setSources(r.results)).finally(() => setLoading(false));
  }, [slug]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      const newSrc = await tenantApi.createSource(slug, form);
      setSources((s) => [...s, newSrc]);
      setCreating(false);
      setForm({ name: "", source_type: "SAP_FLAT_FILE", scope: 1 });
    } catch (err: any) {
      setError(err.body?.detail ?? "Failed to create source.");
    }
  };

  const SCOPE_BY_TYPE: Record<string, number> = {
    SAP_FLAT_FILE: 1,
    UTILITY_CSV: 2,
    TRAVEL_CONCUR: 3,
  };

  return (
    <div className="page">
      <div className="page-header">
        <h1 className="page-title">Data Sources</h1>
        {activeTenant?.role === "ADMIN" && (
          <button className="btn btn-primary" onClick={() => setCreating(true)}>+ New Source</button>
        )}
      </div>

      {activeTenant?.role !== "ADMIN" && (
        <div className="alert alert-info" style={{ marginBottom: 16 }}>
          Only Admins can configure data sources. Contact your tenant admin.
        </div>
      )}

      {creating && (
        <div className="card" style={{ marginBottom: 20 }}>
          <div className="card-title">New Data Source</div>
          <form onSubmit={handleCreate}>
            <div className="form-field">
              <label>Name</label>
              <input
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                placeholder="e.g. SAP ECC — Germany Plants"
                required
              />
            </div>
            <div className="form-row">
              <div className="form-field">
                <label>Source Type</label>
                <select
                  value={form.source_type}
                  onChange={(e) => setForm((f) => ({
                    ...f,
                    source_type: e.target.value,
                    scope: SCOPE_BY_TYPE[e.target.value] ?? 1,
                  }))}
                >
                  <option value="SAP_FLAT_FILE">SAP Flat File Export</option>
                  <option value="UTILITY_CSV">Utility CSV Export</option>
                  <option value="TRAVEL_CONCUR">SAP Concur Export</option>
                </select>
              </div>
              <div className="form-field">
                <label>GHG Scope</label>
                <select
                  value={form.scope}
                  onChange={(e) => setForm((f) => ({ ...f, scope: Number(e.target.value) }))}
                >
                  <option value={1}>Scope 1 — Direct</option>
                  <option value={2}>Scope 2 — Grid</option>
                  <option value={3}>Scope 3 — Value Chain</option>
                </select>
              </div>
            </div>
            {error && <div className="alert alert-error">{error}</div>}
            <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
              <button type="submit" className="btn btn-primary">Create</button>
              <button type="button" className="btn" onClick={() => setCreating(false)}>Cancel</button>
            </div>
          </form>
        </div>
      )}

      {loading ? (
        <div className="page-loading"><div className="spinner" /></div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Type</th>
                <th>Scope</th>
                <th>Status</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {sources.length === 0 && (
                <tr><td colSpan={5} style={{ textAlign: "center", color: "#64748b", padding: 24 }}>
                  No data sources configured yet.
                </td></tr>
              )}
              {sources.map((s) => (
                <tr key={s.id}>
                  <td style={{ fontWeight: 500 }}>{s.name}</td>
                  <td><span className="chip">{s.source_type_display}</span></td>
                  <td>Scope {s.scope}</td>
                  <td>
                    <span style={{ color: s.is_active ? "#22c55e" : "#ef4444" }}>
                      {s.is_active ? "● Active" : "○ Inactive"}
                    </span>
                  </td>
                  <td>{new Date(s.created_at).toLocaleDateString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
