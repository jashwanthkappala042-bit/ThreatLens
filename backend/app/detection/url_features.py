"""URL feature extraction and static indicator heuristics."""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any
from urllib.parse import parse_qs, urlsplit

from .findings import finding

SUSPICIOUS_TLDS = {
    "zip", "mov", "top", "xyz", "tk", "ml", "ga", "cf", "gq", "work", "click",
    "link", "live", "icu", "buzz", "cam", "rest", "monster", "sbs", "cfd",
    "cyou", "lol", "autos", "boats", "quest", "support", "security", "verify",
}

SHORTENERS = {
    "bit.ly", "t.co", "tinyurl.com", "goo.gl", "ow.ly", "is.gd", "buff.ly",
    "rebrand.ly", "cutt.ly", "shorturl.at", "rb.gy", "tiny.cc", "bit.do",
    "t.ly", "shorte.st", "adf.ly",
}

SUSPICIOUS_KEYWORDS = {
    "login", "signin", "sign-in", "logon", "verify", "verification", "secure",
    "account", "update", "confirm", "password", "billing", "invoice", "payment",
    "support", "wallet", "recovery", "unlock", "alert", "suspended", "validate",
    "webscr", "security", "authorize", "authentication", "reset", "credential",
    "banking", "refund", "delivery", "parcel", "customs",
}

RISKY_EXTENSIONS = {
    "exe", "scr", "apk", "msi", "bat", "cmd", "vbs", "ps1", "jar", "msix",
    "hta", "lnk", "iso", "img", "zip", "rar", "7z",
}

BRANDS: dict[str, set[str]] = {
    "paypal": {"paypal.com"},
    "microsoft": {"microsoft.com", "live.com", "office.com", "outlook.com"},
    "apple": {"apple.com", "icloud.com"},
    "google": {"google.com", "gmail.com", "youtube.com"},
    "amazon": {"amazon.com", "amazon.in", "amazon.co.uk"},
    "netflix": {"netflix.com"},
    "facebook": {"facebook.com", "fb.com"},
    "instagram": {"instagram.com"},
    "whatsapp": {"whatsapp.com"},
    "linkedin": {"linkedin.com"},
    "dropbox": {"dropbox.com"},
    "dhl": {"dhl.com"},
    "fedex": {"fedex.com"},
    "ups": {"ups.com"},
    "usps": {"usps.com"},
    "chase": {"chase.com"},
    "wellsfargo": {"wellsfargo.com"},
    "bankofamerica": {"bankofamerica.com"},
    "icici": {"icicibank.com"},
    "hdfc": {"hdfcbank.com"},
    "sbi": {"sbi.co.in", "onlinesbi.sbi"},
    "axis": {"axisbank.com"},
    "kotak": {"kotak.com"},
    "coinbase": {"coinbase.com"},
    "binance": {"binance.com"},
    "metamask": {"metamask.io"},
    "adobe": {"adobe.com"},
    "zoom": {"zoom.us"},
    "github": {"github.com"},
    "steam": {"steampowered.com", "steamcommunity.com"},
}

# Second-level public suffixes used for a lightweight registrable-domain check.
_SECOND_LEVEL = {
    "co.in", "co.uk", "org.uk", "ac.uk", "gov.uk", "com.au", "net.au",
    "co.jp", "co.nz", "co.za", "com.br", "com.mx", "com.sg", "com.tr",
    "co.kr", "com.cn", "com.hk", "co.id", "com.ar", "com.co",
}


def registrable_domain(hostname: str) -> str:
    labels = [label for label in hostname.lower().strip(".").split(".") if label]
    if len(labels) <= 2:
        return ".".join(labels)
    last_two = ".".join(labels[-2:])
    if last_two in _SECOND_LEVEL:
        return ".".join(labels[-3:])
    return last_two


def _entropy(value: str) -> float:
    if not value:
        return 0.0
    counts = Counter(value)
    length = len(value)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


def _brand_hits(hostname: str, path: str) -> tuple[list[str], list[str]]:
    registrable = registrable_domain(hostname)
    host_hits: list[str] = []
    path_hits: list[str] = []
    hostname_lower = hostname.lower()
    path_lower = path.lower()
    for brand, official_domains in BRANDS.items():
        official = registrable in official_domains or any(
            registrable.endswith("." + domain) for domain in official_domains
        )
        if official:
            continue
        if brand in hostname_lower:
            host_hits.append(brand)
        elif brand in path_lower:
            path_hits.append(brand)
    return host_hits, path_hits


