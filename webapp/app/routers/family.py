"""One family: its COGs, class mix, and its BGCs a page at a time."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..db import db, rows

router = APIRouter()

# ---------------------------------------------------------------- family
@router.get("/api/family/{family_id}")
def family(family_id: str):
    c = db()
    fam = c.execute("SELECT * FROM family WHERE family_id = ?", (family_id,)).fetchone()
    if not fam:
        c.close()
        raise HTTPException(404, f"family {family_id} not found")
    cogs = rows(c.execute(
        """SELECT c.cog_id, c.cog_name, c.n_seqs, c.conservation_rank, c.has_meme,
                  c.pct_tf, tf.name AS dominant_tf_family, c.dominant_tf_best_evalue,
                  (SELECT COUNT(*) FROM motif m
                    WHERE m.cog_id = c.cog_id AND m.is_showcase = 1) AS has_showcase
           FROM cog c LEFT JOIN tf_family tf ON tf.tf_family_id = c.dominant_tf_family_id
           WHERE c.family_id = ?
           ORDER BY c.conservation_rank NULLS LAST, c.cog_name""", (family_id,)))
    # color_rank is a display-only colour key that always has a value: the real
    # rank where there is one, then a deterministic continuation (the ORDER BY
    # above is stable). Never present it as a conservation rank.
    top = max((x["conservation_rank"] for x in cogs
               if x["conservation_rank"] is not None), default=0)
    spare = 0
    for x in cogs:
        if x["conservation_rank"] is None:
            spare += 1
            x["color_rank"] = top + spare
        else:
            x["color_rank"] = x["conservation_rank"]

    # MIBiG reference clusters in this family (a bgc_name range, so the index can serve it)
    mibig_bgcs = rows(c.execute(
        """SELECT b.bgc_name, b.length_nt, b.n_cds, bc.class, t.species
           FROM bgc b
           LEFT JOIN bgc_class bc ON bc.class_id = b.class_id
           LEFT JOIN taxon t ON t.taxon_id = b.taxon_id
          WHERE b.family_id = ? AND b.bgc_name >= 'BGC' AND b.bgc_name < 'BGD'
          ORDER BY b.bgc_name""", (family_id,)))
    for b in mibig_bgcs:
        # the stored version suffix is stale; the bare accession is the durable identifier
        b["accession"] = b["bgc_name"].split(".")[0]

    classes = rows(c.execute(
        """SELECT bc.class, COUNT(*) AS n FROM bgc b
           JOIN bgc_class bc ON bc.class_id = b.class_id
           WHERE b.family_id = ? GROUP BY bc.class ORDER BY n DESC LIMIT 6""",
        (family_id,)))
    c.close()
    return {"family": dict(fam), "cogs": cogs, "class_breakdown": classes,
            "mibig": {"bgcs": mibig_bgcs}}

@router.get("/api/family/{family_id}/bgcs")
def family_bgcs(family_id: str,
                offset: int = Query(0, ge=0, le=200000),
                limit: int = Query(20, ge=1, le=100)):
    c = db()
    bgcs = rows(c.execute(
        """SELECT b.bgc_id, b.bgc_name, b.length_nt, b.n_cds, b.bgc_type,
                  b.on_contig_edge, t.species, t.genus, b.organism,
                  bc.class, bc.subclass, b.products
           FROM bgc b
           LEFT JOIN taxon t USING(taxon_id)
           LEFT JOIN bgc_class bc ON bc.class_id = b.class_id
           WHERE b.family_id = ?
           -- characterised clusters first; the largest families page thousands of BGCs
           ORDER BY (b.bgc_type = 'mibig') DESC, b.n_cds DESC, b.bgc_id
           LIMIT ? OFFSET ?""", (family_id, limit, offset)))
    if bgcs:
        ids = [b["bgc_id"] for b in bgcs]
        ph = ",".join("?" * len(ids))
        cds = rows(c.execute(
            f"""SELECT s.bgc_id, s.cds_id, s.gene_key, s.locus_tag, s.protein_id,
                       p.name AS product, s.nt_start, s.nt_end, s.strand,
                       s.cog_id, s.cog_is_propagated, tf.name AS tf_family, s.tf_evalue
                FROM cds s
                LEFT JOIN product p ON p.product_id = s.product_id
                LEFT JOIN tf_family tf ON tf.tf_family_id = s.tf_family_id
                WHERE s.bgc_id IN ({ph})
                ORDER BY s.bgc_id, s.nt_start""", ids))
        by_bgc: dict[str, list] = {}
        for r in cds:
            by_bgc.setdefault(r["bgc_id"], []).append(r)
        for b in bgcs:
            b["cds"] = by_bgc.get(b["bgc_id"], [])
    total = c.execute("SELECT COUNT(*) FROM bgc WHERE family_id = ?",
                      (family_id,)).fetchone()[0]
    c.close()
    return {"total": total, "offset": offset, "bgcs": bgcs}
