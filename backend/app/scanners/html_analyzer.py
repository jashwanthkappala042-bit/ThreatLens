"""Static HTML inspection with BeautifulSoup.

Only structured observations are retained; the raw page body is never stored.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from ..detection.findings import finding
from ..detection.url_features import registrable_domain

_SUSPICIOUS_JS = {
    "eval(": "eval()",
    "document.write": "document.write",
    "unescape(": "unescape()",
    "fromCharCode": "String.fromCharCode",
    "atob(": "atob()",
    "window.location": "window.location",
}
_JS_RE = re.compile("|".join(re.escape(token) for token in _SUSPICIOUS_JS), re.IGNORECASE)


def _host(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def _same_site(a: str, b: str) -> bool:
    if not a or not b:
        return False
    return registrable_domain(a) == registrable_domain(b)


def analyze_html(html: str, base_url: str, features: dict[str, Any]) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "template"]):
        # Keep script elements for reference extraction but remove their text
        # from the visible-text excerpt.
        if tag.name != "script":
            tag.decompose()

    title = ""
    if soup.title and soup.title.string:
        title = re.sub(r"\s+", " ", soup.title.string).strip()[:300]
    meta_description = ""
    meta = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
    if meta and meta.get("content"):
        meta_description = re.sub(r"\s+", " ", str(meta.get("content"))).strip()[:400]

    base_hostname = _host(base_url)
    forms: list[dict[str, Any]] = []
    password_fields = 0
    external_actions: list[dict[str, str]] = []
    hidden_inputs = 0

    for form in soup.find_all("form", limit=25):
        action_raw = str(form.get("action") or "").strip()
        action = urljoin(base_url, action_raw) if action_raw else base_url
        method = str(form.get("method") or "get").lower()[:10]
        field_names: list[str] = []
        field_types: list[str] = []
        has_password = False
        for control in form.find_all(["input", "textarea", "select"], limit=40):
            name = str(control.get("name") or "")[:60]
            input_type = str(control.get("type") or control.name or "").lower()[:20]
            if name:
                field_names.append(name)
            field_types.append(input_type)
            if input_type == "password" or "pass" in name.lower():
                has_password = True
                password_fields += 1
            if input_type == "hidden":
                hidden_inputs += 1
        action_host = _host(action)
        external = bool(action_host and base_hostname and not _same_site(action_host, base_hostname))
        if external:
            external_actions.append({"action": action[:2048], "hostname": action_host})
        forms.append(
            {
                "action": action[:2048],
                "action_hostname": action_host,
                "method": method,
                "has_password": has_password,
                "external_action": external,
                "field_names": field_names[:20],
                "field_types": list(dict.fromkeys(field_types))[:10],
            }
        )

    external_links: list[dict[str, str]] = []
    external_link_count = 0
    seen_links: set[str] = set()
    for anchor in soup.find_all("a", href=True, limit=1500):
        href = str(anchor.get("href") or "").strip()
        if not href or href.lower().startswith(("javascript:", "mailto:", "tel:", "#", "data:")):
            continue
        absolute = urljoin(base_url, href)
        if urlsplit(absolute).scheme not in {"http", "https"}:
            continue
        link_host = _host(absolute)
        if link_host and not _same_site(link_host, base_hostname):
            external_link_count += 1
            if absolute[:2048] not in seen_links and len(external_links) < 30:
                seen_links.add(absolute[:2048])
                external_links.append(
                    {
                        "url": absolute[:2048],
                        "hostname": link_host,
                        "text": re.sub(r"\s+", " ", anchor.get_text(" ", strip=True))[:120],
                    }
                )

    scripts: list[dict[str, str]] = []
    inline_script_count = 0
    js_pattern_hits: list[str] = []
    script_hosts: Counter[str] = Counter()
    for script in soup.find_all("script", limit=200):
        src = str(script.get("src") or "").strip()
        if src:
            absolute = urljoin(base_url, src)
            script_host = _host(absolute)
            if script_host:
                script_hosts[script_host] += 1
            if len(scripts) < 40:
                scripts.append(
                    {
                        "src": absolute[:2048],
                        "hostname": script_host,
                        "third_party": bool(script_host and not _same_site(script_host, base_hostname)),
                    }
                )
        else:
            inline_script_count += 1
            snippet = script.string or script.get_text() or ""
            for match in _JS_RE.finditer(snippet[:200_000]):
                token = match.group(0)
                label = _SUSPICIOUS_JS.get(token.lower()) or _SUSPICIOUS_JS.get(token) or token
                if label not in js_pattern_hits:
                    js_pattern_hits.append(label)

    iframes: list[dict[str, str]] = []
    for iframe in soup.find_all("iframe", src=True, limit=30):
        absolute = urljoin(base_url, str(iframe.get("src")))
        iframe_host = _host(absolute)
        iframes.append(
            {
                "src": absolute[:2048],
                "hostname": iframe_host,
                "third_party": bool(iframe_host and not _same_site(iframe_host, base_hostname)),
            }
        )

    meta_refresh = ""
    refresh_tag = soup.find("meta", attrs={"http-equiv": re.compile("^refresh$", re.I)})
    if refresh_tag and refresh_tag.get("content"):
        meta_refresh = str(refresh_tag.get("content"))[:500]

    favicon = ""
    for link in soup.find_all("link", href=True, limit=100):
        rel = " ".join(link.get("rel") or []).lower()
        if "icon" in rel:
            favicon = urljoin(base_url, str(link.get("href")))
            break

    # Remove scripts before producing the visible-text excerpt, while keeping
    # the script references collected above.
    for script_tag in soup.find_all("script"):
        script_tag.decompose()
    visible_text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))[:1500]

    third_party_hosts: Counter[str] = Counter(script_hosts)
    for item in iframes:
        if item["third_party"] and item["hostname"]:
            third_party_hosts[item["hostname"]] += 1
    third_party_resources = [
        {"hostname": host, "count": count}
        for host, count in third_party_hosts.most_common(15)
    ]

    findings: list[dict[str, Any]] = []
    if password_fields:
        findings.append(
            finding(
                "html_password_form",
                "Password field present",
                f"The page contains {password_fields} password field(s). Many legitimate sites "
                "have these, but combined with other signals it may indicate a credential-"
                "collection page.",
                "medium",
                "credential_theft",
                "html",
                evidence={"password_fields": password_fields, "form_count": len(forms)},
            )
        )
    if external_actions:
        findings.append(
            finding(
                "html_external_form_action",
                "Form submits to a different domain",
                "A form posts data to a domain outside the page's site. This can indicate "
                "credential or payment data being sent to a third party.",
                "high",
                "credential_theft",
                "html",
                evidence={"destinations": external_actions[:5]},
            )
        )
    if password_fields and features.get("brand_in_hostname"):
        findings.append(
            finding(
                "html_brand_password_combo",
                "Brand impersonation combined with a password form",
                "The page asks for a password while using a brand-like hostname that is not the "
                "brand's official domain. This is a strong combination of indicators.",
                "critical",
                "credential_theft",
                "html",
                evidence={
                    "brands": features.get("brand_in_hostname"),
                    "hostname": features.get("hostname"),
                },
            )
        )
    if password_fields and not features.get("https"):
        findings.append(
            finding(
                "html_password_no_tls",
                "Password form served over unencrypted HTTP",
                "Credentials entered into this page would be transmitted without transport "
                "encryption.",
                "critical",
                "transport",
                "html",
                evidence={"hostname": features.get("hostname")},
            )
        )
    if meta_refresh:
        findings.append(
            finding(
                "html_meta_refresh",
                "Automatic meta refresh redirect",
                "The page can redirect automatically without user interaction. Inspect the "
                "destination before continuing.",
                "low",
                "obfuscation",
                "html",
                evidence={"meta_refresh": meta_refresh[:200]},
            )
        )
    external_iframes = [i for i in iframes if i["third_party"]]
    if external_iframes:
        findings.append(
            finding(
                "html_external_iframe",
                "Embedded content from another domain",
                "The page embeds third-party frames, which can host deceptive content.",
                "low",
                "obfuscation",
                "html",
                evidence={"iframes": external_iframes[:5]},
            )
        )
    if js_pattern_hits:
        findings.append(
            finding(
                "html_obfuscated_js",
                "Potentially obfuscating JavaScript patterns",
                "The page uses JavaScript constructs such as encoded evaluation or dynamic "
                "writing. These are common in legitimate apps too, so treat this as a weak signal.",
                "low",
                "obfuscation",
                "html",
                evidence={"patterns": js_pattern_hits[:6], "inline_scripts": inline_script_count},
            )
        )
    if hidden_inputs >= 8:
        findings.append(
            finding(
                "html_many_hidden_inputs",
                "Many hidden form fields",
                "The page includes numerous hidden fields. This is common in web apps but can also "
                "obfuscate form behaviour.",
                "low",
                "obfuscation",
                "html",
                evidence={"hidden_inputs": hidden_inputs},
            )
        )

    return {
        "title": title,
        "meta_description": meta_description,
        "forms": forms,
        "form_count": len(forms),
        "password_field_count": password_fields,
        "external_form_actions": external_actions,
        "external_links": external_links,
        "external_link_count": external_link_count,
        "scripts": scripts,
        "script_count": len(scripts),
        "inline_script_count": inline_script_count,
        "js_pattern_hits": js_pattern_hits,
        "iframes": iframes,
        "meta_refresh": meta_refresh,
        "favicon_url": favicon,
        "third_party_resources": third_party_resources,
        "visible_text": visible_text,
        "hidden_input_count": hidden_inputs,
        "findings": findings,
    }
