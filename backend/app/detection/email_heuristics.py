"""Explainable rule-based analysis for email, SMS and other message text.

The rules are intentionally conservative: each signal is an indicator, never a
verdict. A trained ML classifier can be layered on top by the ML service.
"""

from __future__ import annotations

import re
from typing import Any

from ..utils.text import extract_urls, normalize_whitespace
from .findings import finding
from .url_features import BRANDS, registrable_domain

FREE_MAIL_DOMAINS = {
    "gmail.com", "googlemail.com", "yahoo.com", "yahoo.co.in", "outlook.com",
    "hotmail.com", "live.com", "aol.com", "protonmail.com", "proton.me",
    "icloud.com", "mail.com", "gmx.com", "zoho.com", "yandex.com", "msn.com",
}

URGENCY_TERMS = [
    "urgent", "immediately", "act now", "within 24 hours", "within 48 hours",
    "final notice", "last warning", "expires today", "time-sensitive",
    "as soon as possible", "right away", "deadline",
]

THREAT_TERMS = [
    "suspend", "suspended", "terminate", "terminated", "deactivate", "deactivated",
    "locked", "blocked", "legal action", "account closure", "permanently closed",
    "unauthorized access", "unusual activity", "security alert", "failure to comply",
]

CREDENTIAL_TERMS = [
    "password", "username", "login", "log in", "sign in", "sign-in", "verify your account",
    "confirm your identity", "update your credentials", "one-time password", "otp",
    "pin number", "security code", "re-authenticate", "reauthenticate",
]

FINANCIAL_TERMS = [
    "wire transfer", "bank transfer", "gift card", "itunes card", "google play card",
    "bitcoin", "cryptocurrency", "crypto wallet", "invoice", "payment", "refund",
    "billing", "transaction", "credit card", "debit card", "western union",
    "moneygram", "processing fee", "customs fee", "delivery fee", "claim your prize",
    "lottery", "inheritance", "investment opportunity",
]

PERSONAL_DATA_TERMS = [
    "social security", "ssn", "aadhaar", "pan card", "passport number",
    "date of birth", "mother's maiden name", "cvv", "card number", "account number",
    "ifsc", "upi id", "upi pin",
]

GENERIC_GREETINGS = [
    "dear customer", "dear user", "dear valued customer", "dear account holder",
    "dear sir/madam", "dear member", "hello customer", "attention user",
]

ATTACHMENT_TERMS = [
    ".exe", ".scr", ".apk", ".msi", ".bat", ".cmd", ".vbs", ".ps1", ".hta",
    ".lnk", ".iso", ".img", ".zip", ".rar", ".7z",
]

URGENCY_RE = re.compile(r"(?i)\b(?:%s)\b" % "|".join(re.escape(t) for t in URGENCY_TERMS))
THREAT_RE = re.compile(r"(?i)\b(?:%s)\b" % "|".join(re.escape(t) for t in THREAT_TERMS))
CREDENTIAL_RE = re.compile(r"(?i)\b(?:%s)\b" % "|".join(re.escape(t) for t in CREDENTIAL_TERMS))
FINANCIAL_RE = re.compile(r"(?i)\b(?:%s)\b" % "|".join(re.escape(t) for t in FINANCIAL_TERMS))
PERSONAL_RE = re.compile(r"(?i)\b(?:%s)\b" % "|".join(re.escape(t) for t in PERSONAL_DATA_TERMS))
GREETING_RE = re.compile(r"(?i)\b(?:%s)\b" % "|".join(re.escape(t) for t in GENERIC_GREETINGS))
ATTACHMENT_RE = re.compile(r"(?i)(?:%s)\b" % "|".join(re.escape(t) for t in ATTACHMENT_TERMS))
EMAIL_RE = re.compile(r"[\w.+-]+@([\w.-]+\.[A-Za-z]{2,})")


def _hits(pattern: re.Pattern[str], text: str) -> list[str]:
    seen: list[str] = []
    for match in pattern.finditer(text):
        value = match.group(0).lower()
        if value not in seen:
            seen.append(value)
    return seen


