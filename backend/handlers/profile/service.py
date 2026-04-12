"""Profile service module.

Contains business logic for user profile management:
- Soft delete with 30-day grace period and PII stripping
- Account recovery (within grace period)
- Hard delete (used by scheduled cleanup Lambda)
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import boto3

from backend.handlers.shared.dynamodb import DynamoDBClient

logger = logging.getLogger(__name__)

_SOFT_DELETE_DAYS = 30


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

    def soft_delete_user_account(self, user_id: str) -> Dict[str, Any]:
        """Schedule account for deletion after a 30-day grace period.

        Strips PII from the profile immediately and revokes Cognito tokens,
        but does not delete data. The scheduled cleanup Lambda calls
        _hard_delete_user_account() after the grace period.

        Args:
            user_id: Cognito sub from JWT claims.

        Returns:
            Dict with status and scheduled deletion date.
        """
        now = datetime.now(timezone.utc)
        deletion_date = now + timedelta(days=_SOFT_DELETE_DAYS)

        # Strip PII and mark as deleted.
        self.db.update_item(
            "user_profiles",
            {"userId": user_id},
            {
                "deletedAt": now.isoformat(),
                "deletionScheduledFor": deletion_date.isoformat(),
                "firstName": "[deleted]",
                "lastName": "[deleted]",
                "email": "[deleted]",
                "name": "[deleted]",
            },
        )

        # Revoke all Cognito tokens (but don't delete the user yet).
        if self.user_pool_id:
            try:
                self.cognito.admin_user_global_sign_out(
                    UserPoolId=self.user_pool_id,
                    Username=user_id,
                )
            except Exception:
                logger.warning("Failed to sign out user %s from Cognito", user_id)

        logger.info(
            "Soft-deleted user %s, scheduled for hard delete on %s",
            user_id,
            deletion_date.isoformat(),
        )
        return {
            "status": "scheduled",
            "deletionDate": deletion_date.isoformat(),
        }

    def recover_user_account(self, user_id: str) -> Dict[str, Any]:
        """Recover a soft-deleted account within the grace period.

        Removes the deletion markers. Note: PII was stripped during
        soft delete — the user will need to re-enter their name
        and email on next login.

        Args:
            user_id: Cognito sub from JWT claims.

        Returns:
            Dict with recovery status.
        """
        profile = self.db.get_item("user_profiles", {"userId": user_id})
        if not profile or not profile.get("deletedAt"):
            return {"status": "not_deleted", "message": "Account is not scheduled for deletion"}

        # Remove deletion markers using a raw DynamoDB update.
        table = self.db._get_table("user_profiles")
        table.update_item(
            Key={"userId": user_id},
            UpdateExpression="REMOVE #da, #dsf",
            ExpressionAttributeNames={
                "#da": "deletedAt",
                "#dsf": "deletionScheduledFor",
            },
        )

        logger.info("Recovered soft-deleted account for user %s", user_id)
        return {"status": "recovered"}

    def hard_delete_user_account(self, user_id: str) -> Dict[str, Any]:
        """Permanently delete all user data from DynamoDB, S3, and Cognito.

        Deletion order: DynamoDB tables first, S3 second,
        AgentCore Memory third, Cognito last.

        Args:
            user_id: Cognito sub from JWT claims.

        Returns:
            Dict with status and deleted item counts.
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

        # 6. ConversationThreads — PK=userId, SK=threadId
        deleted["conversation_threads"] = self.db.delete_all_by_partition_key(
            "conversation_threads",
            partition_key_name="userId",
            partition_key_value=user_id,
            sort_key_name="threadId",
        )

        # 7. CalendarEntries — PK=userId, SK=dateEntryId
        if "calendar_entries" in self.db.tables:
            deleted["calendar_entries"] = self.db.delete_all_by_partition_key(
                "calendar_entries",
                partition_key_name="userId",
                partition_key_value=user_id,
                sort_key_name="dateEntryId",
            )

        # 8. Voice practice S3 cleanup
        voice_bucket = os.environ.get("VOICE_PRACTICE_BUCKET_NAME", "")
        if voice_bucket:
            deleted["voice_practice_s3"] = self._delete_s3_prefix(
                voice_bucket, f"{user_id}/voice-practice/"
            )
        else:
            deleted["voice_practice_s3"] = 0

        # 9. Resume S3 cleanup
        resume_bucket = os.environ.get("RESUME_BUCKET_NAME", "")
        if resume_bucket:
            deleted["resume_s3"] = self._delete_s3_prefix(
                resume_bucket, f"{user_id}/resume/"
            )
        else:
            deleted["resume_s3"] = 0

        # 10. Code interpreter S3 cleanup
        code_interp_bucket = os.environ.get("CODE_INTERPRETER_BUCKET_NAME", "")
        if code_interp_bucket:
            deleted["code_interpreter_s3"] = self._delete_s3_prefix(
                code_interp_bucket, f"{user_id}/"
            )
        else:
            deleted["code_interpreter_s3"] = 0

        # 11. Thread archives S3 cleanup
        thread_archive_bucket = os.environ.get("THREAD_ARCHIVE_BUCKET", "")
        if thread_archive_bucket:
            deleted["thread_archives_s3"] = self._delete_s3_prefix(
                thread_archive_bucket, f"{user_id}/"
            )
        else:
            deleted["thread_archives_s3"] = 0

        # 12. AgentCore Memory
        deleted["agentcore_memory"] = self._delete_agentcore_memory(user_id)

        # 13. Cognito — delete user so the email can be re-registered
        if self.user_pool_id:
            try:
                self.cognito.admin_delete_user(
                    UserPoolId=self.user_pool_id,
                    Username=user_id,
                )
                deleted["cognito"] = 1
            except Exception:
                logger.warning("Cognito deletion failed for user %s", user_id)
                deleted["cognito"] = 0
        else:
            deleted["cognito"] = 0

        logger.info("Hard-deleted account for user %s: %s", user_id, deleted)
        return {"status": "deleted", "deleted": deleted}

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
            resp = self.s3.delete_objects(
                Bucket=bucket,
                Delete={"Objects": to_delete, "Quiet": True},
            )
            errors = resp.get("Errors", [])
            if errors:
                logger.warning("S3 delete errors in %s: %s", bucket, errors)
            deleted_count += len(to_delete) - len(errors)
        return deleted_count

    _MEMORY_NAMESPACES = [
        "regain-coaching-{user_id}",
        "/summaries/{user_id}/",
        "/preferences/{user_id}/",
        "/facts/{user_id}/",
    ]

    def _delete_agentcore_memory(self, user_id: str) -> int:
        """Delete all AgentCore Memory records for a user across all namespaces.

        Iterates over all strategy namespace patterns (summaries, preferences,
        facts) plus the legacy flat namespace to ensure complete cleanup.
        Each namespace is cleaned independently so a failure in one does not
        block the others.

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

        deleted_count = 0
        for ns_template in self._MEMORY_NAMESPACES:
            namespace = ns_template.format(user_id=user_id)
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
                logger.warning(
                    "AgentCore Memory cleanup failed for namespace %s: %s",
                    namespace, exc,
                )

        return deleted_count
