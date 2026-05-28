# DEPLOYMENT_CHECKLIST.md

## Pre-Deploy Checklist

Work through this list before promoting to production. Each item has a rationale.

---

### Security

- [ ] **`DEBUG=false`** in all production environment variables
  - `DEBUG=true` exposes stack traces, SQL queries, and the debug toolbar to anyone with access to the API
- [ ] **`SECRET_KEY` is unique and not committed to source control**
  - Django's cryptographic signing (sessions, CSRF, JWT) depends on key secrecy. If committed, rotate immediately
- [ ] **`ALLOWED_HOSTS` contains only your production domain(s)**
  - Prevents HTTP Host header injection attacks
- [ ] **`CORS_ALLOWED_ORIGINS` contains only your frontend domain**
  - Prevents other sites from making authenticated API calls from a user's browser
- [ ] **Database password is strong and not reused**
  - Render generates this automatically; verify it's not a default
- [ ] **No credentials in `render.yaml` or any tracked file**
  - `render.yaml` uses `generateValue: true` and `fromDatabase:` references — verify no literal secrets

### Database

- [ ] **Migrations run cleanly against production database**
  - Run the Render migration job manually after first deploy; verify exit code 0 in logs
- [ ] **PostgreSQL version matches local dev** (16.x)
  - Version mismatches can cause subtle behavioral differences in JSONB operators
- [ ] **Row-Level Security (RLS) policies applied**
  - If using RLS as defense-in-depth (see `MODEL.md`), verify policies are active after migration
- [ ] **`source_file_hash` unique index exists**
  - Prevents duplicate batch uploads. Verify with `\d ingestion_ingestionbatch` in psql

### Application

- [ ] **`python manage.py migrate --noinput` succeeds with zero errors**
- [ ] **`python manage.py collectstatic --noinput` succeeds** (Dockerfile handles this, verify in build logs)
- [ ] **Health check endpoint responds 200**
  - Render uses `/api/v1/health/` — ensure this route exists and returns 200 without auth
- [ ] **File upload limit configured correctly**
  - `DATA_UPLOAD_MAX_MEMORY_SIZE=52428800` (50 MB) must match Render's request body limit
  - For large files, consider streaming to S3 rather than in-memory processing

### Frontend

- [ ] **`VITE_API_URL` points to production API URL** (not localhost)
- [ ] **Build succeeds:** `npm run build` exits 0 with no type errors
- [ ] **SPA fallback route configured** in `render.yaml` (the `rewrite: /* → /index.html` entry)
  - Without this, refreshing any non-root route returns 404

### First Deploy

- [ ] **Create initial superuser** (or use the seed script's admin user for demo)
  ```bash
  python manage.py createsuperuser
  ```
- [ ] **Run seed data** (optional for demo instances)
  ```bash
  python manage.py seed_demo
  ```
- [ ] **Verify demo login works** end-to-end through the production URL
- [ ] **Upload a sample CSV** and confirm the validation pipeline runs
- [ ] **Check the audit trail** records the upload event

### Monitoring

- [ ] **Render deploy notifications** configured (Slack or email)
- [ ] **Check Gunicorn logs** for `[ERROR]` lines after first deploy
- [ ] **Database storage usage** under 50% of provisioned size (starter = 1 GB)
  - Plan to upgrade database tier before hitting 80% storage

### Performance Baselines (record on first deploy)

| Query | Acceptable | Action if exceeded |
|---|---|---|
| `GET /dashboard/` | < 500ms | Add DB indexes or materialized views (see TRADEOFFS.md) |
| `GET /rows/?status=NEEDS_REVIEW` | < 200ms | Check `idx_raw_row_status` index exists |
| `POST /upload/` (50-row CSV) | < 2s | Acceptable; larger files may need Celery async |
| `GET /audit/` | < 300ms | Check `idx_audit_tenant_time` index exists |

---

## Post-Deploy Smoke Test

After every production deploy, run these checks manually or via a smoke test script:

```bash
# 1. Health check
curl https://breathe-esg-api.onrender.com/api/v1/health/
# Expected: {"status": "ok"}

# 2. Auth flow
TOKEN=$(curl -s -X POST https://breathe-esg-api.onrender.com/api/v1/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@acme-demo.com","password":"BreatheESG2024!"}' \
  | python3 -c "import sys, json; print(json.load(sys.stdin)['access'])")

# 3. Dashboard
curl -H "Authorization: Bearer $TOKEN" \
  https://breathe-esg-api.onrender.com/api/v1/tenants/acme-demo/dashboard/
# Expected: JSON with total_records, scope1_co2e_t, etc.

# 4. Review queue
curl -H "Authorization: Bearer $TOKEN" \
  "https://breathe-esg-api.onrender.com/api/v1/tenants/acme-demo/rows/?status=NEEDS_REVIEW"
# Expected: Paginated results with count > 0
```

---

## Rollback Procedure

Render keeps the previous deploy available. If the new deploy is broken:

1. Go to Render dashboard → breathe-esg-api → Deploys
2. Click the previous successful deploy → "Rollback to this deploy"
3. If a migration was applied, you may need to run a reverse migration manually via Render Shell

**Important:** Rollbacks do not reverse database migrations. If a migration added a column, rolling back the code will leave that column in place (harmless). If a migration dropped a column, rollback will fail — test destructive migrations carefully.
