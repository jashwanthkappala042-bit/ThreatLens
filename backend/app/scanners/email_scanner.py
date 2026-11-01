"""Email / message text analysis orchestration."""

from __future__ import annotations

from typing import Any

from flask import current_app

from ..detection import ml
from ..detection.email_heuristics import analyze_email_text
from ..detection.findings import finding
from .url_enrichment import analyze_extracted_urls


def _append_email_ml(
    ml_result: dict[str, Any],
    findings: list[dict[str, Any]],
    stages: list[dict[str, Any]],
    limitations: list[str],
) -> None:
    score = float(ml_result.get("probability", 0))
    if score >= 0.5:
        severity = "high" if score >= 0.75 else "medium"
        findings.append(
            finding(
                "ml_email_prediction",
                "Text classifier flagged this message",
                "A trained TF-IDF + logistic-regression classifier scored this message as likely "
                "phishing. The score is not a calibrated probability; review the rule-based "
                "indicators and the model's documented limitations.",
                severity,
                "ml_signal",
                "ml",
                evidence={
                    "model_score": score,
                    "calibrated": bool(ml_result.get("calibrated")),
                    "model": ml_result.get("model", {}),
                },
            )
        )
    stages.append(
        {
            "name": "ML text classifier (optional)",
            "status": "completed",
            "detail": (
                f"Model score {score:.3f} (uncalibrated) for class "
                f"'{ml_result.get('predicted_label')}'."
            ),
        }
    )
    limitations.append(
        "The ML text classifier's score is not statistically calibrated and is not a probability "
        "of maliciousness."
    )


def _append_sms_ml(
    ml_result: dict[str, Any],
    findings: list[dict[str, Any]],
    stages: list[dict[str, Any]],
    limitations: list[str],
) -> None:
    score = float(ml_result.get("probability", 0))
    distribution = ml_result.get("class_probabilities") or {}
    predicted = str(ml_result.get("predicted_label", ""))
    if predicted == "smishing":
        severity = "high" if score >= 0.75 else "medium"
        findings.append(
            finding(
                "ml_sms_prediction",
                "SMS classifier flagged this message as smishing",
                "A three-class model trained on a public SMS phishing corpus predicted smishing "
                "(SMS phishing). The score is uncalibrated and the training corpus is small and "
                "older than live traffic; review the rule-based indicators.",
                severity,
                "ml_signal",
                "ml",
                evidence={
                    "model_score": score,
                    "class_probabilities": distribution,
                    "calibrated": bool(ml_result.get("calibrated")),
                    "model": ml_result.get("model", {}),
                },
            )
        )
    elif predicted == "spam":
        severity = "medium" if score >= 0.6 else "low"
        findings.append(
            finding(
                "ml_sms_prediction",
                "SMS classifier flagged this message as spam",
                "A three-class model trained on a public SMS corpus predicted spam. Spam is not "
                "necessarily phishing, so this is a weaker signal than a smishing prediction.",
                severity,
                "ml_signal",
                "ml",
                evidence={
                    "model_score": score,
                    "class_probabilities": distribution,
                    "calibrated": bool(ml_result.get("calibrated")),
                    "model": ml_result.get("model", {}),
                },
            )
        )
    stages.append(
        {
            "name": "ML SMS classifier (optional, 3-class)",
            "status": "completed",
            "detail": (
                "Class probabilities: "
                + ", ".join(f"{name} {value:.3f}" for name, value in sorted(distribution.items()))
                + f". Risk mass (1 - ham) {score:.3f}; uncalibrated."
            ),
        }
    )
    limitations.append(
        "The SMS model predicts ham, spam or smishing from a 5,947-message corpus collected before "
        "2022. Its scores are uncalibrated and its class balance differs from live traffic."
    )


def analyze_email(subject: str, sender: str, body: str) -> dict[str, Any]:
    config = current_app.config
    heuristic = analyze_email_text(subject, sender, body)
    findings: list[dict[str, Any]] = list(heuristic["signals"])
    stages: list[dict[str, Any]] = list(heuristic["stages"])
    limitations: list[str] = list(heuristic["limitations"])

    message_text = f"{subject}\n{body}"
    sms_path = str(config.get("SMS_MODEL_PATH", ""))
    sms_max_chars = int(config.get("SMS_MAX_CHARS", 700))
    # A body-only short message is the shape of an SMS. If a subject is
    # supplied we treat the input as an email and use the email model, so the
    # two classifiers never score the same message.
    use_sms = bool(sms_path) and not (subject or "").strip() and len(message_text) <= sms_max_chars

    ml_result: dict[str, Any] = {
        "available": False,
        "reason": "No trained email model is configured.",
    }
    if use_sms:
        ml_result = ml.predict_sms(sms_path, message_text)
        if ml_result.get("available"):
            _append_sms_ml(ml_result, findings, stages, limitations)
        else:
            # Fall back to the binary email model when only that artifact exists.
            ml_result = ml.predict_email(str(config.get("EMAIL_MODEL_PATH", "")), message_text)
            if ml_result.get("available"):
                _append_email_ml(ml_result, findings, stages, limitations)
            else:
                stages.append(
                    {
                        "name": "ML text classifier (optional)",
                        "status": "unavailable",
                        "detail": ml_result.get("reason", "No trained text model is configured."),
                    }
                )
                limitations.append(
                    "No trained text classifier is available; results rely on documented rule-based "
                    "heuristics only. See ml/README.md for training instructions."
                )
    else:
        ml_result = ml.predict_email(str(config.get("EMAIL_MODEL_PATH", "")), message_text)
        if ml_result.get("available"):
            _append_email_ml(ml_result, findings, stages, limitations)
        else:
            stages.append(
                {
                    "name": "ML text classifier (optional)",
                    "status": "unavailable",
                    "detail": ml_result.get("reason", "No trained email model is configured."),
                }
            )
            limitations.append(
                "No trained email classifier is available; results rely on documented rule-based "
                "heuristics only. See ml/README.md for training instructions."
            )

    enrichment = analyze_extracted_urls(
        heuristic["extracted_urls"],
        limit=int(config.get("MAX_EXTRACTED_URLS_EMAIL", 3)),
        source_label="email or message body",
    )
    findings.extend(enrichment["findings"])
    stages.append(enrichment["stage"])
    limitations.extend(enrichment["limitations"])

    has_text = bool((body or "").strip() or (subject or "").strip())
    if not has_text:
        limitations.append("The message body was empty, so text analysis had no content to assess.")

    return {
        "input": {
            "subject": heuristic["subject"],
            "sender": heuristic["sender"],
            "body_preview": heuristic["body"][:1000],
        },
        "features": heuristic["features"],
        "signals": findings,
        "ml": ml_result,
        "extracted_urls": heuristic["extracted_urls"],
        "url_results": enrichment["results"],
        "stages": stages,
        "limitations": list(dict.fromkeys(limitations)),
        "content_extracted": has_text,
    }
