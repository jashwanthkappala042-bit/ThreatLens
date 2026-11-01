"""Tests for the shared text normaliser and optional ML artifacts."""

from __future__ import annotations

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from app.detection import ml
from app.detection.text_normalizer import (
    MessageNormalizer,
    normalize_message_text,
    strip_html,
)


def test_normaliser_matches_corpus_convention_and_is_idempotent():
    raw = "Verify at https://Example.com/Login?token=ABC now!"
    once = normalize_message_text(raw)
    assert once == "verify at https : / / example . com / login ? token = abc now !"
    assert normalize_message_text(once) == once


def test_normaliser_removes_markup_and_entities():
    raw = "<html><body><p>Hello &amp; welcome</p><script>alert(1)</script></body></html>"
    assert strip_html(raw).strip().startswith("Hello & welcome")
    assert normalize_message_text(raw) == "hello & welcome"


def test_plain_text_with_angle_brackets_is_not_mangled():
    assert normalize_message_text("a < b and c > d") == "a < b and c > d"


def _write_text_artifact(path, *, labels, metadata=None):
    pipeline = Pipeline(
        [
            ("normalise", MessageNormalizer(max_chars=500)),
            ("tfidf", TfidfVectorizer(ngram_range=(1, 2), token_pattern=r"(?u)\b\w+\b")),
            ("classifier", LogisticRegression(max_iter=1000)),
        ]
    )
    texts = ["win a free prize now", "meeting notes attached", "urgent verify account"]
    pipeline.fit(texts, labels)
    joblib.dump(
        {
            "model": pipeline,
            "feature_names": [],
            "metadata": metadata
            or {"name": "test model", "trained_at": "2026-01-01T00:00:00Z", "calibrated": False},
            "metrics": {"accuracy": 1.0},
        },
        path,
    )


def test_predict_sms_round_trips_a_pickled_pipeline(tmp_path):
    path = tmp_path / "sms.joblib"
    _write_text_artifact(path, labels=["smishing", "ham", "smishing"])
    result = ml.predict_sms(str(path), "urgent: verify your account now")
    assert result["available"] is True
    assert result["task"] == "sms_3class"
    assert result["predicted_label"] in {"ham", "spam", "smishing"}
    assert set(result["class_probabilities"]) <= {"ham", "spam", "smishing"}
    assert 0.0 <= result["probability"] <= 1.0


def test_predict_sms_maps_integer_classes_through_metadata(tmp_path):
    path = tmp_path / "sms_int.joblib"
    _write_text_artifact(
        path,
        labels=[2, 0, 2],
        metadata={
            "name": "integer-class model",
            "trained_at": "2026-01-01T00:00:00Z",
            "calibrated": False,
            "classes": ["ham", "spam", "smishing"],
        },
    )
    result = ml.predict_sms(str(path), "urgent verify account now")
    assert result["available"] is True
    assert set(result["class_probabilities"]) <= {"ham", "spam", "smishing"}
    assert result["predicted_label"] in {"ham", "smishing"}


def test_predict_email_reports_phishing_probability(tmp_path):
    path = tmp_path / "email.joblib"
    _write_text_artifact(path, labels=["phishing", "legitimate", "phishing"])
    result = ml.predict_email(str(path), "verify your account now")
    assert result["available"] is True
    assert result["task"] == "email_binary"
    assert result["predicted_label"] in {"phishing", "legitimate"}
    assert 0.0 <= result["probability"] <= 1.0


def test_missing_artifact_is_reported_not_faked(tmp_path):
    result = ml.predict_sms(str(tmp_path / "absent.joblib"), "hello")
    assert result["available"] is False
    assert result["reason"]


def test_scanner_routes_body_only_short_message_to_sms_model(app, tmp_path):
    path = tmp_path / "sms.joblib"
    _write_text_artifact(path, labels=["smishing", "ham", "smishing"])
    app.config["SMS_MODEL_PATH"] = str(path)

    with app.app_context():
        from app.scanners.email_scanner import analyze_email

        result = analyze_email("", "", "urgent: verify your account now")

    assert result["ml"]["task"] == "sms_3class"
    assert result["ml"]["available"] is True
    assert "class_probabilities" in result["ml"]
    assert any(stage["name"].startswith("ML SMS classifier") for stage in result["stages"])


def test_scanner_routes_message_with_subject_to_email_model(app, tmp_path):
    e = tmp_path / "email.joblib"
    s = tmp_path / "sms.joblib"
    _write_text_artifact(e, labels=["phishing", "legitimate", "phishing"])
    _write_text_artifact(s, labels=["smishing", "ham", "smishing"])
    app.config["EMAIL_MODEL_PATH"] = str(e)
    app.config["SMS_MODEL_PATH"] = str(s)

    with app.app_context():
        from app.scanners.email_scanner import analyze_email

        result = analyze_email("Account notice", "", "verify your account now")

    assert result["ml"]["task"] == "email_binary"
