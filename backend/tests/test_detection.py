"""Feature-extraction and rule-based text tests."""

from __future__ import annotations

from app.detection import risk_engine
from app.detection.email_heuristics import analyze_email_text, parse_sender
from app.detection.url_features import (
    extract_url_features,
    registrable_domain,
    url_feature_findings,
)


def test_registrable_domain_handles_second_level_suffixes():
    assert registrable_domain("login.sbi.co.in") == "sbi.co.in"
    assert registrable_domain("www.example.com") == "example.com"
    assert registrable_domain("a.b.example.co.uk") == "example.co.uk"


def test_url_features_flag_brand_tld_and_keywords():
    features = extract_url_features("https://paypal-login.secure-verify.top/account/verify?token=abc")
    assert features["tld"] == "top"
    assert features["suspicious_tld"] is True
    assert "paypal" in features["brand_in_hostname"]
    assert "login" in features["keywords"]
    assert features["https"] is True
    ids = {item["indicator_id"] for item in url_feature_findings(features)}
    assert "url_brand_hostname" in ids
    assert "url_suspicious_tld" in ids
    assert "url_suspicious_keywords" in ids


def test_url_features_detect_ip_and_risky_extension():
    features = extract_url_features("http://192.168.10.4/download/invoice.apk")
    assert features["is_ip_literal"] is True
    assert features["risky_extension"] is True
    assert features["https"] is False
    ids = {item["indicator_id"] for item in url_feature_findings(features)}
    assert {"url_ip_literal", "url_no_https", "url_risky_file"} <= ids


def test_punycode_feature():
    features = extract_url_features("https://xn--pypal-4ve.com/login")
    assert features["punycode"] is True
    ids = {item["indicator_id"] for item in url_feature_findings(features)}
    assert "url_punycode" in ids


def test_parse_sender_with_display_name():
    sender = parse_sender("PayPal Security <security@paypal-alerts.top>")
    assert sender["display_name"] == "PayPal Security"
    assert sender["domain"] == "paypal-alerts.top"
    assert sender["parsed"] is True


def test_email_heuristics_are_explainable():
    analysis = analyze_email_text(
        "URGENT: account suspended",
        "Microsoft Support <help@microsoft-verify.top>",
        "Dear customer, within 24 hours your account will be suspended. "
        "Verify your password and sign in immediately at https://microsoft-login.top/verify.",
    )
    ids = {item["indicator_id"] for item in analysis["signals"]}
    assert "email_urgency" in ids
    assert "email_credential_request" in ids
    assert "email_sender_lookalike" in ids
    assert analysis["extracted_urls"] == ["https://microsoft-login.top/verify"]
    for item in analysis["signals"]:
        assert item["evidence"]
        assert item["source"] == "heuristic"


def test_one_keyword_does_not_make_a_message_malicious():
    analysis = analyze_email_text("", "", "Please update your password in the app.")
    result = risk_engine.assess(
        "email",
        {**analysis, "ml": {"available": False, "reason": "no model"}},
        analysis["signals"],
    )
    assert result["classification"] == "no_significant_indicators"
    assert result["risk_score"] < risk_engine.SUSPICIOUS_THRESHOLD


def test_benign_message_has_no_high_severity_signals():
    analysis = analyze_email_text("", "Colleague <colleague@company.com>", "Hi, the meeting notes are attached.")
    assert all(item["severity"] in {"low", "info"} for item in analysis["signals"])
