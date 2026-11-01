"""Bounded, SSRF-aware HTTP fetching.

Every hop (including redirects) is re-validated. The fetcher never forwards
caller headers or cookies, ignores environment proxies, restricts ports,
enforces timeouts and caps the response size.

Known limitation: DNS is resolved for validation and then again by the HTTP
client, leaving a small time-of-check/time-of-use window (DNS rebinding).
This is mitigated by revalidation on every hop, public-IP-only checks, no
credential forwarding, and strict time/size limits. A production deployment
should also pin validated IPs at the socket layer.
"""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import urljoin

import requests

from ..utils.url_safety import InvalidTarget, Target, validate_url

USER_AGENT = "ThreatLens-Scanner/1.0 (local isolated analysis)"
TEXT_CONTENT_TYPES = {
    "text/html",
    "application/xhtml+xml",
    "text/plain",
    "text/xml",
    "application/xml",
    "application/json",
    "application/ld+json",
}
_SAFE_HEADER_LIMIT = 60


def _is_text_content(content_type: str) -> bool:
    base = content_type.split(";")[0].strip().lower()
    return base in TEXT_CONTENT_TYPES or base.endswith("+xml") or base.endswith("+json")


def _decode_body(body: bytes, content_type: str) -> str:
    charset = "utf-8"
    for part in content_type.split(";")[1:]:
        key, _, value = part.strip().partition("=")
        if key.lower() == "charset" and value:
            charset = value.strip('"\' ')
            break
    for encoding in (charset, "utf-8", "latin-1"):
        try:
            return body.decode(encoding, errors="replace")
        except (LookupError, UnicodeDecodeError):
            continue
    return body.decode("utf-8", errors="replace")


def _request_headers() -> dict[str, str]:
    return {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.5",
        "Accept-Language": "en-US,en;q=0.8",
        "Connection": "close",
        "Cache-Control": "no-cache",
    }


