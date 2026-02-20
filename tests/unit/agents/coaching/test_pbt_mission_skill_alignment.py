"""Property-based tests for mission skill alignment.

# Feature: coaching-agent, Property 5: Mission skill alignment

**Validates: Requirements 2.4**

For any GenerationResult returned by the engine, the primary mission's
skill_tags should be non-empty lists of strings. The tool layer faithfully
passes through the engine's structured data.

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

_skill_strategy = st.text(
    min_size=2, max_size=20,
    alphabet=st.characters(whitelist_categories=("Ll",)),
)

_user_id_strategy = st.text(
    min_size=1, max_size=30,
    alphabet=st.characters(whitelist_categories=("L", "N", "Pd")),
)

_category_strategy = st.sampled_from([
    "reflection", "skill_building", "portfolio", "networking", "market_research",
])

_phase_strategy = st.sampled_from(["foundation", "expansion", "launch"])


@st.composite
def _skill_alignment_data(draw):
    """Generate a GenerationResult with known skill_tags for validation."""
    skill_tags = draw(st.lists(_skill_strategy, min_size=1, max_size=5, unique=True))

    def _make_candidate(tags):
        return MissionCandidate(
            template_id=f"tmpl-{draw(st.text(min_size=3, max_size=8, alphabet='abcdefghij'))}",
            category=draw(_category_strategy),
            title="Test Mission",
            description="A test mission description.",
            rationale="Test rationale",
            skill_tags=tags,
            difficulty=draw(st.integers(min_value=1, max_value=5)),
            estimated_minutes=draw(st.integers(min_value=15, max_value=45)),
            expected_evidence_type="reflection",
            phase=draw(_phase_strategy),
            market_relevance_score=0.5,
            priority_score=0.5,
        )

    primary = _make_candidate(skill_tags)
    alt1 = _make_candidate(draw(st.lists(_skill_strategy, min_size=1, max_size=3)))
    alt2 = _make_candidate(draw(st.lists(_skill_strategy, min_size=1, max_size=3)))

    gap_report = SkillGapReport(
        skill_scores={s: 0.5 for s in skill_tags},
        market_alignment_pct=50.0,
        priority_skills=skill_tags,
        evidence_density={s: 1 for s in skill_tags},
    )

    return {
        "user_id": draw(_user_id_strategy),
        "skill_tags": skill_tags,
        "gen_result": GenerationResult(
            primary=primary, alternates=[alt1, alt2], skill_gap_report=gap_report,
        ),
    }


class TestMissionSkillAlignment:
    """Property 5: Mission skill alignment.

    For any engine GenerationResult, the tool returns skill_tags as
    non-empty lists that match the engine's output exactly.
    """

    @given(data=_skill_alignment_data())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_mission_skill_tag_in_valid_pool(
        self,
        dynamodb_tables: Dict[str, Any],
        data: dict,
    ) -> None:
        """generate_mission returns skill_tags matching the engine result.

        # Feature: coaching-agent, Property 5: Mission skill alignment
        **Validates: Requirements 2.4**
        """
        with patch("backend.engine.generator.generate_daily_mission") as mock_gen:
            mock_gen.return_value = data["gen_result"]
            tools = _load_tools()

            with patch.object(tools, "_enforce_daily_rate_limit"):
                result = tools.generate_mission(
                    user_id=data["user_id"],
                    campaign_id="campaign-test",
                )

        assert "error" not in result, f"generate_mission failed: {result}"

        # Primary mission skill_tags match engine output
        returned_tags = result["primary"]["skill_tags"]
        assert returned_tags == data["skill_tags"]
        assert len(returned_tags) >= 1
