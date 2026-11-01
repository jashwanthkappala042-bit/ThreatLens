"""ThreatLens Flask application factory."""

from __future__ import annotations

import logging
from pathlib import Path

from flask import Flask, request
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from sqlalchemy import text
from werkzeug.exceptions import HTTPException

from .config import Config
from .database import close_session, create_all, get_session, init_engine
from .responses import ApiError, failure, success
from .scanners import browser_scanner
from .security import limiter
from .utils.text import utcnow_iso


def create_app(config_object=Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_object)

    logging.basicConfig(level=logging.INFO)
    if app.config.get("SECRET_KEY", "").startswith("threatlens-dev-"):
        app.logger.warning(
            "Using the development SECRET_KEY. Set SECRET_KEY and JWT_SECRET_KEY in .env "
            "before any non-local use."
        )

    database_url = app.config["DATABASE_URL"]
    if database_url.startswith("sqlite:///") and ":memory:" not in database_url:
        db_path = Path(database_url.replace("sqlite:///", "", 1))
        db_path.parent.mkdir(parents=True, exist_ok=True)
    init_engine(database_url)
    if app.config.get("AUTO_INIT_DB", True):
        create_all()

    storage = Path(app.config["STORAGE_DIR"])
    (storage / "complaints").mkdir(parents=True, exist_ok=True)

    CORS(
        app,
        resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}},
        supports_credentials=False,
        allow_headers=["Content-Type", "Authorization"],
        methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        expose_headers=["Content-Disposition"],
    )

    jwt = JWTManager(app)

    @jwt.unauthorized_loader
    def _missing_token(_reason):
        return failure("authentication_required", "Sign in to continue.", 401)

    @jwt.invalid_token_loader
    def _invalid_token(_reason):
        return failure("invalid_token", "Authentication token is invalid.", 401)

    @jwt.expired_token_loader
    def _expired_token(_header, _payload):
        return failure("token_expired", "Your session expired. Sign in again.", 401)

    @jwt.revoked_token_loader
    def _revoked_token(_header, _payload):
        return failure("token_revoked", "Authentication token is no longer valid.", 401)

    @jwt.needs_fresh_token_loader
    def _fresh_token_required(_header, _payload):
        return failure("fresh_token_required", "Please re-authenticate to continue.", 401)

    from .routes.auth import bp as auth_bp
    from .routes.community import bp as community_bp
    from .routes.complaints import bp as complaints_bp
    from .routes.dashboard import bp as dashboard_bp
    from .routes.profile import bp as profile_bp
    from .routes.scans import bp as scans_bp
    from .routes.scans import history_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(scans_bp)
    app.register_blueprint(history_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(community_bp)
    app.register_blueprint(complaints_bp)
    app.register_blueprint(profile_bp)

    @app.get("/api/health")
    def health():
        database_ok = True
        database_error = ""
        try:
            get_session().execute(text("SELECT 1"))
        except Exception:
            database_ok = False
            database_error = "Database check failed."
        browser = browser_scanner.availability()
        try:
            import importlib.util

            ocr_installed = importlib.util.find_spec("easyocr") is not None
        except Exception:
            ocr_installed = False
        try:
            from .services.scan_service import model_capabilities

            local_models = model_capabilities()
        except Exception:
            local_models = {}
        return success(
            {
                "service": "threatlens-api",
                "version": "1.0.0",
                "time": utcnow_iso(),
                "database": {"ok": database_ok, "error": database_error},
                "capabilities": {
                    "browser_analysis": browser,
                    "ocr": {
                        "enabled": bool(app.config.get("ENABLE_OCR")),
                        "installed": ocr_installed,
                        "note": "EasyOCR downloads model weights on first use when enabled.",
                    },
                    "qr_decoding": {"opencv": True},
                    "external_reputation": {
                        "enabled": bool(app.config.get("ENABLE_EXTERNAL_REPUTATION")),
                        "configured": False,
                    },
                    "local_models": local_models,
                },
            }
        )

    @app.get("/api")
    def api_index():
        return success(
            {
                "name": "ThreatLens API",
                "docs": "See README.md for endpoint documentation.",
                "health": "/api/health",
            }
        )

    @app.errorhandler(ApiError)
    def handle_api_error(exc: ApiError):
        if exc.status >= 500:
            app.logger.error("API error %s: %s", exc.code, exc.message)
        return failure(exc.code, exc.message, exc.status, exc.details)

    @app.errorhandler(HTTPException)
    def handle_http_error(exc: HTTPException):
        code = {
            400: "bad_request",
            401: "authentication_required",
            403: "forbidden",
            404: "not_found",
            405: "method_not_allowed",
            413: "payload_too_large",
            415: "unsupported_media_type",
            429: "rate_limited",
        }.get(exc.code, "http_error")
        return failure(code, exc.description or "Request failed.", exc.code or 500)

    @app.errorhandler(Exception)
    def handle_unexpected_error(exc: Exception):
        app.logger.exception("Unhandled server error")
        return failure(
            "internal_error",
            "An internal error occurred. The details were not exposed.",
            500,
        )

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if request.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        if request.is_secure:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
        return response

    @app.teardown_appcontext
    def _teardown(exc):
        close_session(exc)

    @app.cli.command("init-db")
    def init_db_command():
        """Create database tables without starting the server."""
        create_all()
        print("ThreatLens database initialised.")

    @app.cli.command("reset-rate-limits")
    def reset_rates():
        """Clear in-process rate limiter buckets (development helper)."""
        limiter.reset()
        print("Rate limiter reset.")

    return app
