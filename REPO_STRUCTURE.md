# REPO_STRUCTURE.md — GitHub Repository Layout

```
breathe-esg/
│
├── .github/
│   └── workflows/
│       ├── ci.yml              # Run tests + linting on every PR
│       └── deploy.yml          # Trigger Render deploy on merge to main
│
├── breathe/                    # Django project root
│   ├── __init__.py
│   ├── settings.py             # Config from env vars
│   ├── urls.py                 # Root URL conf (includes api.urls)
│   └── wsgi.py
│
├── tenants/                    # Users, Tenants, Memberships
│   ├── __init__.py
│   ├── apps.py
│   ├── models.py               # Tenant, User, TenantMembership
│   ├── admin.py
│   └── migrations/
│
├── ingestion/                  # Data pipeline models
│   ├── __init__.py
│   ├── apps.py
│   ├── models.py               # DataSource, IngestionBatch, RawEmissionRow, NormalizedEmissionRow, ValidationIssue
│   ├── admin.py
│   └── migrations/
│
├── emissions/                  # Emission factors and calculations
│   ├── __init__.py
│   ├── apps.py
│   ├── models.py               # EmissionFactor, EmissionCalculation
│   ├── admin.py
│   └── migrations/
│
├── audit/                      # Audit trail
│   ├── __init__.py
│   ├── apps.py
│   ├── models.py               # AuditEvent (append-only)
│   ├── admin.py
│   └── migrations/
│
├── api/                        # DRF API layer
│   ├── __init__.py
│   ├── apps.py
│   ├── auth.py                 # TenantFromSlugMixin, permission classes, JWT helpers
│   ├── exceptions.py           # Custom exception handler
│   ├── serializers.py          # All serializers
│   ├── urls.py                 # All URL patterns
│   └── views.py                # All views and viewsets
│
├── management/
│   └── commands/
│       └── seed_demo.py        # Demo data seed command
│
├── validation.py               # Pure-function validation engine (no Django imports)
│
├── frontend/                   # React app
│   ├── public/
│   ├── src/
│   │   ├── components/
│   │   │   └── AppShell.tsx    # Sidebar + layout wrapper
│   │   ├── hooks/
│   │   │   └── useAuth.tsx     # Auth context + JWT management
│   │   ├── lib/
│   │   │   └── api.ts          # Typed fetch client + all API calls
│   │   ├── pages/
│   │   │   ├── DashboardPage.tsx
│   │   │   ├── IngestionPage.tsx
│   │   │   ├── ReviewQueuePage.tsx
│   │   │   ├── AuditPage.tsx
│   │   │   ├── SourcesPage.tsx
│   │   │   ├── LoginPage.tsx
│   │   │   └── RegisterPage.tsx
│   │   ├── App.tsx             # Router + PrivateRoute
│   │   ├── main.tsx
│   │   └── index.css           # Global dark theme styles
│   ├── index.html
│   ├── package.json
│   ├── tsconfig.json
│   └── vite.config.ts
│
├── sample_data/                # Sample CSV files for demo and testing
│   ├── sap_fuel_q1_2024.csv
│   ├── utility_electricity_q1_2024.csv
│   ├── travel_concur_q1_2024.csv
│   └── sap_fuel_sample_annotated.txt
│
├── docs/                       # Design documentation
│   ├── MODEL.md                # Data model reference
│   ├── DECISIONS.md            # Architecture decision records
│   ├── TRADEOFFS.md            # Deliberate omissions
│   └── SOURCES.md              # Source system research
│
├── .env.example                # Environment variable template
├── .gitignore
├── Dockerfile                  # Multi-stage production build
├── docker-compose.yml          # Local dev stack (Postgres + Django + Vite)
├── render.yaml                 # Render deployment blueprint
├── requirements.txt            # Python dependencies (pinned)
├── manage.py
├── README.md                   # Setup, quickstart, API reference
├── ENV.md                      # Environment variable documentation
└── DEMO.md                     # Demo credentials and walkthrough
```

## .gitignore (key entries)

```gitignore
# Python
__pycache__/
*.py[cod]
*.egg-info/
.venv/
venv/

# Django
*.sqlite3
/media/
/staticfiles/

# Environment
.env
.env.local
.env.*.local

# Node
node_modules/
frontend/dist/
frontend/.vite/

# OS
.DS_Store
Thumbs.db

# IDE
.vscode/
.idea/
*.swp
```

## CI Workflow (.github/workflows/ci.yml)

```yaml
name: CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  backend:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_DB: breathe_test
          POSTGRES_USER: breathe
          POSTGRES_PASSWORD: test
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r requirements.txt
      - name: Run migrations
        env:
          DATABASE_URL: postgres://breathe:test@localhost:5432/breathe_test
          SECRET_KEY: ci-test-secret-key
          DEBUG: "true"
        run: python manage.py migrate
      - name: Run tests
        env:
          DATABASE_URL: postgres://breathe:test@localhost:5432/breathe_test
          SECRET_KEY: ci-test-secret-key
          DEBUG: "true"
        run: python manage.py test

  frontend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - run: npm ci
      - run: npm run build
      - run: npm test -- --run
```
