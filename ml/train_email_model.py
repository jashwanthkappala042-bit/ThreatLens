"""Train an optional email/message phishing classifier.

This script does not ship with data and does not fabricate metrics. It requires
a labelled CSV that you have the right to use. Expected columns:

    text,label

where label is one of: phishing, malicious, spam, 1 (positive) or
legitimate, benign, ham, 0 (negative). Rows are lower-cased and labels are
normalised to "phishing" / "legitimate".

Example:
    python ml/train_email_model.py --data ml/datasets/email_dataset.csv \
        --output ml/models/email_model.joblib

The output is a joblib dictionary compatible with backend/app/detection/ml.py.
Report only the metrics printed from your own dataset, and include the dataset
source and licence in --dataset-name / --dataset-license.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
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
from sklearn.pipeline import Pipeline

POSITIVE = {"phishing", "malicious", "spam", "1", "true", "fraud"}
NEGATIVE = {"legitimate", "benign", "ham", "0", "false", "safe"}


def normalise_label(value: object) -> str | None:
    text = str(value).strip().lower()
    if text in POSITIVE:
        return "phishing"
    if text in NEGATIVE:
        return "legitimate"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, type=Path, help="Labelled CSV file.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("ml/models/email_model.joblib"),
        help="Destination artifact path.",
    )
    parser.add_argument("--dataset-name", default="", help="Human-readable dataset name.")
    parser.add_argument("--dataset-license", default="", help="Dataset licence or usage terms.")
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--min-rows", type=int, default=200)
    args = parser.parse_args()

    if not args.data.exists():
        print(f"Dataset not found: {args.data}", file=sys.stderr)
        print("See ml/datasets/README.md for the expected schema.", file=sys.stderr)
        return 2

    frame = pd.read_csv(args.data)
    missing = {"text", "label"} - set(frame.columns)
    if missing:
        print(f"Dataset is missing columns: {', '.join(sorted(missing))}", file=sys.stderr)
        return 2

    frame = frame.dropna(subset=["text", "label"]).copy()
    frame["text"] = frame["text"].astype(str).str.strip()
    frame = frame[frame["text"].str.len() >= 10]
    frame["label"] = frame["label"].map(normalise_label)
    frame = frame.dropna(subset=["label"])
    frame = frame.drop_duplicates(subset=["text"])

    if len(frame) < args.min_rows:
        print(
            f"Only {len(frame)} usable rows after cleaning; need at least {args.min_rows}. "
            "A tiny dataset produces a meaningless model, so training is refused.",
            file=sys.stderr,
        )
        return 2

    counts = frame["label"].value_counts()
    if counts.min() < 20:
        print(
            f"Class counts are too small for a split: {counts.to_dict()}. "
            "Collect more examples of both classes.",
            file=sys.stderr,
        )
        return 2

    x_train, x_test, y_train, y_test = train_test_split(
        frame["text"],
        frame["label"],
        test_size=args.test_size,
        random_state=args.seed,
        stratify=frame["label"],
    )

    pipeline = Pipeline(
        [
            ("tfidf", TfidfVectorizer(lowercase=True, ngram_range=(1, 2), max_features=40_000)),
            (
                "model",
                LogisticRegression(max_iter=2_000, class_weight="balanced", random_state=args.seed),
            ),
        ]
    )
    pipeline.fit(x_train, y_train)

    predicted = pipeline.predict(x_test)
    probabilities = pipeline.predict_proba(x_test)[:, list(pipeline.classes_).index("phishing")]
    metrics = {
        "accuracy": round(float(accuracy_score(y_test, predicted)), 4),
        "precision": round(float(precision_score(y_test, predicted, pos_label="phishing")), 4),
        "recall": round(float(recall_score(y_test, predicted, pos_label="phishing")), 4),
        "f1": round(float(f1_score(y_test, predicted, pos_label="phishing")), 4),
        "roc_auc": round(float(roc_auc_score(y_test, probabilities)), 4),
        "confusion_matrix": confusion_matrix(y_test, predicted, labels=["legitimate", "phishing"]).tolist(),
        "test_rows": int(len(y_test)),
        "total_rows": int(len(frame)),
    }

    artifact = {
        "model": pipeline,
        "feature_names": None,
        "metadata": {
            "name": "TF-IDF + Logistic Regression email classifier",
            "trained_at": datetime.now(timezone.utc).isoformat(),
            "dataset": args.dataset_name or str(args.data),
            "dataset_license": args.dataset_license or "not stated",
            "calibrated": False,
            "note": "Uncalibrated model trained on a user-supplied dataset. Metrics apply only to this split.",
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
        "Reminder: these metrics describe this dataset split only. Do not present them as "
        "real-world detection rates."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
