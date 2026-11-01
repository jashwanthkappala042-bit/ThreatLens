"""ThreatLens backend configuration.

All values can be overridden with environment variables (see /.env.example).
Optional capabilities are disabled by default.
"""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent


def _bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _sqlite_url(path: Path) -> str:
    return "sqlite:///" + path.as_posix()


class Config:
    ENV = os.getenv("FLASK_ENV", "development")
    DEBUG = _bool("FLASK_DEBUG", False)
    TESTING = False

    # --- Secrets (override in .env; defaults are development-only) ----------
    SECRET_KEY = os.getenv("SECRET_KEY", "threatlens-dev-secret-change-me")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", SECRET_KEY)
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(seconds=_int("JWT_ACCESS_TOKEN_EXPIRES", 3600))

    # --- Storage ------------------------------------------------------------
    STORAGE_DIR = Path(os.getenv("STORAGE_DIR", BACKEND_DIR / "storage"))
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        _sqlite_url(BACKEND_DIR / "instance" / "threatlens.db"),
    )
    AUTO_INIT_DB = _bool("AUTO_INIT_DB", True)

    # --- HTTP / CORS --------------------------------------------------------
    CORS_ORIGINS = [
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        ).split(",")
        if origin.strip()
    ]

    # --- Upload limits ------------------------------------------------------
    MAX_CONTENT_LENGTH = _int("MAX_CONTENT_LENGTH", 6 * 1024 * 1024)  # 6 MB request
    MAX_IMAGE_BYTES = _int("MAX_IMAGE_BYTES", 5 * 1024 * 1024)
    MAX_IMAGE_PIXELS = _int("MAX_IMAGE_PIXELS", 25_000_000)
    MAX_TEXT_CHARS = _int("MAX_TEXT_CHARS", 20_000)

    # --- Safe URL fetching --------------------------------------------------
    HTTP_CONNECT_TIMEOUT = _float("HTTP_CONNECT_TIMEOUT", 4.0)
    HTTP_READ_TIMEOUT = _float("HTTP_READ_TIMEOUT", 8.0)
    MAX_REDIRECTS = _int("MAX_REDIRECTS", 5)
    MAX_RESPONSE_BYTES = _int("MAX_RESPONSE_BYTES", 2 * 1024 * 1024)
    DNS_TIMEOUT = _float("DNS_TIMEOUT", 5.0)
    ALLOWED_PORTS = {80, 443}
    # Never enable this outside of isolated tests. It permits scanning
    # loopback/private addresses (e.g. a local fixture server).
    ALLOW_PRIVATE_NETWORK_TARGETS = _bool("ALLOW_PRIVATE_NETWORK_TARGETS", False)

    # --- Optional capabilities ---------------------------------------------
    ENABLE_BROWSER_SCAN = _bool("ENABLE_BROWSER_SCAN", False)
    BROWSER_TIMEOUT_MS = _int("BROWSER_TIMEOUT_MS", 15_000)
    BROWSER_SETTLE_MS = _int("BROWSER_SETTLE_MS", 1_500)
    ENABLE_OCR = _bool("ENABLE_OCR", False)
    ENABLE_EXTERNAL_REPUTATION = _bool("ENABLE_EXTERNAL_REPUTATION", False)
    URL_MODEL_PATH = os.getenv(
        "URL_MODEL_PATH", str(PROJECT_ROOT / "ml" / "models" / "url_model.joblib")
    )
    EMAIL_MODEL_PATH = os.getenv(
        "EMAIL_MODEL_PATH", str(PROJECT_ROOT / "ml" / "models" / "email_model.joblib")
    )
    SMS_MODEL_PATH = os.getenv(
        "SMS_MODEL_PATH", str(PROJECT_ROOT / "ml" / "models" / "sms_model.joblib")
    )
    # Body-only messages at or below this length use the 3-class SMS model
    # instead of the binary email model.
    SMS_MAX_CHARS = _int("SMS_MAX_CHARS", 700)

    # --- Analysis bounds ----------------------------------------------------
    MAX_EXTRACTED_URLS_EMAIL = _int("MAX_EXTRACTED_URLS_EMAIL", 3)
    MAX_EXTRACTED_URLS_IMAGE = _int("MAX_EXTRACTED_URLS_IMAGE", 3)

    # --- Rate limits: (scope -> (limit, window_seconds)) --------------------
    RATE_LIMITS = {
        "auth": (_int("RATE_LIMIT_AUTH", 10), 60),
        "scan": (_int("RATE_LIMIT_SCAN", 20), 60),
        "community": (_int("RATE_LIMIT_COMMUNITY", 20), 60),
        "complaint": (_int("RATE_LIMIT_COMPLAINT", 10), 60),
    }

    # --- Community moderation ----------------------------------------------
    REPORTS_TO_FLAG = _int("REPORTS_TO_FLAG", 3)


class TestConfig(Config):
    TESTING = True
    DEBUG = False
    AUTO_INIT_DB = False
    SECRET_KEY = "test-secret-key-that-is-long-enough-for-hs256"
    JWT_SECRET_KEY = "test-jwt-secret-key-that-is-long-enough-for-hs256"
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=30)
    DATABASE_URL = "sqlite:///:memory:"
    ALLOW_PRIVATE_NETWORK_TARGETS = False
    ENABLE_BROWSER_SCAN = False
    ENABLE_OCR = False
    # Tests must not depend on whether real artifacts happen to exist locally.
    URL_MODEL_PATH = str(PROJECT_ROOT / "ml" / "models" / "__test_missing_url_model.joblib")
    EMAIL_MODEL_PATH = str(PROJECT_ROOT / "ml" / "models" / "__test_missing_email_model.joblib")
    SMS_MODEL_PATH = str(PROJECT_ROOT / "ml" / "models" / "__test_missing_sms_model.joblib")
    RATE_LIMITS = {key: (10_000, 60) for key in Config.RATE_LIMITS}
