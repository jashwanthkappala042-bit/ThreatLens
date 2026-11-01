"""Scan orchestration and persistence."""

from __future__ import annotations

import uuid
from typing import Any

from flask import current_app

from ..database import get_session
from ..detection import risk_engine
from ..models import Scan, ScanFinding, utcnow
from ..scanners.email_scanner import analyze_email
from ..scanners.image_scanner import analyze_image
from ..scanners.url_scanner import analyze_url
from ..utils.text import clamp, extract_urls, normalize_whitespace


def _persist(
    *,
    input_type: str,
    input_label: str,
    input_preview: str,
    analysis: dict[str, Any],
    assessment: dict[str, Any],
    user_id: int | None,
) -> Scan:
    session = get_session()
    findings = assessment.get("supporting_findings") or []
    analysis = dict(analysis)
    analysis["assessment"] = assessment

    scan = Scan(
        id=str(uuid.uuid4()),
        user_id=user_id,
        input_type=input_type,
        input_label=clamp(input_label, 500),
        input_preview=clamp(input_preview, 2000),
        status="completed",
        classification=assessment["classification"],
        risk_score=int(assessment["risk_score"]),
        risk_level=assessment["risk_level"],
        summary=clamp(assessment["summary"], 2000),
        findings_count=len(findings),
        analysis=analysis,
        created_at=utcnow(),
        completed_at=utcnow(),
    )
    session.add(scan)
    for item in findings:
        session.add(
            ScanFinding(
                scan_id=scan.id,
                indicator_id=clamp(str(item.get("indicator_id", "")), 100),
                title=clamp(str(item.get("title", "")), 200),
                description=clamp(str(item.get("description", "")), 2000),
                category=clamp(str(item.get("category", "general")), 60),
                severity=clamp(str(item.get("severity", "low")), 20),
                source=clamp(str(item.get("source", "heuristic")), 30),
                weight=float(item.get("weight", 0)),
                evidence=item.get("evidence") or {},
            )
        )
    session.commit()
    return scan


def run_url_scan(url: str, user_id: int | None) -> Scan:
    analysis = analyze_url(url)
    assessment = risk_engine.assess("url", analysis, analysis.get("signals") or [])
    http = analysis.get("http") or {}
    preview_parts = [analysis.get("normalized_url", "")]
    if http.get("available"):
        preview_parts.append(
            f"HTTP {http.get('status_code')} · {http.get('content_type') or 'unknown content type'}"
        )
    html = analysis.get("html") or {}
    if html.get("title"):
        preview_parts.append(html["title"])
    return _persist(
        input_type="url",
        input_label=analysis.get("normalized_url", url),
        input_preview=" · ".join(part for part in preview_parts if part),
        analysis=analysis,
        assessment=assessment,
        user_id=user_id,
    )


def run_email_scan(subject: str, sender: str, body: str, user_id: int | None) -> Scan:
    analysis = analyze_email(subject, sender, body)
    assessment = risk_engine.assess("email", analysis, analysis.get("signals") or [])
    label = subject.strip() or sender.strip() or normalize_whitespace(body)[:120] or "Email / message"
    preview = normalize_whitespace(body)[:300]
    if not preview:
        preview = "No message body supplied."
    return _persist(
        input_type="email",
        input_label=label,
        input_preview=preview,
        analysis=analysis,
        assessment=assessment,
        user_id=user_id,
    )


def run_image_scan(data: bytes, filename: str, declared_type: str, user_id: int | None) -> Scan:
    analysis = analyze_image(data, filename, declared_type)
    assessment = risk_engine.assess("image", analysis, analysis.get("signals") or [])
    extracted = analysis.get("extracted_text") or ""
    preview = normalize_whitespace(extracted)[:300]
    if not preview:
        preview = "No text or QR content was extracted from the image."
    return _persist(
        input_type="image",
        input_label=filename,
        input_preview=preview,
        analysis=analysis,
        assessment=assessment,
        user_id=user_id,
    )


def scan_access_allowed(scan: Scan, user) -> bool:
    if scan.user_id is None:
        return True  # Anonymous scans are retrievable by their unguessable UUID.
    if user is None:
        return False
    return scan.user_id == user.id or bool(getattr(user, "is_admin", False))


def preview_extracted_urls(text: str) -> list[str]:
    return extract_urls(text, limit=10)


def _summarise_model_status(status: dict[str, Any]) -> dict[str, Any]:
    """Return a compact, honest status for the public health endpoint."""
    if not status.get("available"):
        return {"available": False, "reason": status.get("reason", "Model artifact unavailable.")}
    metadata = status.get("metadata") or {}
    metrics = status.get("metrics") or {}
    headline = {
        key: metrics.get(key)
        for key in ("accuracy", "f1_macro", "roc_auc", "roc_auc_ovr_macro", "support")
        if key in metrics
    }
    return {
        "available": True,
        "name": metadata.get("name"),
        "task": metadata.get("task"),
        "algorithm": metadata.get("algorithm"),
        "dataset": metadata.get("dataset"),
        "dataset_license": metadata.get("dataset_license"),
        "trained_at": metadata.get("trained_at"),
        "calibrated": bool(status.get("calibrated", False)),
        "metrics": headline,
    }


def model_capabilities() -> dict[str, Any]:
    from ..detection import ml

    config = current_app.config
    return {
        "url_model": _summarise_model_status(
            ml.model_status(str(config.get("URL_MODEL_PATH", "")))
        ),
        "email_model": _summarise_model_status(
            ml.model_status(str(config.get("EMAIL_MODEL_PATH", "")))
        ),
        "sms_model": _summarise_model_status(
            ml.model_status(str(config.get("SMS_MODEL_PATH", "")))
        ),
    }
