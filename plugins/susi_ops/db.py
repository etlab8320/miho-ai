"""Database and JSON helpers for the 수시 calculation plugin."""

from __future__ import annotations

import json
import os
import pathlib
import sqlite3
from typing import Any


DEFAULT_DB = pathlib.Path(
    "/Users/etlab/.miho/discord/guilds/1507988396235296778/channels/10___1508422955460198420/threads/thread__1513557600497565696/work/susi27_pipeline/susi27_staging.sqlite3"
)


def db_path() -> pathlib.Path:
    return pathlib.Path(os.getenv("MIHO_SUSI27_STAGING_DB", str(DEFAULT_DB))).expanduser()


def _connect() -> sqlite3.Connection:
    path = db_path()
    if not path.exists():
        raise FileNotFoundError(f"수시27 staging DB가 아직 없어: {path}")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _like(value: str | None) -> str:
    return f"%{value or ''}%"


def _json_loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default
