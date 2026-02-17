"""Phase Gate Evaluator for campaign phase progression.

Evaluates whether a user meets the milestone conditions required to advance
from one campaign phase to the next: Foundation → Expansion → Launch.
"""

from __future__ import annotations

from typing import Any

from backend.engine.models import GateCondition, GateResult

GATE_CONDITIONS: dict[str, dict[str, float | int]] = {
    "foundation_to_expansion": {
        "min_completed_missions": 10,
        "min_categories": 3,
        "min_unique_skills": 8,
        "min_market_alignment": 40.0,
    },
    "expansion_to_launch": {
        "min_completed_missions": 25,
        "min_categories": 5,
        "min_unique_skills": 15,
        "min_portfolio_artifacts": 3,
        "min_market_alignment": 65.0,
    },
    "launch_completion": {
        "min_completed_missions": 40,
        "min_unique_skills": 20,
        "min_market_alignment": 80.0,
    },
}

_PHASE_TO_GATE: dict[str, str] = {
    "foundation": "foundation_to_expansion",
    "expansion": "expansion_to_launch",
    "launch": "launch_completion",
}

_NEXT_PHASE: dict[str, str | None] = {
    "foundation": "expansion",
    "expansion": "launch",
    "launch": None,
}


def _count_completed(missions: list[dict[str, Any]]) -> int:
    """Count total completed missions."""
    return len(missions)


def _count_unique_categories(missions: list[dict[str, Any]]) -> int:
    """Count unique mission categories among completed missions."""
    return len({m.get("category", "") for m in missions if m.get("category")})


def _count_portfolio_artifacts(missions: list[dict[str, Any]]) -> int:
    """Count completed missions in the portfolio category."""
    return sum(1 for m in missions if m.get("category") == "portfolio")


def _count_unique_skills(evidence_by_skill: dict[str, list[dict[str, Any]]]) -> int:
    """Count unique skills that have at least one evidence record."""
    return sum(1 for records in evidence_by_skill.values() if len(records) > 0)


def evaluate_gate(
    current_phase: str,
    completed_missions: list[dict[str, Any]],
    evidence_by_skill: dict[str, list[dict[str, Any]]],
    market_alignment_pct: float,
) -> GateResult:
    """Evaluate whether the user meets the gate conditions for the current phase.

    Args:
        current_phase: Current campaign phase ("foundation", "expansion", or "launch").
        completed_missions: List of completed mission dicts (each must have "category").
        evidence_by_skill: Evidence records grouped by skill name.
        market_alignment_pct: Current market alignment percentage (0-100).

    Returns:
        GateResult with passed status, next phase, and per-condition progress.
    """
    gate_key = _PHASE_TO_GATE.get(current_phase)
    if gate_key is None:
        return GateResult(
            passed=False,
            current_phase=current_phase,
            next_phase=None,
            conditions={},
        )

    requirements = GATE_CONDITIONS[gate_key]
    next_phase = _NEXT_PHASE[current_phase]

    total_completed = _count_completed(completed_missions)
    unique_categories = _count_unique_categories(completed_missions)
    unique_skills = _count_unique_skills(evidence_by_skill)
    portfolio_artifacts = _count_portfolio_artifacts(completed_missions)

    condition_evaluators: dict[str, tuple[float | int, float | int]] = {
        "min_completed_missions": (total_completed, requirements.get("min_completed_missions", 0)),
        "min_categories": (unique_categories, requirements.get("min_categories", 0)),
        "min_unique_skills": (unique_skills, requirements.get("min_unique_skills", 0)),
        "min_portfolio_artifacts": (portfolio_artifacts, requirements.get("min_portfolio_artifacts", 0)),
        "min_market_alignment": (market_alignment_pct, requirements.get("min_market_alignment", 0.0)),
    }

    conditions: dict[str, GateCondition] = {}
    all_met = True

    for condition_name, required_value in requirements.items():
        current_value = condition_evaluators[condition_name][0]
        met = current_value >= required_value
        conditions[condition_name] = GateCondition(
            required=required_value,
            current=current_value,
            met=met,
        )
        if not met:
            all_met = False

    return GateResult(
        passed=all_met,
        current_phase=current_phase,
        next_phase=next_phase if all_met else None,
        conditions=conditions,
    )
