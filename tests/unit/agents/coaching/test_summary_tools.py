"""Unit tests for get_evidence_summary and get_market_insights tools.

Tests use moto-mocked DynamoDB via the shared dynamodb_tables fixture.
The @tool decorator from strands is stubbed since strands-agents is not
yet installed.
"""

import importlib
import sys
import types
from typing import Any, Dict
from unittest.mock import MagicMock, patch

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


def _seed_evidence(
    dynamodb_tables: Dict[str, Any],
    user_id: str,
    evidence_id: str,
    skill_tag: str,
    created_at: str,
    reflection: str = "Did some work.",
) -> None:
    """Insert an evidence record into the mocked EvidenceVault table."""
    dynamodb_tables["evidence_vault"].put_item(Item={
        "userId": user_id,
        "evidenceId": evidence_id,
        "missionId": "mission-1",
        "skillTag": skill_tag,
        "reflection": reflection,
        "createdAt": created_at,
    })


def _seed_market_data(
    dynamodb_tables: Dict[str, Any],
    sector: str,
    timestamp: str,
    job_trends: dict | None = None,
    skill_demand: list | None = None,
    salary_ranges: dict | None = None,
    data_source: str = "market_scan_2025_01",
) -> None:
    """Insert a market data record into the mocked MarketData table."""
    dynamodb_tables["market_data"].put_item(Item={
        "sector": sector,
        "timestamp": timestamp,
        "job_trends": job_trends or {},
        "skill_demand": skill_demand or [],
        "salary_ranges": salary_ranges or {},
        "data_source": data_source,
    })


class TestGetEvidenceSummary:
    """Tests for the get_evidence_summary tool."""

    def test_returns_empty_summary_for_new_user(self, dynamodb_tables: Dict[str, Any]) -> None:
        """A user with no evidence gets an empty summary."""
        tools = _load_tools(dynamodb_tables)
        result = tools.get_evidence_summary(user_id="user-new")

        assert result["by_skill"] == {}
        assert result["recent"] == []
        assert result["total_count"] == 0

    def test_aggregates_by_skill_tag(self, dynamodb_tables: Dict[str, Any]) -> None:
        """Evidence is correctly grouped and counted by skill tag."""
        _seed_evidence(dynamodb_tables, "user-1", "e-1", "python", "2025-01-01T01:00:00Z")
        _seed_evidence(dynamodb_tables, "user-1", "e-2", "python", "2025-01-02T01:00:00Z")
        _seed_evidence(dynamodb_tables, "user-1", "e-3", "python", "2025-01-03T01:00:00Z")
        _seed_evidence(dynamodb_tables, "user-1", "e-4", "networking", "2025-01-04T01:00:00Z")
        _seed_evidence(dynamodb_tables, "user-1", "e-5", "communication", "2025-01-05T01:00:00Z")
        _seed_evidence(dynamodb_tables, "user-1", "e-6", "communication", "2025-01-06T01:00:00Z")

        tools = _load_tools(dynamodb_tables)
        result = tools.get_evidence_summary(user_id="user-1")

        assert result["by_skill"] == {"python": 3, "networking": 1, "communication": 2}
        assert result["total_count"] == 6

    def test_recent_returns_last_five(self, dynamodb_tables: Dict[str, Any]) -> None:
        """Recent list contains the 5 most recent evidence items by createdAt."""
        for i in range(7):
            _seed_evidence(
                dynamodb_tables, "user-1", f"e-{i}",
                "python", f"2025-01-{i + 1:02d}T01:00:00Z",
            )

        tools = _load_tools(dynamodb_tables)
        result = tools.get_evidence_summary(user_id="user-1")

        assert len(result["recent"]) == 5
        # Most recent first
        timestamps = [r["createdAt"] for r in result["recent"]]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_scoped_to_user(self, dynamodb_tables: Dict[str, Any]) -> None:
        """Evidence from other users is not included in the summary."""
        _seed_evidence(dynamodb_tables, "user-1", "e-1", "python", "2025-01-01T01:00:00Z")
        _seed_evidence(dynamodb_tables, "user-2", "e-2", "python", "2025-01-02T01:00:00Z")

        tools = _load_tools(dynamodb_tables)
        result = tools.get_evidence_summary(user_id="user-1")

        assert result["total_count"] == 1
        assert result["by_skill"] == {"python": 1}

    def test_returns_error_when_table_not_configured(self, aws_credentials: None) -> None:
        """Returns an error dict when the table env var is missing."""
        import os
        os.environ.pop("EVIDENCE_VAULT_TABLE", None)

        tools = _load_tools({})
        result = tools.get_evidence_summary("u-1")

        assert result["error"] in ("invalid_input", "read_failed")


class TestGetMarketInsights:
    """Tests for the get_market_insights tool."""

    def test_returns_data_for_known_role(self, dynamodb_tables: Dict[str, Any]) -> None:
        """Returns market data when the market_intel module has data."""
        tools = _load_tools(dynamodb_tables)

        mock_demand = {
            "role_id": "qa_engineer",
            "demand_score": 75,
            "trend_direction": "up",
            "growth_rate": 12.5,
            "top_skills": ["python", "selenium"],
            "salary_range": {"entry": "75k-90k"},
        }
        mock_insights = [{"type": "trend", "text": "QA demand rising"}]

        with patch("backend.agents.coaching.tools.importlib") as mock_importlib:
            mock_mi = MagicMock()
            mock_mi.get_demand_score.return_value = mock_demand
            mock_mi.get_insights.return_value = mock_insights
            mock_importlib.import_module.return_value = mock_mi

            result = tools.get_market_insights(role_id="qa_engineer")

        assert result["role_id"] == "qa_engineer"
        assert result["demand_score"] == 75
        assert result["trend_direction"] == "up"

    def test_returns_not_found_for_unknown_role(self, dynamodb_tables: Dict[str, Any]) -> None:
        """Returns an error dict when no data exists for the role."""
        tools = _load_tools(dynamodb_tables)

        with patch("backend.agents.coaching.tools.importlib") as mock_importlib:
            mock_mi = MagicMock()
            mock_mi.get_demand_score.return_value = None
            mock_importlib.import_module.return_value = mock_mi

            result = tools.get_market_insights(role_id="underwater_basket_weaving")

        assert result["error"] == "not_found"
        assert "underwater_basket_weaving" in result["message"]

    def test_returns_error_on_exception(self, aws_credentials: None) -> None:
        """Returns an error dict when the underlying module raises."""
        import os
        os.environ.pop("MARKET_DATA_TABLE", None)

        tools = _load_tools({})

        with patch("backend.agents.coaching.tools.importlib") as mock_importlib:
            mock_importlib.import_module.side_effect = Exception("boom")
            result = tools.get_market_insights("some_role")

        assert result["error"] == "read_failed"
