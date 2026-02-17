"""Property-based tests for mission skill alignment.

# Feature: coaching-agent, Property 5: Mission skill alignment

**Validates: Requirements 2.4**

For any generated mission for a user, the mission's skill_tag should be
present in the user's Transition Profile skills (the union of
transferable_skills, technical_skills, and domain_knowledge) or in the
MarketData skill_demand list for the user's target sector.

Uses moto-mocked DynamoDB via the shared dynamodb_tables fixture.
The @tool decorator from strands is stubbed since strands-agents is not
yet installed.
"""

import importlib
import sys
import types
from datetime import datetime, timezone
from typing import Any, Dict

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

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

# Skill names: lowercase alpha strings, 2-20 chars
_skill_strategy = st.text(
    min_size=2,
    max_size=20,
    alphabet=st.characters(whitelist_categories=("Ll",)),
)

# User IDs: non-empty alphanumeric strings with dashes
_user_id_strategy = st.text(
    min_size=1,
    max_size=30,
    alphabet=st.characters(whitelist_categories=("L", "N", "Pd")),
)

# Sector names: lowercase alpha strings
_sector_strategy = st.text(
    min_size=2,
    max_size=20,
    alphabet=st.characters(whitelist_categories=("Ll",)),
)


@st.composite
def _skill_alignment_data(draw):
    """Generate a user profile with skills and market data with skill_demand.

    Produces three disjoint skill lists (transferable, technical, domain)
    with at least 1 skill total, a market skill_demand list (may overlap
    with profile skills), and picks one skill_tag from the valid pool.
    """
    # Generate three disjoint skill lists
    all_skills = draw(
        st.lists(_skill_strategy, min_size=1, max_size=15, unique=True)
    )

    # Partition into three disjoint groups
    transferable: list[str] = []
    technical: list[str] = []
    domain: list[str] = []

    for i, skill in enumerate(all_skills):
        bucket = i % 3
        if bucket == 0:
            transferable.append(skill)
        elif bucket == 1:
            technical.append(skill)
        else:
            domain.append(skill)

    # Market skill_demand: independent list, may overlap with profile skills
    market_skills = draw(
        st.lists(_skill_strategy, min_size=0, max_size=10, unique=True)
    )

    # Valid pool = union of all profile skills + market demand
    valid_pool = list(set(transferable + technical + domain + market_skills))

    # Pick one skill_tag from the valid pool
    skill_tag = draw(st.sampled_from(valid_pool))

    user_id = draw(_user_id_strategy)
    sector = draw(_sector_strategy)

    return {
        "user_id": user_id,
        "sector": sector,
        "transferable_skills": transferable,
        "technical_skills": technical,
        "domain_knowledge": domain,
        "market_skill_demand": market_skills,
        "valid_pool": set(valid_pool),
        "skill_tag": skill_tag,
    }


class TestMissionSkillAlignment:
    """Property 5: Mission skill alignment.

    For any generated mission, the skill_tag must be present in the
    user's profile skills or in the market skill_demand for the sector.
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
        """generate_mission skill_tag is in profile skills or market demand.

        # Feature: coaching-agent, Property 5: Mission skill alignment
        **Validates: Requirements 2.4**
        """
        tools = _load_tools()

        user_id = data["user_id"]
        sector = data["sector"]
        skill_tag = data["skill_tag"]
        valid_pool = data["valid_pool"]

        # --- Seed user profile with known skills ---
        profile_table = dynamodb_tables["user_profiles"]
        profile_table.put_item(Item={
            "userId": user_id,
            "name": "Test User",
            "persona": "ai_displaced",
            "targetRole": "Engineer",
            "transferable_skills": data["transferable_skills"],
            "technical_skills": data["technical_skills"],
            "domain_knowledge": data["domain_knowledge"],
            "onboarding_completed": True,
        })

        # --- Seed market data with known skill_demand ---
        market_table = dynamodb_tables["market_data"]
        market_table.put_item(Item={
            "sector": sector,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "skill_demand": data["market_skill_demand"],
            "job_trends": {},
            "salary_ranges": {},
            "data_source": "test",
        })

        # --- Generate a mission with the chosen skill_tag ---
        gen_result = tools.generate_mission(
            user_id=user_id,
            campaign_id="campaign-test",
            title="Test Mission",
            description="A test mission for skill alignment",
            skill_tag=skill_tag,
        )

        # --- Assert: no error ---
        assert "error" not in gen_result, f"generate_mission failed: {gen_result}"

        # --- Assert: the mission's skillTag is in the valid pool ---
        returned_skill = gen_result["skillTag"]
        assert returned_skill in valid_pool, (
            f"Mission skillTag {returned_skill!r} not in valid pool. "
            f"Profile skills: {data['transferable_skills'] + data['technical_skills'] + data['domain_knowledge']}, "
            f"Market demand: {data['market_skill_demand']}"
        )

        # --- Read back from DynamoDB and verify ---
        mission_table = dynamodb_tables["mission_history"]
        response = mission_table.get_item(
            Key={"userId": user_id, "missionId": gen_result["missionId"]}
        )
        stored_mission = response.get("Item", {})
        assert stored_mission["skillTag"] in valid_pool, (
            f"Stored mission skillTag {stored_mission['skillTag']!r} "
            f"not in valid pool"
        )
