"""Property-based tests for mission generation round trip and structure.

# Feature: coaching-agent, Property 4: Mission generation round trip and structure

**Validates: Requirements 2.3, 7.2, 7.3**

For any valid mission parameters (user_id, campaign_id, title, description,
skill_tag), calling generate_mission should return a dict containing all
required keys (missionId, title, description, skillTag, status) with status
set to "pending", and subsequently calling get_current_mission for the same
user_id should return a mission with matching fields.

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

# User IDs: non-empty alphanumeric strings with dashes
_user_id_strategy = st.text(
    min_size=1,
    max_size=30,
    alphabet=st.characters(whitelist_categories=("L", "N", "Pd")),
)

# Campaign IDs: non-empty alphanumeric+dash strings prefixed with "campaign-"
_campaign_id_strategy = st.text(
    min_size=1,
    max_size=20,
    alphabet=st.characters(whitelist_categories=("L", "N", "Pd")),
).map(lambda s: f"campaign-{s}")

# Title: non-empty text strings
_title_strategy = st.text(
    min_size=1,
    max_size=60,
    alphabet=st.characters(whitelist_categories=("L", "N", "Zs")),
).filter(lambda s: s.strip())

# Description: non-empty text strings
_description_strategy = st.text(
    min_size=1,
    max_size=120,
    alphabet=st.characters(whitelist_categories=("L", "N", "Zs")),
).filter(lambda s: s.strip())

# Skill tag: non-empty lowercase alpha strings
_skill_tag_strategy = st.text(
    min_size=1,
    max_size=20,
    alphabet=st.characters(whitelist_categories=("Ll",)),
)


class TestMissionGenerationRoundTrip:
    """Property 4: Mission generation round trip and structure.

    For any valid mission parameters, generate_mission should return a dict
    with all required keys and status="pending", and get_current_mission
    should return a mission with matching fields.
    """

    @given(
        user_id=_user_id_strategy,
        campaign_id=_campaign_id_strategy,
        title=_title_strategy,
        description=_description_strategy,
        skill_tag=_skill_tag_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_generate_then_get_returns_matching_mission(
        self,
        dynamodb_tables: Dict[str, Any],
        user_id: str,
        campaign_id: str,
        title: str,
        description: str,
        skill_tag: str,
    ) -> None:
        """generate_mission then get_current_mission returns matching fields.

        # Feature: coaching-agent, Property 4: Mission generation round trip and structure
        **Validates: Requirements 2.3, 7.2, 7.3**
        """
        tools = _load_tools()

        # Clean up existing pending/in_progress missions for this user_id
        # to avoid stale data from prior examples
        mission_table = dynamodb_tables["mission_history"]
        existing = mission_table.query(
            KeyConditionExpression="userId = :uid",
            ExpressionAttributeValues={":uid": user_id},
        ).get("Items", [])
        for item in existing:
            if item.get("status") in ("pending", "in_progress"):
                mission_table.delete_item(
                    Key={"userId": item["userId"], "missionId": item["missionId"]}
                )

        # --- Act: generate a mission ---
        gen_result = tools.generate_mission(
            user_id=user_id,
            campaign_id=campaign_id,
            title=title,
            description=description,
            skill_tag=skill_tag,
        )

        # --- Assert: generate_mission returns no error ---
        assert "error" not in gen_result, f"generate_mission failed: {gen_result}"

        # --- Assert: returned dict has all required keys ---
        required_keys = {"missionId", "title", "description", "skillTag", "status", "campaignId"}
        assert required_keys.issubset(gen_result.keys()), (
            f"Missing keys: {required_keys - gen_result.keys()}"
        )

        # --- Assert: status is "pending" ---
        assert gen_result["status"] == "pending"

        # --- Assert: missionId starts with "mission-" ---
        assert gen_result["missionId"].startswith("mission-")

        # --- Act: read it back via get_current_mission ---
        get_result = tools.get_current_mission(user_id=user_id)

        # --- Assert: get_current_mission returns no error ---
        assert "error" not in get_result, f"get_current_mission failed: {get_result}"

        # --- Assert: returned mission has matching fields ---
        assert get_result["title"] == title
        assert get_result["description"] == description
        assert get_result["skillTag"] == skill_tag
        assert get_result["campaignId"] == campaign_id
