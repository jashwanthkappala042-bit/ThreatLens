"""Scan submission, persistence, history and dashboard tests."""

from __future__ import annotations

from tests.conftest import auth_header, register_user


def email_scan(client, headers, *, sender="Colleague <colleague@company.com>", body="Hi team, the meeting notes are attached."):
    return client.post(
        "/api/scan/email",
        json={"subject": "Meeting notes", "sender": sender, "body": body},
        headers=headers,
    )


def test_benign_email_scan_is_persisted(client, auth):
    response = email_scan(client, auth["headers"])
    assert response.status_code == 201
    data = response.get_json()["data"]
    assert data["input_type"] == "email"
    assert data["classification"] == "no_significant_indicators"
    assert data["analysis"]["assessment"]["score_kind"] == "heuristic_uncalibrated"
    assert data["analysis"]["ml"]["available"] is False
    assert "not a guarantee" in data["summary"].lower() or "not a guarantee" in data["analysis"]["assessment"]["summary"].lower()

    fetched = client.get(f"/api/analysis/{data['id']}", headers=auth["headers"])
    assert fetched.status_code == 200
    assert fetched.get_json()["data"]["id"] == data["id"]

    status = client.get(f"/api/scan/{data['id']}/status", headers=auth["headers"])
    assert status.status_code == 200
    assert status.get_json()["data"]["status"] == "completed"


def test_phishing_email_has_explainable_high_risk(client, auth):
    response = email_scan(
        client,
        auth["headers"],
        sender="PayPal Security <security@paypal-alerts.top>",
        body=(
            "Dear customer, your account will be suspended within 24 hours. "
            "Verify your password and sign in immediately."
        ),
    )
    assert response.status_code == 201
    data = response.get_json()["data"]
    assert data["classification"] in {"suspicious", "malicious"}
    assert data["findings_count"] >= 3
    findings = data["analysis"]["assessment"]["supporting_findings"]
    assert any(item["source"] == "heuristic" for item in findings)
    assert all(item["indicator_id"] for item in findings)
    assert data["analysis"]["assessment"]["decision_trace"]


def test_empty_email_rejected(client, auth):
    response = client.post("/api/scan/email", json={"subject": "", "body": ""}, headers=auth["headers"])
    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "empty_message"


def test_anonymous_scan_is_allowed_and_retrievable_by_uuid(client):
    response = client.post(
        "/api/scan/email",
        json={"body": "Hello, this is a normal message with no links."},
    )
    assert response.status_code == 201
    data = response.get_json()["data"]
    assert data["is_anonymous"] is True
    fetched = client.get(f"/api/analysis/{data['id']}")
    assert fetched.status_code == 200


def test_scan_history_is_user_scoped(client, auth):
    first = email_scan(client, auth["headers"]).get_json()["data"]
    token_b, _user_b = register_user(client, email="other@example.com", name="Other")
    other_headers = auth_header(token_b)

    forbidden = client.get(f"/api/analysis/{first['id']}", headers=other_headers)
    assert forbidden.status_code == 403

    history = client.get("/api/history", headers=auth["headers"])
    assert history.status_code == 200
    assert history.get_json()["meta"]["total"] == 1
    other_history = client.get("/api/history", headers=other_headers)
    assert other_history.get_json()["meta"]["total"] == 0

    deleted = client.delete(f"/api/history/{first['id']}", headers=auth["headers"])
    assert deleted.status_code == 200
    missing = client.get(f"/api/analysis/{first['id']}", headers=auth["headers"])
    assert missing.status_code == 404


def test_history_filters_and_pagination(client, auth):
    for index in range(3):
        email_scan(client, auth["headers"], body=f"Message number {index} with ordinary content.")
    response = client.get("/api/history?per_page=2&page=1", headers=auth["headers"])
    body = response.get_json()
    assert len(body["data"]) == 2
    assert body["meta"]["pages"] == 2
    filtered = client.get("/api/history?classification=no_significant_indicators", headers=auth["headers"])
    assert filtered.get_json()["meta"]["total"] == 3
    filtered = client.get("/api/history?classification=malicious", headers=auth["headers"])
    assert filtered.get_json()["meta"]["total"] == 0


def test_dashboard_statistics_come_from_database(client, auth):
    email_scan(client, auth["headers"])
    email_scan(
        client,
        auth["headers"],
        sender="PayPal Security <security@paypal-alerts.top>",
        body="Urgent: verify your password immediately or your account will be suspended.",
    )
    stats = client.get("/api/dashboard/stats", headers=auth["headers"]).get_json()["data"]
    assert stats["total_scans"] == 2
    assert sum(stats["counts"].values()) == 2
    activity = client.get("/api/dashboard/activity", headers=auth["headers"]).get_json()["data"]
    assert len(activity["days"]) == 14
    assert sum(day["count"] for day in activity["days"]) == 2
    overview = client.get("/api/dashboard/overview", headers=auth["headers"]).get_json()["data"]
    assert len(overview["recent_scans"]) == 2


def test_scan_pdf_contains_real_report(client, auth):
    scan = email_scan(client, auth["headers"]).get_json()["data"]
    response = client.get(f"/api/scan/{scan['id']}/report.pdf", headers=auth["headers"])
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("application/pdf")
    assert response.data.startswith(b"%PDF")
    assert len(response.data) > 1500


def test_invalid_url_submission_rejected(client, auth):
    response = client.post("/api/scan/url", json={"url": "http://127.0.0.1/admin"}, headers=auth["headers"])
    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "blocked_address"

    response = client.post("/api/scan/url", json={"url": "ftp://example.com/x"}, headers=auth["headers"])
    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "unsupported_scheme"


def test_malformed_json_returns_consistent_error(client, auth):
    response = client.post(
        "/api/scan/url",
        data="not-json",
        content_type="application/json",
        headers=auth["headers"],
    )
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_request"
