# ThreatLens API reference

Base URL in local development: `http://127.0.0.1:5000`. The Vite client proxies `/api` from `http://127.0.0.1:5173`, so frontend code uses relative paths.

All endpoints are JSON except image upload (`multipart/form-data`) and PDF downloads (`application/pdf`).

## Response envelope

Success:

```json
{
  "success": true,
  "data": {},
  "message": "optional",
  "meta": {
    "page": 1,
    "per_page": 10,
    "total": 42,
    "pages": 5
  }
}
```

Failure:

```json
{
  "success": false,
  "error": {
    "code": "invalid_url",
    "message": "That address cannot be scanned.",
    "details": null
  }
}
```

`details` is omitted unless present. Common status codes: `400` malformed request, `401` unauthenticated/expired token, `403` forbidden, `404` not found, `409` conflict, `413` payload too large, `422` validation failure, `429` rate limited, `500` unexpected server error.

Every `/api/*` response includes `Cache-Control: no-store`. Security headers are set globally.

## Authentication

Protected endpoints require:

```
Authorization: Bearer <access_token>
```

Tokens are issued by register/login, expire after `JWT_ACCESS_TOKEN_EXPIRES` seconds (default 3600), and contain the user id and role. Logout is client-side: discard the token. The API only records an audit event.

---

## Health and index

### `GET /api/health`

Public. Returns service status, database check, and capability flags:

```json
{
  "success": true,
  "data": {
    "service": "threatlens-api",
    "version": "1.0.0",
    "time": "2026-10-31T06:00:00Z",
    "database": { "ok": true, "error": "" },
    "capabilities": {
      "browser_analysis": { "enabled": false, "installed": false, "available": false, "reason": "…" },
      "ocr": { "enabled": false, "installed": false, "note": "…" },
      "qr_decoding": { "opencv": true },
      "external_reputation": { "enabled": false, "configured": false },
      "local_models": {
        "url_model": { "available": false, "reason": "No trained model artifact is configured." },
        "email_model": { "available": false, "reason": "No trained model artifact is configured." },
        "sms_model": { "available": false, "reason": "No trained model artifact is configured." }
      }
    }
  }
}
```

When an artifact exists, each entry instead contains `available: true`,
`name`, `task`, `algorithm`, `dataset`, `dataset_license`, `trained_at`,
`calibrated` and a small `metrics` summary. Full per-class metrics stay in the
artifact and in the scan analysis.

### `GET /api`

Public. Service name, health path and documentation pointer.

---

## Auth

### `POST /api/auth/register`

Public. Body:

```json
{
  "email": "analyst@example.com",
  "password": "At-least-8-characters",
  "display_name": "Analyst"
}
```

`display_name` is optional and defaults to the email local part. Password rules: 8–128 characters. Display name: trimmed, non-empty, ≤ 80 characters. Returns `200` with:

```json
{
  "success": true,
  "message": "Account created.",
  "data": {
    "access_token": "…",
    "token_type": "Bearer",
    "expires_in": 3600,
    "user": {
      "id": 1,
      "email": "analyst@example.com",
      "display_name": "Analyst",
      "role": "user",
      "is_admin": false,
      "created_at": "2026-10-31T06:00:00Z"
    }
  }
}
```

Errors include `email_in_use` (409) and validation codes (422).

### `POST /api/auth/login`

Public. Body: `{ "email": "...", "password": "..." }`. Returns the same shape as register with `"message": "Signed in."`. Invalid credentials return `401 invalid_credentials` and are audited. Rate-limited.

### `GET /api/auth/me`

Requires auth. Returns `{ "user": { ...same user object... } }`.

### `POST /api/auth/logout`

Optional auth. Always succeeds and records an audit event when a valid user is present:

```json
{
  "success": true,
  "message": "Signed out. Discard the access token on the client.",
  "data": { "logged_out": true, "client_action": "discard_access_token" }
}
```

---

## Scanning

All scan endpoints are **public but optionally authenticated**. When a valid token is supplied, the scan is saved to the account; otherwise `user_id` is `NULL`.

Scans are **synchronous**: the 201 response is the completed result. The status endpoint exists for API symmetry; it is not a queue.

Common rate limit: 20 requests/minute per IP.

### `POST /api/scan/url`

Body:

```json
{ "url": "https://example.com/login" }
```

