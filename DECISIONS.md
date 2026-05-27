# DECISIONS — Breathe ESG Ingestion Platform

## How to Read This Document

This document records every non-obvious decision made during design. Each entry follows the same structure:

- **Decision:** What was chosen
- **Alternatives considered:** What else was viable
- **Reasoning:** Why this was chosen
- **Assumptions made:** What we believed to be true
- **Risk if assumption is wrong:** What breaks

---

## Part 1: Architecture Decisions

### AD-001: Django REST Framework over FastAPI

**Decision:** Use Django REST Framework for the backend.

**Alternatives considered:** FastAPI, Flask + SQLAlchemy, Node.js/Express

**Reasoning:** DRF's generic views, serializer validation, and permission classes map extremely well to a workflow-heavy application with many CRUD-plus-validation endpoints. Django's ORM has mature support for complex multi-tenant queries. FastAPI is faster for pure throughput but provides no scaffolding for the admin interface, permissions, or serialization that DRF ships with.

For an ESG platform where correctness and auditability matter more than sub-millisecond latency, Django's "batteries included" philosophy is an asset, not a liability.

**Assumptions made:** Ingestion throughput is in the hundreds to low-thousands of rows per batch, not millions. If a tenant uploads 500,000 rows at once, the synchronous DRF view will block. Celery is introduced for that case.

**Risk if wrong:** If the platform needs to process real-time streaming data from IoT sensors, DRF is the wrong choice. FastAPI + async workers would be needed.

---

### AD-002: PostgreSQL as the only data store

**Decision:** Single PostgreSQL instance. No Redis, no Elasticsearch, no separate time-series DB at this stage.

**Alternatives considered:** 
- PostgreSQL + Redis (for job queue)
- PostgreSQL + TimescaleDB (for time-series emissions data)
- PostgreSQL + Elasticsearch (for full-text search on audit logs)

**Reasoning:** Adding infrastructure components before you know you need them is a form of premature optimization. PostgreSQL handles our current requirements: JSONB for flexible source data, BTREE indexes for tenant filtering, and transactional integrity for the audit trail. Celery can use the database as a broker for small queue volumes. When dashboards become slow, we add materialized views before we add infrastructure.

**What would change this:** If reporting queries consistently take >2 seconds, introduce a read replica or materialized views. If queue depth regularly exceeds 10,000 jobs, switch to Redis. Neither is expected at MVP.

---

### AD-003: Row-level versioning over event sourcing

**Decision:** Store the current state in a row with a version number and `parent_id` chain, rather than rebuilding state from events.

**Alternatives considered:** Full event sourcing (state = projection of event log)

**Reasoning:** Event sourcing is powerful but adds significant operational complexity — you need to manage projections, handle eventual consistency, and explain to auditors how to read data. Our audit requirement is: "show the history of this row." That's satisfied by the version chain. Full event sourcing is warranted when you have complex business rules that need to be replayed or when projections need to serve multiple read models. We don't have that complexity yet.

**Tradeoff accepted:** Reconstructing a row's complete history requires joining across multiple NormalizedEmissionRow versions, which is a slightly more complex query than reading a flat event log.

---

### AD-004: Multi-tenancy via shared schema with tenant_id column

**Decision:** Single PostgreSQL schema, every table has a `tenant_id` column, enforced via ORM manager + PostgreSQL RLS.

**Alternatives considered:**
- Schema-per-tenant (separate PostgreSQL schema per tenant)
- Database-per-tenant (separate PostgreSQL instance)

**Reasoning:**

| Approach | Isolation | Operational Cost | Query Cross-tenant | Migration Cost |
|---|---|---|---|---|
| Column-level | Medium (RLS strengthens it) | Low | Possible | Run once |
| Schema-per-tenant | High | Medium | Hard | Run N times |
| DB-per-tenant | Highest | Very High | Impossible | Run N times |

For a startup-stage SaaS platform with ~10-100 tenants, schema-per-tenant migration complexity (running ALTER TABLE N times per migration) is not worth the isolation gain that RLS already provides for column-level separation. Database-per-tenant is only justified when tenants have contractual data residency requirements in different regions.

**Assumption:** No tenant has a contractual requirement for physical data isolation. If Breathe ESG signs a customer who requires their data to be on-premises or in a specific cloud region, the architecture would need to change.

---

### AD-005: Synchronous ingestion with Celery escape hatch

**Decision:** Small files (<5,000 rows) are processed synchronously in the request cycle. Larger files are handed to a Celery task.

**Alternatives considered:** Always async (even small files go to Celery queue)

