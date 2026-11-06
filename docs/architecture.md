# ThreatLens architecture

ThreatLens is a local, two-process application:

- `frontend/` — React 19 single-page app built with Vite. It handles presentation, routing, auth state and file selection.
- `backend/` — Flask API with JWT auth, SQLAlchemy persistence and the analysis engines.
- `ml/` - training scripts plus the three committed model artifacts. Raw datasets are not committed.
- Database - SQLite file at `backend/instance/threatlens.db` locally; any `DATABASE_URL` (PostgreSQL) when deployed.
- `backend/storage/complaints/` — locally generated complaint-draft PDFs.

```
Browser
  │  React (Vite dev server, :5173)
  │  /api proxied to :5000
  ▼
Flask API
  ├── routes/        HTTP handlers, auth checks, rate limits
  ├── services/      scan orchestration, PDF generation
  ├── scanners/      URL, email, image pipelines
  ├── detection/     findings, URL features, ML loader, risk policy
  ├── utils/         URL safety, text helpers
  └── SQLAlchemy ──► SQLite (local) / PostgreSQL (deployed)
```

## Request flow

1. The SPA sends JSON (or multipart for images) to `/api/*`. Axios adds a bearer token when one is stored.
2. Flask validates the JWT where required, applies a per-IP sliding-window rate limit, and parses the payload.
3. The scan service calls the relevant scanner. Scanners return observations, findings, stage status and limitations as plain dictionaries.
4. The risk engine groups findings by category, combines them with diminishing returns, applies floors and thresholds, and returns an assessment plus a decision trace.
5. The scan row, findings and the full analysis JSON are committed. Images themselves are not stored.
6. The SPA fetches the analysis by UUID and renders tabs for overview, findings, evidence, decision trace and limitations.

## Backend modules

| Path | Responsibility |
| --- | --- |
| `app/__init__.py` | App factory, CORS, JWT, error envelopes, security headers, health, CLI commands |
| `app/config.py` | Environment-driven configuration and capability flags |
| `app/database.py` | Engine, request-scoped sessions, SQLite pragmas, Postgres pool recycling |
| `app/models.py` | `User`, `Scan`, `ScanFinding`, `CommunityPost`, `Comment`, `CommunityReport`, `ComplaintDraft`, `AuditLog` |
| `app/security.py` | Rate limiter, password/name validation, audit log, current-user helpers |
| `app/routes/scans.py` | Scan submission, analysis, status, PDF, history |
| `app/routes/auth.py` | Register, login, me, logout |
| `app/routes/dashboard.py` | Aggregates computed from the caller's scans |
| `app/routes/community.py` | Feed, posts, comments, reports, admin moderation |
| `app/routes/complaints.py` | Draft creation and PDF download |
| `app/routes/profile.py` | Profile counts and updates |
| `app/services/scan_service.py` | Scanner orchestration and persistence |
| `app/services/report_pdf.py` | ReportLab scan report and complaint draft |
| `app/scanners/http_client.py` | Bounded HTTP fetch with manual, revalidated redirects |
| `app/scanners/url_scanner.py` | Static, DNS, HTTP, HTML and optional browser/ML stages |
| `app/scanners/email_scanner.py` | Text heuristics, URL extraction, optional email/SMS ML |
| `app/scanners/image_scanner.py` | Image validation, QR decode, optional OCR, URL analysis |
| `app/detection/text_normalizer.py` | Shared HTML-safe text normaliser embedded in text-model pipelines |
| `app/detection/risk_engine.py` | Central scoring and classification policy |
| `app/utils/url_safety.py` | Scheme/port/host validation, DNS checks, IP classification |

## Data model

- **User** — local account; `role` is `user` or `admin`.
- **Scan** — UUID primary key, optional `user_id`, input metadata, verdict, score, full `analysis` JSON, timestamps.
- **ScanFinding** — individual explainable indicator linked to a scan. The full finding list also lives inside `analysis`; the table makes history queries and future analytics simpler.
- **CommunityPost** — author, optional linked scan, title, body, shared URL, status (`published` / `removed` / `flagged`).
- **Comment**, **CommunityReport** — discussion and moderation reports.
- **ComplaintDraft** — user-supplied incident details and the generated PDF filename.
- **AuditLog** — action, hashed IP, optional user, timestamp.

Anonymous scans have `user_id = NULL`. They are accessible to anyone who possesses the UUID, but they do not appear in any history or dashboard aggregate.

## Detection pipeline

### URL

