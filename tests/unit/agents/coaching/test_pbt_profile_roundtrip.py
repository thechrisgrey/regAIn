"""Property-based tests for profile update round trip.

# Feature: coaching-agent, Property 1: Profile update round trip

**Validates: Requirements 1.4**

For any valid Transition Profile dict containing skills, experience_years,
industry, and role_history fields, calling update_user_profile followed by
read_user_profile for the same user_id should return a profile containing
all the updated fields with equivalent values.

Uses moto-mocked DynamoDB via the shared dynamodb_tables fixture.
The @tool decorator from strands is stubbed since strands-agents is not
yet installed.
"""

import importlib
import sys
import types
from typing import Any, Dict

import pytest
from hypothesis import given, settings, assume, HealthCheck
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

# User IDs: non-empty alphanumeric strings with dashes
_user_id_strategy = st.text(
    min_size=1,
    max_size=30,
    alphabet=st.characters(whitelist_categories=("L", "N", "Pd")),
)

# Skills: lists of lowercase alpha strings (1-10 items)
_skill_strategy = st.lists(
    st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("Ll",))),
    min_size=1,
    max_size=10,
)

# Experience years: integers 0-50
_experience_years_strategy = st.integers(min_value=0, max_value=50)

# Industry: non-empty text strings
_industry_strategy = st.text(
    min_size=1,
    max_size=40,
    alphabet=st.characters(whitelist_categories=("L", "N", "Zs")),
).filter(lambda s: s.strip())

# Role history: lists of non-empty text strings (1-5 items)
_role_history_strategy = st.lists(
    st.text(
        min_size=1,
        max_size=40,
        alphabet=st.characters(whitelist_categories=("L", "N", "Zs")),
    ).filter(lambda s: s.strip()),
    min_size=1,
    max_size=5,
)


class TestProfileUpdateRoundTrip:
    """Property 1: Profile update round trip.

    For any valid Transition Profile dict, update_user_profile followed
    by read_user_profile should return a profile containing all updated
    fields with equivalent values.
    """

    @given(
        user_id=_user_id_strategy,
        skills=_skill_strategy,
        experience_years=_experience_years_strategy,
        industry=_industry_strategy,
        role_history=_role_history_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_update_then_read_preserves_all_fields(
        self,
        dynamodb_tables: Dict[str, Any],
        user_id: str,
        skills: list,
        experience_years: int,
        industry: str,
        role_history: list,
    ) -> None:
        """update_user_profile then read_user_profile returns equivalent fields.

        # Feature: coaching-agent, Property 1: Profile update round trip
        **Validates: Requirements 1.4**
        """
        # Seed a base profile so the user exists in the table
        dynamodb_tables["user_profiles"].put_item(Item={
            "userId": user_id,
            "name": "Test User",
            "email": "[email]",
            "onboarding_completed": False,
        })

        tools = _load_tools()

        updates = {
            "skills": skills,
            "experience_years": experience_years,
            "industry": industry,
            "role_history": role_history,
        }

        # Update the profile
        update_result = tools.update_user_profile(user_id=user_id, updates=updates)
        assert "error" not in update_result, f"update_user_profile failed: {update_result}"

        # Read it back
        read_result = tools.read_user_profile(user_id=user_id)
        assert "error" not in read_result, f"read_user_profile failed: {read_result}"

        # Assert all updated fields are present with equivalent values
        assert read_result["skills"] == skills
        assert read_result["experience_years"] == experience_years
        assert read_result["industry"] == industry
        assert read_result["role_history"] == role_history

        # Original fields should also be preserved
        assert read_result["userId"] == user_id
        assert read_result["name"] == "Test User"
