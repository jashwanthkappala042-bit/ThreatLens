# ThreatLens

**See the threat before you click.**

ThreatLens is a local, full-stack phishing and cyber-threat analysis app. It accepts a URL, an email/message, or an image (screenshot, QR code or photo), runs explainable heuristic analysis, and shows the evidence behind every result. Community reports, complaint-draft PDFs and scan-report PDFs are included.

> ThreatLens is an educational local analysis tool, not a security product or an authority. Scores are **heuristic and uncalibrated**. A low score is **not a guarantee of safety**, and no result is submitted anywhere automatically.

---

## What is implemented

### Analysis

- **URL scanner** — syntax/normalisation checks, DNS resolution, static URL features (punycode, brand impersonation, suspicious keywords and extensions, entropy, structural quirks), bounded HTTP fetch with per-hop redirect validation, and HTML analysis (forms, password fields, external form actions, iframes, scripts, hidden inputs).
- **Email/message scanner** — urgency, threats, credential requests, payment lures, impersonation, obfuscation and formatting heuristics, plus analysis of up to three extracted URLs.
- **Image scanner** — file-signature and pixel validation, QR decoding with OpenCV (optional pyzbar fallback), optional EasyOCR text extraction, and URL analysis of decoded content. Images are never stored.
- **Explainable risk engine** — category grouping, diminishing returns, capped score, conservative floors, thresholds, a decision trace, and explicit limitations. Missing evidence produces `unknown`/inconclusive, never a fabricated “safe”.
- **Optional local ML** — three locally trained classifiers (static-feature URL, binary email, three-class SMS) load only from artifacts produced by `ml/`. **No dataset or model artifact is committed to the repository**; when an artifact is missing the ML stage reports itself as unavailable.

### Accounts and workspace

- Register/login with JWT access tokens; local accounts only.
- Anonymous scans are allowed; signing in saves scans to a history and dashboard.
- Scan history with filtering, search, deletion and access control.
- Dashboard with verdict counts, average score, 14-day activity, indicator categories and recent scans.
- Scan-report PDFs generated from the actual stored analysis.
- Complaint **draft** PDF generation (explicitly marked DRAFT, never submitted).

### Community and administration

- Community feed, posts, comments and reports.
- Community content is labelled unverified and is not independently analyzed by ThreatLens.
- Shared URLs are rendered as plain text, not clickable links.
- Reporting, automatic flagging after a configurable report threshold, an admin moderation queue, remove/restore, and report resolve/dismiss.
- Admin promotion through a local CLI script.

### Interface

- React SPA with dark (default) and light themes.
- Unified scanner (no separate scanner routes) with drag/drop, file picker and clipboard paste.
- Result tabs: Overview, Findings, Evidence, Decision trace, Limitations.
- Responsive SOC-style layout with a custom shield/lens SVG logo.
- Safe rendering: no raw HTML injection of untrusted content.

---

## Tech stack

| Layer | Technology |
| --- | --- |
| Frontend | React 19, JavaScript, Vite 6, React Router 7, Tailwind CSS 3, Axios, Lucide, Recharts |
| Backend | Python, Flask 3, Flask-JWT-Extended, Flask-CORS, SQLAlchemy 2 |
| Database | SQLite (local file; `DATABASE_URL` configurable) |
| Analysis | Requests, BeautifulSoup, Pillow, OpenCV, optional Playwright/pyzbar/EasyOCR |
| ML (optional) | scikit-learn, Pandas, NumPy, TF-IDF, Logistic Regression, Linear SVM, Random Forest, HistGradientBoosting, ComplementNB |
| PDF | ReportLab |
| Tests | pytest |

Tested locally with Python 3.14 and Node 24. Python 3.11+ and Node 20+ are the intended minimums.

---

## Project structure

```
threatlens/
  backend/
    app/
      routes/        auth, scans/history, dashboard, community, complaints, profile
      scanners/      URL, email, image, HTML, bounded HTTP, optional browser
      detection/     findings, URL features, email heuristics, ML loader, risk engine
      services/      scan orchestration, PDF generation
      utils/         URL safety, text helpers
      models.py      SQLAlchemy models
    tests/           82 backend tests
    scripts/         make_admin.py
    storage/         generated complaint PDFs (local, gitignored)
    run.py
  frontend/
    src/
      components/    layout, guards, cards, badges, modals, evidence renderer
      context/       auth, theme, toast
      lib/           API client, formatting helpers
      pages/         landing, auth, scanner, results, dashboard, history,
                     community, moderation, complaints, profile, about, 404
  ml/                dataset downloader and reproducible training benchmarks
                     (datasets, artifacts and logs are gitignored)
  docs/              architecture, API, security and limitations references
  .env.example
```

See [`docs/architecture.md`](docs/architecture.md) for the request flow, data model and design trade-offs.

---

## Setup

### 1. Backend

