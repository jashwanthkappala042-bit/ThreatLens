"""Complaint-draft generation, ownership and PDF tests."""

from __future__ import annotations

from datetime import date, timedelta

from tests.conftest import auth_header, register_user


def valid_payload(**overrides):
    payload = {
        "incident_date": (date.today() - timedelta(days=2)).isoformat(),
        "incident_category": "phishing",
        "suspect_url": "https://example.com/login",
        "description": (
            "I received a message asking me to sign in to a fake account page. "
            "I did not enter any details."
        ),
        "evidence": "Screenshot retained locally.",
        "financial_loss": "",
    }
    payload.update(overrides)
    return payload


def test_generate_requires_authentication(client):
    response = client.post("/api/complaints/generate", json=valid_payload())
    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "authentication_required"
    assert client.get("/api/complaints").status_code == 401


def test_generate_validates_input(client, auth):
    cases = [
        ({"incident_date": (date.today() + timedelta(days=1)).isoformat()}, "invalid_date"),
        ({"incident_date": "02-01-2026"}, "invalid_date"),
        ({"incident_category": "made_up"}, "invalid_category"),
        ({"description": "too short"}, "invalid_description"),
        ({"suspect_url": "http://127.0.0.1/admin"}, "blocked_address"),
        ({"incident_category": "financial_fraud", "financial_loss": ""}, "invalid_loss"),
    ]
    for overrides, expected in cases:
        response = client.post(
            "/api/complaints/generate",
            json=valid_payload(**overrides),
            headers=auth["headers"],
        )
        assert response.status_code == 422, (overrides, response.get_json())
        assert response.get_json()["error"]["code"] == expected


def test_generated_draft_is_private_and_downloadable(client, auth):
    response = client.post("/api/complaints/generate", json=valid_payload(), headers=auth["headers"])
    assert response.status_code == 201, response.get_json()
    complaint = response.get_json()["data"]
    assert complaint["status"] == "draft_not_submitted"
    assert "did not submit" in complaint["notice"]
    assert complaint["suspect_url"] == "https://example.com/login"

    listing = client.get("/api/complaints", headers=auth["headers"]).get_json()
    assert listing["meta"]["total"] == 1
    assert listing["data"][0]["id"] == complaint["id"]

    pdf = client.get(f"/api/complaints/{complaint['id']}/pdf", headers=auth["headers"])
    assert pdf.status_code == 200
    assert pdf.headers["Content-Type"].startswith("application/pdf")
    assert pdf.data.startswith(b"%PDF")
    assert len(pdf.data) > 1500

    token_b, _user_b = register_user(client, email="intruder@example.com", name="Intruder")
    other = auth_header(token_b)
    assert client.get(f"/api/complaints/{complaint['id']}", headers=other).status_code == 403
    assert client.get(f"/api/complaints/{complaint['id']}/pdf", headers=other).status_code == 403
    assert client.get("/api/complaints", headers=other).get_json()["meta"]["total"] == 0


def test_missing_draft_returns_404(client, auth):
    response = client.get("/api/complaints/does-not-exist", headers=auth["headers"])
    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "complaint_not_found"


def test_incident_date_and_optional_evidence_are_stored(client, auth):
    response = client.post(
        "/api/complaints/generate",
        json=valid_payload(
            incident_category="financial_fraud",
            financial_loss="INR 4,500",
            evidence="",
            suspect_url="",
        ),
        headers=auth["headers"],
    )
    assert response.status_code == 201
    data = response.get_json()["data"]
    assert data["incident_category_label"] == "Financial fraud / payment scam"
    assert data["financial_loss"] == "INR 4,500"
    assert data["suspect_url"] == ""
