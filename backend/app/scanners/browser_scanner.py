"""Optional isolated browser analysis using Playwright + Chromium.

Requires ENABLE_BROWSER_SCAN=true and `playwright install chromium`.
When unavailable, the scanner reports that honestly and the rest of the URL
analysis continues.
"""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlsplit

from flask import current_app

from ..detection.findings import finding
from ..detection.url_features import registrable_domain
from ..utils.url_safety import hostname_is_public

_BLOCKED_RESOURCE_TYPES = {"media", "font"}
_MAX_NETWORK_ENTRIES = 100
_MAX_CONSOLE_ENTRIES = 40


def _import_playwright():
    try:
        from playwright.sync_api import sync_playwright  # type: ignore

        return sync_playwright, None
    except Exception:
        return None, "Playwright is not installed (pip install playwright; playwright install chromium)."


def availability() -> dict[str, Any]:
    if not current_app.config.get("ENABLE_BROWSER_SCAN", False):
        return {
            "available": False,
            "reason": "Browser analysis is disabled. Set ENABLE_BROWSER_SCAN=true and install Chromium to enable it.",
        }
    _, error = _import_playwright()
    if error:
        return {"available": False, "reason": error}
    return {"available": True, "reason": ""}


def analyze_in_browser(url: str) -> dict[str, Any]:
    status = availability()
    if not status["available"]:
        return {
            "available": False,
            "reason": status["reason"],
            "findings": [],
        }

    sync_playwright, error = _import_playwright()
    if error or sync_playwright is None:  # pragma: no cover - defensive
        return {"available": False, "reason": error or "Playwright unavailable.", "findings": []}

    timeout_ms = int(current_app.config.get("BROWSER_TIMEOUT_MS", 15_000))
    settle_ms = int(current_app.config.get("BROWSER_SETTLE_MS", 1_500))
    network: list[dict[str, Any]] = []
    responses: list[dict[str, Any]] = []
    console: list[dict[str, Any]] = []
    page_errors: list[str] = []
    blocked_requests = 0
    download_attempted = False
    host_cache: dict[str, bool] = {}
    started = time.monotonic()

    def allow(hostname: str) -> bool:
        if not hostname:
            return False
        if hostname not in host_cache:
            host_cache[hostname] = hostname_is_public(hostname)
        return host_cache[hostname]

    browser = None
    context = None
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(
                accept_downloads=False,
                ignore_https_errors=False,
                java_script_enabled=True,
                viewport={"width": 1280, "height": 900},
            )
            context.set_default_timeout(timeout_ms)

            def route_handler(route):
                nonlocal blocked_requests
                request = route.request
                try:
                    parsed = urlsplit(request.url)
                    if parsed.scheme not in {"http", "https"}:
                        blocked_requests += 1
                        route.abort()
                        return
                    if request.resource_type in _BLOCKED_RESOURCE_TYPES:
                        blocked_requests += 1
                        route.abort()
                        return
                    if not allow((parsed.hostname or "").lower()):
                        blocked_requests += 1
                        route.abort()
                        return
                    route.continue_()
                except Exception:
                    blocked_requests += 1
                    try:
                        route.abort()
                    except Exception:
                        pass

            context.route("**/*", route_handler)

            page = context.new_page()
            page.on(
                "request",
                lambda request: network.append(
                    {
                        "method": request.method,
                        "url": request.url[:2048],
                        "resource_type": request.resource_type,
                    }
                )
                if len(network) < _MAX_NETWORK_ENTRIES
                else None,
            )
            page.on(
                "response",
                lambda response: responses.append(
                    {
                        "url": response.url[:2048],
                        "status": response.status,
                        "content_type": (response.headers or {}).get("content-type", "")[:120],
                    }
                )
                if len(responses) < _MAX_NETWORK_ENTRIES
                else None,
            )
            page.on(
                "console",
                lambda message: console.append(
                    {"type": message.type, "text": (message.text or "")[:300]}
                )
                if len(console) < _MAX_CONSOLE_ENTRIES
                else None,
            )
            page.on("pageerror", lambda exc: page_errors.append(str(exc)[:300]))
            page.on("download", lambda download: _mark_download(download))

            def _mark_download(_download) -> None:
                nonlocal download_attempted
                download_attempted = True

            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(settle_ms)

            final_url = page.url
            title = page.title()[:300]
            password_fields = page.locator("input[type='password']").count()
            cookies = context.cookies()
            cookie_meta = [
                {
                    "name": str(cookie.get("name", ""))[:80],
                    "domain": str(cookie.get("domain", ""))[:200],
                    "secure": bool(cookie.get("secure")),
                    "http_only": bool(cookie.get("httpOnly")),
                    "same_site": str(cookie.get("sameSite", ""))[:20],
                }
                for cookie in cookies[:30]
            ]

            page_host = (urlsplit(final_url).hostname or "").lower()
            initial_host = (urlsplit(url).hostname or "").lower()
            third_party_hosts = sorted(
                {
                    (urlsplit(entry["url"]).hostname or "").lower()
                    for entry in network
                    if (urlsplit(entry["url"]).hostname or "")
                    and registrable_domain((urlsplit(entry["url"]).hostname or "").lower())
                    != registrable_domain(initial_host)
                }
            )[:20]

            findings: list[dict[str, Any]] = []
            if page_host and initial_host and not (
                page_host == initial_host
                or registrable_domain(page_host) == registrable_domain(initial_host)
            ):
                findings.append(
                    finding(
                        "browser_cross_domain_redirect",
                        "Browser ended on a different site",
                        "After rendering, the browser navigated to a different registrable domain "
                        "than the submitted URL.",
                        "medium",
                        "obfuscation",
                        "browser",
                        evidence={"initial_host": initial_host, "final_host": page_host},
                    )
                )
            if password_fields:
                findings.append(
                    finding(
                        "browser_password_form",
                        "Password field rendered in the browser",
                        "The rendered page contains a password input. Verify the domain before "
                        "entering credentials.",
                        "medium",
                        "credential_theft",
                        "browser",
                        evidence={"password_fields": password_fields, "final_url": final_url[:2048]},
                    )
                )
            if download_attempted:
                findings.append(
                    finding(
                        "browser_download_attempt",
                        "Page attempted to trigger a download",
                        "The page tried to start a file download. Downloads from untrusted pages can "
                        "deliver malware.",
                        "high",
                        "payload",
                        "browser",
                        evidence={"final_url": final_url[:2048]},
                    )
                )
            if blocked_requests:
                findings.append(
                    finding(
                        "browser_blocked_requests",
                        "Unsafe or heavy subresource requests blocked",
                        "Some requests were blocked by the analysis sandbox (private addresses, "
                        "non-HTTP schemes, media or fonts). This is expected in isolation.",
                        "info",
                        "sandbox",
                        "browser",
                        weight=0,
                        evidence={"blocked_requests": blocked_requests},
                    )
                )

            return {
                "available": True,
                "reason": "",
                "final_url": final_url[:2048],
                "title": title,
                "password_fields": password_fields,
                "network_requests": network,
                "responses": responses,
                "third_party_hosts": third_party_hosts,
                "cookies": cookie_meta,
                "console_messages": console,
                "page_errors": page_errors[:10],
                "blocked_requests": blocked_requests,
                "download_attempted": download_attempted,
                "elapsed_ms": int((time.monotonic() - started) * 1000),
                "findings": findings,
            }
    except Exception:
        return {
            "available": False,
            "reason": "Browser analysis failed or timed out. The HTTP and static results remain available.",
            "findings": [],
        }
    finally:
        try:
            if context is not None:
                context.close()
        except Exception:
            pass
        try:
            if browser is not None:
                browser.close()
        except Exception:
            pass
