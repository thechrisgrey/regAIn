"""Missions service module.

Contains business logic for listing missions, completing them,
and generating new missions on demand.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from boto3.dynamodb.conditions import Attr as boto3_attr, Key

from backend.engine.generator import generate_daily_mission
from backend.engine.models import GenerationResult
from backend.handlers.shared.dynamodb import DynamoDBClient
from backend.handlers.shared.models import Evidence, Mission

logger = logging.getLogger(__name__)

# Independent daily limit for the /missions/generate endpoint.
# This is separate from the coaching agent's 3/day limit in tools.py.
_GENERATE_DAILY_LIMIT = 6


class _GenerateRateLimitExceeded(Exception):
    """Raised when the daily mission generation limit is reached."""


class MissionsService:
    """Handles mission-related business logic."""

    def __init__(self, db_client: DynamoDBClient | None = None) -> None:
        self.db = db_client or DynamoDBClient()

    # ------------------------------------------------------------------
    # Rate limiting for /missions/generate
    # ------------------------------------------------------------------

    def _enforce_generate_rate_limit(self, user_id: str) -> None:
        """Atomically increment the daily mission generation counter.

        Uses a DynamoDB conditional update on UserProfiles with a separate
        counter (webMissionGenCount / lastWebMissionGenDate) so it does not
        conflict with the coaching agent's own rate limit.

        Raises:
            _GenerateRateLimitExceeded: If the user has hit the daily limit.
        """
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        table = self.db._get_table("user_profiles")

        # Reset counter if the date has changed.
        try:
            table.update_item(
                Key={"userId": user_id},
                UpdateExpression="SET webMissionGenCount = :zero, lastWebMissionGenDate = :today",
                ConditionExpression=(
                    "attribute_not_exists(lastWebMissionGenDate) OR lastWebMissionGenDate <> :today"
                ),
                ExpressionAttributeValues={
                    ":zero": 0,
                    ":today": today,
                },
            )
        except table.meta.client.exceptions.ConditionalCheckFailedException:
            pass

        # Atomically increment, but only if count < limit.
        try:
            table.update_item(
                Key={"userId": user_id},
                UpdateExpression="ADD webMissionGenCount :inc",
                ConditionExpression="webMissionGenCount < :limit",
                ExpressionAttributeValues={
                    ":inc": 1,
                    ":limit": _GENERATE_DAILY_LIMIT,
                },
            )
        except table.meta.client.exceptions.ConditionalCheckFailedException:
            raise _GenerateRateLimitExceeded()

    def get_daily_remaining(self, user_id: str) -> Dict[str, Any]:
        """Return daily generation quota info for the user.

        Returns:
            Dict with dailyRemaining and dailyLimit.
        """
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        profile = self.db.get_item("user_profiles", {"userId": user_id})
        if not profile:
            return {"dailyRemaining": _GENERATE_DAILY_LIMIT, "dailyLimit": _GENERATE_DAILY_LIMIT}

        last_date = profile.get("lastWebMissionGenDate", "")
        if last_date != today:
            return {"dailyRemaining": _GENERATE_DAILY_LIMIT, "dailyLimit": _GENERATE_DAILY_LIMIT}

        count = int(profile.get("webMissionGenCount", 0))
        remaining = max(0, _GENERATE_DAILY_LIMIT - count)
        return {"dailyRemaining": remaining, "dailyLimit": _GENERATE_DAILY_LIMIT}

    # ------------------------------------------------------------------
    # List missions
    # ------------------------------------------------------------------

    def list_missions(
        self,
        user_id: str,
        status: Optional[str] = None,
        limit: int = 50,
        cursor: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List missions for a user with cursor-based pagination.

        Args:
            user_id: The authenticated user's ID.
            status: Optional status filter.
            limit: Maximum items per page (capped at 200).
            cursor: Opaque pagination cursor from a previous response.

        Returns:
            Dict with "items" list and "nextCursor" (str or None).
        """
        if status:
            return self.db.query_page(
                "mission_history",
                Key("status").eq(status) & Key("userId").eq(user_id),
                limit=limit,
                cursor=cursor,
                index_name="status-index",
            )

        return self.db.query_page(
            "mission_history",
            Key("userId").eq(user_id),
            limit=limit,
            cursor=cursor,
        )

    # ------------------------------------------------------------------
    # Generate new mission
    # ------------------------------------------------------------------

    def generate_mission(self, user_id: str) -> Dict[str, Any]:
        """Generate and persist a new mission for the user.

        Finds the user's active campaign, runs the mission engine pipeline,
        and persists the primary mission to DynamoDB.

        Returns:
            Dict with mission data on success, or error dict.

        Raises:
            _GenerateRateLimitExceeded: If the daily limit is exceeded.
        """
        self._enforce_generate_rate_limit(user_id)

        # Find the active campaign.
        campaigns = self.db.query(
            "campaigns",
            key_condition=Key("userId").eq(user_id),
            filter_expression=boto3_attr("status").eq("active"),
        )
        if not campaigns:
            return {"error": "no_active_campaign", "message": "No active campaign found."}

        campaign_id = campaigns[0]["campaignId"]

        result = generate_daily_mission(
            user_id=user_id,
            campaign_id=campaign_id,
            db=self.db,
        )

        if not isinstance(result, GenerationResult):
            return result  # Error dict from engine

        # Persist the primary mission.
        mission = Mission(
            user_id=user_id,
            mission_id=str(uuid.uuid4()),
            campaign_id=campaign_id,
            title=result.primary.title,
            description=result.primary.description,
            status="pending",
        )
        self.db.put_item("mission_history", mission.to_dynamodb_item())

        remaining = self.get_daily_remaining(user_id)

        return {
            "mission": mission.to_dynamodb_item(),
            **remaining,
        }

    def complete_mission(
        self, user_id: str, mission_id: str, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Mark a mission as completed and create an evidence record.

        Args:
            user_id: The authenticated user's ID.
            mission_id: The mission to complete.
            data: Dict with reflection, optional artifact_url, and skill_tags.

        Returns:
            Dict with success flag and evidence_id.
        """
        now = datetime.now(timezone.utc).isoformat()
        evidence_id = str(uuid.uuid4())

        self.db.update_item(
            "mission_history",
            key={"userId": user_id, "missionId": mission_id},
            updates={
                "status": "completed",
                "completedDate": now,
                "evidenceId": evidence_id,
            },
        )

        evidence = Evidence(
            user_id=user_id,
            evidence_id=evidence_id,
            mission_id=mission_id,
            skill_tag=data.get("skill_tags", ["general"])[0] if data.get("skill_tags") else "general",
            reflection=data.get("reflection", ""),
            created_at=now,
            artifact_url=data.get("artifact_url"),
        )
        self.db.put_item("evidence_vault", evidence.to_dynamodb_item())

        return {"success": True, "evidenceId": evidence_id}
