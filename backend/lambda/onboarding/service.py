"""Onboarding service module.

Contains business logic for user onboarding — creating profiles
and initializing campaigns.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from backend.lambda.shared.dynamodb import DynamoDBClient
from backend.lambda.shared.models import Campaign, UserProfile


class OnboardingService:
    """Handles user onboarding business logic."""

    def __init__(self, db_client: DynamoDBClient | None = None) -> None:
        self.db = db_client or DynamoDBClient()

    def create_profile(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new user profile and initialize a campaign.

        Args:
            data: Dict with email, name, persona, target_role, and optional skills.

        Returns:
            Dict with userId, campaignId, and profile data.
        """
        user_id = str(uuid.uuid4())
        campaign_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        profile = UserProfile(
            user_id=user_id,
            email=data["email"],
            name=data["name"],
            persona=data["persona"],
            onboarding_completed=True,
            created_at=now,
            target_role=data.get("target_role"),
            skills=data.get("skills", []),
        )

        campaign = Campaign(
            user_id=user_id,
            campaign_id=campaign_id,
            title=f"Reskilling Campaign — {data.get('target_role', 'General')}",
            phase="foundation",
            status="active",
            start_date=now,
            target_role=data.get("target_role", ""),
            skills_focus=data.get("skills", []),
        )

        self.db.put_item("user_profiles", profile.to_dynamodb_item())
        self.db.put_item("campaigns", campaign.to_dynamodb_item())

        return {
            "userId": user_id,
            "campaignId": campaign_id,
            "profile": profile.to_dynamodb_item(),
        }
