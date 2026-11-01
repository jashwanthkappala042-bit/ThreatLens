"""Optional machine-learning model loading and inference.

Artifacts are only loaded when they exist. Nothing here fabricates a model or
metrics. Training/evaluation live in /ml and are documented in the README.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

_lock = threading.Lock()
_cache: dict[str, dict[str, Any]] = {}


def _load_artifact(path_value: str) -> dict[str, Any]:
    path = Path(path_value)
    if not path.exists():
        return {"available": False, "reason": "No trained model artifact is configured."}
    try:
        import joblib  # type: ignore
    except Exception:
        return {"available": False, "reason": "joblib/scikit-learn is not installed."}

    key = str(path.resolve())
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return {"available": False, "reason": "Model artifact cannot be read."}

    with _lock:
        cached = _cache.get(key)
        if cached and cached.get("mtime") == mtime:
            return cached["artifact"]

    try:
        loaded = joblib.load(path)
    except Exception:
        return {"available": False, "reason": "Model artifact could not be loaded."}

    if isinstance(loaded, dict) and "model" in loaded:
        artifact = {
            "available": True,
            "model": loaded.get("model"),
            "feature_names": loaded.get("feature_names"),
            "metadata": loaded.get("metadata", {}),
            "metrics": loaded.get("metrics", {}),
        }
    else:
        artifact = {"available": True, "model": loaded, "metadata": {}, "metrics": {}}

    with _lock:
        _cache[key] = {"mtime": mtime, "artifact": artifact}
    return artifact


def model_status(path_value: str) -> dict[str, Any]:
    artifact = _load_artifact(path_value)
    if not artifact.get("available"):
        return artifact
    metrics = artifact.get("metrics") or {}
    metadata = artifact.get("metadata") or {}
    return {
        "available": True,
        "metadata": metadata,
        "metrics": metrics,
        "calibrated": bool(metadata.get("calibrated", False)),
    }


def predict_email(path_value: str, text: str) -> dict[str, Any]:
    status = model_status(path_value)
    if not status.get("available"):
        return status
    artifact = _load_artifact(path_value)
    model = artifact.get("model")
    try:
        probabilities = model.predict_proba([text])[0]
        classes = list(model.classes_)
        classes_lower = [str(c).lower() for c in classes]
        phishing_index = None
        for index, name in enumerate(classes_lower):
            if name in {"phishing", "malicious", "spam", "1", "true"}:
                phishing_index = index
                break
        if phishing_index is None:
            phishing_index = len(classes) - 1
        score = float(probabilities[phishing_index])
        predicted = "phishing" if score >= 0.5 else "legitimate"
    except Exception:
        return {"available": False, "reason": "Model inference failed for this input."}
    return {
        "available": True,
        "task": "email_binary",
        "predicted_label": predicted,
        "probability": round(score, 4),
        "calibrated": bool((artifact.get("metadata") or {}).get("calibrated", False)),
        "model": {
            "name": (artifact.get("metadata") or {}).get("name", "Email classifier"),
            "trained_at": (artifact.get("metadata") or {}).get("trained_at"),
            "dataset": (artifact.get("metadata") or {}).get("dataset"),
            "dataset_license": (artifact.get("metadata") or {}).get("dataset_license"),
        },
        "metrics": artifact.get("metrics") or {},
        "reason": "",
    }


def predict_sms(path_value: str, text: str) -> dict[str, Any]:
    """Run the optional three-class SMS model (ham / spam / smishing).

    ``probability`` is P(spam) + P(smishing), i.e. the model's raw risk mass,
    because the rest of the UI expects a single uncalibrated risk score. The
    full class distribution is returned separately.
    """
    status = model_status(path_value)
    if not status.get("available"):
        return status
    artifact = _load_artifact(path_value)
    model = artifact.get("model")
    metadata = artifact.get("metadata") or {}
    try:
        probabilities = model.predict_proba([text])[0]
        class_labels = metadata.get("class_labels") or metadata.get("classes") or []
        names: list[str] = []
        for value in model.classes_:
            if isinstance(value, str):
                names.append(value.lower())
            else:
                index = int(value)
                if 0 <= index < len(class_labels):
                    names.append(str(class_labels[index]).lower())
                else:
                    names.append(str(value))
        distribution = {name: float(prob) for name, prob in zip(names, probabilities)}
        predicted = max(distribution, key=distribution.get)
        risk = 1.0 - distribution.get("ham", 0.0)
    except Exception:
        return {"available": False, "reason": "Model inference failed for this input."}
    return {
        "available": True,
        "task": "sms_3class",
        "predicted_label": predicted,
        "probability": round(risk, 4),
        "class_probabilities": {name: round(value, 4) for name, value in distribution.items()},
        "calibrated": bool(metadata.get("calibrated", False)),
        "model": {
            "name": metadata.get("name", "SMS classifier"),
            "trained_at": metadata.get("trained_at"),
            "dataset": metadata.get("dataset"),
            "dataset_license": metadata.get("dataset_license"),
        },
        "metrics": artifact.get("metrics") or {},
        "reason": "",
    }


def predict_url(path_value: str, features: dict[str, Any]) -> dict[str, Any]:
    status = model_status(path_value)
    if not status.get("available"):
        return status
    artifact = _load_artifact(path_value)
    model = artifact.get("model")
    names = artifact.get("feature_names") or []
    if not names:
        return {
            "available": False,
            "reason": "URL model artifact has no feature schema; retrain it with the provided script.",
        }
    try:
        import numpy as np

        row = []
        for name in names:
            value = features.get(name, 0)
            if isinstance(value, bool):
                value = int(value)
            elif isinstance(value, (list, tuple)):
                value = len(value)
            elif isinstance(value, str) or value is None:
                value = 0
            row.append(float(value))
        matrix = np.array([row], dtype=float)
        probabilities = model.predict_proba(matrix)[0]
        classes = [str(c).lower() for c in model.classes_]
        bad_index = None
        for index, name in enumerate(classes):
            if name in {"phishing", "malicious", "1", "bad", "true"}:
                bad_index = index
                break
        if bad_index is None:
            bad_index = len(classes) - 1
        score = float(probabilities[bad_index])
        predicted = "phishing" if score >= 0.5 else "legitimate"
    except Exception:
        return {"available": False, "reason": "Model inference failed for this input."}
    return {
        "available": True,
        "predicted_label": predicted,
        "probability": round(score, 4),
        "calibrated": bool((artifact.get("metadata") or {}).get("calibrated", False)),
        "model": {
            "name": (artifact.get("metadata") or {}).get("name", "URL classifier"),
            "trained_at": (artifact.get("metadata") or {}).get("trained_at"),
            "dataset": (artifact.get("metadata") or {}).get("dataset"),
            "dataset_license": (artifact.get("metadata") or {}).get("dataset_license"),
        },
        "metrics": artifact.get("metrics") or {},
        "reason": "",
    }


def reset_cache() -> None:
    with _lock:
        _cache.clear()


def read_metrics(path_value: str) -> dict[str, Any]:
    """Read a sibling metrics.json if present (for honest UI reporting)."""
    path = Path(path_value)
    metrics_path = path.with_name(path.stem + "_metrics.json")
    if not metrics_path.exists():
        return {}
    try:
        return json.loads(metrics_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
