"""Property-based tests for backend.engine.scoring module.

Uses Hypothesis to validate universal scoring properties across randomly
generated inputs. Properties 8-13 from the design document.
"""

from __future__ import annotations

from typing import Any

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from backend.engine.models import (
    CATEGORIES,
    DifficultyState,
    MissionCandidate,
    SkillGapReport,
)
from backend.engine.scoring import (
    WEIGHTS,
    PHASE_PREFERRED_CATEGORIES,
    score_candidate,
    score_gap_priority,
    score_category_balance,
    score_difficulty_appropriateness,
    score_phase_alignment,
    score_streak_momentum,
)

# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

skill_name_st = st.from_regex(r"[a-z][a-z_]{1,14}", fullmatch=True)

phases_st = st.sampled_from(["foundation", "expansion", "launch"])
categories_st = st.sampled_from(CATEGORIES)
difficulty_st = st.integers(min_value=1, max_value=5)


@st.composite
def mission_candidate_st(draw: st.DrawFn) -> MissionCandidate:
    """Generate a valid MissionCandidate."""
    category = draw(categories_st)
    difficulty = draw(difficulty_st)
    skills = draw(st.lists(skill_name_st, min_size=1, max_size=4, unique=True))
    phase = draw(phases_st)
    return MissionCandidate(
        template_id=f"tmpl_{draw(st.integers(min_value=1, max_value=999))}",
        category=category,
        title="Test Mission",
        description="A test mission description.",
        rationale="Test rationale.",
        skill_tags=skills,
        difficulty=difficulty,
        estimated_minutes=draw(st.integers(min_value=15, max_value=45)),
        expected_evidence_type=draw(st.sampled_from(["reflection", "artifact", "connection", "research"])),
        phase=phase,
        market_relevance_score=draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False)),
    )


@st.composite
def skill_gap_report_st(draw: st.DrawFn, skills: list[str] | None = None) -> SkillGapReport:
    """Generate a SkillGapReport, optionally for specific skills."""
    if skills is None:
        skills = draw(st.lists(skill_name_st, min_size=1, max_size=6, unique=True))
    skill_scores = {s: draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False)) for s in skills}
    market_alignment = draw(st.floats(min_value=0.0, max_value=100.0, allow_nan=False))
    evidence_density = {s: draw(st.integers(min_value=0, max_value=20)) for s in skills}
    return SkillGapReport(
        skill_scores=skill_scores,
        market_alignment_pct=market_alignment,
        priority_skills=list(skills),
        evidence_density=evidence_density,
    )


@st.composite
def difficulty_state_st(draw: st.DrawFn) -> DifficultyState:
    """Generate a valid DifficultyState."""
    levels = {c: draw(st.integers(min_value=1, max_value=5)) for c in CATEGORIES}
    completions = {c: draw(st.integers(min_value=0, max_value=5)) for c in CATEGORIES}
    skips = {c: draw(st.integers(min_value=0, max_value=5)) for c in CATEGORIES}
    return DifficultyState(
        levels=levels,
        consecutive_completions=completions,
        consecutive_skips=skips,
        last_advancement_dates={},
    )


@st.composite
def mission_history_st(draw: st.DrawFn) -> list[dict[str, Any]]:
    """Generate a mission history list."""
    size = draw(st.integers(min_value=0, max_value=20))
    history: list[dict[str, Any]] = []
    for _ in range(size):
        history.append({
            "category": draw(categories_st),
            "status": draw(st.sampled_from(["completed", "skipped", "expired"])),
        })
    return history


@st.composite
def streak_info_st(draw: st.DrawFn) -> dict[str, Any]:
    """Generate streak info dict."""
    streak_type = draw(st.sampled_from(["completion", "broken", ""]))
    recent_cats = draw(st.lists(categories_st, min_size=0, max_size=3))
    return {
        "type": streak_type,
        "count": draw(st.integers(min_value=0, max_value=10)),
        "recent_categories": recent_cats,
    }


# ---------------------------------------------------------------------------
# Property 8: Priority score equals weighted sum of sub-scores
# Feature: mission-engine, Property 8: Priority score equals weighted sum of sub-scores
# ---------------------------------------------------------------------------