1. Normalise and validate the scheme, host, port, credentials and address family.
2. Resolve DNS and reject private, loopback, link-local, multicast and reserved addresses.
3. Inspect static features (length, TLD, punycode, brand impersonation, keywords, extensions, entropy).
4. Fetch content with `requests`, `allow_redirects=False`, bounded timeouts and response size; validate each redirect hop.
5. Parse HTML with BeautifulSoup: forms, password fields, external action targets, iframes, scripts, hidden inputs.
6. Optionally run Playwright with request interception when explicitly enabled and installed.
7. Optionally apply the local URL model using only static URL features, so no page content is needed.
8. Assess findings with the risk engine.

### Email / message

1. Validate and normalise text (bounded length).
2. Detect urgency, threats, credential requests, payment lures, impersonation, obfuscation and suspicious formatting.
3. Extract up to three URLs and run the URL pipeline on each.
4. Optionally apply the local text model. Body-only messages up to `SMS_MAX_CHARS` use the
   three-class SMS model (ham/spam/smishing); messages with a subject use the binary email model.
5. Assess findings with the risk engine.

### Image

1. Enforce byte size, MIME signature, decode success and pixel count.
2. Decode QR codes with OpenCV (optional pyzbar fallback).
3. Optionally extract text with EasyOCR when enabled and installed.
4. Analyse decoded URLs through the same protected URL service.
5. If neither QR nor text can be extracted, return an inconclusive assessment rather than “safe”.
6. Store metadata, extracted text and URLs only — never the image bytes.

## Optional ML artifacts

The app never downloads a model. It lazily loads a local joblib dictionary from
`URL_MODEL_PATH`, `EMAIL_MODEL_PATH` or `SMS_MODEL_PATH` and caches it by file
mtime. The artifact contains `{model, feature_names, metadata, metrics}`.

- **URL**: the model is trained only on features that can be computed from the
  URL string, so it can run before DNS or HTTP. Feature names are frozen in the
  artifact and must match `extract_url_features`.
- **Email**: the artifact is a scikit-learn pipeline that starts with
  `MessageNormalizer`. Raw runtime text and the punctuation-tokenised training
  corpus therefore go through the same cleaning.
- **SMS**: the same pipeline shape, with `ham` / `spam` / `smishing` classes.
  It is used only for body-only messages at or below `SMS_MAX_CHARS`.
- A missing or unreadable artifact makes the stage `unavailable`; no score is
  invented. Metrics stored in the artifact describe one held-out split and are
  not a production detection rate.

## Risk policy

Implemented in `app/detection/risk_engine.py`:

- Deduplicate findings by indicator id.
- Group by category.
- Within a category: highest weight + half of the second + a quarter of the rest.
- Sum categories, cap at 100.
- Apply conservative floors: critical ≥ 85, high ≥ 40.
- Thresholds: ≥ 70 high risk, ≥ 35 suspicious, otherwise no significant indicators.
- If essential stages failed or image content could not be extracted, classify as inconclusive regardless of score.
- Emit a decision trace, category breakdown and limitations.

The score is explicitly heuristic and uncalibrated.

## Frontend structure

- `context/` — auth, theme and toast providers.
- `components/` — layout, navigation, cards, badges, modal, confirm dialog, skeletons, protected routes, evidence renderer.
- `pages/` — landing, scanner, results, dashboard, history, community, post detail, moderation, complaints, profile, about, auth, 404.
- `lib/api.js` — axios client, envelope unwrapping, authenticated downloads.
- `lib/format.js` — shared labels and date/severity formatting.

The Vite dev server proxies `/api` to `127.0.0.1:5000`, so the browser makes same-origin requests during development.

## Key trade-offs

- **Synchronous scans.** URL fetches are bounded and complete within the request. A status endpoint exists for API symmetry and future asynchronous work, but scans are not queued. This keeps the local setup simple and avoids a worker dependency.
- **In-process rate limiter.** Correct for one development process; not shared across workers or restarts.
- **Client-side JWT storage.** Simple for a local app, but a token in `localStorage` is readable by any script that achieves XSS. The app avoids `dangerouslySetInnerHTML` and does not auto-link untrusted community URLs, but a strict Content-Security-Policy and httpOnly cookies would be stronger for a multi-user deployment.
- **JSON analysis snapshots.** Each scan stores its full evidence, so historical results do not change silently when heuristics are updated.
- **Images not persisted.** This limits storage and privacy exposure, but means the report cannot embed the uploaded screenshot.
- **No external reputation.** The only network access is the scanned target itself (and DNS). No URL is sent to a third-party reputation provider.

## Extension points

- Replace the in-process limiter with Redis.
- Move scans to a queue and use the existing status endpoint for polling.
- Add a database-backed or httpOnly-cookie session model.
- Add a content security policy and CSRF strategy if cookies are introduced.
- Train and evaluate local models with the scripts in `ml/`, then point the config at the artifacts.
- Enable Playwright and OCR only after installing their dependencies and reviewing the isolation and resource limits.
