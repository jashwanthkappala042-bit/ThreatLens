"""Train an optional URL phishing classifier from static URL features.

Requires a labelled CSV with columns:

    url,label

label may be phishing/malicious/1 or legitimate/benign/0. The script reuses the
backend feature extractor so training and inference share one schema.

Example:
    python ml/train_url_model.py --data ml/datasets/url_dataset.csv \
        --output ml/models/url_model.joblib

Only report metrics computed from the dataset you actually trained on.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.detection.url_features import extract_url_features  # noqa: E402
from app.utils.url_safety import validate_url  # noqa: E402

POSITIVE = {"phishing", "malicious", "1", "true", "bad", "fraud"}
NEGATIVE = {"legitimate", "benign", "0", "false", "safe", "good"}

# Only numeric and boolean features enter the model. Strings, lists and nested
# dictionaries are intentionally excluded so the artifact has a stable schema.
NUMERIC_FEATURES = [
    "url_length",
    "hostname_length",
    "path_length",
    "query_length",
    "is_ip_literal",
    "https",
    "port",
    "hostname_dots",
    "hyphens",
    "hostname_hyphens",
    "digits",
    "subdomain_count",
    "special_characters",
    "percent_encoded_sequences",
    "double_slash_in_path",
    "punycode",
    "suspicious_tld",
    "shortener",
    "keyword_count",
    "risky_extension",
    "query_parameter_count",
    "has_query",
    "at_in_path",
    "hostname_entropy",
    "scheme_port_mismatch",
    "brand_in_hostname",
    "brand_in_path",
]


def normalise_label(value: object) -> str | None:
    text = str(value).strip().lower()
    if text in POSITIVE:
        return "phishing"
    if text in NEGATIVE:
        return "legitimate"
    return None


def feature_row(url: str) -> list[float] | None:
    try:
        validated = validate_url(url, resolve=False)
    except Exception:
        return None
    features = extract_url_features(validated.normalized_url)
    row: list[float] = []
    for name in NUMERIC_FEATURES:
        value = features.get(name, 0)
        if isinstance(value, bool):
            value = int(value)
        elif isinstance(value, (list, tuple)):
            value = len(value)
        elif isinstance(value, str):
            value = 0
        elif value is None:
            value = 0
        row.append(float(value))
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, type=Path, help="Labelled CSV file.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("ml/models/url_model.joblib"),
        help="Destination artifact path.",
    )
    parser.add_argument("--dataset-name", default="", help="Human-readable dataset name.")
    parser.add_argument("--dataset-license", default="", help="Dataset licence or usage terms.")
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--min-rows", type=int, default=500)
    parser.add_argument("--trees", type=int, default=300)
    args = parser.parse_args()

    if not args.data.exists():
        print(f"Dataset not found: {args.data}", file=sys.stderr)
        print("See ml/datasets/README.md for the expected schema.", file=sys.stderr)
        return 2

    frame = pd.read_csv(args.data)
    missing = {"url", "label"} - set(frame.columns)
    if missing:
        print(f"Dataset is missing columns: {', '.join(sorted(missing))}", file=sys.stderr)
        return 2

    frame = frame.dropna(subset=["url", "label"]).copy()
    frame["label"] = frame["label"].map(normalise_label)
    frame = frame.dropna(subset=["label"])

    rows: list[list[float]] = []
    labels: list[str] = []
    skipped = 0
    for url, label in zip(frame["url"].astype(str), frame["label"]):
        vector = feature_row(url.strip())
        if vector is None:
            skipped += 1
            continue
        rows.append(vector)
        labels.append(label)

    if len(rows) < args.min_rows:
        print(
            f"Only {len(rows)} usable rows after validation (skipped {skipped}); "
            f"need at least {args.min_rows}. Training refused.",
            file=sys.stderr,
        )
        return 2

    matrix = np.asarray(rows, dtype=float)
    labels_array = np.asarray(labels)
    class_counts = pd.Series(labels).value_counts()
    if class_counts.min() < 50:
        print(f"Class counts are too small: {class_counts.to_dict()}.", file=sys.stderr)
        return 2

    x_train, x_test, y_train, y_test = train_test_split(
        matrix, labels_array, test_size=args.test_size, random_state=args.seed, stratify=labels_array
    )

    model = RandomForestClassifier(
        n_estimators=args.trees,
        max_depth=None,
        min_samples_leaf=2,
        class_weight="balanced_subsample",
        random_state=args.seed,
        n_jobs=-1,
    )
    model.fit(x_train, y_train)

    predicted = model.predict(x_test)
    probabilities = model.predict_proba(x_test)[:, list(model.classes_).index("phishing")]
    metrics = {
        "accuracy": round(float(accuracy_score(y_test, predicted)), 4),
        "precision": round(float(precision_score(y_test, predicted, pos_label="phishing")), 4),
        "recall": round(float(recall_score(y_test, predicted, pos_label="phishing")), 4),
        "f1": round(float(f1_score(y_test, predicted, pos_label="phishing")), 4),
        "roc_auc": round(float(roc_auc_score(y_test, probabilities)), 4),
        "confusion_matrix": confusion_matrix(y_test, predicted, labels=["legitimate", "phishing"]).tolist(),
        "test_rows": int(len(y_test)),
        "total_rows": int(len(rows)),
        "skipped_rows": int(skipped),
    }

    artifact = {
        "model": model,
        "feature_names": NUMERIC_FEATURES,
        "metadata": {
            "name": "Static URL feature Random Forest",
            "trained_at": datetime.now(timezone.utc).isoformat(),
            "dataset": args.dataset_name or str(args.data),
            "dataset_license": args.dataset_license or "not stated",
            "calibrated": False,
            "note": "Uncalibrated model over static URL features only; it cannot see page content.",
        },
        "metrics": metrics,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, args.output)
    metrics_path = args.output.with_name(args.output.stem + "_metrics.json")
    metrics_path.write_text(
        json.dumps({**metrics, "dataset": args.dataset_name or str(args.data)}, indent=2),
        encoding="utf-8",
    )

    print(f"Saved model to {args.output}")
    print(f"Saved metrics to {metrics_path}")
    print(json.dumps(metrics, indent=2))
    print(classification_report(y_test, predicted, digits=4))
    print(
        "Reminder: static URL features are weak evidence. A model score is shown as an "
        "additional signal, never as a replacement for the heuristic findings."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
