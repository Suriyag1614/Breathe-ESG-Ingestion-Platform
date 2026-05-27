# DATA MODEL — Breathe ESG Ingestion Platform

## Design Philosophy

The data model is built around four axiomatic constraints:

1. **Immutability of raw data.** Once a row is ingested, the source record is never modified. All analyst corrections create new versioned records linked by `parent_row_id`. This is non-negotiable for GHG accounting — auditors must be able to reconstruct exactly what was received from the source system.

2. **Tenant isolation at the row level.** Every record carries a `tenant_id` foreign key, and all queries are filtered through a tenant-aware manager. This is enforced in the ORM layer, not only at the API layer, because defense in depth prevents bugs in one layer from leaking cross-tenant data.

3. **Unit normalization is a separate pipeline stage.** Raw values are stored exactly as received (e.g., `1,200 therms`). Normalized values (e.g., `126,144 MJ`) are computed and stored separately, with the conversion factor and methodology recorded. This means we can recompute if emission factors change without touching raw data.

4. **Every state transition is an event.** Rather than a simple `status` enum that can be silently updated, the workflow uses an `AuditEvent` table that is append-only. The current state of a row is derived from the latest event. This makes the audit trail a first-class data structure, not an afterthought.

---

## Entity Relationship Overview

```
Tenant
  └── DataSource (configured per tenant)
        └── IngestionBatch (one run of the pipeline)
              └── RawEmissionRow (immutable source record)
                    ├── NormalizedEmissionRow (computed, versioned)
                    │     └── EmissionCalculation (EF applied)
                    └── AuditEvent (append-only state log)
                          └── User (who triggered it)

User ──── TenantMembership ──── Tenant
EmissionFactor (global reference table)
ValidationIssue (linked to RawEmissionRow)
```

---

## Tables

### 1. `tenants_tenant`

**Purpose:** Root entity for multi-tenancy. Every piece of data in the platform is owned by a Tenant. This table stores configuration and billing metadata.

**Why a separate Tenant model?** Some platforms use a `company` field on the User model. That approach breaks down when you need per-tenant settings (e.g., default emission factor methodology, reporting year, preferred units). A dedicated Tenant model keeps tenant configuration separate from user identity.

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK | UUIDs prevent enumeration attacks |
| `name` | VARCHAR(255) | NOT NULL | Display name |
| `slug` | VARCHAR(100) | UNIQUE, NOT NULL | URL-safe identifier |
| `created_at` | TIMESTAMPTZ | NOT NULL | |
| `updated_at` | TIMESTAMPTZ | NOT NULL | |
| `is_active` | BOOLEAN | DEFAULT TRUE | Soft-disable entire tenant |
| `reporting_year` | SMALLINT | | Fiscal year for current period |
| `preferred_unit_system` | VARCHAR(10) | DEFAULT 'metric' | metric / imperial |
| `emission_factor_methodology` | VARCHAR(50) | DEFAULT 'GHG_PROTOCOL' | GHG_PROTOCOL / DEFRA / EPA |
| `timezone` | VARCHAR(50) | DEFAULT 'UTC' | For billing period localization |

**Indexes:** `slug` (unique lookup), `is_active` (filter inactive tenants)

---

### 2. `tenants_user`

**Purpose:** Platform user. Extended from Django's AbstractBaseUser to keep email as the primary identifier (not username), which is standard in enterprise B2B software.

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `email` | VARCHAR(254) | UNIQUE, NOT NULL | Primary identifier |
| `first_name` | VARCHAR(150) | NOT NULL | |
| `last_name` | VARCHAR(150) | NOT NULL | |
| `is_active` | BOOLEAN | DEFAULT TRUE | |
| `is_staff` | BOOLEAN | DEFAULT FALSE | Django admin access |
| `date_joined` | TIMESTAMPTZ | NOT NULL | |
| `last_login` | TIMESTAMPTZ | | |

**Why UUID PK?** Sequential IDs expose record counts and make IDs guessable. In a multi-tenant SaaS, this matters.

---

### 3. `tenants_tenantmembership`

