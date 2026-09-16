"""Motifs for one COG."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..db import db, rows
from ..pwm import parse_pwm

router = APIRouter()

# ---------------------------------------------------------------- cog / motifs
@router.get("/api/cog/{cog_id}/motifs")
def cog_motifs(cog_id: int):
    c = db()
    cog = c.execute(
        """SELECT c.*, tf.name AS dominant_tf_family
           FROM cog c LEFT JOIN tf_family tf ON tf.tf_family_id = c.dominant_tf_family_id
           WHERE c.cog_id = ?""", (cog_id,)).fetchone()
    if not cog:
        c.close()
        raise HTTPException(404, f"cog {cog_id} not found")
    # every motif row uses the same MEME settings, so quality order is the E-value
    motifs = rows(c.execute(
        """SELECT m.motif_pk, m.motif_id, m.motif_number, m.evalue,
                  m.width, m.consensus, m.motif_regex, m.n_seqs_with_motif,
                  m.total_seqs_in_cog, m.frac_seqs_with_motif, m.is_showcase, m.pwm
           FROM motif m
           WHERE m.cog_id = ?
           ORDER BY m.is_showcase DESC, m.evalue ASC""", (cog_id,)))
    for m in motifs:
        m["pwm_parsed"] = parse_pwm(m.pop("pwm"))
    mibig = rows(c.execute("SELECT * FROM mibig_xref WHERE cog_id = ?", (cog_id,)))
    c.close()
    return {"cog": dict(cog), "motifs": motifs, "mibig": mibig}
