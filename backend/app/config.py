"""Central configuration, driven by environment variables."""
from __future__ import annotations

import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("INSIGHTFLOW_DATA_DIR", BASE_DIR / "data"))
UPLOAD_DIR = DATA_DIR / "uploads"
SAMPLE_DIR = BASE_DIR / "sample_data"
WAREHOUSE_PATH = DATA_DIR / "warehouse.duckdb"
METADATA_URL = os.getenv("INSIGHTFLOW_METADATA_URL", f"sqlite:///{DATA_DIR / 'metadata.db'}")
FRONTEND_DIST = Path(os.getenv("INSIGHTFLOW_FRONTEND_DIST", BASE_DIR.parent / "frontend" / "dist"))

_secret_file = DATA_DIR / ".secret_key"


def _load_secret() -> str:
    env = os.getenv("INSIGHTFLOW_SECRET_KEY")
    if env:
        return env
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if _secret_file.exists():
        return _secret_file.read_text().strip()
    key = secrets.token_hex(32)
    _secret_file.write_text(key)
    return key


SECRET_KEY = _load_secret()
TOKEN_TTL_HOURS = int(os.getenv("INSIGHTFLOW_TOKEN_TTL_HOURS", "24"))
MAX_UPLOAD_MB = int(os.getenv("INSIGHTFLOW_MAX_UPLOAD_MB", "200"))
SEED_DEMO = os.getenv("INSIGHTFLOW_SEED_DEMO", "true").lower() in {"1", "true", "yes"}
SCHEDULER_ENABLED = os.getenv("INSIGHTFLOW_SCHEDULER", "true").lower() in {"1", "true", "yes"}
CORS_ORIGINS = [o.strip() for o in os.getenv("INSIGHTFLOW_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()]

# Generative AI via Sarvam AI (optional). Without SARVAM_API_KEY the platform uses
# its built-in statistical/rule-based engine for every feature.
AI_MODEL = os.getenv("INSIGHTFLOW_AI_MODEL", "sarvam-105b")
AI_DISABLED = os.getenv("INSIGHTFLOW_AI_DISABLED", "false").lower() in {"1", "true", "yes"}

for d in (DATA_DIR, UPLOAD_DIR):
    d.mkdir(parents=True, exist_ok=True)
