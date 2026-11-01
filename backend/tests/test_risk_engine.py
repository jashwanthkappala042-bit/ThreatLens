"""Risk-engine policy tests (no network required)."""

from __future__ import annotations

from app.detection import risk_engine
from app.detection.findings import finding

URL_STAGES = [
    {"name": "Static URL inspection", "status": "completed", "detail": ""},
    {"name": "HTTP inspection", "status": "completed", "detail": ""},
]


def assess_url(findings, stages=None, analysis=None):
    data = analysis or {"stages": stages or URL_STAGES, "limitations": []}
    return risk_engine.assess("url", data, findings)


def test_no_findings_with_completed_http_is_low():
    result = assess_url([])
    assert result["classification"] == "no_significant_indicators"
    assert result["risk_score"] == 0
    assert result["confidence"]["calibrated"] is False


def test_single_high_finding_is_at_least_suspicious():
    result = assess_url(
        [
            finding(
                "test_high",
                "High signal",
                "A high-severity indicator.",
                "high",
                "impersonation",
                "static",
            )
        ]
    )
    assert result["risk_score"] >= 40
    assert result["classification"] == "suspicious"


def test_critical_finding_raises_score_to_high_risk():
    result = assess_url(
        [
            finding(
                "test_critical",
                "Critical signal",
                "A critical indicator.",
                "critical",
                "credential_theft",
                "html",
            )
        ]
    )
    assert result["risk_score"] >= 85
    assert result["classification"] == "malicious"


def test_categories_combine_with_diminishing_returns_not_averaging():
    findings = [
        finding("a", "A", "desc", "medium", "one", "heuristic"),
        finding("b", "B", "desc", "medium", "one", "heuristic"),
        finding("c", "C", "desc", "medium", "two", "heuristic"),
    ]
    result = assess_url(findings)
    # category one = 12 + 6 = 18, category two = 12; total 30.
    assert result["risk_score"] == 30
    assert result["classification"] == "no_significant_indicators"
    assert len(result["categories"]) == 2


def test_missing_http_is_not_treated_as_safety():
    result = assess_url(
        [],
        stages=[
            {"name": "Static URL inspection", "status": "completed", "detail": ""},
            {"name": "HTTP inspection", "status": "failed", "detail": "timeout"},
            {"name": "HTML inspection", "status": "unavailable", "detail": "no response"},
        ],
    )
    assert result["classification"] == "unknown"
    assert result["risk_score"] == 0
    assert any("did not complete" in line for line in result["limitations"])


def test_image_without_extracted_content_is_unknown():
    result = risk_engine.assess(
        "image",
        {
            "stages": [
                {"name": "Image validation", "status": "completed", "detail": ""},
                {"name": "QR decoding", "status": "completed", "detail": "none"},
                {"name": "OCR extraction", "status": "unavailable", "detail": "disabled"},
            ],
            "content_extracted": False,
            "limitations": [],
        },
        [],
    )
    assert result["classification"] == "unknown"
    assert "could not be assessed" in result["summary"]


def test_ml_disagreement_is_reported():
    result = risk_engine.assess(
        "email",
        {
            "stages": [{"name": "Text heuristics", "status": "completed", "detail": ""}],
            "ml": {
                "available": True,
                "predicted_label": "phishing",
                "probability": 0.91,
                "calibrated": False,
            },
            "limitations": [],
        },
        [],
    )
    assert result["disagreements"]
    assert "uncalibrated" in result["disagreements"][0].lower()


def test_score_never_exceeds_100():
    findings = [
        finding(f"id{i}", f"Finding {i}", "desc", "critical", f"cat{i}", "heuristic")
        for i in range(20)
    ]
    result = assess_url(findings)
    assert result["risk_score"] <= 100
    assert result["classification"] == "malicious"


def test_recommendations_are_input_specific():
    result = risk_engine.assess(
        "email",
        {"stages": [{"name": "Text heuristics", "status": "completed", "detail": ""}], "limitations": []},
        [
            finding(
                "test_credential_request",
                "Credential request",
                "The message asks for a password.",
                "critical",
                "credential_theft",
                "heuristic",
            )
        ],
    )
    assert result["classification"] == "malicious"
    assert any("email provider" in item for item in result["recommended_actions"])
    assert any("cybercrime.gov.in" in item for item in result["recommended_actions"])

    clean = risk_engine.assess(
        "email",
        {"stages": [{"name": "Text heuristics", "status": "completed", "detail": ""}], "limitations": []},
        [],
    )
    # Reporting resources are reserved for risky verdicts; a clean verdict must
    # still carry an explicit "not a guarantee" caveat.
    assert not any("cybercrime.gov.in" in item for item in clean["recommended_actions"])
    assert any("not a guarantee of safety" in item for item in clean["recommended_actions"])
