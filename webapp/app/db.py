"""Read-only SQLite access. The db is opened `mode=ro`; never write to it."""
from __future__ import annotations

import sqlite3

from .config import DB_PATH

def db() -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn

def like_esc(s: str) -> str:
    """Neutralise LIKE wildcards -- locus tags are full of underscores."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

def rows(cur) -> list[dict]:
    return [dict(r) for r in cur.fetchall()]

# one past every string starting with the prefix, so a range comparison stands
# in for LIKE 'x%'. LIKE cannot use ix_bgc_name (BINARY index, case_sensitive_like
# off) and full-scans bgc; the range is an index seek.
HI_CHAR = "\uffff"
