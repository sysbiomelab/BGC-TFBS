"""Suite-wide fixtures.

tests/fixture.db is a miniature website.db with the production schema. Each
run copies it, `_augment` adds the rows the tests need, and the app is
imported over the copy with WEBSITE_DB pointing at it. The copy is opened
read-only by the app; the file in the repository is never modified.
"""
from __future__ import annotations

import contextlib
import importlib
import os
import shutil
import sys

import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TESTS_DIR)             # webapp/, where `app` imports from
if ROOT not in sys.path:                      # tests/ has no __init__.py, so
    sys.path.insert(0, ROOT)                  # pytest only adds tests/ itself

# --------------------------------------------------------------- fixture rows
# family_id -> the columns /api/families reads. The sortable counts are all
# distinct so that a sort assertion cannot pass on a tie.
#
#   FAM10  motif data WITHOUT cog data      -- the tiers are not nested
#   FAM11  cog data only, class exactly NRP -- the positive class match
#   FAM12  tf data only, two-token class
#   FAM13  'NRPS,PKS'                       -- must NOT match class=NRP
#   FAM14  NULLs across the sortable columns -- NULLS LAST in both directions
EXTRA_FAMILIES = {
    "FAM10": dict(n_bgcs=900, total_cds=9000, dominant_class="Polyketide, NRP",
                  n_species=90, n_genera=80, n_cogs_meme=9,
                  has_motif_data=1, has_cog_data=0, has_tf_data=0),
    "FAM11": dict(n_bgcs=700, total_cds=7000, dominant_class="NRP",
                  n_species=70, n_genera=60, n_cogs_meme=7,
                  has_motif_data=0, has_cog_data=1, has_tf_data=0),
    "FAM12": dict(n_bgcs=300, total_cds=3000, dominant_class="Terpene, RiPP",
                  n_species=30, n_genera=20, n_cogs_meme=None,
                  has_motif_data=0, has_cog_data=0, has_tf_data=1),
    "FAM13": dict(n_bgcs=1, total_cds=10, dominant_class="NRPS,PKS",
                  n_species=1, n_genera=1, n_cogs_meme=None,
                  has_motif_data=0, has_cog_data=0, has_tf_data=0),
    "FAM14": dict(n_bgcs=2000, total_cds=None, dominant_class=None,
                  n_species=None, n_genera=None, n_cogs_meme=None,
                  has_motif_data=1, has_cog_data=1, has_tf_data=0),
}

# what fixture.db holds, so tests can reason about all of it
BASE_FAMILIES = {
    "FAM1": dict(n_bgcs=150, total_cds=40, dominant_class="NRPS",
                 n_species=4, n_genera=3, n_cogs_meme=2,
                 has_motif_data=1, has_cog_data=1, has_tf_data=1),
    "FAM2": dict(n_bgcs=150, total_cds=40, dominant_class="NRPS",
                 n_species=4, n_genera=3, n_cogs_meme=2,
                 has_motif_data=1, has_cog_data=1, has_tf_data=1),
    "FAM3": dict(n_bgcs=5, total_cds=40, dominant_class="NRPS",
                 n_species=4, n_genera=3, n_cogs_meme=None,
                 has_motif_data=0, has_cog_data=0, has_tf_data=1),
}
ALL_FAMILIES = {**BASE_FAMILIES, **EXTRA_FAMILIES}

# the EXTRA_FAMILIES are metadata-only rows, so only these three own BGCs (and
# therefore taxonomy)
FAMILIES_WITH_BGCS = {"FAM1", "FAM2", "FAM3"}
# only FAM1 holds a MIBiG cluster; the other fixture BGCs carry assembly-scoped
# antiSMASH names
MIBIG_FAMILIES = {"FAM1"}
MIBIG_ACCESSION = "BGC0001280"

# the shape of a real HPC scratch path: a home directory under /personal/
FAKE_HPC_BASE = "/scratch/prj/example/personal/user1/BGC_TFBS"

