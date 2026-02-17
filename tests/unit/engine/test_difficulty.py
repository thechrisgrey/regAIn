"""Unit tests for backend.engine.difficulty module."""

from datetime import datetime, timedelta, timezone

import pytest

from backend.engine.difficulty import (
    ADVANCEMENT_COOLDOWN_DAYS,
    MAX_LEVEL,
    MIN_LEVEL,
    STREAK_THRESHOLD,
    compute_difficulty_state,
    filter_by_difficulty,
    should_advance,
    should_regress,
    update_difficulty,
)
from backend.engine.models import CATEGORIES, DifficultyState, MissionCandidate


NOW = datetime(2025, 6, 15, tzinfo=timezone.utc)
NOW_ISO = NOW.isoformat()
OLD_DATE = (NOW - timedelta(days=30)).isoformat()


def _make_candidate(category: str = "reflection", difficulty: int = 1) -> MissionCandidate:
    return MissionCandidate(
        template_id="t1",
        category=category,
        title="Test",
        description="Test desc",
        rationale="Test rationale",
        skill_tags=["python"],
        difficulty=difficulty,
        estimated_minutes=20,
        expected_evidence_type="reflection",
        phase="foundation",
    )


# ---------------------------------------------------------------------------
# compute_difficulty_state
# ---------------------------------------------------------------------------

class TestComputeDifficultyState:
    def test_empty_history_returns_defaults(self):
        state = compute_difficulty_state("user1", [])
        for cat in CATEGORIES:
            assert state.levels[cat] == 1
            assert state.consecutive_completions[cat] == 0
            assert state.consecutive_skips[cat] == 0

    def test_three_completions_advances_level(self):
        history = [
            {"category": "reflection", "status": "completed", "completedAt": OLD_DATE},
            {"category": "reflection", "status": "completed", "completedAt": OLD_DATE},
            {"category": "reflection", "status": "completed", "completedAt": OLD_DATE},
        ]
        state = compute_difficulty_state("user1", history)
        assert state.levels["reflection"] == 2

    def test_three_skips_regresses_level(self):
        # First advance to level 2, then skip 3 times.
        history = [
            {"category": "reflection", "status": "completed", "completedAt": OLD_DATE},
            {"category": "reflection", "status": "completed", "completedAt": OLD_DATE},
            {"category": "reflection", "status": "completed", "completedAt": OLD_DATE},
            {"category": "reflection", "status": "skipped", "updatedAt": NOW_ISO},
            {"category": "reflection", "status": "skipped", "updatedAt": NOW_ISO},
            {"category": "reflection", "status": "skipped", "updatedAt": NOW_ISO},
        ]
        state = compute_difficulty_state("user1", history)
        assert state.levels["reflection"] == 1

    def test_ignores_unknown_categories(self):
        history = [
            {"category": "unknown_cat", "status": "completed", "completedAt": NOW_ISO},
        ]
        state = compute_difficulty_state("user1", history)
        for cat in CATEGORIES:
            assert state.levels[cat] == 1

    def test_ignores_non_terminal_statuses(self):
        history = [
            {"category": "reflection", "status": "in_progress", "updatedAt": NOW_ISO},
            {"category": "reflection", "status": "assigned", "updatedAt": NOW_ISO},
        ]
        state = compute_difficulty_state("user1", history)
        assert state.consecutive_completions["reflection"] == 0


# ---------------------------------------------------------------------------
# should_advance
# ---------------------------------------------------------------------------

