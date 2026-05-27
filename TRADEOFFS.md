# TRADEOFFS — Breathe ESG Ingestion Platform

## What This Document Is

This is not a list of things we ran out of time to build. It is a list of deliberate decisions to *not* build specific things, with the engineering reasoning for each omission. Good engineering judgment is knowing what not to build as much as knowing what to build.

Each entry follows: **What | Why Not Now | What Would Change This | Cost of Adding Later**

---

## Tradeoff 1: No Real-Time IoT or Streaming Data Ingestion

### What we omitted
Direct integration with building management systems, smart meters, IoT sensors, or any streaming data source. The platform handles only batch file uploads and scheduled exports.

### Why not now
Real-time streaming ingestion requires a fundamentally different architecture:

- An event streaming layer (Kafka, Kinesis) to buffer incoming sensor data
- A stream processing engine (Flink, Spark Streaming, or at minimum Kafka Streams) to deduplicate, window, and aggregate events
- A separate time-series database or columnar store optimized for write-heavy sequential data
- A completely different validation paradigm — streaming data requires stateful validation (e.g., detecting anomalous spikes relative to the rolling average), which is algorithmically harder than row-level validation of batch data

Adding this infrastructure before validating that customers have IoT-capable facilities and are willing to pay for real-time reporting would be premature optimization. Most ESG reporting is done monthly or quarterly. A customer who receives their utility bill once a month does not benefit from real-time ingestion.

### What would change this
- A customer segment in commercial real estate, manufacturing, or data centers where facilities teams want sub-daily emissions visibility
- Regulatory requirements for real-time reporting (none currently exist in major frameworks)
- IoT integration becoming a sales differentiator in competitive deals

### Cost of adding later
High, but isolated. The streaming ingestion layer would be a parallel pipeline that ultimately writes to the same `RawEmissionRow` table (with a different `source_type`). The batch ingestion pipeline would not need to change. The main investment is infrastructure and operational expertise, not data model changes.

---

## Tradeoff 2: No Spend-Based Scope 3 Category 1 Calculation

### What we omitted
Scope 3 Category 1 (Purchased Goods and Services) calculation using spend-based emission factors — where you multiply supplier invoiced spend ($) by an economic emission intensity factor (kg CO2e per $) from databases like EPA USEEIO.

This is typically the largest component of a company's Scope 3 footprint and is required for a complete GHG inventory.

### Why not now
The spend-based method requires integrating with the company's accounts payable system (SAP FI, Oracle Financials, QuickBooks) to extract supplier invoices, then mapping each supplier to a NAICS/SIC industry code, then applying the appropriate economic factor. This is a significant data integration and data quality problem:

1. **Supplier name deduplication** is a known hard problem. "Microsoft Corp.", "MSFT", "Microsoft Corporation" are the same supplier but require entity resolution to recognize as such.
2. **Industry classification** is often wrong or missing in AP systems. A misclassification can produce a 10x error in the calculated emission.
3. **AP data sensitivity** is high — invoice-level data reveals supplier relationships, pricing, and commercial strategies that companies are often reluctant to upload to a SaaS platform.
4. The USEEIO and similar databases have known methodological limitations that mean spend-based calculations are often off by 50-200%. Building a product feature on top of an inherently imprecise methodology requires careful expectation-setting.