Validation rejects malformed URLs, unsupported schemes/ports, credentials, and private/loopback/link-local/reserved network addresses unless `ALLOW_PRIVATE_NETWORK_TARGETS=true` (tests only). Returns `201` with a full scan object (below). Errors: `invalid_url`, or specific validation codes such as `private_address`/`blocked_host` (422).

### `POST /api/scan/email`

Body:

```json
{
  "subject": "Optional subject",
  "sender": "Optional sender",
  "body": "Required message text unless subject is present"
}
```

`body` may also be sent as `text`. Subject and body cannot both be empty. Body is capped by `MAX_TEXT_CHARS` (20,000). Returns `201` with a full scan object. Errors: `empty_message`, `message_too_long` (422).

If a local SMS artifact is configured, a body-only message of at most `SMS_MAX_CHARS` (default 700) is scored by the three-class SMS model; `analysis.ml.task` is `sms_3class` and `class_probabilities` contains `ham`, `spam` and `smishing`. Messages with a subject use the binary email model (`task: email_binary`). If neither artifact exists the stage reports `available: false`.

### `POST /api/scan/image`

Multipart form field: `file`. Allowed image types are validated by content signature: PNG, JPEG, WEBP, GIF, BMP, TIFF. Caps: 5 MB (`MAX_IMAGE_BYTES`) and 25 megapixels (`MAX_IMAGE_PIXELS`). Returns `201` with a full scan object. Errors: `missing_file`, `file_too_large` (413), `invalid_image`/`unsupported_image` (422).

Images are processed in memory and **not persisted**. Stored data includes filename label, dimensions/format metadata, QR text, OCR text (if enabled), extracted URLs and findings.

### Full scan object

```json
{
  "success": true,
  "data": {
    "id": "0d9a6c1b-…",
    "input_type": "url",
    "input_label": "https://example.com/login",
    "input_preview": "https://example.com/login",
    "status": "completed",
    "classification": "suspicious",
    "classification_label": "Suspicious",
    "risk_score": 52,
    "risk_level": "medium",
    "summary": "Several indicators were found…",
    "findings_count": 4,
    "is_anonymous": false,
    "created_at": "2026-10-31T06:00:00Z",
    "completed_at": "2026-10-31T06:00:02Z",
    "analysis": {
      "input_url": "https://example.com/login",
      "normalized_url": "…",
      "features": { "…": "…" },
      "http": { "status_code": 200, "final_url": "…", "content_type": "text/html" },
      "html": { "forms": [], "iframes": [], "scripts": [] },
      "stages": [
        { "name": "Static URL inspection", "status": "completed", "detail": "…" }
      ],
      "ml": { "available": false, "reason": "No trained model artifact is configured." },
      "limitations": ["…"],
      "assessment": {
        "classification": "suspicious",
        "classification_label": "Suspicious",
        "risk_score": 52,
        "risk_level": "medium",
        "score_kind": "heuristic_uncalibrated",
        "summary": "…",
        "confidence": { "level": "low", "calibrated": false, "explanation": "…" },
        "supporting_findings": [
          {
            "indicator_id": "credential_form",
            "title": "Password field found",
            "description": "…",
            "category": "credential_harvesting",
            "severity": "high",
            "weight": 25,
            "source": "html",
            "evidence": { "…": "…" }
          }
        ],
        "categories": [
          { "category": "credential_harvesting", "score": 25.0, "indicator_count": 1, "indicators": ["Password field found"] }
        ],
        "stages": [],
        "evidence_quality": { "attempted": 5, "completed": 4, "ratio": 0.8, "stages": [] },
        "decision_trace": ["Category contributions sum to 52.0 before floors and caps.", "…"],
        "limitations": ["…"],
        "recommended_actions": ["…"],
        "engine_results": [{ "name": "Static URL inspection", "status": "completed", "detail": "…" }],
        "disagreements": [],
        "generated_at": "2026-10-31T06:00:02Z"
      }
    }
  }
}
```

Classification values: `no_significant_indicators`, `suspicious`, `malicious`, `unknown`. `risk_level` maps to `low`, `medium`, `high`, `unknown`. Scores are always `score_kind: heuristic_uncalibrated`.

The `analysis` object varies by input type:

