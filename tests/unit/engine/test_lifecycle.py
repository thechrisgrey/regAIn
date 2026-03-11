"""Unit tests for backend.engine.lifecycle module."""

from datetime import datetime, timedelta, timezone

import pytest

from backend.engine.lifecycle import (
    VALID_TRANSITIONS,
    check_expired_missions,
    transition_mission,
    validate_transition,
)


NOW = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
NOW_ISO = NOW.isoformat()


def _make_mission(status: str = "generated", **kwargs) -> dict:
    mission = {"missionId": "m1", "status": status}
    mission.update(kwargs)
    return mission


# ---------------------------------------------------------------------------
# validate_transition
# ---------------------------------------------------------------------------


class TestValidateTransition:
    def test_pending_to_in_progress(self):
        assert validate_transition("pending", "in_progress") is True

    def test_pending_to_assigned(self):
        assert validate_transition("pending", "assigned") is True

    def test_pending_to_skipped(self):
        assert validate_transition("pending", "skipped") is True

    def test_pending_to_completed_invalid(self):
        assert validate_transition("pending", "completed") is False

    def test_generated_to_assigned(self):
        assert validate_transition("generated", "assigned") is True

    def test_assigned_to_in_progress(self):
        assert validate_transition("assigned", "in_progress") is True

    def test_assigned_to_skipped(self):
        assert validate_transition("assigned", "skipped") is True

    def test_assigned_to_expired(self):
        assert validate_transition("assigned", "expired") is True

    def test_in_progress_to_completed(self):
        assert validate_transition("in_progress", "completed") is True

    def test_in_progress_to_skipped(self):
        assert validate_transition("in_progress", "skipped") is True

    def test_invalid_generated_to_completed(self):
        assert validate_transition("generated", "completed") is False

    def test_invalid_completed_to_anything(self):
        assert validate_transition("completed", "assigned") is False

    def test_invalid_unknown_status(self):
        assert validate_transition("unknown", "assigned") is False

    def test_invalid_same_status(self):
        assert validate_transition("assigned", "assigned") is False


# ---------------------------------------------------------------------------
# transition_mission
# ---------------------------------------------------------------------------


class TestTransitionMission:
    def test_pending_to_in_progress_sets_started_at(self):
        mission = _make_mission("pending")
        result = transition_mission(mission, "in_progress", timestamp=NOW_ISO)

        assert result["status"] == "in_progress"
        assert result["startedAt"] == NOW_ISO

    def test_pending_to_assigned_sets_assigned_at(self):
        mission = _make_mission("pending")
        result = transition_mission(mission, "assigned", timestamp=NOW_ISO)

        assert result["status"] == "assigned"
        assert result["assignedAt"] == NOW_ISO

    def test_pending_to_completed_raises(self):
        mission = _make_mission("pending")
        with pytest.raises(ValueError, match="Invalid transition"):
            transition_mission(mission, "completed")

    def test_generated_to_assigned_sets_timestamp(self):
        mission = _make_mission("generated")
        result = transition_mission(mission, "assigned", timestamp=NOW_ISO)

        assert result["status"] == "assigned"
        assert result["assignedAt"] == NOW_ISO

    def test_assigned_to_in_progress_sets_started_at(self):
        mission = _make_mission("assigned", assignedAt=NOW_ISO)
        result = transition_mission(mission, "in_progress", timestamp=NOW_ISO)

        assert result["status"] == "in_progress"
        assert result["startedAt"] == NOW_ISO

    def test_in_progress_to_completed_sets_timestamp_and_evidence(self):
        mission = _make_mission("in_progress", startedAt=NOW_ISO)
        evidence = ["ev1", "ev2"]
        result = transition_mission(
            mission, "completed", evidence_ids=evidence, timestamp=NOW_ISO
        )

        assert result["status"] == "completed"
        assert result["completedAt"] == NOW_ISO
        assert result["evidenceIds"] == ["ev1", "ev2"]

    def test_completed_without_evidence_ids(self):
        mission = _make_mission("in_progress")
        result = transition_mission(mission, "completed", timestamp=NOW_ISO)

        assert result["status"] == "completed"
        assert result["completedAt"] == NOW_ISO
        assert "evidenceIds" not in result

    def test_assigned_to_skipped_sets_timestamp(self):
        mission = _make_mission("assigned")
        result = transition_mission(mission, "skipped", timestamp=NOW_ISO)

        assert result["status"] == "skipped"
        assert result["skippedAt"] == NOW_ISO

    def test_assigned_to_expired_sets_timestamp(self):
        mission = _make_mission("assigned")
        result = transition_mission(mission, "expired", timestamp=NOW_ISO)

        assert result["status"] == "expired"
        assert result["expiredAt"] == NOW_ISO

    def test_does_not_mutate_original(self):
        mission = _make_mission("generated")
        result = transition_mission(mission, "assigned", timestamp=NOW_ISO)

        assert mission["status"] == "generated"
        assert "assignedAt" not in mission
        assert result is not mission

    def test_preserves_existing_fields(self):
        mission = _make_mission("generated", category="reflection", difficulty=3)
        result = transition_mission(mission, "assigned", timestamp=NOW_ISO)

        assert result["category"] == "reflection"
        assert result["difficulty"] == 3

    def test_invalid_transition_raises_value_error(self):
        mission = _make_mission("generated")
        with pytest.raises(ValueError, match="Invalid transition"):
            transition_mission(mission, "completed")

    def test_error_message_includes_states(self):
        mission = _make_mission("completed")
        with pytest.raises(ValueError, match="'completed'.*'assigned'"):
            transition_mission(mission, "assigned")

    def test_uses_current_time_when_no_timestamp(self):
        mission = _make_mission("generated")
        result = transition_mission(mission, "assigned")

        assert "assignedAt" in result
        # Should be a valid ISO timestamp
        datetime.fromisoformat(result["assignedAt"])

    def test_evidence_ids_are_copied(self):
        mission = _make_mission("in_progress")
        evidence = ["ev1"]
        result = transition_mission(
            mission, "completed", evidence_ids=evidence, timestamp=NOW_ISO
        )
        evidence.append("ev2")

        assert result["evidenceIds"] == ["ev1"]


