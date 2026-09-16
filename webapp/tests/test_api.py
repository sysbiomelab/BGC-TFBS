"""Every endpoint in the public API, over the miniature fixture database.

The assertions lean on the traps recorded in docs/SCHEMA.md rather than on the exact
numbers the loader happens to produce, so that a fixture that grows a row does
not break the suite but a regression in the un-nested tiers, the
delimiter-anchored class filter, the LIMIT -1 hole or the HPC-path leak does.
"""
from __future__ import annotations

import pytest

from conftest import (ALL_FAMILIES, FAKE_HPC_BASE, FAMILIES_WITH_BGCS,
                      MIBIG_ACCESSION, MIBIG_FAMILIES)

# ---------------------------------------------------------------- helpers
#: the whole documented surface -- every route, with the params worth exercising
API_URLS = [
    "/api/meta",
    "/api/downloads",
    "/api/search?q=FAM1",
    "/api/search?q=Streptomyces",
    "/api/families",
    "/api/families?tier=all&limit=200",
    "/api/families?tier=all&q=Streptomyces",
    "/api/families?tier=all&mibig=true",
    "/api/families/facets",
    "/api/family/FAM1",
    "/api/family/FAM1/bgcs",
    "/api/cog/1/motifs",
    "/api/tf/families",
    "/api/ssn",
    "/api/ssn?min_nodes=1&has_motifs=true",
    "/api/ssn/1",
    "/api/ssn/by/LysR/0",
    "/api/ssn/1/nodes",
    "/api/ssn/1/motif-clusters",
    "/api/motif-cluster/1",
    "/api/motif-cluster/1?with_pwm=true",
    "/api/prodoric/validation",
    "/api/prodoric/validation?scope=all",
    "/api/prodoric/MX000001",
]

#: sort= -> how to read the sorted-on value back out of a family row
SORT_KEY = {
    "id":      lambda f: int(f["family_id"][3:]),   # FAM100 sorts after FAM10
    "bgcs":    lambda f: f["n_bgcs"],
    "cds":     lambda f: f["total_cds"],
    "class":   lambda f: f["dominant_class"],
    "species": lambda f: f["n_species"],
    "genera":  lambda f: f["n_genera"],
    "motifs":  lambda f: f["n_cogs_meme"],
    "tf":      lambda f: f["dominant_tf"],
    "data":    lambda f: (f["has_motif_data"] * 4 + f["has_cog_data"] * 2
                          + f["has_tf_data"]),
}
#: the direction each column falls back to when dir= is not given
DEFAULT_DIR = {"id": "asc", "class": "asc", "tf": "asc"}


def ids(payload) -> list[str]:
    return [f["family_id"] for f in payload["families"]]


def assert_ordered(values, direction, what):
    """Monotonic in `direction`, with every NULL after every non-NULL."""
    seen_null = False
    for v in values:
        if v is None:
            seen_null = True
        else:
            assert not seen_null, f"{what}: a non-NULL followed a NULL -- {values}"
    solid = [v for v in values if v is not None]
    for a, b in zip(solid, solid[1:]):
        if direction == "asc":
            assert a <= b, f"{what}: {a!r} before {b!r} is not ascending"
        else:
            assert a >= b, f"{what}: {a!r} before {b!r} is not descending"


# ================================================================ the surface
def test_openapi_lists_exactly_the_documented_routes(client):
    """A refactor may move an endpoint between routers; it must not drop one."""
    got = set(client.get("/api/openapi.json").json()["paths"])
    assert got == {
        "/api/meta", "/api/search", "/api/families", "/api/families/facets",
        "/api/family/{family_id}", "/api/family/{family_id}/bgcs",
        "/api/cog/{cog_id}/motifs", "/api/tf/families", "/api/ssn",
        "/api/ssn/{ssn_id}", "/api/ssn/by/{tf_name}/{mcl_cluster}",
        "/api/ssn/{ssn_id}/nodes", "/api/ssn/{ssn_id}/motif-clusters",
        "/api/motif-cluster/{mc_id}", "/api/prodoric/validation",
        "/api/prodoric/{mx_acc}", "/api/downloads",
    }


def test_index_is_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "<html" in r.text.lower()


def test_static_files_are_mounted(client):
    r = client.get("/static/css/site.css")
    assert r.status_code == 200


@pytest.mark.parametrize("url", API_URLS)
def test_every_endpoint_answers(client, url):
    r = client.get(url)
    assert r.status_code == 200, r.text[:300]
    assert isinstance(r.json(), dict)


# ================================================================ /api/meta
def test_meta_shape(client):
    m = client.get("/api/meta").json()
    assert set(m) == {"build", "counts", "archive"}
    assert m["build"]["showcase_param"] == "zoops_maxw30"
    for k in ("families", "bgcs", "cds", "cogs", "motifs", "motifs_showcase",
              "families_with_tf", "families_with_cogs",
              "families_with_motifs", "ssn_clusters", "ssn_nodes",
              "motif_clusters", "prodoric_tfs", "prodoric_tested",
              "prodoric_validated", "ssn_family_names"):
        assert k in m["counts"], f"/api/meta lost the {k} count"
    assert m["counts"]["families"] == len(ALL_FAMILIES)


def test_meta_counts_separate_the_motif_totals(client):
    """Every motif row is zoops_maxw30, so there are two totals, not three."""
    c = client.get("/api/meta").json()["counts"]
    assert c["motifs_showcase"] <= c["motifs"]


def test_meta_build_info_is_allow_listed(client):
    """`base` is an HPC scratch path containing a home directory, and a key a
       future rebuild adds must not leak either."""
    build = client.get("/api/meta").json()["build"]
    assert "base" not in build
    assert "source_tree" not in build          # the decoy conftest inserts
    assert set(build) <= {"built_at", "showcase_param", "ssn_families"}


