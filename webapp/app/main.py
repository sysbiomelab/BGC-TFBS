#!/usr/bin/env python3
"""
BGC-TFBS website: FastAPI backend, read-only over the SQLite file built by
database/build_website_db.py. This module only wires routers and static files.
Run: WEBSITE_DB=/path/to/website.db uvicorn --app-dir webapp app.main:app
"""
from __future__ import annotations

import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .caches import taxon_families
from .config import STATIC_DIR
from .routers import (cog, downloads, families, family, meta, prodoric, search, tf)


@asynccontextmanager
async def lifespan(_app):
    """Warm taxon_families() on a daemon thread so neither startup nor Ctrl-C is blocked."""
    threading.Thread(target=taxon_families, name="warm-taxon-map", daemon=True).start()
    yield


app = FastAPI(title="BGC-TFBS", docs_url="/api/docs", openapi_url="/api/openapi.json",
              lifespan=lifespan)

# Include order is match order: keep the specific ahead of the general so a new
# route cannot shadow one (/api/prodoric/validation must precede /api/prodoric/{mx_acc}).
for r in (meta, search, families, family, cog, tf, prodoric, downloads):
    app.include_router(r.router)

# ---------------------------------------------------------------- static
NO_CACHE = "no-cache"          # "cache it, but revalidate before reusing it"


class RevalidatingStatic(StaticFiles):
    """Serve assets with Cache-Control: no-cache. There is no build step and no
       content hash in any filename, so browsers must revalidate (an unchanged
       file costs an empty 304). If names are ever content-hashed, use immutable."""

    def file_response(self, *args, **kwargs):
        resp = super().file_response(*args, **kwargs)
        resp.headers.setdefault("Cache-Control", NO_CACHE)
        return resp


app.mount("/static", RevalidatingStatic(directory=STATIC_DIR), name="static")


@app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
def index():
    # the shell names every script, so it must never be a stale copy either
    return FileResponse(os.path.join(STATIC_DIR, "index.html"),
                        headers={"Cache-Control": NO_CACHE})
