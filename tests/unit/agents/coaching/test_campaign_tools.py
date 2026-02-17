"""Unit tests for get_campaign_status and create_campaign Strands tools.

Tests use moto-mocked DynamoDB via the shared dynamodb_tables fixture.
The @tool decorator from strands is stubbed since strands-agents is not
yet installed.
"""

import importlib
import sys
import types
from typing import Any, Dict

import pytest
from moto import mock_aws


# ---------------------------------------------------------------------------
# Stub the strands module so tools.py can be imported without strands-agents
# ---------------------------------------------------------------------------
_strands_stub = types.ModuleType("strands")
_strands_stub.tool = lambda fn: fn  # @tool is a no-op passthrough
sys.modules.setdefault("strands", _strands_stub)


def _load_tools(dynamodb_tables: Dict[str, Any]):
    """Import tools module with a fresh DynamoDBClient bound to moto tables."""
    mod_name = "backend.agents.coaching.tools"
    if mod_name in sys.modules:
        del sys.modules[mod_name]

    tools = importlib.import_module(mod_name)
    return tools


class TestGetCampaignStatus:
    """Tests for the get_campaign_status tool."""

    def test_returns_active_campaign(self, dynamodb_tables: Dict[str, Any]) -> None:
        """Querying a user with an active campaign returns the campaign dict."""
        table = dynamodb_tables["campaigns"]
        table.put_item(Item={
            "userId": "user-1",
            "campaignId": "campaign-abc",
            "title": "Transition to Data Engineer",
            "phase": "foundation",
            "status": "active",
            "startDate": "2025-01-15T09:00:00+00:00",
            "targetRole": "Data Engineer",
            "skillsFocus": ["python", "sql", "spark"],
        })

        tools = _load_tools(dynamodb_tables)
        result = tools.get_campaign_status("user-1")

        assert result["userId"] == "user-1"
        assert result["campaignId"] == "campaign-abc"
        assert result["title"] == "Transition to Data Engineer"
        assert result["phase"] == "foundation"
        assert result["status"] == "active"
        assert result["targetRole"] == "Data Engineer"
        assert result["skillsFocus"] == ["python", "sql", "spark"]

    def test_returns_error_when_no_active_campaign(self, dynamodb_tables: Dict[str, Any]) -> None:
        """Querying a user with no active campaign returns not_found error."""
        tools = _load_tools(dynamodb_tables)
        result = tools.get_campaign_status("user-no-campaign")

        assert result["error"] == "not_found"
        assert "user-no-campaign" in result["message"]

    def test_ignores_completed_campaigns(self, dynamodb_tables: Dict[str, Any]) -> None:
        """Only active campaigns are returned; completed ones are filtered out."""
        table = dynamodb_tables["campaigns"]
        table.put_item(Item={
            "userId": "user-2",
            "campaignId": "campaign-old",
            "title": "Old Campaign",
            "phase": "launch",
            "status": "completed",
            "startDate": "2024-06-01T00:00:00+00:00",
            "targetRole": "QA Engineer",
            "skillsFocus": ["testing"],
        })

        tools = _load_tools(dynamodb_tables)
        result = tools.get_campaign_status("user-2")

        assert result["error"] == "not_found"

    def test_returns_error_when_table_not_configured(self, aws_credentials: None) -> None:
        """Querying when the table env var is missing returns an error dict."""
        import os
        os.environ.pop("CAMPAIGNS_TABLE", None)

        tools = _load_tools({})
        result = tools.get_campaign_status("user-1")

        assert result["error"] in ("invalid_input", "read_failed")


class TestCreateCampaign:
    """Tests for the create_campaign tool."""

    def test_creates_campaign_with_correct_fields(self, dynamodb_tables: Dict[str, Any]) -> None:
        """Creating a campaign returns a dict with all expected fields."""
        tools = _load_tools(dynamodb_tables)
        result = tools.create_campaign(
            user_id="user-3",
            title="Pivot to ML Engineer",
            target_role="ML Engineer",
            skills_focus=["python", "pytorch", "mlops"],
        )

        assert result["userId"] == "user-3"
        assert result["title"] == "Pivot to ML Engineer"
        assert result["targetRole"] == "ML Engineer"
        assert result["skillsFocus"] == ["python", "pytorch", "mlops"]
        assert result["phase"] == "foundation"
        assert result["status"] == "active"
        assert result["campaignId"].startswith("campaign-")
        assert "startDate" in result

    def test_campaign_persists_in_dynamodb(self, dynamodb_tables: Dict[str, Any]) -> None:
        """Created campaign can be read back from DynamoDB."""
        tools = _load_tools(dynamodb_tables)
        created = tools.create_campaign(
            user_id="user-4",
            title="Career Shift",
            target_role="DevOps Engineer",
            skills_focus=["docker", "kubernetes"],
        )

        # Read it back via get_campaign_status
        result = tools.get_campaign_status("user-4")

        assert result["campaignId"] == created["campaignId"]
        assert result["title"] == "Career Shift"
        assert result["phase"] == "foundation"
        assert result["status"] == "active"

    def test_generates_unique_campaign_ids(self, dynamodb_tables: Dict[str, Any]) -> None:
        """Each campaign gets a unique campaign_id."""
        tools = _load_tools(dynamodb_tables)
        c1 = tools.create_campaign("user-5", "Campaign A", "Role A", ["skill_a"])
        c2 = tools.create_campaign("user-5", "Campaign B", "Role B", ["skill_b"])

        assert c1["campaignId"] != c2["campaignId"]

    def test_returns_error_when_table_not_configured(self, aws_credentials: None) -> None:
        """Creating when the table env var is missing returns an error dict."""
        import os
        os.environ.pop("CAMPAIGNS_TABLE", None)

        tools = _load_tools({})
        result = tools.create_campaign("user-1", "Title", "Role", ["skill"])

        assert result["error"] in ("invalid_input", "write_failed")
