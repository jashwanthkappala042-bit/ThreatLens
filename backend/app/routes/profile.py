"""Profile retrieval and updates."""

from __future__ import annotations

from flask import Blueprint, request
from sqlalchemy import func, select
from werkzeug.security import check_password_hash, generate_password_hash

from ..database import get_session
from ..models import ComplaintDraft, CommunityPost, Scan
from ..responses import ApiError, success
from ..security import (
    audit,
    get_current_user,
    rate_limit,
    validate_display_name,
    validate_password,
)
from ..serializers import user_public

bp = Blueprint("profile", __name__, url_prefix="/api/profile")


def _profile_payload(user) -> dict:
    session = get_session()
    return {
        "user": user_public(user),
        "counts": {
            "scans": session.scalar(
                select(func.count()).select_from(Scan).where(Scan.user_id == user.id)
            )
            or 0,
            "posts": session.scalar(
                select(func.count()).select_from(CommunityPost).where(CommunityPost.user_id == user.id)
            )
            or 0,
            "complaints": session.scalar(
                select(func.count()).select_from(ComplaintDraft).where(ComplaintDraft.user_id == user.id)
            )
            or 0,
        },
    }


@bp.get("")
@bp.get("/")
def get_profile():
    user = get_current_user()
    return success(_profile_payload(user))


@bp.patch("")
@bp.patch("/")
@rate_limit("auth")
def update_profile():
    user = get_current_user()
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ApiError("invalid_request", "Send a JSON object.", 400)

    changed = False
    if "display_name" in payload:
        user.display_name = validate_display_name(str(payload.get("display_name", "")))
        changed = True

    new_password = payload.get("new_password")
    if new_password:
        current_password = payload.get("current_password", "")
        if not isinstance(current_password, str) or not check_password_hash(
            user.password_hash, current_password
        ):
            raise ApiError("invalid_credentials", "Current password is incorrect.", 401)
        validate_password(new_password)
        user.password_hash = generate_password_hash(new_password)
        changed = True

    if not changed:
        raise ApiError("no_changes", "Provide a display name or a new password.", 422)

    get_session().commit()
    audit("profile.updated", detail="fields=" + ",".join(sorted(payload.keys())), user_id=user.id)
    return success(_profile_payload(user), message="Profile updated.")
