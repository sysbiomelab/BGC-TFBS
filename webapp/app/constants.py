"""Query fragments shared by more than one module: caches.family_facets() and
   the families router must use the same tier and class definitions.
"""
from __future__ import annotations

# dominant_class is a ", "-joined SET over these tokens ("NRP, Polyketide" and
# "Polyketide, NRP" are the same set), so the list is hardcoded, never derived
# with GROUP BY dominant_class.
CLASS_TOKENS = ["NRP", "Polyketide", "Other", "Terpene", "RiPP", "Saccharide", "Alkaloid"]
CLASS_RE = "^(" + "|".join(CLASS_TOKENS) + ")$"

# The has_* flags are NOT nested, so each tier is exactly one flag, never an AND.
TIER_SQL = {"motif": "f.has_motif_data = 1",
            "cog":   "f.has_cog_data = 1",
            "tf":    "f.has_tf_data = 1"}
