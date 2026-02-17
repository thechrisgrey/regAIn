"""Property-based tests for mission generation round trip and structure.

# Feature: coaching-agent, Property 4: Mission generation round trip and structure

**Validates: Requirements 2.3, 7.2, 7.3**

For any valid user_id and campaign_id, calling generate_mission should return
a dict containing a "primary" key with all MissionCandidate fields, or an
error dict. The engine handles all generation logic; this test validates the
tool layer correctly wraps the engine result.

Uses moto-mocked DynamoDB via the shared dynamodb_tables fixture.
The @tool decorator from strands is stubbed since strands-agents is not
yet installed.
"""

import importlib
import sys
import types
from typing import Any, Dict
from unittest.mock import patch

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from backend.engine.models import (
    GenerationResult, MissionCandidate, SkillGapReport,
)


# ---------------------------------------------------------------------------
# Stub the strands module so tools.py can be imported without strands-agents
# ---------------------------------------------------------------------------
_strands_stub = types.ModuleType("strands")
_strands_stub.tool = lambda fn: fn  # @tool is a no-op passthrough
sys.modules.setdefault("strands", _strands_stub)


def _load_tools():
    """Import tools module with a fresh DynamoDBClient bound to moto tables."""
    mod_name = "backend.agents.coaching.tools"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    return importlib.import_module(mod_name)


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

_user_id_strategy = st.text(
    min_size=1,
    max_size=30,
    alphabet=st.characters(whitelist_categories=("L", "N", "Pd")),
)

_campaign_id_strategy = st.text(
    min_size=1,
    max_size=20,
    alphabet=st.characters(whitelist_categories=("L", "N", "Pd")),
).map(lambda s: f"campaign-{s}")

_category_strategy = st.sampled_from([
    "reflection", "skill_building", "portfolio", "networking", "market_research",
])

_phase_strategy = st.sampled_from(["foundation", "expansion", "launch"])

_skill_strategy = st.text(
    min_size=2, max_size=20,
    alphabet=st.characters(whitelist_categories=("Ll",)),
)


@st.composite
def _generation_result_strategy(draw):
    """Generate a valid GenerationResult with random data."""
    def _make_candidate():
        return MissionCandidate(
            template_id=f"tmpl-{draw(st.text(min_size=3, max_size=10, alphabet='abcdefghij'))}",
            category=draw(_category_strategy),
            title=draw(st.text(min_size=5, max_size=60, alphabet=st.characters(whitelist_categories=("L", "N", "Zs")))).strip() or "Default Title",
            description=draw(st.text(min_size=5, max_size=120, alphabet=st.characters(whitelist_categories=("L", "N", "Zs")))).strip() or "Default Description",
            rationale="Test rationale",
            skill_tags=draw(st.lists(_skill_strategy, min_size=1, max_size=3)),
            difficulty=draw(st.integers(min_value=1, max_value=5)),
            estimated_minutes=draw(st.integers(min_value=15, max_value=45)),
            expected_evidence_type=draw(st.sampled_from(["reflection", "artifact", "connection", "research"])),
            phase=draw(_phase_strategy),
            market_relevance_score=draw(st.floats(min_value=0.0, max_value=1.0)),
            priority_score=draw(st.floats(min_value=0.0, max_value=1.0)),
        )

    primary = _make_candidate()
    alt1 = _make_candidate()
    alt2 = _make_candidate()

    gap_report = SkillGapReport(
        skill_scores={draw(_skill_strategy): draw(st.floats(min_value=0.0, max_value=1.0))},
        market_alignment_pct=draw(st.floats(min_value=0.0, max_value=100.0)),
        priority_skills=draw(st.lists(_skill_strategy, min_size=0, max_size=5)),
        evidence_density={draw(_skill_strategy): draw(st.integers(min_value=0, max_value=10))},
    )

    return GenerationResult(primary=primary, alternates=[alt1, alt2], skill_gap_report=gap_report)


class TestMissionGenerationRoundTrip:
    """Property 4: Mission generation round trip and structure.

    For any valid engine GenerationResult, the generate_mission tool should
    return a dict with all required keys including primary, alternates, and
    skill_gap_report.
    """

    @given(
        user_id=_user_id_strategy,
        campaign_id=_campaign_id_strategy,
        gen_result=_generation_result_strategy(),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_generate_then_get_returns_matching_mission(
        self,
        dynamodb_tables: Dict[str, Any],
        user_id: str,
        campaign_id: str,
        gen_result: GenerationResult,
    ) -> None:
        """generate_mission wraps engine result with all MissionCandidate fields.

        # Feature: coaching-agent, Property 4: Mission generation round trip and structure
        **Validates: Requirements 2.3, 7.2, 7.3**
        """
        with patch("backend.engine.generator.generate_daily_mission") as mock_gen:
            mock_gen.return_value = gen_result
            tools = _load_tools()

            result = tools.generate_mission(user_id=user_id, campaign_id=campaign_id)

        # No error
        assert "error" not in result, f"generate_mission failed: {result}"

        # Has required top-level keys
        assert "primary" in result
        assert "alternates" in result
        assert "skill_gap_report" in result

        # Primary has all MissionCandidate fields
        primary = result["primary"]
        expected_fields = {
            "template_id", "category", "title", "description", "rationale",
            "skill_tags", "difficulty", "estimated_minutes",
            "expected_evidence_type", "phase", "market_relevance_score",
            "priority_score",
        }
        assert expected_fields.issubset(primary.keys()), (
            f"Missing fields: {expected_fields - primary.keys()}"
        )

        # Alternates is a list of 2
        assert len(result["alternates"]) == 2

        # Values match the engine result
        assert primary["title"] == gen_result.primary.title
        assert primary["category"] == gen_result.primary.category
