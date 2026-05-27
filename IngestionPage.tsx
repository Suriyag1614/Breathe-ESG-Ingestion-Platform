import { useEffect, useRef, useState } from "react";
import { tenantApi, type DataSource, type IngestionBatch } from "../lib/api";
import { useAuth } from "../hooks/useAuth";

export default function IngestionPage() {
  const { activeTenant } = useAuth();
  const slug = activeTenant?.tenant.slug ?? "";
  const [sources, setSources] = useState<DataSource[]>([]);
  const [batches, setBatches] = useState<IngestionBatch[]>([]);
  const [selectedSource, setSelectedSource] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<IngestionBatch | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!slug) return;
    tenantApi.listSources(slug).then((r) => {
      setSources(r.results);
      if (r.results.length > 0) setSelectedSource(r.results[0].id);
    });
    tenantApi.listBatches(slug).then((r) => setBatches(r.results));
  }, [slug]);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files[0];
    if (f) setFile(f);
  };

  const handleUpload = async () => {
    if (!file || !selectedSource) return;
    setUploading(true);
    setError(null);
    setUploadResult(null);
    try {
      const result = await tenantApi.uploadFile(slug, file, selectedSource);
      setUploadResult(result);
      setBatches((prev) => [result, ...prev]);
      setFile(null);
    } catch (e: any) {
      const msg = e.body?.detail ?? e.message ?? "Upload failed";
      setError(msg);
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="page">
      <div className="page-header">
        <h1 className="page-title">Ingest Data</h1>
        <span className="page-subtitle">Upload SAP, Utility, or Travel files</span>
      </div>

      <div className="ingest-grid">
        <div className="ingest-upload-panel">
          <div className="form-field">
            <label>Data Source</label>
            <select value={selectedSource} onChange={(e) => setSelectedSource(e.target.value)}>
              {sources.map((s) => (
                <option key={s.id} value={s.id}>{s.name} (Scope {s.scope})</option>
              ))}
              {sources.length === 0 && <option disabled>No sources configured</option>}
            </select>
          </div>

          <div
            className={`drop-zone ${dragOver ? "drag-over" : ""} ${file ? "has-file" : ""}`}
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
          >
            <input
              type="file"
              ref={fileInputRef}
              accept=".csv,.tsv,.txt"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              style={{ display: "none" }}
            />
            {file ? (
              <>
                <div className="drop-zone-icon">📄</div>
                <div className="drop-zone-filename">{file.name}</div>
                <div className="drop-zone-size">{(file.size / 1024).toFixed(1)} KB</div>
              </>
            ) : (
              <>
                <div className="drop-zone-icon">↑</div>
                <div className="drop-zone-title">Drop file here or click to browse</div>
                <div className="drop-zone-hint">CSV · TSV · Max 50 MB · SHA-256 deduplication</div>
              </>
            )}
          </div>

          {error && <div className="alert alert-error">{error}</div>}
          {uploadResult && (
            <div className="alert alert-success">
              ✓ Ingestion complete — {uploadResult.row_count_valid} valid, {uploadResult.row_count_failed} failed
            </div>
          )}

          <button
            className="btn btn-primary"
            onClick={handleUpload}
            disabled={!file || !selectedSource || uploading}
          >
            {uploading ? <><span className="spinner-sm" /> Processing…</> : "Run Ingestion Pipeline"}
          </button>
        </div>

        <div className="pipeline-status-panel">
          <div className="panel-label">Pipeline Checks</div>
          <div className="check-list">
            {[
              { label: "Encoding detection", value: file ? "UTF-8 / Latin-1" : "—", ok: !!file },
              { label: "Duplicate file check", value: "SHA-256 hash", ok: true },
              { label: "Delimiter detection", value: file ? "Auto-detect" : "—", ok: !!file },
              { label: "Unit normalization", value: file ? "SAP→ISO mapped" : "—", ok: !!file },
              { label: "Validation engine", value: file ? "Ready" : "—", ok: !!file },
            ].map((c) => (
              <div key={c.label} className="check-row">
                <span className="check-label">{c.label}</span>
                <span className={`check-value ${c.ok ? "ok" : "dim"}`}>{c.value}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="section-title" style={{ marginTop: 28, marginBottom: 12 }}>Recent Batches</div>
      <div className="batch-list">
        {batches.length === 0 && <div className="empty-state">No batches yet. Upload a file to get started.</div>}
        {batches.map((b) => (
          <div key={b.id} className="batch-item">
            <div className={`batch-type-badge ${b.source_type.toLowerCase()}`}>
              {b.source_type === "SAP_FLAT_FILE" ? "SAP" : b.source_type === "UTILITY_CSV" ? "UTIL" : "TRAVEL"}
            </div>
            <div className="batch-info">
              <div className="batch-name">{b.source_filename || b.id}</div>
              <div className="batch-meta">{b.data_source_name} · {new Date(b.uploaded_at).toLocaleString()}</div>
            </div>
            <div className="batch-stats">
              <span style={{ color: "#22c55e" }}>✓ {b.row_count_valid ?? 0}</span>
              <span style={{ color: "#ef4444" }}>✕ {b.row_count_failed ?? 0}</span>
            </div>
            <div className="batch-status">{b.status_display}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
