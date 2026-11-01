"""Authentication, authorization and profile tests."""

from __future__ import annotations

from tests.conftest import auth_header, register_user


def test_health_is_public(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    assert body["data"]["database"]["ok"] is True


def test_register_login_and_me(client):
    token, user = register_user(client, email="new@example.com", name="New User")
    assert user["email"] == "new@example.com"
    assert "password_hash" not in str(user)

    me = client.get("/api/auth/me", headers=auth_header(token))
    assert me.status_code == 200
    assert me.get_json()["data"]["user"]["email"] == "new@example.com"

    login = client.post(
        "/api/auth/login", json={"email": "new@example.com", "password": "StrongPass123"}
    )
    assert login.status_code == 200
    assert login.get_json()["data"]["access_token"]


def test_duplicate_email_and_weak_password_rejected(client):
    register_user(client, email="dupe@example.com")
    duplicate = client.post(
        "/api/auth/register",
        json={"email": "dupe@example.com", "password": "StrongPass123", "display_name": "Dupe"},
    )
    assert duplicate.status_code == 409
    assert duplicate.get_json()["error"]["code"] == "email_in_use"

    weak = client.post(
        "/api/auth/register",
        json={"email": "weak@example.com", "password": "short", "display_name": "Weak"},
    )
    assert weak.status_code == 422
    assert weak.get_json()["error"]["code"] == "weak_password"


def test_wrong_password_uses_generic_error(client):
    register_user(client, email="login@example.com")
    response = client.post(
        "/api/auth/login", json={"email": "login@example.com", "password": "WrongPass123"}
    )
    assert response.status_code == 401
    assert response.get_json()["error"]["message"] == "Invalid email or password."


def test_protected_endpoint_requires_token(client):
    response = client.get("/api/history")
    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "authentication_required"


def test_profile_update_and_password_change(client, auth):
    headers = auth["headers"]
    response = client.patch("/api/profile", json={"display_name": "Renamed Analyst"}, headers=headers)
    assert response.status_code == 200
    assert response.get_json()["data"]["user"]["display_name"] == "Renamed Analyst"

    wrong = client.patch(
        "/api/profile",
        json={"current_password": "bad", "new_password": "AnotherPass456"},
        headers=headers,
    )
    assert wrong.status_code == 401

    changed = client.patch(
        "/api/profile",
        json={"current_password": "StrongPass123", "new_password": "AnotherPass456"},
        headers=headers,
    )
    assert changed.status_code == 200
    login = client.post(
        "/api/auth/login",
        json={"email": "analyst@example.com", "password": "AnotherPass456"},
    )
    assert login.status_code == 200


def test_auth_rate_limit_returns_429(tmp_path):
    from app import create_app
    from app.config import TestConfig
    from app.database import create_all
    from app.security import limiter

    class LimitedConfig(TestConfig):
        RATE_LIMITS = {key: (1, 60) for key in TestConfig.RATE_LIMITS}

    limiter.reset()
    limited = create_app(LimitedConfig)
    limited.config["STORAGE_DIR"] = tmp_path
    with limited.app_context():
        create_all()
    client = limited.test_client()
    first = client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "x"})
    assert first.status_code == 401
    second = client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "x"})
    assert second.status_code == 429
    assert second.get_json()["error"]["code"] == "rate_limited"
