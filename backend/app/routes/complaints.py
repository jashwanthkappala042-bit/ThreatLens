"""Cybercrime complaint draft preparation (local PDF generation only)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from flask import Blueprint, current_app, request, send_file
from sqlalchemy import func, select

from ..database import get_session
from ..models import ComplaintDraft, utcnow
from ..responses import ApiError, success
from ..security import audit, get_current_user, rate_limit
from ..services.report_pdf import build_complaint_pdf
from ..utils.text import iso
from ..utils.url_safety import InvalidTarget, validate_url

bp = Blueprint("complaints", __name__, url_prefix="/api/complaints")

CATEGORIES = {
    "phishing": "Phishing or fraudulent website",
    "financial_fraud": "Financial fraud / payment scam",
    "identity_theft": "Identity theft",
    "account_takeover": "Account takeover",
    "cyberbullying": "Harassment or cyberbullying",
    "other": "Other cybercrime",
}


def _payload(complaint: ComplaintDraft) -> dict:
    return {
        "id": complaint.id,
        "incident_date": complaint.incident_date,
        "incident_category": complaint.incident_category,
        "incident_category_label": CATEGORIES.get(complaint.incident_category, complaint.incident_category),
        "suspect_url": complaint.suspect_url,
        "description": complaint.description,
        "evidence": complaint.evidence,
        "financial_loss": complaint.financial_loss,
        "created_at": iso(complaint.created_at),
        "download_url": f"/api/complaints/{complaint.id}/pdf",
        "status": "draft_not_submitted",
        "notice": (
            "This is a locally generated draft for your review. ThreatLens did not submit it to any "
            "authority."
        ),
    }


def _owned_complaint(complaint_id: str) -> ComplaintDraft:
    user = get_current_user()
    complaint = get_session().get(ComplaintDraft, complaint_id)
    if complaint is None:
        raise ApiError("complaint_not_found", "That complaint draft does not exist.", 404)
    if complaint.user_id != user.id and not user.is_admin:
        raise ApiError("forbidden", "You do not have access to this complaint draft.", 403)
    return complaint


@bp.post("/generate")
@rate_limit("complaint")
def generate():
    user = get_current_user()
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ApiError("invalid_request", "Send a JSON object.", 400)

    incident_date = str(payload.get("incident_date", "")).strip()
    try:
        parsed_date = datetime.strptime(incident_date, "%Y-%m-%d").date()
    except ValueError:
        raise ApiError("invalid_date", "Incident date must use the YYYY-MM-DD format.", 422)
    if parsed_date > datetime.now(timezone.utc).date():
        raise ApiError("invalid_date", "Incident date cannot be in the future.", 422)

    category = str(payload.get("incident_category", "")).strip()
    if category not in CATEGORIES:
        raise ApiError("invalid_category", "Select a valid incident category.", 422)

    description = str(payload.get("description", "")).strip()
    if len(description) < 20:
        raise ApiError("invalid_description", "Describe the incident in at least 20 characters.", 422)
    if len(description) > 5000:
        raise ApiError("invalid_description", "Description must be 5000 characters or fewer.", 422)

    evidence = str(payload.get("evidence", "") or "").strip()
    if len(evidence) > 5000:
        raise ApiError("invalid_evidence", "Evidence notes must be 5000 characters or fewer.", 422)

    financial_loss = str(payload.get("financial_loss", "") or "").strip()[:120]
    if category == "financial_fraud" and not financial_loss:
        raise ApiError("invalid_loss", "Provide an approximate loss amount for financial fraud.", 422)

    suspect_url = ""
    raw_url = str(payload.get("suspect_url", "") or "").strip()
    if raw_url:
        try:
            suspect_url = validate_url(raw_url, resolve=False).normalized_url
        except InvalidTarget as exc:
            raise ApiError(exc.code, exc.message, 422)

    complaint = ComplaintDraft(
        user_id=user.id,
        incident_date=parsed_date.isoformat(),
        incident_category=category,
        suspect_url=suspect_url,
        description=description,
        evidence=evidence,
        financial_loss=financial_loss,
        created_at=utcnow(),
    )
    session = get_session()
    session.add(complaint)
    session.flush()

    storage = Path(current_app.config["STORAGE_DIR"]) / "complaints"
    storage.mkdir(parents=True, exist_ok=True)
    filename = f"{complaint.id}.pdf"
    pdf = build_complaint_pdf(complaint, user)
    (storage / filename).write_bytes(pdf)
    complaint.pdf_filename = filename
    session.commit()
    audit("complaint.generated", detail=f"complaint={complaint.id}", user_id=user.id)
    return success(_payload(complaint), status=201)


@bp.get("")
@bp.get("/")
def list_complaints():
    user = get_current_user()
    page = max(1, request.args.get("page", default=1, type=int) or 1)
    per_page = min(50, max(1, request.args.get("per_page", default=10, type=int) or 10))
    session = get_session()
    total = (
        session.scalar(
            select(func.count()).select_from(ComplaintDraft).where(ComplaintDraft.user_id == user.id)
        )
        or 0
    )
    rows = list(
        session.scalars(
            select(ComplaintDraft)
            .where(ComplaintDraft.user_id == user.id)
            .order_by(ComplaintDraft.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
    )
    return success(
        [_payload(row) for row in rows],
        meta={
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": max(1, (total + per_page - 1) // per_page),
        },
    )


@bp.get("/<complaint_id>")
def get_complaint(complaint_id: str):
    return success(_payload(_owned_complaint(complaint_id)))


@bp.get("/<complaint_id>/pdf")
def complaint_pdf(complaint_id: str):
    complaint = _owned_complaint(complaint_id)
    if not complaint.pdf_filename:
        raise ApiError("pdf_missing", "The PDF for this complaint is not available.", 404)
    storage = Path(current_app.config["STORAGE_DIR"]) / "complaints"
    path = (storage / complaint.pdf_filename).resolve()
    if storage.resolve() not in path.parents or not path.exists():
        raise ApiError("pdf_missing", "The PDF for this complaint is not available.", 404)
    return send_file(
        path,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"threatlens-complaint-draft-{complaint.id[:8]}.pdf",
    )
