"""Difficulty scaling model for the Mission Engine.

Tracks per-category difficulty levels (1–5) for each user and determines
when to advance or regress based on completion and skip patterns. Filters
mission candidates to those within an appropriate difficulty range.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from backend.engine.models import CATEGORIES, DifficultyState, MissionCandidate

# Consecutive outcomes needed to trigger a level change.
STREAK_THRESHOLD = 3

# Minimum days between difficulty advancements per category.
ADVANCEMENT_COOLDOWN_DAYS = 7

# Difficulty bounds.
MIN_LEVEL = 1
MAX_LEVEL = 5


def compute_difficulty_state(
    user_id: str,
    mission_history: list[dict[str, Any]],
) -> DifficultyState:
    """Compute current difficulty levels from mission history.

    Scans mission history to determine per-category levels, consecutive
    completion/skip streaks, and last advancement dates. Missions are
    processed in chronological order (by ``completedAt`` or ``updatedAt``).

    New users (empty history) start at level 1 for all categories.

    Args:
        user_id: The user identifier (reserved for future per-user caching).
        mission_history: List of mission dicts. Each should contain at least
            ``category``, ``status`` ("completed" or "skipped"), and a
            timestamp key (``completedAt`` or ``updatedAt``) for ordering.

    Returns:
        A DifficultyState reflecting the user's current standing.
    """
    state = DifficultyState()

    if not mission_history:
        return state

    # Sort by timestamp so we replay events in order.
    def _sort_key(m: dict[str, Any]) -> str:
        return m.get("completedAt") or m.get("updatedAt") or ""

    sorted_history = sorted(mission_history, key=_sort_key)

    for mission in sorted_history:
        category = mission.get("category", "")
        status = mission.get("status", "")

        if category not in state.levels:
            continue
        if status not in ("completed", "skipped"):
            continue

        date_str = mission.get("completedAt") or mission.get("updatedAt") or ""
        state = update_difficulty(state, category, status, date_str)

    return state


def should_advance(state: DifficultyState, category: str) -> bool:
    """Check if a category should advance difficulty.

    Requires 3 consecutive completions AND no advancement in the last 7 days.

    Args:
        state: Current difficulty state.
        category: The mission category to check.

    Returns:
        True if the category qualifies for advancement.
    """
    if state.levels.get(category, MIN_LEVEL) >= MAX_LEVEL:
        return False

    if state.consecutive_completions.get(category, 0) < STREAK_THRESHOLD:
        return False

    last_date_str = state.last_advancement_dates.get(category, "")
    if last_date_str:
        try:
            last_date = datetime.fromisoformat(last_date_str)
            if last_date.tzinfo is None:
                last_date = last_date.replace(tzinfo=timezone.utc)
            cooldown_end = last_date + timedelta(days=ADVANCEMENT_COOLDOWN_DAYS)
            if datetime.now(timezone.utc) < cooldown_end:
                return False
        except (ValueError, TypeError):
            pass

    return True


def should_regress(state: DifficultyState, category: str) -> bool:
    """Check if a category should regress difficulty.

    Requires 3 consecutive skips.

    Args:
        state: Current difficulty state.
        category: The mission category to check.

    Returns:
        True if the category qualifies for regression.
    """
    if state.levels.get(category, MIN_LEVEL) <= MIN_LEVEL:
        return False

    return state.consecutive_skips.get(category, 0) >= STREAK_THRESHOLD


def update_difficulty(
    state: DifficultyState,
    category: str,
    outcome: str,
    current_date: str,
) -> DifficultyState:
    """Return a new DifficultyState reflecting the outcome.

    Updates streak counters and applies level changes when thresholds are met.
    A "completed" outcome increments the completion streak and resets skips.
    A "skipped" outcome increments the skip streak and resets completions.

    Args:
        state: Current difficulty state (not mutated).
        category: The mission category.
        outcome: "completed" or "skipped".
        current_date: ISO-format date string for cooldown tracking.

    Returns:
        A new DifficultyState with updated levels and streaks.
    """
    # Deep-copy the state to avoid mutation.
    new_levels = dict(state.levels)
    new_completions = dict(state.consecutive_completions)
    new_skips = dict(state.consecutive_skips)
    new_dates = dict(state.last_advancement_dates)

    if category not in new_levels:
        return state

    if outcome == "completed":
        new_completions[category] = new_completions.get(category, 0) + 1
        new_skips[category] = 0

        # Check advancement: 3 consecutive completions + cooldown.
        if new_completions[category] >= STREAK_THRESHOLD and new_levels[category] < MAX_LEVEL:
            if _cooldown_elapsed(new_dates.get(category, ""), current_date):
                new_levels[category] += 1
                new_completions[category] = 0
                new_dates[category] = current_date

    elif outcome == "skipped":
        new_skips[category] = new_skips.get(category, 0) + 1
        new_completions[category] = 0

        # Check regression: 3 consecutive skips.
        if new_skips[category] >= STREAK_THRESHOLD and new_levels[category] > MIN_LEVEL:
            new_levels[category] -= 1
            new_skips[category] = 0

    return DifficultyState(
        levels=new_levels,
        consecutive_completions=new_completions,
        consecutive_skips=new_skips,
        last_advancement_dates=new_dates,
    )


def filter_by_difficulty(
    candidates: list[MissionCandidate],
    state: DifficultyState,
) -> list[MissionCandidate]:
    """Filter candidates to those within ±1 of user's level per category.

    Each candidate is checked against the user's difficulty level for that
    candidate's category. Candidates whose difficulty is within 1 level
    (inclusive) of the user's level are kept.

    Args:
        candidates: List of mission candidates to filter.
        state: Current difficulty state with per-category levels.

    Returns:
        Filtered list of candidates within the acceptable difficulty range.
    """
    result: list[MissionCandidate] = []
    for candidate in candidates:
        user_level = state.levels.get(candidate.category, MIN_LEVEL)
        if abs(candidate.difficulty - user_level) <= 1:
            result.append(candidate)
    return result


def _cooldown_elapsed(last_advancement_date: str, current_date: str) -> bool:
    """Check whether the 7-day cooldown has elapsed since last advancement.

    Args:
        last_advancement_date: ISO date of last advancement, or empty string.
        current_date: ISO date to compare against.

    Returns:
        True if cooldown has elapsed or no prior advancement exists.
    """
    if not last_advancement_date:
        return True

    try:
        last_dt = datetime.fromisoformat(last_advancement_date)
        current_dt = datetime.fromisoformat(current_date)

        # Normalize to UTC if no timezone info.
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
        if current_dt.tzinfo is None:
            current_dt = current_dt.replace(tzinfo=timezone.utc)

        return current_dt >= last_dt + timedelta(days=ADVANCEMENT_COOLDOWN_DAYS)
    except (ValueError, TypeError):
        # Unparseable dates — allow advancement.
        return True
