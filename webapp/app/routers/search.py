"""The FTS-backed quick search. Its hit list is capped at 2000 rows with no rank
   ordering, so no count derived from it is exact.
"""
from __future__ import annotations

import re
import sqlite3

from fastapi import APIRouter, Query

from ..db import db, rows

router = APIRouter()

# ---------------------------------------------------------------- search
@router.get("/api/search")
def search(q: str = Query(min_length=1, max_length=200),
           limit: int = Query(25, ge=1, le=100)):
    c = db()
    out = {"families": [], "bgcs": []}
    qs = q.strip()

    if re.fullmatch(r"FAM\d+", qs, re.I):
        out["families"] = rows(c.execute(
            "SELECT family_id, n_bgcs, dominant_class, has_cog_data, has_motif_data "
            "FROM family WHERE family_id = ? COLLATE NOCASE", (qs.upper(),)))
    if re.fullmatch(r"(BGC)?\d+(\.\d+)?", qs, re.I):
        bid = qs[3:] if qs.upper().startswith("BGC") and qs[3:].isdigit() else qs
        out["bgcs"] = rows(c.execute(
            """SELECT b.bgc_id, b.bgc_name, b.family_id, t.species, b.length_nt, b.n_cds
               FROM bgc b LEFT JOIN taxon t USING(taxon_id)
               WHERE b.bgc_id = ? OR b.bgc_name = ? LIMIT ?""", (bid, qs, limit)))

    if not out["families"] and not out["bgcs"]:
        # bgc_fts covers species, organism, genus, name and products; the last token is a prefix
        tokens = re.findall(r"[\w.]+", qs)
        if tokens:
            match = " ".join(f'"{t}"' for t in tokens[:-1]) + f' "{tokens[-1]}"*'
            try:
                hits = rows(c.execute(
                    """SELECT f.bgc_id FROM bgc_fts f WHERE bgc_fts MATCH ?
                       LIMIT 2000""", (match.strip(),)))
            except sqlite3.OperationalError:
                hits = []
            if hits:
                ids = [h["bgc_id"] for h in hits]
                ph = ",".join("?" * min(len(ids), 2000))
                out["families"] = rows(c.execute(
                    f"""SELECT b.family_id, COUNT(*) AS n_matching_bgcs,
                               fam.n_bgcs, fam.dominant_class,
                               fam.has_cog_data, fam.has_motif_data
                        FROM bgc b JOIN family fam ON fam.family_id = b.family_id
                        WHERE b.bgc_id IN ({ph})
                        GROUP BY b.family_id
                        ORDER BY fam.has_motif_data DESC, n_matching_bgcs DESC
                        LIMIT ?""", (*ids, limit)))
                out["bgcs"] = rows(c.execute(
                    f"""SELECT b.bgc_id, b.bgc_name, b.family_id, t.species,
                               b.length_nt, b.n_cds
                        FROM bgc b LEFT JOIN taxon t USING(taxon_id)
                        WHERE b.bgc_id IN ({ph}) LIMIT ?""", (*ids, limit)))
    c.close()
    return out
