"""Security helpers: rate limiting, hashing, password policy, audit logging."""

from __future__ import annotations

import hashlib
import hmac
import re
import threading
import time
from collections import defaultdict, deque
from functools import wraps
from typing import Callable

from flask import current_app, request
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

from .database import get_session
from .models import AuditLog, User
from .responses import ApiError

_EMAIL_RE = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$")
_PASSWORD_MIN = 8
_PASSWORD_MAX = 128


class RateLimiter:
    """Small in-process sliding-window limiter.

    Suitable for a single-process local deployment. A multi-process or
    production deployment should use a shared store (Redis) instead.
    """

    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            bucket = self._events[key]
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                retry_after = max(1, int(window_seconds - (now - bucket[0])))
                return False, retry_after
            bucket.append(now)
            # Opportunistic cleanup so idle keys do not grow forever.
            if len(self._events) > 5_000:
                for stale in [k for k, v in self._events.items() if not v or v[-1] < cutoff]:
                    self._events.pop(stale, None)
            return True, 0

    def reset(self) -> None:
        with self._lock:
            self._events.clear()


limiter = RateLimiter()


def rate_limit(scope: str) -> Callable:
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            settings = current_app.config.get("RATE_LIMITS", {})
            limit, window = settings.get(scope, (60, 60))
            client = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
            client = client or request.remote_addr or "unknown"
            allowed, retry_after = limiter.check(f"{scope}:{client}", limit, window)
            if not allowed:
                raise ApiError(
                    "rate_limited",
                    "Too many requests. Please wait and try again.",
                    429,
                    {"retry_after_seconds": retry_after},
                )
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def hash_ip(ip: str | None) -> str:
    if not ip:
        return ""
    salt = current_app.config.get("SECRET_KEY", "")
    return hashlib.sha256(f"{salt}:{ip}".encode("utf-8")).hexdigest()[:32]


def audit(action: str, detail: str = "", user_id: int | None = None) -> None:
    """Record an audit event without secrets or sensitive payloads."""
    try:
        if user_id is None:
            try:
                verify_jwt_in_request(optional=True)
                identity = get_jwt_identity()
                user_id = int(identity) if identity else None
            except Exception:
                user_id = None
        session = get_session()
        session.add(
            AuditLog(
                user_id=user_id,
                action=action[:80],
                detail=detail[:2000],
                ip_hash=hash_ip(request.remote_addr),
            )
        )
        session.commit()
    except Exception:  # pragma: no cover - audit must never break the request
        pass


def validate_email_address(email: str) -> str:
    email = (email or "").strip().lower()
    if len(email) > 254 or not _EMAIL_RE.match(email):
        raise ApiError("invalid_email", "Enter a valid email address.", 422)
    return email


def validate_password(password: str) -> str:
    if not isinstance(password, str) or len(password) < _PASSWORD_MIN:
        raise ApiError(
            "weak_password",
            f"Password must be at least {_PASSWORD_MIN} characters.",
            422,
        )
    if len(password) > _PASSWORD_MAX:
        raise ApiError("weak_password", "Password is too long.", 422)
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        raise ApiError(
            "weak_password",
            "Password must contain at least one letter and one number.",
            422,
        )
    return password


def validate_display_name(name: str) -> str:
    name = re.sub(r"\s+", " ", (name or "").strip())
    if not name:
        raise ApiError("invalid_name", "Display name is required.", 422)
    if len(name) > 60:
        raise ApiError("invalid_name", "Display name must be 60 characters or fewer.", 422)
    if re.search(r"[\x00-\x1f\x7f<>]", name):
        raise ApiError("invalid_name", "Display name contains unsupported characters.", 422)
    return name


def constant_time_compare(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def get_current_user(optional: bool = False) -> User | None:
    verify_jwt_in_request(optional=optional)
    identity = get_jwt_identity()
    if not identity:
        return None
    try:
        user_id = int(identity)
    except (TypeError, ValueError):
        raise ApiError("invalid_token", "Authentication token is invalid.", 401)
    user = get_session().get(User, user_id)
    if user is None:
        raise ApiError("invalid_token", "Authenticated user no longer exists.", 401)
    return user


def require_admin(user: User | None) -> User:
    if user is None:
        raise ApiError("authentication_required", "Sign in to continue.", 401)
    if not user.is_admin:
        raise ApiError("forbidden", "Administrator access is required.", 403)
    return user
