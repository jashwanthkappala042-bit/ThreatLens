"""Validation and SSRF-oriented checks for URLs and hostnames.

This module only checks syntax, schemes, ports and DNS/IP destinations. It is
used before every outbound request *and* before every redirect hop.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from urllib.parse import urlsplit, urlunsplit

from flask import current_app

MAX_URL_LENGTH = 2048
_ALLOWED_SCHEMES = {"http", "https"}
_BLOCKED_HOSTNAMES = {
    "localhost",
    "metadata",
    "metadata.google.internal",
    "instance-data",
    "instance-data.ec2.internal",
}
_HOST_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f\\]")


class InvalidTarget(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class Target:
    original: str
    normalized_url: str
    scheme: str
    hostname: str
    port: int
    path: str
    query: str
    is_ip_literal: bool
    resolved_ips: list[str] = field(default_factory=list)
    punycode: bool = False


def _allow_private() -> bool:
    try:
        return bool(current_app.config.get("ALLOW_PRIVATE_NETWORK_TARGETS", False))
    except RuntimeError:
        return False


def _is_disallowed_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        return _is_disallowed_ip(ip.ipv4_mapped)
    return not ip.is_global


def _parse_ip(hostname: str):
    try:
        return ipaddress.ip_address(hostname)
    except ValueError:
        return None


def _resolve(hostname: str, port: int) -> list[str]:
    """Resolve A/AAAA records with a bounded timeout."""
    timeout = float(current_app.config.get("DNS_TIMEOUT", 5.0)) if _has_app() else 5.0

    def lookup() -> list[str]:
        infos = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        return sorted({info[4][0] for info in infos})

    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="dns")
    future = executor.submit(lookup)
    try:
        addresses = future.result(timeout=timeout)
    except FutureTimeout as exc:
        future.cancel()
        raise InvalidTarget(
            "dns_timeout", "The hostname could not be resolved within the time limit."
        ) from exc
    except socket.gaierror as exc:
        raise InvalidTarget("dns_failed", "The hostname could not be resolved.") from exc
    finally:
        executor.shutdown(wait=False)
    if not addresses:
        raise InvalidTarget("dns_failed", "The hostname did not resolve to an address.")
    return addresses


def _has_app() -> bool:
    try:
        from flask import current_app

        return bool(current_app)
    except Exception:
        return False


def _validate_hostname(
    hostname: str, port: int, allow_private: bool, resolve_host: bool = True
) -> tuple[str, bool, list[str]]:
    if not hostname:
        raise InvalidTarget("invalid_url", "The URL has no hostname.")
    hostname = hostname.lower().rstrip(".")
    if hostname in _BLOCKED_HOSTNAMES or hostname.endswith(".localhost") or hostname.endswith(".local"):
        raise InvalidTarget("blocked_host", "This hostname is not allowed for scanning.")

    ip = _parse_ip(hostname)
    if ip is not None:
        if not allow_private and _is_disallowed_ip(ip):
            raise InvalidTarget(
                "blocked_address",
                "The URL points to a private, loopback or reserved address.",
            )
        return str(ip), True, [str(ip)]

    try:
        ascii_host = hostname.encode("idna").decode("ascii")
    except (UnicodeError, ValueError) as exc:
        raise InvalidTarget("invalid_hostname", "The hostname is not valid.") from exc
    ascii_host = ascii_host.lower().rstrip(".")
    if len(ascii_host) > 253:
        raise InvalidTarget("invalid_hostname", "The hostname is too long.")
    if "." not in ascii_host:
        raise InvalidTarget("invalid_hostname", "Enter a hostname with a valid public domain.")
    labels = ascii_host.split(".")
    if any(not _HOST_LABEL_RE.match(label) for label in labels):
        raise InvalidTarget("invalid_hostname", "The hostname contains invalid characters.")

    if not resolve_host:
        return ascii_host, False, []

    addresses = _resolve(ascii_host, port)
    if not allow_private:
        for address in addresses:
            parsed = _parse_ip(address)
            if parsed is None or _is_disallowed_ip(parsed):
                raise InvalidTarget(
                    "blocked_address",
                    "The hostname resolves to a private, loopback or reserved address.",
                )
    return ascii_host, False, addresses


def validate_url(raw: str, *, resolve: bool = True) -> Target:
    """Validate and normalise a user-supplied URL.

    Raises InvalidTarget with a stable machine code on failure.
    """
    if not isinstance(raw, str):
        raise InvalidTarget("invalid_url", "URL must be text.")
    raw = raw.strip()
    if not raw:
        raise InvalidTarget("invalid_url", "Enter a URL to scan.")
    if len(raw) > MAX_URL_LENGTH:
        raise InvalidTarget("url_too_long", f"URL must be {MAX_URL_LENGTH} characters or fewer.")
    if _CONTROL_RE.search(raw):
        raise InvalidTarget("invalid_url", "The URL contains unsupported control characters.")
    if "://" not in raw:
        raise InvalidTarget(
            "unsupported_scheme",
            "Include a scheme, for example https://example.com.",
        )
    try:
        parts = urlsplit(raw)
    except ValueError as exc:
        raise InvalidTarget("invalid_url", "The URL could not be parsed.") from exc

    scheme = parts.scheme.lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise InvalidTarget(
            "unsupported_scheme", "Only http:// and https:// URLs can be scanned."
        )
    if parts.username or parts.password:
        raise InvalidTarget("invalid_url", "URLs containing embedded credentials are not supported.")
    if not parts.hostname:
        raise InvalidTarget("invalid_url", "The URL has no hostname.")

    try:
        port = parts.port or (443 if scheme == "https" else 80)
    except ValueError as exc:
        raise InvalidTarget("invalid_url", "The URL has an invalid port.") from exc

    allowed_ports = current_app.config.get("ALLOWED_PORTS", {80, 443}) if _has_app() else {80, 443}
    if port not in allowed_ports:
        raise InvalidTarget(
            "blocked_port",
            f"Only standard web ports ({', '.join(str(p) for p in sorted(allowed_ports))}) are allowed.",
        )

    allow_private = _allow_private()
    hostname, is_ip, addresses = _validate_hostname(parts.hostname, port, allow_private, resolve)

    # Rebuild a canonical URL without fragment or userinfo.
    netloc = hostname
    default_port = 443 if scheme == "https" else 80
    if port != default_port:
        netloc = f"{hostname}:{port}"
    path = parts.path or "/"
    normalized = urlunsplit((scheme, netloc, path, parts.query, ""))
    if len(normalized) > MAX_URL_LENGTH:
        raise InvalidTarget("url_too_long", "The normalised URL is too long.")

    return Target(
        original=raw,
        normalized_url=normalized,
        scheme=scheme,
        hostname=hostname,
        port=port,
        path=parts.path or "/",
        query=parts.query,
        is_ip_literal=is_ip,
        resolved_ips=addresses if resolve else [],
        punycode=hostname.startswith("xn--") or ".xn--" in hostname,
    )


def hostname_is_public(hostname: str) -> bool:
    """Best-effort check used by browser request interception.

    Returns False when the hostname cannot be resolved, so unknown destinations
    are blocked rather than allowed.
    """
    if not hostname:
        return False
    host = hostname.lower().rstrip(".")
    if host in _BLOCKED_HOSTNAMES or host.endswith(".local") or host.endswith(".localhost"):
        return False
    ip = _parse_ip(host)
    if ip is not None:
        return _allow_private() or not _is_disallowed_ip(ip)
    try:
        addresses = _resolve(host, 443)
    except InvalidTarget:
        return False
    return all(not _is_disallowed_ip(ipaddress.ip_address(a)) for a in addresses)
