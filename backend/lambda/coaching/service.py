"""Coaching service module.

Placeholder for future agent integration. Currently returns
a basic acknowledgement for check-in requests.
"""

from typing import Any, Dict

from backend.lambda.shared.dynamodb import DynamoDBClient


class CoachingService:
    """Handles coaching check-in business logic."""

    def __init__(self, db_client: DynamoDBClient | None = None) -> None:
        self.db = db_client or DynamoDBClient()

    def checkin(self, user_id: str, message: str) -> Dict[str, Any]:
        """Process a coaching check-in.

        This is a placeholder that will be replaced with Strands agent
        integration in a future spec.

        Args:
            user_id: The authenticated user's ID.
            message: The user's check-in message.

        Returns:
            Dict with a placeholder response.
        """
        profile = self.db.get_item("user_profiles", {"userId": user_id})
        name = profile.get("name", "there") if profile else "there"

        return {
            "response": f"Thanks for checking in, {name}. "
            "Coaching agent integration coming soon.",
            "userId": user_id,
        }