**Purpose:** Many-to-many between User and Tenant with role. A user can belong to multiple tenants (e.g., a consultant auditing multiple clients) with different roles in each.

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant` | FK → Tenant | NOT NULL | |
| `user` | FK → User | NOT NULL | |
| `role` | VARCHAR(30) | NOT NULL | ADMIN / ANALYST / VIEWER |
| `created_at` | TIMESTAMPTZ | NOT NULL | |
| `invited_by` | FK → User | NULL | Audit who added this member |

**Unique constraint:** `(tenant, user)` — a user has exactly one role per tenant.

**Roles:**
- `ADMIN` — can configure data sources, manage members, approve final submissions
- `ANALYST` — can review, edit, approve/reject individual rows
- `VIEWER` — read-only access to approved data and reports

---

### 4. `ingestion_datasource`

**Purpose:** Configured integration endpoint per tenant. Tracks *where* data comes from, not the data itself. This separation means we can have multiple SAP connections for the same tenant (e.g., different plant groups).

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant` | FK → Tenant | NOT NULL | |
| `name` | VARCHAR(255) | NOT NULL | Human label, e.g. "SAP ECC - Germany Plants" |
| `source_type` | VARCHAR(30) | NOT NULL | SAP_FLAT_FILE / UTILITY_CSV / TRAVEL_CONCUR |
| `scope` | SMALLINT | NOT NULL | 1, 2, or 3 |
| `config` | JSONB | NOT NULL DEFAULT '{}' | Source-specific config (column mappings, etc.) |
| `created_at` | TIMESTAMPTZ | | |
| `is_active` | BOOLEAN | DEFAULT TRUE | |
| `created_by` | FK → User | | |

**Why JSONB for config?** Each source type has a completely different configuration schema (SAP needs plant code mapping, Utility needs meter ID normalization rules, Travel needs carrier mapping). A JSONB field avoids a proliferation of nullable columns or a complex EAV scheme. The config schema is validated in the application layer against a Pydantic model per source type.

---

### 5. `ingestion_ingestionbatch`

**Purpose:** One execution of the ingestion pipeline for a given data source. Groups all rows from a single file upload or API pull. Critical for bulk operations (e.g., "reject all rows from the bad February upload").

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant` | FK → Tenant | NOT NULL | Denormalized for query performance |
| `data_source` | FK → DataSource | NOT NULL | |
| `status` | VARCHAR(30) | NOT NULL | PENDING / PROCESSING / COMPLETED / FAILED |
| `uploaded_by` | FK → User | NOT NULL | |
| `uploaded_at` | TIMESTAMPTZ | NOT NULL | |
| `completed_at` | TIMESTAMPTZ | NULL | NULL until pipeline finishes |
| `source_filename` | VARCHAR(500) | | Original filename |
| `source_file_hash` | VARCHAR(64) | | SHA-256 of raw file for deduplication |
| `row_count_raw` | INTEGER | | How many rows were parsed |
| `row_count_valid` | INTEGER | | How many passed validation |
| `row_count_failed` | INTEGER | | How many failed validation |
| `error_summary` | JSONB | | Top-level pipeline errors (not row errors) |
| `pipeline_version` | VARCHAR(20) | NOT NULL | Semver of ingestion code used |

**Why `source_file_hash`?** Prevents accidental duplicate uploads of the same file. If a user re-uploads the same CSV, the system detects it and warns rather than creating duplicate records.

**Why `pipeline_version`?** If a bug is found in the normalization code, we can identify which batches were processed with the affected version and trigger reprocessing.

---

### 6. `ingestion_rawemissionrow`

**Purpose:** The immutable ledger of exactly what was received from the source system. This is the single most important table in the schema. **It is never updated after creation.**

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant` | FK → Tenant | NOT NULL | |
| `batch` | FK → IngestionBatch | NOT NULL | |
| `row_index` | INTEGER | NOT NULL | Position in source file (0-based) |
| `source_type` | VARCHAR(30) | NOT NULL | Copied from DataSource |
| `scope` | SMALLINT | NOT NULL | 1, 2, or 3 |
| `raw_data` | JSONB | NOT NULL | Full original row, keys = source column names |
| `ingested_at` | TIMESTAMPTZ | NOT NULL | |
| `status` | VARCHAR(30) | NOT NULL | PENDING / APPROVED / REJECTED / NEEDS_REVIEW |
| `is_deleted` | BOOLEAN | DEFAULT FALSE | Soft delete only |
| `deleted_at` | TIMESTAMPTZ | NULL | |
| `deleted_by` | FK → User | NULL | |

**Why store `raw_data` as JSONB?** Each source type has a different column structure. Storing the complete original row means we never lose data, regardless of whether our parsing logic extracted every field correctly. We can reparse from the stored raw data if the extraction logic changes.

**Why `row_index`?** Analysts can cross-reference with the original file. "Row 247 in February_SAP_export.csv" is a meaningful statement.

---

### 7. `ingestion_normalizedemissionrow`

