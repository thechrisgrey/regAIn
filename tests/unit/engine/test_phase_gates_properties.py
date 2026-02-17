"""Property-based tests for backend.engine.phase_gates module.

Uses Hypothesis to validate universal properties across randomly generated inputs.
"""

from __future__ import annotations

from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from backend.engine.models import GateResult
from backend.engine.phase_gates import (
    GATE_CONDITIONS,
    evaluate_gate,
    _PHASE_TO_GATE,
    _NEXT_PHASE,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALL_PHASES = ["foundation", "expansion", "launch"]
ALL_CATEGORIES = ["reflection", "skill_building", "portfolio", "networking", "market_research"]

# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

phase_st = st.sampled_from(ALL_PHASES)
category_st = st.sampled_from(ALL_CATEGORIES)


@st.composite
def completed_missions_st(draw: st.DrawFn) -> list[dict[str, Any]]:
    """Generate a list of completed mission dicts with random categories."""
    count = draw(st.integers(min_value=0, max_value=60))
    categories = draw(
        st.lists(category_st, min_size=count, max_size=count)
    )
    return [{"category": cat} for cat in categories]


@st.composite
def evidence_by_skill_st(draw: st.DrawFn) -> dict[str, list[dict[str, Any]]]:
    """Generate evidence_by_skill with a random number of skills.

    Each skill has either an empty list (not counted) or at least one record.
    """
    num_skills = draw(st.integers(min_value=0, max_value=30))
    result: dict[str, list[dict[str, Any]]] = {}
    for i in range(num_skills):
        has_evidence = draw(st.booleans())
        if has_evidence:
            count = draw(st.integers(min_value=1, max_value=5))
            result[f"skill_{i}"] = [{"id": f"ev_{i}_{j}"} for j in range(count)]
        else:
            result[f"skill_{i}"] = []
    return result


market_alignment_st = st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)


# ---------------------------------------------------------------------------
# Helper: independently compute expected gate result
# ---------------------------------------------------------------------------

def _compute_expected(
    phase: str,
    missions: list[dict[str, Any]],
    evidence_by_skill: dict[str, list[dict[str, Any]]],
    market_alignment_pct: float,
) -> dict[str, Any]:
    """Independently compute expected gate evaluation results."""
    gate_key = _PHASE_TO_GATE.get(phase)
    if gate_key is None:
        return {"passed": False, "next_phase": None, "conditions": {}}

    requirements = GATE_CONDITIONS[gate_key]
    next_phase = _NEXT_PHASE[phase]

    # Compute current values
    total_completed = len(missions)
    unique_categories = len({m.get("category", "") for m in missions if m.get("category")})
    unique_skills = sum(1 for records in evidence_by_skill.values() if len(records) > 0)
    portfolio_artifacts = sum(1 for m in missions if m.get("category") == "portfolio")

    current_values = {
        "min_completed_missions": total_completed,
        "min_categories": unique_categories,
        "min_unique_skills": unique_skills,
        "min_portfolio_artifacts": portfolio_artifacts,
        "min_market_alignment": market_alignment_pct,
    }

    conditions = {}
    all_met = True
    for cond_name, required in requirements.items():
        current = current_values[cond_name]
        met = current >= required
        conditions[cond_name] = {"required": required, "current": current, "met": met}
        if not met:
            all_met = False

    return {
        "passed": all_met,
        "next_phase": next_phase if all_met else None,
        "conditions": conditions,
    }


# ---------------------------------------------------------------------------
# Property 15: Gate evaluation correct for all phases
# Feature: mission-engine, Property 15: Gate evaluation correct for all phases
# ---------------------------------------------------------------------------