class TestShouldAdvance:
    def test_advances_with_streak_and_cooldown(self):
        state = DifficultyState(
            levels={"reflection": 2},
            consecutive_completions={"reflection": 3},
            consecutive_skips={"reflection": 0},
            last_advancement_dates={"reflection": OLD_DATE},
        )
        assert should_advance(state, "reflection") is True

    def test_no_advance_below_streak_threshold(self):
        state = DifficultyState(
            levels={"reflection": 2},
            consecutive_completions={"reflection": 2},
            consecutive_skips={"reflection": 0},
            last_advancement_dates={},
        )
        assert should_advance(state, "reflection") is False

    def test_no_advance_at_max_level(self):
        state = DifficultyState(
            levels={"reflection": MAX_LEVEL},
            consecutive_completions={"reflection": 5},
            consecutive_skips={"reflection": 0},
            last_advancement_dates={},
        )
        assert should_advance(state, "reflection") is False

    def test_no_advance_within_cooldown(self):
        recent = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        state = DifficultyState(
            levels={"reflection": 2},
            consecutive_completions={"reflection": 3},
            consecutive_skips={"reflection": 0},
            last_advancement_dates={"reflection": recent},
        )
        assert should_advance(state, "reflection") is False

    def test_advances_with_no_prior_advancement(self):
        state = DifficultyState(
            levels={"reflection": 1},
            consecutive_completions={"reflection": 3},
            consecutive_skips={"reflection": 0},
            last_advancement_dates={},
        )
        assert should_advance(state, "reflection") is True


# ---------------------------------------------------------------------------
# should_regress
# ---------------------------------------------------------------------------

class TestShouldRegress:
    def test_regresses_with_skip_streak(self):
        state = DifficultyState(
            levels={"reflection": 3},
            consecutive_completions={"reflection": 0},
            consecutive_skips={"reflection": 3},
        )
        assert should_regress(state, "reflection") is True

    def test_no_regress_below_threshold(self):
        state = DifficultyState(
            levels={"reflection": 3},
            consecutive_completions={"reflection": 0},
            consecutive_skips={"reflection": 2},
        )
        assert should_regress(state, "reflection") is False

    def test_no_regress_at_min_level(self):
        state = DifficultyState(
            levels={"reflection": MIN_LEVEL},
            consecutive_completions={"reflection": 0},
            consecutive_skips={"reflection": 5},
        )
        assert should_regress(state, "reflection") is False


# ---------------------------------------------------------------------------
# update_difficulty
# ---------------------------------------------------------------------------

class TestUpdateDifficulty:
    def test_completion_increments_streak(self):
        state = DifficultyState()
        new_state = update_difficulty(state, "reflection", "completed", NOW_ISO)
        assert new_state.consecutive_completions["reflection"] == 1
        assert new_state.consecutive_skips["reflection"] == 0

    def test_skip_increments_skip_streak(self):
        state = DifficultyState()
        new_state = update_difficulty(state, "reflection", "skipped", NOW_ISO)
        assert new_state.consecutive_skips["reflection"] == 1
        assert new_state.consecutive_completions["reflection"] == 0

    def test_completion_resets_skip_streak(self):
        state = DifficultyState(
            consecutive_skips={"reflection": 2},
        )
        new_state = update_difficulty(state, "reflection", "completed", NOW_ISO)
        assert new_state.consecutive_skips["reflection"] == 0

    def test_skip_resets_completion_streak(self):
        state = DifficultyState(
            consecutive_completions={"reflection": 2},
        )
        new_state = update_difficulty(state, "reflection", "skipped", NOW_ISO)
        assert new_state.consecutive_completions["reflection"] == 0

    def test_advances_on_third_completion(self):
        state = DifficultyState(
            levels={"reflection": 1},
            consecutive_completions={"reflection": 2},
            consecutive_skips={"reflection": 0},
            last_advancement_dates={},
        )
        new_state = update_difficulty(state, "reflection", "completed", NOW_ISO)
        assert new_state.levels["reflection"] == 2
        assert new_state.consecutive_completions["reflection"] == 0

    def test_regresses_on_third_skip(self):
        state = DifficultyState(
            levels={"reflection": 3},
            consecutive_completions={"reflection": 0},
            consecutive_skips={"reflection": 2},
            last_advancement_dates={},
        )
        new_state = update_difficulty(state, "reflection", "skipped", NOW_ISO)
        assert new_state.levels["reflection"] == 2
        assert new_state.consecutive_skips["reflection"] == 0

    def test_does_not_advance_past_max(self):
        state = DifficultyState(
            levels={"reflection": MAX_LEVEL},
            consecutive_completions={"reflection": 2},
            consecutive_skips={"reflection": 0},
            last_advancement_dates={},
        )
        new_state = update_difficulty(state, "reflection", "completed", NOW_ISO)
        assert new_state.levels["reflection"] == MAX_LEVEL

    def test_does_not_regress_past_min(self):
        state = DifficultyState(
            levels={"reflection": MIN_LEVEL},
            consecutive_completions={"reflection": 0},
            consecutive_skips={"reflection": 2},
            last_advancement_dates={},
        )
        new_state = update_difficulty(state, "reflection", "skipped", NOW_ISO)
        assert new_state.levels["reflection"] == MIN_LEVEL

    def test_does_not_mutate_original_state(self):
        state = DifficultyState()
        original_level = state.levels["reflection"]
        update_difficulty(state, "reflection", "completed", NOW_ISO)
        assert state.levels["reflection"] == original_level

    def test_cooldown_blocks_advancement(self):
        recent = (NOW - timedelta(days=3)).isoformat()
        state = DifficultyState(
            levels={"reflection": 2},
            consecutive_completions={"reflection": 2},
            consecutive_skips={"reflection": 0},
            last_advancement_dates={"reflection": recent},
        )
        new_state = update_difficulty(state, "reflection", "completed", NOW_ISO)
        # Streak hit 3 but cooldown not elapsed — no advancement.
        assert new_state.levels["reflection"] == 2
        assert new_state.consecutive_completions["reflection"] == 3

    def test_unknown_category_returns_unchanged(self):
        state = DifficultyState()
        new_state = update_difficulty(state, "nonexistent", "completed", NOW_ISO)
        assert new_state.levels == state.levels