def test_meta_counts_agree_with_the_families_endpoint(client):
    counts = client.get("/api/meta").json()["counts"]
    for tier, key in (("motif", "families_with_motifs"), ("cog", "families_with_cogs"),
                      ("tf", "families_with_tf")):
        total = client.get(f"/api/families?tier={tier}&limit=1").json()["total"]
        assert total == counts[key], f"tier={tier} disagrees with /api/meta"


# ================================================================ /api/downloads
def test_downloads_is_the_zenodo_manifest_grouped_by_folder(client):
    """webapp/manifest.tsv (48 rows: 47 files plus the record README) drives
       the page; nothing links while BGC_TFBS_DOWNLOADS_LIVE is unset."""
    dl = client.get("/api/downloads").json()
    assert dl == client.get("/api/meta").json()["archive"]
    assert dl["live"] is False
    assert dl["doi"] == "10.5281/zenodo.22766286"
    assert dl["doi_url"] == "https://doi.org/10.5281/zenodo.22766286"
    assert [g["key"] for g in dl["groups"]] == ["global", "TFs", "ssn"]
    files = [f for g in dl["groups"] for f in g["files"]]
    assert len(files) + 1 == dl["n_files"] == 48
    assert dl["readme"]["name"] == "README.md" and dl["readme"]["url"] is None
    assert dl["total_bytes"] == sum(f["size_bytes"] for f in files) + dl["readme"]["size_bytes"]
    for f in files:
        assert set(f) >= {"path", "name", "size_bytes", "size", "md5", "url"}
        assert f["url"] is None, "the record is private, so nothing links yet"
        assert len(f["md5"]) == 32
    # every basename is unique -- Zenodo serves files flat, by basename
    assert len({f["name"] for f in files}) == len(files)


def test_downloads_go_live_with_only_the_env_var(archive_client):
    """The same rows become Zenodo links with no code change."""
    dl = archive_client.get("/api/downloads").json()
    assert dl["live"] is True
    assert dl["contact"] == "someone@example.org"
    files = [f for g in dl["groups"] for f in g["files"]]
    assert [f["url"] for f in files] == [
        f"https://zenodo.org/records/22766286/files/{f['name']}?download=1" for f in files]
    assert dl["readme"]["url"].endswith("/files/README.md?download=1")
    assert dl == archive_client.get("/api/meta").json()["archive"]


def test_human_size_is_decimal_and_readable():
    from app.routers.downloads import human_size
    assert human_size(2955) == "3.0 kB"
    assert human_size(4292934782) == "4.3 GB"
    assert human_size(12) == "12 B"


# ================================================================ /api/families
def test_families_default_view_is_the_motif_tier(client):
    p = client.get("/api/families").json()
    assert set(p) == {"total", "offset", "tier", "q", "sort", "dir", "families"}
    assert (p["tier"], p["sort"], p["dir"], p["offset"]) == ("motif", "bgcs", "desc", 0)
    assert all(f["has_motif_data"] == 1 for f in p["families"])


def test_families_row_shape(client):
    f = client.get("/api/families?tier=all&limit=1&sort=bgcs").json()["families"][0]
    assert set(f) == {"family_id", "n_bgcs", "total_cds", "dominant_class",
                      "n_kingdoms", "n_phyla", "n_genera", "n_species",
                      "n_cogs_meme", "has_tf_data", "has_cog_data",
                      "has_motif_data", "dominant_tf", "best_evalue", "mibig"}
    # the dead columns must stay out
    assert not {"kingdoms", "mean_cds_per_bgc", "n_cogs", "dominant_subclass",
                "subgroup", "passed_bgc_filter"} & set(f)


# ---- the tiers are three independent flags, never an AND -------------------
def test_tier_filters_are_independent_flags(client):
    got = {t: set(ids(client.get(f"/api/families?tier={t}&limit=200").json()))
           for t in ("all", "motif", "cog", "tf")}
    expect = {
        t: {fid for fid, r in ALL_FAMILIES.items() if r[f"has_{k}_data"] == 1}
        for t, k in (("motif", "motif"), ("cog", "cog"), ("tf", "tf"))}
    expect["all"] = set(ALL_FAMILIES)
    assert got == expect


def test_motif_tier_keeps_a_family_that_has_no_cog_data(client):
    """A family can have motif data without COG or TF data; ANDing the flags
       would silently drop it."""
    motif = set(ids(client.get("/api/families?tier=motif&limit=200").json()))
    cog = set(ids(client.get("/api/families?tier=cog&limit=200").json()))
    tf = set(ids(client.get("/api/families?tier=tf&limit=200").json()))
    assert "FAM10" in motif and "FAM10" not in cog and "FAM10" not in tf
    assert motif - cog and cog - motif, "the tiers must not be nested"
    assert len(motif) > len(motif & cog & tf), "tier=motif looks like an AND"


# ---- dominant_class is a ", "-joined SET -----------------------------------
def test_class_filter_is_delimiter_anchored(client):
    """"NRPS" and "NRPS,PKS" contain "NRP" as a substring and must not match."""
    got = set(ids(client.get("/api/families?tier=all&class=NRP&limit=200").json()))
    assert got == {"FAM10", "FAM11"}          # "Polyketide, NRP" and "NRP"
    assert "FAM13" not in got, 'dominant_class "NRPS,PKS" matched class=NRP'
    # more families contain "NRP" as a substring than carry it as a token, so a
    # LIKE '%NRP%' would return a bigger set
    all_classes = [f["dominant_class"] or "" for f in
                   client.get("/api/families?tier=all&limit=200").json()["families"]]
    assert sum("NRP" in c for c in all_classes) > len(got)


