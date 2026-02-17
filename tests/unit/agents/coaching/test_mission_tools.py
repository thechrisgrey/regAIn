"""Unit tests for get_current_mission, generate_mission, and _analyze_patterns.

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


class TestGenerateMission:
    """Tests for the generate_mission tool."""

    def test_creates_mission_with_correct_fields(self, dynamodb_tables: Dict[str, Any]) -> None:
        """Creating a mission returns a dict with all expected fields."""
        tools = _load_tools(dynamodb_tables)
        result = tools.generate_mission(
            user_id="user-1",
            campaign_id="campaign-abc",
            title="Document Your Testing Methodology",
            description="Write down three times you caught a critical bug.",
            skill_tag="systematic_debugging",
        )

        assert result["userId"] == "user-1"
        assert result["campaignId"] == "campaign-abc"
        assert result["title"] == "Document Your Testing Methodology"
        assert result["description"] == "Write down three times you caught a critical bug."
        assert result["skillTag"] == "systematic_debugging"
        assert result["status"] == "pending"
        assert result["missionId"].startswith("mission-")
        assert "createdAt" in result

    def test_generates_unique_mission_ids(self, dynamodb_tables: Dict[str, Any]) -> None:
        """Each mission gets a unique mission_id."""
        tools = _load_tools(dynamodb_tables)
        m1 = tools.generate_mission("user-1", "c-1", "Mission A", "Do A", "skill_a")
        m2 = tools.generate_mission("user-1", "c-1", "Mission B", "Do B", "skill_b")

        assert m1["missionId"] != m2["missionId"]

    def test_mission_persists_in_dynamodb(self, dynamodb_tables: Dict[str, Any]) -> None:
        """Created mission can be read back from DynamoDB."""
        tools = _load_tools(dynamodb_tables)
        created = tools.generate_mission(
            user_id="user-2",
            campaign_id="campaign-xyz",
            title="Network with a peer",
            description="Reach out to one person in your target field.",
            skill_tag="networking",
        )

        # Read it back directly from the table
        table = dynamodb_tables["mission_history"]
        response = table.get_item(Key={
            "userId": "user-2",
            "missionId": created["missionId"],
        })
        item = response["Item"]

        assert item["title"] == "Network with a peer"
        assert item["status"] == "pending"
        assert item["skillTag"] == "networking"

    def test_returns_error_when_table_not_configured(self, aws_credentials: None) -> None:
        """Creating when the table env var is missing returns an error dict."""
        import os
        os.environ.pop("MISSION_HISTORY_TABLE", None)

        tools = _load_tools({})
        result = tools.generate_mission("u-1", "c-1", "T", "D", "s")

        assert result["error"] in ("invalid_input", "write_failed")


class TestGetCurrentMission:
    """Tests for the get_current_mission tool."""

    def test_returns_pending_mission(self, dynamodb_tables: Dict[str, Any]) -> None:
        """Querying a user with a pending mission returns it."""
        table = dynamodb_tables["mission_history"]
        table.put_item(Item={
            "userId": "user-1",
            "missionId": "mission-aaa",
            "campaignId": "campaign-1",
            "title": "Quick Win",
            "description": "Do something small.",
            "status": "pending",
            "skillTag": "communication",
            "createdAt": "2025-01-15T09:00:00+00:00",
        })

        tools = _load_tools(dynamodb_tables)
        result = tools.get_current_mission("user-1")

        assert result["missionId"] == "mission-aaa"
        assert result["status"] == "pending"
        assert "patterns" in result

    def test_returns_in_progress_mission(self, dynamodb_tables: Dict[str, Any]) -> None:
        """Querying a user with an in_progress mission returns it."""
        table = dynamodb_tables["mission_history"]
        table.put_item(Item={
            "userId": "user-2",
            "missionId": "mission-bbb",
            "campaignId": "campaign-2",
            "title": "Stretch Goal",
            "description": "Push your limits.",
            "status": "in_progress",
            "skillTag": "python",
            "createdAt": "2025-01-16T09:00:00+00:00",
        })

        tools = _load_tools(dynamodb_tables)
        result = tools.get_current_mission("user-2")

        assert result["missionId"] == "mission-bbb"
        assert result["status"] == "in_progress"

    def test_ignores_completed_missions(self, dynamodb_tables: Dict[str, Any]) -> None:
        """Only pending/in_progress missions are returned as current."""
        table = dynamodb_tables["mission_history"]
        table.put_item(Item={
            "userId": "user-3",
            "missionId": "mission-done",
            "campaignId": "campaign-3",
            "title": "Old Mission",
            "description": "Already done.",
            "status": "completed",
            "skillTag": "testing",
            "createdAt": "2025-01-10T09:00:00+00:00",
        })

        tools = _load_tools(dynamodb_tables)
        result = tools.get_current_mission("user-3")

        assert result["error"] == "not_found"
        assert "patterns" in result

    def test_returns_error_when_no_missions(self, dynamodb_tables: Dict[str, Any]) -> None:
        """Querying a user with no missions returns not_found with patterns."""
        tools = _load_tools(dynamodb_tables)
        result = tools.get_current_mission("user-no-missions")

        assert result["error"] == "not_found"
        assert "patterns" in result

    def test_returns_error_when_table_not_configured(self, aws_credentials: None) -> None:
        """Querying when the table env var is missing returns an error dict."""
        import os
        os.environ.pop("MISSION_HISTORY_TABLE", None)

        tools = _load_tools({})
        result = tools.get_current_mission("user-1")

        assert result["error"] in ("invalid_input", "read_failed")


class TestAnalyzePatterns:
    """Tests for the _analyze_patterns helper function."""

    def test_empty_list_returns_zero_counts(self, dynamodb_tables: Dict[str, Any]) -> None:
        """Empty mission list returns zeroed-out analysis with no signals."""
        tools = _load_tools(dynamodb_tables)
        result = tools._analyze_patterns([])

        assert result["total_missions"] == 0
        assert result["completed"] == 0
        assert result["skipped"] == 0
        assert result["pending"] == 0
        assert result["in_progress"] == 0
        assert result["by_category"] == {}
        assert result["avoidance_signals"] == []
        assert result["strength_signals"] == []

    def test_all_completed_single_category(self, dynamodb_tables: Dict[str, Any]) -> None:
        """All completed missions in one category → strength signal, no avoidance."""
        tools = _load_tools(dynamodb_tables)
        missions = [
            {"missionId": "m-1", "status": "completed", "skillTag": "python"},
            {"missionId": "m-2", "status": "completed", "skillTag": "python"},
            {"missionId": "m-3", "status": "completed", "skillTag": "python"},
        ]
        result = tools._analyze_patterns(missions)

        assert result["total_missions"] == 3
        assert result["completed"] == 3
        assert result["skipped"] == 0
        assert result["by_category"]["python"] == {"assigned": 3, "completed": 3, "skipped": 0}
        assert result["strength_signals"] == ["python"]
        assert result["avoidance_signals"] == []

    def test_all_skipped_single_category(self, dynamodb_tables: Dict[str, Any]) -> None:
        """All skipped missions in one category → avoidance signal."""
        tools = _load_tools(dynamodb_tables)
        missions = [
            {"missionId": "m-1", "status": "skipped", "skillTag": "networking"},
            {"missionId": "m-2", "status": "skipped", "skillTag": "networking"},
        ]
        result = tools._analyze_patterns(missions)

        assert result["total_missions"] == 2
        assert result["skipped"] == 2
        assert result["avoidance_signals"] == ["networking"]
        assert result["strength_signals"] == []

    def test_mixed_statuses_multiple_categories(self, dynamodb_tables: Dict[str, Any]) -> None:
        """Mixed statuses across categories produce correct signals."""
        tools = _load_tools(dynamodb_tables)
        missions = [
            # technical: 7 completed, 1 skipped → skip rate 1/8 = 12.5% → strength? No (has skips)
            {"missionId": "m-1", "status": "completed", "skillTag": "technical"},
            {"missionId": "m-2", "status": "completed", "skillTag": "technical"},
            {"missionId": "m-3", "status": "completed", "skillTag": "technical"},
            {"missionId": "m-4", "status": "completed", "skillTag": "technical"},
            {"missionId": "m-5", "status": "completed", "skillTag": "technical"},
            {"missionId": "m-6", "status": "completed", "skillTag": "technical"},
            {"missionId": "m-7", "status": "completed", "skillTag": "technical"},
            {"missionId": "m-8", "status": "skipped", "skillTag": "technical"},
            # networking: 1 completed, 2 skipped, 1 pending → skip rate 2/4 = 50% → NOT avoidance (must be >50%)
            {"missionId": "m-9", "status": "completed", "skillTag": "networking"},
            {"missionId": "m-10", "status": "skipped", "skillTag": "networking"},
            {"missionId": "m-11", "status": "skipped", "skillTag": "networking"},
            {"missionId": "m-12", "status": "pending", "skillTag": "networking"},
            # reflection: 2 completed, 0 skipped, 1 in_progress → strength signal
            {"missionId": "m-13", "status": "completed", "skillTag": "reflection"},
            {"missionId": "m-14", "status": "completed", "skillTag": "reflection"},
            {"missionId": "m-15", "status": "in_progress", "skillTag": "reflection"},
        ]
        result = tools._analyze_patterns(missions)

        assert result["total_missions"] == 15
        assert result["completed"] == 10
        assert result["skipped"] == 3
        assert result["pending"] == 1
        assert result["in_progress"] == 1
        assert result["by_category"]["technical"] == {"assigned": 8, "completed": 7, "skipped": 1}
        assert result["by_category"]["networking"] == {"assigned": 4, "completed": 1, "skipped": 2}
        assert result["by_category"]["reflection"] == {"assigned": 3, "completed": 2, "skipped": 0}
        # networking at exactly 50% is NOT avoidance (must be >50%)
        assert result["avoidance_signals"] == []
        assert result["strength_signals"] == ["reflection"]

    def test_avoidance_threshold_just_above_50_percent(self, dynamodb_tables: Dict[str, Any]) -> None:
        """A category with skip rate just above 50% is flagged as avoidance."""
        tools = _load_tools(dynamodb_tables)
        # 2 skipped out of 3 assigned → 66.7% skip rate → avoidance
        missions = [
            {"missionId": "m-1", "status": "skipped", "skillTag": "public_speaking"},
            {"missionId": "m-2", "status": "skipped", "skillTag": "public_speaking"},
            {"missionId": "m-3", "status": "completed", "skillTag": "public_speaking"},
        ]
        result = tools._analyze_patterns(missions)

        assert result["avoidance_signals"] == ["public_speaking"]
        assert result["strength_signals"] == []

    def test_exactly_50_percent_skip_rate_not_avoidance(self, dynamodb_tables: Dict[str, Any]) -> None:
        """A category with exactly 50% skip rate is NOT flagged (must be >50%)."""
        tools = _load_tools(dynamodb_tables)
        missions = [
            {"missionId": "m-1", "status": "skipped", "skillTag": "writing"},
            {"missionId": "m-2", "status": "completed", "skillTag": "writing"},
        ]
        result = tools._analyze_patterns(missions)

        assert result["avoidance_signals"] == []
        assert result["strength_signals"] == []

    def test_pending_only_category_no_signals(self, dynamodb_tables: Dict[str, Any]) -> None:
        """A category with only pending missions produces no signals."""
        tools = _load_tools(dynamodb_tables)
        missions = [
            {"missionId": "m-1", "status": "pending", "skillTag": "design"},
            {"missionId": "m-2", "status": "pending", "skillTag": "design"},
        ]
        result = tools._analyze_patterns(missions)

        assert result["pending"] == 2
        assert result["avoidance_signals"] == []
        assert result["strength_signals"] == []

    def test_missing_skill_tag_defaults_to_unknown(self, dynamodb_tables: Dict[str, Any]) -> None:
        """Missions without a skillTag key are grouped under 'unknown'."""
        tools = _load_tools(dynamodb_tables)
        missions = [
            {"missionId": "m-1", "status": "completed"},
        ]
        result = tools._analyze_patterns(missions)

        assert "unknown" in result["by_category"]
        assert result["by_category"]["unknown"]["completed"] == 1
        assert result["strength_signals"] == ["unknown"]
