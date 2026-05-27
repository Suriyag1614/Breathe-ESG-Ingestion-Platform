/**
 * Breathe ESG — API Client
 * Typed fetch wrapper. All calls go through `apiFetch`.
 * JWT access token is read from localStorage and injected automatically.
 * On 401, token is cleared and user is redirected to /login.
 */

const BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1";

// ─── TOKEN STORAGE ───────────────────────────────────────────────────────────

export const tokenStore = {
  get: () => localStorage.getItem("access_token"),
  set: (t: string) => localStorage.setItem("access_token", t),
  getRefresh: () => localStorage.getItem("refresh_token"),
  setRefresh: (t: string) => localStorage.setItem("refresh_token", t),
  clear: () => {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    localStorage.removeItem("active_tenant");
  },
};

// ─── CORE FETCH ──────────────────────────────────────────────────────────────

export class ApiError extends Error {
  constructor(public status: number, public body: unknown) {
    super(`API error ${status}`);
  }
}

async function apiFetch<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = tokenStore.get();
  const headers: Record<string, string> = {
    ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.headers as Record<string, string> ?? {}),
  };

  const res = await fetch(`${BASE_URL}${path}`, { ...options, headers });

  if (res.status === 401) {
    // Attempt token refresh
    const refreshed = await tryRefresh();
    if (refreshed) {
      // Retry original request once
      const retryHeaders = { ...headers, Authorization: `Bearer ${tokenStore.get()}` };
      const retry = await fetch(`${BASE_URL}${path}`, { ...options, headers: retryHeaders });
      if (!retry.ok) throw new ApiError(retry.status, await retry.json().catch(() => null));
      return retry.json();
    } else {
      tokenStore.clear();
      window.location.href = "/login";
      throw new ApiError(401, null);
    }
  }

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(res.status, body);
  }

  if (res.status === 204) return null as T;
  return res.json();
}

