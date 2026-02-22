"""Unit tests for skill tag normalization in log_evidence.

Verifies that log_evidence normalizes known aliases to canonical skill
names via the taxonomy module, preserves unknown tags as-is, and handles
case insensitivity.
"""

import importlib
import sys
import types
from typing import Any, Dict

import pytest


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


class TestSkillNormalizationInLogEvidence:
    """Tests for skill tag normalization in the log_evidence tool."""

    def test_normalizes_known_alias_to_canonical_name(
        self, dynamodb_tables: Dict[str, Any]
    ) -> None:
        """'python' should be normalized to 'Python Programming'."""
        tools = _load_tools(dynamodb_tables)
        result = tools.log_evidence(
            user_id="user-1",
            mission_id="m-1",
            skill_tag="python",
            reflection="I wrote a Python script.",
        )
        assert "evidence_id" in result

        # Verify the stored skillTag is the canonical name
        table = dynamodb_tables["evidence_vault"]
        response = table.get_item(Key={
            "userId": "user-1",
            "evidenceId": result["evidence_id"],
        })
        assert response["Item"]["skillTag"] == "Python Programming"

    def test_normalizes_case_insensitively(
        self, dynamodb_tables: Dict[str, Any]
    ) -> None:
        """'PYTHON' (uppercase) should also normalize to 'Python Programming'."""
        tools = _load_tools(dynamodb_tables)
        result = tools.log_evidence(
            user_id="user-1",
            mission_id="m-1",
            skill_tag="PYTHON",
            reflection="I used Python.",
        )

        table = dynamodb_tables["evidence_vault"]
        response = table.get_item(Key={
            "userId": "user-1",
            "evidenceId": result["evidence_id"],
        })
        assert response["Item"]["skillTag"] == "Python Programming"

    def test_normalizes_job_posting_alias(
        self, dynamodb_tables: Dict[str, Any]
    ) -> None:
        """'qa' should normalize to 'Quality Assurance'."""
        tools = _load_tools(dynamodb_tables)
        result = tools.log_evidence(
            user_id="user-1",
            mission_id="m-1",
            skill_tag="qa",
            reflection="I did QA testing.",
        )

        table = dynamodb_tables["evidence_vault"]
        response = table.get_item(Key={
            "userId": "user-1",
            "evidenceId": result["evidence_id"],
        })
        assert response["Item"]["skillTag"] == "Quality Assurance"

    def test_preserves_unknown_tags(
        self, dynamodb_tables: Dict[str, Any]
    ) -> None:
        """Unknown skill tags should be stored as-is without rejection."""
        tools = _load_tools(dynamodb_tables)
        result = tools.log_evidence(
            user_id="user-1",
            mission_id="m-1",
            skill_tag="quantum_computing_optimization",
            reflection="I explored quantum algorithms.",
        )

        table = dynamodb_tables["evidence_vault"]
        response = table.get_item(Key={
            "userId": "user-1",
            "evidenceId": result["evidence_id"],
        })
        assert response["Item"]["skillTag"] == "quantum_computing_optimization"

    def test_normalizes_user_alias(
        self, dynamodb_tables: Dict[str, Any]
    ) -> None:
        """'I code in java' (user alias) should normalize to 'Java Programming'."""
        tools = _load_tools(dynamodb_tables)
        result = tools.log_evidence(
            user_id="user-1",
            mission_id="m-1",
            skill_tag="I code in java",
            reflection="Built a Java application.",
        )

        table = dynamodb_tables["evidence_vault"]
        response = table.get_item(Key={
            "userId": "user-1",
            "evidenceId": result["evidence_id"],
        })
        assert response["Item"]["skillTag"] == "Java Programming"

    def test_complete_mission_also_normalizes(
        self, dynamodb_tables: Dict[str, Any]
    ) -> None:
        """complete_mission calls log_evidence internally, so normalization applies."""
        from unittest.mock import patch
        from backend.engine.models import CompletionResult, GateResult, GateCondition

        # Seed an in_progress mission (valid for completion transition)
        dynamodb_tables["mission_history"].put_item(Item={
            "userId": "user-1",
            "missionId": "mission-norm",
            "campaignId": "campaign-1",
            "title": "Test",
            "description": "Test",
            "status": "in_progress",
            "skillTag": "python",
            "createdAt": "2025-01-15T09:00:00+00:00",
        })

        mock_result = CompletionResult(
            mission_id="mission-norm",
            difficulty_change=None,
            gate_result=GateResult(
                passed=False,
                current_phase="foundation",
                next_phase=None,
                conditions={
                    "min_completed_missions": GateCondition(required=10, current=1, met=False),
                },
            ),
            behavioral_update={},
        )

        # Patch before loading tools so the import picks up the mock
        with patch("backend.engine.generator.complete_mission", return_value=mock_result):
            tools = _load_tools(dynamodb_tables)
            result = tools.complete_mission(
                user_id="user-1",
                mission_id="mission-norm",
                reflection="Wrote Python tests.",
                skill_tag="python",
            )

        assert "evidence_id" in result
        table = dynamodb_tables["evidence_vault"]
        response = table.get_item(Key={
            "userId": "user-1",
            "evidenceId": result["evidence_id"],
        })
        assert response["Item"]["skillTag"] == "Python Programming"

    def test_evidence_count_uses_normalized_tag(
        self, dynamodb_tables: Dict[str, Any]
    ) -> None:
        """Different aliases for the same skill converge to one canonical tag."""
        tools = _load_tools(dynamodb_tables)

        # "python" normalizes to "Python Programming"
        r1 = tools.log_evidence("user-1", "m-1", "python", "First")
        assert r1["skill_evidence_count"] == 1

        # "python3" also normalizes to "Python Programming"
        r2 = tools.log_evidence("user-1", "m-2", "python3", "Second")
        assert r2["skill_evidence_count"] == 2

        # "python programming" (lowercase) also normalizes to "Python Programming"
        r3 = tools.log_evidence("user-1", "m-3", "python programming", "Third")
        assert r3["skill_evidence_count"] == 3
