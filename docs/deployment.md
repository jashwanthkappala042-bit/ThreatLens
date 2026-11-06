# Deploying ThreatLens

This is the deployment guide for the exact repository layout:

| Piece | Host | What it runs |
| --- | --- | --- |
| API | **Render** (native Python web service) | Flask via gunicorn, `backend/wsgi.py` |
| Web app | **Vercel** (static Vite build) | `frontend/dist` |
| Database | **Neon / Supabase / Render Postgres** | PostgreSQL via `DATABASE_URL` |

Deploy the **backend first**. The frontend needs the backend's public URL, and
the backend needs the frontend's public URL for CORS. You will update Render's
`CORS_ORIGINS` once Vercel gives you a domain.

---

## 1. Can I keep SQLite?

**Not for a hosted deployment.** SQLite itself is fine software, but Render's
web-service filesystem is **ephemeral**:

- every deploy, restart or crash starts from the Git checkout again;
- the free plan cannot attach a persistent disk;
- the free instance spins down after 15 minutes of inactivity and wakes with a
  fresh filesystem.

So `backend/instance/threatlens.db` would disappear, taking accounts, scans,
community posts and complaint rows with it. The app would still boot (tables are
recreated), but data would silently vanish. That is not a deployment bug you can
fix with configuration; it is the storage model.

**Recommendation: managed PostgreSQL.** The code already supports it —
`app/database.py` reads `DATABASE_URL` and only applies SQLite pragmas when the
URL starts with `sqlite`. `render.yaml` normalises the legacy `postgres://`
scheme to `postgresql://`, and uses `pool_pre_ping` + `pool_recycle=280` because
hosted Postgres closes idle connections.

### Database options

| Option | Free tier | Good for | Caveats |
| --- | --- | --- | --- |
| **Neon** (recommended) | Yes | This app; serverless Postgres, scales to zero | Cold queries after long idle; copy the **pooled** connection string |
| **Supabase** | Yes | Postgres + extras (auth/storage) you do not need yet | Free projects pause after a week of inactivity |
| **Render Postgres** | Yes, but **expires after 30 days** | One-vendor setup | Free database is deleted after 30 days; paid plan needed for permanence |
| **Railway / Aiven / ElephantSQL-style** | Varies | Alternative managed Postgres | Check current free limits |
| **VPS + SQLite on a real disk** | No | Maximum control, cheapest long-term | You run OS updates, backups, TLS and process supervision |
| **SQLite on Render** | N/A | A disposable demo only | All data lost on deploy/spin-down; no disk on free |

### Neon setup (5 minutes)

1. Sign in at <https://neon.tech> and create a project (pick the region closest
   to your Render region).
2. Open **Connect** and copy the connection string. Prefer the **pooled** host
   (it contains `-pooler`).
3. Append `?sslmode=require` if it is not already present. The final value looks
   like:

   ```
   postgresql://neondb_owner:PASSWORD@ep-xxx-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require
   ```

4. Paste it into Render as `DATABASE_URL` (see below). Do not commit it.

Tables are created automatically on first boot (`AUTO_INIT_DB=true` →
`Base.metadata.create_all`). There are no migration files, so schema changes in
future code would need manual SQL or a migration tool. Existing local SQLite
data is **not** copied automatically; create a fresh account after switching.

---

## 2. Pre-deployment checklist

Everything below is already present in this repository. The "why" column is
what breaks without it.

| Requirement | File / setting | Why |
| --- | --- | --- |
| WSGI entry point | `backend/wsgi.py` → `wsgi:app` | `python run.py` is a dev server; gunicorn needs an importable app |
| Production server | `gunicorn` in `backend/requirements.txt` | Render does not run Flask's dev server |
| Python version pin | `render.yaml` `PYTHON_VERSION=3.14.10`, plus `.python-version` files | Artifacts were trained on Python 3.14 / scikit-learn 1.9.1 |
| ML version pins | `backend/requirements.txt` | Unpickling a different scikit-learn version can fail or change results |
| Postgres driver | `psycopg2-binary` | Required by `postgresql://` URLs |
| SPA rewrite | `frontend/vercel.json` | Without it, `/dashboard` 404s on refresh/direct link |
| API base URL | `VITE_API_BASE` in Vercel | Without it the site calls its own domain and every request fails |
| CORS | `CORS_ORIGINS` in Render | Browser blocks the Vercel origin otherwise |
| Secrets | `SECRET_KEY`, `JWT_SECRET_KEY` | Defaults are development-only |
| Request timeout | gunicorn `--timeout 120`, axios 75–90 s | Free Render cold starts can take ~1 minute |
| Single worker | `--workers 1 --threads 4` | In-process rate limiter + one copy of ML models |

Repository size is not a problem for either host:

| What | Size |
| --- | --- |
| Everything Git tracks | **12.7 MB**, 114 files |
| ML artifacts | 11.85 MB (`email` 9.45 MB, `sms` 2.12 MB, `url` 0.28 MB) |
| `.git` history | 12.2 MB |
| Working tree (ignored dirs included) | ~1.08 GB — `.venv` 491 MB, datasets 456 MB, `node_modules` 112 MB |