class TestProperty8PriorityScoreWeightedSum:
    """**Validates: Requirements 4.1**

    For ANY MissionCandidate and scoring inputs, the computed priority_score
    shall equal 0.40 * gap_priority + 0.20 * category_balance +
    0.15 * difficulty_appropriateness + 0.15 * phase_alignment +
    0.10 * streak_momentum, within tolerance of 0.001.
    """

    @given(
        candidate=mission_candidate_st(),
        skill_gaps=skill_gap_report_st(),
        mission_history=mission_history_st(),
        current_phase=phases_st,
        streak_info=streak_info_st(),
        difficulty_state=difficulty_state_st(),
    )
    @settings(max_examples=200)
    def test_score_equals_weighted_sum(
        self,
        candidate: MissionCandidate,
        skill_gaps: SkillGapReport,
        mission_history: list[dict[str, Any]],
        current_phase: str,
        streak_info: dict[str, Any],
        difficulty_state: DifficultyState,
    ) -> None:
        # Feature: mission-engine, Property 8: Priority score equals weighted sum of sub-scores
        # **Validates: Requirements 4.1**
        total_score = score_candidate(
            candidate, skill_gaps, mission_history, current_phase,
            streak_info, difficulty_state,
        )

        gap = score_gap_priority(candidate, skill_gaps)
        balance = score_category_balance(candidate, mission_history)
        diff = score_difficulty_appropriateness(candidate, difficulty_state)
        phase = score_phase_alignment(candidate, current_phase)
        streak = score_streak_momentum(candidate, streak_info)

        expected = (
            WEIGHTS["gap_priority"] * gap
            + WEIGHTS["category_balance"] * balance
            + WEIGHTS["difficulty_appropriateness"] * diff
            + WEIGHTS["phase_alignment"] * phase
            + WEIGHTS["streak_momentum"] * streak
        )
        # Clamp expected the same way the implementation does.
        expected = max(0.0, min(1.0, expected))

        assert total_score == pytest.approx(expected, abs=0.001), (
            f"score_candidate={total_score} != weighted_sum={expected}"
        )


# ---------------------------------------------------------------------------
# Property 9: Gap priority monotonic with gap width and demand
# Feature: mission-engine, Property 9: Gap priority monotonic with gap width and demand
# ---------------------------------------------------------------------------


class TestProperty9GapPriorityMonotonic:
    """**Validates: Requirements 4.2**

    For ANY two MissionCandidates where candidate A targets a skill with a
    wider gap AND higher market demand than candidate B, the gap_priority
    sub-score of A shall be >= that of B.
    """

    @given(
        skill_a=skill_name_st,
        skill_b=skill_name_st,
        score_a=st.floats(min_value=0.0, max_value=0.49, allow_nan=False),
        score_b=st.floats(min_value=0.5, max_value=1.0, allow_nan=False),
    )
    @settings(max_examples=200)
    def test_wider_gap_higher_demand_scores_higher(
        self,
        skill_a: str,
        skill_b: str,
        score_a: float,
        score_b: float,
    ) -> None:
        # Feature: mission-engine, Property 9: Gap priority monotonic with gap width and demand
        # **Validates: Requirements 4.2**
        assume(skill_a != skill_b)

        # skill_a has lower skill_score → wider gap (gap = 1 - score)
        # skill_a is ranked higher in priority_skills → higher demand
        gap_report = SkillGapReport(
            skill_scores={skill_a: score_a, skill_b: score_b},
            market_alignment_pct=50.0,
            priority_skills=[skill_a, skill_b],  # skill_a ranked first = higher demand
            evidence_density={skill_a: 0, skill_b: 3},
        )

        candidate_a = MissionCandidate(
            template_id="tmpl_a", category="skill_building",
            title="A", description="A", rationale="A",
            skill_tags=[skill_a], difficulty=3, estimated_minutes=30,
            expected_evidence_type="artifact", phase="foundation",
        )
        candidate_b = MissionCandidate(
            template_id="tmpl_b", category="skill_building",
            title="B", description="B", rationale="B",
            skill_tags=[skill_b], difficulty=3, estimated_minutes=30,
            expected_evidence_type="artifact", phase="foundation",
        )

        score_a_val = score_gap_priority(candidate_a, gap_report)
        score_b_val = score_gap_priority(candidate_b, gap_report)

        assert score_a_val >= score_b_val, (
            f"Candidate A (wider gap, higher demand) scored {score_a_val} "
            f"< candidate B scored {score_b_val}"
        )


