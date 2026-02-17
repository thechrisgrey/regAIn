"""Unit tests for phase gate evaluation.

Tests evaluate_gate() across all three phase transitions,
edge cases, and progress reporting.
"""

from backend.engine.models import GateCondition, GateResult
from backend.engine.phase_gates import (
    GATE_CONDITIONS,
    evaluate_gate,
)


def _make_missions(count: int, categories: list[str] | None = None) -> list[dict]:
    """Build a list of completed mission dicts.

    If categories is provided, cycles through them. Otherwise defaults to
    "skill_building" for all missions.
    """
    cats = categories or ["skill_building"]
    return [{"category": cats[i % len(cats)]} for i in range(count)]


def _make_evidence(skill_count: int) -> dict[str, list[dict]]:
    """Build evidence_by_skill with the given number of unique skills."""
    return {f"skill_{i}": [{"id": f"ev_{i}"}] for i in range(skill_count)}


# ---------------------------------------------------------------------------
# Foundation → Expansion gate (Req 5.1)
# ---------------------------------------------------------------------------

class TestFoundationToExpansion:
    """Tests for the foundation → expansion gate."""

    def test_all_conditions_met(self):
        missions = _make_missions(12, ["reflection", "skill_building", "portfolio"])
        evidence = _make_evidence(10)
        result = evaluate_gate("foundation", missions, evidence, 50.0)

        assert result.passed is True
        assert result.current_phase == "foundation"
        assert result.next_phase == "expansion"
        assert all(c.met for c in result.conditions.values())

    def test_not_enough_missions(self):
        missions = _make_missions(5, ["reflection", "skill_building", "portfolio"])
        evidence = _make_evidence(10)
        result = evaluate_gate("foundation", missions, evidence, 50.0)

        assert result.passed is False
        assert result.next_phase is None
        assert result.conditions["min_completed_missions"].met is False
        assert result.conditions["min_completed_missions"].current == 5
        assert result.conditions["min_completed_missions"].required == 10

    def test_not_enough_categories(self):
        missions = _make_missions(12, ["skill_building"])  # only 1 category
        evidence = _make_evidence(10)
        result = evaluate_gate("foundation", missions, evidence, 50.0)

        assert result.passed is False
        assert result.conditions["min_categories"].met is False
        assert result.conditions["min_categories"].current == 1

    def test_not_enough_skills(self):
        missions = _make_missions(12, ["reflection", "skill_building", "portfolio"])
        evidence = _make_evidence(5)
        result = evaluate_gate("foundation", missions, evidence, 50.0)

        assert result.passed is False
        assert result.conditions["min_unique_skills"].met is False
        assert result.conditions["min_unique_skills"].current == 5

    def test_low_market_alignment(self):
        missions = _make_missions(12, ["reflection", "skill_building", "portfolio"])
        evidence = _make_evidence(10)
        result = evaluate_gate("foundation", missions, evidence, 30.0)

        assert result.passed is False
        assert result.conditions["min_market_alignment"].met is False
        assert result.conditions["min_market_alignment"].current == 30.0

    def test_exact_thresholds_pass(self):
        missions = _make_missions(10, ["reflection", "skill_building", "portfolio"])
        evidence = _make_evidence(8)
        result = evaluate_gate("foundation", missions, evidence, 40.0)

        assert result.passed is True
        assert result.next_phase == "expansion"


# ---------------------------------------------------------------------------
# Expansion → Launch gate (Req 5.2)
# ---------------------------------------------------------------------------

class TestExpansionToLaunch:
    """Tests for the expansion → launch gate."""

    def test_all_conditions_met(self):
        all_cats = ["reflection", "skill_building", "portfolio", "networking", "market_research"]
        missions = _make_missions(30, all_cats)
        evidence = _make_evidence(20)
        result = evaluate_gate("expansion", missions, evidence, 70.0)

        assert result.passed is True
        assert result.current_phase == "expansion"
        assert result.next_phase == "launch"

    def test_not_enough_portfolio_artifacts(self):
        # 25 missions but only 2 portfolio (cycling 5 cats → 5 of each)
        cats = ["reflection", "skill_building", "networking", "market_research", "portfolio"]
        missions = _make_missions(10, cats)  # 2 portfolio out of 10
        evidence = _make_evidence(15)
        result = evaluate_gate("expansion", missions, evidence, 65.0)

        assert result.passed is False
        assert result.conditions["min_portfolio_artifacts"].met is False

    def test_missing_categories(self):
        missions = _make_missions(30, ["reflection", "skill_building", "portfolio"])
        evidence = _make_evidence(20)
        result = evaluate_gate("expansion", missions, evidence, 70.0)

        assert result.passed is False
        assert result.conditions["min_categories"].met is False
        assert result.conditions["min_categories"].current == 3

    def test_exact_thresholds_pass(self):
        all_cats = ["reflection", "skill_building", "portfolio", "networking", "market_research"]
        # 25 missions cycling 5 cats → 5 each, 5 portfolio artifacts
        missions = _make_missions(25, all_cats)
        evidence = _make_evidence(15)
        result = evaluate_gate("expansion", missions, evidence, 65.0)

        assert result.passed is True