**Purpose:** The analyst-editable, versioned view of a raw row after normalization. When an analyst edits a value, a new NormalizedEmissionRow is created with `parent_id` pointing to the previous version. The current version is the one where `is_current = TRUE`.

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant` | FK → Tenant | NOT NULL | |
| `raw_row` | FK → RawEmissionRow | NOT NULL | Always traceable to source |
| `parent_id` | FK → self | NULL | NULL = first version |
| `version` | SMALLINT | NOT NULL DEFAULT 1 | Increments on edit |
| `is_current` | BOOLEAN | NOT NULL DEFAULT TRUE | Only one TRUE per raw_row |
| `activity_type` | VARCHAR(50) | NOT NULL | FUEL_COMBUSTION / ELECTRICITY / FLIGHT / etc. |
| `quantity` | NUMERIC(18,6) | NOT NULL | Normalized quantity |
| `unit` | VARCHAR(30) | NOT NULL | Normalized unit (e.g., MJ, kWh, km) |
| `quantity_original` | NUMERIC(18,6) | | As received from source |
| `unit_original` | VARCHAR(30) | | As received from source |
| `conversion_factor` | NUMERIC(18,10) | | Applied to convert original → normalized |
| `conversion_source` | VARCHAR(100) | | e.g., "DEFRA 2023 Table 1A" |
| `period_start` | DATE | NOT NULL | Start of activity period |
| `period_end` | DATE | NOT NULL | End of activity period |
| `facility_id` | VARCHAR(100) | | Plant code, meter ID, cost center |
| `facility_name` | VARCHAR(255) | | Human-readable |
| `country_code` | CHAR(2) | | ISO 3166-1 alpha-2 |
| `region` | VARCHAR(100) | | State/province for grid emission factors |
| `supplier` | VARCHAR(255) | | Utility provider, airline, fuel supplier |
| `notes` | TEXT | | Analyst notes |
| `created_at` | TIMESTAMPTZ | NOT NULL | |
| `created_by` | FK → User | NOT NULL | |
| `metadata` | JSONB | DEFAULT '{}' | Source-specific extra fields |

**Why version and is_current instead of update-in-place?** Regulatory audits require showing the complete edit history of every record. If an analyst corrects a quantity from 1,200 to 1,020 kWh, an auditor must be able to see who made that change, when, and what the original value was. Update-in-place with a separate history table is technically equivalent but more fragile — it requires two tables to stay in sync.

**Why separate `quantity_original` and `quantity`?** The original value from SAP might be in `therms`; the normalized value is in `MJ`. Storing both means we can verify the conversion is correct and re-run conversions with updated factors.

---

### 8. `ingestion_validationissue`

**Purpose:** One record per validation rule failure per raw row. Not a boolean flag — a structured object that the analyst UI can render meaningfully.

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `raw_row` | FK → RawEmissionRow | NOT NULL | |
| `tenant` | FK → Tenant | NOT NULL | |
| `rule_code` | VARCHAR(50) | NOT NULL | e.g., MISSING_QUANTITY, INVALID_AIRPORT_CODE |
| `severity` | VARCHAR(10) | NOT NULL | ERROR / WARNING / INFO |
| `field_name` | VARCHAR(100) | | Which field triggered it |
| `field_value` | VARCHAR(500) | | The offending value |
| `message` | TEXT | NOT NULL | Human-readable description |
| `is_resolved` | BOOLEAN | DEFAULT FALSE | |
| `resolved_by` | FK → User | NULL | |
| `resolved_at` | TIMESTAMPTZ | NULL | |
| `resolution_note` | TEXT | | Why it was overridden |
| `created_at` | TIMESTAMPTZ | NOT NULL | |

**Why store `field_value`?** The raw row's `raw_data` JSONB could change keys between pipeline versions. Snapshotting the offending value here makes the validation issue self-contained and readable without parsing the raw_data again.

---

### 9. `audit_auditevent`

**Purpose:** Append-only log of every state-changing action on any entity. This is the foundation of the audit trail. Nothing is ever deleted from this table.

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant` | FK → Tenant | NOT NULL | |
| `event_type` | VARCHAR(50) | NOT NULL | ROW_APPROVED / ROW_REJECTED / ROW_EDITED / BATCH_UPLOADED / etc. |
| `actor` | FK → User | NOT NULL | Who triggered it |
| `actor_ip` | INET | | Request IP at time of action |
| `target_type` | VARCHAR(50) | NOT NULL | Content type (RawEmissionRow, IngestionBatch, etc.) |
| `target_id` | UUID | NOT NULL | PK of the affected object |
| `before_state` | JSONB | | Serialized state before change |
| `after_state` | JSONB | | Serialized state after change |
| `comment` | TEXT | | Analyst's justification |
| `created_at` | TIMESTAMPTZ | NOT NULL | |
| `batch_event_id` | UUID | | Groups events in bulk operations |

**Why JSONB for before/after state?** The alternative is a separate diff table with one row per changed field. JSONB is significantly simpler to write and query for audit display purposes, and the size overhead is acceptable for compliance use cases where storage is cheap relative to regulatory risk.

**Why not use Django's built-in signals?** Signals are hard to test, can be accidentally disabled, and don't capture the actor's IP or comment. A dedicated service method that writes audit events explicitly is more reliable.

---