def test_class_filter_matches_every_token_of_a_multi_token_set(client):
    for tok, expect in (("Polyketide", {"FAM10"}), ("Terpene", {"FAM12"}),
                        ("RiPP", {"FAM12"}), ("Alkaloid", set()),
                        ("Saccharide", set()), ("Other", set())):
        got = set(ids(client.get(
            f"/api/families?tier=all&class={tok}&limit=200").json()))
        assert got == expect, f"class={tok}"


def test_class_filter_rejects_a_value_outside_the_seven_tokens(client):
    # "NRPS" is a real dominant_class string but not one of the 7 tokens
    assert client.get("/api/families?class=NRPS").status_code == 422
    assert client.get("/api/families?class=nrp").status_code == 422
    assert client.get("/api/families?class=NRP,%20Polyketide").status_code == 422


def test_facets_agree_with_the_filtered_totals(client):
    facets = client.get("/api/families/facets").json()
    assert set(facets) == {"all", "motif", "cog", "tf"}
    for tier, block in facets.items():
        assert set(block) == {"n", "n_mibig", "classes"}
        assert block["n"] == client.get(
            f"/api/families?tier={tier}&limit=1").json()["total"]
        for tok, n in block["classes"].items():
            assert n == client.get(
                f"/api/families?tier={tier}&class={tok}&limit=1").json()["total"], \
                f"facet {tier}/{tok}"


# ---- guards ----------------------------------------------------------------
@pytest.mark.parametrize("limit", [-1, 0, 201, 1000])
def test_families_rejects_out_of_range_limit(client, limit):
    """SQLite reads LIMIT -1 as unbounded, so ge=1 is the guard, not just le=."""
    assert client.get(f"/api/families?limit={limit}").status_code == 422


@pytest.mark.parametrize("offset", [-1, 200001])
def test_families_rejects_out_of_range_offset(client, offset):
    assert client.get(f"/api/families?offset={offset}").status_code == 422


def test_families_limit_one_returns_one_row(client):
    p = client.get("/api/families?tier=all&limit=1").json()
    assert len(p["families"]) == 1 and p["total"] == len(ALL_FAMILIES)


@pytest.mark.parametrize("bad", ["nope", "n_bgcs", "", "bgcs;--", "BGCS"])
def test_families_rejects_an_unknown_sort(client, bad):
    assert client.get(f"/api/families?sort={bad}").status_code == 422


@pytest.mark.parametrize("bad", ["up", "ASC", "descending", "1"])
def test_families_rejects_an_unknown_dir(client, bad):
    assert client.get(f"/api/families?dir={bad}").status_code == 422


def test_families_rejects_an_unknown_tier(client):
    assert client.get("/api/families?tier=motifs").status_code == 422
    assert client.get("/api/families?tier=").status_code == 422


def test_families_rejects_an_over_long_query(client):
    assert client.get("/api/families?q=" + "x" * 101).status_code == 422
    assert client.get("/api/families?min_bgcs=-1").status_code == 422


# ---- every sort, both directions, actually sorted --------------------------
@pytest.mark.parametrize("sort", sorted(SORT_KEY))
@pytest.mark.parametrize("direction", ["asc", "desc"])
def test_every_sort_and_dir_is_honoured(client, sort, direction):
    r = client.get(f"/api/families?tier=all&sort={sort}&dir={direction}&limit=200")
    assert r.status_code == 200
    p = r.json()
    assert (p["sort"], p["dir"]) == (sort, direction)
    assert len(p["families"]) == len(ALL_FAMILIES)
    assert_ordered([SORT_KEY[sort](f) for f in p["families"]], direction,
                   f"sort={sort}&dir={direction}")


@pytest.mark.parametrize("sort", sorted(SORT_KEY))
def test_default_direction_per_column(client, sort):
    """Counts read high-to-low; ids, names and classes low-to-high."""
    p = client.get(f"/api/families?tier=all&sort={sort}&limit=200").json()
    expect = DEFAULT_DIR.get(sort, "desc")
    assert p["dir"] == expect
    assert_ordered([SORT_KEY[sort](f) for f in p["families"]], expect, f"sort={sort}")


def test_id_sort_is_numeric_not_lexicographic(client):
    got = ids(client.get("/api/families?tier=all&sort=id&dir=asc&limit=200").json())
    assert got == sorted(got, key=lambda f: int(f[3:]))
    assert got != sorted(got), "FAM10 must not sort between FAM1 and FAM2"


def test_offset_pages_through_the_same_ordering(client):
    whole = ids(client.get("/api/families?tier=all&sort=id&dir=asc&limit=200").json())
    page = client.get(
        "/api/families?tier=all&sort=id&dir=asc&limit=3&offset=3").json()
    assert ids(page) == whole[3:6]
    assert page["offset"] == 3 and page["total"] == len(whole)


# ---- q= and mibig= ---------------------------------------------------------
def test_families_query_by_family_id(client):
    p = client.get("/api/families?tier=all&q=fam1").json()
    assert ids(p) == ["FAM1"] and p["q"] == "fam1"


def test_families_query_for_an_absent_family_is_empty_not_an_error(client):
    p = client.get("/api/families?tier=all&q=FAM999999").json()
    assert p["total"] == 0 and p["families"] == []


