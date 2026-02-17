"""Unit tests for complete_mission and log_evidence tools.

Tests use moto-mocked DynamoDB via the shared dynamodb_tables fixture.
The @tool decorator from strands is stubbed since strands-agents is not
yet installed.

complete_mission now delegates to the Mission Engine after logging evidence.
We mock the engine to isolate the tool layer.
"""

import importlib
import sys
import types
from typing import Any, Dict
from unittest.mock import patch

import pytest
from moto import mock_aws

from backend.engine.models import (
    CompletionResult, GateResult, GateCondition,
)


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


def _make_completion_result(mission_id: str) -> CompletionResult:
    """Build a CompletionResult for testing."""
    return CompletionResult(
        mission_id=mission_id,
        difficulty_change=None,
        gate_result=GateResult(
            passed=False,
            current_phase="foundation",
            next_phase=None,
            conditions={
                "min_completed_missions": GateCondition(required=10, current=1, met=False),
            },
        ),
        behavioral_update={
            "category": "reflection",
            "outcome": "completed",
            "new_difficulty_state": {},
        },
    )


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
    """Tests for the complete_mission tool (engine-backed)."""

    @patch("backend.engine.generator.complete_mission")
    def test_logs_evidence_and_delegates_to_engine(
        self, mock_complete, dynamodb_tables: Dict[str, Any]
    ) -> None:
        """complete_mission logs evidence first, then calls the engine."""
        _seed_mission(dynamodb_tables, "user-1", "mission-aaa")
        mock_complete.return_value = _make_completion_result("mission-aaa")
        tools = _load_tools(dynamodb_tables)

        result = tools.complete_mission(
            user_id="user-1",
            mission_id="mission-aaa",
            reflection="Learned a lot about testing.",
            skill_tag="python",
        )

        assert "evidence_id" in result
        assert "mission_id" in result
        assert "gate_result" in result
        mock_complete.assert_called_once()

    @patch("backend.engine.generator.complete_mission")
    def test_returns_evidence_id_and_count(
        self, mock_complete, dynamodb_tables: Dict[str, Any]
    ) -> None:
        """complete_mission includes evidence_id and skill_evidence_count."""
        _seed_mission(dynamodb_tables, "user-1", "mission-bbb")
        mock_complete.return_value = _make_completion_result("mission-bbb")
        tools = _load_tools(dynamodb_tables)

        result = tools.complete_mission(
            user_id="user-1",
            mission_id="mission-bbb",
            reflection="Wrote automated tests.",
            skill_tag="test_automation",
        )

        assert result["evidence_id"].startswith("evidence-")
        assert result["skill_evidence_count"] == 1

    @patch("backend.engine.generator.complete_mission")
    def test_passes_evidence_ids_to_engine(
        self, mock_complete, dynamodb_tables: Dict[str, Any]
    ) -> None:
        """complete_mission passes the logged evidence_id to the engine."""
        _seed_mission(dynamodb_tables, "user-1", "mission-ccc")
        mock_complete.return_value = _make_completion_result("mission-ccc")
        tools = _load_tools(dynamodb_tables)

        result = tools.complete_mission(
            user_id="user-1",
            mission_id="mission-ccc",
            reflection="Published my portfolio.",
            skill_tag="portfolio",
            artifact_url="https://example.com/portfolio",
        )

        call_kwargs = mock_complete.call_args
        evidence_ids = call_kwargs.kwargs.get("evidence_ids") or call_kwargs[1].get("evidence_ids", [])
        assert len(evidence_ids) == 1
        assert evidence_ids[0].startswith("evidence-")

    @patch("backend.engine.generator.complete_mission")
    def test_returns_engine_error_dict(
        self, mock_complete, dynamodb_tables: Dict[str, Any]
    ) -> None:
        """complete_mission passes through engine error dicts."""
        _seed_mission(dynamodb_tables, "user-1", "mission-ddd")
        mock_complete.return_value = {"error": "Mission not found for mission_id=mission-ddd"}
        tools = _load_tools(dynamodb_tables)

        result = tools.complete_mission(
            user_id="user-1",
            mission_id="mission-ddd",
            reflection="Test",
            skill_tag="python",
        )

        assert "error" in result

    @patch("backend.engine.generator.complete_mission")
    def test_handles_engine_exception(
        self, mock_complete, dynamodb_tables: Dict[str, Any]
    ) -> None:
        """complete_mission catches engine exceptions and returns error dict."""
        _seed_mission(dynamodb_tables, "user-1", "mission-eee")
        mock_complete.side_effect = RuntimeError("DynamoDB throttled")
        tools = _load_tools(dynamodb_tables)

        result = tools.complete_mission(
            user_id="user-1",
            mission_id="mission-eee",
            reflection="Test",
            skill_tag="python",
        )

        assert result["error"] == "completion_failed"
        assert "DynamoDB throttled" in result["message"]