class TestProperty15GateEvaluationCorrectForAllPhases:
    """**Validates: Requirements 5.1, 5.2, 5.3, 5.6**

    For ANY phase and mission/evidence data, the gate passes if and only if
    all conditions for that phase are met. When the gate fails, every
    condition in the GateResult has accurate current values and correct
    met/not-met status.
    """

    @given(
        phase=phase_st,
        missions=completed_missions_st(),
        evidence=evidence_by_skill_st(),
        alignment=market_alignment_st,
    )
    @settings(max_examples=200)
    def test_gate_passes_iff_all_conditions_met(
        self,
        phase: str,
        missions: list[dict[str, Any]],
        evidence: dict[str, list[dict[str, Any]]],
        alignment: float,
    ) -> None:
        """Gate passes if and only if every condition's current >= required."""
        # Feature: mission-engine, Property 15: Gate evaluation correct for all phases
        # **Validates: Requirements 5.1, 5.2, 5.3, 5.6**
        result = evaluate_gate(phase, missions, evidence, alignment)
        expected = _compute_expected(phase, missions, evidence, alignment)

        assert result.passed == expected["passed"]

        # If passed, all conditions must be met
        if result.passed:
            assert all(c.met for c in result.conditions.values())
        # If not passed, at least one condition must not be met (when conditions exist)
        if not result.passed and result.conditions:
            assert any(not c.met for c in result.conditions.values())

    @given(
        phase=phase_st,
        missions=completed_missions_st(),
        evidence=evidence_by_skill_st(),
        alignment=market_alignment_st,
    )
    @settings(max_examples=200)
    def test_condition_met_field_matches_current_vs_required(
        self,
        phase: str,
        missions: list[dict[str, Any]],
        evidence: dict[str, list[dict[str, Any]]],
        alignment: float,
    ) -> None:
        """Each condition's met field correctly reflects current >= required."""
        # Feature: mission-engine, Property 15: Gate evaluation correct for all phases
        # **Validates: Requirements 5.1, 5.2, 5.3, 5.6**
        result = evaluate_gate(phase, missions, evidence, alignment)

        for cond_name, cond in result.conditions.items():
            assert cond.met == (cond.current >= cond.required), (
                f"Condition '{cond_name}': met={cond.met} but "
                f"current={cond.current} vs required={cond.required}"
            )

    @given(
        phase=phase_st,
        missions=completed_missions_st(),
        evidence=evidence_by_skill_st(),
        alignment=market_alignment_st,
    )
    @settings(max_examples=200)
    def test_condition_current_values_accurate(
        self,
        phase: str,
        missions: list[dict[str, Any]],
        evidence: dict[str, list[dict[str, Any]]],
        alignment: float,
    ) -> None:
        """Each condition's current value matches independently computed values."""
        # Feature: mission-engine, Property 15: Gate evaluation correct for all phases
        # **Validates: Requirements 5.1, 5.2, 5.3, 5.6**
        result = evaluate_gate(phase, missions, evidence, alignment)
        expected = _compute_expected(phase, missions, evidence, alignment)

        for cond_name, expected_cond in expected["conditions"].items():
            actual_cond = result.conditions[cond_name]
            assert actual_cond.current == expected_cond["current"], (
                f"Condition '{cond_name}': current={actual_cond.current} "
                f"expected={expected_cond['current']}"
            )
            assert actual_cond.required == expected_cond["required"], (
                f"Condition '{cond_name}': required={actual_cond.required} "
                f"expected={expected_cond['required']}"
            )

    @given(
        phase=phase_st,
        missions=completed_missions_st(),
        evidence=evidence_by_skill_st(),
        alignment=market_alignment_st,
    )
    @settings(max_examples=200)
    def test_next_phase_correct_on_pass_and_fail(
        self,
        phase: str,
        missions: list[dict[str, Any]],
        evidence: dict[str, list[dict[str, Any]]],
        alignment: float,
    ) -> None:
        """When gate passes, next_phase is set correctly. When it fails, next_phase is None."""
        # Feature: mission-engine, Property 15: Gate evaluation correct for all phases
        # **Validates: Requirements 5.1, 5.2, 5.3, 5.6**
        result = evaluate_gate(phase, missions, evidence, alignment)

        if result.passed:
            assert result.next_phase == _NEXT_PHASE[phase]
        else:
            assert result.next_phase is None

    @given(
        phase=phase_st,
        missions=completed_missions_st(),
        evidence=evidence_by_skill_st(),
        alignment=market_alignment_st,
    )
    @settings(max_examples=200)
    def test_conditions_keys_match_gate_requirements(
        self,
        phase: str,
        missions: list[dict[str, Any]],
        evidence: dict[str, list[dict[str, Any]]],
        alignment: float,
    ) -> None:
        """The returned conditions dict has exactly the keys defined in GATE_CONDITIONS for that phase."""
        # Feature: mission-engine, Property 15: Gate evaluation correct for all phases
        # **Validates: Requirements 5.1, 5.2, 5.3, 5.6**
        result = evaluate_gate(phase, missions, evidence, alignment)
        gate_key = _PHASE_TO_GATE[phase]
        expected_keys = set(GATE_CONDITIONS[gate_key].keys())

        assert set(result.conditions.keys()) == expected_keys