def test_families_query_by_taxon_bgc_id_and_accession_prefix(client):
    by_taxon = set(ids(client.get("/api/families?tier=all&q=Streptomyces").json()))
    assert by_taxon == FAMILIES_WITH_BGCS        # taxonomy comes through bgc
    # the bare surrogate bgc_id, a MIBiG accession with and without its version
    # suffix, and an assembly accession prefix must all resolve
    assert ids(client.get("/api/families?tier=all&q=00").json()) == ["FAM1"]
    assert ids(client.get("/api/families?tier=all&q=BGC0001280").json()) == ["FAM1"]
    assert ids(client.get("/api/families?tier=all&q=BGC0001280.1").json()) == ["FAM1"]
    assert ids(client.get("/api/families?tier=all&q=bgc0001280").json()) == ["FAM1"]
    assert ids(client.get("/api/families?tier=all&q=GCF_00000100").json()) == ["FAM1"]
    assert ids(client.get("/api/families?tier=all&q=GCF_001").json()) == ["FAM2"]


def test_families_mibig_filter(client):
    p = client.get("/api/families?tier=all&mibig=true&limit=200").json()
    assert set(ids(p)) == MIBIG_FAMILIES
    assert all(f["mibig"] for f in p["families"])
    # the accession is served without its version suffix
    assert all("." not in acc for f in p["families"] for acc in f["mibig"])
    assert p["families"][0]["mibig"] == [MIBIG_ACCESSION]


def test_families_min_bgcs(client):
    p = client.get("/api/families?tier=all&min_bgcs=300&limit=200").json()
    assert set(ids(p)) == {fid for fid, r in ALL_FAMILIES.items() if r["n_bgcs"] >= 300}
    assert all(f["n_bgcs"] >= 300 for f in p["families"])


def test_families_filters_combine(client):
    p = client.get("/api/families?tier=motif&class=NRP&limit=200").json()
    assert set(ids(p)) == {"FAM10"}


# ================================================================ /api/search
def test_search_by_family_id(client):
    s = client.get("/api/search?q=FAM1").json()
    assert set(s) == {"families", "bgcs"}
    assert [f["family_id"] for f in s["families"]] == ["FAM1"]


def test_search_by_bgc_id_and_free_text(client):
    assert [b["bgc_id"] for b in client.get("/api/search?q=00").json()["bgcs"]] == ["00"]
    s = client.get("/api/search?q=Streptomyces").json()
    assert s["families"] and s["bgcs"]
    assert set(s["bgcs"][0]) == {"bgc_id", "bgc_name", "family_id", "species",
                                 "length_nt", "n_cds"}


@pytest.mark.parametrize("q", ['"unbalanced', '"', 'a AND', 'NEAR(', '*', '^',
                               'a OR OR b', '.', ')', 'x:', '--', "O'Brien",
                               'foo NOT', '""', '{}', 'AND OR NOT'])
def test_search_survives_malformed_fts_syntax(client, q):
    """A bad MATCH raises sqlite3.OperationalError; it must not become a 500.

       The tokenizer and per-token quoting disarm these before FTS sees them;
       the contract under test is the status code, not which defence produced it.
       """
    r = client.get("/api/search", params={"q": q})
    assert r.status_code == 200, f"{q!r} -> {r.status_code} {r.text[:200]}"
    assert set(r.json()) == {"families", "bgcs"}


def test_search_requires_a_query(client):
    assert client.get("/api/search?q=").status_code == 422
    assert client.get("/api/search").status_code == 422
    assert client.get("/api/search?q=" + "x" * 201).status_code == 422
    assert client.get("/api/search?q=FAM1&limit=101").status_code == 422


def test_search_finds_nothing_gracefully(client):
    s = client.get("/api/search?q=Nothingosaurus").json()
    assert s == {"families": [], "bgcs": []}


# ================================================================ /api/family
def test_family_detail(client):
    p = client.get("/api/family/FAM1").json()
    assert set(p) == {"family", "cogs", "class_breakdown", "mibig"}
    assert p["family"]["family_id"] == "FAM1"
    assert p["cogs"] and set(p["cogs"][0]) == {
        "cog_id", "cog_name", "n_seqs", "conservation_rank", "has_meme", "pct_tf",
        "dominant_tf_family", "dominant_tf_best_evalue", "has_showcase", "color_rank"}
    # COG colouring is driven by color_rank, which is never null, even where
    # conservation_rank is
    assert p["cogs"][0]["conservation_rank"] is not None
    assert p["cogs"][0]["color_rank"] is not None
    assert p["class_breakdown"][0]["class"]


def test_family_with_no_gene_level_data_still_answers(client):
    """Most families have no COG or motif data at all -- an empty list, not a 404."""
    p = client.get("/api/family/FAM3").json()
    assert p["family"]["has_cog_data"] == 0
    assert p["cogs"] == []


def test_unknown_family_is_404(client):
    r = client.get("/api/family/FAM999999")
    assert r.status_code == 404
    assert "FAM999999" in r.json()["detail"]


def test_family_bgcs_with_cds_attached(client):
    p = client.get("/api/family/FAM1/bgcs").json()
    assert set(p) == {"total", "offset", "bgcs"}
    b = p["bgcs"][0]
    assert set(b) >= {"bgc_id", "bgc_name", "length_nt", "n_cds", "species",
                      "class", "products", "cds"}
    cds = b["cds"][0]
    assert set(cds) == {"bgc_id", "cds_id", "gene_key", "locus_tag",
                        "protein_id", "product", "nt_start", "nt_end", "strand",
                        "cog_id", "cog_is_propagated", "tf_family", "tf_evalue"}
    # gene_key is the join identity and is never empty, unlike locus_tag
    assert all(g["gene_key"] for bb in p["bgcs"] for g in bb["cds"])
    # a gene in no orthologous group keeps a NULL cog_id (it renders grey)
    assert any(g["cog_id"] is None for bb in p["bgcs"] for g in bb["cds"])


def test_family_bgcs_paging(client):
    whole = client.get("/api/family/FAM1/bgcs").json()
    page = client.get("/api/family/FAM1/bgcs?offset=1&limit=1").json()
    assert page["total"] == whole["total"] == 2
    assert len(page["bgcs"]) == 1
    assert page["bgcs"][0]["bgc_id"] == whole["bgcs"][1]["bgc_id"]


