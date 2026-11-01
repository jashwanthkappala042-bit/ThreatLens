"""URL / website analysis orchestration."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from flask import current_app

from ..detection import ml
from ..detection.findings import finding
from ..detection.url_features import (
    BRANDS,
    extract_url_features,
    registrable_domain,
    url_feature_findings,
)
from ..utils.url_safety import InvalidTarget, validate_url
from . import browser_scanner
from .html_analyzer import analyze_html
from .http_client import fetch_small_resource, fetch_url

_DOWNLOAD_CONTENT_TYPES = {
    "application/octet-stream",
    "application/x-msdownload",
    "application/x-msdos-program",
    "application/vnd.microsoft.portable-executable",
    "application/zip",
    "application/x-zip-compressed",
    "application/x-rar-compressed",
    "application/x-7z-compressed",
    "application/x-msi",
    "application/vnd.android.package-archive",
}


def _brand_in_title(title: str, hostname: str) -> list[str]:
    registrable = registrable_domain(hostname)
    hits: list[str] = []
    title_lower = (title or "").lower()
    for brand, domains in BRANDS.items():
        official = any(registrable == d or registrable.endswith("." + d) for d in domains)
        if not official and brand in title_lower:
            hits.append(brand)
    return hits


def _http_findings(http: dict[str, Any], features: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if not http.get("available"):
        return findings

    chain = http.get("redirect_chain") or []
    if len(chain) > 1:
        initial_host = chain[0].get("hostname", "")
        final_host = http.get("final_hostname", "")
        cross_domain = bool(
            initial_host
            and final_host
            and registrable_domain(initial_host) != registrable_domain(final_host)
        )
        if cross_domain:
            findings.append(
                finding(
                    "http_cross_domain_redirect",
                    "Redirect to a different site",
                    "The submitted link redirects to a different registrable domain. Verify the "
                    "final destination before interacting.",
                    "medium",
                    "obfuscation",
                    "http",
                    evidence={
                        "initial_host": initial_host,
                        "final_host": final_host,
                        "redirects": len(chain) - 1,
                    },
                )
            )
        elif len(chain) > 3:
            findings.append(
                finding(
                    "http_many_redirects",
                    "Long redirect chain",
                    "The URL passes through several redirects, which can obscure the destination.",
                    "low",
                    "obfuscation",
                    "http",
                    evidence={"redirects": len(chain) - 1},
                )
            )

    final_url = http.get("final_url", "")
    if final_url and urlsplit(final_url).scheme == "http" and not features.get("https"):
        # Already flagged by static features; avoid duplicating.
        pass

    content_type = (http.get("content_type") or "").lower()
    disposition = (http.get("headers") or {}).get("content-disposition", "").lower()
    if content_type in _DOWNLOAD_CONTENT_TYPES or "attachment" in disposition:
        findings.append(
            finding(
                "http_download_response",
                "Response is a downloadable file",
                "The URL returns a file download rather than a web page. Do not open files from "
                "untrusted sources.",
                "high",
                "payload",
                "http",
                evidence={"content_type": content_type, "content_disposition": disposition[:200]},
            )
        )

    status = http.get("status_code")
    if isinstance(status, int) and status >= 500:
        findings.append(
            finding(
                "http_server_error",
                "Server error response",
                "The destination returned a server error. The page may be unavailable or "
                "misconfigured; this is not a security verdict.",
                "info",
                "availability",
                "http",
                weight=0,
                evidence={"status_code": status},
            )
        )
    return findings


def analyze_url(url: str) -> dict[str, Any]:
    target = validate_url(url)
    config = current_app.config
    findings: list[dict[str, Any]] = []
    limitations: list[str] = []
    stages: list[dict[str, Any]] = []

    features = extract_url_features(target.normalized_url)
    findings.extend(url_feature_findings(features))
    stages.append(
        {
            "name": "Static URL inspection",
            "status": "completed",
            "detail": "URL structure, hostname and lexical indicators were inspected.",
        }
    )

    http = fetch_url(
        target.normalized_url,
        max_redirects=int(config.get("MAX_REDIRECTS", 5)),
        connect_timeout=float(config.get("HTTP_CONNECT_TIMEOUT", 4.0)),
        read_timeout=float(config.get("HTTP_READ_TIMEOUT", 8.0)),
        max_bytes=int(config.get("MAX_RESPONSE_BYTES", 2 * 1024 * 1024)),
    )
    raw_content = http.pop("content", "")
    is_text = http.pop("is_text", False)

    if http.get("available"):
        stages.append(
            {
                "name": "HTTP inspection",
                "status": "partial" if http.get("content_truncated") else "completed",
                "detail": (
                    f"HTTP {http.get('status_code')} returned {http.get('response_bytes', 0)} bytes "
                    f"after {max(0, len(http.get('redirect_chain') or []) - 1)} redirect(s)."
                ),
            }
        )
        findings.extend(_http_findings(http, features))
    else:
        stages.append(
            {
                "name": "HTTP inspection",
                "status": "failed",
                "detail": http.get("error", "The destination could not be retrieved."),
            }
        )
        limitations.append(
            "The page could not be retrieved, so HTTP, HTML and browser observations are unavailable. "
            "The submitted URL structure was still inspected."
        )

    html: dict[str, Any] = {"available": False, "reason": "No HTML document was retrieved."}
    if http.get("available") and is_text and raw_content:
        content_type = http.get("content_type", "")
        if content_type in {"text/html", "application/xhtml+xml"}:
            parsed = analyze_html(raw_content, http.get("final_url", target.normalized_url), features)
            html = {
                "available": True,
                "title": parsed["title"],
                "meta_description": parsed["meta_description"],
                "forms": parsed["forms"],
                "form_count": parsed["form_count"],
                "password_field_count": parsed["password_field_count"],
                "external_form_actions": parsed["external_form_actions"],
                "external_links": parsed["external_links"],
                "external_link_count": parsed["external_link_count"],
                "scripts": parsed["scripts"],
                "script_count": parsed["script_count"],
                "inline_script_count": parsed["inline_script_count"],
                "js_pattern_hits": parsed["js_pattern_hits"],
                "iframes": parsed["iframes"],
                "meta_refresh": parsed["meta_refresh"],
                "favicon_url": parsed["favicon_url"],
                "third_party_resources": parsed["third_party_resources"],
                "visible_text": parsed["visible_text"],
                "hidden_input_count": parsed["hidden_input_count"],
            }
            findings.extend(parsed["findings"])
            stages.append(
                {
                    "name": "HTML inspection",
                    "status": "completed",
                    "detail": (
                        f"Parsed title, {parsed['form_count']} form(s), "
                        f"{parsed['external_link_count']} external link(s), "
                        f"{parsed['script_count']} external script(s)."
                    ),
                }
            )
            title = parsed["title"]
            brand_title_hits = _brand_in_title(title, target.hostname)
            if brand_title_hits:
                findings.append(
                    finding(
                        "html_title_brand_mismatch",
                        "Page title names a brand outside its official domain",
                        "The page title references a known brand, but the hostname is not the "
                        "brand's official domain. This is a common impersonation pattern.",
                        "medium",
                        "impersonation",
                        "html",
                        evidence={
                            "title": title[:160],
                            "brands": brand_title_hits,
                            "hostname": target.hostname,
                        },
                    )
                )
            favicon_url = parsed.get("favicon_url") or ""
            if favicon_url.startswith(("http://", "https://")):
                favicon = fetch_small_resource(favicon_url)
                favicon["declared_url"] = favicon_url[:2048]
            else:
                favicon = {"collected": False, "reason": "No favicon link was found."}
        else:
            excerpt = raw_content[:1200]
            html = {
                "available": False,
                "reason": f"Response content type is {content_type or 'unknown'}, not HTML.",
                "text_excerpt": excerpt,
            }
            stages.append(
                {
                    "name": "HTML inspection",
                    "status": "skipped",
                    "detail": "The response was not an HTML document.",
                }
            )
            favicon = {"collected": False, "reason": "No HTML document to inspect."}
    else:
        if http.get("available"):
            stages.append(
                {
                    "name": "HTML inspection",
                    "status": "skipped",
                    "detail": "The response contained no decodable HTML text.",
                }
            )
        else:
            stages.append(
                {
                    "name": "HTML inspection",
                    "status": "unavailable",
                    "detail": "HTTP retrieval failed, so HTML could not be inspected.",
                }
            )
        favicon = {"collected": False, "reason": "No HTML document to inspect."}

    if http.get("content_truncated"):
        limitations.append(
            f"The response exceeded the {int(config.get('MAX_RESPONSE_BYTES', 0)) // 1024} KB limit "
            "and was truncated before analysis."
        )

    browser = browser_scanner.analyze_in_browser(target.normalized_url)
    if browser.get("available"):
        findings.extend(browser.get("findings") or [])
        stages.append(
            {
                "name": "Browser inspection (optional)",
                "status": "completed",
                "detail": (
                    f"Rendered in an isolated Chromium context; {len(browser.get('network_requests') or [])} "
                    "network request(s) and "
                    f"{len(browser.get('console_messages') or [])} console message(s) observed."
                ),
            }
        )
    else:
        stages.append(
            {
                "name": "Browser inspection (optional)",
                "status": "unavailable",
                "detail": browser.get("reason", "Browser analysis is unavailable."),
            }
        )
        limitations.append(
            f"Dynamic browser analysis is unavailable: {browser.get('reason', 'not configured')} "
            "Static HTML and HTTP observations are still shown."
        )

    url_ml = ml.predict_url(str(config.get("URL_MODEL_PATH", "")), features)
    if url_ml.get("available"):
        score = float(url_ml.get("probability", 0))
        if score >= 0.5:
            severity = "high" if score >= 0.75 else "medium"
            findings.append(
                finding(
                    "ml_url_prediction",
                    "URL model flagged this link",
                    "A trained URL feature classifier scored this link as likely phishing. The model "
                    "score is not a calibrated probability and must be read with the listed indicators.",
                    severity,
                    "ml_signal",
                    "ml",
                    evidence={
                        "model_score": score,
                        "calibrated": bool(url_ml.get("calibrated")),
                        "model": url_ml.get("model", {}),
                    },
                )
            )
        stages.append(
            {
                "name": "ML URL classifier (optional)",
                "status": "completed",
                "detail": f"Model score {score:.3f} (uncalibrated) for class '{url_ml.get('predicted_label')}'.",
            }
        )
    else:
        stages.append(
            {
                "name": "ML URL classifier (optional)",
                "status": "unavailable",
                "detail": url_ml.get("reason", "No URL model artifact is configured."),
            }
        )

    limitations.extend(
        [
            "HTTP and HTML results are a single snapshot; content can change between requests or by region.",
            "Domain age, WHOIS ownership and external reputation services were not queried.",
            "No downloaded files or scripts were executed.",
            "Features are indicators, not proof of malicious intent.",
        ]
    )
    if not bool(config.get("ENABLE_EXTERNAL_REPUTATION", False)):
        limitations.append("No external reputation provider is configured, by design.")

    return {
        "input_url": target.original,
        "normalized_url": target.normalized_url,
        "hostname": target.hostname,
        "registrable_domain": registrable_domain(target.hostname),
        "scheme": target.scheme,
        "punycode": target.punycode,
        "is_ip_literal": target.is_ip_literal,
        "resolved_ips": target.resolved_ips,
        "features": features,
        "http": http,
        "html": html,
        "favicon": favicon,
        "browser": browser,
        "ml": url_ml,
        "signals": findings,
        "stages": stages,
        "limitations": list(dict.fromkeys(limitations)),
        "content_extracted": bool(http.get("available")),
    }