From the project root (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
Copy-Item .env.example .env
```

Edit `.env` and set strong values for `SECRET_KEY` and `JWT_SECRET_KEY`. Generate them with:

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

Start the API:

```powershell
.\.venv\Scripts\python.exe backend\run.py
```

The API listens on `http://127.0.0.1:5000` by default. Tables are created automatically on first start (`AUTO_INIT_DB=true`). The SQLite file defaults to `backend/instance/threatlens.db`.

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:5000/api/health
```

### 2. Frontend

In a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173`. Vite proxies `/api` to `http://127.0.0.1:5000`, so no frontend API URL is required during development.

### 3. Admin user (optional)

Register normally in the UI, then promote the account:

```powershell
.\.venv\Scripts\python.exe backend\scripts\make_admin.py --list
.\.venv\Scripts\python.exe backend\scripts\make_admin.py you@example.com
```

The moderation queue is available under **Moderation** after signing in as an admin.

### Production build

```powershell
cd frontend
npm run build
npm run preview
```

The build output is `frontend/dist`. The Flask backend does not serve the frontend bundle; use a static host or reverse proxy if you wire them together. This project is configured for local use only.

---

## Configuration

All backend settings are environment variables. See [`.env.example`](.env.example) for the full annotated list. Key values:

| Variable | Default | Purpose |
| --- | --- | --- |
| `SECRET_KEY` / `JWT_SECRET_KEY` | development placeholders | Signing keys; replace before any non-local use |
| `JWT_ACCESS_TOKEN_EXPIRES` | `3600` | Token lifetime in seconds |
| `DATABASE_URL` | `backend/instance/threatlens.db` | SQLAlchemy database URL |
| `STORAGE_DIR` | `backend/storage` | Complaint PDF storage |
| `CORS_ORIGINS` | local Vite origins | Allowed browser origins |
| `MAX_IMAGE_BYTES` / `MAX_IMAGE_PIXELS` | 5 MB / 25 MP | Upload limits |
| `MAX_TEXT_CHARS` | 20,000 | Email/message text limit |
| `HTTP_CONNECT_TIMEOUT` / `HTTP_READ_TIMEOUT` | 4 s / 8 s | Outbound request bounds |
| `MAX_REDIRECTS` / `MAX_RESPONSE_BYTES` | 5 / 2 MB | Redirect and response bounds |
| `RATE_LIMIT_*` | 10–20 per minute | In-process request limits |
| `ENABLE_BROWSER_SCAN` | `false` | Optional Playwright analysis |
| `ENABLE_OCR` | `false` | Optional EasyOCR text extraction |
| `SMS_MAX_CHARS` | `700` | Body-only messages at or below this length use the 3-class SMS model |
| `ALLOW_PRIVATE_NETWORK_TARGETS` | `false` | **Tests only**; defeats SSRF protection |

Optional capabilities are disabled by default. Enabling a flag does not install its dependency, and `ENABLE_EXTERNAL_REPUTATION` has no provider wired up in this build.

### Optional dependencies

```powershell
# OCR (downloads model weights on first use)
.\.venv\Scripts\python.exe -m pip install easyocr

# Isolated Chromium rendering
.\.venv\Scripts\python.exe -m pip install playwright
.\.venv\Scripts\python.exe -m playwright install chromium
```

Then set `ENABLE_OCR=true` and/or `ENABLE_BROWSER_SCAN=true` in `.env`. Review the resource and isolation implications before enabling either.

### Optional ML

Three optional classifiers are trained from public, licensed corpora. Datasets,
artifacts and training logs are gitignored; no model ships with the repository.

```powershell
# 1. Download the datasets (CC BY 4.0) and write SHA-256 checksums.
.\.venv\Scripts\python.exe ml\download_datasets.py

# 2. Reproducible benchmarks; the best deployable model is saved per task.
.\.venv\Scripts\python.exe ml\train_url_models.py
.\.venv\Scripts\python.exe ml\train_email_models.py
.\.venv\Scripts\python.exe ml\train_sms_models.py
```

Outputs:

- `ml/models/url_model.joblib` — static-URL-feature model (no network fetch)
- `ml/models/email_model.joblib` — TF-IDF text pipeline
- `ml/models/sms_model.joblib` — three-class `ham`/`spam`/`smishing` pipeline
- `ml/reports/*_comparison.json` — every compared model, split sizes and metrics

The app also accepts your own CSV through the simpler
`ml/train_email_model.py` and `ml/train_url_model.py` scripts
(`--data`, `--dataset-name`, `--dataset-license`). Read
[`ml/README.md`](ml/README.md) for schemas, the evaluation protocol, measured
results and limitations. Metrics describe one held-out split, not real-world
detection rates, and the scores are not calibrated probabilities.

---

## API summary

All JSON responses use one envelope:

```json
{ "success": true, "data": { }, "meta": { } }
```

```json
{ "success": false, "error": { "code": "invalid_url", "message": "…" } }
```

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| `GET` | `/api/health` | No | Service, database and capability status |
| `POST` | `/api/auth/register` | No | Create an account and receive a token |
| `POST` | `/api/auth/login` | No | Sign in |
| `GET` | `/api/auth/me` | Yes | Current user |
| `POST` | `/api/auth/logout` | Optional | Audit-only logout; client discards the token |
| `POST` | `/api/scan/url` | Optional | Analyze a URL |
| `POST` | `/api/scan/email` | Optional | Analyze an email/message |
| `POST` | `/api/scan/image` | Optional | Analyze an uploaded image |
| `GET` | `/api/analysis/<scan_id>` | Optional | Full stored analysis |
| `GET` | `/api/scan/<scan_id>/status` | Optional | Scan status (synchronous scans complete before return) |
| `GET` | `/api/scan/<scan_id>/report.pdf` | Optional | Download the scan report |
| `GET` | `/api/history` | Yes | Paginated scan history |
| `DELETE` | `/api/history/<scan_id>` | Yes | Delete an owned scan |
| `GET` | `/api/dashboard/stats` | Yes | Verdict counts and averages |
| `GET` | `/api/dashboard/activity` | Yes | 14-day scan activity |
| `GET` | `/api/dashboard/categories` | Yes | Indicator category counts |
| `GET` | `/api/dashboard/overview` | Yes | Recent scans and community posts |
| `GET` | `/api/community/posts` | No | Community feed |
| `POST` | `/api/community/posts` | Yes | Create a post |
| `GET` | `/api/community/posts/<id>` | No | Post detail and comments |
| `POST` | `/api/community/posts/<id>/comments` | Yes | Add a comment |
| `POST` | `/api/community/posts/<id>/report` | Yes | Report a post |
| `DELETE` | `/api/community/posts/<id>` | Yes | Delete an owned post (admin: any) |
| `GET` | `/api/community/moderation/reports` | Admin | Open reports |
| `PATCH` | `/api/community/posts/<id>/moderation` | Admin | Remove or restore a post |
| `PATCH` | `/api/community/reports/<id>` | Admin | Resolve or dismiss a report |
| `POST` | `/api/complaints/generate` | Yes | Generate a local DRAFT PDF |
| `GET` | `/api/complaints` | Yes | List owned drafts |
| `GET` | `/api/complaints/<id>` | Yes | Draft details |
| `GET` | `/api/complaints/<id>/pdf` | Yes | Download a draft PDF |
| `GET` | `/api/profile` | Yes | Profile and counts |
| `PATCH` | `/api/profile` | Yes | Update display name/password |

Full request/response details are in [`docs/api.md`](docs/api.md).

**Scan access rule:** anonymous scans (`user_id = NULL`) can be read by anyone who knows the UUID. Scans saved to an account are readable only by their owner or an admin. Treat scan links as sensitive.

Rate limits are per-IP, in-process, sliding-window: auth 10/min, scans 20/min, community 20/min, complaints 10/min. They reset when the process restarts and are not shared across workers.

---

## Testing and verification

Backend suite:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q
```

Recorded result for this build:

```
73 passed in 29.09s
```

Frontend production build:

```powershell
cd frontend
npm run build
```

Recorded result: build succeeded (948.41 kB JS, 270.97 kB gzip; Vite emits a chunk-size warning only). No frontend unit/e2e test suite is included.

Manual browser smoke checks performed on this build covered: landing page, registration/login, theme switching, signed-in and anonymous URL scans, email scan, QR/image scan, all result tabs, dashboard charts, history, community post/share/detail, moderation queue, complaint prefill/generation/download, profile update, and scan-report PDF download. There is no automated browser test suite in the repository.

---

## Security and limitations

ThreatLens blocks private/loopback/link-local targets by default, revalidates every redirect hop, bounds timeouts and response sizes, does not forward credentials or arbitrary headers, and never persists uploaded images. Access control, rate limiting, input validation, safe rendering and audit logging are implemented.

It is still a local development app. The important residuals:

- The JWT is stored in `localStorage`, so an XSS flaw would expose it. A strict CSP and httpOnly cookies would be stronger.
- The in-process rate limiter is per-worker and resets on restart.
- Scans are synchronous, not queued.
- Heuristic scores are uncalibrated and can produce false positives and false negatives.
- There is no external reputation/threat-intelligence provider and no malware sandbox.
- Browser analysis and OCR are optional and disabled by default.
- Community reports are unverified user content, not findings by ThreatLens.
- Complaint PDFs are drafts for the user to review and file themselves. **Nothing is submitted to cybercrime.gov.in or any authority.**

Read [`docs/security.md`](docs/security.md) and [`docs/limitations.md`](docs/limitations.md) before relying on any result. For cybercrime in India, the official portal is <https://cybercrime.gov.in/>. ThreatLens is not affiliated with it.

---

## Privacy

- Scanned images are processed in memory and not stored. Metadata, extracted text, decoded URLs and findings are stored.
- Scan text, URLs, findings and community content are stored in the local SQLite database.
- Complaint drafts and their PDFs are stored locally under `backend/storage/complaints`.
- The only outbound network traffic is DNS resolution and fetching the URL being analyzed (plus optional Playwright/OCR model downloads if you enable them).
- No analytics, telemetry or third-party reputation calls are included.

---

## License and attribution

No license file is included. Treat this as a local project, not a redistributable product. The ThreatLens name, shield/lens logo and UI are original to this project. Third-party libraries retain their own licenses.
