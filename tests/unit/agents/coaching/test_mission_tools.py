"""Unit tests for generate_mission and get_current_mission tools.

Tests use moto-mocked DynamoDB via the shared dynamodb_tables fixture.
The @tool decorator from strands is stubbed since strands-agents is not
yet installed.

generate_mission now delegates to the Mission Engine. We mock the engine
to isolate the tool layer.
"""

import importlib
import sys
import types
from typing import Any, Dict
from unittest.mock import patch, MagicMock
from dataclasses import asdict

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


def _make_generation_result():
    """Build a mock GenerationResult for testing."""
    from backend.engine.models import (
        GenerationResult, MissionCandidate, SkillGapReport,
    )
    primary = MissionCandidate(
        template_id="tmpl-reflect-1",
        category="reflection",
        title="Reflect on your Python experience",
        description="Write about three projects where you used Python.",
        rationale="Builds evidence for your strongest skill.",
        skill_tags=["python"],
        difficulty=1,
        estimated_minutes=20,
        expected_evidence_type="reflection",
        phase="foundation",
        market_relevance_score=0.8,
        priority_score=0.9,
    )
    alt1 = MissionCandidate(
        template_id="tmpl-skill-1",
        category="skill_building",
        title="Build a CLI tool",
        description="Create a small command-line tool.",
        rationale="Demonstrates practical coding ability.",
        skill_tags=["python", "cli"],
        difficulty=2,
        estimated_minutes=30,
        expected_evidence_type="artifact",
        phase="foundation",
        market_relevance_score=0.7,
        priority_score=0.8,
    )
    alt2 = MissionCandidate(
        template_id="tmpl-market-1",
        category="market_research",
        title="Research QA roles",
        description="Find 3 job postings for QA engineers.",
        rationale="Aligns your search with market demand.",
        skill_tags=["market_research"],
        difficulty=1,
        estimated_minutes=15,
        expected_evidence_type="research",
        phase="foundation",
        market_relevance_score=0.6,
        priority_score=0.7,
    )
    gap_report = SkillGapReport(
        skill_scores={"python": 0.8, "testing": 0.2},
        market_alignment_pct=45.0,
        priority_skills=["testing", "python"],
        evidence_density={"python": 3, "testing": 0},
    )
    return GenerationResult(primary=primary, alternates=[alt1, alt2], skill_gap_report=gap_report)


class TestGenerateMission:
    """Tests for the generate_mission tool (engine-backed)."""

    @patch("backend.engine.generator.generate_daily_mission")
    def test_returns_generation_result_as_dict(
        self, mock_gen, dynamodb_tables: Dict[str, Any]
    ) -> None:
        """generate_mission returns the engine's GenerationResult as a dict."""
        mock_gen.return_value = _make_generation_result()
        tools = _load_tools(dynamodb_tables)

        result = tools.generate_mission(user_id="user-1", campaign_id="campaign-abc")

        assert "primary" in result
        assert "alternates" in result
        assert "skill_gap_report" in result
        assert result["primary"]["title"] == "Reflect on your Python experience"
        assert len(result["alternates"]) == 2

    @patch("backend.engine.generator.generate_daily_mission")
    def test_returns_error_dict_from_engine(
        self, mock_gen, dynamodb_tables: Dict[str, Any]
    ) -> None:
        """generate_mission passes through engine error dicts."""
        mock_gen.return_value = {"error": "User profile not found for user_id=user-1"}
        tools = _load_tools(dynamodb_tables)

        result = tools.generate_mission(user_id="user-1", campaign_id="campaign-abc")

        assert "error" in result
        assert "User profile not found" in result["error"]

    @patch("backend.engine.generator.generate_daily_mission")
    def test_handles_engine_exception(
        self, mock_gen, dynamodb_tables: Dict[str, Any]
    ) -> None:
        """generate_mission catches engine exceptions and returns error dict."""
        mock_gen.side_effect = RuntimeError("DynamoDB throttled")
        tools = _load_tools(dynamodb_tables)

        result = tools.generate_mission(user_id="user-1", campaign_id="campaign-abc")

        assert result["error"] == "generation_failed"
        assert "DynamoDB throttled" in result["message"]

    @patch("backend.engine.generator.generate_daily_mission")
    def test_passes_db_to_engine(
        self, mock_gen, dynamodb_tables: Dict[str, Any]
    ) -> None:
        """generate_mission passes the module-level db client to the engine."""
        mock_gen.return_value = _make_generation_result()
        tools = _load_tools(dynamodb_tables)

        tools.generate_mission(user_id="user-1", campaign_id="campaign-abc")

        mock_gen.assert_called_once()
        call_kwargs = mock_gen.call_args
        assert call_kwargs.kwargs.get("db") is not None or (
            len(call_kwargs.args) >= 3 or "db" in call_kwargs.kwargs
        )

    @patch("backend.engine.generator.generate_daily_mission")
    def test_primary_has_all_mission_candidate_fields(
        self, mock_gen, dynamodb_tables: Dict[str, Any]
    ) -> None:
        """The primary mission dict includes all MissionCandidate fields."""
        mock_gen.return_value = _make_generation_result()
        tools = _load_tools(dynamodb_tables)

        result = tools.generate_mission(user_id="user-1", campaign_id="campaign-abc")

        primary = result["primary"]
        expected_fields = {
            "template_id", "category", "title", "description", "rationale",
            "skill_tags", "difficulty", "estimated_minutes",
            "expected_evidence_type", "phase", "market_relevance_score",
            "priority_score",
        }
        assert expected_fields.issubset(primary.keys())


