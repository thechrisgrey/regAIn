"""Unit tests for complete_mission and log_evidence tools.

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
    return importlib.import_module(mod_name)


def _seed_mission(dynamodb_tables: Dict[str, Any], user_id: str, mission_id: str) -> None:
    """Insert a pending mission into the mocked MissionHistory table."""
    dynamodb_tables["mission_history"].put_item(Item={
        "userId": user_id,
        "missionId": mission_id,
        "campaignId": "campaign-1",
        "title": "Test Mission",
        "description": "A test mission.",
        "status": "pending",
        "skillTag": "python",
        "createdAt": "2025-01-15T09:00:00+00:00",
    })


class TestLogEvidence:
    """Tests for the log_evidence tool."""

    def test_creates_evidence_with_correct_fields(self, dynamodb_tables: Dict[str, Any]) -> None:
        """Logging evidence returns evidence_id and skill_evidence_count."""
        tools = _load_tools(dynamodb_tables)
        result = tools.log_evidence(
            user_id="user-1",
            mission_id="mission-aaa",
            skill_tag="python",
            reflection="I wrote a script to automate testing.",
        )

        assert "evidence_id" in result
        assert result["evidence_id"].startswith("evidence-")
        assert result["skill_evidence_count"] == 1

    def test_count_increments_for_same_skill(self, dynamodb_tables: Dict[str, Any]) -> None:
        """Logging multiple evidence for the same skill increments the count."""
        tools = _load_tools(dynamodb_tables)

        r1 = tools.log_evidence("user-1", "m-1", "python", "First reflection")
        assert r1["skill_evidence_count"] == 1

        r2 = tools.log_evidence("user-1", "m-2", "python", "Second reflection")
        assert r2["skill_evidence_count"] == 2

        r3 = tools.log_evidence("user-1", "m-3", "python", "Third reflection")
        assert r3["skill_evidence_count"] == 3

    def test_different_skills_counted_separately(self, dynamodb_tables: Dict[str, Any]) -> None:
        """Evidence for different skill_tags have independent counts."""
        tools = _load_tools(dynamodb_tables)

        r1 = tools.log_evidence("user-1", "m-1", "python", "Python work")
        assert r1["skill_evidence_count"] == 1

        r2 = tools.log_evidence("user-1", "m-2", "networking", "Networking work")
        assert r2["skill_evidence_count"] == 1

    def test_different_users_counted_separately(self, dynamodb_tables: Dict[str, Any]) -> None:
        """Evidence counts are scoped per user."""
        tools = _load_tools(dynamodb_tables)

        r1 = tools.log_evidence("user-1", "m-1", "python", "User 1 work")
        assert r1["skill_evidence_count"] == 1

        r2 = tools.log_evidence("user-2", "m-2", "python", "User 2 work")
        assert r2["skill_evidence_count"] == 1

    def test_stores_artifact_url_when_provided(self, dynamodb_tables: Dict[str, Any]) -> None:
        """Evidence record includes artifactUrl when provided."""
        tools = _load_tools(dynamodb_tables)
        result = tools.log_evidence(
            user_id="user-1",
            mission_id="m-1",
            skill_tag="python",
            reflection="Built a portfolio site.",
            artifact_url="https://example.com/portfolio",
        )

        table = dynamodb_tables["evidence_vault"]
        response = table.get_item(Key={
            "userId": "user-1",
            "evidenceId": result["evidence_id"],
        })
        item = response["Item"]
        assert item["artifactUrl"] == "https://example.com/portfolio"

    def test_omits_artifact_url_when_empty(self, dynamodb_tables: Dict[str, Any]) -> None:
        """Evidence record does not include artifactUrl when not provided."""
        tools = _load_tools(dynamodb_tables)
        result = tools.log_evidence(
            user_id="user-1",
            mission_id="m-1",
            skill_tag="python",
            reflection="Practiced coding.",
        )

        table = dynamodb_tables["evidence_vault"]
        response = table.get_item(Key={
            "userId": "user-1",
            "evidenceId": result["evidence_id"],
        })
        item = response["Item"]
        assert "artifactUrl" not in item

    def test_persists_evidence_in_dynamodb(self, dynamodb_tables: Dict[str, Any]) -> None:
        """Evidence record is readable from DynamoDB after logging."""
        tools = _load_tools(dynamodb_tables)
        result = tools.log_evidence(
            user_id="user-1",
            mission_id="m-1",
            skill_tag="communication",
            reflection="Gave a presentation.",
        )

        table = dynamodb_tables["evidence_vault"]
        response = table.get_item(Key={
            "userId": "user-1",
            "evidenceId": result["evidence_id"],
        })
        item = response["Item"]
        assert item["skillTag"] == "communication"
        assert item["reflection"] == "Gave a presentation."
        assert item["missionId"] == "m-1"
        assert "createdAt" in item

    def test_returns_error_when_table_not_configured(self, aws_credentials: None) -> None:
        """Logging when the table env var is missing returns an error dict."""
        import os
        os.environ.pop("EVIDENCE_VAULT_TABLE", None)

        tools = _load_tools({})
        result = tools.log_evidence("u-1", "m-1", "s", "r")

        assert result["error"] in ("invalid_input", "write_failed")


class TestCompleteMission:
    """Tests for the complete_mission tool."""

    def test_updates_mission_status_to_completed(self, dynamodb_tables: Dict[str, Any]) -> None:
        """Completing a mission sets its status to 'completed' with a completedDate."""
        _seed_mission(dynamodb_tables, "user-1", "mission-aaa")
        tools = _load_tools(dynamodb_tables)

        tools.complete_mission(
            user_id="user-1",
            mission_id="mission-aaa",
            reflection="Learned a lot about testing.",
            skill_tag="python",
        )

        table = dynamodb_tables["mission_history"]
        response = table.get_item(Key={
            "userId": "user-1",
            "missionId": "mission-aaa",
        })
        item = response["Item"]
        assert item["status"] == "completed"
        assert "completedDate" in item

    def test_creates_evidence_record(self, dynamodb_tables: Dict[str, Any]) -> None:
        """Completing a mission creates an evidence record in the vault."""
        _seed_mission(dynamodb_tables, "user-1", "mission-bbb")
        tools = _load_tools(dynamodb_tables)

        result = tools.complete_mission(
            user_id="user-1",
            mission_id="mission-bbb",
            reflection="Wrote automated tests.",
            skill_tag="test_automation",
        )

        assert "evidence_id" in result
        assert result["evidence_id"].startswith("evidence-")
        assert result["skill_evidence_count"] == 1

    def test_returns_evidence_with_artifact_url(self, dynamodb_tables: Dict[str, Any]) -> None:
        """Completing a mission with an artifact_url passes it to evidence."""
        _seed_mission(dynamodb_tables, "user-1", "mission-ccc")
        tools = _load_tools(dynamodb_tables)

        result = tools.complete_mission(
            user_id="user-1",
            mission_id="mission-ccc",
            reflection="Published my portfolio.",
            skill_tag="portfolio",
            artifact_url="https://example.com/portfolio",
        )

        assert "evidence_id" in result

        table = dynamodb_tables["evidence_vault"]
        response = table.get_item(Key={
            "userId": "user-1",
            "evidenceId": result["evidence_id"],
        })
        assert response["Item"]["artifactUrl"] == "https://example.com/portfolio"

    def test_evidence_count_accumulates(self, dynamodb_tables: Dict[str, Any]) -> None:
        """Completing multiple missions for the same skill accumulates evidence count."""
        _seed_mission(dynamodb_tables, "user-1", "mission-d1")
        _seed_mission(dynamodb_tables, "user-1", "mission-d2")
        tools = _load_tools(dynamodb_tables)

        r1 = tools.complete_mission("user-1", "mission-d1", "First", "python")
        assert r1["skill_evidence_count"] == 1

        r2 = tools.complete_mission("user-1", "mission-d2", "Second", "python")
        assert r2["skill_evidence_count"] == 2

    def test_returns_error_when_table_not_configured(self, aws_credentials: None) -> None:
        """Completing when the table env var is missing returns an error dict."""
        import os
        os.environ.pop("MISSION_HISTORY_TABLE", None)

        tools = _load_tools({})
        result = tools.complete_mission("u-1", "m-1", "r", "s")

        assert result["error"] in ("invalid_input", "write_failed")
