"""Property-based tests for the REGAIN skill taxonomy module.

Tests Properties 4, 5, and 6 from the Market Intelligence design document
using Hypothesis for property-based testing.

**Validates: Requirements 4.2, 4.3, 4.4, 4.6**
"""

import importlib
import string

from hypothesis import given, settings
from hypothesis import strategies as st

# 'lambda' is a Python keyword — use importlib to import the taxonomy module.
_taxonomy_mod = importlib.import_module("backend.handlers.market_intel.taxonomy")

TAXONOMY = _taxonomy_mod.TAXONOMY
ALIAS_INDEX = _taxonomy_mod.ALIAS_INDEX
normalize_skill = _taxonomy_mod.normalize_skill
serialize_taxonomy = _taxonomy_mod.serialize_taxonomy
deserialize_taxonomy = _taxonomy_mod.deserialize_taxonomy


# ---------------------------------------------------------------------------
# Property 4: Taxonomy alias completeness
# For any CanonicalSkill, onet_codes, job_posting_aliases, and user_aliases
# are non-empty.
# **Validates: Requirements 4.2**
# ---------------------------------------------------------------------------


@given(skill_name=st.sampled_from(sorted(TAXONOMY.keys())))
@settings(max_examples=100)
def test_property4_alias_completeness(skill_name: str) -> None:
    """Every canonical skill has at least one alias in each source."""
    skill = TAXONOMY[skill_name]
    assert len(skill.onet_codes) > 0, f"{skill_name} has empty onet_codes"
    assert len(skill.job_posting_aliases) > 0, f"{skill_name} has empty job_posting_aliases"
    assert len(skill.user_aliases) > 0, f"{skill_name} has empty user_aliases"


# ---------------------------------------------------------------------------
# Property 5: Taxonomy normalization and round-trip
# For any alias in the taxonomy, normalize returns correct canonical name;
# serialize then deserialize preserves all lookups.
# **Validates: Requirements 4.3, 4.6**
# ---------------------------------------------------------------------------


@given(alias=st.sampled_from(sorted(ALIAS_INDEX.keys())))
@settings(max_examples=100)
def test_property5_normalization(alias: str) -> None:
    """Normalizing any known alias returns the correct canonical name."""
    expected_canonical = ALIAS_INDEX[alias]
    result = normalize_skill(alias)
    assert result == expected_canonical, (
        f"normalize_skill({alias!r}) returned {result!r}, expected {expected_canonical!r}"
    )


@given(alias=st.sampled_from(sorted(ALIAS_INDEX.keys())))
@settings(max_examples=100)
def test_property5_normalization_case_insensitive(alias: str) -> None:
    """Normalization is case-insensitive — upper/mixed case aliases resolve."""
    expected_canonical = ALIAS_INDEX[alias]
    assert normalize_skill(alias.upper()) == expected_canonical
    assert normalize_skill(alias.title()) == expected_canonical


def test_property5_serialize_deserialize_roundtrip() -> None:
    """Serializing then deserializing preserves all alias lookups."""
    json_str = serialize_taxonomy()
    restored = deserialize_taxonomy(json_str)

    # Same set of canonical skill names
    assert set(restored.keys()) == set(TAXONOMY.keys())

    # Every alias still resolves to the same canonical name
    for canonical_name, skill in restored.items():
        original = TAXONOMY[canonical_name]
        assert skill.name == original.name
        assert skill.category == original.category
        assert skill.onet_codes == original.onet_codes
        assert skill.job_posting_aliases == original.job_posting_aliases
        assert skill.user_aliases == original.user_aliases


# ---------------------------------------------------------------------------
# Property 6: Taxonomy unmatched skills return None
# For any string not in ALIAS_INDEX, normalize_skill returns None.
# **Validates: Requirements 4.4**
# ---------------------------------------------------------------------------


@given(text=st.text(
    alphabet=string.ascii_letters + string.digits + " -_",
    min_size=1,
    max_size=60,
))
@settings(max_examples=100)
def test_property6_unmatched_returns_none(text: str) -> None:
    """Random strings not in the alias index return None."""
    if text.lower() in ALIAS_INDEX:
        # Skip strings that happen to be valid aliases
        return
    assert normalize_skill(text) is None
