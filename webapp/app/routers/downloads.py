"""The download manifest: the Zenodo record, rendered from manifest.tsv. Nothing
   is generated at request time; per-file links are withheld until
   BGC_TFBS_DOWNLOADS_LIVE is set, because they 404 while the record is private.
"""
from __future__ import annotations

import csv
import functools
import os

from fastapi import APIRouter

from ..config import (ARCHIVE_CONTACT, DOWNLOADS_LIVE, MANIFEST_PATH, ZENODO_DOI,
                      ZENODO_DOI_URL, ZENODO_RECORD, ZENODO_RECORD_URL)

router = APIRouter()

# the three folders of the record, in display order
GROUPS = [
    ("global", "Global results",
     "Motifs, binding sites and TF-motif pairings across all families, at each "
     "of the six MEME settings; the showcase set the site presents is "
     "all_showcase_motifs.meme."),
    ("TFs", "TF annotations",
     "ENTRAF annotations for every gene, and the regulator protein sequences."),
    ("ssn", "Sequence-similarity networks",
     "One package per TF family (nodes, clusters, motif clusters) and the "
     "PRODORIC reference matrices and sequences they were compared against."),
]


def human_size(n: int) -> str:
    for unit in ("B", "kB", "MB", "GB", "TB"):
        if n < 1000 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1000
    return f"{n:.1f} TB"


def file_url(basename: str) -> str:
    return f"{ZENODO_RECORD_URL}/files/{basename}?download=1"


@functools.lru_cache(maxsize=1)
def _manifest() -> list[dict]:
    if not os.path.exists(MANIFEST_PATH):
        return []
    with open(MANIFEST_PATH, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh, delimiter="\t"))
    out = []
    for r in rows:
        # a malformed row must not take /api/meta down with it: skip it, never raise
        path = (r.get("path") or "").strip()
        size_txt = (r.get("size_bytes") or "").strip()
        if not path or not size_txt.isdigit():
            continue
        size = int(size_txt)
        out.append({"path": path, "name": os.path.basename(path),
                    "folder": path.split("/")[0] if "/" in path else "",
                    "size_bytes": size, "size": human_size(size),
                    "md5": (r.get("md5") or "").strip()})
    return out


def archive_manifest() -> dict:
    files = _manifest()
    link = (lambda f: file_url(f["name"])) if DOWNLOADS_LIVE else (lambda f: None)
    groups = []
    for key, title, blurb in GROUPS:
        members = [{**f, "url": link(f)} for f in files if f["folder"] == key]
        if members:
            groups.append({"key": key, "title": title, "blurb": blurb,
                           "n_files": len(members),
                           "total_bytes": sum(f["size_bytes"] for f in members),
                           "files": members})
    readme = next(({**f, "url": link(f)} for f in files
                   if f["folder"] == "" and f["name"].lower() == "readme.md"), None)
    return {
        "live": DOWNLOADS_LIVE,
        "doi": ZENODO_DOI, "doi_url": ZENODO_DOI_URL,
        "record": ZENODO_RECORD, "record_url": ZENODO_RECORD_URL,
        "contact": ARCHIVE_CONTACT,
        "n_files": len(files),
        "total_bytes": sum(f["size_bytes"] for f in files),
        "total_size": human_size(sum(f["size_bytes"] for f in files)),
        "readme": readme,
        "groups": groups,
    }


@router.get("/api/downloads")
def downloads():
    return archive_manifest()