async function tryRefresh(): Promise<boolean> {
  const refresh = tokenStore.getRefresh();
  if (!refresh) return false;
  try {
    const res = await fetch(`${BASE_URL}/auth/refresh/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh }),
    });
    if (!res.ok) return false;
    const data = await res.json();
    tokenStore.set(data.access);
    return true;
  } catch {
    return false;
  }
}

// ─── TYPES ───────────────────────────────────────────────────────────────────

export interface User {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  full_name: string;
}

export interface Tenant {
  id: string;
  name: string;
  slug: string;
  reporting_year: number | null;
  preferred_unit_system: string;
  emission_factor_methodology: string;
  timezone: string;
}

export interface DataSource {
  id: string;
  name: string;
  source_type: string;
  source_type_display: string;
  scope: number;
  config: Record<string, unknown>;
  is_active: boolean;
  created_at: string;
}

export interface IngestionBatch {
  id: string;
  data_source: string;
  data_source_name: string;
  source_type: string;
  status: string;
  status_display: string;
  uploaded_by: User;
  uploaded_at: string;
  completed_at: string | null;
  source_filename: string;
  row_count_raw: number | null;
  row_count_valid: number | null;
  row_count_failed: number | null;
  error_rate: number | null;
}

export interface ValidationIssue {
  id: string;
  rule_code: string;
  severity: "ERROR" | "WARNING" | "INFO";
  field_name: string;
  field_value: string;
  message: string;
  is_resolved: boolean;
  resolved_at: string | null;
  resolution_note: string;
}

export interface RawEmissionRow {
  id: string;
  row_index: number;
  source_type: string;
  scope: number;
  status: string;
  status_display: string;
  ingested_at: string;
  batch: string;
  batch_filename: string;
  issue_count: number;
  has_errors: boolean;
  raw_data?: Record<string, unknown>;
  validation_issues?: ValidationIssue[];
  normalized_current?: NormalizedRow | null;
}

export interface NormalizedRow {
  id: string;
  version: number;
  activity_type: string;
  activity_type_display: string;
  quantity: string;
  unit: string;
  quantity_original: string | null;
  unit_original: string;
  period_start: string;
  period_end: string;
  facility_id: string;
  facility_name: string;
  country_code: string;
  supplier: string;
  notes: string;
  created_at: string;
  created_by: User;
}

export interface AuditEvent {
  id: string;
  event_type: string;
  event_type_display: string;
  actor: User;
  actor_ip: string | null;
  target_type: string;
  target_id: string;
  before_state: unknown;
  after_state: unknown;
  comment: string;
  created_at: string;
}

export interface DashboardSummary {
  total_records: number;
  pending_review: number;
  validation_errors: number;
  approved: number;
  approval_rate_pct: number;
  scope1_co2e_t: number;
  scope2_co2e_t: number;
  scope3_co2e_t: number;
  recent_batches: IngestionBatch[];
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

// ─── AUTH API ────────────────────────────────────────────────────────────────

export const authApi = {
  login: (email: string, password: string) =>
    apiFetch<{ access: string; refresh: string; user: User }>("/auth/login/", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  register: (data: { email: string; first_name: string; last_name: string; password: string; password_confirm: string }) =>
    apiFetch<{ access: string; refresh: string; user: User }>("/auth/register/", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  me: () => apiFetch<User>("/auth/me/"),

  myTenants: () =>
    apiFetch<Array<{ tenant: Tenant; role: string }>>("/auth/tenants/"),
};

// ─── TENANT API ───────────────────────────────────────────────────────────────

const t = (slug: string) => `/tenants/${slug}`;

export const tenantApi = {
  create: (data: { name: string }) =>
    apiFetch<Tenant>("/tenants/", { method: "POST", body: JSON.stringify(data) }),

  get: (slug: string) => apiFetch<Tenant>(`${t(slug)}/`),

  dashboard: (slug: string) => apiFetch<DashboardSummary>(`${t(slug)}/dashboard/`),

  // Data Sources
  listSources: (slug: string) =>
    apiFetch<PaginatedResponse<DataSource>>(`${t(slug)}/sources/`),

  createSource: (slug: string, data: Partial<DataSource>) =>
    apiFetch<DataSource>(`${t(slug)}/sources/`, { method: "POST", body: JSON.stringify(data) }),

  // Batches
  listBatches: (slug: string, params?: Record<string, string>) => {
    const qs = params ? "?" + new URLSearchParams(params).toString() : "";
    return apiFetch<PaginatedResponse<IngestionBatch>>(`${t(slug)}/batches/${qs}`);
  },

  // Upload
  uploadFile: (slug: string, file: File, dataSourceId: string) => {
    const form = new FormData();
    form.append("file", file);
    form.append("data_source_id", dataSourceId);
    return apiFetch<IngestionBatch>(`${t(slug)}/upload/`, { method: "POST", body: form });
  },

  // Review queue
  listRows: (slug: string, params?: Record<string, string>) => {
    const qs = params ? "?" + new URLSearchParams(params).toString() : "";
    return apiFetch<PaginatedResponse<RawEmissionRow>>(`${t(slug)}/rows/${qs}`);
  },

  getRow: (slug: string, rowId: string) =>
    apiFetch<RawEmissionRow>(`${t(slug)}/rows/${rowId}/`),

  approveRow: (slug: string, rowId: string, comment = "") =>
    apiFetch(`${t(slug)}/rows/${rowId}/approve/`, {
      method: "POST",
      body: JSON.stringify({ comment }),
    }),

  rejectRow: (slug: string, rowId: string, comment = "") =>
    apiFetch(`${t(slug)}/rows/${rowId}/reject/`, {
      method: "POST",
      body: JSON.stringify({ comment }),
    }),

  bulkApprove: (slug: string, ids: string[]) =>
    apiFetch<{ approved: number }>(`${t(slug)}/rows/bulk_approve/`, {
      method: "POST",
      body: JSON.stringify({ ids }),
    }),

  editRow: (slug: string, rowId: string, data: Partial<NormalizedRow>, comment = "") =>
    apiFetch<NormalizedRow>(`${t(slug)}/rows/${rowId}/edit/`, {
      method: "POST",
      body: JSON.stringify({ ...data, comment }),
    }),

  // Issues
  resolveIssue: (slug: string, issueId: string, resolution_note: string) =>
    apiFetch<ValidationIssue>(`${t(slug)}/issues/${issueId}/resolve/`, {
      method: "POST",
      body: JSON.stringify({ resolution_note }),
    }),

  // Audit
  listAudit: (slug: string, params?: Record<string, string>) => {
    const qs = params ? "?" + new URLSearchParams(params).toString() : "";
    return apiFetch<PaginatedResponse<AuditEvent>>(`${t(slug)}/audit/${qs}`);
  },
};
