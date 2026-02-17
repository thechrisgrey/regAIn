"""Property-based tests for backend.engine.lifecycle module.

Uses Hypothesis to validate universal properties across randomly generated inputs.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from backend.engine.lifecycle import (
    VALID_TRANSITIONS,
    check_expired_missions,
    transition_mission,
    validate_transition,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALL_STATUSES = ["generated", "assigned", "in_progress", "completed", "skipped", "expired"]
REF_TIME = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)

# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

status_st = st.sampled_from(ALL_STATUSES)
mission_id_st = st.from_regex(r"m[0-9a-z]{1,8}", fullmatch=True)
evidence_id_st = st.from_regex(r"ev[0-9a-z]{1,8}", fullmatch=True)
iso_timestamp_st = st.integers(min_value=0, max_value=365).map(
    lambda days: (REF_TIME - timedelta(days=days)).isoformat()
)


@st.composite
def mission_dict(draw: st.DrawFn, status: str | None = None) -> dict[str, Any]:
    """Generate a mission dict with a given or random status."""
    s = status if status is not None else draw(status_st)
    mission: dict[str, Any] = {
        "missionId": draw(mission_id_st),
        "status": s,
    }
    if s in ("assigned", "in_progress", "completed", "skipped", "expired"):
        mission["assignedAt"] = draw(iso_timestamp_st)
    if s in ("in_progress", "completed"):
        mission["startedAt"] = draw(iso_timestamp_st)
    return mission


# ---------------------------------------------------------------------------
# Property 16: State transitions match valid transition map
# Feature: mission-engine, Property 16: State transitions match valid transition map
# ---------------------------------------------------------------------------


class TestProperty16StateTransitionsMatchValidMap:
    """**Validates: Requirements 6.1, 6.2**

    For ANY mission in state S and target state T, the transition succeeds
    if and only if T is in VALID_TRANSITIONS[S]. Invalid transitions raise
    ValueError.
    """

    @given(current=status_st, target=status_st)
    @settings(max_examples=200)
    def test_valid_transitions_succeed_invalid_raise(
        self, current: str, target: str
    ) -> None:
        # Feature: mission-engine, Property 16: State transitions match valid transition map
        # **Validates: Requirements 6.1, 6.2**
        allowed = VALID_TRANSITIONS.get(current, set())
        is_valid = target in allowed

        # validate_transition must agree with the map
        assert validate_transition(current, target) == is_valid

        # transition_mission must succeed or raise accordingly
        mission = {"missionId": "test", "status": current}
        if current in ("assigned", "in_progress", "completed", "skipped", "expired"):
            mission["assignedAt"] = REF_TIME.isoformat()
        if current in ("in_progress", "completed"):
            mission["startedAt"] = REF_TIME.isoformat()

        if is_valid:
            result = transition_mission(
                mission, target, timestamp=REF_TIME.isoformat()
            )
            assert result["status"] == target
        else:
            with pytest.raises(ValueError, match="Invalid transition"):
                transition_mission(mission, target, timestamp=REF_TIME.isoformat())

    @given(current=status_st)
    @settings(max_examples=200)
    def test_terminal_states_reject_all_transitions(self, current: str) -> None:
        """States not in VALID_TRANSITIONS keys are terminal — all targets rejected."""
        # Feature: mission-engine, Property 16: State transitions match valid transition map
        # **Validates: Requirements 6.1, 6.2**
        assume(current not in VALID_TRANSITIONS)

        for target in ALL_STATUSES:
            assert validate_transition(current, target) is False


# ---------------------------------------------------------------------------
# Property 17: Transitions produce correct timestamps and linked data
# Feature: mission-engine, Property 17: Transitions produce correct timestamps and linked data
# ---------------------------------------------------------------------------


class TestProperty17TransitionsProduceCorrectTimestampsAndData:
    """**Validates: Requirements 6.3, 6.4**

    For ANY valid transition to "assigned", the resulting mission has an
    assignedAt timestamp. For ANY valid transition to "completed", the
    resulting mission has a completedAt timestamp and evidenceIds linked.
    """

    @given(data=mission_dict(status="generated"), ts=iso_timestamp_st)
    @settings(max_examples=200)
    def test_transition_to_assigned_sets_assigned_at(
        self, data: dict[str, Any], ts: str
    ) -> None:
        # Feature: mission-engine, Property 17: Transitions produce correct timestamps and linked data
        # **Validates: Requirements 6.3, 6.4**
        result = transition_mission(data, "assigned", timestamp=ts)
        assert result["status"] == "assigned"
        assert result["assignedAt"] == ts

    @given(
        data=mission_dict(status="in_progress"),
        ts=iso_timestamp_st,
        evidence=st.lists(evidence_id_st, min_size=1, max_size=5),
    )
    @settings(max_examples=200)
    def test_transition_to_completed_sets_timestamp_and_evidence(
        self, data: dict[str, Any], ts: str, evidence: list[str]
    ) -> None:
        # Feature: mission-engine, Property 17: Transitions produce correct timestamps and linked data
        # **Validates: Requirements 6.3, 6.4**
        result = transition_mission(
            data, "completed", evidence_ids=evidence, timestamp=ts
        )
        assert result["status"] == "completed"
        assert result["completedAt"] == ts
        assert result["evidenceIds"] == evidence

    @given(
        data=mission_dict(status="in_progress"),
        ts=iso_timestamp_st,
        evidence=st.lists(evidence_id_st, min_size=1, max_size=5),
    )
    @settings(max_examples=200)
    def test_completed_evidence_ids_are_independent_copy(
        self, data: dict[str, Any], ts: str, evidence: list[str]
    ) -> None:
        """evidenceIds in the result must not be the same list object as the input."""
        # Feature: mission-engine, Property 17: Transitions produce correct timestamps and linked data
        # **Validates: Requirements 6.3, 6.4**
        result = transition_mission(
            data, "completed", evidence_ids=evidence, timestamp=ts
        )
        assert result["evidenceIds"] is not evidence
        assert result["evidenceIds"] == evidence


# ---------------------------------------------------------------------------
# Property 18: Expiry detection for 48-hour assigned missions
# Feature: mission-engine, Property 18: Expiry detection for 48-hour assigned missions
# ---------------------------------------------------------------------------


class TestProperty18ExpiryDetection48Hours:
    """**Validates: Requirements 6.5**

    For ANY assigned mission where elapsed time since assignedAt exceeds
    48 hours, check_expired_missions shall include it. For ANY assigned
    mission where elapsed time is 48 hours or less, it shall not be included.
    """

    @given(
        hours_past=st.floats(
            min_value=48.001, max_value=720.0, allow_nan=False, allow_infinity=False
        ),
    )
    @settings(max_examples=200)
    def test_assigned_beyond_48h_is_expired(self, hours_past: float) -> None:
        # Feature: mission-engine, Property 18: Expiry detection for 48-hour assigned missions
        # **Validates: Requirements 6.5**
        assigned_at = REF_TIME - timedelta(hours=hours_past)
        mission = {
            "missionId": "m1",
            "status": "assigned",
            "assignedAt": assigned_at.isoformat(),
        }

        expired = check_expired_missions([mission], REF_TIME.isoformat())
        assert len(expired) == 1
        assert expired[0]["missionId"] == "m1"

    @given(
        hours_within=st.floats(
            min_value=0.0, max_value=48.0, allow_nan=False, allow_infinity=False
        ),
    )
    @settings(max_examples=200)
    def test_assigned_within_48h_is_not_expired(self, hours_within: float) -> None:
        # Feature: mission-engine, Property 18: Expiry detection for 48-hour assigned missions
        # **Validates: Requirements 6.5**
        assigned_at = REF_TIME - timedelta(hours=hours_within)
        mission = {
            "missionId": "m1",
            "status": "assigned",
            "assignedAt": assigned_at.isoformat(),
        }

        expired = check_expired_missions([mission], REF_TIME.isoformat())
        assert len(expired) == 0

    @given(
        non_assigned_status=st.sampled_from(
            ["generated", "in_progress", "completed", "skipped", "expired"]
        ),
        hours_past=st.floats(
            min_value=49.0, max_value=720.0, allow_nan=False, allow_infinity=False
        ),
    )
    @settings(max_examples=200)
    def test_non_assigned_missions_never_expire(
        self, non_assigned_status: str, hours_past: float
    ) -> None:
        """Only missions in 'assigned' status can be detected as expired."""
        # Feature: mission-engine, Property 18: Expiry detection for 48-hour assigned missions
        # **Validates: Requirements 6.5**
        assigned_at = REF_TIME - timedelta(hours=hours_past)
        mission = {
            "missionId": "m1",
            "status": non_assigned_status,
            "assignedAt": assigned_at.isoformat(),
        }

        expired = check_expired_missions([mission], REF_TIME.isoformat())
        assert len(expired) == 0