**Reasoning:** Always-async introduces UX complexity — users must poll for status or receive a webhook. For a typical monthly SAP export (200-500 rows), synchronous processing completes in <500ms and the user gets immediate feedback. The complexity cost of mandatory async is not justified for small batches.

The 5,000 row threshold is configurable per tenant.

---

## Part 2: Data Source Decisions

### DS-001: SAP Flat File Export over OData/BAPI

**Decision:** Ingest SAP data via scheduled flat file (CSV/TSV) export, not direct OData API or BAPI calls.

**Alternatives considered:**

| Method | Integration Complexity | IT Gatekeeping | Real-time | Stability |
|---|---|---|---|---|
| OData API | Medium | Very High | Yes | Medium |
| BAPI/RFC | High | Very High | Yes | Medium |
| IDoc | Very High | Very High | Near-real-time | High |
| Flat File Export | Low | Low | No (batch) | High |

**Reasoning:** In practice, getting a corporate IT department to expose an SAP OData or BAPI endpoint to an external SaaS takes 3-18 months of security review. Flat file export via SFTP or secure upload can be approved in days. ESG data is inherently backward-looking (monthly, quarterly), so real-time ingestion provides no meaningful advantage. The engineering cost of building an IDoc adapter with zero benefit over flat files is not defensible.

The flat file approach also means we're not subject to SAP's licensing restrictions on API access, which can be significant for some customers.

**What we're giving up:** Human error in the export process (wrong date range selected, wrong plant codes included). This is mitigated by our validation layer and deduplication via file hash.

---

### DS-002: Utility data via structured CSV export

**Decision:** Ingest utility data from CSV exports from the utility portal or energy management system (not PDF bill extraction).

**Alternatives considered:**
- PDF bill extraction via OCR (e.g., Amazon Textract)
- Direct utility API (e.g., Green Button Data)

**Reasoning:** PDF extraction is inherently unreliable — utility bill formats change with every billing system upgrade, OCR fails on poor-quality scans, and column detection for multi-page PDFs requires significant engineering. For an MVP, the failure rate of PDF extraction would generate more analyst review work than it saves.

Green Button API is excellent but supported by fewer than 30% of US utilities and almost none internationally.