### What would change this
- A customer segment (large enterprise manufacturers) where Scope 3 Category 1 is required for CDP or Science Based Targets (SBT) compliance
- A reliable third-party supplier data API that handles entity resolution (Ecovadis, Watershed's supplier engagement module)
- A data sharing agreement with the customer's finance team for AP data

### Cost of adding later
Medium. The data model already has a `calculation_method` field with values `ACTIVITY_BASED` and `SPEND_BASED`. The NormalizedEmissionRow `metadata` JSONB field can store the supplier mapping and NAICS code. The main work is building the supplier resolution pipeline and integrating USEEIO factor data.

---

## Tradeoff 3: No Third-Party Verification Integration

### What we omitted
A workflow for engaging a third-party verifier (e.g., Bureau Veritas, SGS, or an independent auditor) who needs read-only access to the platform to verify data before a regulatory submission. This would include:

- Verifier-role user type with scoped read access
- Document annotation system for verifiers to flag issues
- Formal "verification complete" status on a reporting period
- Digital signature or timestamping of the verified data set

### Why not now
Third-party verification workflows are complex to design correctly because they vary significantly across:

- **Standards:** ISO 14064-3 verification has different requirements than CDP independent assurance or SEC climate disclosure verification
- **Scope:** Limited assurance vs. reasonable assurance vs. full certification have different documentation requirements
- **Process:** Some verifiers want raw data access; others want summary reports; others want an API they can query

Building the wrong verification workflow would require significant rework when the first real verifier engagement exposes the mismatches. The better approach is to first ship the audit trail and export functionality (which we have), let customers use that for manual verification processes, and design the formal verification module after watching one or two real engagements.

### What would change this
- A customer with a signed third-party verification contract that requires platform integration
- A regulatory mandate that requires platform-native verification (SEC rules do not currently require this)

### Cost of adding later
Medium-low for the access model (add a new role, scope the permissions), medium-high for the workflow and documentation features. The audit trail is already designed to produce the evidence a verifier needs — the gap is the UI and formal sign-off mechanism.

---

## Tradeoff 4: No Automated Emission Factor Refresh Pipeline

### What we omitted
An automated system that fetches updated emission factors from DEFRA, EPA, IEA, or other official sources and flags which existing calculations need to be recomputed due to factor updates.

In production ESG software, emission factors change annually. When DEFRA releases their updated Conversion Factors document each year, every calculation using the old factors should be recomputed and the delta flagged for review.

### Why not now
Emission factor databases are published in inconsistent formats (DEFRA as Excel, EPA as CSV and API, IEA as PDF), on inconsistent schedules, with inconsistent versioning. Building reliable parsers for these sources requires ongoing maintenance as the formats change each year. Maintaining a curated factor database is a domain expertise problem as much as a software problem.

The correct short-term approach is: maintain the factor library manually (as a seeded database fixture), document the process for loading updated factors, and track which calculations used which factor version via the `emission_factor_id` FK on `EmissionCalculation`. When factors update, a management command can identify affected calculations and re-run them.

### What would change this
- A customer volume where manual factor maintenance takes more than 2 hours per year per source
- A partnership with a factor data provider (e.g., ClimatePartner, ecoinvent)

### Cost of adding later
Low for the recomputation pipeline (it's just a management command that already works). Medium for the automated scraping and parsing of factor databases (ongoing maintenance cost, not one-time).

---

## Tradeoff 5: No Materialized Views or Separate Analytics Schema

### What we omitted
Pre-aggregated summary tables (materialized views) for dashboard queries. Dashboard metrics like "total Scope 1 emissions this quarter" require summing across potentially millions of rows. Without pre-aggregation, these queries get slow.

### Why not now
Premature optimization. Before the system has real data from real tenants, we don't know:

1. What the actual query patterns are (maybe dashboards query by facility more than by scope)
2. What the data volume will be (a tenant with 50 rows/month doesn't need materialized views)
3. Whether PostgreSQL's query planner with appropriate indexes is sufficient

The correct sequence is: build with plain queries, measure query times, identify the slow ones, then introduce materialized views for those specific queries. Adding materialized views speculatively creates maintenance burden (refresh scheduling, invalidation logic) without confirmed benefit.

### What would change this
- A tenant with >100,000 rows where dashboard queries take >3 seconds
- A product requirement for sub-second dashboard loading

### Cost of adding later
Low. PostgreSQL `CREATE MATERIALIZED VIEW` is straightforward. The application code change is minimal — the dashboard API endpoint queries the materialized view instead of the base table. The main operational cost is setting up the refresh schedule (pg_cron or a Celery beat task).

---

## Summary Table

| Omitted Feature | Primary Reason | Future Trigger | Difficulty to Add |
|---|---|---|---|
| Real-time IoT streaming | Architecture complexity vs. marginal value | IoT customer segment | High (infrastructure) |
| Spend-based Scope 3 Cat 1 | Data quality + AP data sensitivity | SBT/CDP compliance customers | Medium (data pipeline) |
| Third-party verifier workflow | Spec uncertainty, need real examples | Signed verifier contract | Medium |
| Automated factor refresh | Inconsistent source formats | Volume justification | Medium |
| Materialized view analytics | Premature optimization | Measured slow queries | Low |
