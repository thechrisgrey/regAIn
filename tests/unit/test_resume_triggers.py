"""Unit tests for async resume trigger non-blocking behavior.

Verifies that Lambda.invoke failures in _trigger_resume_generation
do not propagate to complete_mission, ensuring mission completion
always succeeds regardless of resume generation outcome.

Requirements: 5.3
"""

import dataclasses
import importlib
import json
import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

from backend.engine.models import CompletionResult, GateResult


# ---------------------------------------------------------------------------
# Module-level setup: ensure backend.agents.coaching.tools is importable
# by stubbing the 'strands' package that isn't installed in the test env.
# ---------------------------------------------------------------------------

_strands_stub = types.ModuleType("strands")
_strands_stub.tool = lambda fn: fn  # @tool is a no-op decorator in tests
if "strands" not in sys.modules:
    sys.modules["strands"] = _strands_stub


class TestAsyncTriggerNonBlocking:
    """Lambda.invoke failure must not block mission completion."""

    def test_complete_mission_succeeds_when_lambda_invoke_fails(self) -> None:
        """Mission completion returns a successful result even when
        the async resume Lambda invocation raises an exception."""
        os.environ["RESUME_LAMBDA_ARN"] = "arn:aws:lambda:us-east-1:123:function:resume"

        try:
            # Patch boto3 and engine dependencies inside the tools module
            with (
                patch("backend.agents.coaching.tools.boto3") as mock_boto3,
                patch("backend.agents.coaching.tools.engine_complete_mission") as mock_engine,
                patch("backend.agents.coaching.tools.log_evidence") as mock_log_ev,
            ):
                from backend.agents.coaching.tools import complete_mission

                # log_evidence succeeds
                mock_log_ev.return_value = {
                    "evidence_id": "ev-001",
                    "skill_evidence_count": 3,
                }

                # engine_complete_mission succeeds (no phase gate pass)
                gate = GateResult(passed=False, current_phase="foundation", next_phase=None)
                mock_engine.return_value = CompletionResult(
                    mission_id="m-001",
                    difficulty_change=None,
                    gate_result=gate,
                )

                # boto3.client("lambda").invoke raises
                mock_lambda_client = MagicMock()
                mock_lambda_client.invoke.side_effect = Exception("Lambda invoke failed")
                mock_boto3.client.return_value = mock_lambda_client

                result = complete_mission(
                    user_id="user-001",
                    mission_id="m-001",
                    reflection="Learned a lot",
                    skill_tag="Python",
                )

                # Result must be a successful completion dict, not an error
                assert "error" not in result, f"Expected success, got error: {result}"
                assert result["mission_id"] == "m-001"
                assert "gate_result" in result
                assert result["evidence_id"] == "ev-001"
        finally:
            os.environ.pop("RESUME_LAMBDA_ARN", None)

    def test_complete_mission_succeeds_when_phase_advancement_trigger_fails(self) -> None:
        """Mission completion succeeds even when the phase advancement
        resume trigger raises an exception."""
        os.environ["RESUME_LAMBDA_ARN"] = "arn:aws:lambda:us-east-1:123:function:resume"

        try:
            with (
                patch("backend.agents.coaching.tools.boto3") as mock_boto3,
                patch("backend.agents.coaching.tools.engine_complete_mission") as mock_engine,
                patch("backend.agents.coaching.tools.log_evidence") as mock_log_ev,
            ):
                from backend.agents.coaching.tools import complete_mission

                mock_log_ev.return_value = {
                    "evidence_id": "ev-002",
                    "skill_evidence_count": 5,
                }

                # Phase gate passes with next_phase in _RESUME_PHASE_TRIGGERS
                gate = GateResult(
                    passed=True,
                    current_phase="foundation",
                    next_phase="expansion",
                )
                mock_engine.return_value = CompletionResult(
                    mission_id="m-002",
                    difficulty_change={"skill_building": 2},
                    gate_result=gate,
                )

                # Both Lambda invocations fail
                mock_lambda_client = MagicMock()
                mock_lambda_client.invoke.side_effect = Exception("Connection timeout")
                mock_boto3.client.return_value = mock_lambda_client

                result = complete_mission(
                    user_id="user-002",
                    mission_id="m-002",
                    reflection="Built a full test suite",
                    skill_tag="Testing",
                )

                assert "error" not in result, f"Expected success, got error: {result}"
                assert result["mission_id"] == "m-002"
                assert result["gate_result"]["passed"] is True
                assert result["gate_result"]["next_phase"] == "expansion"
        finally:
            os.environ.pop("RESUME_LAMBDA_ARN", None)