class TestGetCurrentMission:
    """Tests for the get_current_mission tool."""

    def test_returns_pending_mission(self, dynamodb_tables: Dict[str, Any]) -> None:
        """get_current_mission returns a mission with pending status."""
        table = dynamodb_tables["mission_history"]
        table.put_item(Item={
            "userId": "user-1",
            "missionId": "mission-aaa",
            "campaignId": "campaign-1",
            "title": "Test Mission",
            "description": "A test mission.",
            "status": "pending",
            "skillTag": "python",
        })
        tools = _load_tools(dynamodb_tables)

        result = tools.get_current_mission(user_id="user-1")

        assert result["missionId"] == "mission-aaa"
        assert result["status"] == "pending"
        assert "patterns" in result

    def test_returns_in_progress_mission(self, dynamodb_tables: Dict[str, Any]) -> None:
        """get_current_mission returns a mission with in_progress status."""
        table = dynamodb_tables["mission_history"]
        table.put_item(Item={
            "userId": "user-1",
            "missionId": "mission-bbb",
            "campaignId": "campaign-1",
            "title": "Active Mission",
            "description": "An active mission.",
            "status": "in_progress",
            "skillTag": "networking",
        })
        tools = _load_tools(dynamodb_tables)

        result = tools.get_current_mission(user_id="user-1")

        assert result["missionId"] == "mission-bbb"
        assert result["status"] == "in_progress"

    def test_ignores_completed_missions(self, dynamodb_tables: Dict[str, Any]) -> None:
        """get_current_mission does not return completed missions."""
        table = dynamodb_tables["mission_history"]
        table.put_item(Item={
            "userId": "user-1",
            "missionId": "mission-done",
            "campaignId": "campaign-1",
            "title": "Done Mission",
            "description": "Already done.",
            "status": "completed",
            "skillTag": "python",
        })
        tools = _load_tools(dynamodb_tables)

        result = tools.get_current_mission(user_id="user-1")

        assert result["error"] == "not_found"

    def test_returns_error_when_no_missions(self, dynamodb_tables: Dict[str, Any]) -> None:
        """get_current_mission returns error when user has no missions."""
        tools = _load_tools(dynamodb_tables)

        result = tools.get_current_mission(user_id="user-no-missions")

        assert result["error"] == "not_found"

    def test_returns_error_when_table_not_configured(self, aws_credentials: None) -> None:
        """get_current_mission returns error when table env var is missing."""
        import os
        os.environ.pop("MISSION_HISTORY_TABLE", None)

        tools = _load_tools({})
        result = tools.get_current_mission(user_id="user-1")

        assert result["error"] in ("invalid_input", "read_failed")


