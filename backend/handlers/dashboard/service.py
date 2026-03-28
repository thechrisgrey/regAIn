"""Dashboard service module.

Contains business logic for aggregating campaign statistics.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Any, Dict, List

from boto3.dynamodb.conditions import Key

from backend.handlers.shared.dynamodb import DynamoDBClient

logger = logging.getLogger(__name__)

_QUERY_TIMEOUT_SECONDS = 8


class DashboardService:
    """Handles dashboard aggregation business logic."""

    def __init__(self, db_client: DynamoDBClient | None = None) -> None:
        self.db = db_client or DynamoDBClient()

    def get_dashboard(self, user_id: str) -> Dict[str, Any]:
        """Aggregate campaign progress and statistics for a user.

        Args:
            user_id: The authenticated user's ID.

        Returns:
            Dict with campaign info, stats, and optional deletion fields.
        """
        key_condition = Key("userId").eq(user_id)

        with ThreadPoolExecutor(max_workers=4) as executor:
            profile_future = executor.submit(
                self.db.get_item, "user_profiles", {"userId": user_id}
            )
            campaigns_future = executor.submit(
                self.db.query_all, "campaigns", key_condition
            )
            missions_future = executor.submit(
                self.db.query_all, "mission_history", key_condition
            )
            evidence_future = executor.submit(
                self.db.query_all, "evidence_vault", key_condition
            )

            try:
                profile = profile_future.result(timeout=_QUERY_TIMEOUT_SECONDS)
                campaigns = campaigns_future.result(timeout=_QUERY_TIMEOUT_SECONDS)
                missions = missions_future.result(timeout=_QUERY_TIMEOUT_SECONDS)
                evidence = evidence_future.result(timeout=_QUERY_TIMEOUT_SECONDS)
            except FuturesTimeoutError:
                logger.error("Dashboard query timed out after %ds", _QUERY_TIMEOUT_SECONDS)
                raise

        active_campaign = next(
            (c for c in campaigns if c.get("status") == "active"), None
        )
        completed = [m for m in missions if m.get("status") == "completed"]

        result: Dict[str, Any] = {
            "campaign": active_campaign,
            "stats": {
                "missionsCompleted": len(completed),
                "missionsTotal": len(missions),
                "evidenceCount": len(evidence),
                "currentPhase": active_campaign.get("phase") if active_campaign else None,
            },
        }

        if profile:
            deleted_at = profile.get("deletedAt")
            deletion_scheduled = profile.get("deletionScheduledFor")
            if deleted_at:
                result["deletedAt"] = deleted_at
            if deletion_scheduled:
                result["deletionScheduledFor"] = deletion_scheduled

        return result
