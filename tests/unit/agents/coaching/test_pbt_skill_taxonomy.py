"""Property-based tests for skill taxonomy partitioning.

# Feature: coaching-agent, Property 2: Skill taxonomy partitioning

**Validates: Requirements 1.2**

For any set of extracted skills, classifying them into the Skill_Taxonomy
should produce exactly three non-overlapping categories (transferable_skills,
technical_skills, domain_knowledge) where the union of all three categories
equals the original skill set and no skill appears in more than one category.

Uses moto-mocked DynamoDB via the shared dynamodb_tables fixture.
The @tool decorator from strands is stubbed since strands-agents is not
yet installed.
"""

import importlib
import sys
import types
from typing import Any, Dict

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Stub the strands module so tools.py can be imported without strands-agents
# ---------------------------------------------------------------------------
_strands_stub = types.ModuleType("strands")
_strands_stub.tool = lambda fn: fn  # @tool is a no-op passthrough
sys.modules.setdefault("strands", _strands_stub)


def _load_tools():
    """Import tools module with a fresh DynamoDBClient bound to moto tables."""
    mod_name = "backend.agents.coaching.tools"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    return importlib.import_module(mod_name)


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Categories as written to DynamoDB (camelCase after normalization).
_TAXONOMY_CATEGORIES = ("transferableSkills", "technicalSkills", "domainKnowledge")

# User IDs: non-empty alphanumeric strings with dashes
_user_id_strategy = st.text(
    min_size=1,
    max_size=30,
    alphabet=st.characters(whitelist_categories=("L", "N", "Pd")),
)


@st.composite
def disjoint_skill_partition(draw):
    """Generate three disjoint skill lists that partition a pool of unique skills."""
    all_skills = draw(st.lists(
        st.text(
            min_size=1,
            max_size=20,
            alphabet=st.characters(whitelist_categories=("Ll",)),
        ),
        min_size=1,
        max_size=15,
        unique=True,
    ))
    transferable = []
    technical = []
    domain = []
    for skill in all_skills:
        bucket = draw(st.sampled_from(["t", "tech", "d"]))
        if bucket == "t":
            transferable.append(skill)
        elif bucket == "tech":
            technical.append(skill)
        else:
            domain.append(skill)
    return transferable, technical, domain, set(all_skills)


class TestSkillTaxonomyPartitioning:
    """Property 2: Skill taxonomy partitioning.

    For any set of extracted skills, storing them as three taxonomy
    categories via update_user_profile and reading them back via
    read_user_profile should produce exactly three non-overlapping
    categories whose union equals the original skill set.
    """

    @given(
        user_id=_user_id_strategy,
        partition=disjoint_skill_partition(),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_skill_taxonomy_forms_valid_partition(
        self,
        dynamodb_tables: Dict[str, Any],
        user_id: str,
        partition: tuple,
    ) -> None:
        """Three taxonomy categories are disjoint and their union equals the original set.

        # Feature: coaching-agent, Property 2: Skill taxonomy partitioning
        **Validates: Requirements 1.2**
        """
        transferable, technical, domain, original_set = partition

        # Seed a base profile so the user exists
        dynamodb_tables["user_profiles"].put_item(Item={
            "userId": user_id,
            "name": "Test User",
            "email": "[email]",
            "onboarding_completed": False,
        })

        tools = _load_tools()

        # Store the three taxonomy categories
        update_result = tools.update_user_profile(
            user_id=user_id,
            updates={
                "transferable_skills": transferable,
                "technical_skills": technical,
                "domain_knowledge": domain,
            },
        )
        assert "error" not in update_result, f"update_user_profile failed: {update_result}"

        # Read them back
        profile = tools.read_user_profile(user_id=user_id)
        assert "error" not in profile, f"read_user_profile failed: {profile}"

        # Extract the three categories from the profile (camelCase after
        # update_user_profile normalization).
        read_transferable = set(profile.get("transferableSkills", []))
        read_technical = set(profile.get("technicalSkills", []))
        read_domain = set(profile.get("domainKnowledge", []))

        # Assert: exactly three category keys exist in the profile
        for cat in _TAXONOMY_CATEGORIES:
            assert cat in profile, f"Missing taxonomy category '{cat}' in profile"

        # Assert: union of all three equals the original skill set
        union = read_transferable | read_technical | read_domain
        assert union == original_set, (
            f"Union mismatch: got {union}, expected {original_set}"
        )

        # Assert: pairwise disjoint (no skill in more than one category)
        assert read_transferable & read_technical == set(), (
            f"Overlap between transferable and technical: "
            f"{read_transferable & read_technical}"
        )
        assert read_transferable & read_domain == set(), (
            f"Overlap between transferable and domain: "
            f"{read_transferable & read_domain}"
        )
        assert read_technical & read_domain == set(), (
            f"Overlap between technical and domain: "
            f"{read_technical & read_domain}"
        )
