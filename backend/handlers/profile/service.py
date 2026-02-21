"""Profile service module.

Contains business logic for user profile management — currently
limited to account deletion (hard delete across all tables + Cognito).
"""

import logging
import os
from typing import Any, Dict

import boto3

from backend.handlers.shared.dynamodb import DynamoDBClient

logger = logging.getLogger(__name__)


class ProfileService:
    """Handles user profile business logic."""

    def __init__(
        self,
        db_client: DynamoDBClient | None = None,
        cognito_client: Any | None = None,
    ) -> None:
        self.db = db_client or DynamoDBClient()
        self.cognito = cognito_client or boto3.client("cognito-idp")
        self.user_pool_id = os.environ.get("USER_POOL_ID", "")

    def delete_user_account(self, user_id: str) -> Dict[str, Any]:
        """Delete all user data from DynamoDB and Cognito.

        Deletion order: DynamoDB tables first, Cognito last. If Cognito
        deletion fails the user can still sign in and retry. If we
        deleted Cognito first, orphaned DynamoDB data would be
        unrecoverable.

        Args:
            user_id: Cognito sub from JWT claims.

        Returns:
            Dict with deleted item counts per table.
        """
        deleted: Dict[str, int] = {}

        # 1. UserProfiles — single item, PK=userId
        self.db.delete_item("user_profiles", {"userId": user_id})
        deleted["user_profiles"] = 1

        # 2. Campaigns — PK=userId, SK=campaignId
        deleted["campaigns"] = self.db.delete_all_by_partition_key(
            "campaigns",
            partition_key_name="userId",
            partition_key_value=user_id,
            sort_key_name="campaignId",
        )

        # 3. MissionHistory — PK=userId, SK=missionId
        deleted["mission_history"] = self.db.delete_all_by_partition_key(
            "mission_history",
            partition_key_name="userId",
            partition_key_value=user_id,
            sort_key_name="missionId",
        )

        # 4. EvidenceVault — PK=userId, SK=evidenceId
        deleted["evidence_vault"] = self.db.delete_all_by_partition_key(
            "evidence_vault",
            partition_key_name="userId",
            partition_key_value=user_id,
            sort_key_name="evidenceId",
        )

        # 5. Cognito — delete user so the email can be re-registered
        if self.user_pool_id:
            self.cognito.admin_delete_user(
                UserPoolId=self.user_pool_id,
                Username=user_id,
            )
            deleted["cognito"] = 1
        else:
            logger.warning("USER_POOL_ID not set; skipping Cognito deletion")
            deleted["cognito"] = 0

        logger.info("Deleted account for user %s: %s", user_id, deleted)
        return deleted
