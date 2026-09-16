"""PRODORIC: the known binding sites our de-novo motifs are tested against."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..caches import node_tf_family_source, tf_family_of_node
from ..config import Q_MATCH
from ..db import db, rows

router = APIRouter()

@router.get("/api/prodoric/validation")
def prodoric_validation(scope: str = Query("cluster", pattern="^(all|cluster|tested|matched)$")):
    """PRODORIC TFs and their status against the de-novo motif clusters; the default scope is those that entered an SSN."""
    c = db()
    node_tf = (", MIN(tf_family_id) AS node_tf_family_id"
               if node_tf_family_source() == "column"
               else ", NULL AS node_tf_family_id")
    rs = rows(c.execute(
        """SELECT p.mx_acc, p.tf_name, p.gene, p.organism, p.uniprot,
                  p.consensus, p.n_sites, p.has_pwm,
                  v.ssn_id, v.mc_id, v.n_motif_clusters_tested, v.n_motifs_tested,
                  v.n_motifs_matched, v.best_qvalue, v.best_query_motif,
                  v.family_coverage, mc.n_families_motif, mc.n_families_ssn,
                  tf.name AS tf_family, s.mcl_cluster, s.n_nodes, s.n_families,
                  n.n_ssn_nodes, n.node_pk, n.node_tf_family_id
             FROM prodoric_tf p
             LEFT JOIN prodoric_validation v ON v.mx_acc = p.mx_acc
             LEFT JOIN motif_cluster mc ON mc.mc_id = v.mc_id
             LEFT JOIN (SELECT mx_acc, MIN(ssn_id) AS ssn_id, COUNT(*) AS n_ssn_nodes,
                                 MIN(node_pk) AS node_pk {NODE_TF}
                          FROM ssn_node WHERE is_prodoric = 1
                         GROUP BY mx_acc) n ON n.mx_acc = p.mx_acc
             LEFT JOIN ssn_cluster s ON s.ssn_id = COALESCE(v.ssn_id, n.ssn_id)
             LEFT JOIN tf_family tf ON tf.tf_family_id = s.tf_family_id"""
        .replace("{NODE_TF}", node_tf)))
    names = {r["tf_family_id"]: r["name"] for r in c.execute("SELECT * FROM tf_family")}
    c.close()
    for r in rs:
        # a singleton has no ssn_cluster to inherit the family from
        if not r["tf_family"]:
            fid = r.pop("node_tf_family_id", None) or tf_family_of_node(r.get("node_pk"))
            r["tf_family"] = names.get(fid)
        r.pop("node_tf_family_id", None)
        r.pop("node_pk", None)
        # n_motifs_matched uses a looser cut than Q_MATCH; gate on the displayed q-value
        if (r["n_motifs_matched"] or 0) > 0 and \
                r["best_qvalue"] is not None and r["best_qvalue"] <= Q_MATCH:
            r["status"] = "matched"
        elif (r["n_motifs_tested"] or 0) > 0:
            r["status"] = "no_match"
        elif r["mcl_cluster"] is not None:
            r["status"] = "not_tested"
        elif r["n_ssn_nodes"]:
            r["status"] = "singleton"
        else:
            r["status"] = "not_in_ssn"
    rank = {"matched": 0, "no_match": 1, "not_tested": 2,
            "singleton": 3, "not_in_ssn": 4}
    rs.sort(key=lambda r: (rank[r["status"]],
                           r["best_qvalue"] if r["best_qvalue"] is not None else 9e9,
                           (r["tf_name"] or r["mx_acc"] or "").lower()))
    keep = {"all": None,
            "cluster": {"matched", "no_match", "not_tested", "singleton"},
            "tested": {"matched", "no_match"},
            "matched": {"matched"}}[scope]
    out = rs if keep is None else [r for r in rs if r["status"] in keep]
    counts = {k: sum(1 for r in rs if r["status"] == k) for k in rank}
    return {"total": len(out), "q_match": Q_MATCH, "scope": scope,
            "n_prodoric": len(rs), "counts": counts,
            "n_in_ssn": sum(counts[k] for k in
                            ("matched", "no_match", "not_tested", "singleton")),
            "n_matched": counts["matched"], "validation": out}

@router.get("/api/prodoric/{mx_acc}")
def prodoric_tf_detail(mx_acc: str):
    c = db()
    p = c.execute("SELECT * FROM prodoric_tf WHERE mx_acc = ?", (mx_acc,)).fetchone()
    if not p:
        c.close()
        raise HTTPException(404, f"prodoric tf {mx_acc} not found")
    ssns = rows(c.execute(
        """SELECT n.ssn_id, s.n_nodes, s.n_families, tf.name AS tf_family
             FROM ssn_node n
             LEFT JOIN ssn_cluster s USING(ssn_id)
             LEFT JOIN tf_family tf ON tf.tf_family_id = s.tf_family_id
            WHERE n.mx_acc = ?""", (mx_acc,)))
    val = rows(c.execute(
        "SELECT * FROM prodoric_validation WHERE mx_acc = ? ORDER BY best_qvalue",
        (mx_acc,)))
    if not ssns and val:
        # a node with a malformed mx_acc (EctR1 stores 'nan') misses the join
        # above; recover its cluster through the validation row's ssn_id
        ssns = rows(c.execute(
            """SELECT s.ssn_id, s.n_nodes, s.n_families, tf.name AS tf_family
                 FROM ssn_cluster s
                 LEFT JOIN tf_family tf USING(tf_family_id)
                WHERE s.ssn_id IN (%s)"""
            % ",".join("?" * len(val)), [v["ssn_id"] for v in val]))
    c.close()
    return {"tf": dict(p), "ssn_clusters": ssns, "validation": val}
