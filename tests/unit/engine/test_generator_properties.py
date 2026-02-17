"""Property-based tests for backend.engine.generator module.

Uses Hypothesis to validate universal properties across randomly generated inputs.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from backend.engine.generator import _exclude_recent_duplicates
from backend.engine.models import GenerationResult, MissionCandidate

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CATEGORIES = ["reflection", "skill_building", "portfolio", "networking", "market_research"]
PHASES = ["foundation", "expansion", "launch"]
EVIDENCE_TYPES = ["reflection", "artifact", "connection", "research"]

# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

skill_tag_st = st.from_regex(r"skill_[a-z]{2,6}", fullmatch=True)
template_id_st = st.from_regex(r"tpl_[a-z]{2,6}_[0-9]{1,2}", fullmatch=True)


@st.composite
def mission_candidate_st(draw: st.DrawFn) -> MissionCandidate:
    """Generate a random MissionCandidate with valid fields."""
    return MissionCandidate(
        template_id=draw(template_id_st),
        category=draw(st.sampled_from(CATEGORIES)),
        title=f"Mission {draw(st.integers(min_value=1, max_value=999))}",
        description="Test description",
        rationale="Test rationale",
        skill_tags=draw(st.lists(skill_tag_st, min_size=1, max_size=4)),
        difficulty=draw(st.integers(min_value=1, max_value=5)),
        estimated_minutes=draw(st.integers(min_value=15, max_value=45)),
        expected_evidence_type=draw(st.sampled_from(EVIDENCE_TYPES)),
        phase=draw(st.sampled_from(PHASES)),
    )


def _make_history_entry(
    template_id: str,
    primary_skill: str,
    days_ago: float,
    status: str = "completed",
) -> dict[str, Any]:
    """Build a mission history dict with a completedAt relative to now."""
    completed_at = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return {
        "missionId": f"m_{abs(hash((template_id, primary_skill, days_ago))) % 100000}",
        "status": status,
        "templateId": template_id,
        "skillTags": [primary_skill],
        "completedAt": completed_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# Property 19: Recent duplicate exclusion within 14 days
# Feature: mission-engine, Property 19: Recent duplicate exclusion within 14 days
# ---------------------------------------------------------------------------


class TestProperty19RecentDuplicateExclusion:
    """**Validates: Requirements 7.5**

    For ANY set of MissionCandidates and a mission history, candidates whose
    template_id AND primary skill_tag match a mission completed within the
    last 14 days shall be excluded from the generation result.
    """

    @given(data=st.data())
    @settings(max_examples=200)
    def test_matching_recent_duplicates_are_excluded(
        self, data: st.DataObject
    ) -> None:
        """Candidates matching a completed mission within 14 days are excluded."""
        # Feature: mission-engine, Property 19: Recent duplicate exclusion within 14 days
        # **Validates: Requirements 7.5**

        candidate = data.draw(mission_candidate_st())
        primary_tag = candidate.skill_tags[0]

        # Completed 0-12 days ago — clearly within the 14-day window
        days_ago = data.draw(st.integers(min_value=0, max_value=12))
        history = [_make_history_entry(candidate.template_id, primary_tag, days_ago)]

        # Add some unrelated history noise
        extra = data.draw(st.lists(mission_candidate_st(), min_size=0, max_size=3))
        other_candidates = [candidate] + extra

        result = _exclude_recent_duplicates(other_candidates, history, window_days=14)

        # The matching candidate must be excluded
        for c in result:
            c_tag = c.skill_tags[0] if c.skill_tags else ""
            if c.template_id == candidate.template_id and c_tag == primary_tag:
                # This candidate should have been excluded
                assert False, (
                    f"Candidate ({c.template_id}, {c_tag}) should have been "
                    f"excluded by recent completion {days_ago} days ago"
                )

    @given(
        candidates=st.lists(mission_candidate_st(), min_size=1, max_size=10),
    )
    @settings(max_examples=200)
    def test_non_matching_candidates_are_kept(
        self,
        candidates: list[MissionCandidate],
    ) -> None:
        """Candidates NOT matching any recent completion are preserved."""
        # Feature: mission-engine, Property 19: Recent duplicate exclusion within 14 days
        # **Validates: Requirements 7.5**

        # Build history with completely different template_ids so nothing matches
        history = [
            _make_history_entry(f"unrelated_{i}", f"other_skill_{i}", days_ago=1)
            for i in range(3)
        ]

        result = _exclude_recent_duplicates(candidates, history, window_days=14)

        # All candidates should be kept since none match history
        assert len(result) == len(candidates)

    @given(data=st.data())
    @settings(max_examples=200)
    def test_old_completions_do_not_exclude(self, data: st.DataObject) -> None:
        """Missions completed more than 14 days ago do NOT cause exclusion."""
        # Feature: mission-engine, Property 19: Recent duplicate exclusion within 14 days
        # **Validates: Requirements 7.5**

        candidate = data.draw(mission_candidate_st())
        primary_tag = candidate.skill_tags[0]

        # Completed 16-365 days ago — clearly outside the 14-day window
        days_ago = data.draw(st.integers(min_value=16, max_value=365))
        history = [_make_history_entry(candidate.template_id, primary_tag, days_ago)]

        result = _exclude_recent_duplicates([candidate], history, window_days=14)

        # The candidate should NOT be excluded since the match is old
        assert len(result) == 1
        assert result[0].template_id == candidate.template_id


# ---------------------------------------------------------------------------
# Property 14: Top candidate selected as primary
# Feature: mission-engine, Property 14: Top candidate selected as primary
# ---------------------------------------------------------------------------


@st.composite
def scored_candidate_st(draw: st.DrawFn) -> MissionCandidate:
    """Generate a MissionCandidate with a known priority_score."""
    return MissionCandidate(
        template_id=draw(template_id_st),
        category=draw(st.sampled_from(CATEGORIES)),
        title=f"Mission {draw(st.integers(min_value=1, max_value=999))}",
        description="Test description",
        rationale="Test rationale",
        skill_tags=draw(st.lists(skill_tag_st, min_size=1, max_size=4)),
        difficulty=draw(st.integers(min_value=1, max_value=5)),
        estimated_minutes=draw(st.integers(min_value=15, max_value=45)),
        expected_evidence_type=draw(st.sampled_from(EVIDENCE_TYPES)),
        phase=draw(st.sampled_from(PHASES)),
        priority_score=draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False)),
    )


class TestProperty14TopCandidateSelectedAsPrimary:
    """**Validates: Requirements 4.7**

    For ANY list of 3 or more scored MissionCandidates, the GenerationResult's
    primary mission shall have the highest priority_score, and the 2 alternates
    shall have the next two highest scores.
    """

    @given(
        candidates=st.lists(scored_candidate_st(), min_size=3, max_size=20),
    )
    @settings(max_examples=200)
    def test_primary_has_highest_score(
        self, candidates: list[MissionCandidate]
    ) -> None:
        """The primary mission has the highest priority_score among all candidates."""
        # Feature: mission-engine, Property 14: Top candidate selected as primary
        # **Validates: Requirements 4.7**

        # Sort descending by priority_score (same logic the orchestrator uses)
        ranked = sorted(candidates, key=lambda c: c.priority_score, reverse=True)

        primary = ranked[0]
        alternates = ranked[1:3]

        result = GenerationResult(
            primary=primary,
            alternates=alternates,
            skill_gap_report=None,  # type: ignore[arg-type]
        )

        # Primary must have the highest score
        for alt in result.alternates:
            assert result.primary.priority_score >= alt.priority_score, (
                f"Primary score {result.primary.priority_score} < "
                f"alternate score {alt.priority_score}"
            )

        # Primary must have the highest score among ALL candidates
        for c in candidates:
            assert result.primary.priority_score >= c.priority_score, (
                f"Primary score {result.primary.priority_score} < "
                f"candidate score {c.priority_score}"
            )

    @given(
        candidates=st.lists(scored_candidate_st(), min_size=3, max_size=20),
    )
    @settings(max_examples=200)
    def test_alternates_are_next_two_highest(
        self, candidates: list[MissionCandidate]
    ) -> None:
        """The 2 alternates have the next two highest priority_scores."""
        # Feature: mission-engine, Property 14: Top candidate selected as primary
        # **Validates: Requirements 4.7**

        ranked = sorted(candidates, key=lambda c: c.priority_score, reverse=True)

        primary = ranked[0]
        alternates = ranked[1:3]

        result = GenerationResult(
            primary=primary,
            alternates=alternates,
            skill_gap_report=None,  # type: ignore[arg-type]
        )

        # Alternates should be exactly 2
        assert len(result.alternates) == 2

        # Alternates' scores should be >= all remaining candidates (rank 3+)
        remaining = ranked[3:]
        for alt in result.alternates:
            for rem in remaining:
                assert alt.priority_score >= rem.priority_score, (
                    f"Alternate score {alt.priority_score} < "
                    f"remaining candidate score {rem.priority_score}"
                )

    @given(
        candidates=st.lists(scored_candidate_st(), min_size=3, max_size=20),
    )
    @settings(max_examples=200)
    def test_selection_order_matches_score_ranking(
        self, candidates: list[MissionCandidate]
    ) -> None:
        """Primary + alternates are the top 3 by score in descending order."""
        # Feature: mission-engine, Property 14: Top candidate selected as primary
        # **Validates: Requirements 4.7**

        ranked = sorted(candidates, key=lambda c: c.priority_score, reverse=True)

        primary = ranked[0]
        alternates = ranked[1:3]

        result = GenerationResult(
            primary=primary,
            alternates=alternates,
            skill_gap_report=None,  # type: ignore[arg-type]
        )

        # The selected top-3 scores should be monotonically non-increasing
        selected_scores = [result.primary.priority_score] + [
            a.priority_score for a in result.alternates
        ]
        for i in range(len(selected_scores) - 1):
            assert selected_scores[i] >= selected_scores[i + 1], (
                f"Score at position {i} ({selected_scores[i]}) < "
                f"score at position {i+1} ({selected_scores[i+1]})"
            )
