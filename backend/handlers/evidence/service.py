"""Evidence service module.

Contains business logic for querying the Evidence Vault.
"""

from typing import Any, Dict, Optional

from boto3.dynamodb.conditions import Attr, Key

from backend.handlers.shared.dynamodb import DynamoDBClient


class EvidenceService:
    """Handles evidence-related business logic."""

    def __init__(self, db_client: DynamoDBClient | None = None) -> None:
        self.db = db_client or DynamoDBClient()

    def list_evidence(
        self,
        user_id: str,
        skill_tag: Optional[str] = None,
        limit: int = 50,
        cursor: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List evidence for a user with cursor-based pagination.

        Args:
            user_id: The authenticated user's ID.
            skill_tag: Optional skill tag to filter by.
            limit: Maximum items per page (capped at 200).
            cursor: Opaque pagination cursor from a previous response.

        Returns:
            Dict with "items" list and "nextCursor" (str or None).
        """
        if skill_tag:
            return self.db.query_page(
                "evidence_vault",
                Key("userId").eq(user_id),
                limit=limit,
                cursor=cursor,
                filter_expression=Attr("skillTag").eq(skill_tag),
            )

        return self.db.query_page(
            "evidence_vault",
            Key("userId").eq(user_id),
            limit=limit,
            cursor=cursor,
        )
