"""Disposable local config for the embedded Superset demo."""

from __future__ import annotations

import os
from pathlib import Path

from flask_caching.backends.filesystemcache import FileSystemCache


STATE_DIR = Path(
    os.environ.get(
        "DEVIN_DEMO_STATE_DIR",
        Path(__file__).resolve().parents[2] / ".state" / "superset",
    )
)
STATE_DIR.mkdir(parents=True, exist_ok=True)

SECRET_KEY = "devin-demo-local-secret"
GUEST_TOKEN_JWT_SECRET = "devin-demo-local-guest-token-secret"
SQLALCHEMY_DATABASE_URI = f"sqlite:///{STATE_DIR / 'superset.db'}"
SQLALCHEMY_EXAMPLES_URI = f"sqlite:///{STATE_DIR / 'examples.db'}"

FEATURE_FLAGS = {"EMBEDDED_SUPERSET": True}
TALISMAN_ENABLED = False
PUBLIC_ROLE_LIKE = "Gamma"

CACHE_CONFIG = {
    "CACHE_TYPE": "SimpleCache",
    "CACHE_DEFAULT_TIMEOUT": 300,
    "CACHE_KEY_PREFIX": "devin_demo_",
}
DATA_CACHE_CONFIG = CACHE_CONFIG
THUMBNAIL_CACHE_CONFIG = CACHE_CONFIG
RESULTS_BACKEND = FileSystemCache(str(STATE_DIR / "results"))
CELERY_CONFIG = None

