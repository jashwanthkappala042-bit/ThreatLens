# ThreatLens security notes

This document describes the threat model, implemented controls, and the residual risks of running ThreatLens locally. It is written to be honest about what the code does and does not protect against.

## Scope and threat model

ThreatLens is a **single-user, local development application**. It is not hardened for public deployment. The relevant threats are:

1. A user submitting a malicious URL that tries to reach internal services (SSRF).
2. A malicious scanned page serving oversized responses, slow responses, redirect loops or hostile HTML.
3. Malicious uploaded images or QR/OCR content.
4. Untrusted community content attempting script injection or social engineering.
5. Credential theft through token exposure, weak passwords or brute force.
6. Resource exhaustion through repeated scans or large payloads.
7. Accidental disclosure of scan results or complaint drafts to another local account.
8. Over-trusting heuristic results.

Out of scope for this build: multi-tenant isolation, internet-facing deployment, malware detonation, enterprise identity, audit retention policy, and guarantees about third-party dependencies.

## Implemented controls

### Authentication and authorization

- Passwords are hashed with Werkzeug's password hashing (PBKDF2 by default). Plaintext passwords are never stored.
- Password policy: 8–128 characters, at least one letter and one digit. Email addresses are normalised and length-checked. Display names are stripped, whitespace-collapsed, length-limited and reject control characters and `<>`.
- JWT access tokens are signed with `JWT_SECRET_KEY`, expire after one hour by default, and are required via the `Authorization: Bearer` header.
- Missing, invalid, expired and revoked tokens return structured `401` responses.
- Ownership checks:
  - History and dashboard endpoints only query the caller's records.
  - Scan analysis is available to the owner or an admin; anonymous scans are available to anyone with the UUID.
  - Complaint drafts and PDFs are owner/admin only.
  - Community posts can be deleted by their author or an admin.
  - Moderation endpoints call `require_admin`.
- Logout is stateless. The client discards the token; the server records an audit event. Tokens remain valid until expiry, which is a deliberate local-app trade-off.

### SSRF and outbound request safety

Implemented in `app/utils/url_safety.py` and `app/scanners/http_client.py`:

- Only `http` and `https` are accepted.
- Only ports 80 and 443 are allowed.
- Embedded credentials (`user:pass@host`) are rejected.
- Control characters and backslashes are rejected.
- URL length is capped at 2048 characters.
- Hostnames are IDNA-encoded and label-validated.
- `localhost`, `*.localhost`, `*.local`, cloud metadata hostnames and similar names are blocked.
- Hostnames are resolved before the request. Any non-global address (private, loopback, link-local, multicast, reserved, IPv6 unique-local) is rejected. IPv4-mapped IPv6 addresses are unwrapped and checked.
- Redirects are followed manually. **Every hop is revalidated**, including its destination address and port.
- Redirect count, connect timeout, read timeout and response bytes are bounded.
- The fetcher never forwards caller headers, cookies or authorization data. It sends a fixed, minimal header set and a ThreatLens user agent.
- `session.trust_env = False` prevents environment proxy settings from silently rerouting traffic.
- TLS certificate verification is left enabled. Certificate failures are reported as evidence, not bypassed.
- The response body is streamed and truncated at the byte cap.

**Residual risk — DNS rebinding:** the hostname is resolved for validation and then resolved again by `requests` when connecting. A hostile DNS server could return a public address during validation and a private one during the request. Every hop is revalidated, but this does not close the race. A production deployment should pin validated IPs at the socket layer and re-check after connection. This is documented in the HTTP client source.

**Residual risk — `X-Forwarded-For`:** the rate limiter prefers this header when present. With no trusted proxy in front of the app, a client can spoof it to rotate rate-limit buckets. This only affects local abuse accounting, not authorization.

### Upload and image handling

- Request size is capped at 6 MB (`MAX_CONTENT_LENGTH`); image bytes at 5 MB; decoded pixels at 25 MP.
- The declared MIME type is not trusted. Pillow opens the file and the decoded format must be PNG, JPEG, WEBP, GIF, BMP or TIFF.
- Decompression-bomb limits are enforced by the pixel cap and Pillow's own guards.
- Images are processed in memory. Only metadata, decoded QR values, OCR text and findings are persisted. **The original bytes are not stored.**
- QR decoding uses OpenCV in-process; optional pyzbar and EasyOCR are imported defensively.
- Extracted URLs are passed through the same SSRF-safe URL pipeline.

### Input validation and output safety

- JSON bodies must be objects; unknown types are rejected.
- Text fields have explicit minimum/maximum lengths.
- Scan text is capped at 20,000 characters; URLs at 2,048; findings and evidence are clamped before storage.
- Complaint dates must parse as `YYYY-MM-DD` and cannot be in the future; categories are allow-listed; the suspect URL is independently validated.
- Community URLs are validated and normalised but not fetched.
- PDF filenames are server-generated UUIDs. Download paths are resolved and checked to stay inside the complaint storage directory.
- The frontend does not use `dangerouslySetInnerHTML`. React escapes all displayed text.
- Untrusted community URLs are shown as plain text with a copy action, not as clickable anchors, reducing accidental visits.
- No raw HTML from scanned pages is rendered in the UI.

