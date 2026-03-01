"""Scheduled cleanup Lambda handler.

Runs daily via CloudWatch Events to permanently delete user accounts
that have been soft-deleted past their 30-day grace period.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict

import boto3
from boto3.dynamodb.conditions import Attr

from backend.handlers.shared.dynamodb import DynamoDBClient
from backend.handlers.profile.service import ProfileService

logger = logging.getLogger(__name__)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Scan for expired soft-deleted accounts and hard-delete them.

    Args:
        event: CloudWatch Events scheduled event.
        context: Lambda context.

    Returns:
        Dict with count of processed accounts.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    processed = 0
    errors = 0

    try:
        db = DynamoDBClient()
        table = db._get_table("user_profiles")

        # Scan for soft-deleted profiles past their grace period.
        # Using scan with filter because there's no GSI on deletedAt.
        # Expected volume is very small (handful of accounts at most).
        response = table.scan(
            FilterExpression=(
                Attr("deletedAt").exists()
                & Attr("deletionScheduledFor").lt(now_iso)
            ),
            ProjectionExpression="userId",
        )

        items = response.get("Items", [])

        # Handle pagination for scan.
        while "LastEvaluatedKey" in response:
            response = table.scan(
                FilterExpression=(
                    Attr("deletedAt").exists()
                    & Attr("deletionScheduledFor").lt(now_iso)
                ),
                ProjectionExpression="userId",
                ExclusiveStartKey=response["LastEvaluatedKey"],
            )
            items.extend(response.get("Items", []))

        service = ProfileService(db_client=db)

        for item in items:
            user_id = item.get("userId")
            if not user_id:
                continue
            try:
                service._hard_delete_user_account(user_id)
                processed += 1
                logger.info("Hard-deleted expired account: %s", user_id)
            except Exception:
                errors += 1
                logger.exception("Failed to hard-delete user %s", user_id)

    except Exception:
        logger.exception("Cleanup scan failed")

    logger.info("Cleanup complete: %d processed, %d errors", processed, errors)
    return {"processed": processed, "errors": errors}
