"""Integration tests for campaign CRUD operations.

Verifies campaign creation via onboarding, composite key queries,
user isolation, and GSI-based status queries.
"""

import uuid
from unittest.mock import patch

import pytest
from boto3.dynamodb.conditions import Key

from backend.engine.models import (
    GenerationResult,
    MissionCandidate,
    SkillGapReport,
)
from backend.handlers.onboarding.service import OnboardingService
from backend.handlers.shared.dynamodb import DynamoDBClient
from backend.handlers.shared.models import Campaign


def _mock_generation_result() -> GenerationResult:
    """Build a mock GenerationResult for generate_daily_mission."""
    return GenerationResult(
        primary=MissionCandidate(
            template_id="tmpl-1",
            category="skill_building",
            title="Campaign Test Mission",
            description="A test mission for campaign CRUD",
            rationale="Testing",
            skill_tags=["Python"],
            difficulty=1,
            estimated_minutes=15,
            expected_evidence_type="reflection",
            phase="foundation",
        ),
        alternates=[
            MissionCandidate(
                template_id=f"tmpl-alt-{i}",
                category="reflection",
                title=f"Alt Mission {i}",
                description=f"Alt test mission {i}",
                rationale="Testing",
                skill_tags=["Communication"],
                difficulty=1,
                estimated_minutes=15,
                expected_evidence_type="reflection",
                phase="foundation",
            )
            for i in range(2)
        ],
        skill_gap_report=SkillGapReport(
            skill_scores={"Python": 0.3},
            market_alignment_pct=45.0,
            priority_skills=["Python"],
            evidence_density={"Python": 0},
        ),
    )


def _onboard_user(db: DynamoDBClient, user_id: str, target_role: str = "Data Engineer") -> dict:
    """Create a user via OnboardingService with mocked mission generation."""
    with patch(
        "backend.handlers.onboarding.service.generate_daily_mission",
        return_value=_mock_generation_result(),
    ):
        service = OnboardingService(db_client=db)
        return service.create_profile(
            user_id,
            {
                "email": f"{user_id}@test.com",
                "first_name": "Test",
                "last_name": "User",
                "persona": "veteran",
                "target_role": target_role,
                "skills": ["Python", "SQL"],
            },
        )


class TestOnboardingCreatesCorrectData:
    """Tests that onboarding creates properly keyed campaign and profile."""

    def test_onboarding_creates_campaign_with_correct_keys(self, integration_tables):
        """Campaign has both userId and campaignId stored correctly."""
        db = DynamoDBClient()
        user_id = f"camp-keys-{uuid.uuid4().hex[:8]}"
        result = _onboard_user(db, user_id)

        campaign_id = result["campaignId"]

        # get_item with composite key.
        item = db.get_item("campaigns", {"userId": user_id, "campaignId": campaign_id})
        assert item is not None
        assert item["userId"] == user_id
        assert item["campaignId"] == campaign_id
        assert item["status"] == "active"
        assert item["targetRole"] == "Data Engineer"

    def test_onboarding_creates_profile(self, integration_tables):
        """Profile is created with correct fields."""
        db = DynamoDBClient()
        user_id = f"prof-{uuid.uuid4().hex[:8]}"
        result = _onboard_user(db, user_id)

        profile = db.get_item("user_profiles", {"userId": user_id})
        assert profile is not None
        assert profile["userId"] == user_id
        assert profile["name"] == "Test User"
        assert profile["persona"] == "veteran"
        assert profile["onboardingCompleted"] is True
        assert profile["targetRole"] == "Data Engineer"
        assert profile["skills"] == ["Python", "SQL"]

    def test_onboarding_seeds_missions(self, integration_tables):
        """Onboarding seeds missions (primary + alternates)."""
        db = DynamoDBClient()
        user_id = f"seed-miss-{uuid.uuid4().hex[:8]}"
        result = _onboard_user(db, user_id)

        missions = db.query_all("mission_history", Key("userId").eq(user_id))
        # 1 primary + 2 alternates = 3 missions
        assert len(missions) == 3
        assert all(m["status"] == "pending" for m in missions)