### Rate limiting and resource bounds

- In-process sliding-window limits per IP: auth 10/min, scans 20/min, community 20/min, complaints 10/min.
- Limits are configurable through `RATE_LIMIT_*`.
- Scan timeouts and byte caps bound outbound work. Email/image URL enrichment analyses at most three URLs.
- SQLite is used with WAL mode for local concurrency.

### Audit logging

The `audit_logs` table records auth events, scan creation/deletion, complaint generation, profile updates, community posts/comments/reports, deletions and moderation actions. IP addresses are stored only as a salted SHA-256 prefix; full IPs are not retained. Audit writes are best-effort and never break a request. Payload contents and secrets are not logged.

### Transport and response headers

- CORS is restricted to configured origins (`CORS_ORIGINS`), with only `Content-Type` and `Authorization` allowed as request headers.
- API responses set `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer` and a restrictive `Permissions-Policy`.
- HSTS is added when the request is already HTTPS.
- Unexpected exceptions return a generic `internal_error`; stack traces are logged server-side, not returned to the client.

### Community moderation controls

- Posting, commenting and reporting require authentication and are rate-limited.
- Content is labelled `unverified_community_report` and the UI repeats that warning.
- Duplicate open reports by the same user are rejected.
- A configurable number of open reports flags a post (`REPORTS_TO_FLAG`, default 3).
- Admins can remove/restore posts and resolve/dismiss reports. Removal closes open reports and comments are blocked on non-published posts.
- Removed posts are hidden from non-admin users, including their detail pages.

## Residual risks and known weaknesses

These are real and should be understood before using ThreatLens beyond a local demo.

1. **Token storage in `localStorage`.** Any XSS would expose the token. React escaping and the absence of raw-HTML injection reduce the risk, but a strict Content-Security-Policy and httpOnly cookie sessions would be stronger. No CSP is set by the API or Vite dev server.
2. **No CSRF protection.** The app uses bearer tokens rather than cookies, so classic CSRF is not applicable. If you switch to cookie auth, add CSRF protection.
3. **In-process rate limiter.** Per-process, reset on restart, and spoofable via `X-Forwarded-For` when no trusted proxy is present. Not suitable for multi-worker or public use.
4. **DNS rebinding window.** See above; address pinning is not implemented.
5. **No malware analysis.** ThreatLens fetches page content and parses HTML. It does not detonate payloads, scan downloads, or execute JavaScript by default. Playwright, if enabled, must be treated as hostile-content execution and isolated.
6. **Heuristics can be wrong.** False positives and false negatives are expected. Scores are uncalibrated and are not probabilities. "No significant indicators" is not proof of safety.
7. **No external reputation.** There is no Google Safe Browsing, VirusTotal, PhishTank or similar integration. Enabling `ENABLE_EXTERNAL_REPUTATION` does not create one; no provider is wired up.
8. **Community content is unverified.** A linked scan reflects the author's saved analysis, not an independent moderation verdict. Reports can be abused. Moderators must review evidence.
9. **Synchronous scans.** A slow target can occupy a request up to the configured timeouts. There is no queue or worker isolation.
10. **Optional OCR/browser dependencies.** EasyOCR downloads model weights, and Playwright launches a browser. Both expand the attack surface and resource usage. They are disabled by default and not installed.
11. **Optional ML artifacts.** A model loaded from disk is trusted code/data. Only load artifacts you trained or obtained from a trusted source. Metrics from a single split are not real-world performance.
12. **No secrets management.** Default development keys are in `config.py` if `.env` is absent. The app logs a warning, but it does not refuse to start. Set strong keys before any shared use.
13. **Audit log is not tamper-evident.** A local database administrator can edit or delete rows.
14. **PDF content.** Report and complaint PDFs include user-supplied text. They are generated locally with ReportLab and served as attachments. Review before sharing; they may contain personal data.
15. **No account deletion or password reset.** Compromised accounts must be handled manually in the local database.
16. **Dependency risk.** No dependency audit or lockfile pinning is enforced beyond the version ranges in `requirements.txt` and `package.json`.

## Deployment guidance

Do **not** expose this build directly to the internet. If you need a shared deployment, at minimum:

- Set strong, unique `SECRET_KEY` and `JWT_SECRET_KEY` values and keep `.env` out of version control.
- Put the app behind a reverse proxy that terminates TLS and sets trusted forwarded headers.
- Replace the in-process limiter with a shared store; do not trust client-supplied `X-Forwarded-For`.
- Move tokens to httpOnly, Secure, SameSite cookies with CSRF protection, or use a proper session store.
- Add a strict Content-Security-Policy and review the frontend build for third-party scripts.
- Pin validated destination IPs at the socket layer to close the DNS-rebinding window.
- Isolate optional browser rendering in a container with no network access beyond the target and strict resource limits.
- Run as an unprivileged user with a dedicated data directory and backups.
- Add monitoring, log retention and an incident-response process.

## Reporting security issues

This is a local project with no security contact or bug bounty. If you find a problem, document the reproduction locally and fix it before sharing the app. Do not test against systems you do not own or have permission to assess.
