"""Shared helpers for the reproducible ThreatLens training scripts.

Nothing here invents data or metrics. Every number written into a report or
model artifact is computed from the downloaded corpus in ``ml/datasets/raw``.
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

REPORTS_DIR = PROJECT_ROOT / "ml" / "reports"
MODELS_DIR = PROJECT_ROOT / "ml" / "models"


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def dataset_fingerprint(path: Path) -> dict[str, Any]:
    path = Path(path).resolve()
    try:
        display = str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")
    except ValueError:
        display = path.name
    return {
        "path": display,
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def evaluation_metrics(
    y_true: Iterable[int],
    y_pred: Iterable[int],
    y_score: np.ndarray | None,
    labels: list[str],
    positive_index: int | None = None,
) -> dict[str, Any]:
    """Compute the same metric set for every model and task.

    ``y_score`` is either a 1-D positive-class score (binary) or a 2-D class
    probability matrix (multiclass). ROC AUC is macro one-vs-rest for
    multiclass, which is reported for transparency but is not the selection
    metric.
    """
    from sklearn.metrics import (
        accuracy_score,
        confusion_matrix,
        f1_score,
        precision_score,
        recall_score,
        roc_auc_score,
    )

    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)
    report: dict[str, Any] = {
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 6),
        "precision_macro": round(float(precision_score(y_true, y_pred, average="macro", zero_division=0)), 6),
        "recall_macro": round(float(recall_score(y_true, y_pred, average="macro", zero_division=0)), 6),
        "f1_macro": round(float(f1_score(y_true, y_pred, average="macro", zero_division=0)), 6),
        "f1_weighted": round(float(f1_score(y_true, y_pred, average="weighted", zero_division=0)), 6),
        "per_class": {},
        "confusion_matrix": confusion_matrix(y_true, y_pred).tolist(),
        "labels": labels,
        "support": int(len(y_true)),
    }
    per = precision_score(y_true, y_pred, average=None, zero_division=0, labels=list(range(len(labels))))
    rec = recall_score(y_true, y_pred, average=None, zero_division=0, labels=list(range(len(labels))))
    f1s = f1_score(y_true, y_pred, average=None, zero_division=0, labels=list(range(len(labels))))
    for index, name in enumerate(labels):
        report["per_class"][name] = {
            "precision": round(float(per[index]), 6),
            "recall": round(float(rec[index]), 6),
            "f1": round(float(f1s[index]), 6),
            "support": int((y_true == index).sum()),
        }

    if y_score is not None:
        try:
            if y_score.ndim == 2 and y_score.shape[1] == 2 and positive_index is not None:
                report["roc_auc"] = round(float(roc_auc_score(y_true, y_score[:, positive_index])), 6)
            elif y_score.ndim == 2 and y_score.shape[1] > 2:
                report["roc_auc_ovr_macro"] = round(
                    float(roc_auc_score(y_true, y_score, multi_class="ovr", average="macro")), 6
                )
            elif y_score.ndim == 1:
                report["roc_auc"] = round(float(roc_auc_score(y_true, y_score)), 6)
        except ValueError:
            report["roc_auc"] = None
    return report


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def save_artifact(
    path: Path,
    *,
    model: Any,
    feature_names: list[str] | None,
    metadata: dict[str, Any],
    metrics: dict[str, Any],
) -> int:
    """Save the dictionary format expected by ``backend/app/detection/ml.py``."""
    import joblib

    path.parent.mkdir(parents=True, exist_ok=True)
    artifact = {
        "model": model,
        "feature_names": feature_names or [],
        "metadata": metadata,
        "metrics": metrics,
    }
    joblib.dump(artifact, path, compress=3)
    return path.stat().st_size


def environment() -> dict[str, str]:
    import joblib
    import numpy
    import pandas
    import sklearn

    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "scikit_learn": sklearn.__version__,
        "pandas": pandas.__version__,
        "numpy": numpy.__version__,
        "joblib": joblib.__version__,
    }