# ---------------------------------------------------------------------------
# check_expired_missions
# ---------------------------------------------------------------------------


class TestCheckExpiredMissions:
    def test_finds_expired_mission(self):
        assigned_at = (NOW - timedelta(hours=49)).isoformat()
        missions = [_make_mission("assigned", assignedAt=assigned_at)]

        expired = check_expired_missions(missions, NOW_ISO)
        assert len(expired) == 1

    def test_ignores_mission_within_window(self):
        assigned_at = (NOW - timedelta(hours=47)).isoformat()
        missions = [_make_mission("assigned", assignedAt=assigned_at)]

        expired = check_expired_missions(missions, NOW_ISO)
        assert len(expired) == 0

    def test_ignores_non_assigned_missions(self):
        old_time = (NOW - timedelta(hours=100)).isoformat()
        missions = [
            _make_mission("in_progress", assignedAt=old_time),
            _make_mission("completed", assignedAt=old_time),
            _make_mission("generated"),
        ]

        expired = check_expired_missions(missions, NOW_ISO)
        assert len(expired) == 0

    def test_ignores_assigned_without_timestamp(self):
        missions = [_make_mission("assigned")]

        expired = check_expired_missions(missions, NOW_ISO)
        assert len(expired) == 0

    def test_empty_list(self):
        assert check_expired_missions([], NOW_ISO) == []

    def test_exactly_48_hours_not_expired(self):
        assigned_at = (NOW - timedelta(hours=48)).isoformat()
        missions = [_make_mission("assigned", assignedAt=assigned_at)]

        expired = check_expired_missions(missions, NOW_ISO)
        assert len(expired) == 0

    def test_mixed_missions(self):
        old = (NOW - timedelta(hours=50)).isoformat()
        recent = (NOW - timedelta(hours=10)).isoformat()
        missions = [
            _make_mission("assigned", missionId="m1", assignedAt=old),
            _make_mission("assigned", missionId="m2", assignedAt=recent),
            _make_mission("in_progress", missionId="m3", assignedAt=old),
        ]

        expired = check_expired_missions(missions, NOW_ISO)
        assert len(expired) == 1
        assert expired[0]["missionId"] == "m1"

    def test_custom_expiry_hours(self):
        assigned_at = (NOW - timedelta(hours=25)).isoformat()
        missions = [_make_mission("assigned", assignedAt=assigned_at)]

        expired = check_expired_missions(missions, NOW_ISO, expiry_hours=24)
        assert len(expired) == 1