# ---------------------------------------------------------------------------
# Property 10: Category balance penalizes overindexed categories
# Feature: mission-engine, Property 10: Category balance penalizes overindexed categories
# ---------------------------------------------------------------------------


class TestProperty10CategoryBalancePenalizesOverindexed:
    """**Validates: Requirements 4.3**

    For ANY mission history where category X has more completed missions
    than category Y, a candidate in category X shall have a lower
    category_balance sub-score than a candidate in category Y.
    """

    @given(
        cat_x=categories_st,
        cat_y=categories_st,
        extra_x=st.integers(min_value=1, max_value=10),
        base_count=st.integers(min_value=0, max_value=5),
    )
    @settings(max_examples=200)
    def test_overindexed_category_scores_lower(
        self,
        cat_x: str,
        cat_y: str,
        extra_x: int,
        base_count: int,
    ) -> None:
        # Feature: mission-engine, Property 10: Category balance penalizes overindexed categories
        # **Validates: Requirements 4.3**
        assume(cat_x != cat_y)

        # Build history where cat_x has strictly more completions than cat_y.
        history: list[dict[str, Any]] = []
        for _ in range(base_count):
            history.append({"category": cat_y, "status": "completed"})
        for _ in range(base_count + extra_x):
            history.append({"category": cat_x, "status": "completed"})

        candidate_x = MissionCandidate(
            template_id="tmpl_x", category=cat_x,
            title="X", description="X", rationale="X",
            skill_tags=["test_skill"], difficulty=3, estimated_minutes=30,
            expected_evidence_type="artifact", phase="foundation",
        )
        candidate_y = MissionCandidate(
            template_id="tmpl_y", category=cat_y,
            title="Y", description="Y", rationale="Y",
            skill_tags=["test_skill"], difficulty=3, estimated_minutes=30,
            expected_evidence_type="artifact", phase="foundation",
        )

        score_x = score_category_balance(candidate_x, history)
        score_y = score_category_balance(candidate_y, history)

        assert score_x <= score_y, (
            f"Overindexed category '{cat_x}' scored {score_x} > "
            f"underrepresented '{cat_y}' scored {score_y}"
        )


# ---------------------------------------------------------------------------
# Property 11: Difficulty appropriateness peaks at matching level
# Feature: mission-engine, Property 11: Difficulty appropriateness peaks at matching level
# ---------------------------------------------------------------------------


