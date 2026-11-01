"""Train and compare three-class SMS phishing classifiers.

Dataset (CC BY 4.0):
    SMS Phishing Dataset for Machine Learning and Pattern Recognition
    Mendeley Data, DOI 10.17632/f45bkkt8pr.1
    https://data.mendeley.com/datasets/f45bkkt8pr/1

The dataset preserves the original labels ``ham``, ``spam`` and ``smishing``
(case differences are normalised). Duplicate texts are removed after the shared
normaliser is applied, and any duplicate group with conflicting labels is
dropped rather than guessed.

Compared models:
    1. word TF-IDF (1-2 grams) + logistic regression
    2. word TF-IDF (1-2 grams) + linear SVM (probability-calibrated)
    3. character TF-IDF (2-5 grams) + logistic regression
    4. word TF-IDF (1-2 grams) + complement naive Bayes

Selection uses validation macro-F1 only. The chosen pipeline is refitted on
train + validation and its metrics on the untouched test split are stored with
the artifact.

Usage:
    .\\.venv\\Scripts\\python.exe ml\\train_sms_models.py
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.naive_bayes import ComplementNB
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC

from _common import (
    MODELS_DIR,
    REPORTS_DIR,
    dataset_fingerprint,
    environment,
    evaluation_metrics,
    save_artifact,
    save_json,
    utcnow,
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from app.detection.text_normalizer import MessageNormalizer  # noqa: E402

DEFAULT_DATA = Path(__file__).resolve().parent / "datasets" / "raw" / "sms" / "Dataset_5971.csv"
DEFAULT_MODEL = MODELS_DIR / "sms_model.joblib"
DEFAULT_REPORT = REPORTS_DIR / "sms_comparison.json"
LABELS = ["ham", "spam", "smishing"]
LABEL_ALIASES = {"ham": "ham", "spam": "spam", "smishing": "smishing", "smish": "smishing"}
MAX_CHARS = 1000
SEED = 42


def load_dataset(path: Path) -> tuple[list[str], list[str], dict]:
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    frame.columns = [column.strip().upper() for column in frame.columns]
    if "TEXT" not in frame.columns or "LABEL" not in frame.columns:
        raise SystemExit(f"Expected TEXT and LABEL columns, found {list(frame.columns)}")

    text_column = "TEXT"
    frame = frame.copy()
    frame["_label"] = frame["LABEL"].str.strip().str.lower().map(LABEL_ALIASES)
    frame["_text"] = frame[text_column].fillna("").astype(str)

    missing_label = int(frame["_label"].isna().sum())
    missing_text = int((frame["_text"].str.strip() == "").sum())
    frame = frame[frame["_label"].notna() & (frame["_text"].str.strip() != "")]

    # Deduplicate on normalised text. Drop ambiguous groups instead of picking
    # one label arbitrarily.
    frame["_key"] = frame["_text"].map(lambda value: hashlib.sha1(value.encode("utf-8", "ignore")).hexdigest())
    label_counts = frame.groupby("_key")["_label"].nunique()
    ambiguous = set(label_counts[label_counts > 1].index)
    before = len(frame)
    frame = frame[~frame["_key"].isin(ambiguous)]
    deduped = frame.drop_duplicates("_key", keep="first")

    stats = {
        "rows_read": int(before),
        "duplicate_texts_removed": int(before - len(deduped)),
        "ambiguous_duplicate_groups_dropped": len(ambiguous),
        "rows_missing_label": missing_label,
        "rows_empty_text": missing_text,
        "rows_used": int(len(deduped)),
        "label_counts": {label: int((deduped["_label"] == label).sum()) for label in LABELS},
        "original_label_spellings": sorted(set(frame["LABEL"].astype(str))),
    }
    return deduped["_text"].tolist(), deduped["_label"].tolist(), stats


def word_vectorizer() -> TfidfVectorizer:
    return TfidfVectorizer(
        ngram_range=(1, 2),
        min_df=1,
        max_features=50_000,
        sublinear_tf=True,
        strip_accents="unicode",
        token_pattern=r"(?u)\b\w+\b",
    )


def char_vectorizer() -> TfidfVectorizer:
    return TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(2, 5),
        min_df=2,
        max_features=100_000,
        sublinear_tf=True,
        lowercase=False,
    )


def build_models() -> dict[str, Pipeline]:
    def pipe(vectorizer: TfidfVectorizer, classifier) -> Pipeline:
        return Pipeline(
            [
                ("normalise", MessageNormalizer(max_chars=MAX_CHARS)),
                ("tfidf", vectorizer),
                ("classifier", classifier),
            ]
        )

    return {
        "word_tfidf_logistic_regression": pipe(
            word_vectorizer(),
            LogisticRegression(C=10.0, max_iter=3000, class_weight="balanced", random_state=SEED),
        ),
        "word_tfidf_linear_svm": pipe(
            word_vectorizer(),
            CalibratedClassifierCV(
                LinearSVC(C=0.5, class_weight="balanced", random_state=SEED, max_iter=5000),
                cv=3,
            ),
        ),
        "char_tfidf_logistic_regression": pipe(
            char_vectorizer(),
            LogisticRegression(C=10.0, max_iter=3000, class_weight="balanced", random_state=SEED),
        ),
        "word_tfidf_complement_nb": pipe(
            word_vectorizer(),
            ComplementNB(alpha=0.3),
        ),
    }


def split_indices(y: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    indices = np.arange(len(y))
    train_idx, holdout_idx = train_test_split(
        indices, test_size=0.30, random_state=SEED, stratify=y
    )
    val_idx, test_idx = train_test_split(
        holdout_idx, test_size=0.50, random_state=SEED, stratify=y[holdout_idx]
    )
    return train_idx, val_idx, test_idx


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--output", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    if not args.data.exists():
        raise SystemExit(f"Dataset not found: {args.data}\nRun ml/download_datasets.py first.")

    print(f"Loading {args.data}")
    texts, raw_labels, stats = load_dataset(args.data)
    y = np.array([LABELS.index(label) for label in raw_labels])
    print(f"Rows used: {len(texts):,}  labels: {stats['label_counts']}")

    train_idx, val_idx, test_idx = split_indices(y)
    x_train = [texts[i] for i in train_idx]
    x_val = [texts[i] for i in val_idx]
    x_test = [texts[i] for i in test_idx]

    comparison: list[dict] = []
    fitted: dict[str, Pipeline] = {}
    for name, pipeline in build_models().items():
        print(f"\nTraining {name} ...")
        started = time.perf_counter()
        pipeline.fit(x_train, y[train_idx])
        fit_seconds = time.perf_counter() - started
        val_prob = pipeline.predict_proba(x_val)
        val_pred = val_prob.argmax(axis=1)
        test_prob = pipeline.predict_proba(x_test)
        test_pred = test_prob.argmax(axis=1)
        entry = {
            "model": name,
            "fit_seconds_train_only": round(fit_seconds, 2),
            "validation": evaluation_metrics(y[val_idx], val_pred, val_prob, LABELS),
            "test": evaluation_metrics(y[test_idx], test_pred, test_prob, LABELS),
        }
        comparison.append(entry)
        fitted[name] = pipeline
        print(
            f"  val macro-F1 {entry['validation']['f1_macro']:.4f} | "
            f"test macro-F1 {entry['test']['f1_macro']:.4f} | "
            f"test accuracy {entry['test']['accuracy']:.4f} ({fit_seconds:.1f}s)"
        )

    best = max(comparison, key=lambda item: (item["validation"]["f1_macro"], item["validation"]["accuracy"]))
    best_name = best["model"]
    print(f"\nSelected on validation macro-F1: {best_name}")

    # Refit the selected pipeline on train + validation. The test split is
    # still untouched, so the saved metrics remain an honest held-out estimate.
    combined_idx = np.concatenate([train_idx, val_idx])
    final_pipeline = build_models()[best_name]
    started = time.perf_counter()
    final_pipeline.fit([texts[i] for i in combined_idx], y[combined_idx])
    final_fit_seconds = time.perf_counter() - started
    final_prob = final_pipeline.predict_proba(x_test)
    final_pred = final_prob.argmax(axis=1)
    final_metrics = evaluation_metrics(y[test_idx], final_pred, final_prob, LABELS)

    metadata = {
        "name": "ThreatLens SMS three-class classifier",
        "task": "sms_3class",
        "algorithm": best_name,
        "trained_at": utcnow(),
        "dataset": "SMS Phishing Dataset for Machine Learning and Pattern Recognition",
        "dataset_publisher": "Mendeley Data, DOI 10.17632/f45bkkt8pr.1",
        "dataset_url": "https://data.mendeley.com/datasets/f45bkkt8pr/1",
        "dataset_license": "CC BY 4.0",
        "dataset_fingerprint": dataset_fingerprint(args.data),
        "classes": LABELS,
        "class_labels": LABELS,
        "label_mapping": {"ham": "legitimate message", "spam": "unwanted commercial message", "smishing": "SMS phishing"},
        "preprocessing": (
            "Shared MessageNormalizer: HTML entities/tags removed, NFKC, lower-cased, "
            "punctuation spaced, whitespace collapsed, truncated to 1000 characters. "
            "Duplicate texts removed by SHA-1; ambiguous duplicates dropped."
        ),
        "split": "70% train / 15% validation / 15% test, stratified, seed 42",
        "selection_metric": "validation macro-F1",
        "calibrated": False,
        "environment": environment(),
        "source_script": "ml/train_sms_models.py",
        "notes": (
            "The SMS corpus is small and was collected before 2022; class balance and "
            "campaign vocabulary differ from live traffic. Probabilities are uncalibrated."
        ),
        "metrics": final_metrics,
    }

    size = save_artifact(
        args.output,
        model=final_pipeline,
        feature_names=[],
        metadata=metadata,
        metrics=final_metrics,
    )
    print(f"Saved {args.output} ({size / 1_000_000:.1f} MB)")

    report = {
        "generated_at": utcnow(),
        "dataset": metadata["dataset"],
        "dataset_license": metadata["dataset_license"],
        "dataset_fingerprint": metadata["dataset_fingerprint"],
        "dataset_stats": stats,
        "split": {
            "seed": SEED,
            "train": int(len(train_idx)),
            "validation": int(len(val_idx)),
            "test": int(len(test_idx)),
            "stratified": True,
        },
        "environment": environment(),
        "models": sorted(comparison, key=lambda item: item["validation"]["f1_macro"], reverse=True),
        "selected_model": best_name,
        "selected_refit_seconds": round(final_fit_seconds, 2),
        "selected_test_metrics": final_metrics,
        "artifact": str(Path(args.output).resolve().relative_to(Path(__file__).resolve().parent.parent)).replace("\\", "/"),
        "artifact_bytes": size,
    }
    save_json(args.report, report)
    print(f"Report written to {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
