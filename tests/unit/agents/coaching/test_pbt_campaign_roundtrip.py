"""Property-based tests for campaign creation round trip.

# Feature: coaching-agent, Property 3: Campaign creation round trip

**Validates: Requirements 2.1, 2.2**

For any valid campaign parameters (user_id, title, target_role, skills_focus),
calling create_campaign followed by get_campaign_status for the same user_id
should return a campaign with matching title, target_role, skills_focus,
phase set to "foundation", and status set to "active".

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

# Title: non-empty text strings
_title_strategy = st.text(
    min_size=1,
    max_size=60,
    alphabet=st.characters(whitelist_categories=("L", "N", "Zs")),
).filter(lambda s: s.strip())

# Target role: non-empty text strings
_target_role_strategy = st.text(
    min_size=1,
    max_size=60,
    alphabet=st.characters(whitelist_categories=("L", "N", "Zs")),
).filter(lambda s: s.strip())

# Skills focus: lists of non-empty lowercase alpha strings (1-10 items)
_skills_focus_strategy = st.lists(
    st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("Ll",))),
    min_size=1,
    max_size=10,
)


class TestCampaignCreationRoundTrip:
    """Property 3: Campaign creation round trip.

    For any valid campaign parameters, create_campaign followed by
    get_campaign_status should return a campaign with matching fields,
    phase="foundation", and status="active".
    """

    @given(
        user_id=_user_id_strategy,
        title=_title_strategy,
        target_role=_target_role_strategy,
        skills_focus=_skills_focus_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_create_then_get_returns_matching_campaign(
        self,
        dynamodb_tables: Dict[str, Any],
        user_id: str,
        title: str,
        target_role: str,
        skills_focus: list,
    ) -> None:
        """create_campaign then get_campaign_status returns matching fields.

        # Feature: coaching-agent, Property 3: Campaign creation round trip
        **Validates: Requirements 2.1, 2.2**
        """
        tools = _load_tools()

        # Clean up any existing campaigns for this user_id from prior examples
        campaigns_table = dynamodb_tables["campaigns"]
        existing = campaigns_table.query(
            KeyConditionExpression="userId = :uid",
            ExpressionAttributeValues={":uid": user_id},
        ).get("Items", [])
        for item in existing:
            campaigns_table.delete_item(
                Key={"userId": item["userId"], "campaignId": item["campaignId"]}
            )

        # Create the campaign
        create_result = tools.create_campaign(
            user_id=user_id,
            title=title,
            target_role=target_role,
            skills_focus=skills_focus,
        )
        assert "error" not in create_result, f"create_campaign failed: {create_result}"

        # Read it back
        get_result = tools.get_campaign_status(user_id=user_id)
        assert "error" not in get_result, f"get_campaign_status failed: {get_result}"

        # Matching fields
        assert get_result["title"] == title
        assert get_result["targetRole"] == target_role
        assert get_result["skillsFocus"] == skills_focus

        # Phase and status defaults
        assert get_result["phase"] == "foundation"
        assert get_result["status"] == "active"

        # Campaign ID format
        assert get_result["campaignId"].startswith("campaign-")
