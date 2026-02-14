"""Evidence service module.

Contains business logic for querying the Evidence Vault.
"""

from typing import Any, Dict, List, Optional

from boto3.dynamodb.conditions import Key

from backend.lambda.shared.dynamodb import DynamoDBClient


class EvidenceService:
    """Handles evidence-related business logic."""

    def __init__(self, db_client: DynamoDBClient | None = None) -> None:
        self.db = db_client or DynamoDBClient()

    def list_evidence(
        self, user_id: str, skill_tag: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List evidence for a user, optionally filtered by skill tag.

        Args:
            user_id: The authenticated user's ID.
            skill_tag: Optional skill tag to filter by (uses GSI).

        Returns:
            List of evidence items.
        """
        if skill_tag:
            return self.db.query(
                "evidence_vault",
                Key("skillTag").eq(skill_tag),
                index_name="skill-index",
            )

        return self.db.query(
            "evidence_vault",
            Key("userId").eq(user_id),
        )
