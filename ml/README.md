# Optional machine-learning models

ThreatLens includes three pre-trained machine-learning models:
URL, email, and SMS. These models are included in the repository
so users can run detection without training them again.

Training datasets are not included. Users can download them using
`ml/download_datasets.py` if they want to reproduce the benchmarks.

The backend lazily loads local artifacts when the configured path exists:

| Environment variable | Default                        | Task                            |
| -------------------- | ------------------------------ | ------------------------------- |
| `URL_MODEL_PATH`     | `ml/models/url_model.joblib`   | Static-feature URL classifier   |
| `EMAIL_MODEL_PATH`   | `ml/models/email_model.joblib` | Binary email/message classifier |
| `SMS_MODEL_PATH`     | `ml/models/sms_model.joblib`   | Three-class SMS classifier      |

If an artifact is missing, the scan reports the ML stage as **unavailable**. It
never substitutes a fake score.

---

## Datasets

All three datasets are public and licensed **CC BY 4.0**. They are downloaded by
`ml/download_datasets.py`, which streams each file and records its size and
SHA-256 in `ml/datasets/raw/manifest.json`.

| Key        | Dataset                                                           | Source                                                                                                  | Label semantics                                               |
| ---------- | ----------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------- |
| `phiusiil` | PhiUSIIL Phishing URL Dataset                                     | [UCI ML Repository, dataset 967](https://archive.ics.uci.edu/dataset/967/phiusiil+phishing+url+dataset) | `label` 1 = legitimate, 0 = phishing (mapped to 1 = phishing) |
| `email`    | Phishing Email Detection Dataset (2025), merged corpus            | [Zenodo 17314806](https://zenodo.org/records/17314806), DOI 10.5281/zenodo.17314806                     | 1 = phishing (spam/scam folded in by the authors), 0 = safe   |
| `sms`      | SMS Phishing Dataset for Machine Learning and Pattern Recognition | [Mendeley 10.17632/f45bkkt8pr.1](https://data.mendeley.com/datasets/f45bkkt8pr/1)                       | `ham`, `spam`, `smishing` (all retained)                      |

```powershell
.\.venv\Scripts\python.exe ml\download_datasets.py
.\.venv\Scripts\python.exe ml\download_datasets.py --only phiusiil --force
```

See [`datasets/README.md`](datasets/README.md) for the raw layout and label
notes.

---

## Reproducing the benchmarks

```powershell
# URL: three feature tiers x four algorithms, grouped by registrable domain
.\.venv\Scripts\python.exe ml\train_url_models.py

# Email: chunked streaming, deduplicated, four text pipelines
.\.venv\Scripts\python.exe ml\train_email_models.py

# SMS: three-class comparison, four text pipelines
.\.venv\Scripts\python.exe ml\train_sms_models.py
```

Each script:

1. refuses to run if the dataset file is absent (run the downloader first);
2. writes a `*_comparison.json` report containing every model, every metric,
   split sizes, environment versions and the dataset fingerprint;
3. selects the best model by **validation macro-F1 only**;
4. refits that model on train + validation and evaluates it **once** on the
   untouched test split;
5. saves `ml/models/<task>_model.joblib`.

A quick smoke test is available without touching the saved artifact:

```powershell
.\.venv\Scripts\python.exe ml\train_url_models.py --max-rows 5000 `
  --output ml\models\_smoke_url.joblib --report ml\reports\_smoke_url.json
```

The email script also accepts `--max-rows` and `--only <model>`.

---

## URL benchmark (`ml/train_url_models.py`)

PhiUSIIL has 235,795 rows and 56 columns. Several columns are unusable for a
scanner that must score a link **before fetching it**, and some are effectively
label leakage:

- `URLSimilarityIndex` is `100` for every legitimate row in this corpus.
- `TLDLegitimateProb`, `URLCharProb` and `CharContinuationRate` are derived
  statistics that encode the dataset's own label distribution.
- Title, favicon, redirect, iframe, social-network, copyright, form and HTML
  structure fields require a page fetch.

Three tiers are reported separately so that a benchmark number is never confused
with what the deployed scanner can do:

| Tier                      | Features                                                 | Deployable?                  |
| ------------------------- | -------------------------------------------------------- | ---------------------------- |
| `dataset_url_only`        | 18 numeric PhiUSIIL columns computed from the URL string | No — dataset-specific schema |
| `threatlens_static`       | 26 features from `backend/app/detection/url_features.py` | **Yes** — this is what ships |
| `all_numeric_upper_bound` | every numeric column, including leaky/page-derived ones  | No — upper bound only        |

Rows are split 70/15/15 with `GroupShuffleSplit` on the **registrable domain**.
The source contains 15,709 duplicate domains and 54 domains with conflicting
labels; splitting by row would let the same site appear in train and test and
inflate the measured accuracy. The script asserts that no domain crosses
partitions.

Algorithms compared in every tier: logistic regression, random forest,
calibrated linear SVM and histogram gradient boosting.

> Results are filled in from `ml/reports/url_comparison.json` after the full run.

---

## Email benchmark (`ml/train_email_models.py`)

The merged corpus has 213,189 rows and two columns, `body` and `label`
(0 = safe, 1 = phishing). It arrives lower-cased and punctuation-tokenised, for
example `http : / / example . com`. Runtime text from ThreatLens is ordinary
prose and may contain HTML, so both paths share
`backend/app/detection/text_normalizer.py`:

1. decode entities and drop markup/script/style content without executing it;
2. NFKC-normalise and lower-case;
3. put spaces around punctuation (the corpus convention);
4. collapse whitespace and truncate (4,000 chars for word models, 1,500 for the
   character model).

That transformer is embedded as the first step of every saved pipeline, so live
input is preprocessed identically to training data.

Duplicates are removed by SHA-1 of the normalised text; duplicate groups with
conflicting labels are dropped instead of guessed. Splits are stratified
70/15/15, and exact duplicates never cross splits.

Algorithms compared: word TF-IDF (1–2 grams) + logistic regression, word TF-IDF

- calibrated linear SVM, character TF-IDF (2–4 grams) + logistic regression, and
  word TF-IDF + complement naive Bayes.

> Results are filled in from `ml/reports/email_comparison.json` after the full run.

---

## SMS benchmark (`ml/train_sms_models.py`)

The corpus has 5,971 rows; after removing 24 duplicate texts and 2 ambiguous
duplicate groups, **5,947** messages remain: 4,834 `ham`, 487 `spam`, 626
`smishing`. All three original classes are preserved. Splits are stratified
70/15/15 (4,162 / 892 / 893).

Selection is by validation macro-F1. Results on the untouched test split:

| Model                                              | Val macro-F1 | Test macro-F1 | Test accuracy | Test AUC (OVR) |
| -------------------------------------------------- | ------------ | ------------- | ------------- | -------------- |
| **word TF-IDF + calibrated linear SVM** (selected) | **0.8639**   | 0.8837        | 0.9653        | 0.9883         |
| char TF-IDF + logistic regression                  | 0.8619       | **0.8927**    | **0.9675**    | 0.9828         |
| word TF-IDF + logistic regression                  | 0.8556       | 0.8861        | 0.9653        | 0.9791         |
| word TF-IDF + complement naive Bayes               | 0.8348       | 0.8838        | 0.9642        | 0.9703         |

The selected model was refitted on train + validation. Its test per-class scores:

| Class    | Precision | Recall | F1     | Support |
| -------- | --------- | ------ | ------ | ------- |
| ham      | 0.9931    | 0.9972 | 0.9952 | 726     |
| spam     | 0.8485    | 0.7671 | 0.8058 | 73      |
| smishing | 0.8776    | 0.9149 | 0.8958 | 94      |

Confusion matrix (rows = truth, columns = prediction):

```
[[724,   2,   0],
 [  5,  56,  12],
 [  0,   8,  86]]
```

The character model scored marginally better on test but lost on validation, so
the selection rule kept the word SVM. This is deliberate: choosing on test
scores would make the reported test metrics optimistic.

---

## Artifact format

Every artifact is a joblib dictionary:

```python
{
    "model": <fitted scikit-learn estimator or pipeline>,
    "feature_names": [ ... ],          # URL models only
    "metadata": {
        "name", "task", "algorithm", "trained_at",
        "dataset", "dataset_url", "dataset_license",
        "dataset_fingerprint": {"path", "bytes", "sha256"},
        "preprocessing", "split", "selection_metric",
        "calibrated": False,
        "environment": {"python", "scikit_learn", "pandas", "numpy", "joblib"},
        "metrics": {...}
    },
    "metrics": {...}                   # held-out test metrics
}
```

`backend/app/detection/ml.py` validates presence, caches by file mtime, and
returns `available: false` with a reason for any problem. It never invents a
prediction.

### Runtime feature parity

- **URL** — the saved model uses exactly the 26 `feature_names` written by
  `extract_url_features()`. Booleans become 0/1, list-valued features become
  their length. No DNS, HTTP or page data is needed.
- **Email** — the pipeline begins with `MessageNormalizer`, so the scanner can
  pass raw subject + body.
- **SMS** — same pipeline shape with three classes. It is only used for
  body-only messages at or below `SMS_MAX_CHARS` (default 700). Messages with a
  subject use the binary email model, so a message is never scored twice.

### Short-message routing

`analyze_email()` chooses the model:

```
subject empty AND len(subject + body) <= SMS_MAX_CHARS  -> sms_model (ham/spam/smishing)
otherwise                                               -> email_model (legitimate/phishing)
```

If the chosen artifact is missing, the scanner falls back to the other text
model; if both are missing the stage reports `unavailable`.

---

## Using your own CSV

The simpler legacy scripts remain for user-supplied data:

```powershell
.\.venv\Scripts\python.exe ml\train_email_model.py --data ml\datasets\email_dataset.csv `
  --dataset-name "your corpus" --dataset-license "your licence"

.\.venv\Scripts\python.exe ml\train_url_model.py --data ml\datasets\url_dataset.csv `
  --dataset-name "your corpus" --dataset-license "your licence"
```

They expect `text,label` and `url,label` respectively and accept `phishing` /
`legitimate` spellings. Confirm you are allowed to use the data before training.

---

## Limitations

These numbers are **not** production detection rates.

- **One split, one corpus.** Each metric describes a single held-out split of a
  public dataset. Nothing here has been validated on live traffic from this
  instance.
- **Age.** PhiUSIIL was collected before 2024; the email corpora span 1998–2008
  (Ling, Enron, SpamAssassin, TREC 2005–2007, CEAS, Nazario_5, Nigerian_5); the
  SMS corpus predates 2022. Vocabulary, formatting, languages and campaigns have
  moved on.
- **Label definitions differ from the product.** The email dataset folds spam and
  scam into "phishing". A spam prediction is therefore not proof of fraud. The
  SMS model distinguishes spam from smishing but has only 487 spam and 626
  smishing training examples, so those per-class numbers are noisy.
- **Uncalibrated scores.** No model is probability-calibrated. The UI labels the
  score as uncalibrated and does not treat it as a probability of maliciousness.
- **Near-duplicates remain.** Exact duplicates are removed, but forwarded
  threads, templated campaigns and quoted replies can still cross splits and
  make results optimistic.
- **Domain grouping is approximate.** Registrable-domain grouping stops trivial
  leakage but not shared infrastructure, URL shorteners or copied campaigns
  across domains.
- **Feature drift.** The URL model sees only URL-string features. If attackers
  shift to patterns absent from the training years, recall will fall.
- **Artifacts are trusted files.** Only load joblib files you produced or trust;
  unpickling is code execution.
