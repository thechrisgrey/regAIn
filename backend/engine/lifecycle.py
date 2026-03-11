"""Mission lifecycle state machine.

Manages valid state transitions for missions, applies timestamps and
evidence linking on transitions, and detects expired assigned missions.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

VALID_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"in_progress", "assigned", "skipped"},
    "generated": {"assigned"},
    "assigned": {"in_progress", "skipped", "expired"},
    "in_progress": {"completed", "skipped"},
}


def validate_transition(current_status: str, target_status: str) -> bool:
    """Check if a state transition is valid.

    Args:
        current_status: The mission's current status.
        target_status: The desired target status.

    Returns:
        True if the transition is allowed, False otherwise.
    """
    allowed = VALID_TRANSITIONS.get(current_status, set())
    return target_status in allowed


def transition_mission(
    mission: dict[str, Any],
    target_status: str,
    evidence_ids: list[str] | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Apply a state transition to a mission dict.

    Returns a new dict with updated status and appropriate timestamps.
    Does not mutate the original mission dict.

    Args:
        mission: The mission dict containing at least a "status" key.
        target_status: The desired target status.
        evidence_ids: Evidence IDs to link when transitioning to completed.
        timestamp: ISO timestamp to use. Defaults to current UTC time.

    Returns:
        A new mission dict with the updated status and timestamps.

    Raises:
        ValueError: If the transition is not valid per VALID_TRANSITIONS.
    """
    current_status = mission.get("status", "")
    if not validate_transition(current_status, target_status):
        raise ValueError(
            f"Invalid transition from '{current_status}' to '{target_status}'"
        )

    ts = timestamp or datetime.now(timezone.utc).isoformat()
    updated = dict(mission)
    updated["status"] = target_status

    if target_status == "assigned":
        updated["assignedAt"] = ts
    elif target_status == "in_progress":
        updated["startedAt"] = ts
    elif target_status == "completed":
        updated["completedAt"] = ts
        if evidence_ids is not None:
            updated["evidenceIds"] = list(evidence_ids)
    elif target_status == "skipped":
        updated["skippedAt"] = ts
    elif target_status == "expired":
        updated["expiredAt"] = ts

    return updated


def check_expired_missions(
    missions: list[dict[str, Any]],
    current_time: str,
    expiry_hours: int = 48,
) -> list[dict[str, Any]]:
    """Identify missions that should transition to expired status.

    A mission is considered expired if it is in "assigned" status and
    the elapsed time since its assignedAt timestamp exceeds expiry_hours.

    Args:
        missions: List of mission dicts.
        current_time: ISO timestamp representing the current time.
        expiry_hours: Number of hours after which an assigned mission expires.

    Returns:
        List of mission dicts that have exceeded the expiry window.
    """
    now = datetime.fromisoformat(current_time)
    expired: list[dict[str, Any]] = []

    for mission in missions:
        if mission.get("status") != "assigned":
            continue
        assigned_at = mission.get("assignedAt")
        if not assigned_at:
            continue
        assigned_dt = datetime.fromisoformat(assigned_at)
        elapsed_hours = (now - assigned_dt).total_seconds() / 3600
        if elapsed_hours > expiry_hours:
            expired.append(mission)

    return expired
