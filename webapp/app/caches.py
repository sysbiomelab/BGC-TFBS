"""lru_cache-backed lookups over the database, which is read-only and never
   changes while the process lives, so nothing here can go stale.
"""
from __future__ import annotations

import functools
import json

from .constants import CLASS_TOKENS, TIER_SQL
from .db import HI_CHAR, db

@functools.lru_cache(maxsize=1)
def site_counts() -> dict:
    """Site-wide counts for /api/meta."""
    c = db()
    counts = {}
    for label, q in [
        # corpus
        ("families", "SELECT COUNT(*) FROM family"),
        ("bgcs", "SELECT COUNT(*) FROM bgc"),
        ("cds", "SELECT COUNT(*) FROM cds"),
        ("species", "SELECT COUNT(DISTINCT species) FROM taxon"),
        ("genera", "SELECT COUNT(DISTINCT genus) FROM taxon"),
        ("phyla", "SELECT COUNT(DISTINCT phylum) FROM taxon"),
        # per-family data tiers; the flags are NOT nested
        ("families_with_tf", "SELECT COUNT(*) FROM family WHERE has_tf_data=1"),
        ("families_with_cogs", "SELECT COUNT(*) FROM family WHERE has_cog_data=1"),
        ("families_with_motifs", "SELECT COUNT(*) FROM family WHERE has_motif_data=1"),
        # motifs; is_showcase marks the best per COG
        ("cogs", "SELECT COUNT(*) FROM cog"),
        ("cogs_with_meme", "SELECT COUNT(*) FROM cog WHERE has_meme=1"),
        ("motifs_showcase", "SELECT COUNT(*) FROM motif WHERE is_showcase=1"),
        ("motifs", "SELECT COUNT(*) FROM motif"),
        # Path B
        ("tf_families_with_ssn", "SELECT COUNT(*) FROM tf_family WHERE has_ssn=1"),
        ("ssn_clusters", "SELECT COUNT(*) FROM ssn_cluster"),
        ("ssn_nodes", "SELECT COUNT(*) FROM ssn_node"),
        ("motif_clusters", "SELECT COUNT(*) FROM motif_cluster"),
        ("prodoric_tfs", "SELECT COUNT(*) FROM prodoric_tf"),
        ("prodoric_in_ssn",
         "SELECT COUNT(DISTINCT mx_acc) FROM ssn_node WHERE is_prodoric=1"),
        ("prodoric_tested", "SELECT COUNT(*) FROM prodoric_validation"),
        ("prodoric_validated",
         "SELECT COUNT(*) FROM prodoric_validation WHERE n_motifs_matched > 0"),
    ]:
        counts[label] = c.execute(q).fetchone()[0]
    counts["ssn_family_names"] = [r[0] for r in c.execute(
        "SELECT name FROM tf_family WHERE has_ssn=1 ORDER BY name")]
    c.close()
    return counts

@functools.lru_cache(maxsize=1)
def taxon_families() -> dict[int, frozenset]:
    """taxon_id -> frozenset(family_id); ix_bgc_taxon is not covering, so the SQL form is too slow per query."""
    c = db()
    m: dict[int, set] = {}
    for tid, fam in c.execute("SELECT DISTINCT taxon_id, family_id FROM bgc"):
        m.setdefault(tid, set()).add(fam)
    c.close()
    return {k: frozenset(v) for k, v in m.items()}

@functools.lru_cache(maxsize=1)
def mibig_families() -> dict[str, list]:
    """family_id -> MIBiG accessions with the version suffix dropped (only the bare accession is durable)."""
    c = db()
    out: dict[str, list] = {}
    for fam, name in c.execute(
            """SELECT family_id, bgc_name FROM bgc
                WHERE bgc_name >= 'BGC' AND bgc_name < ? ORDER BY bgc_name""",
            ("BGC" + HI_CHAR,)):
        out.setdefault(fam, []).append(name.split(".")[0])
    c.close()
    return out

@functools.lru_cache(maxsize=1)
def family_facets() -> dict:
    """Tier counts and, per tier, the class counts."""
    c = db()
    out = {}
    mib = json.dumps(sorted(mibig_families()))
    for tier, cond in [("all", "1"), *[(k, v) for k, v in TIER_SQL.items()]]:
        n = c.execute(f"SELECT COUNT(*) FROM family f WHERE {cond}").fetchone()[0]
        n_mibig = c.execute(
            f"""SELECT COUNT(*) FROM family f JOIN json_each(?) j ON j.value = f.family_id
                 WHERE {cond}""", (mib,)).fetchone()[0]
        classes = {}
        for tok in CLASS_TOKENS:
            classes[tok] = c.execute(
                f"""SELECT COUNT(*) FROM family f
                     WHERE {cond} AND (', ' || f.dominant_class || ', ') LIKE ?""",
                (f"%, {tok}, %",)).fetchone()[0]
        out[tier] = {"n": n, "n_mibig": n_mibig, "classes": classes}
    c.close()
    return out

@functools.lru_cache(maxsize=1)
def node_tf_family_source() -> str:
    """'column' once ssn_node carries tf_family_id, else 'blocks'."""
    c = db()
    cols = {r[1] for r in c.execute("PRAGMA table_info(ssn_node)")}
    c.close()
    return "column" if "tf_family_id" in cols else "blocks"

@functools.lru_cache(maxsize=1)
def ssn_family_blocks() -> tuple[tuple[int, int], ...]:
    """((lo_node_pk, tf_family_id), ...) ascending: the loader writes one family at a
       time, so each owns a contiguous node_pk block -- the only route to a singleton's family."""
    c = db()
    out = tuple((r["lo"], r["tf_family_id"]) for r in c.execute(
        """SELECT s.tf_family_id, MIN(n.node_pk) AS lo
             FROM ssn_node n JOIN ssn_cluster s USING(ssn_id)
            GROUP BY s.tf_family_id ORDER BY lo"""))
    c.close()
    return out

def tf_family_of_node(node_pk: int | None) -> int | None:
    """The family owning this node_pk: the block with the greatest lo <= it."""
    if node_pk is None:
        return None
    fid = None
    for lo, f in ssn_family_blocks():
        if lo <= node_pk:
            fid = f
        else:
            break
    return fid
