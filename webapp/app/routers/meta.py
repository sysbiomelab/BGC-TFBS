"""Site-wide counts and build provenance."""
from __future__ import annotations

from fastapi import APIRouter

from ..caches import site_counts
from ..db import db
from .downloads import archive_manifest

router = APIRouter()

# ---------------------------------------------------------------- meta
# build_info also holds build-machine paths; allow-list so a new key cannot
# leak by accident.
PUBLIC_BUILD_KEYS = ("built_at", "showcase_param", "ssn_families")

@router.get("/api/meta")
def meta():
    c = db()
    info = {r["key"]: r["value"] for r in c.execute("SELECT key, value FROM build_info")
            if r["key"] in PUBLIC_BUILD_KEYS}
    c.close()
    return {"build": info, "counts": site_counts(), "archive": archive_manifest()}
