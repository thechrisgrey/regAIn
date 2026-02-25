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
        s3_client: Any | None = None,
    ) -> None:
        self.db = db_client or DynamoDBClient()
        self.cognito = cognito_client or boto3.client("cognito-idp")
        self.s3 = s3_client or boto3.client("s3")
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

        # 5. VoiceSessions — PK=userId, SK=sessionId
        deleted["voice_sessions"] = self.db.delete_all_by_partition_key(
            "voice_sessions",
            partition_key_name="userId",
            partition_key_value=user_id,
            sort_key_name="sessionId",
        )

        # 6. Voice practice S3 cleanup — delete all objects under user's prefix
        voice_bucket = os.environ.get("VOICE_PRACTICE_BUCKET_NAME", "")
        if voice_bucket:
            s3_deleted = self._delete_s3_prefix(voice_bucket, f"{user_id}/voice-practice/")
            deleted["voice_practice_s3"] = s3_deleted
        else:
            logger.warning("VOICE_PRACTICE_BUCKET_NAME not set; skipping S3 cleanup")
            deleted["voice_practice_s3"] = 0

        # 7. Resume S3 cleanup — delete all resume objects under user's prefix
        resume_bucket = os.environ.get("RESUME_BUCKET_NAME", "")
        if resume_bucket:
            s3_deleted = self._delete_s3_prefix(resume_bucket, f"{user_id}/resume/")
            deleted["resume_s3"] = s3_deleted
        else:
            logger.warning("RESUME_BUCKET_NAME not set; skipping resume S3 cleanup")
            deleted["resume_s3"] = 0

        # 8. Code interpreter S3 cleanup — delete any user-prefixed objects
        code_interp_bucket = os.environ.get("CODE_INTERPRETER_BUCKET_NAME", "")
        if code_interp_bucket:
            s3_deleted = self._delete_s3_prefix(code_interp_bucket, f"{user_id}/")
            deleted["code_interpreter_s3"] = s3_deleted
        else:
            logger.warning("CODE_INTERPRETER_BUCKET_NAME not set; skipping code interpreter S3 cleanup")
            deleted["code_interpreter_s3"] = 0

        # 9. AgentCore Memory — purge coaching session summaries
        deleted["agentcore_memory"] = self._delete_agentcore_memory(user_id)

        # 10. Cognito — delete user so the email can be re-registered
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

    def _delete_s3_prefix(self, bucket: str, prefix: str) -> int:
        """Delete all object versions and delete markers under an S3 prefix.

        Uses ``list_object_versions`` so that versioned buckets are fully
        purged (not just delete-marker'd).  Works identically on
        non-versioned buckets where ``VersionId`` is ``"null"``.

        Args:
            bucket: S3 bucket name.
            prefix: Object key prefix to delete under.

        Returns:
            Number of object versions deleted.
        """
        deleted_count = 0
        paginator = self.s3.get_paginator("list_object_versions")
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            to_delete = []
            for obj in page.get("Versions", []):
                to_delete.append({"Key": obj["Key"], "VersionId": obj["VersionId"]})
            for marker in page.get("DeleteMarkers", []):
                to_delete.append({"Key": marker["Key"], "VersionId": marker["VersionId"]})
            if not to_delete:
                continue
            # S3 delete_objects accepts max 1000 keys per call;
            # list_object_versions returns max 1000 entries per page, so safe.
            resp = self.s3.delete_objects(
                Bucket=bucket,
                Delete={"Objects": to_delete, "Quiet": True},
            )
            errors = resp.get("Errors", [])
            if errors:
                logger.warning("S3 delete errors in %s: %s", bucket, errors)
            deleted_count += len(to_delete) - len(errors)
        return deleted_count

    def _delete_agentcore_memory(self, user_id: str) -> int:
        """Delete all AgentCore Memory records for a user's coaching namespace.

        Gracefully degrades if the ``bedrock-agentcore`` service model is
        unavailable in the Lambda runtime's boto3 version.

        Args:
            user_id: Cognito sub from JWT claims.

        Returns:
            Number of memory records deleted.
        """
        memory_id = os.environ.get("AGENTCORE_MEMORY_ID", "")
        if not memory_id:
            logger.warning("AGENTCORE_MEMORY_ID not set; skipping memory cleanup")
            return 0

        try:
            client = boto3.client(
                "bedrock-agentcore",
                region_name=os.environ.get("AWS_REGION", "us-east-1"),
            )
        except Exception:
            logger.warning("bedrock-agentcore client unavailable; skipping memory cleanup")
            return 0

        namespace = f"regain-coaching-{user_id}"
        deleted_count = 0

        try:
            paginator = client.get_paginator("list_memory_records")
            for page in paginator.paginate(memoryId=memory_id, namespace=namespace):
                for record in page.get("memoryRecordSummaries", []):
                    record_id = record.get("memoryRecordId", "")
                    if not record_id:
                        continue
                    client.delete_memory_record(
                        memoryId=memory_id,
                        memoryRecordId=record_id,
                    )
                    deleted_count += 1
        except Exception as exc:
            logger.warning("AgentCore Memory cleanup failed for user %s: %s", user_id, exc)

        return deleted_count
