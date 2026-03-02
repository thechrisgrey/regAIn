"""Unit tests for MissionsService.complete_mission.

Validates mission completion flow including status transitions,
evidence creation, skill tag normalization, and error handling.
"""

from typing import Any, Dict

import pytest

from backend.handlers.missions.service import MissionsService
from backend.handlers.shared.dynamodb import DynamoDBClient

USER_ID = "test-user-id-123"
CAMPAIGN_ID = "campaign-001"


def _seed_mission(
    tables: Dict[str, Any],
    mission_id: str = "m-001",
    status: str = "in_progress",
    title: str = "Test Mission",
) -> None:
    """Seed a mission record into the MissionHistory table."""
    tables["mission_history"].put_item(
        Item={
            "userId": USER_ID,
            "missionId": mission_id,
            "campaignId": CAMPAIGN_ID,
            "title": title,
            "description": "A test mission.",
            "status": status,
        }
    )


class TestCompleteMission:
    """Tests for MissionsService.complete_mission."""

    def test_basic_completion_creates_evidence(self, dynamodb_tables):
        """In-progress mission transitions to completed and evidence is created."""
        _seed_mission(dynamodb_tables)
        svc = MissionsService(db_client=DynamoDBClient())

        result = svc.complete_mission(USER_ID, "m-001", {
            "reflection": "I learned Python basics.",
            "skill_tags": ["python"],
        })

        assert result["success"] is True
        assert "evidenceId" in result

        # Verify mission status updated
        mission = dynamodb_tables["mission_history"].get_item(
            Key={"userId": USER_ID, "missionId": "m-001"},
        )["Item"]
        assert mission["status"] == "completed"
        assert "completedDate" in mission

        # Verify evidence record created
        evidence = dynamodb_tables["evidence_vault"].get_item(
            Key={"userId": USER_ID, "evidenceId": result["evidenceId"]},
        )["Item"]
        assert evidence["reflection"] == "I learned Python basics."

    def test_skill_tag_normalization(self, dynamodb_tables):
        """Raw 'python' is normalized to its canonical form."""
        _seed_mission(dynamodb_tables)
        svc = MissionsService(db_client=DynamoDBClient())

        result = svc.complete_mission(USER_ID, "m-001", {
            "reflection": "Wrote a Python script.",
            "skill_tags": ["python"],
        })

        evidence = dynamodb_tables["evidence_vault"].get_item(
            Key={"userId": USER_ID, "evidenceId": result["evidenceId"]},
        )["Item"]
        # normalize_skill("python") returns "Python Programming" per taxonomy
        assert evidence["skillTag"] == "Python Programming"

    def test_unknown_skill_tag_passes_through(self, dynamodb_tables):
        """Unknown skill tags are stored as-is."""
        _seed_mission(dynamodb_tables)
        svc = MissionsService(db_client=DynamoDBClient())

        result = svc.complete_mission(USER_ID, "m-001", {
            "reflection": "Did something unique.",
            "skill_tags": ["obscure-skill-xyz-9999"],
        })

        evidence = dynamodb_tables["evidence_vault"].get_item(
            Key={"userId": USER_ID, "evidenceId": result["evidenceId"]},
        )["Item"]
        assert evidence["skillTag"] == "obscure-skill-xyz-9999"

    def test_default_general_tag_when_no_skill_tags(self, dynamodb_tables):
        """Missing skill_tags defaults to 'general'."""
        _seed_mission(dynamodb_tables)
        svc = MissionsService(db_client=DynamoDBClient())

        result = svc.complete_mission(USER_ID, "m-001", {
            "reflection": "General reflection.",
        })

        evidence = dynamodb_tables["evidence_vault"].get_item(
            Key={"userId": USER_ID, "evidenceId": result["evidenceId"]},
        )["Item"]
        assert evidence["skillTag"] == "general"

    def test_mission_not_found(self, dynamodb_tables):
        """Nonexistent mission returns error."""
        svc = MissionsService(db_client=DynamoDBClient())

        result = svc.complete_mission(USER_ID, "nonexistent-id", {
            "reflection": "Won't work.",
        })

        assert result["success"] is False
        assert "not found" in result["error"].lower() or "already completed" in result["error"].lower()

    def test_pending_mission_cannot_be_completed(self, dynamodb_tables):
        """Mission in 'pending' status cannot be completed — must be 'in_progress'."""
        _seed_mission(dynamodb_tables, status="pending")
        svc = MissionsService(db_client=DynamoDBClient())

        result = svc.complete_mission(USER_ID, "m-001", {
            "reflection": "Tried to skip ahead.",
            "skill_tags": ["leadership"],
        })

        assert result["success"] is False

    def test_already_completed_mission_rejected(self, dynamodb_tables):
        """Double-completion is rejected."""
        _seed_mission(dynamodb_tables)
        svc = MissionsService(db_client=DynamoDBClient())

        # Complete once
        result1 = svc.complete_mission(USER_ID, "m-001", {
            "reflection": "First completion.",
            "skill_tags": ["teamwork"],
        })
        assert result1["success"] is True

        # Try to complete again
        result2 = svc.complete_mission(USER_ID, "m-001", {
            "reflection": "Second attempt.",
            "skill_tags": ["teamwork"],
        })
        assert result2["success"] is False