def extract_url_features(url: str) -> dict[str, Any]:
    parts = urlsplit(url)
    hostname = (parts.hostname or "").lower()
    path = parts.path or ""
    query = parts.query or ""
    registrable = registrable_domain(hostname)
    labels = [label for label in hostname.split(".") if label]
    subdomain_count = max(0, len(labels) - (3 if registrable.count(".") == 2 else 2))
    tld = labels[-1] if labels else ""
    keyword_hits = sorted(
        {word for word in SUSPICIOUS_KEYWORDS if word in url.lower()}
    )
    host_brands, path_brands = _brand_hits(hostname, path)
    query_params = parse_qs(query, keep_blank_values=True)
    extension = ""
    if "." in path.split("/")[-1]:
        extension = path.split("/")[-1].rsplit(".", 1)[-1].lower()

    try:
        port = parts.port
    except ValueError:
        port = None

    features: dict[str, Any] = {
        "url_length": len(url),
        "hostname_length": len(hostname),
        "path_length": len(path),
        "query_length": len(query),
        "hostname": hostname,
        "registrable_domain": registrable,
        "tld": tld,
        "is_ip_literal": bool(re.fullmatch(r"[0-9a-f:.]+", hostname)) and (
            hostname.count(".") == 3 or ":" in hostname
        ),
        "https": parts.scheme.lower() == "https",
        "port": port,
        "hostname_dots": hostname.count("."),
        "hyphens": url.count("-"),
        "hostname_hyphens": hostname.count("-"),
        "digits": sum(char.isdigit() for char in url),
        "subdomain_count": subdomain_count,
        "special_characters": sum(url.count(ch) for ch in "%@?&=_~+!$'()*,;"),
        "percent_encoded_sequences": len(re.findall(r"%[0-9a-fA-F]{2}", url)),
        "double_slash_in_path": "//" in path,
        "punycode": hostname.startswith("xn--") or ".xn--" in hostname,
        "suspicious_tld": tld in SUSPICIOUS_TLDS,
        "shortener": registrable in SHORTENERS,
        "keywords": keyword_hits,
        "keyword_count": len(keyword_hits),
        "brand_in_hostname": host_brands,
        "brand_in_path": path_brands,
        "path_extension": extension,
        "risky_extension": extension in RISKY_EXTENSIONS,
        "query_parameter_count": sum(len(values) for values in query_params.values()),
        "has_query": bool(query),
        "at_in_path": "@" in path,
        "hostname_entropy": round(_entropy(hostname), 3),
        "scheme_port_mismatch": (
            (parts.scheme.lower() == "http" and port == 443)
            or (parts.scheme.lower() == "https" and port == 80)
        ),
    }
    return features