class TestProperty11DifficultyAppropriatenessPeaks:
    """**Validates: Requirements 4.4**

    For ANY user difficulty level L in a category, a candidate at difficulty L
    shall have a higher difficulty_appropriateness sub-score than a candidate
    at difficulty L+1 or L-1 in the same category.
    """

    @given(
        category=categories_st,
        user_level=st.integers(min_value=2, max_value=4),
    )
    @settings(max_examples=200)
    def test_exact_match_scores_higher_than_neighbors(
        self,
        category: str,
        user_level: int,
    ) -> None:
        # Feature: mission-engine, Property 11: Difficulty appropriateness peaks at matching level
        # **Validates: Requirements 4.4**
        state = DifficultyState(
            levels={c: user_level if c == category else 1 for c in CATEGORIES},
            consecutive_completions={c: 0 for c in CATEGORIES},
            consecutive_skips={c: 0 for c in CATEGORIES},
            last_advancement_dates={},
        )

        def make_candidate(diff: int) -> MissionCandidate:
            return MissionCandidate(
                template_id="tmpl", category=category,
                title="T", description="D", rationale="R",
                skill_tags=["skill"], difficulty=diff, estimated_minutes=30,
                expected_evidence_type="artifact", phase="foundation",
            )

        score_match = score_difficulty_appropriateness(make_candidate(user_level), state)
        score_above = score_difficulty_appropriateness(make_candidate(user_level + 1), state)
        score_below = score_difficulty_appropriateness(make_candidate(user_level - 1), state)

        assert score_match > score_above, (
            f"Match score {score_match} not > above score {score_above}"
        )
        assert score_match > score_below, (
            f"Match score {score_match} not > below score {score_below}"
        )

    @given(
        category=categories_st,
        user_level=difficulty_st,
    )
    @settings(max_examples=200)
    def test_exact_match_is_maximum(
        self,
        category: str,
        user_level: int,
    ) -> None:
        """The exact match always scores 1.0."""
        # Feature: mission-engine, Property 11: Difficulty appropriateness peaks at matching level
        # **Validates: Requirements 4.4**
        state = DifficultyState(
            levels={c: user_level if c == category else 1 for c in CATEGORIES},
            consecutive_completions={c: 0 for c in CATEGORIES},
            consecutive_skips={c: 0 for c in CATEGORIES},
            last_advancement_dates={},
        )

        candidate = MissionCandidate(
            template_id="tmpl", category=category,
            title="T", description="D", rationale="R",
            skill_tags=["skill"], difficulty=user_level, estimated_minutes=30,
            expected_evidence_type="artifact", phase="foundation",
        )

        score = score_difficulty_appropriateness(candidate, state)
        assert score == pytest.approx(1.0, abs=0.001), (
            f"Exact match score {score} != 1.0"
        )


# ---------------------------------------------------------------------------
# Property 12: Phase alignment favors phase-appropriate categories
# Feature: mission-engine, Property 12: Phase alignment favors phase-appropriate categories
# ---------------------------------------------------------------------------


class TestProperty12PhaseAlignmentFavorsPreferred:
    """**Validates: Requirements 4.5**

    For ANY campaign phase, a candidate in a phase-preferred category shall
    have a higher phase_alignment sub-score than a candidate in a
    non-preferred category.

    Preferred: Foundation → {reflection, skill_building},
    Expansion → {portfolio, market_research}, Launch → {networking}.
    """

    @given(phase=phases_st)
    @settings(max_examples=200)
    def test_preferred_scores_higher_than_non_preferred(self, phase: str) -> None:
        # Feature: mission-engine, Property 12: Phase alignment favors phase-appropriate categories
        # **Validates: Requirements 4.5**
        preferred = PHASE_PREFERRED_CATEGORIES[phase]
        non_preferred = [c for c in CATEGORIES if c not in preferred]
        assume(len(non_preferred) > 0)

        preferred_cat = list(preferred)[0]
        non_preferred_cat = non_preferred[0]

        candidate_preferred = MissionCandidate(
            template_id="tmpl_p", category=preferred_cat,
            title="P", description="P", rationale="P",
            skill_tags=["skill"], difficulty=3, estimated_minutes=30,
            expected_evidence_type="artifact", phase=phase,
        )
        candidate_non = MissionCandidate(
            template_id="tmpl_n", category=non_preferred_cat,
            title="N", description="N", rationale="N",
            skill_tags=["skill"], difficulty=3, estimated_minutes=30,
            expected_evidence_type="artifact", phase=phase,
        )

        score_pref = score_phase_alignment(candidate_preferred, phase)
        score_non = score_phase_alignment(candidate_non, phase)

        assert score_pref > score_non, (
            f"Preferred '{preferred_cat}' scored {score_pref} not > "
            f"non-preferred '{non_preferred_cat}' scored {score_non} "
            f"in phase '{phase}'"
        )

    @given(phase=phases_st, data=st.data())
    @settings(max_examples=200)
    def test_all_preferred_categories_score_1(self, phase: str, data: st.SearchStrategy) -> None:
        """Every preferred category for a phase scores exactly 1.0."""
        # Feature: mission-engine, Property 12: Phase alignment favors phase-appropriate categories
        # **Validates: Requirements 4.5**
        preferred = PHASE_PREFERRED_CATEGORIES[phase]
        cat = data.draw(st.sampled_from(sorted(preferred)))

        candidate = MissionCandidate(
            template_id="tmpl", category=cat,
            title="T", description="D", rationale="R",
            skill_tags=["skill"], difficulty=3, estimated_minutes=30,
            expected_evidence_type="artifact", phase=phase,
        )

        score = score_phase_alignment(candidate, phase)
        assert score == pytest.approx(1.0, abs=0.001), (
            f"Preferred category '{cat}' in phase '{phase}' scored {score} != 1.0"
        )