CSV export from the utility portal (or the customer's energy management system like Schneider Electric EcoStruxure) is available for virtually all commercial utility accounts and produces structured, consistent data.

**Assumption:** The customer has an energy management system or can log into their utility portal and export data. This is a valid assumption for any commercial operation large enough to need an ESG platform.

---

### DS-003: Concur for corporate travel

**Decision:** Model corporate travel ingestion around Concur's expense report export format.

**Alternatives considered:** Navan (TripActions), TravelPerk, generic travel agency export

**Reasoning:** Concur (SAP Concur) has approximately 55% market share in enterprise travel and expense management. Any enterprise customer large enough to run a formal ESG program almost certainly uses Concur or can export Concur-compatible data. Navan is growing rapidly but is concentrated in tech companies; TravelPerk is strong in Europe.

Modeling around Concur's schema also gives us indirect SAP system alignment — the same IT team managing SAP ERP often manages SAP Concur, reducing integration friction.

---

### DS-004: Activity-based calculation over spend-based

**Decision:** Use activity-based emission calculation (actual fuel quantities, kWh, km flown) as the primary method. Spend-based calculation ($ spend × economic emission factor) as a fallback for incomplete data.

**Reasoning:** The GHG Protocol explicitly states activity-based calculation is more accurate. Spend-based is only appropriate when activity data is unavailable (common in Scope 3 Category 1 purchased goods). For Scope 1, 2, and business travel (Scope 3 Category 6), activity data should always be available from the source systems we're ingesting.

Building a spend-based calculator without the activity data foundation would produce numbers that won't survive third-party verification.

---

## Part 3: Data Model Decisions

### DM-001: Immutable RawEmissionRow

**Decision:** `RawEmissionRow` records are created once and never modified. The `is_deleted` flag is the only mutation allowed.

**Reasoning:** If an auditor asks "what did your February fuel data look like when it was first received?", the answer must be unambiguous. Any system that allows the raw record to be overwritten cannot answer that question. This is the same principle that makes financial ledgers append-only.

**Operational consequence:** If a user re-uploads a corrected file, the system creates a new batch and new raw rows. The old batch is not deleted — it is marked as superseded. The analyst must explicitly reject the old rows.

---

### DM-002: JSONB for raw_data over EAV

**Decision:** Store the complete original source row as a JSONB blob in `raw_data`, rather than using an Entity-Attribute-Value table.

**Alternatives considered:**
- EAV table (one row per source field per record)
- Fixed columns for all possible source fields

**Reasoning:** Fixed columns fail because SAP, utility, and travel data have completely different schemas with no overlap. EAV is queryable but notoriously slow and hard to understand. JSONB provides the flexibility of EAV with much better query performance (GIN indexing) and readability. The tradeoff is that JSONB fields cannot have database-level constraints — but we enforce constraints in the application validation layer anyway.

---

### DM-003: Period_start and period_end as DATE, not TIMESTAMP

**Decision:** Emission activity periods are stored as DATE, not TIMESTAMPTZ.

**Reasoning:** Utility bills cover a billing period of e.g. March 1–March 31. There is no meaningful time-of-day component to this. Storing as TIMESTAMP introduces timezone confusion without adding information. Specifically: a utility bill that covers "March" in a US time zone would store as different TIMESTAMP values depending on where the ingestion server is located, creating subtle bugs in period overlap validation.

**Edge case:** Corporate flights have a specific departure datetime that matters for multi-day itineraries. This is handled by storing `metadata` JSONB on the NormalizedEmissionRow with departure/arrival timestamps as strings. The `period_start` and `period_end` represent the fiscal period the trip is attributed to (usually the departure date's month).

---

### DM-004: Scope as integer (1, 2, 3), not enum

**Decision:** Store GHG scope as SMALLINT (1, 2, 3), not as a string enum.

**Reasoning:** Scope is defined by the GHG Protocol as a number. Using "SCOPE_1" strings is redundant, introduces spelling variant risk, and makes arithmetic comparisons awkward. The valid values are exactly {1, 2, 3} and will not change.

**Database constraint:** `CHECK (scope IN (1, 2, 3))`

---

## Part 4: Questions for the Product Manager

These are questions that would be answered before building a production system. Assumptions made in this implementation are noted.

**Q1: What GHG reporting standard must the output conform to?**
GHG Protocol? ISO 14064? Task Force on Climate-related Financial Disclosures (TCFD)? Each has different requirements for which scopes must be reported and which calculation methodologies are acceptable.
*Assumption made: GHG Protocol.*

**Q2: Does the approval workflow require dual control (two analysts must approve before a row is locked)?**
Regulatory frameworks like ISO 14064 often require independent verification.
*Assumption made: Single analyst approval is sufficient for MVP. Admin can override.*

**Q3: What is the expected data volume? How many rows per batch, how many batches per month?**
This determines whether synchronous processing is viable or whether all batches need Celery.
*Assumption made: <10,000 rows per batch, <50 batches per month per tenant.*

**Q4: Are there contractual data residency requirements (e.g., EU data must stay in EU)?**
This would require schema-per-tenant or database-per-tenant architecture rather than the shared schema approach chosen here.
*Assumption made: No data residency requirements.*

**Q5: Does the platform need to produce a formatted PDF/Excel report for submission to a regulator or third-party verifier?**
If yes, a separate reporting module is needed. Omitted from this scope.
*Assumption made: Out of scope for MVP.*

**Q6: How are emission factors sourced and updated? Does Breathe ESG maintain them, or can customers upload custom factors?**
Custom factors are common for Scope 2 (market-based method using supplier-specific emission factors).
*Assumption made: Breathe ESG maintains a global factor library. Market-based Scope 2 factors are a future feature.*

**Q7: What happens when a batch is partially approved and then a correction is found in the source system?**
Does the analyst re-upload the entire file, or only the corrected rows? The answer determines whether the system needs a partial batch reprocessing feature.
*Assumption made: Full re-upload with explicit rejection of the old batch.*

**Q8: Are there regulatory deadlines that create peak load events?**
CDP submission deadlines, SEC climate disclosure deadlines, and GHG protocol reporting periods all create predictable spikes where many tenants upload data simultaneously.
*Assumption made: Infrastructure is not load-tested at this stage.*

**Q9: Does multi-tenancy mean customer isolation only, or do some customers have internal divisions that need their own tenant boundaries?**
A large corporation might need subsidiary-level data isolation with consolidated group reporting.
*Assumption made: One tenant = one legal entity. Consolidated reporting is a future feature.*

**Q10: What is the retention policy for raw data and audit events?**
Some regulators require 7-10 years of emissions data retention. This affects storage costs and whether the `is_deleted` soft delete mechanism is sufficient or whether data archival to cold storage is needed.
*Assumption made: Data is retained indefinitely. Archival strategy is out of scope.*