def url_feature_findings(features: dict[str, Any]) -> list[dict[str, Any]]:
    """Translate static features into explainable indicators."""
    out: list[dict[str, Any]] = []
    host = features.get("hostname", "")

    if features.get("is_ip_literal"):
        out.append(
            finding(
                "url_ip_literal",
                "IP address used instead of a domain",
                "The link points directly to an IP address. This is unusual for legitimate "
                "consumer services and is a common pattern in phishing campaigns.",
                "medium",
                "infrastructure",
                "static",
                evidence={"hostname": host},
            )
        )

    if not features.get("https"):
        out.append(
            finding(
                "url_no_https",
                "Connection is not encrypted (HTTP)",
                "The URL uses plain HTTP, so content and credentials could be intercepted in transit.",
                "medium",
                "transport",
                "static",
                evidence={"scheme": "http"},
            )
        )

    if features.get("punycode"):
        out.append(
            finding(
                "url_punycode",
                "Internationalised (punycode) hostname",
                "The hostname uses punycode. This can be legitimate, but it is also used to "
                "create lookalike domains. Verify the domain before entering any information.",
                "high",
                "impersonation",
                "static",
                evidence={"hostname": host},
            )
        )

    if features.get("suspicious_tld"):
        out.append(
            finding(
                "url_suspicious_tld",
                f"Frequently abused top-level domain (.{features.get('tld')})",
                "Some top-level domains have a high abuse rate. The TLD alone is not proof "
                "of malicious activity, but it raises the baseline concern.",
                "medium",
                "infrastructure",
                "static",
                evidence={"tld": features.get("tld")},
            )
        )

    if features.get("shortener"):
        out.append(
            finding(
                "url_shortener",
                "URL shortening service",
                "The destination is hidden behind a shortener. Expand and verify the final "
                "destination before interacting with it.",
                "low",
                "obfuscation",
                "static",
                evidence={"domain": features.get("registrable_domain")},
            )
        )

    if features.get("brand_in_hostname"):
        out.append(
            finding(
                "url_brand_hostname",
                "Brand name used outside its official domain",
                "A well-known brand appears in a hostname that is not the brand's official "
                "domain. This is a common impersonation pattern.",
                "high",
                "impersonation",
                "static",
                evidence={
                    "brands": features["brand_in_hostname"],
                    "hostname": host,
                    "registrable_domain": features.get("registrable_domain"),
                },
            )
        )
    elif features.get("brand_in_path"):
        out.append(
            finding(
                "url_brand_path",
                "Brand name in URL path",
                "A brand name appears in the path of another domain. Confirm the domain "
                "itself is legitimate before signing in or paying.",
                "low",
                "impersonation",
                "static",
                evidence={"brands": features["brand_in_path"], "path": features.get("path_length")},
            )
        )

    keywords = features.get("keywords", [])
    if keywords:
        severity = "medium" if len(keywords) >= 3 else "low"
        out.append(
            finding(
                "url_suspicious_keywords",
                "Account or credential themed keywords",
                "The URL contains words commonly used in credential-phishing pages. "
                "Keywords are weak signals on their own.",
                severity,
                "social_engineering",
                "static",
                evidence={"keywords": keywords[:8]},
            )
        )

    if features.get("subdomain_count", 0) >= 3:
        out.append(
            finding(
                "url_many_subdomains",
                "Deep subdomain nesting",
                "The URL uses several subdomain levels. Attackers sometimes place a trusted "
                "brand in a subdomain while the real domain is different.",
                "medium",
                "obfuscation",
                "static",
                evidence={"subdomain_count": features.get("subdomain_count"), "hostname": host},
            )
        )

    if features.get("hostname_hyphens", 0) >= 2:
        out.append(
            finding(
                "url_hyphenated_hostname",
                "Multiple hyphens in hostname",
                "Hyphenated hostnames are common for lookalike domains, though many legitimate "
                "services also use them.",
                "low",
                "impersonation",
                "static",
                evidence={"hostname_hyphens": features.get("hostname_hyphens"), "hostname": host},
            )
        )

    if features.get("url_length", 0) > 120:
        out.append(
            finding(
                "url_long",
                "Unusually long URL",
                "Long URLs can hide the real destination. Inspect the domain and path carefully.",
                "low" if features.get("url_length", 0) < 200 else "medium",
                "obfuscation",
                "static",
                evidence={"url_length": features.get("url_length")},
            )
        )

    if features.get("percent_encoded_sequences", 0) >= 6:
        out.append(
            finding(
                "url_encoded",
                "Heavy percent-encoding",
                "The URL contains many encoded characters, which can be used to obscure its meaning.",
                "low",
                "obfuscation",
                "static",
                evidence={"encoded_sequences": features.get("percent_encoded_sequences")},
            )
        )

    if features.get("risky_extension"):
        out.append(
            finding(
                "url_risky_file",
                f"Link targets a .{features.get('path_extension')} file",
                "The path appears to point to an executable or archive file. Do not run "
                "downloaded files from untrusted links.",
                "high",
                "payload",
                "static",
                evidence={"extension": features.get("path_extension")},
            )
        )

    if features.get("scheme_port_mismatch"):
        out.append(
            finding(
                "url_scheme_port_mismatch",
                "Scheme and port combination is unusual",
                "The URL mixes a standard scheme with the other scheme's default port.",
                "low",
                "transport",
                "static",
            )
        )

    if features.get("digits", 0) > 8 and features.get("hostname_length", 0) < 40:
        out.append(
            finding(
                "url_many_digits",
                "Digit-heavy URL",
                "Numerous digits can indicate an automatically generated or tracking URL. "
                "This is a low-specificity signal.",
                "low",
                "obfuscation",
                "static",
                evidence={"digits": features.get("digits")},
            )
        )

    return out
