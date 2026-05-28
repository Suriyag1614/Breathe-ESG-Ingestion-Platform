# DEMO.md — Demo Credentials and Walkthrough

## Credentials

After running `python manage.py seed_demo`, the following accounts are available:

| Role | Email | Password | What they can do |
|---|---|---|---|
| **Admin** | `admin@acme-demo.com` | `BreatheESG2024!` | Configure data sources, manage members, approve/reject rows, view audit trail |
| **Analyst** | `analyst@acme-demo.com` | `Analyst2024!` | Upload files, approve/reject rows, resolve validation issues, view audit trail |

**Tenant slug:** `acme-demo`  
**Tenant name:** Acme Corp  
**Reporting year:** FY2024

---

## Demo Walkthrough

### 1. Dashboard
Log in as the analyst. The dashboard shows:
- 3 batches processed (SAP fuel, utility electricity, travel)
- Some rows pending review (those with validation issues)
- Scope 1/2/3 CO₂e breakdown (from approved rows with emission factors)

### 2. Data Ingestion
Navigate to **Ingest Data**. The three sample files are listed in the recent batches panel with their row counts and error rates. You can also upload the actual CSV files from the project:
- `sap_fuel_q1_2024.csv`
- `utility_electricity_q1_2024.csv`
- `travel_concur_q1_2024.csv`

### 3. Review Queue
Navigate to **Review Queue**. Rows with validation issues are listed here. Click any row to open the detail panel showing:
- Raw source data (exact fields from the CSV)
- Validation issues with rule codes, severity, and actionable messages

**Interesting rows to explore:**

| Row | Source | Issue | What to do |
|---|---|---|---|
| SAP row with material 999999 | SAP | `SAP_UNMAPPED_MATERIAL` (WARNING) | Can approve — add material to fuel mapping in DataSource config |
| SAP row with blank MENGE | SAP | `SAP_MISSING_QUANTITY` (ERROR) | Cannot approve — must reject |
| Dallas utility row | Utility | `UTIL_ESTIMATED_READ` (WARNING) | Can approve with analyst note |
| Pittsburgh credit adjustment | Utility | `UTIL_NEGATIVE_CONSUMPTION` (ERROR) | Reject — credit adjustments are not consumption records |
| LHR→LHR travel row | Travel | `TRVL_SAME_ORIGIN_DESTINATION` (ERROR) | Cannot approve — reject |
| NYC→SYD travel row | Travel | `TRVL_CITY_CODE_NOT_AIRPORT` (WARNING) | Can approve assuming JFK |

### 4. Audit Trail
Navigate to **Audit Trail**. Every approval, rejection, and batch upload from the seed run is logged with actor, IP, timestamp, and before/after state.

---

## Resetting Demo Data

```bash
python manage.py seed_demo --reset
```

This removes all demo tenant data and recreates it fresh.
