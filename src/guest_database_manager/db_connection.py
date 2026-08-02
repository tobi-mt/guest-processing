"""Shared SQLite connection policy for every application component."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


def connect_database(path: str | Path, **kwargs: Any) -> sqlite3.Connection:
    """Open SQLite with referential integrity and bounded lock waiting enabled."""
    kwargs.setdefault("timeout", 5.0)
    conn = sqlite3.connect(str(path), **kwargs)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn
