# ThreatLens limitations

ThreatLens is a local analysis and education project. This file lists what it does **not** do, where results can mislead, and which features are intentionally incomplete or disabled.

If a result matters, verify it independently. For anything involving money, credentials or personal safety, contact the relevant organisation through a channel you initiate, and consider reporting to the appropriate authority. In India, the official portal is <https://cybercrime.gov.in/>. ThreatLens is not affiliated with it and does not submit anything.

## 1. Analytical limitations

### Scores are heuristics, not probabilities

- Every score is emitted as `score_kind: heuristic_uncalibrated`.
- The score is a weighted combination of hand-written indicators with diminishing returns, floors and thresholds. It is not trained, calibrated or validated against a labelled population.
- A score of 0 does **not** mean safe. It means no configured indicator fired in the stages that completed.
- A high score does not prove malicious intent. Legitimate sites can use the same patterns (password forms, urgency, redirects, third-party scripts).
- Confidence is derived from category coverage and completed stages. It is explicitly `calibrated: false` and is not a statistical confidence interval.

### Missing evidence is treated as unknown, but only in defined cases

- If an essential stage fails or an image yields no extractable content, the engine returns `unknown` rather than “clean”.
- The essential-stage rules are limited: URL requires static inspection and HTTP inspection; email requires text heuristics; image requires image validation.
- Other gaps become limitations and are surfaced, but they may not force an inconclusive verdict. Read the Limitations tab and stage list rather than the score alone.
- A page that returns a login form with no other indicators may still be a well-crafted phishing page. Static indicators cannot establish intent.

### URL analysis

- Only `http`/`https`, ports 80/443 and public addresses are analyzed. Intranet hosts, non-standard ports and private services are rejected by design.
- Content is fetched with a fixed user agent and no cookies or credentials. Some sites behave differently for automated requests or block them entirely.
- Only a bounded amount of HTML is retrieved and parsed. Content behind authentication, CAPTCHAs, paywalls, or heavy client-side rendering is not seen unless optional Playwright analysis is enabled.
- Redirect chains are followed up to the configured limit and each hop is validated, but the final landing page may still change after the scan.
- DNS rebinding is not fully mitigated: validation resolves the hostname, then the HTTP client resolves it again. See [security.md](security.md).
- HTML parsing looks for structural signals (forms, password fields, iframes, scripts, hidden inputs). It does not execute JavaScript by default and does not perform visual similarity or brand-asset comparison.
- There is no live blocklist, certificate-transparency lookup, WHOIS/domain-age lookup, or external reputation service.
- Compromised legitimate domains, newly registered lookalikes and targeted spear-phishing pages can easily evade the heuristics.

### Email/message analysis

- The input is plain text supplied by the user. Headers, attachments, embedded images, SPF/DKIM/DMARC results and real sender authentication are not available or checked.
- Up to three extracted URLs are analyzed. Additional links are ignored, and that limit is documented in the result.
- Heuristics detect common social-engineering language, not all phishing. Short messages, non-English messages, image-only emails and highly personalised attacks may produce few or no indicators.
- A legitimate marketing email may trigger urgency/payment keywords and be marked suspicious.
- No attachment sandboxing, macro analysis or file reputation is performed.

### Image analysis

- Images are validated and decoded, but the scanner only understands **QR codes** and **OCR text**.
- QR decoding relies on OpenCV, with optional pyzbar fallback. Stylised, damaged, cropped, inverted or low-resolution codes may not decode.
- OCR is disabled by default. Even when enabled, EasyOCR requires a separate install and may download model weights. OCR quality varies with language, font, layout and image quality.
- If no QR or OCR text is extracted, the result is inconclusive — not safe. An image can contain a threat that neither decoder sees.
- The original image is not stored, so a later reviewer cannot re-examine the exact pixels through the app.
- Logos, screenshots of browser UI and visual brand impersonation are not compared against reference assets.

### Optional browser analysis

- Playwright/Chromium support exists but is **disabled by default and not installed**.
- When enabled, it executes hostile page JavaScript in a browser process. Isolation depends on how you configure the host/container; the app does not provide a hardened sandbox.
- Request interception blocks private destinations on a best-effort basis, but this is not a substitute for network isolation.
- Browser evidence can differ from what a human sees due to geolocation, login state, bot detection and timing.

### Optional machine learning

- **The three trained artifacts ship with ThreatLens; the raw datasets do not.** When an artifact is missing or unreadable, the ML stage reports `available: false` and no prediction is invented. Datasets and training logs are gitignored.
- Three local artifacts are supported: a static-feature URL classifier, a binary email classifier, and a three-class SMS classifier (`ham` / `spam` / `smishing`). They are trained by the reproducible scripts in `ml/` on CC BY 4.0 public corpora with recorded SHA-256 fingerprints.
- Any metrics printed during training describe one split of one dataset. They are not real-world detection rates and are not displayed as calibrated probabilities. The URL benchmark is grouped by domain; the email split is deduplicated and stratified.
- The SMS model is only applied to body-only messages at or below `SMS_MAX_CHARS`. It was trained on 5,947 short messages collected before 2022, so its vocabulary and class balance are dated, and the corpus is small.
- The email corpus spans 1998–2008 and the URL corpus was collected before 2024. None of the models has been validated on live traffic from this instance.
- URL models use only features computable from the URL string, so page-derived and dataset-derived scores (notably `URLSimilarityIndex`) are excluded from the deployable model. Higher benchmark numbers that include them are labelled as a non-deployable upper bound.
- The ML output is a supporting signal, not the verdict. Heuristic findings remain visible, and engine disagreement is surfaced when detected.
- Model artifacts are trusted local files. Loading an artifact from an untrusted source is a code/data risk.

