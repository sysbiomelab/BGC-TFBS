"""Path B: TF families -> SSN clusters -> motif clusters.

   Cross-family and TF-centric, as opposed to Path A's per-family view.
"""
from __future__ import annotations

import re
import sqlite3

from fastapi import APIRouter, HTTPException, Query

from ..config import Q_MATCH
from ..db import db, like_esc, rows
from ..pwm import parse_pwm

router = APIRouter()

# ================================================================ Path B: TF / SSN
# Few SSNs carry motif clusters or a PRODORIC anchor; every list needs an empty state.

def pipe(s) -> list[str]:
    """'NRP|Other|RiPP' -> ['NRP','Other','RiPP']"""
    return [x for x in (s or "").split("|") if x]

def ssn_row(r: sqlite3.Row) -> dict:
    d = dict(r)
    for k in ("bgc_classes", "kingdoms", "top_phyla", "prodoric_tfs"):
        if k in d:
            d[k] = pipe(d[k])
    return d

@router.get("/api/tf/families")
def tf_families():
    """TF families that have an SSN, with cluster/node/validation totals."""
    c = db()
    fams = rows(c.execute(
        """SELECT tf.tf_family_id, tf.name,
                  COUNT(*)                AS n_ssn,
                  SUM(s.n_nodes)          AS n_nodes,
                  SUM(s.n_families)       AS n_families,
                  SUM(s.n_prodoric)       AS n_prodoric,
                  SUM(s.n_nodes >= 5)     AS n_ssn_min5,
                  MAX(s.n_nodes)          AS max_nodes
             FROM ssn_cluster s JOIN tf_family tf USING(tf_family_id)
            GROUP BY tf.tf_family_id
            ORDER BY n_nodes DESC"""))
    # SSNs carrying motif clusters, per TF family
    withmc = {r["tf_family_id"]: r["n"] for r in c.execute(
        """SELECT s.tf_family_id, COUNT(DISTINCT mc.ssn_id) AS n
             FROM motif_cluster mc JOIN ssn_cluster s USING(ssn_id)
            GROUP BY s.tf_family_id""")}
    # the db's n_motifs_matched is a looser cut than Q_MATCH; gate on best_qvalue too
    validated = {r["tf_family_id"]: r["n"] for r in c.execute(
        """SELECT s.tf_family_id, COUNT(*) AS n
             FROM prodoric_validation v JOIN ssn_cluster s USING(ssn_id)
            WHERE v.n_motifs_matched > 0 AND v.best_qvalue <= ?
            GROUP BY s.tf_family_id""", (Q_MATCH,))}
    for f in fams:
        f["n_ssn_with_motifs"] = withmc.get(f["tf_family_id"], 0)
        f["n_validated"] = validated.get(f["tf_family_id"], 0)
    c.close()
    return {"tf_families": fams}

@router.get("/api/ssn")
def ssn_list(
    tf_family_id: int | None = None,
    min_nodes: int = Query(5, ge=1),
    has_motifs: bool = False,
    has_prodoric: bool = False,
    q: str = Query("", max_length=100),
    sort: str = Query("nodes", pattern="^(nodes|families|prodoric|motifs)$"),
    offset: int = Query(0, ge=0, le=200000),
    limit: int = Query(50, ge=1, le=200),
):
    """Ranked SSN clusters; `q` matches only the displayed mcl_cluster number, a regulator name or a phylum."""
    where = ["s.n_nodes >= ?"]
    args: list = [min_nodes]
    if tf_family_id is not None:
        where.append("s.tf_family_id = ?")
        args.append(tf_family_id)
    qs = q.strip()
    if qs:
        ors, qargs = [], []
        m_id = re.fullmatch(r"(?:cluster\s*)?(\d+)", qs, re.I)
        if m_id:            # the cluster number as displayed: per-family, 0-based
            ors.append("s.mcl_cluster = ?")
            qargs.append(int(m_id.group(1)))
        else:                                      # a known regulator, or a phylum
            for col in ("s.prodoric_tfs", "s.top_phyla"):
                ors.append(f"{col} LIKE ? ESCAPE '\\'")
                qargs.append(f"%{like_esc(qs)}%")
        where.append("(" + " OR ".join(ors) + ")")
        args.extend(qargs)
    if has_prodoric:
        where.append("s.n_prodoric > 0")
    if has_motifs:
        where.append("mc.n_motif_clusters > 0")
    order = {
        "nodes": "s.n_nodes DESC",
        "families": "s.n_families DESC",
        "prodoric": "s.n_prodoric DESC, s.n_nodes DESC",
        "motifs": "mc.n_motif_clusters DESC NULLS LAST, s.n_nodes DESC",
    }[sort]
    sql_from = """
        FROM ssn_cluster s
        JOIN tf_family tf USING(tf_family_id)
        LEFT JOIN (SELECT ssn_id, COUNT(*) AS n_motif_clusters,
                          SUM(n_motifs) AS n_motifs, MAX(family_coverage) AS best_coverage
                     FROM motif_cluster GROUP BY ssn_id) mc ON mc.ssn_id = s.ssn_id
        WHERE """ + " AND ".join(where)
    c = db()
    total = c.execute("SELECT COUNT(*) " + sql_from, args).fetchone()[0]
    clusters = [ssn_row(r) for r in c.execute(
        f"""SELECT s.ssn_id, s.tf_family_id, tf.name AS tf_family, s.mcl_cluster,
                   s.n_nodes, s.n_families, s.n_prodoric, s.in_pipeline_pct,
                   s.bgc_classes, s.kingdoms, s.top_phyla, s.prodoric_tfs,
                   COALESCE(mc.n_motif_clusters, 0) AS n_motif_clusters,
                   COALESCE(mc.n_motifs, 0) AS n_motifs, mc.best_coverage
            {sql_from} ORDER BY {order}, s.ssn_id LIMIT ? OFFSET ?""",
        (*args, limit, offset)).fetchall()]
    c.close()
    return {"total": total, "offset": offset, "clusters": clusters}