def test_bgcs_of_an_unknown_family_is_an_empty_page(client):
    p = client.get("/api/family/FAM999999/bgcs").json()
    assert p == {"total": 0, "offset": 0, "bgcs": []}


# ================================================================ /api/cog
def test_cog_motifs_shape(client):
    """Every motif row is zoops_maxw30; the showcase motif leads, then by E-value."""
    p = client.get("/api/cog/1/motifs").json()
    assert set(p) == {"cog", "motifs", "mibig"}
    assert p["cog"]["cog_id"] == 1
    assert p["motifs"][0]["is_showcase"] == 1, "the showcase motif leads"
    assert sum(m["is_showcase"] for m in p["motifs"]) == 1
    ev = [m["evalue"] for m in p["motifs"][1:]]
    assert ev == sorted(ev)
    assert p["mibig"], "mibig_xref rows belong on the COG"


def test_cog_motifs_carry_a_parsed_pwm_not_a_logo_path(client):
    m = client.get("/api/cog/1/motifs").json()["motifs"][0]
    assert "pwm" not in m and "logo_path" not in m
    pwm = m["pwm_parsed"]
    assert set(pwm) == {"width", "nsites", "evalue", "matrix"}
    assert pwm["matrix"] and all(len(row) == 4 for row in pwm["matrix"])


def test_cog_from_an_auto_created_group_has_no_colouring_but_still_answers(client):
    """Auto-created COGs (MEME output, no cog_stats row) lack n_seqs/rank."""
    p = client.get("/api/cog/5/motifs").json()
    assert p["cog"]["conservation_rank"] is None
    assert p["motifs"]


def test_unknown_cog_is_404(client):
    r = client.get("/api/cog/999999/motifs")
    assert r.status_code == 404 and "999999" in r.json()["detail"]


def test_cog_id_must_be_an_integer(client):
    """motif_id and cog_name are not unique -- the API only takes the surrogate."""
    assert client.get("/api/cog/COG_00001/motifs").status_code == 422


# ================================================================ Path B: TF
def test_tf_families(client):
    p = client.get("/api/tf/families").json()
    assert set(p) == {"tf_families"}
    f = p["tf_families"][0]
    assert set(f) == {"tf_family_id", "name", "n_ssn", "n_nodes", "n_families",
                      "n_prodoric", "n_ssn_min5", "max_nodes",
                      "n_ssn_with_motifs", "n_validated"}
    assert f["n_ssn"] >= f["n_ssn_with_motifs"] >= f["n_validated"]


def test_ssn_list(client):
    p = client.get("/api/ssn?min_nodes=1&limit=200").json()
    assert set(p) == {"total", "offset", "clusters"}
    c = p["clusters"][0]
    assert set(c) == {"ssn_id", "tf_family_id", "tf_family", "mcl_cluster",
                      "n_nodes", "n_families", "n_prodoric", "in_pipeline_pct",
                      "bgc_classes", "kingdoms", "top_phyla", "prodoric_tfs",
                      "n_motif_clusters", "n_motifs", "best_coverage"}
    # the pipe-joined summary columns come back as lists
    for k in ("bgc_classes", "kingdoms", "top_phyla", "prodoric_tfs"):
        assert isinstance(c[k], list)


def test_ssn_list_defaults_to_five_nodes(client):
    """The list hides clusters with fewer than 5 nodes by default."""
    assert client.get("/api/ssn").json()["total"] == client.get(
        "/api/ssn?min_nodes=5").json()["total"]
    assert all(c["n_nodes"] >= 5 for c in client.get("/api/ssn").json()["clusters"])
    assert client.get("/api/ssn?min_nodes=0").status_code == 422


def test_ssn_list_filters(client):
    only_motifs = client.get("/api/ssn?min_nodes=1&has_motifs=true").json()
    assert only_motifs["total"] >= 1
    assert all(c["n_motif_clusters"] > 0 for c in only_motifs["clusters"])
    only_prodoric = client.get("/api/ssn?min_nodes=1&has_prodoric=true").json()
    assert all(c["n_prodoric"] > 0 for c in only_prodoric["clusters"])
    by_family = client.get("/api/ssn?min_nodes=1&tf_family_id=1").json()
    assert all(c["tf_family_id"] == 1 for c in by_family["clusters"])
    assert client.get("/api/ssn?min_nodes=1&tf_family_id=999").json()["total"] == 0


def ids_of_ssn(payload) -> list[int]:
    return [c["ssn_id"] for c in payload["clusters"]]


def test_ssn_list_query_matches_only_cluster_regulator_and_phylum(client):
    """Three things and no more: the per-family mcl_cluster (never the ssn_id
       surrogate), a known regulator, a phylum."""
    p = client.get("/api/ssn?min_nodes=1&q=1").json()
    assert p["total"] == 1 and p["clusters"][0]["mcl_cluster"] == 1
    assert client.get("/api/ssn?min_nodes=1&q=cluster 1").json()["total"] == 1
    assert client.get("/api/ssn?min_nodes=1&q=OxyR").json()["total"] == 1
    assert client.get("/api/ssn?min_nodes=1&q=Actinobacteria").json()["total"] == 1
    assert client.get("/api/ssn?min_nodes=1&q=NoSuchThing").json()["total"] == 0
    # phylum matching is a substring, so "Bacteria" finds Actinobacteria and
    # Proteobacteria; top_phyla holds only phylum names, never the kingdom
    assert client.get("/api/ssn?min_nodes=1&q=Bacteria").json()["total"] == 2
    # not searched: family id, BGC class, member locus tag
    for gone in ("FAM1", "NRPS", "LT_BGC00_0"):
        assert client.get(f"/api/ssn?min_nodes=1&q={gone}").json()["total"] == 0, gone