# environment that must not be inherited from the shell -- the downloads
# assertions depend on the live flag being unset
_CLEARED_ENV = ("BGC_TFBS_DOWNLOADS_LIVE", "BGC_TFBS_CONTACT", "BGC_TFBS_BASE",
                "BGC_TFBS_MANIFEST")


# --------------------------------------------------------------- db building
def _build_fixture_db(workdir: str) -> str:
    """Copy the checked-in fixture and add the rows the tests need."""
    src = os.path.join(TESTS_DIR, "fixture.db")
    if not os.path.exists(src):
        raise RuntimeError(f"{src} is missing")
    db_path = os.path.join(workdir, "website.db")
    shutil.copyfile(src, db_path)
    _augment(db_path)
    return db_path


def _augment(db_path: str) -> None:
    """Add the rows, paths and outcomes the fixture cannot produce."""
    import sqlite3

    c = sqlite3.connect(db_path)
    with c:
        cols = ("family_id", "n_bgcs", "total_cds", "dominant_class", "n_species",
                "n_genera", "n_cogs_meme", "has_motif_data", "has_cog_data",
                "has_tf_data")
        c.executemany(
            f"INSERT INTO family ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
            [(fid, *(row[k] for k in cols[1:])) for fid, row in EXTRA_FAMILIES.items()])

        # HPC scratch paths -- never servable, and they carry a home directory
        c.execute("UPDATE build_info SET value = ? WHERE key = 'base'", (FAKE_HPC_BASE,))
        # a key a future rebuild might add: /api/meta allow-lists, so it must
        # not appear either
        c.execute("INSERT OR REPLACE INTO build_info (key, value) VALUES (?, ?)",
                  ("source_tree", FAKE_HPC_BASE + "/analysis"))

        # --- motif_cluster as the real db holds it -------------------------
        # pipe-joined membership, a chosen best motif, and a consensus PWM
        c.execute("UPDATE motif_cluster SET families = REPLACE(families, ',', '|'),"
                  " cogs = REPLACE(cogs, ',', '|')")
        c.execute("""UPDATE motif_cluster SET
                       best_motif_pk = (SELECT MIN(motif_pk) FROM motif_cluster_member
                                         WHERE mc_id = motif_cluster.mc_id),
                       pwm = (SELECT m.pwm FROM motif_cluster_member mm
                                JOIN motif m USING(motif_pk)
                               WHERE mm.mc_id = motif_cluster.mc_id
                                 AND m.pwm IS NOT NULL LIMIT 1)""")

        # --- one PRODORIC TF per documented status -------------------------
        # matched: MX000001, already validated by the fixture
        c.executemany(
            """INSERT OR REPLACE INTO prodoric_tf
               (mx_acc, tf_name, gene, organism, uniprot, consensus, n_sites, has_pwm)
               VALUES (?, ?, ?, ?, ?, ?, ?, 1)""",
            [("MX000002", "ToxT", "toxT", "V. cholerae", "P0B1", "TTTTGAT", 6),
             ("MX000003", "FooR", "fooR", "E. coli", "P0B2", "GGGCCC", 4),
             ("MX000004", "CysB", "cysB", "S. enterica", "P0B3", "TAAT", 9),
             ("MX000005", "GcvA", "gcvA", "E. coli", "P0B4", "CTAAT", 7)])
        # anchors inside cluster 1; the singleton keeps ssn_id NULL because MCL
        # emits no 1-node clusters
        c.executemany(
            """INSERT INTO ssn_node
               (node_pk, ssn_id, is_prodoric, mx_acc, uniprot, seq_len)
               VALUES (?, ?, 1, ?, ?, ?)""",
            [(2, 1, "MX000001", "P0A9", 305),
             (3, 1, "MX000004", "P0B3", 324),
             (4, 1, "MX000005", "P0B4", 305),
             (5, None, "MX000002", "P0B1", 276)])
        c.execute("UPDATE ssn_cluster SET n_prodoric = 3,"
                  " prodoric_tfs = 'OxyR|CysB|GcvA' WHERE ssn_id = 1")

        # --- representative sequences, as the real database holds them ------------
        # every node carries aa_seq; the rep prefers a non-PRODORIC member
        c.execute("UPDATE ssn_node SET aa_seq = 'MKT' || node_pk,"
                  " locus_tag = COALESCE(locus_tag, 'LT_' || node_pk)")
        c.execute("""
            UPDATE ssn_cluster AS sc
               SET rep_locus_tag = s.locus_tag, rep_aa_seq = s.aa_seq
              FROM (SELECT ssn_id, locus_tag, aa_seq,
                           ROW_NUMBER() OVER (PARTITION BY ssn_id
                               ORDER BY COALESCE(is_prodoric,0) ASC,
                                        LENGTH(COALESCE(aa_seq,'')) DESC, node_pk) rn
                      FROM ssn_node WHERE aa_seq IS NOT NULL AND aa_seq != '') s
             WHERE s.ssn_id = sc.ssn_id AND s.rn = 1""")

        # tested but nothing matched
        c.execute("""INSERT INTO prodoric_validation
                     (mx_acc, ssn_id, mc_id, n_motif_clusters_tested,
                      n_motifs_tested, n_motifs_matched, best_qvalue)
                     VALUES ('MX000004', 1, NULL, 1, 3, 0, NULL)""")
    c.close()