def _serialize_headers(headers: requests.structures.CaseInsensitiveDict[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for index, (key, value) in enumerate(headers.items()):
        if index >= _SAFE_HEADER_LIMIT:
            break
        if key.lower() in {"set-cookie"}:
            continue
        out[key.lower()] = value[:500]
    return out


def _cookie_metadata(response: requests.Response) -> list[dict[str, Any]]:
    cookies: list[dict[str, Any]] = []
    for cookie in response.cookies:
        cookies.append(
            {
                "name": cookie.name[:100],
                "domain": cookie.domain or "",
                "path": cookie.path or "",
                "secure": bool(cookie.secure),
                "http_only": bool(getattr(cookie, "_rest", {}) and "HttpOnly" in cookie._rest),
            }
        )
    return cookies[:30]


def fetch_url(
    url: str,
    *,
    max_redirects: int,
    connect_timeout: float,
    read_timeout: float,
    max_bytes: int,
) -> dict[str, Any]:
    """Fetch a URL with manual redirect handling and per-hop validation."""
    started = time.monotonic()
    chain: list[dict[str, Any]] = []
    current = url
    session = requests.Session()
    session.trust_env = False
    session.cookies.clear()

    try:
        for hop in range(max_redirects + 1):
            try:
                target: Target = validate_url(current)
            except InvalidTarget as exc:
                return {
                    "available": False,
                    "error_code": exc.code,
                    "error": exc.message,
                    "redirect_chain": chain,
                    "final_url": current,
                    "elapsed_ms": int((time.monotonic() - started) * 1000),
                }

            try:
                response = session.get(
                    target.normalized_url,
                    headers=_request_headers(),
                    allow_redirects=False,
                    stream=True,
                    timeout=(connect_timeout, read_timeout),
                )
            except requests.exceptions.SSLError:
                return {
                    "available": False,
                    "error_code": "tls_error",
                    "error": "TLS certificate validation failed for the destination.",
                    "redirect_chain": chain,
                    "final_url": target.normalized_url,
                    "elapsed_ms": int((time.monotonic() - started) * 1000),
                }
            except requests.exceptions.Timeout:
                return {
                    "available": False,
                    "error_code": "timeout",
                    "error": "The destination did not respond within the time limit.",
                    "redirect_chain": chain,
                    "final_url": target.normalized_url,
                    "elapsed_ms": int((time.monotonic() - started) * 1000),
                }
            except requests.exceptions.ConnectionError:
                return {
                    "available": False,
                    "error_code": "connection_failed",
                    "error": "The destination could not be reached.",
                    "redirect_chain": chain,
                    "final_url": target.normalized_url,
                    "elapsed_ms": int((time.monotonic() - started) * 1000),
                }
            except requests.exceptions.RequestException:
                return {
                    "available": False,
                    "error_code": "request_failed",
                    "error": "The HTTP request failed for an unexpected reason.",
                    "redirect_chain": chain,
                    "final_url": target.normalized_url,
                    "elapsed_ms": int((time.monotonic() - started) * 1000),
                }

            location = response.headers.get("Location", "")
            chain.append(
                {
                    "hop": hop + 1,
                    "url": target.normalized_url,
                    "hostname": target.hostname,
                    "status": response.status_code,
                    "location": location[:2048] if location else "",
                }
            )

            if response.is_redirect and location:
                response.close()
                if hop >= max_redirects:
                    return {
                        "available": False,
                        "error_code": "too_many_redirects",
                        "error": f"The redirect limit ({max_redirects}) was exceeded.",
                        "redirect_chain": chain,
                        "final_url": target.normalized_url,
                        "elapsed_ms": int((time.monotonic() - started) * 1000),
                    }
                try:
                    current = urljoin(target.normalized_url, location)
                except ValueError:
                    return {
                        "available": False,
                        "error_code": "invalid_redirect",
                        "error": "A redirect destination could not be parsed.",
                        "redirect_chain": chain,
                        "final_url": target.normalized_url,
                        "elapsed_ms": int((time.monotonic() - started) * 1000),
                    }
                continue

            content_type = response.headers.get("Content-Type", "")
            body = bytearray()
            truncated = False
            try:
                for chunk in response.iter_content(chunk_size=16_384):
                    if not chunk:
                        continue
                    remaining = max_bytes - len(body)
                    if remaining <= 0:
                        truncated = True
                        break
                    body.extend(chunk[:remaining])
                    if len(chunk) > remaining:
                        truncated = True
                        break
            except requests.exceptions.RequestException:
                truncated = True
            finally:
                response.close()

            content = _decode_body(bytes(body), content_type) if _is_text_content(content_type) else ""
            return {
                "available": True,
                "status_code": response.status_code,
                "reason": response.reason,
                "final_url": target.normalized_url,
                "final_hostname": target.hostname,
                "headers": _serialize_headers(response.headers),
                "content_type": content_type.split(";")[0].strip().lower(),
                "content_charset": content_type,
                "content": content,
                "is_text": bool(content),
                "content_truncated": truncated,
                "response_bytes": len(body),
                "redirect_chain": chain,
                "cookies": _cookie_metadata(response),
                "elapsed_ms": int((time.monotonic() - started) * 1000),
            }

        return {
            "available": False,
            "error_code": "too_many_redirects",
            "error": f"The redirect limit ({max_redirects}) was exceeded.",
            "redirect_chain": chain,
            "final_url": current,
            "elapsed_ms": int((time.monotonic() - started) * 1000),
        }
    finally:
        session.close()


def fetch_small_resource(url: str, *, max_bytes: int = 65_536) -> dict[str, Any]:
    """Fetch a small same-purpose resource (e.g. favicon) with validation."""
    try:
        target = validate_url(url)
    except InvalidTarget as exc:
        return {"collected": False, "reason": exc.message, "code": exc.code}
    session = requests.Session()
    session.trust_env = False
    try:
        response = session.get(
            target.normalized_url,
            headers={"User-Agent": USER_AGENT, "Connection": "close"},
            allow_redirects=False,
            stream=True,
            timeout=(4.0, 5.0),
        )
        if response.is_redirect:
            return {"collected": False, "reason": "Favicon URL redirected; not followed."}
        body = response.raw.read(max_bytes + 1, decode_content=True) or b""
        truncated = len(body) > max_bytes
        body = body[:max_bytes]
        return {
            "collected": True,
            "url": target.normalized_url,
            "hostname": target.hostname,
            "status_code": response.status_code,
            "content_type": response.headers.get("Content-Type", "")[:120],
            "bytes": len(body),
            "truncated": truncated,
            "sha256": __import__("hashlib").sha256(body).hexdigest() if body else "",
        }
    except requests.exceptions.RequestException:
        return {"collected": False, "reason": "Favicon could not be retrieved."}
    finally:
        session.close()