@pytest.mark.parametrize("sort", ["nodes", "families", "prodoric", "motifs"])
def test_ssn_list_sorts(client, sort):
    p = client.get(f"/api/ssn?min_nodes=1&sort={sort}&limit=200").json()
    field = {"nodes": "n_nodes", "families": "n_families",
             "prodoric": "n_prodoric", "motifs": "n_motif_clusters"}[sort]
    assert_ordered([c[field] for c in p["clusters"]], "desc", f"ssn sort={sort}")


def test_ssn_list_rejects_an_unknown_sort(client):
    assert client.get("/api/ssn?sort=nope").status_code == 422


def test_ssn_detail(client):
    p = client.get("/api/ssn/1").json()
    assert set(p) == {"cluster", "n_motif_clusters", "motif_clusters",
                      "prodoric_anchors", "validation", "top_families", "taxa",
                      "n_member_families_with_motifs"}
    assert p["cluster"]["ssn_id"] == 1 and p["cluster"]["tf_family"] == "LysR"
    # every validation row says whether it counts as matched at Q_MATCH, so
    # the cluster page and the regulators table cannot disagree
    assert all(isinstance(v["matched"], bool) for v in p["validation"])
    # a db without rep_* would drop both keys instead of serving blanks
    rep = p["cluster"]["rep_aa_seq"]
    assert rep.startswith("MKT") and p["cluster"]["rep_locus_tag"]
    # never the PRODORIC anchor when a pipeline TF is available
    anchors = {a["mx_acc"] for a in p["prodoric_anchors"]}
    assert anchors and p["cluster"]["rep_locus_tag"] not in {
        "LT_2", "LT_3", "LT_4"}  # the seeded PRODORIC node pks
    mc = p["motif_clusters"][0]
    assert set(mc) == {"mc_id", "mcl_cluster", "n_motifs", "n_families_motif",
                       "n_families_ssn", "family_coverage", "n_cogs",
                       "is_best_for_ssn", "best_motif_pk", "pwm_parsed"}
    assert mc["pwm_parsed"]["matrix"]
    assert p["top_families"] and p["taxa"]


def test_ssn_detail_addressed_by_tf_name_and_mcl_cluster(client):
    """#ssn/{tf}/{mcl} is the public address; ssn_id is a build surrogate."""
    by_id = client.get("/api/ssn/1").json()
    assert client.get("/api/ssn/by/LysR/0").json() == by_id
    assert client.get("/api/ssn/by/lysr/0").json() == by_id      # COLLATE NOCASE
    assert by_id["cluster"]["mcl_cluster"] == 0 != by_id["cluster"]["ssn_id"]


def test_ssn_detail_caps_the_logos_it_parses(client):
    """Parsing PWMs is the expensive half of the response."""
    assert client.get("/api/ssn/1?logos=50").status_code == 200
    assert client.get("/api/ssn/1?logos=51").status_code == 422
    assert client.get("/api/ssn/by/LysR/0?logos=51").status_code == 422
    assert client.get("/api/ssn/1/motif-clusters?limit=101").status_code == 422
    assert client.get("/api/ssn/1/nodes?limit=201").status_code == 422
    assert client.get("/api/ssn?limit=201").status_code == 422
    assert client.get("/api/family/FAM1/bgcs?limit=101").status_code == 422


def test_unknown_ssn_is_404(client):
    assert client.get("/api/ssn/999999").status_code == 404
    assert client.get("/api/ssn/by/LysR/9999").status_code == 404
    assert client.get("/api/ssn/by/NoSuchFamily/0").status_code == 404


def test_ssn_nodes(client):
    p = client.get("/api/ssn/1/nodes").json()
    assert set(p) == {"total", "offset", "nodes"}
    n = p["nodes"][0]
    assert set(n) == {"node_pk", "is_prodoric", "family_id", "bgc_id", "locus_tag",
                      "uniprot", "mx_acc", "seq_len", "species", "genus", "phylum"}
    assert "aa_seq" not in n, "26k sequences are never returned in bulk"
    assert p["nodes"][0]["is_prodoric"] == 1, "PRODORIC anchors sort first"


def test_ssn_nodes_of_an_unknown_cluster_is_an_empty_page(client):
    assert client.get("/api/ssn/999999/nodes").json() == {
        "total": 0, "offset": 0, "nodes": []}


def test_ssn_motif_clusters(client):
    p = client.get("/api/ssn/1/motif-clusters").json()
    assert set(p) == {"total", "offset", "motif_clusters"}
    assert p["total"] == client.get("/api/ssn/1").json()["n_motif_clusters"]
    assert p["motif_clusters"][0]["pwm_parsed"]["matrix"]


def test_ssn_with_no_motif_clusters_has_an_empty_state(client):
    """Most SSN clusters carry no motif clusters."""
    p = client.get("/api/ssn/2").json()
    assert p["n_motif_clusters"] == 0 and p["motif_clusters"] == []
    assert client.get("/api/ssn/2/motif-clusters").json()["motif_clusters"] == []


