"""Train and compare phishing-email text classifiers (chunked pipeline).

Dataset (CC BY 4.0):
    Phishing Email Detection Dataset (2025), merged corpus
    Zenodo record 17314806, DOI 10.5281/zenodo.17314806
    https://zenodo.org/records/17314806

The merged file contains 213,189 rows and two columns, ``body`` and ``label``,
where 1 = phishing (including spam/scam, per the dataset authors) and 0 = safe.
About 228 MB of email bodies are processed in chunks so the file is never
loaded twice into memory.

Cleaning and leakage control
----------------------------
* HTML entities/tags are removed with the shared, non-executing normaliser.
* Text is NFKC-normalised, lower-cased, punctuation-spaced (the corpus
  convention) and truncated to 4,000 characters for the word models and 1,500
  characters for the character model.
* Duplicates are removed by SHA-1 of the normalised text. Duplicate groups with
  conflicting labels are dropped rather than guessed.
* Splits are stratified 70/15/15. Exact duplicates never cross splits.

Compared models:
    1. word TF-IDF (1-2 grams) + logistic regression
    2. word TF-IDF (1-2 grams) + linear SVM (probability-calibrated)
    3. character TF-IDF (2-4 grams) + logistic regression
    4. word TF-IDF (1-2 grams) + complement naive Bayes

The model with the best validation macro-F1 is refitted on train + validation
and evaluated once on the untouched test split before being saved.

Usage:
    .\\.venv\\Scripts\\python.exe ml\\train_email_models.py
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

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))
from app.detection.text_normalizer import MessageNormalizer, normalize_message_text  # noqa: E402

DEFAULT_DATA = Path(__file__).resolve().parent / "datasets" / "raw" / "phishing_email_merged.csv"
DEFAULT_MODEL = MODELS_DIR / "email_model.joblib"
DEFAULT_REPORT = REPORTS_DIR / "email_comparison.json"
LABELS = ["legitimate", "phishing"]
SEED = 42
WORD_MAX_CHARS = 4000
CHAR_MAX_CHARS = 1500
CHUNK_ROWS = 50_000


def load_dataset(path: Path, max_rows: int = 0) -> tuple[list[str], np.ndarray, dict]:
    """Stream the CSV, normalise, and deduplicate without loading raw text twice."""
    seen: dict[str, tuple[str, int]] = {}
    conflicts: set[str] = set()
    stats = {
        "rows_read": 0,
        "rows_missing_label": 0,
        "rows_missing_body": 0,
        "rows_empty_after_normalisation": 0,
        "duplicate_texts_removed": 0,
        "ambiguous_duplicate_groups_dropped": 0,
        "label_counts_raw": {"0": 0, "1": 0},
    }

    reader = pd.read_csv(
        path,
        usecols=["body", "label"],
        dtype=str,
        keep_default_na=False,
        chunksize=CHUNK_ROWS,
    )
    started = time.perf_counter()
    for chunk in reader:
        bodies = chunk["body"].astype(str).tolist()
        labels = chunk["label"].astype(str).str.strip().tolist()
        for body, label_text in zip(bodies, labels):          
            if max_rows and stats["rows_read"] >= max_rows:
                break
            stats["rows_read"] += 1
            if label_text in {"", "nan", "none"}:
                stats["rows_missing_label"] += 1
                continue
            try:
                label = int(float(label_text))
            except ValueError:
                stats["rows_missing_label"] += 1
                continue
            if label not in {0, 1}:
                stats["rows_missing_label"] += 1
                continue
            if not body.strip():
                stats["rows_missing_body"] += 1
                continue
            normalised = normalize_message_text(body, WORD_MAX_CHARS)
            if not normalised:
                stats["rows_empty_after_normalisation"] += 1
                continue
            key = hashlib.sha1(normalised.encode("utf-8", "ignore")).hexdigest()
            previous = seen.get(key)
            if previous is not None:
                stats["duplicate_texts_removed"] += 1
                if previous[1] != label:
                    conflicts.add(key)
                continue
            seen[key] = (normalised, label)
            stats["label_counts_raw"][str(label)] += 1
        print(
            f"  read {stats['rows_read']:,} rows; {len(seen):,} unique texts so far "
            f"({time.perf_counter() - started:.1f}s)",
            flush=True,
        )
        if max_rows and stats["rows_read"] >= max_rows:
            break

    print(f"Streamed and normalised in {time.perf_counter() - started:.1f}s")

    texts: list[str] = []
    labels: list[int] = []
    for key, (text, label) in seen.items():
        if key in conflicts:
            continue
        texts.append(text)
        labels.append(label)

    stats["ambiguous_duplicate_groups_dropped"] = len(conflicts)
    stats["unique_texts_used"] = len(texts)
    stats["label_counts_final"] = {
        "legitimate_0": int(sum(1 for label in labels if label == 0)),
        "phishing_1": int(sum(1 for label in labels if label == 1)),
    }
    return texts, np.asarray(labels, dtype=np.int8), stats


def word_vectorizer() -> TfidfVectorizer:
    return TfidfVectorizer(
        ngram_range=(1, 2),
        min_df=3,
        max_features=300_000,
        sublinear_tf=True,
        strip_accents="unicode",
        token_pattern=r"(?u)\b\w+\b",
        dtype=np.float32,
    )


def char_vectorizer() -> TfidfVectorizer:
    return TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(2, 4),
        min_df=3,
        max_features=150_000,
        sublinear_tf=True,
        lowercase=False,
        dtype=np.float32,
    )


def build_models() -> dict[str, Pipeline]:
    def pipeline(vectorizer: TfidfVectorizer, classifier, max_chars: int) -> Pipeline:
        return Pipeline(
            [
                ("normalise", MessageNormalizer(max_chars=max_chars)),
                ("tfidf", vectorizer),
                ("classifier", classifier),
            ]
        )

    return {
        "word_tfidf_logistic_regression": pipeline(
            word_vectorizer(),
            LogisticRegression(
                C=4.0,
                solver="liblinear",
                max_iter=3000,
                class_weight="balanced",
                random_state=SEED,
            ),
            WORD_MAX_CHARS,
        ),
        "word_tfidf_linear_svm": pipeline(
            word_vectorizer(),
            CalibratedClassifierCV(
                LinearSVC(C=0.5, class_weight="balanced", random_state=SEED, max_iter=5000),
                cv=3,
            ),
            WORD_MAX_CHARS,
        ),
        "char_tfidf_logistic_regression": pipeline(
            char_vectorizer(),
            LogisticRegression(
                C=4.0,
                solver="liblinear",
                max_iter=3000,
                class_weight="balanced",
                random_state=SEED,
            ),
            CHAR_MAX_CHARS,
        ),
        "word_tfidf_complement_nb": pipeline(
            word_vectorizer(),
            ComplementNB(alpha=0.3),
            WORD_MAX_CHARS,
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--output", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--max-rows",
        type=int,
        default=0,
        help="Optional row limit for a smoke test (0 = all rows).",
    )
    parser.add_argument(
        "--only",
        action="append",
        choices=sorted(build_models()),
        help="Train only the named model(s). Default: all.",
    )
    args = parser.parse_args()

    if not args.data.exists():
        raise SystemExit(f"Dataset not found: {args.data}\nRun ml/download_datasets.py first.")

    print(f"Loading {args.data}")
    texts, y, stats = load_dataset(args.data, args.max_rows)
    if len(texts) < 1_000:
        raise SystemExit(f"Only {len(texts)} usable rows; refusing to train on a tiny sample.")
    print(f"Unique texts used: {len(texts):,}  labels: {stats['label_counts_final']}")
    print(
        f"Removed duplicates: {stats['duplicate_texts_removed']:,}; "
        f"ambiguous duplicate groups dropped: {stats['ambiguous_duplicate_groups_dropped']:,}"
    )

    indices = np.arange(len(y))
    train_idx, holdout_idx = train_test_split(
        indices, test_size=0.30, random_state=SEED, stratify=y
    )
    val_idx, test_idx = train_test_split(
        holdout_idx, test_size=0.50, random_state=SEED, stratify=y[holdout_idx]
    )
    x_train = [texts[i] for i in train_idx]
    x_val = [texts[i] for i in val_idx]
    x_test = [texts[i] for i in test_idx]
    print(
        f"Split: train {len(train_idx):,} / val {len(val_idx):,} / test {len(test_idx):,}"
    )

    selected = args.only or list(build_models())
    comparison: list[dict] = []
    for name in selected:
        print(f"\nTraining {name} ...")
        pipeline = build_models()[name]
        started = time.perf_counter()
        pipeline.fit(x_train, y[train_idx])
        fit_seconds = time.perf_counter() - started
        val_prob = pipeline.predict_proba(x_val)
        test_prob = pipeline.predict_proba(x_test)
        entry = {
            "model": name,
            "fit_seconds_train_only": round(fit_seconds, 2),
            "validation": evaluation_metrics(
                y[val_idx], val_prob.argmax(axis=1), val_prob, LABELS, positive_index=1
            ),
            "test": evaluation_metrics(
                y[test_idx], test_prob.argmax(axis=1), test_prob, LABELS, positive_index=1
            ),
        }
        comparison.append(entry)
        n_features = len(pipeline.named_steps["tfidf"].vocabulary_)
        entry["n_features"] = int(n_features)
        print(
            f"  {n_features:,} features | val macro-F1 {entry['validation']['f1_macro']:.4f} "
            f"/ AUC {entry['validation'].get('roc_auc')} | test macro-F1 "
            f"{entry['test']['f1_macro']:.4f} / accuracy {entry['test']['accuracy']:.4f} "
            f"({fit_seconds:.1f}s)"
        )

    best = max(comparison, key=lambda item: (item["validation"]["f1_macro"], item["validation"]["accuracy"]))
    best_name = best["model"]
    print(f"\nSelected on validation macro-F1: {best_name}")

    combined_idx = np.concatenate([train_idx, val_idx])
    final_pipeline = build_models()[best_name]
    started = time.perf_counter()
    final_pipeline.fit([texts[i] for i in combined_idx], y[combined_idx])
    final_fit_seconds = time.perf_counter() - started
    final_prob = final_pipeline.predict_proba(x_test)
    final_metrics = evaluation_metrics(
        y[test_idx], final_prob.argmax(axis=1), final_prob, LABELS, positive_index=1
    )

    metadata = {
        "name": "ThreatLens phishing email classifier",
        "task": "email_binary",
        "algorithm": best_name,
        "trained_at": utcnow(),
        "dataset": "Phishing Email Detection Dataset (2025), merged corpus",
        "dataset_publisher": "Zenodo record 17314806, DOI 10.5281/zenodo.17314806",
        "dataset_url": "https://zenodo.org/records/17314806",
        "dataset_license": "CC BY 4.0",
        "dataset_fingerprint": dataset_fingerprint(args.data),
        "classes": LABELS,
        "label_mapping": {"0": "legitimate", "1": "phishing (all spam/scam grouped by authors)"},
        "preprocessing": (
            "Shared MessageNormalizer (HTML tags/entities removed, NFKC, lower-cased, punctuation "
            "spaced, whitespace collapsed); 4,000 characters for word models, 1,500 for the "
            "character model. Exact duplicates removed by SHA-1 of normalised text; ambiguous "
            "duplicates dropped."
        ),
        "split": "70% train / 15% validation / 15% test, stratified, seed 42",
        "selection_metric": "validation macro-F1",
        "calibrated": False,
        "environment": environment(),
        "source_script": "ml/train_email_models.py",
        "notes": (
            "The corpus spans 1998-2008 (Ling, Enron, SpamAssassin, TREC 2005-2007, CEAS, "
            "Nazario_5, Nigerian_5). Vocabulary, formatting and campaigns differ from modern "
            "mail. The dataset folds spam and scam into the phishing label. Scores are "
            "uncalibrated and exact-duplicate removal does not remove near-duplicate threads."
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
        "artifact": str(Path(args.output).resolve().relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "artifact_bytes": size,
    }
    save_json(args.report, report)
    print(f"Report written to {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