class TestCampaignCompositeKeyQueries:
    """Tests for campaign queries using composite keys."""

    def test_query_campaigns_by_user_id(self, integration_tables):
        """Campaign query by userId returns all campaigns for that user."""
        db = DynamoDBClient()
        user_id = f"query-camp-{uuid.uuid4().hex[:8]}"
        _onboard_user(db, user_id)

        campaigns = db.query_all("campaigns", Key("userId").eq(user_id))
        assert len(campaigns) == 1
        assert campaigns[0]["userId"] == user_id

    def test_get_item_requires_sort_key(self, integration_tables):
        """get_item on Campaigns with only PK should fail."""
        db = DynamoDBClient()
        user_id = f"sort-key-{uuid.uuid4().hex[:8]}"
        result = _onboard_user(db, user_id)
        campaign_id = result["campaignId"]

        # This should raise because Campaigns has a composite key.
        with pytest.raises(Exception):
            db.get_item("campaigns", {"userId": user_id})

        # With sort key, it should work.
        item = db.get_item("campaigns", {"userId": user_id, "campaignId": campaign_id})
        assert item is not None

    def test_two_users_same_campaign_id_are_isolated(self, integration_tables):
        """Two users with the same campaignId pattern are fully isolated."""
        db = DynamoDBClient()
        user_a = f"iso-a-{uuid.uuid4().hex[:8]}"
        user_b = f"iso-b-{uuid.uuid4().hex[:8]}"

        result_a = _onboard_user(db, user_a, target_role="Data Engineer")
        result_b = _onboard_user(db, user_b, target_role="ML Engineer")

        campaigns_a = db.query_all("campaigns", Key("userId").eq(user_a))
        campaigns_b = db.query_all("campaigns", Key("userId").eq(user_b))

        assert len(campaigns_a) == 1
        assert len(campaigns_b) == 1
        assert campaigns_a[0]["targetRole"] == "Data Engineer"
        assert campaigns_b[0]["targetRole"] == "ML Engineer"

    def test_multiple_campaigns_per_user(self, integration_tables):
        """A user can have multiple campaigns with different campaignIds."""
        db = DynamoDBClient()
        user_id = f"multi-camp-{uuid.uuid4().hex[:8]}"
        _onboard_user(db, user_id)

        # Manually add a second campaign.
        campaign2 = Campaign(
            user_id=user_id,
            campaign_id=f"campaign-2-{uuid.uuid4().hex[:8]}",
            title="Second Campaign",
            phase="foundation",
            status="paused",
            start_date="2026-02-01T00:00:00+00:00",
            target_role="ML Engineer",
            skills_focus=["TensorFlow"],
        )
        db.put_item("campaigns", campaign2.to_dynamodb_item())

        campaigns = db.query_all("campaigns", Key("userId").eq(user_id))
        assert len(campaigns) == 2
        statuses = {c["status"] for c in campaigns}
        assert statuses == {"active", "paused"}


class TestCampaignStatusOperations:
    """Tests for campaign status queries and updates."""

    def test_campaign_status_query_via_gsi(self, integration_tables):
        """Query campaigns by status via the status-index GSI."""
        db = DynamoDBClient()
        user_a = f"gsi-a-{uuid.uuid4().hex[:8]}"
        user_b = f"gsi-b-{uuid.uuid4().hex[:8]}"

        _onboard_user(db, user_a)
        _onboard_user(db, user_b)

        # Both campaigns are "active".
        active = db.query_all(
            "campaigns",
            Key("status").eq("active"),
            index_name="status-index",
        )
        user_ids = {c["userId"] for c in active}
        assert user_a in user_ids
        assert user_b in user_ids

    def test_campaign_status_update_via_composite_key(self, integration_tables):
        """Update campaign status using the composite key."""
        db = DynamoDBClient()
        user_id = f"status-upd-{uuid.uuid4().hex[:8]}"
        result = _onboard_user(db, user_id)
        campaign_id = result["campaignId"]

        # Update status to paused.
        db.update_item(
            "campaigns",
            key={"userId": user_id, "campaignId": campaign_id},
            updates={"status": "paused"},
        )

        item = db.get_item("campaigns", {"userId": user_id, "campaignId": campaign_id})
        assert item["status"] == "paused"

        # Verify GSI reflects the change.
        paused = db.query_all(
            "campaigns",
            Key("status").eq("paused"),
            index_name="status-index",
        )
        paused_user_ids = {c["userId"] for c in paused}
        assert user_id in paused_user_ids