def test_motif_cluster_detail(client):
    p = client.get("/api/motif-cluster/1").json()
    assert set(p) == {"motif_cluster", "members"}
    d = p["motif_cluster"]
    assert set(d) == {"mc_id", "ssn_id", "mcl_cluster", "n_motifs",
                      "n_families_motif", "n_families_ssn", "family_coverage",
                      "n_cogs", "families", "cogs", "is_best_for_ssn",
                      "best_motif_pk", "tf_family_id", "tf_family",
                      "ssn_mcl_cluster", "ssn_n_nodes", "pwm_parsed"}
    # the pipe-joined membership columns are split, not handed over raw
    assert d["families"] == ["FAM1", "FAM2"]
    assert d["cogs"] == ["COG_00001", "COG_00002"]
    assert len(p["members"]) == d["n_motifs"]
    m = p["members"][0]
    assert set(m) == {"motif_pk", "family_id", "cog_id", "cog_name",
                      "conservation_rank", "motif_number", "evalue",
                      "width", "consensus", "is_showcase", "frac_seqs_with_motif",
                      "is_best"}
    assert m["is_best"] == 1, "the cluster's best motif leads the member list"
    assert "pwm" not in m and "pwm_parsed" not in m


def test_motif_cluster_members_can_carry_pwms(client):
    p = client.get("/api/motif-cluster/1?with_pwm=true").json()
    assert all("pwm" not in m for m in p["members"])
    assert p["members"][0]["pwm_parsed"]["matrix"]


def test_unknown_motif_cluster_is_404(client):
    r = client.get("/api/motif-cluster/999999")
    assert r.status_code == 404 and "999999" in r.json()["detail"]


# ================================================================ PRODORIC
EXPECTED_STATUS = {"MX000001": "matched", "MX000004": "no_match",
                   "MX000005": "not_tested", "MX000002": "singleton",
                   "MX000003": "not_in_ssn"}
RANK = ["matched", "no_match", "not_tested", "singleton", "not_in_ssn"]


def test_prodoric_validation_status_ladder(client):
    p = client.get("/api/prodoric/validation?scope=all").json()
    assert set(p) == {"total", "q_match", "scope", "n_prodoric", "counts",
                      "n_in_ssn", "n_matched", "validation"}
    assert p["q_match"] == 0.1
    assert {r["mx_acc"]: r["status"] for r in p["validation"]} == EXPECTED_STATUS
    assert p["counts"] == {k: 1 for k in RANK}
    assert p["n_prodoric"] == 5 and p["n_in_ssn"] == 4 and p["n_matched"] == 1
    # matched first, then no_match, then the rest
    assert [RANK.index(r["status"]) for r in p["validation"]] == sorted(
        RANK.index(r["status"]) for r in p["validation"])


@pytest.mark.parametrize("scope,expect", [
    ("all", set(EXPECTED_STATUS)),
    ("cluster", {"MX000001", "MX000004", "MX000005", "MX000002"}),
    ("tested", {"MX000001", "MX000004"}),
    ("matched", {"MX000001"}),
])
def test_prodoric_validation_scopes(client, scope, expect):
    """The regulators page leads with the TFs that reached an SSN."""
    p = client.get(f"/api/prodoric/validation?scope={scope}").json()
    assert {r["mx_acc"] for r in p["validation"]} == expect
    assert p["total"] == len(expect)
    assert p["scope"] == scope
    # the counts always describe the whole set, whatever the scope shows
    assert p["n_prodoric"] == len(EXPECTED_STATUS)


def test_prodoric_validation_rejects_an_unknown_scope(client):
    assert client.get("/api/prodoric/validation?scope=everything").status_code == 422


def test_a_singleton_keeps_its_tf_family_despite_a_null_ssn_id(client):
    """MCL emits no 1-node clusters, so an unpaired node has ssn_id NULL and no
       route to ssn_cluster.tf_family_id."""
    p = client.get("/api/prodoric/validation?scope=cluster").json()
    single = next(r for r in p["validation"] if r["status"] == "singleton")
    assert single["ssn_id"] is None and single["mcl_cluster"] is None
    assert single["tf_family"] == "LysR", "the singleton lost its TF family"


def test_prodoric_validation_row_shape(client):
    r = next(r for r in client.get("/api/prodoric/validation").json()["validation"]
             if r["status"] == "matched")
    for k in ("mx_acc", "tf_name", "gene", "organism", "consensus", "best_qvalue",
              "n_motifs_tested", "n_motifs_matched", "family_coverage",
              "n_families_motif", "n_families_ssn", "tf_family", "mcl_cluster"):
        assert k in r
    assert r["best_qvalue"] <= 0.1
    # internal join scaffolding must not escape
    assert "node_pk" not in r and "node_tf_family_id" not in r


def test_prodoric_tf_detail(client):
    p = client.get("/api/prodoric/MX000001").json()
    assert set(p) == {"tf", "ssn_clusters", "validation"}
    assert p["tf"]["tf_name"] == "OxyR"
    assert p["ssn_clusters"] and p["validation"]


def test_prodoric_tf_detail_of_a_singleton(client):
    """The node's ssn_id is NULL, so the LEFT JOIN must not lose the row."""
    p = client.get("/api/prodoric/MX000002").json()
    assert p["tf"]["mx_acc"] == "MX000002"
    assert len(p["ssn_clusters"]) == 1 and p["ssn_clusters"][0]["ssn_id"] is None
    assert p["validation"] == []


def test_unknown_prodoric_is_404(client):
    r = client.get("/api/prodoric/MX999999")
    assert r.status_code == 404 and "MX999999" in r.json()["detail"]
    assert client.get("/api/prodoric/validation/nope").status_code == 404


def test_tf_family_is_derived_from_node_blocks_when_the_column_is_absent(
        client):
    """Without ssn_node.tf_family_id the app derives the family from contiguous
       node_pk blocks; the answers must be the same either way."""
    p = client.get("/api/prodoric/validation?scope=all").json()
    assert {r["mx_acc"]: r["status"] for r in p["validation"]} == EXPECTED_STATUS
    single = next(r for r in p["validation"] if r["status"] == "singleton")
    assert single["tf_family"] == "LysR"


# ================================================================ leak guard
LEAKY = ("logo_path", "/personal/", FAKE_HPC_BASE)