@router.get("/api/ssn/{ssn_id}")
def ssn_detail(ssn_id: int, logos: int = Query(24, le=50)):
    """Cluster summary, its top `logos` motif clusters, PRODORIC anchors and validation."""
    c = db()
    s = c.execute(
        """SELECT s.*, tf.name AS tf_family FROM ssn_cluster s
           LEFT JOIN tf_family tf USING(tf_family_id) WHERE s.ssn_id = ?""",
        (ssn_id,)).fetchone()
    if not s:
        c.close()
        raise HTTPException(404, f"ssn cluster {ssn_id} not found")
    cluster = ssn_row(s)
    # empty rep_* columns are dropped so the page never renders a blank sequence block
    for k in ("rep_aa_seq", "rep_locus_tag"):
        if not cluster.get(k):
            cluster.pop(k, None)

    # member families with motif data; PRODORIC anchor nodes carry pseudo family
    # ids and drop out of the join by themselves
    n_fam_motif = c.execute(
        """SELECT COUNT(*) FROM (SELECT DISTINCT n.family_id FROM ssn_node n
                                   WHERE n.ssn_id = ?) x
             JOIN family f ON f.family_id = x.family_id
            WHERE f.has_motif_data = 1""", (ssn_id,)).fetchone()[0]

    n_mc = c.execute("SELECT COUNT(*) FROM motif_cluster WHERE ssn_id = ?",
                     (ssn_id,)).fetchone()[0]
    mcs = rows(c.execute(
        """SELECT mc_id, mcl_cluster, n_motifs, n_families_motif, n_families_ssn,
                  family_coverage, n_cogs, is_best_for_ssn, best_motif_pk, pwm
             FROM motif_cluster WHERE ssn_id = ?
            ORDER BY is_best_for_ssn DESC, family_coverage DESC, n_motifs DESC
            LIMIT ?""", (ssn_id, logos)))
    for m in mcs:
        m["pwm_parsed"] = parse_pwm(m.pop("pwm"))

    anchors = rows(c.execute(
        """SELECT n.mx_acc, n.uniprot, n.locus_tag, n.seq_len,
                  p.tf_name, p.gene, p.organism, p.consensus, p.n_sites, p.has_pwm
             FROM ssn_node n LEFT JOIN prodoric_tf p USING(mx_acc)
            WHERE n.ssn_id = ? AND n.is_prodoric = 1
            ORDER BY p.tf_name""", (ssn_id,)))
    validation = rows(c.execute(
        """SELECT v.*, p.tf_name, p.gene, p.organism, p.consensus
             FROM prodoric_validation v LEFT JOIN prodoric_tf p USING(mx_acc)
            WHERE v.ssn_id = ?
            ORDER BY (v.n_motifs_matched > 0) DESC, v.best_qvalue""", (ssn_id,)))
    for v in validation:
        v["matched"] = bool((v["n_motifs_matched"] or 0) > 0
                            and v["best_qvalue"] is not None
                            and v["best_qvalue"] <= Q_MATCH)

    top_families = rows(c.execute(
        """SELECT n.family_id, COUNT(*) AS n_nodes, f.dominant_class,
                  f.n_bgcs, f.has_motif_data
             FROM ssn_node n LEFT JOIN family f USING(family_id)
            WHERE n.ssn_id = ? AND n.is_prodoric = 0
            GROUP BY n.family_id ORDER BY n_nodes DESC, n.family_id LIMIT 25""",
        (ssn_id,)))
    taxa = rows(c.execute(
        """SELECT t.phylum, t.genus, COUNT(*) AS n
             FROM ssn_node n JOIN taxon t USING(taxon_id)
            WHERE n.ssn_id = ? AND n.is_prodoric = 0
            GROUP BY t.phylum, t.genus ORDER BY n DESC LIMIT 15""", (ssn_id,)))
    c.close()
    return {"cluster": cluster, "n_motif_clusters": n_mc, "motif_clusters": mcs,
            "prodoric_anchors": anchors, "validation": validation,
            "n_member_families_with_motifs": n_fam_motif,
            "top_families": top_families, "taxa": taxa}

