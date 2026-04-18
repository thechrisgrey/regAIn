"""Tests for market alignment integration in AnalyticsService."""

from unittest.mock import MagicMock, patch

import pytest

from backend.handlers.dashboard.analytics_service import AnalyticsService


@pytest.fixture()
def mock_db():
    """Return a mock DynamoDB client."""
    db = MagicMock()
    db.query_all.return_value = []
    db.get_item.return_value = None
    return db


class TestMarketAlignmentInAnalytics:
    """Tests for marketAlignment field in get_analytics response."""

    def test_returns_null_when_no_target_role(self, mock_db):
        """marketAlignment is None when user has no targetRole."""
        mock_db.get_item.return_value = {"userId": "u1", "skills": []}
        service = AnalyticsService(db_client=mock_db)

        with patch(
            "backend.handlers.dashboard.analytics_service.calculate_alignment"
        ) as mock_align:
            result = service.get_analytics("u1")

        assert result["marketAlignment"] is None
        mock_align.assert_not_called()

    def test_returns_null_when_no_profile(self, mock_db):
        """marketAlignment is None when profile doesn't exist."""
        mock_db.get_item.return_value = None
        service = AnalyticsService(db_client=mock_db)

        result = service.get_analytics("u1")

        assert result["marketAlignment"] is None

    def test_returns_alignment_when_target_role_set(self, mock_db):
        """marketAlignment populated when targetRole exists."""
        mock_db.get_item.return_value = {
            "userId": "u1",
            "targetRole": "ai_qa_engineer",
        }
        service = AnalyticsService(db_client=mock_db)

        mock_result = MagicMock()
        mock_result.alignment_pct = 62.5
        mock_result.top_gaps = [
            {"skill": "Python Testing", "gap": 0.78, "market_weight": 0.78, "user_score": 0.0},
        ]
        mock_result.top_strengths = [
            {"skill": "Manual QA", "user_score": 1.0, "market_weight": 0.65},
        ]
        mock_result.calculated_at = "2026-04-18T00:00:00+00:00"

        with patch(
            "backend.handlers.dashboard.analytics_service.calculate_alignment",
            return_value=mock_result,
        ) as mock_align:
            result = service.get_analytics("u1")

        mock_align.assert_called_once_with("u1", "ai_qa_engineer")
        ma = result["marketAlignment"]
        assert ma is not None
        assert ma["alignmentPct"] == 62.5
        assert ma["targetRole"] == "ai_qa_engineer"
        assert len(ma["topGaps"]) == 1
        assert ma["topGaps"][0]["skill"] == "Python Testing"
        assert ma["topGaps"][0]["demand"] == 78
        assert len(ma["topStrengths"]) == 1
        assert ma["topStrengths"][0]["skill"] == "Manual QA"
        assert ma["calculatedAt"] == "2026-04-18T00:00:00+00:00"

    def test_alignment_failure_returns_null(self, mock_db):
        """marketAlignment is None when calculate_alignment raises."""
        mock_db.get_item.return_value = {
            "userId": "u1",
            "targetRole": "ai_qa_engineer",
        }
        service = AnalyticsService(db_client=mock_db)

        with patch(
            "backend.handlers.dashboard.analytics_service.calculate_alignment",
            side_effect=RuntimeError("boom"),
        ):
            result = service.get_analytics("u1")

        assert result["marketAlignment"] is None

    def test_other_fields_unaffected_by_alignment(self, mock_db):
        """Existing analytics fields are present regardless of alignment."""
        mock_db.get_item.return_value = None
        service = AnalyticsService(db_client=mock_db)

        result = service.get_analytics("u1")

        assert "skillBreakdown" in result
        assert "activityHeatmap" in result
        assert "velocityTrend" in result
        assert "campaignEta" in result
        assert "skillSuggestions" in result
        assert "marketAlignment" in result

    def test_empty_target_role_string_returns_null(self, mock_db):
        """marketAlignment is None when targetRole is empty string."""
        mock_db.get_item.return_value = {"userId": "u1", "targetRole": "  "}
        service = AnalyticsService(db_client=mock_db)

        result = service.get_analytics("u1")

        assert result["marketAlignment"] is None
