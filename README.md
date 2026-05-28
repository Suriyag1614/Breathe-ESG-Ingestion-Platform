# Breathe ESG — Emissions Data Ingestion Platform

A production-ready multi-tenant platform for ingesting, validating, and auditing greenhouse gas emissions data from SAP, utility, and corporate travel sources.

---

## What It Does

Breathe ESG solves the hardest part of GHG reporting: getting raw, messy source data from enterprise systems (SAP, utility portals, Concur) into a clean, auditable record that can support third-party verification.

**Core capabilities:**

- **Ingests** SAP flat-file exports (Scope 1 fuel combustion), utility CSV exports (Scope 2 electricity), and SAP Concur travel reports (Scope 3 business travel)
- **Validates** data with 20+ rule checks covering missing fields, impossible values, overlapping billing periods, invalid airport codes, and more
- **Workflows** analyst review queue where flagged rows can be approved, rejected, or edited with mandatory comments
- **Audits** every state transition — approval, rejection, edit — as an append-only event log with actor IP and timestamps
- **Multi-tenant** architecture with row-level PostgreSQL security; each tenant's data is completely isolated

---

## Quick Start (Docker)

### Prerequisites

- Docker Desktop ≥ 4.x
- Node.js ≥ 20 (for local frontend development without Docker)

### 1. Clone and configure

```bash
git clone https://github.com/your-org/breathe-esg.git
cd breathe-esg
cp .env.example .env
```

### 2. Start all services

```bash
docker compose up --build
```

This starts:
- PostgreSQL on port 5432
- Django API on http://localhost:8000
- React dev server on http://localhost:5173

### 3. Run migrations and seed demo data

```bash
docker compose run --rm web python manage.py migrate
docker compose run --rm web python manage.py seed_demo
```

### 4. Open the app

Navigate to **http://localhost:5173**

**Demo credentials:**

| Role | Email | Password |
|---|---|---|
| Admin | `admin@acme-demo.com` | `BreatheESG2024!` |
| Analyst | `analyst@acme-demo.com` | `Analyst2024!` |

---

## Architecture

```
┌──────────────────┐     HTTPS      ┌──────────────────────────┐
│  React Frontend  │ ◄────────────► │  Django REST Framework   │
│  (Vite + TS)     │                │  (DRF + SimpleJWT)       │
└──────────────────┘                └───────────┬──────────────┘
                                                │
                                    ┌───────────▼──────────────┐
                                    │      PostgreSQL 16        │
                                    │  (multi-tenant, RLS)      │
                                    └──────────────────────────┘
```

**Backend:** Django 4.2 + Django REST Framework + SimpleJWT  
**Frontend:** React 18 + TypeScript + Vite  
**Database:** PostgreSQL 16 (single schema, tenant_id on every table, RLS)  
**Auth:** JWT (access token 8h, refresh 30d with rotation)  
**Deployment:** Docker + Render (web service + static site + managed Postgres)

---

## Project Structure

```
breathe-esg/
├── breathe/                  # Django project root
│   ├── settings.py           # All config, reads from env
│   ├── urls.py               # Root URL config
│   └── wsgi.py
├── tenants/                  # User + Tenant models
│   └── models.py
├── ingestion/                # DataSource, Batch, RawRow, NormalizedRow
│   └── models.py
├── emissions/                # EmissionFactor, EmissionCalculation
│   └── models.py
├── audit/                    # AuditEvent (append-only)
│   └── models.py
├── api/                      # All DRF views, serializers, auth, urls
│   ├── views.py
│   ├── serializers.py
│   ├── auth.py
│   └── urls.py
├── validation.py             # Pure-function validation engine (no DB)
├── management/
│   └── commands/
│       └── seed_demo.py      # Demo data seed command
├── frontend/                 # React app (Vite)
│   ├── src/
│   │   ├── pages/            # DashboardPage, IngestionPage, ReviewQueuePage, AuditPage
│   │   ├── hooks/            # useAuth
│   │   ├── lib/              # api.ts (typed fetch client)
│   │   └── App.tsx
│   └── package.json
├── Dockerfile                # Multi-stage production build
├── docker-compose.yml        # Local dev stack
├── render.yaml               # Render deployment blueprint
├── requirements.txt
├── ENV.md                    # Environment variable reference
├── MODEL.md                  # Data model documentation
├── DECISIONS.md              # Architecture decision records
├── TRADEOFFS.md              # Explicit omissions with reasoning
└── SOURCES.md                # Source system research notes
```

---

## Data Sources Supported

### SAP Flat File (Scope 1)
Export from SAP transaction `MB51` or report `CKMVFM`. Expected columns match the standard MSEG/MKPF flat export. See `SOURCES.md` for parsing notes on MATNR trailing spaces, BUDAT date format, and MEINS unit mapping.

### Utility CSV (Scope 2)
Standard export from utility portals or energy management systems. The validator checks for negative consumption, estimated reads, overlapping billing periods, and unusually long periods. See `validation.py` → `validate_utility_row`.

### SAP Concur Travel (Scope 3)
Export from Concur Intelligence or Expense Report Detail report. Validates IATA airport codes, flags city codes vs. airport codes, computes great-circle distance, and checks origin ≠ destination. See `validation.py` → `validate_travel_row`.

---

## API Reference

Base URL: `/api/v1/`

### Authentication
| Method | Endpoint | Description |
|---|---|---|
| POST | `/auth/register/` | Create account |
| POST | `/auth/login/` | Get JWT token pair |
| POST | `/auth/refresh/` | Rotate access token |
| GET | `/auth/me/` | Current user |
| GET | `/auth/tenants/` | User's tenants |

### Tenant-Scoped (all require `Authorization: Bearer <token>`)
| Method | Endpoint | Description |
|---|---|---|
| GET | `/tenants/{slug}/dashboard/` | Aggregate stats |
| GET/POST | `/tenants/{slug}/sources/` | Data source config |
| GET | `/tenants/{slug}/batches/` | Ingestion batch history |
| POST | `/tenants/{slug}/upload/` | Upload CSV file |
| GET | `/tenants/{slug}/rows/` | Review queue |
| POST | `/tenants/{slug}/rows/{id}/approve/` | Approve row |
| POST | `/tenants/{slug}/rows/{id}/reject/` | Reject row |
| POST | `/tenants/{slug}/rows/bulk_approve/` | Bulk approve (up to 500) |
| POST | `/tenants/{slug}/rows/{id}/edit/` | Create new normalized version |
| POST | `/tenants/{slug}/issues/{id}/resolve/` | Resolve validation issue |
| GET | `/tenants/{slug}/audit/` | Audit trail |

---

## Deployment (Render)

1. Push to GitHub
2. In Render: New → Blueprint → connect repo → Render detects `render.yaml`
3. After first deploy, run the migration job from Render dashboard
4. Optionally seed demo data: `python manage.py seed_demo` via Render Shell

The `render.yaml` blueprint provisions:
- Django web service (Docker)
- React static site (Vite build)
- PostgreSQL 16 managed database
- Automated migration job

See `ENV.md` for all environment variables.

---

## Design Decisions

Key decisions and their rationale are in:
- `DECISIONS.md` — Architecture decision records (ADRs)
- `TRADEOFFS.md` — Explicit omissions with engineering reasoning
- `MODEL.md` — Data model with table-by-table documentation
- `SOURCES.md` — Source system research and production failure modes

---

## Running Tests

```bash
# Backend
docker compose run --rm web python manage.py test

# Frontend
docker compose run --rm frontend npm test
```

---

## License

MIT