def parse_sender(sender: str) -> dict[str, Any]:
    sender = (sender or "").strip()
    if not sender:
        return {"raw": "", "address": "", "domain": "", "display_name": "", "parsed": False}
    display = ""
    address = sender
    match = re.match(r"^(.*)<([^<>]+)>\s*$", sender)
    if match:
        display = match.group(1).strip().strip('"').strip()
        address = match.group(2).strip()
    email_match = EMAIL_RE.search(address)
    if not email_match:
        return {
            "raw": sender,
            "address": address[:254],
            "domain": "",
            "display_name": display,
            "parsed": False,
        }
    domain = email_match.group(1).lower().strip(".")
    return {
        "raw": sender,
        "address": email_match.group(0).lower(),
        "domain": domain,
        "display_name": display,
        "parsed": True,
        "free_mail": registrable_domain(domain) in FREE_MAIL_DOMAINS,
        "registrable_domain": registrable_domain(domain),
    }


def analyze_email_text(
    subject: str,
    sender: str,
    body: str,
    *,
    max_urls: int = 10,
) -> dict[str, Any]:
    subject = (subject or "").strip()[:300]
    sender = (sender or "").strip()[:300]
    body = (body or "").strip()[:20000]
    combined = f"{subject}\n{body}".strip()
    normalized = normalize_whitespace(combined)
    findings: list[dict[str, Any]] = []

    urgency = _hits(URGENCY_RE, combined)
    threats = _hits(THREAT_RE, combined)
    credentials = _hits(CREDENTIAL_RE, combined)
    financial = _hits(FINANCIAL_RE, combined)
    personal = _hits(PERSONAL_RE, combined)
    greetings = _hits(GREETING_RE, combined)
    attachments = _hits(ATTACHMENT_RE, combined)
    urls = extract_urls(combined, limit=max_urls)
    links = re.findall(r"(?i)https?://[^\s<>\"']+|www\.[^\s<>\"']+", combined)
    exclamations = combined.count("!")
    uppercase_ratio = (
        sum(char.isupper() for char in combined) / max(1, sum(char.isalpha() for char in combined))
    )

    if urgency:
        findings.append(
            finding(
                "email_urgency",
                "Urgency or deadline pressure",
                "The message pushes for immediate action. Urgency is a common social-engineering "
                "tactic and is not proof of phishing by itself.",
                "medium" if len(urgency) >= 2 else "low",
                "social_engineering",
                "heuristic",
                evidence={"terms": urgency[:8]},
            )
        )

    if threats:
        findings.append(
            finding(
                "email_threat",
                "Threat of account loss or legal action",
                "The message warns of suspension, closure or legal consequences. Verify the claim "
                "through the service's official website, not through links in the message.",
                "medium" if len(threats) >= 2 else "low",
                "social_engineering",
                "heuristic",
                evidence={"terms": threats[:8]},
            )
        )

    if credentials:
        findings.append(
            finding(
                "email_credential_request",
                "Request related to credentials or verification",
                "The message references passwords, sign-in or identity verification. Legitimate "
                "services rarely ask for credentials by email.",
                "high" if len(credentials) >= 2 else "medium",
                "credential_theft",
                "heuristic",
                evidence={"terms": credentials[:8]},
            )
        )

    if financial:
        findings.append(
            finding(
                "email_financial",
                "Payment, refund or financial incentive language",
                "Financial requests and unsolicited refunds or prizes are frequently used in fraud. "
                "Confirm through official channels before paying or sharing details.",
                "high" if len(financial) >= 3 else "medium",
                "financial_fraud",
                "heuristic",
                evidence={"terms": financial[:8]},
            )
        )

    if personal:
        findings.append(
            finding(
                "email_personal_data",
                "Sensitive personal information requested",
                "The message mentions identity or payment data. Do not share these details in "
                "response to an unsolicited message.",
                "high",
                "credential_theft",
                "heuristic",
                evidence={"terms": personal[:8]},
            )
        )

    if greetings:
        findings.append(
            finding(
                "email_generic_greeting",
                "Generic greeting",
                "The message uses a generic greeting rather than your name. This is a weak signal "
                "that also appears in legitimate bulk email.",
                "low",
                "social_engineering",
                "heuristic",
                evidence={"terms": greetings[:4]},
            )
        )

    if attachments:
        findings.append(
            finding(
                "email_attachment_mention",
                "Risky attachment type mentioned",
                "The message refers to an executable or archive attachment. Do not open attachments "
                "from unexpected senders.",
                "medium",
                "payload",
                "heuristic",
                evidence={"terms": attachments[:6]},
            )
        )

    if any(
        domain in candidate.lower()
        for candidate in urls
        for domain in ("bit.ly", "tinyurl.com", "t.co", "cutt.ly", "rb.gy")
    ):
        findings.append(
            finding(
                "email_shortened_link",
                "Shortened link in message",
                "A shortened link hides its destination. Expand it with a reputable tool before use.",
                "low",
                "obfuscation",
                "heuristic",
                evidence={"url_count": len(urls)},
            )
        )

    if len(urls) >= 5:
        findings.append(
            finding(
                "email_many_links",
                "Several links in one message",
                "Multiple links increase the chance that at least one points to an untrusted site. "
                "Count alone is not conclusive.",
                "low",
                "obfuscation",
                "heuristic",
                evidence={"url_count": len(urls)},
            )
        )

    if exclamations >= 4 or uppercase_ratio > 0.35:
        findings.append(
            finding(
                "email_style_pressure",
                "Melodramatic formatting",
                "Excessive capital letters or exclamation marks can indicate a pressure tactic. "
                "Formatting alone is weak evidence.",
                "low",
                "social_engineering",
                "heuristic",
                evidence={"exclamations": exclamations, "uppercase_ratio": round(uppercase_ratio, 2)},
            )
        )

    sender_info = parse_sender(sender)
    sender_findings: list[dict[str, Any]] = []
    if sender_info.get("parsed"):
        domain = sender_info["domain"]
        registrable = registrable_domain(domain)
        display = sender_info.get("display_name", "").lower()
        brand_official = {
            brand: any(
                registrable == official or registrable.endswith("." + official)
                for official in official_domains
            )
            for brand, official_domains in BRANDS.items()
        }
        brand_in_display = [
            brand for brand in BRANDS if brand in display and not brand_official[brand]
        ]
        if brand_in_display:
            sender_findings.append(
                finding(
                    "email_sender_brand_mismatch",
                    "Sender name impersonates a brand",
                    "The display name mentions a known brand, but the sender domain does not "
                    "belong to that brand.",
                    "high",
                    "impersonation",
                    "heuristic",
                    evidence={
                        "display_name": sender_info.get("display_name", "")[:80],
                        "domain": domain,
                        "brands": brand_in_display[:4],
                    },
                )
            )
        lookalike_brands = [
            brand for brand in BRANDS if brand in registrable and not brand_official[brand]
        ]
        if lookalike_brands:
            sender_findings.append(
                finding(
                    "email_sender_lookalike",
                    "Sender domain resembles a known brand",
                    "The sender's domain contains a brand term but is not the brand's official "
                    "domain.",
                    "high",
                    "impersonation",
                    "heuristic",
                    evidence={"domain": domain, "brands": lookalike_brands[:4]},
                )
            )
        if sender_info.get("free_mail") and brand_in_display:
            sender_findings.append(
                finding(
                    "email_free_mail_brand",
                    "Brand name sent from a free mail service",
                    "A message claiming to represent a brand was sent from a free consumer mail "
                    "domain. Organisations normally use their own domain.",
                    "high",
                    "impersonation",
                    "heuristic",
                    evidence={"domain": domain, "display_name": sender_info.get("display_name", "")[:80]},
                )
            )
        findings.extend(sender_findings)

    if subject and subject.isupper() and len(subject) > 8:
        findings.append(
            finding(
                "email_subject_caps",
                "Subject line is entirely capitalised",
                "All-capital subjects are a weak pressure signal, common in bulk and fraudulent mail.",
                "low",
                "social_engineering",
                "heuristic",
                evidence={"subject_length": len(subject)},
            )
        )

    features = {
        "text_length": len(combined),
        "word_count": len(normalized.split()) if normalized else 0,
        "link_count": len(urls),
        "exclamations": exclamations,
        "uppercase_ratio": round(uppercase_ratio, 3),
        "urgency_terms": urgency,
        "threat_terms": threats,
        "credential_terms": credentials,
        "financial_terms": financial,
        "personal_data_terms": personal,
        "generic_greeting": greetings,
        "attachment_terms": attachments,
        "sender": sender_info,
    }

    limitations: list[str] = [
        "Rule-based text analysis cannot understand context, tone or intent with certainty.",
        "A message with no matching indicators may still be fraudulent.",
    ]
    if not sender:
        limitations.append("No sender was supplied, so sender-domain checks were skipped.")
    if not urls:
        limitations.append("No links were extracted from the message.")

    return {
        "subject": subject,
        "sender": sender,
        "body": body,
        "features": features,
        "signals": findings,
        "extracted_urls": urls,
        "limitations": limitations,
        "stages": [
            {
                "name": "Text heuristics",
                "status": "completed",
                "detail": f"{len(findings)} indicator(s) recorded from rule-based text analysis.",
            }
        ],
    }