# --------------------------------------------------------------- app import
@contextlib.contextmanager
def _imported_app(db_path: str, **env):
    """Import a pristine `app` package with WEBSITE_DB pointing at `db_path`.

    app/config.py reads the environment at import time and app/db.py binds
    `from .config import DB_PATH`, so reloading one module is not enough --
    every app.* module is dropped from sys.modules and re-imported. The
    previous set is restored on exit so a test that needs a differently
    configured app cannot leave the shared client's modules swapped out.
    """
    saved_modules = {k: v for k, v in sys.modules.items()
                     if k == "app" or k.startswith("app.")}
    saved_env = {k: os.environ.get(k) for k in (*_CLEARED_ENV, "WEBSITE_DB")}
    try:
        for k in saved_modules:
            del sys.modules[k]
        for k in _CLEARED_ENV:
            os.environ.pop(k, None)
        os.environ["WEBSITE_DB"] = db_path
        os.environ.update(env)
        yield importlib.import_module("app.main")
    finally:
        for k in list(sys.modules):
            if k == "app" or k.startswith("app."):
                del sys.modules[k]
        sys.modules.update(saved_modules)
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# --------------------------------------------------------------- fixtures
@pytest.fixture(scope="session")
def fixture_db(tmp_path_factory) -> str:
    """Path to the miniature website.db. Skips the suite if it cannot be built."""
    workdir = str(tmp_path_factory.mktemp("bgc_tfbs_fixture"))
    try:
        return _build_fixture_db(workdir)
    except Exception as e:                      # noqa: BLE001 -- skip, never error
        pytest.skip(f"could not build the fixture database: {e}")


@pytest.fixture(scope="session")
def app_module(fixture_db):
    with _imported_app(fixture_db) as mod:
        # sanity: the env var won, so the suite is not running against a real
        # database
        from app.config import DB_PATH
        assert DB_PATH == fixture_db, f"WEBSITE_DB was ignored: DB_PATH={DB_PATH}"
        yield mod


@pytest.fixture(scope="session")
def client(app_module):
    """TestClient over the fixture db. `with` runs lifespan (the taxon warmer)."""
    from fastapi.testclient import TestClient

    with TestClient(app_module.app) as c:
        yield c


@pytest.fixture
def archive_client(fixture_db):
    """A second app, imported with BGC_TFBS_DOWNLOADS_LIVE set, for the one
       test that checks the download links go live with no code change."""
    from fastapi.testclient import TestClient

    with _imported_app(fixture_db,
                       BGC_TFBS_DOWNLOADS_LIVE="1",
                       BGC_TFBS_CONTACT="someone@example.org") as mod:
        with TestClient(mod.app) as c:
            yield c
