"""Train and benchmark URL phishing classifiers on the PhiUSIIL dataset.

Dataset (CC BY 4.0):
    PhiUSIIL Phishing URL Dataset
    UCI Machine Learning Repository, dataset 967
    https://archive.ics.uci.edu/dataset/967/phiusiil+phishing+url+dataset

The dataset has 235,795 rows and 56 columns. Its ``label`` column is 1 for a
legitimate page and 0 for a phishing page; this script maps the target to
1 = phishing.

Three feature tiers are compared so that benchmark performance is not confused
with what the running application can actually compute:

``dataset_url_only``
    18 numeric columns that are properties of the URL string. No page content.
``threatlens_static``
    Features produced by ``backend/app/detection/url_features.py`` from the URL
    alone. This is the only deployable tier; its best model is saved.
``all_numeric_upper_bound``
    Every numeric dataset column, including page-derived fields and derived
    scores such as ``URLSimilarityIndex``. This is an upper bound only and is
    never deployed.

Leakage handling
----------------
``URLSimilarityIndex`` is 100 for every legitimate row in this dataset, and
``TLDLegitimateProb``/``URLCharProb`` are derived statistics. Page-derived
fields (title, favicon, iframe, copyright, social network, redirects, ...)
cannot be known before fetching and rendering a page. They are excluded from
the deployable tier and called out explicitly in the report.

Splitting
---------
Rows are split 70/15/15 with ``GroupShuffleSplit`` on the registrable domain so
that the same domain cannot appear in both training and test data. Without
this, 15,709 duplicate domains and 54 label-conflicting domains would inflate
the measured accuracy.

Usage:
    .\\.venv\\Scripts\\python.exe ml\\train_url_models.py
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
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
from app.detection.url_features import extract_url_features, registrable_domain  # noqa: E402
from app.utils.url_safety import InvalidTarget, validate_url  # noqa: E402

DEFAULT_DATA = (
    Path(__file__).resolve().parent
    / "datasets"
    / "raw"
    / "phiusiil"
    / "PhiUSIIL_Phishing_URL_Dataset.csv"
)
DEFAULT_MODEL = MODELS_DIR / "url_model.joblib"
DEFAULT_REPORT = REPORTS_DIR / "url_comparison.json"
SEED = 42
LABELS = ["legitimate", "phishing"]

# Numeric columns that are properties of the URL string alone.
DATASET_URL_ONLY = [
    "URLLength",
    "DomainLength",
    "IsDomainIP",
    "TLDLength",
    "NoOfSubDomain",
    "HasObfuscation",
    "NoOfObfuscatedChar",
    "ObfuscationRatio",
    "NoOfLettersInURL",
    "LetterRatioInURL",
    "NoOfDegitsInURL",
    "DegitRatioInURL",
    "NoOfEqualsInURL",
    "NoOfQMarkInURL",
    "NoOfAmpersandInURL",
    "NoOfOtherSpecialCharsInURL",
    "SpacialCharRatioInURL",
    "IsHTTPS",
]

# Fields that are derived from the label distribution or from page content and
# therefore must never be treated as deployable URL features.
LEAKY_OR_PAGE_DERIVED = [
    "URLSimilarityIndex",
    "CharContinuationRate",
    "TLDLegitimateProb",
    "URLCharProb",
    "LineOfCode",
    "LargestLineLength",
    "HasTitle",
    "Title",
    "DomainTitleMatchScore",
    "URLTitleMatchScore",
    "HasFavicon",
    "Robots",
    "IsResponsive",
    "NoOfURLRedirect",
    "HasDescription",
    "NoOfPopup",
    "NoOfiFrame",
    "HasExternalFormSubmit",
    "HasSocialNet",
    "HasSubmitButton",
    "HasHiddenFields",
    "HasPasswordField",
    "Bank",
    "Pay",
    "Crypto",
    "HasCopyrightInfo",
    "NoOfImage",
    "NoOfCSS",
    "NoOfJS",
    "NoOfSelfRef",
    "NoOfEmptyRef",
    "NoOfExternalRef",
    "Domain",
    "TLD",
    "URL",
    "FILENAME",
]

# Exactly the static keys produced by extract_url_features() and consumed by
# ml.predict_url(). Lists are converted to their length, booleans to 0/1.
THREATLENS_STATIC = [
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
    "query_parameter_count",
    "has_query",
    "at_in_path",
    "hostname_entropy",
    "scheme_port_mismatch",
    "brand_in_hostname",
    "brand_in_path",
]


def _numeric(value) -> float:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (list, tuple, set)):
        return float(len(value))
    if value is None:
        return 0.0
    if isinstance(value, str):
        return 0.0
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if np.isfinite(number) else 0.0


def build_features(frame: pd.DataFrame) -> tuple[dict[str, np.ndarray], np.ndarray, np.ndarray, dict, list[str]]:
    frame = frame.reset_index(drop=True)
    rows_url_only: list[list[float]] = []
    rows_static: list[list[float]] = []
    kept_labels: list[int] = []
    groups: list[str] = []
    kept_positions: list[int] = []
    rejected: list[dict] = []

    for position, record in enumerate(frame.itertuples(index=False)):
        url = str(getattr(record, "URL"))
        try:
            target = validate_url(url, resolve=False)
        except InvalidTarget as exc:
            rejected.append({"url": url[:300], "reason": str(exc)[:200]})
            continue
        features = extract_url_features(target.normalized_url)
        rows_url_only.append([_numeric(getattr(record, column)) for column in DATASET_URL_ONLY])
        rows_static.append([_numeric(features.get(column)) for column in THREATLENS_STATIC])
        kept_labels.append(1 if int(getattr(record, "label")) == 0 else 0)
        groups.append(registrable_domain(str(getattr(record, "Domain"))))
        kept_positions.append(position)

    numeric_columns = [
        column
        for column in frame.columns
        if column != "label" and pd.api.types.is_numeric_dtype(frame[column])
    ]
    # The all-numeric tier is aligned with the rows that passed validation.
    all_numeric = frame.loc[kept_positions, numeric_columns].to_numpy(dtype=np.float32, copy=True)

    matrices = {
        "dataset_url_only": np.asarray(rows_url_only, dtype=np.float32),
        "threatlens_static": np.asarray(rows_static, dtype=np.float32),
        "all_numeric_upper_bound": all_numeric,
    }
    y = np.asarray(kept_labels, dtype=np.int8)
    group_array = np.asarray(groups)
    metadata = {
        "rejected_rows": len(rejected),
        "rejected_examples": rejected[:10],
        "numeric_columns": numeric_columns,
    }
    if not (len(matrices["dataset_url_only"]) == len(y) == len(matrices["all_numeric_upper_bound"])):
        raise RuntimeError("Feature tiers are misaligned after validation filtering.")
    return matrices, group_array, y, metadata, numeric_columns


def build_models() -> dict[str, object]:
    return {
        "logistic_regression": Pipeline(
            [
                ("impute", SimpleImputer(strategy="median")),
                ("scale", StandardScaler()),
                (
                    "classifier",
                    LogisticRegression(
                        C=1.0,
                        max_iter=3000,
                        class_weight="balanced",
                        random_state=SEED,
                    ),
                ),
            ]
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=200,
            min_samples_leaf=2,
            class_weight="balanced_subsample",
            n_jobs=-1,
            random_state=SEED,
        ),
        "linear_svm": Pipeline(
            [
                ("impute", SimpleImputer(strategy="median")),
                ("scale", StandardScaler()),
                (
                    "classifier",
                    CalibratedClassifierCV(
                        LinearSVC(C=0.5, class_weight="balanced", random_state=SEED, max_iter=10_000),
                        cv=3,
                    ),
                ),
            ]
        ),
        "hist_gradient_boosting": HistGradientBoostingClassifier(
            max_iter=300,
            learning_rate=0.08,
            max_leaf_nodes=31,
            l2_regularization=1.0,
            early_stopping=True,
            validation_fraction=0.1,
            random_state=SEED,
        ),
    }


def group_split(groups: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    outer = GroupShuffleSplit(n_splits=1, test_size=0.15, random_state=SEED)
    train_val_idx, test_idx = next(outer.split(np.zeros(len(groups)), y, groups))
    inner = GroupShuffleSplit(n_splits=1, test_size=0.15 / 0.85, random_state=SEED)
    train_rel, val_rel = next(
        inner.split(np.zeros(len(train_val_idx)), y[train_val_idx], groups[train_val_idx])
    )
    train_idx = train_val_idx[train_rel]
    val_idx = train_val_idx[val_rel]
    return train_idx, val_idx, test_idx


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--output", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--max-rows",
        type=int,
        default=0,
        help="Optional deterministic row limit for a smoke test (0 = all rows).",
    )
    args = parser.parse_args()

    if not args.data.exists():
        raise SystemExit(f"Dataset not found: {args.data}\nRun ml/download_datasets.py first.")

    print(f"Loading {args.data}")
    frame = pd.read_csv(args.data)
    if args.max_rows:
        frame = frame.iloc[: args.max_rows].copy()
    print(f"Rows: {len(frame):,}  columns: {len(frame.columns)}")

    started = time.perf_counter()
    matrices, groups, y, extraction, numeric_columns = build_features(frame)
    print(
        f"Extracted static features in {time.perf_counter() - started:.1f}s; "
        f"kept {len(y):,}/{len(frame):,} rows; rejected {extraction['rejected_rows']}"
    )

    train_idx, val_idx, test_idx = group_split(groups, y)
    train_groups = set(groups[train_idx])
    val_groups = set(groups[val_idx])
    test_groups = set(groups[test_idx])
    if train_groups & test_groups or train_groups & val_groups or val_groups & test_groups:
        raise RuntimeError("Group split leaked a domain across partitions.")

    print(
        f"Split (grouped by domain): train {len(train_idx):,} / "
        f"val {len(val_idx):,} / test {len(test_idx):,}"
    )

    tier_columns = {
        "dataset_url_only": DATASET_URL_ONLY,
        "threatlens_static": THREATLENS_STATIC,
        "all_numeric_upper_bound": numeric_columns,
    }
    tier_notes = {
        "dataset_url_only": "18 numeric PhiUSIIL columns computable from the URL string alone.",
        "threatlens_static": (
            "Deployable: backend URL extractor only, no network fetch. The best model in this tier "
            "is saved as the runtime artifact."
        ),
        "all_numeric_upper_bound": (
            "Every numeric dataset column, including page-derived fields and the leaky "
            "URLSimilarityIndex/TLDLegitimateProb/URLCharProb scores. Upper bound, never deployed."
        ),
    }

    results: dict[str, list[dict]] = {}
    fitted: dict[tuple[str, str], object] = {}
    for tier, matrix in matrices.items():
        if matrix.size == 0:
            raise RuntimeError(f"Tier {tier} produced no usable rows.")
        results[tier] = []
        for model_name in build_models():
            print(f"\nTraining {tier} / {model_name} ...")
            model = build_models()[model_name]
            begin = time.perf_counter()
            model.fit(matrix[train_idx], y[train_idx])
            fit_seconds = time.perf_counter() - begin
            val_prob = model.predict_proba(matrix[val_idx])
            test_prob = model.predict_proba(matrix[test_idx])
            val_pred = val_prob.argmax(axis=1)
            test_pred = test_prob.argmax(axis=1)
            entry = {
                "tier": tier,
                "model": model_name,
                "n_features": int(matrix.shape[1]),
                "fit_seconds": round(fit_seconds, 2),
                "validation": evaluation_metrics(y[val_idx], val_pred, val_prob, LABELS, positive_index=1),
                "test": evaluation_metrics(y[test_idx], test_pred, test_prob, LABELS, positive_index=1),
            }
            results[tier].append(entry)
            fitted[(tier, model_name)] = model
            print(
                f"  val F1 {entry['validation']['f1_macro']:.4f} / AUC "
                f"{entry['validation'].get('roc_auc')} | test F1 {entry['test']['f1_macro']:.4f} "
                f"/ AUC {entry['test'].get('roc_auc')} ({fit_seconds:.1f}s)"
            )
            if args.max_rows:
                break

    best_entry = max(
        results["threatlens_static"],
        key=lambda item: (item["validation"]["f1_macro"], item["validation"].get("roc_auc") or 0),
    )
    best_name = best_entry["model"]
    print(f"\nSelected deployable model on validation macro-F1: {best_name}")

    # Refit the chosen deployable model on train + validation. The test split
    # remains untouched and is used once for the saved artifact metrics.
    combined_idx = np.concatenate([train_idx, val_idx])
    final_model = build_models()[best_name]
    begin = time.perf_counter()
    final_model.fit(matrices["threatlens_static"][combined_idx], y[combined_idx])
    final_fit_seconds = time.perf_counter() - begin
    final_prob = final_model.predict_proba(matrices["threatlens_static"][test_idx])
    final_pred = final_prob.argmax(axis=1)
    final_metrics = evaluation_metrics(
        y[test_idx], final_pred, final_prob, LABELS, positive_index=1
    )

    metadata = {
        "name": "ThreatLens static URL classifier",
        "task": "url_binary",
        "algorithm": best_name,
        "trained_at": utcnow(),
        "dataset": "PhiUSIIL Phishing URL Dataset",
        "dataset_publisher": "UCI Machine Learning Repository, dataset 967",
        "dataset_url": "https://archive.ics.uci.edu/dataset/967/phiusiil+phishing+url+dataset",
        "dataset_license": "CC BY 4.0",
        "dataset_fingerprint": dataset_fingerprint(args.data),
        "feature_tier": "threatlens_static",
        "feature_names": THREATLENS_STATIC,
        "excluded_features": LEAKY_OR_PAGE_DERIVED,
        "label_mapping": {"0": "phishing", "1": "legitimate (dataset)", "target": "1 = phishing"},
        "preprocessing": (
            "Median imputation and standard scaling for linear models; raw values for tree "
            "models. Splits are grouped by registrable domain."
        ),
        "split": "70% train / 15% validation / 15% test, grouped by domain, seed 42",
        "selection_metric": "validation macro-F1",
        "calibrated": False,
        "environment": environment(),
        "source_script": "ml/train_url_models.py",
        "notes": (
            "Only URL-string features are used at runtime, so the model can score a link "
            "before any network request. PhiUSIIL was collected before 2024 and its legitimate "
            "class comes from a seed of popular sites; probabilities are uncalibrated."
        ),
        "metrics": final_metrics,
    }
    size = save_artifact(
        args.output,
        model=final_model,
        feature_names=THREATLENS_STATIC,
        metadata=metadata,
        metrics=final_metrics,
    )
    print(f"Saved {args.output} ({size / 1_000_000:.1f} MB)")

    report = {
        "generated_at": utcnow(),
        "dataset": metadata["dataset"],
        "dataset_license": metadata["dataset_license"],
        "dataset_fingerprint": metadata["dataset_fingerprint"],
        "dataset_rows_read": int(len(frame)),
        "dataset_rows_used": int(len(y)),
        "rejected_invalid_urls": extraction["rejected_rows"],
        "rejected_examples": extraction["rejected_examples"],
        "duplicate_urls_in_source": int(frame["URL"].duplicated().sum()),
        "duplicate_domains_in_source": int(frame["Domain"].duplicated().sum()),
        "domains_with_conflicting_labels": int(frame.groupby("Domain")["label"].nunique().gt(1).sum()),
        "label_counts": {
            "legitimate_original_1": int((frame["label"] == 1).sum()),
            "phishing_original_0": int((frame["label"] == 0).sum()),
        },
        "feature_tiers": {
            tier: {"n_features": int(matrices[tier].shape[1]), "columns": tier_columns[tier], "note": tier_notes[tier]}
            for tier in matrices
        },
        "split": {
            "method": "GroupShuffleSplit on registrable domain",
            "seed": SEED,
            "train": int(len(train_idx)),
            "validation": int(len(val_idx)),
            "test": int(len(test_idx)),
            "train_domains": len(train_groups),
            "validation_domains": len(val_groups),
            "test_domains": len(test_groups),
        },
        "environment": environment(),
        "tiers": {
            tier: sorted(entries, key=lambda item: item["validation"]["f1_macro"], reverse=True)
            for tier, entries in results.items()
        },
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
