"""Integration tests for mission lifecycle.

Verifies full mission lifecycle through handler -> service -> DynamoDB
round-trips with composite key validation.
"""

import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest
from boto3.dynamodb.conditions import Key

from backend.engine.models import (
    GenerationResult,
    MissionCandidate,
    SkillGapReport,
)
from backend.handlers.missions.service import MissionsService, _GenerateRateLimitExceeded
from backend.handlers.shared.dynamodb import DynamoDBClient
from backend.handlers.shared.models import Mission


def _make_mission(user_id: str, campaign_id: str, status: str = "pending") -> Mission:
    """Build a Mission model with a random ID."""
    return Mission(
        user_id=user_id,
        mission_id=str(uuid.uuid4()),
        campaign_id=campaign_id,
        title=f"Mission {uuid.uuid4().hex[:6]}",
        description="Test mission description",
        status=status,
    )


def _mock_generation_result() -> GenerationResult:
    """Build a mock GenerationResult for generate_daily_mission."""
    return GenerationResult(
        primary=MissionCandidate(
            template_id="tmpl-gen",
            category="skill_building",
            title="Generated Mission",
            description="A generated test mission",
            rationale="Testing generation",
            skill_tags=["Python"],
            difficulty=2,
            estimated_minutes=20,
            expected_evidence_type="artifact",
            phase="foundation",
        ),
        alternates=[
            MissionCandidate(
                template_id=f"tmpl-alt-{i}",
                category="reflection",
                title=f"Alternate Mission {i}",
                description=f"Alternate test mission {i}",
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
            skill_scores={"Python": 0.4},
            market_alignment_pct=50.0,
            priority_skills=["Python"],
            evidence_density={"Python": 1},
        ),
    )


class TestMissionListing:
    """Tests for listing missions with isolation and filtering."""

    def test_list_returns_all_user_missions(self, seeded_user, integration_tables):
        """Seed 3 missions for user-A, 2 for user-B. Verify isolation."""
        db = DynamoDBClient()
        user_a = seeded_user["user_id"]
        campaign_a = seeded_user["campaign_id"]

        # user-A already has 3 seeded missions from onboarding.
        # Create 2 missions for user-B.
        user_b = f"user-b-{uuid.uuid4().hex[:8]}"
        for _ in range(2):
            m = _make_mission(user_b, "campaign-b")
            db.put_item("mission_history", m.to_dynamodb_item())

        service = MissionsService(db_client=db)

        page_a = service.list_missions(user_a)
        page_b = service.list_missions(user_b)

        assert len(page_a["items"]) == 3
        assert len(page_b["items"]) == 2
        # All missions for user-A belong to user-A.
        assert all(m["userId"] == user_a for m in page_a["items"])
        assert all(m["userId"] == user_b for m in page_b["items"])

    def test_list_with_status_filter(self, seeded_user, integration_tables):
        """Seed mixed statuses, filter by pending."""
        db = DynamoDBClient()
        user_id = seeded_user["user_id"]
        campaign_id = seeded_user["campaign_id"]

        # Seeded missions are all "pending". Add an in_progress one.
        ip_mission = _make_mission(user_id, campaign_id, status="in_progress")
        db.put_item("mission_history", ip_mission.to_dynamodb_item())

        service = MissionsService(db_client=db)

        pending = service.list_missions(user_id, status="pending")
        in_progress = service.list_missions(user_id, status="in_progress")

        assert len(pending["items"]) == 3  # 3 from onboarding
        assert len(in_progress["items"]) == 1
        assert in_progress["items"][0]["missionId"] == ip_mission.mission_id

    def test_list_uses_query_all_pagination(self, integration_tables):
        """Seed 30+ missions to verify query_all follows pagination."""
        db = DynamoDBClient()
        user_id = f"paginate-user-{uuid.uuid4().hex[:8]}"

        for i in range(35):
            m = _make_mission(user_id, "campaign-page")
            db.put_item("mission_history", m.to_dynamodb_item())

        service = MissionsService(db_client=db)
        # With pagination, fetch all pages to verify total count.
        page = service.list_missions(user_id, limit=200)

        assert len(page["items"]) == 35


class TestMissionCompletion:
    """Tests for completing missions and evidence creation."""

    def test_complete_updates_status_via_composite_key(self, seeded_user, integration_tables):
        """Complete then get_item with BOTH userId AND missionId."""
        db = DynamoDBClient()
        user_id = seeded_user["user_id"]

        # Get a seeded mission to complete.
        missions = db.query_all(
            "mission_history",
            Key("userId").eq(user_id),
        )
        target = missions[0]
        mission_id = target["missionId"]

        # First transition to in_progress (service.complete_mission skips lifecycle check).
        db.update_item(
            "mission_history",
            key={"userId": user_id, "missionId": mission_id},
            updates={"status": "in_progress"},
        )

        service = MissionsService(db_client=db)
        result = service.complete_mission(
            user_id,
            mission_id,
            {"reflection": "Done!", "skill_tags": ["Python"]},
        )

        assert result["success"] is True

        # Verify via composite key get_item.
        item = db.get_item(
            "mission_history",
            {"userId": user_id, "missionId": mission_id},
        )
        assert item is not None
        assert item["status"] == "completed"
        assert "completedDate" in item
        assert item["evidenceId"] == result["evidenceId"]

    def test_complete_creates_evidence_in_evidence_vault(self, seeded_user, integration_tables):
        """Verify evidence record after completion."""
        db = DynamoDBClient()
        user_id = seeded_user["user_id"]

        missions = db.query_all("mission_history", Key("userId").eq(user_id))
        target = missions[0]
        mission_id = target["missionId"]

        db.update_item(
            "mission_history",
            key={"userId": user_id, "missionId": mission_id},
            updates={"status": "in_progress"},
        )

        service = MissionsService(db_client=db)
        result = service.complete_mission(
            user_id,
            mission_id,
            {"reflection": "Learned a lot", "skill_tags": ["Python"]},
        )

        # Evidence should exist in the vault.
        evidence = db.query_all("evidence_vault", Key("userId").eq(user_id))
        assert len(evidence) == 1
        assert evidence[0]["missionId"] == mission_id
        assert evidence[0]["reflection"] == "Learned a lot"
        assert evidence[0]["skillTag"] == "Python"

    def test_complete_evidence_has_correct_composite_key(self, seeded_user, integration_tables):
        """get_item on EvidenceVault with userId + evidenceId."""
        db = DynamoDBClient()
        user_id = seeded_user["user_id"]

        missions = db.query_all("mission_history", Key("userId").eq(user_id))
        target = missions[1]
        mission_id = target["missionId"]

        db.update_item(
            "mission_history",
            key={"userId": user_id, "missionId": mission_id},
            updates={"status": "in_progress"},
        )

        service = MissionsService(db_client=db)
        result = service.complete_mission(
            user_id,
            mission_id,
            {"reflection": "Composite key test", "skill_tags": ["SQL"]},
        )

        evidence_id = result["evidenceId"]

        # Must use BOTH keys.
        item = db.get_item(
            "evidence_vault",
            {"userId": user_id, "evidenceId": evidence_id},
        )
        assert item is not None
        assert item["userId"] == user_id
        assert item["evidenceId"] == evidence_id
        assert item["skillTag"] == "SQL"


class TestMissionGeneration:
    """Tests for mission generation and rate limiting."""

    def test_generate_creates_mission_in_table(self, seeded_user, integration_tables):
        """Mock generate_daily_mission, verify new mission exists."""
        db = DynamoDBClient()
        user_id = seeded_user["user_id"]

        # Count existing missions before generation.
        before = db.query_all("mission_history", Key("userId").eq(user_id))
        before_count = len(before)

        mock_result = _mock_generation_result()

        with patch(
            "backend.handlers.missions.service.generate_daily_mission",
            return_value=mock_result,
        ):
            service = MissionsService(db_client=db)
            result = service.generate_mission(user_id)

        assert "mission" in result
        assert result["mission"]["title"] == "Generated Mission"

        after = db.query_all("mission_history", Key("userId").eq(user_id))
        assert len(after) == before_count + 1

    def test_generate_rate_limit_enforced(self, seeded_user, integration_tables):
        """Call generate 6 times (limit), verify 7th fails."""
        db = DynamoDBClient()
        user_id = seeded_user["user_id"]

        mock_result = _mock_generation_result()

        with patch(
            "backend.handlers.missions.service.generate_daily_mission",
            return_value=mock_result,
        ):
            service = MissionsService(db_client=db)

            for i in range(6):
                result = service.generate_mission(user_id)
                assert "mission" in result, f"Generation {i+1} should succeed"

            with pytest.raises(_GenerateRateLimitExceeded):
                service.generate_mission(user_id)

    def test_generate_rate_limit_resets_on_new_day(self, seeded_user, integration_tables):
        """Manually update lastWebMissionGenDate to yesterday, then generate succeeds."""
        db = DynamoDBClient()
        user_id = seeded_user["user_id"]

        mock_result = _mock_generation_result()

        with patch(
            "backend.handlers.missions.service.generate_daily_mission",
            return_value=mock_result,
        ):
            service = MissionsService(db_client=db)

            # Exhaust the daily limit.
            for _ in range(6):
                service.generate_mission(user_id)

            with pytest.raises(_GenerateRateLimitExceeded):
                service.generate_mission(user_id)

            # Simulate date rollover by setting lastWebMissionGenDate to yesterday.
            yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
            db.update_item(
                "user_profiles",
                key={"userId": user_id},
                updates={"lastWebMissionGenDate": yesterday},
            )

            # Should succeed again.
            result = service.generate_mission(user_id)
            assert "mission" in result

    def test_generate_daily_remaining_decrements(self, seeded_user, integration_tables):
        """Verify dailyRemaining decreases with each generation."""
        db = DynamoDBClient()
        user_id = seeded_user["user_id"]

        mock_result = _mock_generation_result()

        with patch(
            "backend.handlers.missions.service.generate_daily_mission",
            return_value=mock_result,
        ):
            service = MissionsService(db_client=db)

            remaining_before = service.get_daily_remaining(user_id)
            assert remaining_before["dailyRemaining"] == 6

            service.generate_mission(user_id)

            remaining_after = service.get_daily_remaining(user_id)
            assert remaining_after["dailyRemaining"] == 5