@pytest.mark.parametrize("url", API_URLS + [
    "/api/prodoric/MX000002", "/api/ssn/2", "/api/ssn/2/motif-clusters",
    "/api/cog/5/motifs", "/api/family/FAM3", "/api/family/FAM3/bgcs",
    "/api/families?tier=all&limit=200", "/api/families/facets",
])
def test_no_hpc_paths_leak(client, url):
    """HPC scratch paths contain a home directory; nothing may serve them."""
    body = client.get(url).text
    for needle in LEAKY:
        assert needle not in body, f"{url} leaked {needle!r}"


def test_the_leak_guard_can_actually_fail(client, fixture_db):
    """Sanity: the fixture holds a /personal/ path, so the sweep above is not
       passing because there is nothing to find."""
    import sqlite3

    c = sqlite3.connect(f"file:{fixture_db}?mode=ro", uri=True)
    base = c.execute("SELECT value FROM build_info WHERE key='base'").fetchone()[0]
    c.close()
    assert "/personal/" in base


# ================================================================ known holes
@pytest.mark.parametrize("url", [
    "/api/family/FAM1/bgcs?limit=-1",
    "/api/search?q=Streptomyces&limit=-1",
    "/api/ssn?limit=-1",
    "/api/ssn/1/nodes?limit=-1",
    "/api/ssn/1/motif-clusters?limit=-1",
])
def test_older_endpoints_should_also_reject_limit_minus_one(client, url):
    assert client.get(url).status_code == 422


@pytest.mark.parametrize("url", [
    "/api/family/FAM1/bgcs?offset=-1",
    "/api/ssn?offset=-1",
    "/api/ssn/1/nodes?offset=-1",
])
def test_older_endpoints_should_also_reject_a_negative_offset(client, url):
    assert client.get(url).status_code == 422


def test_color_rank_is_never_null_and_never_collides(client):
    """The colour key always has a value, and two groups never share a hue."""
    cogs = client.get("/api/family/FAM1").json()["cogs"]
    ranks = [c["color_rank"] for c in cogs]
    assert all(r is not None for r in ranks)
    assert len(set(ranks)) == len(ranks)
    for c in cogs:
        if c["conservation_rank"] is not None:
            assert c["color_rank"] == c["conservation_rank"]


def test_family_mibig_shape(client):
    """FAM1 holds a MIBiG reference cluster."""
    m = client.get("/api/family/FAM1").json()["mibig"]
    assert set(m) == {"bgcs"}
    assert m["bgcs"], "FAM1 holds a MIBiG cluster in the fixture"
    b = m["bgcs"][0]
    for k in ("bgc_name", "accession", "species", "class", "n_cds", "length_nt"):
        assert k in b, k
    # the stored name carries a version suffix; the bare accession is what
    # /go/ resolves, so it must be stripped
    assert "." not in b["accession"]
    assert b["bgc_name"].startswith(b["accession"])


def test_family_mibig_is_empty_not_absent_for_a_family_without_one(client):
    m = client.get("/api/family/FAM2").json()["mibig"]
    assert m["bgcs"] == [] or all(x["accession"].startswith("BGC") for x in m["bgcs"])
    assert isinstance(m["bgcs"], list)


def test_family_mibig_only_returns_mibig_bgcs(client, fixture_db):
    import sqlite3
    m = client.get("/api/family/FAM1").json()["mibig"]
    con = sqlite3.connect(f"file:{fixture_db}?mode=ro", uri=True)
    want = {r[0] for r in con.execute(
        "SELECT bgc_name FROM bgc WHERE family_id='FAM1' AND bgc_type='mibig'")}
    con.close()
    assert {b["bgc_name"] for b in m["bgcs"]} == want


def test_cog_motifs_carries_the_mibig_xref(client, fixture_db):
    """n_mibig_proteins counts proteins and mibig_bgc_names the distinct
       clusters they came from; the two can differ."""
    import sqlite3
    con = sqlite3.connect(f"file:{fixture_db}?mode=ro", uri=True)
    row = con.execute("SELECT cog_id FROM mibig_xref LIMIT 1").fetchone()
    con.close()
    if not row:
        pytest.skip("fixture has no mibig_xref rows")
    r = client.get(f"/api/cog/{row[0]}/motifs").json()
    assert r["mibig"], "the xref row must come back with the COG"
    x = r["mibig"][0]
    assert x["n_mibig_proteins"] >= 1
    assert x["mibig_bgc_names"], "the page derives its accessions from this"
    # comma-joined here, unlike motif_cluster which is pipe-joined
    assert "|" not in x["mibig_bgc_names"]


# ------------------------------------------------------------------- caching
@pytest.mark.parametrize("url", ["/", "/static/index.html", "/static/css/site.css",
                                 "/static/js/core.js", "/static/js/pages/family.js"])
def test_static_assets_must_revalidate(client, url):
    """No build step and no content hash in any filename, so a browser that
       caches without asking would serve stale JS after a deploy; StaticFiles
       alone sends an ETag but no Cache-Control."""
    r = client.get(url)
    assert r.status_code == 200
    assert r.headers.get("cache-control") == "no-cache"
    assert r.headers.get("etag"), "no-cache is only cheap if the ETag is there"


def test_unchanged_asset_revalidates_to_304(client):
    """no-cache must not mean re-download: an unchanged file costs an empty 304."""
    first = client.get("/static/js/core.js")
    again = client.get("/static/js/core.js",
                       headers={"If-None-Match": first.headers["etag"]})
    assert again.status_code == 304
    assert not again.content


def test_index_answers_head(client):
    """HEAD must answer 200; monitors and link checkers use it."""
    assert client.head("/").status_code == 200
