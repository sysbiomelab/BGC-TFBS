"""Paths and deployment settings — everything the app reads from the environment.

   Nothing here touches the database; import it freely.
"""
from __future__ import annotations

import os

# ROOT is the repository root; the database and the manifest live outside webapp/.
WEBAPP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(WEBAPP_DIR)
STATIC_DIR = os.path.join(WEBAPP_DIR, "static")

# WEBSITE_DB wins; otherwise the first of these that exists.
_DB_CANDIDATES = (
    os.path.join(ROOT, "data", "website.db"),
    os.path.join(ROOT, "output", "db", "website.db"),
)


def _resolve_db() -> str:
    env = os.environ.get("WEBSITE_DB")
    if env:
        return env
    for p in _DB_CANDIDATES:
        if os.path.exists(p):
            return p
    return _DB_CANDIDATES[0]          # report the documented path when missing


DB_PATH = _resolve_db()

# The published dataset is one Zenodo record; webapp/manifest.tsv lists its
# files (path, size_bytes, md5). Per-file links are served only when
# BGC_TFBS_DOWNLOADS_LIVE=1, because they 404 while the record is private.
ZENODO_RECORD = "22766286"
ZENODO_DOI = f"10.5281/zenodo.{ZENODO_RECORD}"
ZENODO_DOI_URL = f"https://doi.org/{ZENODO_DOI}"
ZENODO_RECORD_URL = f"https://zenodo.org/records/{ZENODO_RECORD}"
MANIFEST_PATH = os.environ.get("BGC_TFBS_MANIFEST") or os.path.join(WEBAPP_DIR, "manifest.tsv")
DOWNLOADS_LIVE = os.environ.get("BGC_TFBS_DOWNLOADS_LIVE", "").lower() in ("1", "true", "yes")
ARCHIVE_CONTACT = os.environ.get("BGC_TFBS_CONTACT", "")

# A motif matches a PRODORIC site at Tomtom q <= Q_MATCH. The db's
# n_motifs_matched uses a looser cut, so the routers re-apply this threshold.
Q_MATCH = 0.1
