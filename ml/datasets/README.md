# Datasets

No dataset or model artifact is committed to this repository. The folder is
ignored by git.

`ml/download_datasets.py` downloads the three public corpora used for the
reproducible benchmarks:

| Key | Dataset | Source | Licence |
| --- | --- | --- | --- |
| `phiusiil` | PhiUSIIL Phishing URL Dataset | [UCI dataset 967](https://archive.ics.uci.edu/dataset/967/phiusiil+phishing+url+dataset) | CC BY 4.0 |
| `email` | Phishing Email Detection Dataset (2025), merged corpus | [Zenodo 17314806](https://zenodo.org/records/17314806) | CC BY 4.0 |
| `sms` | SMS Phishing Dataset for Machine Learning and Pattern Recognition | [Mendeley 10.17632/f45bkkt8pr.1](https://data.mendeley.com/datasets/f45bkkt8pr/1) | CC BY 4.0 |

```powershell
.\.venv\Scripts\python.exe ml\download_datasets.py
.\.venv\Scripts\python.exe ml\download_datasets.py --only phiusiil --force
```

Files are streamed to `ml/datasets/raw/`. The script writes
`ml/datasets/raw/manifest.json` with the URL, byte size and SHA-256 of every
download and extracts archives with a path-traversal check.

## Layout

```
ml/datasets/raw/
  manifest.json
  phishing_email_merged.csv               # ~391 MB
  phiusiil/PhiUSIIL_Phishing_URL_Dataset.csv
  sms/Dataset_5971.csv
```

## Label semantics

- **PhiUSIIL**: `label` 1 = legitimate, 0 = phishing. The training script maps
  the target to 1 = phishing.
- **Email merged**: `label` 1 = phishing (the authors group spam and scam into
  this class), 0 = safe. 772 rows have no label and are dropped.
- **SMS**: `ham`, `spam`, `smishing` (case variants are preserved in metadata
  and normalised for training). All three classes are retained.

## Before using your own data

1. Confirm you are allowed to use and, if applicable, redistribute it.
2. Check that labels describe the phenomenon you want to detect, not just one
   vendor's blocklist.
3. Consider age, geography and campaign concentration.
4. Record the source and licence in the training metadata.

Read [`../README.md`](../README.md) for the training commands, evaluation
method and limitations.
