"""Browsing and filtering gene cluster families."""
from __future__ import annotations

import json
import re

from fastapi import APIRouter, HTTPException, Query

from ..caches import family_facets, mibig_families, taxon_families
from ..constants import CLASS_RE, TIER_SQL
from ..db import HI_CHAR, db, like_esc, rows

router = APIRouter()

TF_EXPR = """(SELECT tf.name FROM cog c2
          JOIN tf_family tf ON tf.tf_family_id = c2.dominant_tf_family_id
         WHERE c2.family_id = f.family_id
         GROUP BY c2.dominant_tf_family_id
         ORDER BY COUNT(*) DESC, tf.name LIMIT 1)"""

# every column the table can sort on, as a bare expression; direction is the caller's
FAM_ORDER = {
    # FAM100 sorts before FAM10 as text
    "id":      "CAST(SUBSTR(f.family_id, 4) AS INTEGER)",
    "bgcs":    "f.n_bgcs",
    "cds":     "f.total_cds",
    "class":   "f.dominant_class",
    "species": "f.n_species",
    "genera":  "f.n_genera",
    "motifs":  "f.n_cogs_meme",
    "tf":      TF_EXPR,
    "data":    "(f.has_motif_data * 4 + f.has_cog_data * 2 + f.has_tf_data)",
}
FAM_SORT_RE = "^(" + "|".join(FAM_ORDER) + ")$"
# counts read high-to-low, names and ids low-to-high
FAM_DIR = {"id": "ASC", "class": "ASC", "tf": "ASC"}

# Columns deliberately absent: kingdoms, mean_cds_per_bgc, n_cogs and
# dominant_subclass are always NULL; subgroup is an n_bgcs bucket, not taxonomy.
FAM_SELECT = """
SELECT f.family_id, f.n_bgcs, f.total_cds, f.dominant_class,
       f.n_kingdoms, f.n_phyla, f.n_genera, f.n_species, f.n_cogs_meme,
       f.has_tf_data, f.has_cog_data, f.has_motif_data,
       """ + TF_EXPR + """                                     AS dominant_tf,
       (SELECT MIN(m.evalue) FROM motif m
          JOIN cog c3 ON c3.cog_id = m.cog_id
         WHERE c3.family_id = f.family_id AND m.is_showcase = 1) AS best_evalue
  FROM family f
"""

BGC_PREFIX_CAP = 20000      # BGCs a single prefix may match before it is refused

def bgc_prefix_families(c, qs: str) -> set[str]:
    """Families holding a BGC whose name starts with `qs`; names are paths, so only a prefix match is usable."""
    hits = []
    for pfx in dict.fromkeys((qs, qs.upper())):        # accessions are upper-case
        n = c.execute("SELECT COUNT(*) FROM bgc WHERE bgc_name >= ? AND bgc_name < ?",
                      (pfx, pfx + HI_CHAR)).fetchone()[0]
        if n > BGC_PREFIX_CAP:
            raise HTTPException(422, f"{qs!r} matches {n:,} BGCs — type more of it")
        if n:
            hits += [r[0] for r in c.execute(
                "SELECT DISTINCT family_id FROM bgc WHERE bgc_name >= ? AND bgc_name < ?",
                (pfx, pfx + HI_CHAR))]
    return set(hits)

def families_matching(c, qs: str) -> set[str]:
    """The family ids a free-text query restricts to: a union, since a query can be both an accession and a name."""
    if re.fullmatch(r"FAM\d+", qs, re.I):
        return {qs.upper()}
    if qs.isdigit():                                   # the surrogate bgc_id
        return {r[0] for r in c.execute(
            "SELECT family_id FROM bgc WHERE bgc_id = ?", (qs,))}

    out = set()
    # accessions carry a digit and taxon names do not, so a name never pays for a prefix scan
    if len(qs) >= 3 and any(ch.isdigit() for ch in qs):
        out |= bgc_prefix_families(c, qs)

    # kingdom is deliberately not searched: "bacter" would select all of Bacteria
    p = like_esc(qs)
    tax = [r[0] for r in c.execute(
        """SELECT taxon_id FROM taxon
            WHERE genus   LIKE :p ESCAPE '\\'
               OR phylum  LIKE :p ESCAPE '\\'
               OR species LIKE :p ESCAPE '\\'
               OR species LIKE :w ESCAPE '\\'""",
        {"p": p + "%", "w": "% " + p + "%"})]
    if tax:
        by_taxon = taxon_families()
        out |= set().union(*(by_taxon.get(t, frozenset()) for t in tax))
    return out

