"""URL validation and SSRF boundary tests."""

from __future__ import annotations

import pytest

from app.scanners import http_client
from app.utils.url_safety import InvalidTarget, Target, hostname_is_public, validate_url


@pytest.fixture()
def app_ctx(app):
    with app.app_context():
        yield


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://127.0.0.1:80/admin",
        "http://[::1]/",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/",
        "http://192.168.1.1/",
        "http://172.16.0.1/",
        "http://0.0.0.0/",
    ],
)
def test_private_and_reserved_targets_rejected(app_ctx, url):
    with pytest.raises(InvalidTarget) as exc:
        validate_url(url)
    assert exc.value.code in {"blocked_address", "blocked_host", "invalid_hostname"}


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/file",
        "javascript:alert(1)",
        "data:text/html,<script>alert(1)</script>",
    ],
)
def test_unsupported_schemes_rejected(app_ctx, url):
    with pytest.raises(InvalidTarget) as exc:
        validate_url(url)
    assert exc.value.code in {"unsupported_scheme", "invalid_url"}


def test_credentials_in_url_rejected(app_ctx):
    with pytest.raises(InvalidTarget) as exc:
        validate_url("https://user:pass@example.com/")
    assert exc.value.code == "invalid_url"


def test_non_standard_port_rejected(app_ctx):
    with pytest.raises(InvalidTarget) as exc:
        validate_url("http://example.com:8080/")
    assert exc.value.code == "blocked_port"


def test_missing_scheme_rejected(app_ctx):
    with pytest.raises(InvalidTarget) as exc:
        validate_url("example.com/login")
    assert exc.value.code == "unsupported_scheme"


def test_syntax_only_validation_skips_dns(app_ctx, monkeypatch):
    def fail(*_args, **_kwargs):
        raise AssertionError("DNS should not be called for syntax-only validation")

    monkeypatch.setattr("app.utils.url_safety._resolve", fail)
    target = validate_url("https://example.com/login?x=1#fragment", resolve=False)
    assert target.normalized_url == "https://example.com/login?x=1"
    assert target.resolved_ips == []


def test_hostname_is_public_blocks_loopback_and_metadata(app_ctx):
    assert hostname_is_public("localhost") is False
    assert hostname_is_public("127.0.0.1") is False
    assert hostname_is_public("169.254.169.254") is False


def test_redirect_is_revalidated_before_following(app_ctx, monkeypatch):
    calls = []

    def fake_validate(url):
        calls.append(url)
        if len(calls) == 1:
            return Target(
                original=url,
                normalized_url="https://public.example/start",
                scheme="https",
                hostname="public.example",
                port=443,
                path="/start",
                query="",
                is_ip_literal=False,
                resolved_ips=["93.184.216.34"],
            )
        raise InvalidTarget("blocked_address", "Redirect target is private.")

    class RedirectResponse:
        status_code = 302
        reason = "Found"
        is_redirect = True
        headers = {"Location": "http://127.0.0.1/secret"}

        def close(self):
            pass

    class FakeCookies:
        def clear(self):
            pass

    class FakeSession:
        trust_env = False
        cookies = FakeCookies()

        def get(self, *_args, **_kwargs):
            return RedirectResponse()

        def close(self):
            pass

    monkeypatch.setattr(http_client, "validate_url", fake_validate)
    monkeypatch.setattr(http_client.requests, "Session", lambda: FakeSession())

    result = http_client.fetch_url(
        "https://public.example/start",
        max_redirects=3,
        connect_timeout=1,
        read_timeout=1,
        max_bytes=1024,
    )
    assert result["available"] is False
    assert result["error_code"] == "blocked_address"
    assert len(calls) == 2
    assert result["redirect_chain"][0]["status"] == 302
