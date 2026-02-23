"""Onboarding service module.

Contains business logic for user onboarding — creating profiles
and initializing campaigns.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from backend.engine.generator import generate_daily_mission
from backend.engine.models import GenerationResult
from backend.handlers.shared.dynamodb import DynamoDBClient
from backend.handlers.shared.models import Campaign, Mission, UserProfile

logger = logging.getLogger(__name__)


class OnboardingService:
    """Handles user onboarding business logic."""

    def __init__(self, db_client: DynamoDBClient | None = None) -> None:
        self.db = db_client or DynamoDBClient()

    def _seed_first_missions(
        self, user_id: str, campaign_id: str
    ) -> list[Dict[str, Any]]:
        """Generate and persist initial missions so the user has work on day 1."""
        try:
            result = generate_daily_mission(user_id, campaign_id, db=self.db)
            if not isinstance(result, GenerationResult):
                logger.warning("Mission generation returned error: %s", result)
                return []

            missions: list[Dict[str, Any]] = []
            for candidate in [result.primary, *result.alternates]:
                mission = Mission(
                    user_id=user_id,
                    mission_id=str(uuid.uuid4()),
                    campaign_id=campaign_id,
                    title=candidate.title,
                    description=candidate.description,
                    status="pending",
                )
                self.db.put_item("mission_history", mission.to_dynamodb_item())
                missions.append(mission.to_dynamodb_item())

            return missions
        except Exception:
            logger.exception("Failed to seed missions for %s", user_id)
            return []

    def create_profile(self, user_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new user profile and initialize a campaign.

        Args:
            user_id: Cognito sub from JWT claims.
            data: Dict with email, name, persona, target_role, and optional skills.

        Returns:
            Dict with userId, campaignId, and profile data.
        """
        campaign_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        first_name = data.get("first_name", "")
        last_name = data.get("last_name", "")
        name = f"{first_name} {last_name}".strip() or data.get("name", "")

        # Build experience list for template engine (profile["experience"][0]["company"])
        experience = None
        if data.get("company") or data.get("current_role"):
            experience = [{
                "company": data.get("company", ""),
                "role": data.get("current_role", ""),
            }]

        profile = UserProfile(
            user_id=user_id,
            email=data["email"],
            name=name,
            persona=data["persona"],
            onboarding_completed=True,
            created_at=now,
            target_role=data.get("target_role"),
            skills=data.get("skills", []),
            first_name=first_name or None,
            last_name=last_name or None,
            current_role=data.get("current_role"),
            company=data.get("company"),
            industry=data.get("industry"),
            years_experience=data.get("years_experience"),
            years_in_role=data.get("years_in_role"),
            highest_position=data.get("highest_position"),
            story=data.get("story"),
            coach_notes=data.get("coach_notes"),
            experience=experience,
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

        # Seed first missions so the user has work on day 1.
        missions = self._seed_first_missions(user_id, campaign_id)

        return {
            "userId": user_id,
            "campaignId": campaign_id,
            "profile": profile.to_dynamodb_item(),
            "missions": missions,
        }
