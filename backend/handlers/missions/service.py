"""Missions service module.

Contains business logic for listing missions and completing them.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from boto3.dynamodb.conditions import Key

from backend.handlers.shared.dynamodb import DynamoDBClient
from backend.handlers.shared.models import Evidence


class MissionsService:
    """Handles mission-related business logic."""

    def __init__(self, db_client: DynamoDBClient | None = None) -> None:
        self.db = db_client or DynamoDBClient()

    def list_missions(self, user_id: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """List missions for a user, optionally filtered by status.

        Args:
            user_id: The authenticated user's ID.
            status: Optional status filter.

        Returns:
            List of mission items.
        """
        if status:
            return self.db.query(
                "mission_history",
                Key("status").eq(status) & Key("userId").eq(user_id),
                index_name="status-index",
            )

        return self.db.query(
            "mission_history",
            Key("userId").eq(user_id),
        )

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