The large directories are all in `.gitignore`; neither host clones them.

---

## 3. Deploy the backend on Render

### Option A — Blueprint (recommended)

1. Push the repository to GitHub/GitLab.
2. In Render: **New → Blueprint**, connect the repo. Render reads
   `render.yaml`.
3. It prompts for the two `sync: false` values:
   - `DATABASE_URL` - your Neon string. **Do not leave this blank**: an empty
     value falls back to SQLite, which is wiped on the next deploy or spin-down.
   - `CORS_ORIGINS` - for now enter `http://localhost:5173`. You will replace
     this after Vercel is live.
4. Apply. Wait for the build (`pip install` compiles nothing, but the ML wheels
   take a few minutes on first deploy).
5. Open the service URL + `/api/health`.

`render.yaml` sets:

| Setting | Value |
| --- | --- |
| Root directory | `backend` |
| Build | `pip install --upgrade pip && pip install -r requirements.txt` |
| Start | `gunicorn --workers 1 --threads 4 --timeout 120 --bind 0.0.0.0:$PORT wsgi:app` |
| Health check | `/api/health` |
| Plan | `free` |
| Python | `3.14.10` |

### Option B — Manual web service

If you prefer not to use a Blueprint:

1. **New → Web Service** → connect the repo.
2. **Root Directory**: `backend`
3. **Runtime**: Python 3
4. **Build Command**: `pip install --upgrade pip && pip install -r requirements.txt`
5. **Start Command**: `gunicorn --workers 1 --threads 4 --timeout 120 --bind 0.0.0.0:$PORT wsgi:app`
6. **Health Check Path**: `/api/health`
7. Add environment variables:

| Key | Required | Value |
| --- | --- | --- |
| `PYTHON_VERSION` | Yes | `3.14.10` |
| `SECRET_KEY` | Yes | long random string |
| `JWT_SECRET_KEY` | Yes | a different long random string |
| `DATABASE_URL` | Yes | Neon/Supabase/Render Postgres URL with `sslmode=require` |
| `CORS_ORIGINS` | Yes | `https://your-app.vercel.app` (comma-separate preview URLs too) |
| `FLASK_ENV` | No | `production` |
| `FLASK_DEBUG` | No | `false` |
| `AUTO_INIT_DB` | No | `true` (default) |
| `ENABLE_BROWSER_SCAN` | No | leave `false` on free (Playwright is not installed) |
| `ENABLE_OCR` | No | leave `false` (EasyOCR is not installed) |

Generate secrets locally:

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

Run it twice; use one value per secret. Never commit them.

### Verify the backend

```powershell
$api = "https://your-service-name.onrender.com"
Invoke-RestMethod "$api/api/health" | ConvertTo-Json -Depth 6
```

Expected: `success = true`, `database.ok = true`, and `capabilities.local_models`
showing the three models as available. If a model is missing, the scan still
works but that ML stage reports `unavailable` — it never fabricates a score.

```powershell
# Register and scan (anonymous scans also work)
$body = @{ email = "you@example.com"; password = "CorrectHorseBattery9!"; display_name = "You" } | ConvertTo-Json
Invoke-RestMethod -Method Post "$api/api/auth/register" -ContentType "application/json" -Body $body

$scan = @{ url = "https://example.com/login" } | ConvertTo-Json
Invoke-RestMethod -Method Post "$api/api/scan/url" -ContentType "application/json" -Body $scan
```

---

## 4. Deploy the frontend on Vercel

1. In Vercel: **Add New → Project**, import the same repository.
2. Set **Root Directory** to `frontend`.
3. Framework preset: **Vite** (Vercel should detect it).
4. Build settings (also encoded in `frontend/vercel.json`):
   - Install: `npm ci`
   - Build: `npm run build`
   - Output: `dist`
5. Add an environment variable **before the first deploy**:

   | Key | Value |
   | --- | --- |
   | `VITE_API_BASE` | `https://your-service-name.onrender.com` (no trailing slash) |

   Apply it to Production, Preview and Development if you want previews to
   work.
6. Deploy. Copy the production domain (for example
   `https://threatlens.vercel.app`).
7. Return to Render → Environment → set:

   ```
   CORS_ORIGINS=https://threatlens.vercel.app
   ```

   Add preview domains too if you use them, comma-separated, for example:

   ```
   CORS_ORIGINS=https://threatlens.vercel.app,https://threatlens-git-main-you.vercel.app
   ```

   Save; Render restarts the service automatically.
8. Open the Vercel URL, register an account and run a URL scan.

### Why the SPA rewrite matters

`frontend/vercel.json` rewrites unknown paths to `/index.html`. Without it, a
direct visit or refresh on `/dashboard`, `/history` or `/results/<id>` returns
Vercel's 404 instead of letting React Router handle the route.

### `VITE_API_BASE` is baked in

Vite replaces `import.meta.env.VITE_API_BASE` at build time. Changing the
variable in the Vercel dashboard does **nothing** until you trigger a new
deployment. If you later rename or recreate the Render service, update the
variable and redeploy the frontend.

---

## 5. Free-tier behaviour (important)

