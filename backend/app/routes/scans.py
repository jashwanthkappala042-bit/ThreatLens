"""Scan submission, analysis retrieval and history routes."""

from __future__ import annotations

import io

from flask import Blueprint, current_app, request, send_file
from sqlalchemy import func, select
from werkzeug.utils import secure_filename

from ..database import get_session
from ..models import Scan
from ..responses import ApiError, success
from ..scanners.image_scanner import InvalidImage
from ..security import audit, get_current_user, rate_limit
from ..serializers import scan_full, scan_summary
from ..services.report_pdf import build_scan_report_pdf
from ..services.scan_service import run_email_scan, run_image_scan, run_url_scan, scan_access_allowed
from ..utils.url_safety import InvalidTarget

bp = Blueprint("scans", __name__, url_prefix="/api")
history_bp = Blueprint("history", __name__, url_prefix="/api/history")

CLASSIFICATIONS = {"no_significant_indicators", "suspicious", "malicious", "unknown"}
INPUT_TYPES = {"url", "email", "image"}


def _json_object() -> dict:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ApiError("invalid_request", "Send a JSON object.", 400)
    return payload


def _get_scan(scan_id: str) -> Scan:
    scan = get_session().get(Scan, scan_id)
    if scan is None:
        raise ApiError("scan_not_found", "That scan does not exist.", 404)
    return scan


@bp.post("/scan/url")
@rate_limit("scan")
def scan_url():
    user = get_current_user(optional=True)
    payload = _json_object()
    raw_url = payload.get("url")
    if not isinstance(raw_url, str) or not raw_url.strip():
        raise ApiError("invalid_url", "Enter a URL to scan.", 422)
    try:
        scan = run_url_scan(raw_url.strip(), user.id if user else None)
    except InvalidTarget as exc:
        raise ApiError(exc.code, exc.message, 422)
    audit("scan.url.created", detail=f"scan={scan.id} classification={scan.classification}", user_id=user.id if user else None)
    return success(scan_full(scan), status=201)


@bp.post("/scan/email")
@rate_limit("scan")
def scan_email():
    user = get_current_user(optional=True)
    payload = _json_object()
    subject = payload.get("subject") or ""
    sender = payload.get("sender") or ""
    body = payload.get("body")
    if body is None:
        body = payload.get("text") or ""
    if not all(isinstance(value, str) for value in (subject, sender, body)):
        raise ApiError("invalid_request", "Subject, sender and body must be text.", 422)
    if not subject.strip() and not body.strip():
        raise ApiError("empty_message", "Provide a subject or message body to analyze.", 422)
    max_chars = int(current_app.config.get("MAX_TEXT_CHARS", 20_000))
    if len(body) > max_chars:
        raise ApiError("message_too_long", f"Message text must be {max_chars} characters or fewer.", 422)
    scan = run_email_scan(subject[:300], sender[:300], body, user.id if user else None)
    audit("scan.email.created", detail=f"scan={scan.id} classification={scan.classification}", user_id=user.id if user else None)
    return success(scan_full(scan), status=201)


@bp.post("/scan/image")
@rate_limit("scan")
def scan_image():
    user = get_current_user(optional=True)
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        raise ApiError("missing_file", "Attach an image file to scan.", 422)
    max_bytes = int(current_app.config.get("MAX_IMAGE_BYTES", 5 * 1024 * 1024))
    data = upload.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ApiError("file_too_large", f"The image must be {max_bytes // (1024 * 1024)} MB or smaller.", 413)
    filename = secure_filename(upload.filename) or "upload"
    try:
        scan = run_image_scan(data, filename, upload.mimetype or "", user.id if user else None)
    except InvalidImage as exc:
        raise ApiError(exc.code, exc.message, 422)
    audit("scan.image.created", detail=f"scan={scan.id} classification={scan.classification}", user_id=user.id if user else None)
    return success(scan_full(scan), status=201)


@bp.get("/analysis/<scan_id>")
def analysis(scan_id: str):
    user = get_current_user(optional=True)
    scan = _get_scan(scan_id)
    if not scan_access_allowed(scan, user):
        raise ApiError("forbidden", "You do not have access to this scan.", 403)
    return success(scan_full(scan))


@bp.get("/scan/<scan_id>/status")
def scan_status(scan_id: str):
    user = get_current_user(optional=True)
    scan = _get_scan(scan_id)
    if not scan_access_allowed(scan, user):
        raise ApiError("forbidden", "You do not have access to this scan.", 403)
    return success(
        {
            "id": scan.id,
            "status": scan.status,
            "classification": scan.classification,
            "risk_score": scan.risk_score,
            "completed_at": scan.completed_at.isoformat() if scan.completed_at else None,
            "note": "Scans run synchronously and are persisted only after analysis completes.",
        }
    )


@bp.get("/scan/<scan_id>/report.pdf")
def scan_report_pdf(scan_id: str):
    user = get_current_user(optional=True)
    scan = _get_scan(scan_id)
    if not scan_access_allowed(scan, user):
        raise ApiError("forbidden", "You do not have access to this scan.", 403)
    pdf = build_scan_report_pdf(scan)
    return send_file(
        io.BytesIO(pdf),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"threatlens-report-{scan.id[:8]}.pdf",
    )


@history_bp.get("")
@history_bp.get("/")
def history_list():
    user = get_current_user()
    page = max(1, request.args.get("page", default=1, type=int) or 1)
    per_page = min(50, max(1, request.args.get("per_page", default=10, type=int) or 10))
    classification = request.args.get("classification", "").strip()
    input_type = request.args.get("input_type", "").strip()
    search = request.args.get("q", "").strip()

    filters = [Scan.user_id == user.id]
    if classification in CLASSIFICATIONS:
        filters.append(Scan.classification == classification)
    if input_type in INPUT_TYPES:
        filters.append(Scan.input_type == input_type)
    if search:
        filters.append(Scan.input_label.ilike(f"%{search[:100]}%"))

    session = get_session()
    total = session.scalar(select(func.count()).select_from(Scan).where(*filters)) or 0
    scans = list(
        session.scalars(
            select(Scan)
            .where(*filters)
            .order_by(Scan.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
    )
    return success(
        [scan_summary(scan) for scan in scans],
        meta={
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": max(1, (total + per_page - 1) // per_page),
        },
    )


@history_bp.delete("/<scan_id>")
def history_delete(scan_id: str):
    user = get_current_user()
    scan = _get_scan(scan_id)
    if scan.user_id != user.id and not user.is_admin:
        raise ApiError("forbidden", "You can only delete your own scan history.", 403)
    session = get_session()
    session.delete(scan)
    session.commit()
    audit("scan.deleted", detail=f"scan={scan_id}", user_id=user.id)
    return success({"deleted": scan_id}, message="Scan deleted.")
