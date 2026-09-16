"""The pure functions behind the endpoints, where the edge cases are cheap.

Everything here depends on `app_module` so that the package is the one imported
against the fixture database, not whatever WEBSITE_DB the developer's shell has.
"""
from __future__ import annotations

import pytest

MEME = """MEME version 4
ALPHABET= ACGT
strands: + -
Background letter frequencies
A 0.25 C 0.25 G 0.25 T 0.25

MOTIF test
letter-probability matrix: alength= 4 w= 3 nsites= 41 E= 2.3e-17
0.10 0.20 0.30 0.40
0.40 0.30 0.20 0.10
0.25 0.25 0.25 0.25
"""


# ---------------------------------------------------------------- pwm.py
def test_parse_pwm_reads_header_and_matrix(app_module):
    from app.pwm import parse_pwm

    p = parse_pwm(MEME)
    assert p["width"] == 3
    assert p["nsites"] == 41
    assert p["evalue"] == "2.3e-17"
    assert p["matrix"] == [[0.1, 0.2, 0.3, 0.4], [0.4, 0.3, 0.2, 0.1],
                           [0.25, 0.25, 0.25, 0.25]]
    assert all(abs(sum(row) - 1.0) < 1e-9 for row in p["matrix"])


@pytest.mark.parametrize("text", [None, "", "MEME version 4\nALPHABET= ACGT\n",
                                  "letter-probability matrix: w= 2\n"])
def test_parse_pwm_returns_none_when_there_is_no_matrix(app_module, text):
    """motif.pwm is NULL for plenty of rows; the logo just does not render."""
    from app.pwm import parse_pwm

    assert parse_pwm(text) is None


def test_parse_pwm_ignores_trailing_non_numeric_lines(app_module):
    from app.pwm import parse_pwm

    p = parse_pwm(MEME + "\nURL http://example.org/motif\nsome other four words\n")
    assert p["width"] == 3 and len(p["matrix"]) == 3


def test_parse_pwm_falls_back_to_the_row_count(app_module):
    """A header with no w= still has to report a width."""
    from app.pwm import parse_pwm

    p = parse_pwm("letter-probability matrix: alength= 4\n0.1 0.2 0.3 0.4\n")
    assert p["width"] == 1 and p["nsites"] == 0 and p["evalue"] is None


# ---------------------------------------------------------------- db.py
def test_like_esc_neutralises_wildcards(app_module):
    """Locus tags are full of underscores, which LIKE reads as 'any character'."""
    from app.db import like_esc

    assert like_esc("METRZ18153_RS0101665") == "METRZ18153\\_RS0101665"
    assert like_esc("50%") == "50\\%"
    assert like_esc("a\\b") == "a\\\\b"


def test_hi_char_bounds_a_prefix_range(app_module):
    from app.db import HI_CHAR

    assert "BGC0001286.1" < "BGC" + HI_CHAR
    assert "BGD" > "BGC" + HI_CHAR          # the range stops at the prefix


# ---------------------------------------------------------------- constants
def test_class_tokens_are_the_closed_set_of_seven(app_module):
    from app.constants import CLASS_TOKENS, TIER_SQL

    assert set(CLASS_TOKENS) == {"NRP", "Polyketide", "Other", "Terpene", "RiPP",
                                 "Saccharide", "Alkaloid"}
    # one flag per tier, never an AND
    assert set(TIER_SQL) == {"motif", "cog", "tf"}
    assert all(" AND " not in sql for sql in TIER_SQL.values())


# ---------------------------------------------------------------- caches.py
def test_tf_family_of_node_maps_a_node_pk_to_its_block(app_module):
    """Each TF family owns a contiguous node_pk block, which is the only way to
       recover the family of a singleton once ssn_id is NULL."""
    from app.caches import ssn_family_blocks, tf_family_of_node

    blocks = ssn_family_blocks()
    assert blocks and all(len(b) == 2 for b in blocks)
    assert [lo for lo, _ in blocks] == sorted(lo for lo, _ in blocks)

    lo, fid = blocks[0]
    assert tf_family_of_node(lo) == fid
    assert tf_family_of_node(lo + 1000) == blocks[-1][1]
    assert tf_family_of_node(lo - 1) is None    # before every block
    assert tf_family_of_node(None) is None


def test_caches_are_stable_across_calls(app_module):
    """The db is opened read-only and never rebuilt, so these can be memoised."""
    from app.caches import family_facets, mibig_families, site_counts

    for fn in (site_counts, family_facets, mibig_families):
        assert fn() is fn()
