"""Authentication routes: register, login and current user."""

from __future__ import annotations

from flask import Blueprint, request
from flask_jwt_extended import create_access_token, get_jwt_identity
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from ..database import get_session
from ..models import User, utcnow
from ..responses import ApiError, success
from ..security import (
    audit,
    get_current_user,
    rate_limit,
    validate_display_name,
    validate_email_address,
    validate_password,
)
from ..serializers import user_public

bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def _token_response(user: User, message: str | None = None):
    token = create_access_token(identity=str(user.id), additional_claims={"role": user.role})
    from flask import current_app

    expires = int(current_app.config["JWT_ACCESS_TOKEN_EXPIRES"].total_seconds())
    return success(
        {"access_token": token, "token_type": "Bearer", "expires_in": expires, "user": user_public(user)},
        message=message,
    )


@bp.post("/register")
@rate_limit("auth")
def register():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ApiError("invalid_request", "Send a JSON object.", 400)
    email = validate_email_address(str(payload.get("email", "")))
    password = validate_password(payload.get("password", ""))
    display_name = validate_display_name(str(payload.get("display_name", "") or email.split("@")[0]))

    session = get_session()
    existing = session.scalar(select(User).where(User.email == email))
    if existing is not None:
        raise ApiError("email_in_use", "An account with this email already exists.", 409)

    user = User(
        email=email,
        password_hash=generate_password_hash(password),
        display_name=display_name,
        role="user",
        created_at=utcnow(),
    )
    session.add(user)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise ApiError("email_in_use", "An account with this email already exists.", 409)
    audit("auth.register.success", user_id=user.id)
    return _token_response(user, "Account created.")


@bp.post("/login")
@rate_limit("auth")
def login():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ApiError("invalid_request", "Send a JSON object.", 400)
    email = str(payload.get("email", "")).strip().lower()
    password = payload.get("password", "")
    if not email or not isinstance(password, str) or not password:
        raise ApiError("invalid_credentials", "Invalid email or password.", 401)

    session = get_session()
    user = session.scalar(select(User).where(User.email == email))
    if user is None or not check_password_hash(user.password_hash, password):
        audit("auth.login.failure")
        raise ApiError("invalid_credentials", "Invalid email or password.", 401)

    audit("auth.login.success", user_id=user.id)
    return _token_response(user, "Signed in.")


@bp.get("/me")
def me():
    user = get_current_user()
    if user is None:  # pragma: no cover - protected in practice
        raise ApiError("authentication_required", "Sign in to continue.", 401)
    return success({"user": user_public(user)})


@bp.post("/logout")
def logout():
    # JWTs are stateless; logout is completed by discarding the token on the
    # client. This endpoint only records the audit event for transparency.
    user = get_current_user(optional=True)
    if user is not None:
        audit("auth.logout", user_id=user.id)
    return success(
        {"logged_out": True, "client_action": "discard_access_token"},
        message="Signed out. Discard the access token on the client.",
    )
