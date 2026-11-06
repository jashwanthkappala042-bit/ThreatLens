"""WSGI entry point for gunicorn and other production servers.

Run locally with ``run.py``; on Render use:

    gunicorn --workers 1 --threads 4 --timeout 120 --bind 0.0.0.0:$PORT wsgi:app

A single worker is deliberate: the rate limiter is in-process and each extra
worker would load its own copy of the ML models.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

try:
    from dotenv import load_dotenv  # type: ignore

    # Local convenience only. On a host, configure real environment variables.
    load_dotenv(PROJECT_ROOT / ".env")
except Exception:
    pass

from app import create_app  # noqa: E402

app = create_app()

if __name__ == "__main__":  # pragma: no cover - convenience for manual runs
    app.run(
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "5000")),
        debug=False,
    )
