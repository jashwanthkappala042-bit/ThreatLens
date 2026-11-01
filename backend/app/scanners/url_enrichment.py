"""Shared helper: analyze URLs extracted from messages or images."""

from __future__ import annotations

from typing import Any

from flask import current_app

from ..detection import risk_engine
from ..detection.findings import finding
from ..utils.url_safety import InvalidTarget
from .url_scanner import analyze_url


def _summarize(result: dict[str, Any], assessment: dict[str, Any]) -> dict[str, Any]:
    http = result.get("http") or {}
    chain = http.get("redirect_chain") or []
    return {
        "url": result.get("normalized_url") or result.get("input_url", ""),
        "hostname": result.get("hostname", ""),
        "ok": True,
        "classification": assessment["classification"],
        "classification_label": assessment["classification_label"],
        "risk_score": assessment["risk_score"],
        "risk_level": assessment["risk_level"],
        "summary": assessment["summary"],
        "findings": assessment["supporting_findings"][:10],
        "stages": assessment["stages"],
        "limitations": assessment["limitations"],
        "http": {
            "available": bool(http.get("available")),
            "status_code": http.get("status_code"),
            "final_url": http.get("final_url", ""),
            "content_type": http.get("content_type", ""),
            "redirect_count": max(0, len(chain) - 1) if chain else 0,
            "error": http.get("error", ""),
        },
        "html": {
            "available": bool((result.get("html") or {}).get("available")),
            "title": (result.get("html") or {}).get("title", ""),
        },
        "browser": {"available": bool((result.get("browser") or {}).get("available"))},
    }


def analyze_extracted_urls(
    urls: list[str], *, limit: int, source_label: str
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    limitations: list[str] = []
    scanned = 0
    failed = 0
    seen: set[str] = set()
    candidates = []
    for url in urls:
        key = url.lower()
        if key in seen:
            continue
        seen.add(key)
        candidates.append(url)
        if len(candidates) >= limit:
            break

    for url in candidates:
        try:
            result = analyze_url(url)
            assessment = risk_engine.assess("url", result, result.get("signals") or [])
            results.append(_summarize(result, assessment))
            scanned += 1
            if assessment["classification"] == "malicious":
                findings.append(
                    finding(
                        f"embedded_url_malicious_{len(results)}",
                        "Embedded link assessed as high risk",
                        "One of the links extracted from this content was rated high risk by the "
                        "URL analysis pipeline. The link evidence is listed separately.",
                        "critical",
                        "embedded_link",
                        "http",
                        evidence={
                            "url": result.get("normalized_url"),
                            "risk_score": assessment["risk_score"],
                            "source": source_label,
                        },
                    )
                )
            elif assessment["classification"] == "suspicious":
                findings.append(
                    finding(
                        f"embedded_url_suspicious_{len(results)}",
                        "Embedded link assessed as suspicious",
                        "One of the extracted links showed suspicious indicators. Review the link "
                        "details before opening it.",
                        "medium",
                        "embedded_link",
                        "http",
                        evidence={
                            "url": result.get("normalized_url"),
                            "risk_score": assessment["risk_score"],
                            "source": source_label,
                        },
                    )
                )
        except InvalidTarget as exc:
            failed += 1
            results.append(
                {
                    "url": url,
                    "ok": False,
                    "classification": "unknown",
                    "classification_label": "Not scanned",
                    "error": {"code": exc.code, "message": exc.message},
                }
            )
            limitations.append(f"An extracted link was not scanned: {exc.message}")
        except Exception:
            failed += 1
            results.append(
                {
                    "url": url,
                    "ok": False,
                    "classification": "unknown",
                    "classification_label": "Not scanned",
                    "error": {
                        "code": "analysis_failed",
                        "message": "The extracted link could not be analyzed.",
                    },
                }
            )
            limitations.append("An extracted link could not be analyzed due to an internal error.")

    total_candidates = len(urls)
    if total_candidates > len(candidates):
        limitations.append(
            f"Only the first {len(candidates)} of {total_candidates} extracted link(s) were analyzed."
        )

    if not candidates:
        status = "skipped"
        detail = "No URLs were extracted from this content."
    elif failed and not scanned:
        status = "failed"
        detail = f"All {failed} extracted link(s) failed validation or analysis."
    elif failed:
        status = "partial"
        detail = f"{scanned} link(s) analyzed, {failed} could not be analyzed."
    else:
        status = "completed"
        detail = f"{scanned} extracted link(s) analyzed through the protected URL pipeline."

    return {
        "results": results,
        "findings": findings,
        "limitations": limitations,
        "stage": {"name": "Extracted URL analysis", "status": status, "detail": detail},
        "scanned": scanned,
        "failed": failed,
    }
