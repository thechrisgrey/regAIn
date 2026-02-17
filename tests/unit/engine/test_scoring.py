"""Unit tests for backend.engine.scoring."""

from __future__ import annotations

from backend.engine.models import (
    CATEGORIES,
    DifficultyState,
    MissionCandidate,
    SkillGapReport,
)
from backend.engine.scoring import (
    PHASE_PREFERRED_CATEGORIES,
    WEIGHTS,
    score_and_rank,
    score_candidate,
    score_category_balance,
    score_difficulty_appropriateness,
    score_gap_priority,
    score_phase_alignment,
    score_streak_momentum,
)


def _make_candidate(**overrides) -> MissionCandidate:
    """Helper to build a MissionCandidate with sensible defaults."""
    defaults = {
        "template_id": "t1",
        "category": "skill_building",
        "title": "Test Mission",
        "description": "Do something useful",
        "rationale": "Because growth",
        "skill_tags": ["python"],
        "difficulty": 2,
        "estimated_minutes": 30,
        "expected_evidence_type": "artifact",
        "phase": "foundation",
        "market_relevance_score": 0.5,
        "priority_score": 0.0,
    }
    defaults.update(overrides)
    return MissionCandidate(**defaults)


def _make_skill_gaps(**overrides) -> SkillGapReport:
    defaults = {
        "skill_scores": {"python": 0.3, "aws": 0.1},
        "market_alignment_pct": 40.0,
        "priority_skills": ["aws", "python"],
        "evidence_density": {"python": 1, "aws": 0},
    }
    defaults.update(overrides)
    return SkillGapReport(**defaults)


# --- score_gap_priority ---

class TestScoreGapPriority:
    def test_wider_gap_scores_higher(self):
        gaps = _make_skill_gaps(skill_scores={"python": 0.2, "aws": 0.8})
        c_wide = _make_candidate(skill_tags=["python"])  # gap = 0.8
        c_narrow = _make_candidate(skill_tags=["aws"])   # gap = 0.2
        assert score_gap_priority(c_wide, gaps) > score_gap_priority(c_narrow, gaps)

    def test_no_skill_tags_returns_zero(self):
        gaps = _make_skill_gaps()
        c = _make_candidate(skill_tags=[])
        assert score_gap_priority(c, gaps) == 0.0

    def test_unknown_skill_treated_as_zero_score(self):
        gaps = _make_skill_gaps(skill_scores={})
        c = _make_candidate(skill_tags=["unknown_skill"])
        # gap = 1.0 - 0.0 = 1.0
        assert score_gap_priority(c, gaps) == 1.0

    def test_result_bounded_zero_to_one(self):
        gaps = _make_skill_gaps(skill_scores={"python": 0.0})
        c = _make_candidate(skill_tags=["python"])
        score = score_gap_priority(c, gaps)
        assert 0.0 <= score <= 1.0

    def test_priority_skill_rank_affects_score(self):
        gaps = _make_skill_gaps(
            skill_scores={"a": 0.0, "b": 0.0},
            priority_skills=["a", "b"],
        )
        c_top = _make_candidate(skill_tags=["a"])
        c_low = _make_candidate(skill_tags=["b"])
        assert score_gap_priority(c_top, gaps) >= score_gap_priority(c_low, gaps)


# --- score_category_balance ---

class TestScoreCategoryBalance:
    def test_overindexed_category_penalized(self):
        history = [
            {"category": "reflection", "status": "completed"},
            {"category": "reflection", "status": "completed"},
            {"category": "reflection", "status": "completed"},
            {"category": "skill_building", "status": "completed"},
        ]
        c_over = _make_candidate(category="reflection")
        c_under = _make_candidate(category="skill_building")
        assert score_category_balance(c_over, history) < score_category_balance(c_under, history)

    def test_empty_history_returns_one(self):
        c = _make_candidate()
        assert score_category_balance(c, []) == 1.0

    def test_zero_category_in_history(self):
        history = [{"category": "reflection", "status": "completed"}]
        c = _make_candidate(category="portfolio")  # 0 completions
        assert score_category_balance(c, history) == 1.0

    def test_skipped_missions_not_counted(self):
        history = [
            {"category": "reflection", "status": "skipped"},
            {"category": "reflection", "status": "skipped"},
        ]
        c = _make_candidate(category="reflection")
        assert score_category_balance(c, history) == 1.0


# --- score_difficulty_appropriateness ---

class TestScoreDifficultyAppropriateness:
    def test_exact_match_scores_one(self):
        state = DifficultyState(levels={"skill_building": 3})
        c = _make_candidate(category="skill_building", difficulty=3)
        assert score_difficulty_appropriateness(c, state) == 1.0

    def test_one_off_scores_less_than_match(self):
        state = DifficultyState(levels={"skill_building": 3})
        c_match = _make_candidate(category="skill_building", difficulty=3)
        c_off = _make_candidate(category="skill_building", difficulty=4)
        assert score_difficulty_appropriateness(c_match, state) > score_difficulty_appropriateness(c_off, state)

    def test_max_distance_scores_zero(self):
        state = DifficultyState(levels={"skill_building": 1})
        c = _make_candidate(category="skill_building", difficulty=5)
        assert score_difficulty_appropriateness(c, state) == 0.0

    def test_missing_category_defaults_to_level_one(self):
        state = DifficultyState(levels={})
        c = _make_candidate(category="skill_building", difficulty=1)
        assert score_difficulty_appropriateness(c, state) == 1.0