class TestAnalyzePatterns:
    """Tests for the _analyze_patterns helper function."""

    def test_empty_list_returns_zero_counts(self, dynamodb_tables: Dict[str, Any]) -> None:
        """Empty mission list produces zero counts and no signals."""
        tools = _load_tools(dynamodb_tables)
        result = tools._analyze_patterns([])

        assert result["total_missions"] == 0
        assert result["completed"] == 0
        assert result["skipped"] == 0
        assert result["avoidance_signals"] == []
        assert result["strength_signals"] == []

    def test_all_completed_single_category(self, dynamodb_tables: Dict[str, Any]) -> None:
        """All completed missions in one category produces a strength signal."""
        tools = _load_tools(dynamodb_tables)
        missions = [
            {"status": "completed", "skillTag": "python"},
            {"status": "completed", "skillTag": "python"},
            {"status": "completed", "skillTag": "python"},
        ]
        result = tools._analyze_patterns(missions)

        assert result["completed"] == 3
        assert result["skipped"] == 0
        assert "python" in result["strength_signals"]
        assert result["avoidance_signals"] == []

    def test_all_skipped_single_category(self, dynamodb_tables: Dict[str, Any]) -> None:
        """All skipped missions in one category produces an avoidance signal."""
        tools = _load_tools(dynamodb_tables)
        missions = [
            {"status": "skipped", "skillTag": "networking"},
            {"status": "skipped", "skillTag": "networking"},
        ]
        result = tools._analyze_patterns(missions)

        assert result["skipped"] == 2
        assert "networking" in result["avoidance_signals"]

    def test_mixed_statuses_multiple_categories(self, dynamodb_tables: Dict[str, Any]) -> None:
        """Mixed statuses across categories produce correct signals."""
        tools = _load_tools(dynamodb_tables)
        missions = [
            {"status": "completed", "skillTag": "python"},
            {"status": "completed", "skillTag": "python"},
            {"status": "skipped", "skillTag": "networking"},
            {"status": "skipped", "skillTag": "networking"},
            {"status": "skipped", "skillTag": "networking"},
            {"status": "completed", "skillTag": "networking"},
        ]
        result = tools._analyze_patterns(missions)

        assert result["completed"] == 3
        assert result["skipped"] == 3
        assert "python" in result["strength_signals"]

    def test_avoidance_threshold_just_above_50_percent(self, dynamodb_tables: Dict[str, Any]) -> None:
        """Category with >50% skip rate is flagged as avoidance."""
        tools = _load_tools(dynamodb_tables)
        missions = [
            {"status": "skipped", "skillTag": "public_speaking"},
            {"status": "skipped", "skillTag": "public_speaking"},
            {"status": "completed", "skillTag": "public_speaking"},
        ]
        result = tools._analyze_patterns(missions)

        assert "public_speaking" in result["avoidance_signals"]

    def test_exactly_50_percent_skip_rate_not_avoidance(self, dynamodb_tables: Dict[str, Any]) -> None:
        """Category with exactly 50% skip rate is NOT flagged as avoidance."""
        tools = _load_tools(dynamodb_tables)
        missions = [
            {"status": "skipped", "skillTag": "writing"},
            {"status": "completed", "skillTag": "writing"},
        ]
        result = tools._analyze_patterns(missions)

        assert "writing" not in result["avoidance_signals"]

    def test_pending_only_category_no_signals(self, dynamodb_tables: Dict[str, Any]) -> None:
        """Category with only pending missions produces no signals."""
        tools = _load_tools(dynamodb_tables)
        missions = [
            {"status": "pending", "skillTag": "design"},
        ]
        result = tools._analyze_patterns(missions)

        assert result["avoidance_signals"] == []
        assert result["strength_signals"] == []

    def test_missing_skill_tag_defaults_to_unknown(self, dynamodb_tables: Dict[str, Any]) -> None:
        """Missions without skillTag are bucketed under 'unknown'."""
        tools = _load_tools(dynamodb_tables)
        missions = [
            {"status": "completed"},
        ]
        result = tools._analyze_patterns(missions)

        assert "unknown" in result["by_category"]