| Behaviour | Effect on ThreatLens |
| --- | --- |
| Render free spins down after 15 min idle | First request can take ~1 minute. The UI timeout is 75 s (90 s for images). Subsequent requests are fast. |
| 512 MB RAM / 0.1 CPU | All three models loaded measured ~309 MB RSS locally, before the web server. Light use fits; concurrent scans are slow and can OOM. Use the Starter plan (2 GB) for regular use. |
| Ephemeral disk | SQLite is out. Complaint PDFs written to `backend/storage/complaints` disappear on restart, so an old complaint's PDF can return 404 while its database row remains. Scans and accounts are safe in Postgres. |
| Single gunicorn worker | Rate limits are per-worker and reset on restart. Fine for a demo; not a distributed limiter. |
| 750 free instance-hours | One always-on free service consumes ~730 hours/month. If it sleeps, it consumes less. |
| Render free Postgres expires | Do not use it for data you want to keep beyond 30 days. Neon avoids this. |

### Reduce memory on the free plan

The email model is the largest (~130–150 MB resident). If you only demo URL
scanning, point `EMAIL_MODEL_PATH` and `SMS_MODEL_PATH` at paths that do not
exist; the scanner falls back to heuristics and reports ML as unavailable. For
full functionality, use Render Starter.

---

## 6. Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| Build fails: `No module named app` / `wsgi` | Wrong root directory | Set Render **Root Directory** to `backend`; start command must be `wsgi:app` |
| Build fails on `scikit-learn==1.9.1` or `psycopg2` | Unsupported Python or no wheel | Keep `PYTHON_VERSION=3.14.10`; both packages publish cp314 Linux wheels |
| Deploy succeeds, requests hang and 502 | Out of memory during model load, or cold start | Retry once; check Render logs; move to Starter or disable the email model |
| `local_models` shows unavailable | Artifact missing or incompatible | Artifacts are committed under `ml/models`; do not add them to `.gitignore`. Check the Render log for the exact joblib error |
| Login/registration works, then data disappears after deploy | SQLite on ephemeral disk | Set `DATABASE_URL` to Postgres |
| `could not translate host name` / SSL error | Bad URL or missing TLS | Copy the Neon pooled string, include `?sslmode=require` |
| Browser console: CORS policy blocks request | Origin not listed | Put the exact Vercel origin (scheme + host, no trailing slash) in `CORS_ORIGINS`; save and let Render restart |
| Site loads but every API call fails | `VITE_API_BASE` unset or set after build | Set it in Vercel and **redeploy** |
| Refresh on `/dashboard` gives 404 | SPA rewrite missing | Ensure Vercel root directory is `frontend` so `vercel.json` is used |
| `413 payload_too_large` | Upload over `MAX_CONTENT_LENGTH` (6 MB) | Raise it in Render env vars or upload a smaller image |
| `429 rate_limited` | Per-IP limits (scan 20/min) | Wait a minute; raise `RATE_LIMIT_SCAN` if this is a demo |
| Complaint PDF returns 404 after a deploy | File lived on ephemeral disk | Regenerate the complaint; move PDFs to object storage if this must persist |
| `token_expired` after an hour | Default JWT lifetime | Sign in again, or raise `JWT_ACCESS_TOKEN_EXPIRES` |

---

## 7. Deployment options and cost

| Option | Monthly cost | Pros | Cons |
| --- | --- | --- | --- |
| **Render free + Neon free + Vercel free** | $0 | Free tiers; Blueprint is committed; good for a demo/college submission | Cold starts, 512 MB, no persistent disk, free DB limits |
| **Render Starter + Neon free + Vercel free** | ~$7 | No spin-down, 2 GB RAM, full ML comfortably | Paid backend |
| **Render Starter + Render Postgres** | ~$14 | One dashboard/bill | More expensive than Neon |
| **Railway** (backend + Postgres) | Usage-based, ~$5+ | Simple, supports persistent volumes | Not free long-term; still needs CORS/Vercel setup |
| **Fly.io** | Usage-based, small free allowance | Global regions, volumes for SQLite | Requires a Dockerfile; more moving parts |
| **VPS** (Hetzner/DigitalOcean) + Nginx/Caddy | ~$4–6 | SQLite on a real disk, full control, no cold starts | You handle TLS, updates, backups, uptime |
| **Docker on any container host** | Varies | Reproducible | No Dockerfile is committed; Render's native Python runtime is simpler |

For this project the lowest-risk free setup is:

```
Vercel (static)  ->  Render free (Flask + gunicorn)  ->  Neon free (Postgres)
```

If you need reliable response times or full ML under load, change only the
Render plan to Starter.

---

## 8. What is still local-only

- `backend/storage/complaints` and generated PDFs: local/ephemeral.
- The downloaded datasets (`ml/datasets`, 456 MB) are intentionally not in Git;
  only the three trained artifacts are.
- Browser rendering and OCR remain disabled unless you install Playwright /
  EasyOCR and enable the flags. They are not part of the Render build.
- Rate limiting is in-process, and scans run synchronously inside the request.
- Nothing is submitted to any authority; complaint PDFs are drafts.