## 2. Product and workflow limitations

### Scanning

- Scans run **synchronously** in the request. There is no queue, worker, cancellation or progress stream. The status endpoint exists for API symmetry and returns the completed record.
- A slow destination can hold a request open until timeouts expire, up to the configured bounds.
- There is no bulk scan, scheduled re-scan, monitoring, or change detection.
- Scan results are snapshots. Re-scanning later may produce different evidence and a different score.
- Images are not retained, so reports cannot embed the uploaded screenshot.
- There is no file/malware scanner, sandbox, attachment analysis or APK/document inspection.
- Anonymous scans are accessible to anyone with the UUID. Treat links as sensitive if the scanned content is private.

### Accounts

- Accounts are local email/password accounts. There is no email verification, password reset by email, OAuth/SSO, MFA, account deletion or session revocation list.
- Logout only clears the client token. A copied token remains valid until expiry (default one hour).
- Tokens are stored in `localStorage`, which is readable by any successful XSS.
- There is no per-user data export or retention policy.
- Admin promotion is a local CLI operation, not an in-app workflow.

### Community

- Community posts are **unverified claims by users**, not ThreatLens findings. A linked scan is the author's saved result and is not re-run or independently verified on share.
- Reporting flags content but does not analyze it. Moderators see reports, not an automatic truth assessment.
- There is no reputation system, edit history, notifications, following, voting or real-time updates.
- Shared URLs are intentionally not clickable. There is no preview fetching or screenshotting of community links.
- A determined user can create multiple accounts and abuse reports. Rate limits reduce, but do not eliminate, spam.
- Deleted posts and comments are hard-deleted; there is no recovery or full moderation audit trail beyond the audit log entries.

### Complaints

- Complaint PDFs are **drafts only**. They are stored locally and linked to the account. **Nothing is submitted to cybercrime.gov.in or any authority.**
- The form does not validate legal sufficiency, jurisdiction or evidence quality.
- There is no attachment upload, digital signature, acknowledgement tracking or submission status.
- Draft PDFs may contain personal data. They are not encrypted at rest beyond the host filesystem.
- The link to the official portal is informational only; ThreatLens is not affiliated with it.

### History and dashboard

- History shows only the signed-in user's scans. Anonymous scans never appear there.
- Dashboard figures are computed from that user's stored scans only. They are not global or cross-user statistics.
- Activity covers 14 days; category distribution covers only medium/high/critical findings in the caller's scans.
- There is no export, scheduled report, team view or comparison over time.

## 3. Security and operational limitations

- The app is designed for **local use**, but a deployment configuration is included (`render.yaml`, `frontend/vercel.json`, [deployment.md](deployment.md)). Read it before exposing an instance: set real secrets, use PostgreSQL, restrict CORS, and keep the single-worker/rate-limit caveat in mind.
- The rate limiter is in-process, resets on restart, is not shared across workers, and trusts `X-Forwarded-For` for client identity. Without a trusted proxy, that header is spoofable.
- No Content-Security-Policy is configured. The JWT is in `localStorage`. There is no CSRF layer because bearer tokens, not cookies, are used; switching to cookies would require one.
- DNS rebinding is a known residual risk. Validated IPs are not pinned at the socket layer.
- Default development secrets are used if `.env` is missing. The app warns but still starts.
- SQLite is suitable for one local process, not high concurrency. Hosted deployments should use PostgreSQL (`DATABASE_URL`); Render's filesystem is ephemeral. There are no migrations; tables are created with `create_all`. Schema changes require manual handling or a fresh database.
- Audit logs are best-effort, stored in the same database, and not tamper-evident.
- There is no backup, restore, log rotation or retention automation.
- Optional dependencies (Playwright, EasyOCR, pyzbar) are not installed by default and their system requirements vary. Enabling a flag without installing the dependency yields an `unavailable` stage, not a silent fake result.
- No dependency vulnerability scanning, lockfile enforcement, container image or CI pipeline is included. Host configuration is documented in [deployment.md](deployment.md).

## 4. Honest verification status

- Backend tests: **82 passed** at the time of writing (`pytest backend/tests -q`).
- Frontend production build: **succeeds** with a Vite chunk-size warning (single JS bundle ≈ 948 kB, ≈ 271 kB gzip). No code splitting.
- There is **no frontend unit/e2e test suite** and **no automated accessibility or cross-browser test suite**.
- Manual smoke testing covered the main flows: landing, auth, signed-in and anonymous scans, email scan, QR/image scan, result tabs, dashboard, history, community, moderation, complaint draft generation/download, profile update, theme switch and scan report PDF.
- Live URL behavior depends on the network and the destination. Tests that require outbound access are separate (`test_url_scan_live.py`) and should be interpreted as environment-dependent smoke checks, not deterministic guarantees.
- The presence of a passing test does not mean the detection heuristic is accurate. Tests verify behaviour and safety properties, not real-world detection quality.

## 5. What would be needed for a production-grade tool

- A labelled, licensed dataset with proper train/validation/test splits, calibration and documented evaluation.
- External reputation feeds and domain intelligence with clear terms and privacy review.
- Isolated browser and sandbox workers with pinned egress and no access to internal networks.
- A queue, idempotent workers, observability, retention and incident response.
- Hardened auth (httpOnly cookies or a session service, MFA, reset flow, revocation), CSP, CSRF strategy and trusted proxy configuration.
- Migration tooling, backups, encryption at rest and a privacy/data-retention policy.
- Legal review for complaint handling and clear disclaimers about non-affiliation with any authority.

Until then, treat ThreatLens as an explainable local assistant — useful for learning and triage, not an authority.
