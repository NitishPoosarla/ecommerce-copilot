"""Shared database connection for the copilot (same pattern as scripts/etl.py).

Two gotchas we already learned in Phase 2:
1. SQLAlchemy 2.x defaults to psycopg3, which isn't installed -> we rewrite
   the URL to `postgresql+psycopg2://`.
2. Timescale requires SSL -> force `sslmode=require`.
"""

import os
from pathlib import Path

from sqlalchemy import create_engine

ROOT = Path(__file__).resolve().parent.parent


def load_env_file(path: Path) -> None:
    """Minimal .env reader (no python-dotenv dependency)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def get_engine():
    load_env_file(ROOT / ".env")
    url = os.environ["DATABASE_URL"]
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    if "sslmode=" not in url:
        url += ("&" if "?" in url else "?") + "sslmode=require"
    return create_engine(url)