@router.get("/api/ssn/by/{tf_name}/{mcl_cluster}")
def ssn_by_cluster(tf_name: str, mcl_cluster: int, logos: int = Query(24, le=50)):
    """Look up a cluster by TF family and 0-based mcl_cluster; ssn_id is a surrogate, never shown as a cluster number."""
    c = db()
    row = c.execute(
        """SELECT s.ssn_id FROM ssn_cluster s JOIN tf_family tf USING(tf_family_id)
            WHERE tf.name = ? COLLATE NOCASE AND s.mcl_cluster = ?""",
        (tf_name, mcl_cluster)).fetchone()
    c.close()
    if not row:
        raise HTTPException(404, f"{tf_name} cluster {mcl_cluster} not found")
    return ssn_detail(row["ssn_id"], logos=logos)

@router.get("/api/ssn/{ssn_id}/nodes")
def ssn_nodes(ssn_id: int,
              offset: int = Query(0, ge=0, le=200000),
              limit: int = Query(50, ge=1, le=200)):
    """Member TF proteins; aa_seq is never returned in bulk."""
    c = db()
    total = c.execute("SELECT COUNT(*) FROM ssn_node WHERE ssn_id = ?",
                      (ssn_id,)).fetchone()[0]
    nodes = rows(c.execute(
        """SELECT n.node_pk, n.is_prodoric, n.family_id, n.bgc_id, n.locus_tag,
                  n.uniprot, n.mx_acc, n.seq_len, t.species, t.genus, t.phylum
             FROM ssn_node n LEFT JOIN taxon t USING(taxon_id)
            WHERE n.ssn_id = ?
            ORDER BY n.is_prodoric DESC, n.seq_len DESC, n.node_pk
            LIMIT ? OFFSET ?""", (ssn_id, limit, offset)))
    c.close()
    return {"total": total, "offset": offset, "nodes": nodes}

@router.get("/api/ssn/{ssn_id}/motif-clusters")
def ssn_motif_clusters(ssn_id: int,
                       offset: int = Query(0, ge=0, le=200000),
                       limit: int = Query(24, ge=1, le=100)):
    """Paged motif clusters."""
    c = db()
    total = c.execute("SELECT COUNT(*) FROM motif_cluster WHERE ssn_id = ?",
                      (ssn_id,)).fetchone()[0]
    mcs = rows(c.execute(
        """SELECT mc_id, mcl_cluster, n_motifs, n_families_motif, n_families_ssn,
                  family_coverage, n_cogs, is_best_for_ssn, best_motif_pk, pwm
             FROM motif_cluster WHERE ssn_id = ?
            ORDER BY is_best_for_ssn DESC, family_coverage DESC, n_motifs DESC
            LIMIT ? OFFSET ?""", (ssn_id, limit, offset)))
    for m in mcs:
        m["pwm_parsed"] = parse_pwm(m.pop("pwm"))
    c.close()
    return {"total": total, "offset": offset, "motif_clusters": mcs}

@router.get("/api/motif-cluster/{mc_id}")
def motif_cluster(mc_id: int, with_pwm: bool = False):
    """One motif cluster: consensus logo and member motifs, linked back to their family / COG."""
    c = db()
    mc = c.execute(
        """SELECT mc.mc_id, mc.ssn_id, mc.mcl_cluster, mc.n_motifs,
                  mc.n_families_motif, mc.n_families_ssn, mc.family_coverage,
                  mc.n_cogs, mc.families, mc.cogs, mc.is_best_for_ssn,
                  mc.best_motif_pk, mc.pwm,
                  s.tf_family_id, tf.name AS tf_family,
                  s.mcl_cluster AS ssn_mcl_cluster, s.n_nodes AS ssn_n_nodes
             FROM motif_cluster mc
             LEFT JOIN ssn_cluster s USING(ssn_id)
             LEFT JOIN tf_family tf ON tf.tf_family_id = s.tf_family_id
            WHERE mc.mc_id = ?""", (mc_id,)).fetchone()
    if not mc:
        c.close()
        raise HTTPException(404, f"motif cluster {mc_id} not found")
    d = dict(mc)
    d["pwm_parsed"] = parse_pwm(d.pop("pwm"))
    d["families"] = pipe(d.get("families"))
    d["cogs"] = pipe(d.get("cogs"))
    pwm_col = "m.pwm," if with_pwm else ""
    members = rows(c.execute(
        f"""SELECT mm.motif_pk, c2.family_id, c2.cog_id, c2.cog_name,
                   c2.conservation_rank, m.motif_number, m.evalue,
                   m.width, m.consensus, m.is_showcase, m.frac_seqs_with_motif,
                   {pwm_col} (m.motif_pk = ?) AS is_best
              FROM motif_cluster_member mm
              JOIN motif m USING(motif_pk)
              LEFT JOIN cog c2 ON c2.cog_id = m.cog_id
             WHERE mm.mc_id = ?
             ORDER BY is_best DESC, m.evalue ASC""",
        (d.get("best_motif_pk"), mc_id)))
    if with_pwm:
        for m in members:
            m["pwm_parsed"] = parse_pwm(m.pop("pwm"))
    c.close()
    return {"motif_cluster": d, "members": members}
