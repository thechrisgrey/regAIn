"""Property-based tests for backend.engine.skill_gap module.

Uses Hypothesis to validate universal properties across randomly generated inputs.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from backend.engine.skill_gap import analyze_skill_gaps

# Fixed reference date for deterministic testing.
REF_DATE = datetime(2025, 6, 1, tzinfo=timezone.utc)

# Import normalize_skill so expected values use canonical names.
import importlib as _importlib
_taxonomy = _importlib.import_module("backend.lambda.market_intel.taxonomy")
_normalize_skill = _taxonomy.normalize_skill

# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Skill names: short lowercase alphabetic strings, realistic identifiers.
skill_name_st = st.from_regex(r"[a-z][a-z_]{1,14}", fullmatch=True)

# ISO date strings within 2 years of REF_DATE.
evidence_date_st = st.integers(min_value=0, max_value=730).map(
    lambda days_ago: (REF_DATE - timedelta(days=days_ago)).isoformat()
)

# A single evidence record with a "date" key.
evidence_record_st = evidence_date_st.map(lambda d: {"date": d})

# Market demand weight per skill: positive float in (0.0, 1.0].
demand_weight_st = st.floats(min_value=0.01, max_value=1.0, allow_nan=False, allow_infinity=False)


def _build_inputs(
    skills: list[str],
    evidence_lists: dict[str, list[dict[str, Any]]],
    demand: dict[str, float],
) -> tuple[list[str], dict[str, list[dict[str, Any]]], list[dict[str, Any]], dict[str, float]]:
    """Build the four arguments for analyze_skill_gaps from generated data."""
    target_requirements = [{"skill": s} for s in demand]
    return skills, evidence_lists, target_requirements, demand


# Strategy: a consistent set of skills with evidence and demand data.
@st.composite
def skill_gap_inputs(draw: st.DrawFn) -> dict[str, Any]:
    """Generate a coherent set of inputs for analyze_skill_gaps.

    Produces 1-8 skills, each with 0-6 evidence records and a demand weight.
    """
    skills = draw(st.lists(skill_name_st, min_size=1, max_size=8, unique=True))

    evidence_by_skill: dict[str, list[dict[str, Any]]] = {}
    market_demand: dict[str, float] = {}

    for skill in skills:
        evidence_by_skill[skill] = draw(
            st.lists(evidence_record_st, min_size=0, max_size=6)
        )
        market_demand[skill] = draw(demand_weight_st)

    return {
        "user_skills": skills,
        "evidence_by_skill": evidence_by_skill,
        "target_requirements": [{"skill": s} for s in skills],
        "market_demand": market_demand,
    }


# ---------------------------------------------------------------------------
# Property 2: Skill gap scores bounded 0.0–1.0
# Feature: mission-engine, Property 2: Skill gap scores bounded 0.0-1.0
# ---------------------------------------------------------------------------


class TestProperty2SkillGapScoresBounded:
    """**Validates: Requirements 2.2**

    For ANY combination of user evidence records and market demand data,
    every per-skill score shall be between 0.0 and 1.0 inclusive.
    """

    @given(data=skill_gap_inputs())
    @settings(max_examples=200)
    def test_all_skill_scores_between_zero_and_one(self, data: dict[str, Any]) -> None:
        # Feature: mission-engine, Property 2: Skill gap scores bounded 0.0-1.0
        # **Validates: Requirements 2.2**
        report = analyze_skill_gaps(
            user_skills=data["user_skills"],
            evidence_by_skill=data["evidence_by_skill"],
            target_requirements=data["target_requirements"],
            market_demand=data["market_demand"],
            reference_date=REF_DATE,
        )

        for skill, score in report.skill_scores.items():
            assert 0.0 <= score <= 1.0, (
                f"Skill '{skill}' score {score} out of bounds [0.0, 1.0]"
            )

    @given(data=skill_gap_inputs())
    @settings(max_examples=200)
    def test_scores_bounded_with_extra_user_skills(self, data: dict[str, Any]) -> None:
        """Scores stay bounded even when user_skills has skills not in demand."""
        # Feature: mission-engine, Property 2: Skill gap scores bounded 0.0-1.0
        # **Validates: Requirements 2.2**
        extra_skills = data["user_skills"] + ["extra_skill_x", "extra_skill_y"]
        report = analyze_skill_gaps(
            user_skills=extra_skills,
            evidence_by_skill=data["evidence_by_skill"],
            target_requirements=data["target_requirements"],
            market_demand=data["market_demand"],
            reference_date=REF_DATE,
        )

        for skill, score in report.skill_scores.items():
            assert 0.0 <= score <= 1.0, (
                f"Skill '{skill}' score {score} out of bounds [0.0, 1.0]"
            )


# ---------------------------------------------------------------------------
# Property 3: Market alignment is correct weighted average
# Feature: mission-engine, Property 3: Market alignment is correct weighted average
# ---------------------------------------------------------------------------


class TestProperty3MarketAlignmentWeightedAverage:
    """**Validates: Requirements 2.3**

    For ANY set of per-skill scores and market demand weights,
    market_alignment_pct shall equal
    sum(score[s] * demand[s]) / sum(demand[s]) * 100,
    within tolerance of 0.01.
    """

    @given(data=skill_gap_inputs())
    @settings(max_examples=200)
    def test_market_alignment_matches_weighted_average(self, data: dict[str, Any]) -> None:
        # Feature: mission-engine, Property 3: Market alignment is correct weighted average
        # **Validates: Requirements 2.3**
        report = analyze_skill_gaps(
            user_skills=data["user_skills"],
            evidence_by_skill=data["evidence_by_skill"],
            target_requirements=data["target_requirements"],
            market_demand=data["market_demand"],
            reference_date=REF_DATE,
        )

        # Recompute expected alignment from the report's own skill_scores.
        # The implementation normalizes skill names, so we must normalize too.
        norm_demand = {
            _normalize_skill(k) or k: v for k, v in data["market_demand"].items()
        }
        norm_target = {
            _normalize_skill(r["skill"]) or r["skill"] for r in data["target_requirements"]
        }
        target_skills = norm_target | set(norm_demand.keys())
        target_skills.discard("")

        total_weighted = 0.0
        total_demand = 0.0
        for skill in target_skills:
            demand = norm_demand.get(skill, 0.0)
            score = report.skill_scores.get(skill, 0.0)
            total_weighted += score * demand
            total_demand += demand

        if total_demand > 0:
            expected_pct = (total_weighted / total_demand) * 100
        else:
            expected_pct = 0.0

        assert report.market_alignment_pct == pytest.approx(expected_pct, abs=0.01), (
            f"market_alignment_pct {report.market_alignment_pct} != "
            f"expected {expected_pct}"
        )

    @given(
        demand_values=st.lists(
            st.tuples(skill_name_st, demand_weight_st),
            min_size=1,
            max_size=6,
            unique_by=lambda x: x[0],
        )
    )
    @settings(max_examples=200)
    def test_zero_evidence_gives_zero_alignment(
        self, demand_values: list[tuple[str, float]]
    ) -> None:
        """With no evidence at all, alignment must be 0.0."""
        # Feature: mission-engine, Property 3: Market alignment is correct weighted average
        # **Validates: Requirements 2.3**
        skills = [s for s, _ in demand_values]
        market_demand = dict(demand_values)

        report = analyze_skill_gaps(
            user_skills=skills,
            evidence_by_skill={},
            target_requirements=[{"skill": s} for s in skills],
            market_demand=market_demand,
            reference_date=REF_DATE,
        )

        assert report.market_alignment_pct == pytest.approx(0.0, abs=0.01)