# ---------------------------------------------------------------------------
# Launch completion gate (Req 5.3)
# ---------------------------------------------------------------------------

class TestLaunchCompletion:
    """Tests for the launch completion gate."""

    def test_all_conditions_met(self):
        missions = _make_missions(45)
        evidence = _make_evidence(25)
        result = evaluate_gate("launch", missions, evidence, 85.0)

        assert result.passed is True
        assert result.current_phase == "launch"
        assert result.next_phase is None  # final phase

    def test_not_enough_missions(self):
        missions = _make_missions(35)
        evidence = _make_evidence(25)
        result = evaluate_gate("launch", missions, evidence, 85.0)

        assert result.passed is False
        assert result.conditions["min_completed_missions"].met is False

    def test_low_alignment(self):
        missions = _make_missions(45)
        evidence = _make_evidence(25)
        result = evaluate_gate("launch", missions, evidence, 75.0)

        assert result.passed is False
        assert result.conditions["min_market_alignment"].met is False

    def test_exact_thresholds_pass(self):
        missions = _make_missions(40)
        evidence = _make_evidence(20)
        result = evaluate_gate("launch", missions, evidence, 80.0)

        assert result.passed is True
        assert result.next_phase is None


# ---------------------------------------------------------------------------
# Edge cases and progress reporting (Req 5.5, 5.6)
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Edge cases and progress reporting."""

    def test_unknown_phase_returns_not_passed(self):
        result = evaluate_gate("unknown", [], {}, 0.0)
        assert result.passed is False
        assert result.next_phase is None
        assert result.conditions == {}

    def test_empty_missions_and_evidence(self):
        result = evaluate_gate("foundation", [], {}, 0.0)
        assert result.passed is False
        assert result.conditions["min_completed_missions"].current == 0
        assert result.conditions["min_unique_skills"].current == 0

    def test_evidence_with_empty_records_not_counted(self):
        evidence = {"python": [{"id": "1"}], "java": [], "rust": [{"id": "2"}]}
        missions = _make_missions(12, ["reflection", "skill_building", "portfolio"])
        result = evaluate_gate("foundation", missions, evidence, 50.0)

        # java has empty list → not counted
        assert result.conditions["min_unique_skills"].current == 2

    def test_progress_summary_shows_all_conditions(self):
        """Req 5.6: progress summary when conditions not met."""
        missions = _make_missions(5, ["skill_building"])
        evidence = _make_evidence(3)
        result = evaluate_gate("foundation", missions, evidence, 20.0)

        assert result.passed is False
        assert "min_completed_missions" in result.conditions
        assert "min_categories" in result.conditions
        assert "min_unique_skills" in result.conditions
        assert "min_market_alignment" in result.conditions

        # Verify current values are accurate
        assert result.conditions["min_completed_missions"].current == 5
        assert result.conditions["min_categories"].current == 1
        assert result.conditions["min_unique_skills"].current == 3
        assert result.conditions["min_market_alignment"].current == 20.0

    def test_gate_conditions_dict_matches_design(self):
        """Verify GATE_CONDITIONS matches the design spec exactly."""
        assert GATE_CONDITIONS["foundation_to_expansion"] == {
            "min_completed_missions": 10,
            "min_categories": 3,
            "min_unique_skills": 8,
            "min_market_alignment": 40.0,
        }
        assert GATE_CONDITIONS["expansion_to_launch"] == {
            "min_completed_missions": 25,
            "min_categories": 5,
            "min_unique_skills": 15,
            "min_portfolio_artifacts": 3,
            "min_market_alignment": 65.0,
        }
        assert GATE_CONDITIONS["launch_completion"] == {
            "min_completed_missions": 40,
            "min_unique_skills": 20,
            "min_market_alignment": 80.0,
        }
