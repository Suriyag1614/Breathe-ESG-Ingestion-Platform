# ENV.md — Environment Variable Reference

## Required in Production

| Variable | Description | Example |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string | `postgres://user:pass@host:5432/db` |
| `SECRET_KEY` | Django secret key — must be long, random, unique per environment | `openssl rand -base64 60` |
| `ALLOWED_HOSTS` | Comma-separated list of valid hostnames | `myapp.onrender.com` |
| `CORS_ALLOWED_ORIGINS` | Comma-separated frontend origins | `https://myapp.onrender.com` |

## Optional / Has Defaults

| Variable | Default | Description |
|---|---|---|
| `DEBUG` | `false` | Set `true` only in development. **Never `true` in production.** |
| `PORT` | `8000` | Port Gunicorn binds to |
| `GUNICORN_WORKERS` | `2` | Number of Gunicorn worker processes. Rule of thumb: 2× CPU cores |
| `TIME_ZONE` | `UTC` | Django timezone. Keep UTC; convert in the frontend |
| `DATA_UPLOAD_MAX_MEMORY_SIZE` | `52428800` | Max upload size in bytes (50 MB) |

## Frontend (Vite)

| Variable | Description | Example |
|---|---|---|
| `VITE_API_URL` | Full base URL for the Django API | `https://breathe-esg-api.onrender.com/api/v1` |

## Generating a SECRET_KEY

```bash
python -c "import secrets; print(secrets.token_urlsafe(60))"
# or
openssl rand -base64 60
```

## Local Development (.env)

Copy `.env.example` to `.env` and fill in values. The `.env` file is gitignored.

```bash
cp .env.example .env
```

`.env.example`:
```
DATABASE_URL=postgres://breathe:breathe_dev_password@localhost:5432/breathe_esg
SECRET_KEY=dev-only-not-secure-change-me
DEBUG=true
ALLOWED_HOSTS=localhost,127.0.0.1
CORS_ALLOWED_ORIGINS=http://localhost:5173
```

## Security Notes

- `SECRET_KEY` must be unique per environment. Never reuse dev keys in production.
- `DEBUG=true` exposes stack traces, SQL queries, and the Django debug toolbar. Never enable in production.
- `DATABASE_URL` contains credentials. Never commit it to source control.
- Render's `generateValue: true` in `render.yaml` auto-generates `SECRET_KEY` securely on first deploy.