- **URL:** `input_url`, `normalized_url`, `hostname`, `registrable_domain`, `scheme`, `punycode`, `is_ip_literal`, `resolved_ips`, `features`, `http`, `html`, `favicon`, `browser`, `ml`, `signals`, `stages`, `limitations`, `content_extracted`.
- **Email:** `input` (`subject`, `sender`, `body_preview`), `features`, `signals`, `ml`, `extracted_urls`, `url_results`, `stages`, `limitations`, `content_extracted`.
- **Image:** `file` (filename, declared type, actual format, dimensions, bytes, SHA-256, analysis dimension), `qr_values`, `ocr_text`, `extracted_text`, `extracted_urls`, `signals`, `url_results`, `stages`, `limitations`, `content_extracted`, `input_type_detail`.

In every case `analysis.assessment` is the risk-engine result and contains the final classification, score, findings, category breakdown, decision trace, limitations and recommendations.

### `GET /api/analysis/<scan_id>`

Optional auth. Returns the full scan object.

Access rule:

- Anonymous scan (`is_anonymous: true`): anyone with the UUID.
- Account scan: owner or admin only.

Otherwise `403 forbidden`; unknown id returns `404 scan_not_found`.

### `GET /api/scan/<scan_id>/status`

Optional auth, same access rule. Returns:

```json
{
  "success": true,
  "data": {
    "id": "…",
    "status": "completed",
    "classification": "…",
    "risk_score": 52,
    "completed_at": "…",
    "note": "Scans run synchronously and are persisted only after analysis completes."
  }
}
```

### `GET /api/scan/<scan_id>/report.pdf`

Optional auth, same access rule. Returns a ReportLab-generated PDF with the stored result, findings, stages, limitations and a disclaimer. Filename: `threatlens-report-<first 8 chars>.pdf`.

---

## History

Requires auth. Only the caller's scans are returned.

### `GET /api/history`

Query parameters:

| Name | Type | Default | Notes |
| --- | --- | --- | --- |
| `page` | int | 1 | Minimum 1 |
| `per_page` | int | 10 | 1–50 |
| `classification` | string | — | One of the four classifications |
| `input_type` | string | — | `url`, `email`, `image` |
| `q` | string | — | Case-insensitive label search, max 100 chars |

Returns an array of scan summaries in `data` and pagination in `meta`.

### `DELETE /api/history/<scan_id>`

Owner or admin. Deletes the scan and its findings. Returns `{ "deleted": "<id>" }`.

---

## Dashboard

All require auth and aggregate only the caller's data.

| Endpoint | Returns |
| --- | --- |
| `GET /api/dashboard/stats` | `total_scans`, verdict `counts`, `scans_last_7_days`, `flagged_scans`, `average_risk_score` |
| `GET /api/dashboard/activity` | `{ "days": [{ "date": "YYYY-MM-DD", "count": 0 }], "range_days": 14 }` |
| `GET /api/dashboard/categories` | Up to 8 `{ "category": "…", "count": 3 }` for medium/high/critical findings |
| `GET /api/dashboard/overview` | `{ "recent_scans": [...], "community_posts": [...] }` (5 scans, 3 posts) |

`flagged_scans` counts `suspicious` and `malicious` results. `average_risk_score` is rounded to one decimal.

---

## Community

Community content is user-submitted and **unverified**. The API exposes the marker `verification: "unverified_community_report"` and the frontend renders untrusted URLs as plain text.

### `GET /api/community/posts`

Public. Query: `page` (default 1), `per_page` (1–50, default 10), `q` (title/content search, max 100 chars). Returns published and flagged posts, newest first, with `comment_count` and an optional `linked_scan` summary. `meta.verification_note` states the content is unverified.

Post summary:

```json
{
  "id": 1,
  "title": "…",
  "content": "…",
  "url": "https://example.com/",
  "status": "published",
  "verification": "unverified_community_report",
  "author": { "id": 2, "display_name": "Analyst" },
  "linked_scan": {
    "id": "…",
    "classification": "suspicious",
    "classification_label": "Suspicious",
    "risk_score": 52,
    "input_type": "url"
  },
  "comment_count": 0,
  "created_at": "…",
  "updated_at": "…"
}
```

### `POST /api/community/posts`

Requires auth; community rate limit (20/min). Body:

```json
{
  "title": "5–160 characters",
  "content": "10–5000 characters",
  "url": "optional public URL",
  "scan_id": "optional scan UUID"
}
```

`url` is validated and normalised but **not fetched**. `scan_id` must reference a scan owned by the caller; anonymous scans cannot be linked. Returns `201` with the post summary.