### 10. `emissions_emissionfactor`

**Purpose:** Reference data mapping activity types to GHG emission factors. Shared across tenants but versioned so methodology changes are tracked.

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `activity_type` | VARCHAR(50) | NOT NULL | FUEL_COMBUSTION, ELECTRICITY, etc. |
| `fuel_type` | VARCHAR(50) | | Natural Gas, Diesel, etc. |
| `country_code` | CHAR(2) | | NULL = global |
| `region` | VARCHAR(100) | | For grid emission factors |
| `unit` | VARCHAR(30) | NOT NULL | Per unit of activity (e.g., per kWh) |
| `co2_factor` | NUMERIC(18,10) | NOT NULL | kg CO2 per unit |
| `ch4_factor` | NUMERIC(18,10) | | kg CH4 per unit |
| `n2o_factor` | NUMERIC(18,10) | | kg N2O per unit |
| `co2e_factor` | NUMERIC(18,10) | NOT NULL | kg CO2e per unit (with GWP applied) |
| `gwp_version` | VARCHAR(20) | | AR4 / AR5 / AR6 |
| `source` | VARCHAR(200) | NOT NULL | e.g., "DEFRA 2023 Conversion Factors" |
| `valid_from` | DATE | NOT NULL | |
| `valid_to` | DATE | | NULL = currently valid |
| `created_at` | TIMESTAMPTZ | | |

---

### 11. `emissions_emissioncalculation`

**Purpose:** The computed GHG output for a normalized row. Kept separate from NormalizedEmissionRow so calculation logic can be re-run when emission factors are updated without touching the analyst-reviewed data.

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `tenant` | FK → Tenant | NOT NULL | |
| `normalized_row` | FK → NormalizedEmissionRow | NOT NULL | |
| `emission_factor` | FK → EmissionFactor | NOT NULL | Full traceability |
| `co2e_kg` | NUMERIC(18,6) | NOT NULL | Result |
| `co2_kg` | NUMERIC(18,6) | | |
| `ch4_kg` | NUMERIC(18,6) | | |
| `n2o_kg` | NUMERIC(18,6) | | |
| `calculation_method` | VARCHAR(50) | | SPEND_BASED / ACTIVITY_BASED |
| `calculated_at` | TIMESTAMPTZ | NOT NULL | |
| `calculator_version` | VARCHAR(20) | NOT NULL | Semver |

---

## Multi-Tenancy Strategy

Every application-level table carries a `tenant_id` column. The ORM enforces tenant isolation through a custom `TenantAwareManager`:

```python
class TenantAwareManager(models.Manager):
    def get_queryset(self):
        # Requires tenant to be set on the manager instance
        # Called as: Model.objects.for_tenant(request.tenant)
        raise ImproperlyConfigured("Use for_tenant() instead of objects directly")

    def for_tenant(self, tenant):
        return super().get_queryset().filter(tenant=tenant)
```

Row-Level Security (RLS) in PostgreSQL is the defense-in-depth layer. Even if application code accidentally omits the tenant filter, the database will prevent cross-tenant data access.

---

## Soft Deletion Strategy

All user-facing entities implement soft deletion via `is_deleted` + `deleted_at` + `deleted_by`. The default manager filters these out. A `with_deleted` manager provides access for admin and audit purposes.

Hard deletion is never performed on ingestion or audit data.

---

## Index Strategy

```sql
-- Tenant isolation (most critical)
CREATE INDEX idx_raw_row_tenant ON ingestion_rawemissionrow(tenant_id);
CREATE INDEX idx_raw_row_batch ON ingestion_rawemissionrow(batch_id);
CREATE INDEX idx_raw_row_status ON ingestion_rawemissionrow(tenant_id, status);

-- Audit trail
CREATE INDEX idx_audit_target ON audit_auditevent(target_type, target_id);
CREATE INDEX idx_audit_actor ON audit_auditevent(actor_id, created_at DESC);
CREATE INDEX idx_audit_tenant_time ON audit_auditevent(tenant_id, created_at DESC);

-- Emission calculations
CREATE INDEX idx_calc_normalized ON emissions_emissioncalculation(normalized_row_id);
CREATE INDEX idx_ef_activity ON emissions_emissionfactor(activity_type, valid_from, valid_to);
```

---

## What Was Deliberately Not Modeled

1. **Reporting/aggregation tables** — A production system would have materialized views or a separate analytics schema for dashboard queries. These were omitted to keep the model focused on ingestion and audit.

2. **Document attachments** — Real ESG platforms store PDF bills, purchase orders, etc. as attachments to rows. This would require an S3 integration and a `Document` table. Omitted for scope.

3. **Approval chains** — Enterprise deployments often require multi-level approval (analyst → manager → CFO). The current workflow supports single-level analyst approval, which is sufficient for this scope.
