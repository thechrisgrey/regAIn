"""Contract test for dashboard response shape.

Verifies that DashboardService response keys match the frontend
DashboardResponse TypeScript interface (camelCase keys).
"""

from boto3.dynamodb.conditions import Key

from backend.handlers.shared.dynamodb import DynamoDBClient
from backend.handlers.dashboard.service import DashboardService


EXPECTED_STATS_KEYS = {"missionsCompleted", "missionsTotal", "evidenceCount", "currentPhase"}

TEST_USER_ID = "contract-test-user"


def _seed_data(tables: dict) -> None:
    """Insert minimal data so get_dashboard returns a populated response."""
    tables["user_profiles"].put_item(Item={
        "userId": TEST_USER_ID,
        "name": "Test User",
        "email": "test@example.com",
        "persona": "veteran",
    })
    tables["campaigns"].put_item(Item={
        "userId": TEST_USER_ID,
        "campaignId": "camp-001",
        "title": "Test Campaign",
        "phase": "foundation",
        "status": "active",
        "targetRole": "Engineer",
    })
    tables["mission_history"].put_item(Item={
        "userId": TEST_USER_ID,
        "missionId": "m-001",
        "campaignId": "camp-001",
        "title": "First Mission",
        "description": "Do something",
        "status": "completed",
    })
    tables["evidence_vault"].put_item(Item={
        "userId": TEST_USER_ID,
        "evidenceId": "ev-001",
        "missionId": "m-001",
        "skillTag": "Python",
        "reflection": "Learned Python",
        "createdAt": "2025-01-01T00:00:00Z",
    })


class TestDashboardStatsContract:
    """Verify response keys match the frontend DashboardResponse TypeScript interface."""

    def test_stats_keys_match_frontend_contract(self, dynamodb_tables):
        """DashboardService.get_dashboard() stats dict uses camelCase keys."""
        _seed_data(dynamodb_tables)
        service = DashboardService(db_client=DynamoDBClient())
        result = service.get_dashboard(TEST_USER_ID)

        assert "stats" in result
        assert set(result["stats"].keys()) == EXPECTED_STATS_KEYS

    def test_stats_values_are_correct(self, dynamodb_tables):
        """Verify stats values match seeded data."""
        _seed_data(dynamodb_tables)
        service = DashboardService(db_client=DynamoDBClient())
        result = service.get_dashboard(TEST_USER_ID)

        stats = result["stats"]
        assert stats["missionsCompleted"] == 1
        assert stats["missionsTotal"] == 1
        assert stats["evidenceCount"] == 1
        assert stats["currentPhase"] == "foundation"

    def test_no_active_campaign_returns_null_phase(self, dynamodb_tables):
        """When no active campaign exists, currentPhase is None."""
        dynamodb_tables["user_profiles"].put_item(Item={
            "userId": TEST_USER_ID,
            "name": "Test User",
            "email": "test@example.com",
            "persona": "veteran",
        })
        service = DashboardService(db_client=DynamoDBClient())
        result = service.get_dashboard(TEST_USER_ID)

        assert result["stats"]["currentPhase"] is None
        assert result["campaign"] is None