@router.get("/api/families")
def families(
    q: str = Query("", max_length=100),
    tier: str = Query("motif", pattern="^(motif|cog|tf|all)$"),
    bgc_class: str | None = Query(None, alias="class", pattern=CLASS_RE),
    min_bgcs: int = Query(0, ge=0, le=100000),
    mibig: bool = Query(False, description="only families holding a MIBiG reference BGC"),
    sort: str = Query("bgcs", pattern=FAM_SORT_RE),
    dir: str = Query("", pattern="^(asc|desc)?$"),
    offset: int = Query(0, ge=0, le=200000),
    limit: int = Query(50, ge=1, le=200),
):
    """Browse gene cluster families; the default tier is the motif set, the one the site can show most for."""
    where, args = [], []
    if tier != "all":
        where.append(TIER_SQL[tier])
    if bgc_class:
        # delimiter-anchored so "NRP" cannot match inside another token
        where.append("(', ' || f.dominant_class || ', ') LIKE ?")
        args.append(f"%, {bgc_class}, %")
    if min_bgcs:
        where.append("f.n_bgcs >= ?")
        args.append(min_bgcs)

    c = db()
    mib = mibig_families()

    def envelope(total, fams, total_all=None):
        """Response body; `total_all` is the same count with the tier clause dropped."""
        out = {"total": total, "offset": offset, "tier": tier, "q": qs,
               "sort": sort, "dir": dir or FAM_DIR.get(sort, "desc").lower(),
               "families": fams}
        if total_all is not None:
            out["total_all"] = total_all
        return out

    # q and mibig both narrow to a set of ids; intersect here and bind once
    ids, qs = None, q.strip()
    if qs:
        try:
            ids = families_matching(c, qs)
        except HTTPException:
            c.close()
            raise
    if mibig:
        ids = set(mib) if ids is None else ids & set(mib)
    if ids is not None and not ids:                 # nothing matched at all
        c.close()
        return envelope(0, [], 0 if (qs or mibig) else None)

    join, pre = "", []
    if ids is not None:
        join = " JOIN json_each(?) j ON j.value = f.family_id "
        pre = [json.dumps(sorted(ids))]

    sql_where = (" WHERE " + " AND ".join(where)) if where else ""
    total = c.execute("SELECT COUNT(*) FROM family f" + join + sql_where,
                      (*pre, *args)).fetchone()[0]

    # the same query with no tier filter, so the page can tell "nothing matches"
    # from "nothing matches in this tier"
    total_all = None
    if qs or mibig:
        # TIER_SQL entries bind nothing, so dropping one leaves `args` untouched
        untiered = [w for w in where if w not in TIER_SQL.values()]
        total_all = c.execute(
            "SELECT COUNT(*) FROM family f" + join +
            ((" WHERE " + " AND ".join(untiered)) if untiered else ""),
            (*pre, *args)).fetchone()[0]
    # NULLS LAST in both directions: n_cogs_meme and dominant_tf are NULL for most families
    order = f"{FAM_ORDER[sort]} {(dir or FAM_DIR.get(sort, 'DESC')).upper()} NULLS LAST"
    fams = rows(c.execute(
        FAM_SELECT + join + sql_where +
        f" ORDER BY {order}, f.family_id LIMIT ? OFFSET ?",
        (*pre, *args, limit, offset)))
    c.close()
    for f in fams:
        f["mibig"] = mib.get(f["family_id"], [])
    return envelope(total, fams, total_all)

@router.get("/api/families/facets")
def families_facets():
    return family_facets()