# ---------------------------------------------------------------------------
# filter_by_difficulty
# ---------------------------------------------------------------------------

class TestFilterByDifficulty:
    def test_keeps_matching_level(self):
        state = DifficultyState(levels={"reflection": 3})
        candidates = [_make_candidate("reflection", 3)]
        result = filter_by_difficulty(candidates, state)
        assert len(result) == 1

    def test_keeps_plus_one(self):
        state = DifficultyState(levels={"reflection": 3})
        candidates = [_make_candidate("reflection", 4)]
        result = filter_by_difficulty(candidates, state)
        assert len(result) == 1

    def test_keeps_minus_one(self):
        state = DifficultyState(levels={"reflection": 3})
        candidates = [_make_candidate("reflection", 2)]
        result = filter_by_difficulty(candidates, state)
        assert len(result) == 1

    def test_filters_out_too_high(self):
        state = DifficultyState(levels={"reflection": 1})
        candidates = [_make_candidate("reflection", 3)]
        result = filter_by_difficulty(candidates, state)
        assert len(result) == 0

    def test_filters_out_too_low(self):
        state = DifficultyState(levels={"reflection": 5})
        candidates = [_make_candidate("reflection", 3)]
        result = filter_by_difficulty(candidates, state)
        assert len(result) == 0

    def test_empty_candidates(self):
        state = DifficultyState()
        assert filter_by_difficulty([], state) == []

    def test_mixed_categories(self):
        state = DifficultyState(levels={"reflection": 2, "portfolio": 4})
        candidates = [
            _make_candidate("reflection", 3),  # within ±1 of 2 → keep
            _make_candidate("portfolio", 2),    # 4-2=2 > 1 → filter
            _make_candidate("portfolio", 4),    # exact match → keep
        ]
        result = filter_by_difficulty(candidates, state)
        assert len(result) == 2

    def test_defaults_to_level_one_for_missing_category(self):
        state = DifficultyState(levels={})
        candidates = [
            _make_candidate("reflection", 1),  # within ±1 of default 1
            _make_candidate("reflection", 2),  # within ±1 of default 1
            _make_candidate("reflection", 3),  # too far from default 1
        ]
        result = filter_by_difficulty(candidates, state)
        assert len(result) == 2