### `GET /api/community/posts/<post_id>`

Public. Returns the post detail plus `comments` (published, oldest first). Removed posts return `404` unless the caller is an admin. Admins also receive `moderation.report_count`.

### `POST /api/community/posts/<post_id>/comments`

Requires auth; community rate limit. Body: `{ "content": "1–2000 characters" }`. Comments are closed (`409 post_unavailable`) unless the post is `published`. Returns `201` with the comment.

### `POST /api/community/posts/<post_id>/report`

Requires auth; community rate limit. Body: `{ "reason": "5–500 characters" }`. Duplicate open reports by the same user return `409 already_reported`. When open reports reach `REPORTS_TO_FLAG` (default 3) and the post is published, its status becomes `flagged`. Returns:

```json
{
  "success": true,
  "data": {
    "report_id": 1,
    "post_flagged": true,
    "message": "Report received. Community content remains unverified until moderated."
  }
}
```

### `DELETE /api/community/posts/<post_id>`

Author or admin. Hard-deletes the post and related records. Returns `{ "deleted": 1 }`.

### Admin moderation

All require an admin account.

- `GET /api/community/moderation/reports` — open reports (max 100), oldest first, with reporter and post summaries.
- `PATCH /api/community/posts/<post_id>/moderation` — body `{ "action": "remove" | "restore", "note": "optional ≤500 chars" }`. Removing also resolves all open reports.
- `PATCH /api/community/reports/<report_id>` — body `{ "action": "resolve" | "dismiss", "note": "optional" }`.

---

## Complaints

All endpoints require auth and only expose the caller's drafts (admins may read any). Rate limit: 10/minute for generation.

### `POST /api/complaints/generate`

Body:

```json
{
  "incident_date": "2026-10-30",
  "incident_category": "phishing",
  "suspect_url": "https://example.com/",
  "description": "At least 20 characters describing what happened.",
  "evidence": "Optional notes, ≤5000 characters.",
  "financial_loss": "Required for financial_fraud, ≤120 characters"
}
```

Categories: `phishing`, `financial_fraud`, `identity_theft`, `account_takeover`, `cyberbullying`, `other`.

Rules: date must be `YYYY-MM-DD` and not in the future; description 20–5000 characters; evidence ≤5000; `suspect_url` optional and validated without DNS resolution; `financial_loss` required for `financial_fraud`.

The server writes a PDF under `STORAGE_DIR/complaints/<uuid>.pdf` and returns `201`:

```json
{
  "success": true,
  "data": {
    "id": "…",
    "incident_date": "2026-10-30",
    "incident_category": "phishing",
    "incident_category_label": "Phishing or fraudulent website",
    "suspect_url": "…",
    "description": "…",
    "evidence": "…",
    "financial_loss": "",
    "created_at": "…",
    "download_url": "/api/complaints/<id>/pdf",
    "status": "draft_not_submitted",
    "notice": "This is a locally generated draft for your review. ThreatLens did not submit it to any authority."
  }
}
```

### `GET /api/complaints`

Paginated list of owned drafts (`page`, `per_page` 1–50).

### `GET /api/complaints/<complaint_id>`

Owned draft details. Other users get `403`; unknown ids `404`.

### `GET /api/complaints/<complaint_id>/pdf`

Downloads the stored DRAFT PDF. The path is resolved and confined to the complaint storage directory. Missing file returns `404 pdf_missing`.

**No endpoint submits a complaint anywhere.**

---

## Profile

Both require auth.

### `GET /api/profile`

```json
{
  "success": true,
  "data": {
    "user": { "id": 1, "email": "…", "display_name": "…", "role": "user", "is_admin": false, "created_at": "…" },
    "counts": { "scans": 2, "posts": 1, "complaints": 0 }
  }
}
```

### `PATCH /api/profile`

Body may contain:

```json
{
  "display_name": "New name",
  "current_password": "required only when changing password",
  "new_password": "8–128 characters"
}
```

Returns the updated profile with `"message": "Profile updated."`. Incorrect current password returns `401 wrong current password`; no usable fields returns `422 no_changes`. Auth rate limit applies.

---

## Not implemented

The following are **not** endpoints in this build:

- External reputation lookups or third-party threat feeds.
- Complaint submission to any authority.
- Asynchronous scan queues/workers.
- Community auto-analysis of reported posts.
- Account deletion, email verification, password reset by email, or OAuth.