# --- score_phase_alignment ---

class TestScorePhaseAlignment:
    def test_preferred_category_scores_one(self):
        c = _make_candidate(category="reflection")
        assert score_phase_alignment(c, "foundation") == 1.0

    def test_non_preferred_category_scores_low(self):
        c = _make_candidate(category="networking")
        assert score_phase_alignment(c, "foundation") == 0.3

    def test_all_phases_have_preferred(self):
        for phase, preferred in PHASE_PREFERRED_CATEGORIES.items():
            for cat in preferred:
                c = _make_candidate(category=cat)
                assert score_phase_alignment(c, phase) == 1.0

    def test_unknown_phase_returns_low(self):
        c = _make_candidate(category="reflection")
        assert score_phase_alignment(c, "unknown_phase") == 0.3


# --- score_streak_momentum ---

class TestScoreStreakMomentum:
    def test_completion_streak_favors_recent_category(self):
        streak = {"type": "completion", "count": 3, "recent_categories": ["skill_building"]}
        c_match = _make_candidate(category="skill_building")
        c_other = _make_candidate(category="portfolio")
        assert score_streak_momentum(c_match, streak) > score_streak_momentum(c_other, streak)

    def test_broken_streak_favors_easier(self):
        streak = {"type": "broken", "count": 2, "recent_categories": []}
        c_easy = _make_candidate(difficulty=1)
        c_hard = _make_candidate(difficulty=5)
        assert score_streak_momentum(c_easy, streak) > score_streak_momentum(c_hard, streak)

    def test_no_streak_returns_neutral(self):
        c = _make_candidate()
        assert score_streak_momentum(c, {}) == 0.5

    def test_broken_streak_difficulty_one_scores_one(self):
        streak = {"type": "broken", "count": 1, "recent_categories": []}
        c = _make_candidate(difficulty=1)
        assert score_streak_momentum(c, streak) == 1.0


# --- score_candidate ---

class TestScoreCandidate:
    def test_returns_weighted_sum(self):
        candidate = _make_candidate(
            skill_tags=["python"],
            category="skill_building",
            difficulty=2,
        )
        gaps = _make_skill_gaps(skill_scores={"python": 0.3})
        history: list[dict] = []
        phase = "foundation"
        streak = {"type": "completion", "count": 2, "recent_categories": ["skill_building"]}
        state = DifficultyState(levels={"skill_building": 2})

        total = score_candidate(candidate, gaps, history, phase, streak, state)

        # Verify it equals the manual weighted sum.
        gap = score_gap_priority(candidate, gaps)
        balance = score_category_balance(candidate, history)
        diff = score_difficulty_appropriateness(candidate, state)
        pa = score_phase_alignment(candidate, phase)
        sm = score_streak_momentum(candidate, streak)

        expected = (
            WEIGHTS["gap_priority"] * gap
            + WEIGHTS["category_balance"] * balance
            + WEIGHTS["difficulty_appropriateness"] * diff
            + WEIGHTS["phase_alignment"] * pa
            + WEIGHTS["streak_momentum"] * sm
        )
        assert abs(total - expected) < 0.001

    def test_score_bounded(self):
        candidate = _make_candidate()
        gaps = _make_skill_gaps()
        state = DifficultyState()
        score = score_candidate(candidate, gaps, [], "foundation", {}, state)
        assert 0.0 <= score <= 1.0


# --- score_and_rank ---

class TestScoreAndRank:
    def test_returns_descending_order(self):
        gaps = _make_skill_gaps(skill_scores={"python": 0.1, "aws": 0.9})
        c1 = _make_candidate(template_id="t1", skill_tags=["python"])  # big gap
        c2 = _make_candidate(template_id="t2", skill_tags=["aws"])     # small gap
        state = DifficultyState()

        ranked = score_and_rank(
            [c1, c2], gaps, [], "foundation",
            {"type": "completion", "count": 1, "recent_categories": []},
            state,
        )
        assert ranked[0].priority_score >= ranked[1].priority_score

    def test_priority_scores_set_on_candidates(self):
        gaps = _make_skill_gaps()
        c = _make_candidate()
        state = DifficultyState()

        ranked = score_and_rank([c], gaps, [], "foundation", {}, state)
        assert ranked[0].priority_score > 0.0

    def test_empty_candidates_returns_empty(self):
        gaps = _make_skill_gaps()
        state = DifficultyState()
        ranked = score_and_rank([], gaps, [], "foundation", {}, state)
        assert ranked == []
