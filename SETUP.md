# SETUP.md — Local Development Setup

## Final Repository Structure

```
breathe-esg/
│
├── breathe/
│   ├── __init__.py          ← REQUIRED (new)
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
│
├── tenants/
│   ├── __init__.py          ← REQUIRED (new)
│   ├── apps.py
│   ├── models.py
│   ├── admin.py
│   └── migrations/
│       └── __init__.py      ← REQUIRED (new)
│
├── ingestion/
│   ├── __init__.py          ← REQUIRED (new)
│   ├── apps.py
│   ├── models.py
│   ├── admin.py
│   └── migrations/
│       └── __init__.py      ← REQUIRED (new)
│
├── emissions/               ← COMPLETE (new)
│   ├── __init__.py
│   ├── apps.py
│   ├── models.py
│   ├── admin.py
│   └── migrations/
│       └── __init__.py
│
├── audit/
│   ├── __init__.py          ← REQUIRED (new)
│   ├── apps.py
│   ├── models.py
│   ├── admin.py
│   └── migrations/
│       └── __init__.py      ← REQUIRED (new)
│
├── api/
│   ├── __init__.py          ← REQUIRED (new)
│   ├── apps.py
│   ├── auth.py
│   ├── exceptions.py
│   ├── serializers.py
│   ├── urls.py
│   └── views.py
│
├── management/
│   ├── __init__.py          ← REQUIRED (new)
│   └── commands/
│       ├── __init__.py      ← REQUIRED (new)
│       └── seed_demo.py
│
├── validation.py
├── manage.py
├── requirements.txt
├── Dockerfile               ← FIXED (exec CMD)
├── docker-compose.yml
├── render.yaml
├── .env.example
├── .gitignore               ← NEW
│
├── frontend/
│   ├── .env                 ← NEW (VITE_API_URL)
│   ├── .env.example
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── tsconfig.node.json
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── index.css
│       ├── components/
│       │   └── AppShell.tsx
│       ├── hooks/
│       │   └── useAuth.tsx
│       ├── lib/
│       │   └── api.ts
│       └── pages/
│           ├── DashboardPage.tsx
│           ├── IngestionPage.tsx
│           ├── ReviewQueuePage.tsx
│           ├── AuditPage.tsx
│           ├── SourcesPage.tsx
│           ├── LoginPage.tsx
│           └── RegisterPage.tsx
│
└── sample_data/
    ├── sap_fuel_q1_2024.csv
    ├── utility_electricity_q1_2024.csv
    └── travel_concur_q1_2024.csv
```

---

## PowerShell — Backend Setup

```powershell
# 1. Create and activate virtual environment
cd breathe-esg
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Copy env file
Copy-Item .env.example .env
# Edit .env if needed — SQLite is the default (no Postgres required locally)

# 4. Run migrations
python manage.py migrate

# 5. Seed demo data
python manage.py seed_demo

# 6. Start Django dev server
python manage.py runserver 8000
```

---

## PowerShell — Frontend Setup

```powershell
# In a NEW terminal window:
cd breathe-esg\frontend

# 1. Install Node dependencies
npm install

# 2. Start Vite dev server
npm run dev
```

---

## Expected URLs after startup

| Service       | URL                          |
|---------------|------------------------------|
| Frontend (Vite) | http://localhost:5173       |
| Backend API   | http://localhost:8000/api/v1 |
| Health check  | http://localhost:8000/api/v1/health/ |
| Django Admin  | http://localhost:8000/admin/ |

---

## Demo Login Credentials

| Role    | Email                    | Password        |
|---------|--------------------------|-----------------|
| Admin   | admin@acme-demo.com      | BreatheESG2024! |
| Analyst | analyst@acme-demo.com    | Analyst2024!    |

---

## Docker Compose (alternative to manual setup)

```powershell
# From project root
docker compose up --build

# In a second terminal, run migrations + seed
docker compose run --rm web python manage.py migrate
docker compose run --rm web python manage.py seed_demo
```

Then open: http://localhost:5173

---

## Verify backend is working

```powershell
# Health check (no auth required)
Invoke-WebRequest http://localhost:8000/api/v1/health/ | Select-Object -ExpandProperty Content
# Expected: {"status": "ok"}

# Login
$body = '{"email":"admin@acme-demo.com","password":"BreatheESG2024!"}'
$resp = Invoke-RestMethod -Method POST `
  -Uri http://localhost:8000/api/v1/auth/login/ `
  -ContentType "application/json" `
  -Body $body
$token = $resp.access

# Dashboard
Invoke-RestMethod -Uri http://localhost:8000/api/v1/tenants/acme-demo/dashboard/ `
  -Headers @{ Authorization = "Bearer $token" }
```