# ---------------------------------------------------------------------------
# Property 13: Streak momentum adapts to streak state
# Feature: mission-engine, Property 13: Streak momentum adapts to streak state
# ---------------------------------------------------------------------------


class TestProperty13StreakMomentumAdapts:
    """**Validates: Requirements 4.6**

    For ANY user on a completion streak, a candidate similar to recent
    completions shall score higher on streak_momentum than a dissimilar
    candidate. For ANY user with a broken streak, an easier candidate shall
    score higher on streak_momentum than a harder one.
    """

    @given(
        recent_cat=categories_st,
        other_cat=categories_st,
    )
    @settings(max_examples=200)
    def test_completion_streak_favors_recent_category(
        self,
        recent_cat: str,
        other_cat: str,
    ) -> None:
        """On a completion streak, candidates matching recent categories score higher."""
        # Feature: mission-engine, Property 13: Streak momentum adapts to streak state
        # **Validates: Requirements 4.6**
        assume(recent_cat != other_cat)

        streak_info = {
            "type": "completion",
            "count": 3,
            "recent_categories": [recent_cat],
        }

        candidate_similar = MissionCandidate(
            template_id="tmpl_s", category=recent_cat,
            title="S", description="S", rationale="S",
            skill_tags=["skill"], difficulty=3, estimated_minutes=30,
            expected_evidence_type="artifact", phase="foundation",
        )
        candidate_different = MissionCandidate(
            template_id="tmpl_d", category=other_cat,
            title="D", description="D", rationale="D",
            skill_tags=["skill"], difficulty=3, estimated_minutes=30,
            expected_evidence_type="artifact", phase="foundation",
        )

        score_sim = score_streak_momentum(candidate_similar, streak_info)
        score_diff = score_streak_momentum(candidate_different, streak_info)

        assert score_sim > score_diff, (
            f"Similar category '{recent_cat}' scored {score_sim} not > "
            f"different category '{other_cat}' scored {score_diff} "
            f"on completion streak"
        )

    @given(
        easy_diff=st.integers(min_value=1, max_value=2),
        hard_diff=st.integers(min_value=4, max_value=5),
        category=categories_st,
    )
    @settings(max_examples=200)
    def test_broken_streak_favors_easier_missions(
        self,
        easy_diff: int,
        hard_diff: int,
        category: str,
    ) -> None:
        """On a broken streak, easier missions score higher."""
        # Feature: mission-engine, Property 13: Streak momentum adapts to streak state
        # **Validates: Requirements 4.6**
        streak_info = {
            "type": "broken",
            "count": 2,
            "recent_categories": [],
        }

        candidate_easy = MissionCandidate(
            template_id="tmpl_e", category=category,
            title="E", description="E", rationale="E",
            skill_tags=["skill"], difficulty=easy_diff, estimated_minutes=30,
            expected_evidence_type="artifact", phase="foundation",
        )
        candidate_hard = MissionCandidate(
            template_id="tmpl_h", category=category,
            title="H", description="H", rationale="H",
            skill_tags=["skill"], difficulty=hard_diff, estimated_minutes=30,
            expected_evidence_type="artifact", phase="foundation",
        )

        score_easy = score_streak_momentum(candidate_easy, streak_info)
        score_hard = score_streak_momentum(candidate_hard, streak_info)

        assert score_easy > score_hard, (
            f"Easy (diff={easy_diff}) scored {score_easy} not > "
            f"hard (diff={hard_diff}) scored {score_hard} on broken streak"
        )
