"""Community permissions, reporting and moderation tests."""

from __future__ import annotations

from tests.conftest import auth_header, make_admin, register_user


def make_post(client, headers, **overrides):
    payload = {
        "title": "Suspicious delivery message",
        "content": "I received a message asking me to pay a customs fee through a lookalike site.",
        "url": "https://example.com/tracking",
    }
    payload.update(overrides)
    return client.post("/api/community/posts", json=payload, headers=headers)


def test_anonymous_cannot_post_or_comment(client, auth):
    anonymous = make_post(client, {})
    assert anonymous.status_code == 401

    post = make_post(client, auth["headers"]).get_json()["data"]
    comment = client.post(f"/api/community/posts/{post['id']}/comments", json={"content": "Hi"})
    assert comment.status_code == 401


def test_community_post_and_comment_flow(client, auth):
    post_response = make_post(client, auth["headers"])
    assert post_response.status_code == 201
    post = post_response.get_json()["data"]
    assert post["verification"] == "unverified_community_report"
    assert post["status"] == "published"

    listing = client.get("/api/community/posts")
    assert listing.status_code == 200
    assert listing.get_json()["data"][0]["id"] == post["id"]
    assert "unverified" in listing.get_json()["meta"]["verification_note"]

    comment = client.post(
        f"/api/community/posts/{post['id']}/comments",
        json={"content": "Thanks for sharing. Verify through the official app."},
        headers=auth["headers"],
    )
    assert comment.status_code == 201
    detail = client.get(f"/api/community/posts/{post['id']}").get_json()["data"]
    assert len(detail["comments"]) == 1
    assert detail["comment_count"] == 1


def test_reports_flag_post_at_threshold_and_moderator_can_remove(client, app, auth):
    app.config["REPORTS_TO_FLAG"] = 2
    post = make_post(client, auth["headers"]).get_json()["data"]

    token_b, user_b = register_user(client, email="b@example.com", name="Bee")
    token_c, user_c = register_user(client, email="c@example.com", name="Cee")
    first = client.post(
        f"/api/community/posts/{post['id']}/report",
        json={"reason": "This link looks misleading."},
        headers=auth_header(token_b),
    )
    assert first.status_code == 201
    assert first.get_json()["data"]["post_flagged"] is False

    duplicate = client.post(
        f"/api/community/posts/{post['id']}/report",
        json={"reason": "Reporting again."},
        headers=auth_header(token_b),
    )
    assert duplicate.status_code == 409

    second = client.post(
        f"/api/community/posts/{post['id']}/report",
        json={"reason": "I also think this is misleading."},
        headers=auth_header(token_c),
    )
    assert second.status_code == 201
    assert second.get_json()["data"]["post_flagged"] is True

    non_admin = client.get("/api/community/moderation/reports", headers=auth_header(token_b))
    assert non_admin.status_code == 403

    make_admin(app, user_c["id"])
    reports = client.get("/api/community/moderation/reports", headers=auth_header(token_c))
    assert reports.status_code == 200
    assert len(reports.get_json()["data"]) == 2

    removed = client.patch(
        f"/api/community/posts/{post['id']}/moderation",
        json={"action": "remove", "note": "Misleading content removed."},
        headers=auth_header(token_c),
    )
    assert removed.status_code == 200
    assert removed.get_json()["data"]["status"] == "removed"

    public_detail = client.get(f"/api/community/posts/{post['id']}")
    assert public_detail.status_code == 404
    admin_detail = client.get(f"/api/community/posts/{post['id']}", headers=auth_header(token_c))
    assert admin_detail.status_code == 200


def test_link_scan_requires_ownership(client, auth):
    from tests.test_scans import email_scan

    own_scan = email_scan(client, auth["headers"]).get_json()["data"]
    token_b, _ = register_user(client, email="link@example.com", name="Link")
    response = make_post(client, auth_header(token_b), scan_id=own_scan["id"])
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "forbidden"


def test_author_can_delete_own_post_only(client, auth):
    post = make_post(client, auth["headers"]).get_json()["data"]
    token_b, _ = register_user(client, email="delete@example.com", name="Delete")
    denied = client.delete(f"/api/community/posts/{post['id']}", headers=auth_header(token_b))
    assert denied.status_code == 403
    deleted = client.delete(f"/api/community/posts/{post['id']}", headers=auth["headers"])
    assert deleted.status_code == 200
    assert client.get(f"/api/community/posts/{post['id']}").status_code == 404


def test_invalid_post_payload_rejected(client, auth):
    response = make_post(client, auth["headers"], title="bad", content="short")
    assert response.status_code == 422
    response = make_post(client, auth["headers"], url="javascript:alert(1)")
    assert response.status_code == 422
