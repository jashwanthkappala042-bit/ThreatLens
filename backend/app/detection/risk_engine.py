"""Central, documented and testable risk-assessment policy.

The engine does not average unrelated scores. It:

1. Groups explainable findings by category.
2. Combines findings within a category with diminishing returns
   (highest + 1/2 second + 1/4 of the rest).
3. Sums category contributions, capped at 100.
4. Applies conservative floors for critical/high findings.
5. Applies decision thresholds and refuses to imply safety when essential
   analysis stages failed or no content could be extracted.

The resulting score is explicitly heuristic and uncalibrated.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

CLASSIFICATION_LABELS = {
    "no_significant_indicators": "No significant indicators detected",
    "suspicious": "Suspicious",
    "malicious": "High risk",
    "unknown": "Inconclusive",
}

RISK_LEVELS = {
    "no_significant_indicators": "low",
    "suspicious": "medium",
    "malicious": "high",
    "unknown": "unknown",
}

MALICIOUS_THRESHOLD = 70
SUSPICIOUS_THRESHOLD = 35

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}

_URL_KEY_STAGES = {"Static URL inspection", "HTTP inspection"}
_EMAIL_KEY_STAGES = {"Text heuristics"}
_IMAGE_KEY_STAGES = {"Image validation"}


def _combine_category(weights: Iterable[float]) -> float:
    weights = sorted((w for w in weights if w > 0), reverse=True)
    if not weights:
        return 0.0
    total = weights[0]
    if len(weights) > 1:
        total += weights[1] * 0.5
    if len(weights) > 2:
        total += sum(weights[2:]) * 0.25
    return total


def _dedupe(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for item in findings:
        if not isinstance(item, dict) or not item.get("title"):
            continue
        key = item.get("indicator_id") or f"{item.get('category')}:{item.get('title')}"
        current = best.get(key)
        if current is None or float(item.get("weight", 0)) > float(current.get("weight", 0)):
            best[key] = item
    return sorted(
        best.values(),
        key=lambda f: (
            SEVERITY_ORDER.get(str(f.get("severity", "low")), 5),
            -float(f.get("weight", 0)),
            str(f.get("title", "")),
        ),
    )


def _category_scores(findings: list[dict[str, Any]]) -> tuple[float, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in findings:
        groups.setdefault(str(item.get("category", "general")), []).append(item)
    breakdown: list[dict[str, Any]] = []
    total = 0.0
    for category, items in groups.items():
        score = _combine_category(float(i.get("weight", 0)) for i in items)
        if score <= 0:
            continue
        total += score
        breakdown.append(
            {
                "category": category,
                "score": round(score, 1),
                "indicator_count": len(items),
                "indicators": [i.get("title") for i in items],
            }
        )
    breakdown.sort(key=lambda c: c["score"], reverse=True)
    return min(100.0, total), breakdown


def _apply_floors(
    score: float, findings: list[dict[str, Any]], trace: list[str]
) -> float:
    severities = {str(f.get("severity", "")) for f in findings}
    if "critical" in severities:
        if score < 85:
            trace.append("Floor applied: critical finding(s) raised score to 85.")
        score = max(score, 85.0)
    if "high" in severities:
        if score < 40:
            trace.append("Floor applied: high-severity finding(s) raised score to 40.")
        score = max(score, 40.0)
    return min(100.0, score)


def _stages_summary(stages: list[dict[str, Any]]) -> dict[str, Any]:
    attempted = [s for s in stages if s.get("status") != "skipped"]
    completed = [s for s in attempted if s.get("status") in {"completed", "partial"}]
    ratio = len(completed) / len(attempted) if attempted else 0.0
    return {
        "attempted": len(attempted),
        "completed": len(completed),
        "ratio": round(ratio, 2),
        "stages": stages,
    }


def _essential_failed(input_type: str, stages: list[dict[str, Any]]) -> list[str]:
    key = {
        "url": _URL_KEY_STAGES,
        "email": _EMAIL_KEY_STAGES,
        "image": _IMAGE_KEY_STAGES,
    }.get(input_type, set())
    failed: list[str] = []
    for stage in stages:
        name = str(stage.get("name", ""))
        if name in key and stage.get("status") in {"failed", "unavailable"}:
            failed.append(name)
    return failed


def _ml_disagreement(
    input_type: str,
    analysis: dict[str, Any],
    findings: list[dict[str, Any]],
) -> list[str]:
    ml = analysis.get("ml") or {}
    if not ml.get("available"):
        return []
    prediction = str(ml.get("predicted_label", "")).lower()
    probability = ml.get("probability")
    if probability is None:
        return []
    try:
        probability = float(probability)
    except (TypeError, ValueError):
        return []

    heuristic_findings = [f for f in findings if f.get("source") != "ml"]
    heuristic_score, _ = _category_scores(heuristic_findings)
    if heuristic_score >= MALICIOUS_THRESHOLD:
        heuristic_class = "malicious"
    elif heuristic_score >= SUSPICIOUS_THRESHOLD:
        heuristic_class = "suspicious"
    else:
        heuristic_class = "no_significant_indicators"

    ml_class = "suspicious" if prediction in {"phishing", "malicious", "spam", "smishing", "1"} else "no_significant_indicators"
    if probability >= 0.75:
        ml_class = "malicious"
    if ml_class == "malicious" and heuristic_class == "no_significant_indicators":
        return [
            "The machine-learning classifier scored this input as high-risk while rule-based "
            "indicators were limited. Treat the model output as an uncalibrated signal, not proof."
        ]
    if ml_class == "no_significant_indicators" and heuristic_class in {"suspicious", "malicious"}:
        return [
            "The machine-learning classifier did not flag this input, while rule-based indicators "
            "were present. The engines disagree; review the listed indicators manually."
        ]
    return []


def _recommendations(input_type: str, classification: str) -> list[str]:
    common = {
        "malicious": [
            "Do not enter credentials, payment details or personal information on the inspected content.",
            "Do not download or run files from this source.",
            "If you already interacted with it, change affected passwords and enable multi-factor authentication.",
            "Report the incident to the relevant platform and, in India, consider https://cybercrime.gov.in/.",
        ],
        "suspicious": [
            "Verify the request independently using an official app or a website address you type yourself.",
            "Avoid clicking links until the destination is confirmed by another channel.",
            "Do not share passwords, one-time codes or payment details.",
        ],
        "no_significant_indicators": [
            "No significant indicators were found, but this is not a guarantee of safety.",
            "Confirm unexpected requests through an official channel before acting.",
            "Keep your browser and security software up to date.",
        ],
        "unknown": [
            "The available evidence is insufficient for a reliable assessment.",
            "Retry the scan later or inspect the content manually using trusted tools.",
            "Do not treat an inconclusive result as a clean result.",
        ],
    }[classification]

    if input_type == "email":
        common = [
            "Do not reply to the message or send additional information.",
            "Report the message as phishing to your email provider.",
            *common,
        ]
    elif input_type == "image":
        common = [
            "Do not scan QR codes from untrusted sources unless you intend to visit the destination.",
            "Preview the decoded destination before opening it, and never open it on a work device.",
            *common,
        ]
    elif input_type == "url":
        common = [
            "Type the organisation's official address manually instead of following the link.",
            *common,
        ]
    return common[:6]


def assess(
    input_type: str,
    analysis: dict[str, Any],
    findings_in: list[dict[str, Any]],
) -> dict[str, Any]:
    findings = _dedupe(findings_in)
    stages = [s for s in (analysis.get("stages") or []) if isinstance(s, dict)]
    trace: list[str] = []

    raw_score, breakdown = _category_scores(findings)
    trace.append(f"Category contributions sum to {raw_score:.1f} before floors and caps.")
    score = _apply_floors(raw_score, findings, trace)

    essential_failed = _essential_failed(input_type, stages)
    content_extracted = analysis.get("content_extracted")
    insufficient = False
    insufficient_reason = ""

    if input_type == "image" and content_extracted is False:
        insufficient = True
        insufficient_reason = (
            "The image was readable, but no QR content or OCR text could be extracted, so the "
            "visible content could not be assessed."
        )
    if essential_failed and score < SUSPICIOUS_THRESHOLD:
        insufficient = True
        if not insufficient_reason:
            insufficient_reason = (
                "Essential analysis stage(s) did not complete: "
                + ", ".join(essential_failed)
                + "."
            )
    if not findings and not insufficient and input_type == "url":
        # No static indicators is fine only if the page was actually retrieved.
        http_stage = next((s for s in stages if s.get("name") == "HTTP inspection"), None)
        if http_stage is None or http_stage.get("status") not in {"completed", "partial"}:
            insufficient = True
            insufficient_reason = (
                "The page could not be retrieved, so the absence of indicators is not informative."
            )

    if score >= MALICIOUS_THRESHOLD:
        classification = "malicious"
    elif score >= SUSPICIOUS_THRESHOLD:
        classification = "suspicious"
    elif insufficient:
        classification = "unknown"
    else:
        classification = "no_significant_indicators"

    trace.append(
        f"Thresholds: >= {MALICIOUS_THRESHOLD} high risk, >= {SUSPICIOUS_THRESHOLD} suspicious, "
        "otherwise low unless evidence is insufficient."
    )
    trace.append(f"Final heuristic score: {score:.1f}.")
    if insufficient_reason:
        trace.append(f"Insufficient-evidence rule applied: {insufficient_reason}")

    quality = _stages_summary(stages)
    categories_with_findings = len([c for c in breakdown if c["score"] >= 5])
    if categories_with_findings >= 3 and quality["ratio"] >= 0.75:
        confidence_level = "high"
    elif categories_with_findings >= 2 and quality["ratio"] >= 0.5:
        confidence_level = "moderate"
    else:
        confidence_level = "low"
    if classification == "unknown":
        confidence_level = "low"

    # Keep the verdict helper score away from 0 for unknown results so the UI
    # does not accidentally display a "clean" gauge.
    display_score = int(round(score))

    subject = {
        "url": "the URL and, where reachable, the page it serves",
        "email": "the supplied message text and extracted links",
        "image": "the uploaded image content and extracted links",
    }.get(input_type, "the submitted content")

    summaries = {
        "malicious": (
            f"Strong indicators were found for {subject}. The evidence supports treating this as "
            "high risk, although an automated assessment cannot prove malicious intent."
        ),
        "suspicious": (
            f"Several indicators were found for {subject}. Treat it with caution and verify through "
            "an official channel before interacting."
        ),
        "no_significant_indicators": (
            f"No significant indicators were detected for {subject} in the stages that completed. "
            "This is not a guarantee of safety."
        ),
        "unknown": (
            f"The assessment for {subject} is inconclusive. {insufficient_reason or 'Not enough reliable evidence was available.'}"
        ),
    }

    limitations = list(dict.fromkeys(list(analysis.get("limitations") or [])))
    limitations.append(
        "The risk score is a heuristic, uncalibrated score derived from indicators; it is not a "
        "probability of maliciousness."
    )
    for stage in stages:
        if stage.get("status") in {"failed", "unavailable"}:
            limitations.append(f"{stage.get('name')}: {stage.get('detail', 'not available')}")
    if insufficient_reason:
        limitations.append(insufficient_reason)
    limitations = list(dict.fromkeys(limitations))

    ml = analysis.get("ml") or {}
    engine_results: list[dict[str, Any]] = []
    for stage in stages:
        engine_results.append(
            {
                "name": stage.get("name"),
                "status": stage.get("status"),
                "detail": stage.get("detail", ""),
            }
        )
    if ml.get("available"):
        engine_results.append(
            {
                "name": "ML text classifier" if input_type == "email" else "ML classifier",
                "status": "completed",
                "detail": (
                    f"Predicted '{ml.get('predicted_label')}' with an uncalibrated score of "
                    f"{ml.get('probability')}."
                ),
            }
        )
    elif ml:
        engine_results.append(
            {
                "name": "ML classifier",
                "status": "unavailable",
                "detail": ml.get("reason", "Model artifact not available."),
            }
        )

    result = {
        "classification": classification,
        "classification_label": CLASSIFICATION_LABELS[classification],
        "risk_score": display_score,
        "risk_level": RISK_LEVELS[classification],
        "score_kind": "heuristic_uncalibrated",
        "summary": summaries[classification],
        "confidence": {
            "level": confidence_level,
            "calibrated": False,
            "explanation": (
                "Confidence reflects the number of independent indicator categories and completed "
                "analysis stages. It is not a statistical probability."
            ),
        },
        "supporting_findings": findings,
        "categories": breakdown,
        "stages": stages,
        "evidence_quality": quality,
        "decision_trace": trace,
        "limitations": limitations,
        "recommended_actions": _recommendations(input_type, classification),
        "engine_results": engine_results,
        "disagreements": _ml_disagreement(input_type, analysis, findings),
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
    return result
