"""Shared pytest fixtures for the ThreatLens backend."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app import create_app  # noqa: E402
from app.config import TestConfig  # noqa: E402
from app.database import create_all  # noqa: E402
from app.security import limiter  # noqa: E402


@pytest.fixture()
def app(tmp_path):
    limiter.reset()
    application = create_app(TestConfig)
    application.config["STORAGE_DIR"] = tmp_path / "storage"
    with application.app_context():
        create_all()
    yield application


@pytest.fixture()
def client(app):
    return app.test_client()


def register_user(client, email="analyst@example.com", password="StrongPass123", name="Analyst"):
    response = client.post(
        "/api/auth/register",
        json={"email": email, "password": password, "display_name": name},
    )
    assert response.status_code == 200, response.get_json()
    data = response.get_json()["data"]
    return data["access_token"], data["user"]


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def auth(client):
    token, user = register_user(client)
    return {"headers": auth_header(token), "token": token, "user": user}


def make_admin(app, user_id: int) -> None:
    from app.database import get_session
    from app.models import User

    with app.app_context():
        session = get_session()
        user = session.get(User, user_id)
        user.role = "admin"
        session.commit()
