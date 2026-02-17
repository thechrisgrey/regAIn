"""Property-based tests for backend.engine.difficulty module.

Uses Hypothesis to validate universal properties across randomly generated inputs.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from backend.engine.difficulty import (
    ADVANCEMENT_COOLDOWN_DAYS,
    MAX_LEVEL,
    MIN_LEVEL,
    STREAK_THRESHOLD,
    compute_difficulty_state,
    should_advance,
    should_regress,
    update_difficulty,
)
from backend.engine.models import CATEGORIES, DifficultyState

# Fixed reference date for deterministic testing.
REF_DATE = datetime(2025, 6, 1, tzinfo=timezone.utc)

# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

category_st = st.sampled_from(CATEGORIES)

difficulty_level_st = st.integers(min_value=MIN_LEVEL, max_value=MAX_LEVEL)

# ISO date strings within a 2-year window before REF_DATE.
iso_date_st = st.integers(min_value=0, max_value=730).map(
    lambda days_ago: (REF_DATE - timedelta(days=days_ago)).isoformat()
)


@st.composite
def difficulty_state_st(draw: st.DrawFn) -> DifficultyState:
    """Generate a valid DifficultyState with consistent data."""
    levels = {c: draw(difficulty_level_st) for c in CATEGORIES}
    completions = {c: draw(st.integers(min_value=0, max_value=10)) for c in CATEGORIES}
    skips = {c: draw(st.integers(min_value=0, max_value=10)) for c in CATEGORIES}
    dates: dict[str, str] = {}
    for c in CATEGORIES:
        if draw(st.booleans()):
            dates[c] = draw(iso_date_st)
    return DifficultyState(
        levels=levels,
        consecutive_completions=completions,
        consecutive_skips=skips,
        last_advancement_dates=dates,
    )


@st.composite
def mission_history_st(draw: st.DrawFn) -> list[dict[str, Any]]:
    """Generate a list of mission history entries with valid categories and statuses."""
    entries = draw(st.lists(
        st.fixed_dictionaries({
            "category": category_st,
            "status": st.sampled_from(["completed", "skipped"]),
            "completedAt": iso_date_st,
        }),
        min_size=0,
        max_size=30,
    ))
    return entries


# ---------------------------------------------------------------------------
# Property 4: Difficulty levels bounded 1-5
# Feature: mission-engine, Property 4: Difficulty levels bounded 1-5
# ---------------------------------------------------------------------------


class TestProperty4DifficultyLevelsBounded:
    """**Validates: Requirements 3.1**

    For ANY DifficultyState produced by compute_difficulty_state or
    update_difficulty, all category levels shall be between 1 and 5 inclusive.
    """

    @given(history=mission_history_st())
    @settings(max_examples=200)
    def test_compute_difficulty_state_levels_bounded(
        self, history: list[dict[str, Any]]
    ) -> None:
        # Feature: mission-engine, Property 4: Difficulty levels bounded 1-5
        # **Validates: Requirements 3.1**
        state = compute_difficulty_state("user-1", history)

        for cat, level in state.levels.items():
            assert MIN_LEVEL <= level <= MAX_LEVEL, (
                f"Category '{cat}' level {level} out of bounds "
                f"[{MIN_LEVEL}, {MAX_LEVEL}]"
            )

    @given(
        state=difficulty_state_st(),
        category=category_st,
        outcome=st.sampled_from(["completed", "skipped"]),
        date=iso_date_st,
    )
    @settings(max_examples=200)
    def test_update_difficulty_levels_bounded(
        self,
        state: DifficultyState,
        category: str,
        outcome: str,
        date: str,
    ) -> None:
        # Feature: mission-engine, Property 4: Difficulty levels bounded 1-5
        # **Validates: Requirements 3.1**
        new_state = update_difficulty(state, category, outcome, date)

        for cat, level in new_state.levels.items():
            assert MIN_LEVEL <= level <= MAX_LEVEL, (
                f"Category '{cat}' level {level} out of bounds "
                f"[{MIN_LEVEL}, {MAX_LEVEL}]"
            )


# ---------------------------------------------------------------------------
# Property 5: Difficulty advances after 3 consecutive completions
# Feature: mission-engine, Property 5: Difficulty advances after 3 consecutive completions
# ---------------------------------------------------------------------------


class TestProperty5DifficultyAdvancesAfterStreak:
    """**Validates: Requirements 3.3**

    For ANY category at level L < 5 with 3 consecutive completions and no
    advancement in the last 7 days, calling update_difficulty with "completed"
    shall produce level L + 1.
    """

    @given(
        category=category_st,
        level=st.integers(min_value=MIN_LEVEL, max_value=MAX_LEVEL - 1),
    )
    @settings(max_examples=200)
    def test_advances_on_streak_threshold(self, category: str, level: int) -> None:
        # Feature: mission-engine, Property 5: Difficulty advances after 3 consecutive completions
        # **Validates: Requirements 3.3**

        # Set up state: level L, STREAK_THRESHOLD - 1 consecutive completions,
        # last advancement far in the past so cooldown is elapsed.
        old_advancement_date = (REF_DATE - timedelta(days=ADVANCEMENT_COOLDOWN_DAYS + 1)).isoformat()
        # current_date must also be far enough from old_advancement_date
        current_date = REF_DATE.isoformat()

        state = DifficultyState(
            levels={c: (level if c == category else 1) for c in CATEGORIES},
            consecutive_completions={
                c: (STREAK_THRESHOLD - 1 if c == category else 0) for c in CATEGORIES
            },
            consecutive_skips={c: 0 for c in CATEGORIES},
            last_advancement_dates={category: old_advancement_date},
        )

        new_state = update_difficulty(state, category, "completed", current_date)

        assert new_state.levels[category] == level + 1, (
            f"Expected level {level + 1} after {STREAK_THRESHOLD} completions, "
            f"got {new_state.levels[category]}"
        )


# ---------------------------------------------------------------------------
# Property 6: Difficulty regresses after 3 consecutive skips
# Feature: mission-engine, Property 6: Difficulty regresses after 3 consecutive skips
# ---------------------------------------------------------------------------


class TestProperty6DifficultyRegressesAfterSkips:
    """**Validates: Requirements 3.4**

    For ANY category at level L > 1 with 3 consecutive skips, calling
    update_difficulty with "skipped" shall produce level L - 1.
    """

    @given(
        category=category_st,
        level=st.integers(min_value=MIN_LEVEL + 1, max_value=MAX_LEVEL),
    )
    @settings(max_examples=200)
    def test_regresses_on_skip_streak_threshold(self, category: str, level: int) -> None:
        # Feature: mission-engine, Property 6: Difficulty regresses after 3 consecutive skips
        # **Validates: Requirements 3.4**

        # Set up state: level L, STREAK_THRESHOLD - 1 consecutive skips.
        state = DifficultyState(
            levels={c: (level if c == category else 1) for c in CATEGORIES},
            consecutive_completions={c: 0 for c in CATEGORIES},
            consecutive_skips={
                c: (STREAK_THRESHOLD - 1 if c == category else 0) for c in CATEGORIES
            },
            last_advancement_dates={},
        )

        current_date = REF_DATE.isoformat()
        new_state = update_difficulty(state, category, "skipped", current_date)

        assert new_state.levels[category] == level - 1, (
            f"Expected level {level - 1} after {STREAK_THRESHOLD} skips, "
            f"got {new_state.levels[category]}"
        )


# ---------------------------------------------------------------------------
# Property 7: Difficulty advancement capped at 1 per 7 days
# Feature: mission-engine, Property 7: Difficulty advancement capped at 1 per 7 days
# ---------------------------------------------------------------------------


class TestProperty7AdvancementCooldown:
    """**Validates: Requirements 3.5**

    For ANY category that was advanced within the last 7 days,
    should_advance shall return False regardless of consecutive completion count.
    """

    @given(
        category=category_st,
        level=st.integers(min_value=MIN_LEVEL, max_value=MAX_LEVEL - 1),
        completions=st.integers(min_value=STREAK_THRESHOLD, max_value=20),
        days_ago=st.integers(min_value=0, max_value=ADVANCEMENT_COOLDOWN_DAYS - 1),
    )
    @settings(max_examples=200)
    def test_should_advance_false_within_cooldown(
        self,
        category: str,
        level: int,
        completions: int,
        days_ago: int,
    ) -> None:
        # Feature: mission-engine, Property 7: Difficulty advancement capped at 1 per 7 days
        # **Validates: Requirements 3.5**

        # Last advancement was within the cooldown window (0 to 6 days ago).
        now = datetime.now(timezone.utc)
        last_advancement = (now - timedelta(days=days_ago)).isoformat()

        state = DifficultyState(
            levels={c: (level if c == category else 1) for c in CATEGORIES},
            consecutive_completions={
                c: (completions if c == category else 0) for c in CATEGORIES
            },
            consecutive_skips={c: 0 for c in CATEGORIES},
            last_advancement_dates={category: last_advancement},
        )

        result = should_advance(state, category)

        assert result is False, (
            f"should_advance returned True for category '{category}' "
            f"advanced {days_ago} days ago (within {ADVANCEMENT_COOLDOWN_DAYS}-day cooldown)"
        )
