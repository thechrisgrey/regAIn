"""Dashboard service module.

Contains business logic for aggregating campaign statistics.
"""

from typing import Any, Dict, List

from boto3.dynamodb.conditions import Key

from backend.handlers.shared.dynamodb import DynamoDBClient


class DashboardService:
    """Handles dashboard aggregation business logic."""

    def __init__(self, db_client: DynamoDBClient | None = None) -> None:
        self.db = db_client or DynamoDBClient()

    def get_dashboard(self, user_id: str) -> Dict[str, Any]:
        """Aggregate campaign progress and statistics for a user.

        Args:
            user_id: The authenticated user's ID.

        Returns:
            Dict with campaign info and stats.
        """
        campaigns = self.db.query(
            "campaigns", Key("userId").eq(user_id)
        )
        active_campaign = next(
            (c for c in campaigns if c.get("status") == "active"), None
        )

        missions = self.db.query(
            "mission_history", Key("userId").eq(user_id)
        )
        completed = [m for m in missions if m.get("status") == "completed"]

        evidence = self.db.query(
            "evidence_vault", Key("userId").eq(user_id)
        )

        return {
            "campaign": active_campaign,
            "stats": {
                "missions_completed": len(completed),
                "missions_total": len(missions),
                "evidence_count": len(evidence),
                "current_phase": active_campaign.get("phase") if active_campaign else None,
            },
        }
