"""Property-based tests for behavioral pattern detection accuracy.

# Feature: coaching-agent, Property 9: Behavioral pattern detection accuracy

**Validates: Requirements 4.1**

For any mission history where a skill category has more than 50% skip rate,
the _analyze_patterns function should include that category in the
avoidance_signals list. Conversely, for any skill category with 0% skip rate
and at least one completion, it should appear in strength_signals.

_analyze_patterns is a pure function — no DynamoDB or fixtures needed.
"""

import importlib
import sys
import types

from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Stub the strands module so tools.py can be imported without strands-agents
# ---------------------------------------------------------------------------
_strands_stub = types.ModuleType("strands")
_strands_stub.tool = lambda fn: fn  # @tool is a no-op passthrough
sys.modules.setdefault("strands", _strands_stub)


def _load_tools():
    """Import tools module fresh to pick up the _analyze_patterns helper."""
    mod_name = "backend.agents.coaching.tools"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    return importlib.import_module(mod_name)


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

_STATUSES = ["pending", "in_progress", "completed", "skipped"]

# Skill tags: short lowercase alpha strings
_skill_tag_strategy = st.text(
    min_size=1,
    max_size=15,
    alphabet=st.characters(whitelist_categories=("Ll",)),
)

# A single mission dict
_mission_strategy = st.builds(
    lambda status, skill_tag: {"status": status, "skillTag": skill_tag},
    status=st.sampled_from(_STATUSES),
    skill_tag=_skill_tag_strategy,
)

# A list of missions (at least one so patterns are meaningful)
_mission_list_strategy = st.lists(_mission_strategy, min_size=1, max_size=60)


def _build_missions_with_avoidance(
    category: str, skip_count: int, other_count: int, other_status: str
) -> list[dict]:
    """Build a mission list where `category` has a controlled skip distribution."""
    missions: list[dict] = []
    for _ in range(skip_count):
        missions.append({"status": "skipped", "skillTag": category})
    for _ in range(other_count):
        missions.append({"status": other_status, "skillTag": category})
    return missions


def _build_missions_with_strength(
    category: str, completed_count: int, non_skip_extra: int
) -> list[dict]:
    """Build a mission list where `category` has 0 skips and >=1 completion."""
    missions: list[dict] = []
    for _ in range(completed_count):
        missions.append({"status": "completed", "skillTag": category})
    for _ in range(non_skip_extra):
        missions.append({"status": "pending", "skillTag": category})
    return missions


class TestBehavioralPatternDetection:
    """Property 9: Behavioral pattern detection accuracy.

    For any mission history where a skill category has >50% skip rate,
    that category must appear in avoidance_signals. For any category with
    0% skip rate and >=1 completion, it must appear in strength_signals.
    """

    @given(data=st.data())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_avoidance_signal_detected_for_high_skip_rate(self, data: st.DataObject) -> None:
        """Categories with >50% skip rate appear in avoidance_signals.

        # Feature: coaching-agent, Property 9: Behavioral pattern detection accuracy
        **Validates: Requirements 4.1**
        """
        tools = _load_tools()

        category = data.draw(_skill_tag_strategy, label="category")
        # Total missions for this category: at least 1
        total = data.draw(st.integers(min_value=1, max_value=30), label="total")
        # Skip count must be strictly > 50% of total
        min_skips = (total // 2) + 1
        skip_count = data.draw(
            st.integers(min_value=min_skips, max_value=total), label="skip_count"
        )
        other_count = total - skip_count
        # Remaining missions can be any non-skip status
        other_status = data.draw(
            st.sampled_from(["pending", "in_progress", "completed"]),
            label="other_status",
        )

        missions = _build_missions_with_avoidance(category, skip_count, other_count, other_status)
        result = tools._analyze_patterns(missions)

        assert category in result["avoidance_signals"], (
            f"Category '{category}' has skip rate {skip_count}/{total} "
            f"(>{0.5}) but not in avoidance_signals: {result['avoidance_signals']}"
        )

    @given(data=st.data())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_strength_signal_detected_for_zero_skip_with_completions(
        self, data: st.DataObject
    ) -> None:
        """Categories with 0% skip rate and >=1 completion appear in strength_signals.

        # Feature: coaching-agent, Property 9: Behavioral pattern detection accuracy
        **Validates: Requirements 4.1**
        """
        tools = _load_tools()

        category = data.draw(_skill_tag_strategy, label="category")
        completed_count = data.draw(
            st.integers(min_value=1, max_value=20), label="completed_count"
        )
        # Extra non-skip missions (pending or in_progress only — no skips)
        non_skip_extra = data.draw(
            st.integers(min_value=0, max_value=10), label="non_skip_extra"
        )

        missions = _build_missions_with_strength(category, completed_count, non_skip_extra)
        result = tools._analyze_patterns(missions)

        assert category in result["strength_signals"], (
            f"Category '{category}' has 0 skips and {completed_count} completions "
            f"but not in strength_signals: {result['strength_signals']}"
        )

    @given(missions=_mission_list_strategy)
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_avoidance_and_strength_signals_are_mutually_exclusive(
        self, missions: list[dict]
    ) -> None:
        """No category can appear in both avoidance_signals and strength_signals.

        # Feature: coaching-agent, Property 9: Behavioral pattern detection accuracy
        **Validates: Requirements 4.1**

        A category with >50% skip rate cannot simultaneously have 0% skip rate,
        so these sets must be disjoint for any input.
        """
        tools = _load_tools()
        result = tools._analyze_patterns(missions)

        avoidance = set(result["avoidance_signals"])
        strength = set(result["strength_signals"])

        assert avoidance.isdisjoint(strength), (
            f"Overlap between avoidance and strength signals: {avoidance & strength}"
        )

    @given(missions=_mission_list_strategy)
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_all_high_skip_categories_detected(self, missions: list[dict]) -> None:
        """Every category with >50% skip rate appears in avoidance_signals.

        # Feature: coaching-agent, Property 9: Behavioral pattern detection accuracy
        **Validates: Requirements 4.1**
        """
        tools = _load_tools()
        result = tools._analyze_patterns(missions)

        by_category = result["by_category"]
        for cat, counts in by_category.items():
            assigned = counts["assigned"]
            if assigned > 0 and counts["skipped"] / assigned > 0.5:
                assert cat in result["avoidance_signals"], (
                    f"Category '{cat}' has skip rate {counts['skipped']}/{assigned} "
                    f"but missing from avoidance_signals"
                )

    @given(missions=_mission_list_strategy)
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_all_zero_skip_completed_categories_detected(self, missions: list[dict]) -> None:
        """Every category with 0 skips and >=1 completion appears in strength_signals.

        # Feature: coaching-agent, Property 9: Behavioral pattern detection accuracy
        **Validates: Requirements 4.1**
        """
        tools = _load_tools()
        result = tools._analyze_patterns(missions)

        by_category = result["by_category"]
        for cat, counts in by_category.items():
            if counts["skipped"] == 0 and counts["completed"] >= 1:
                assert cat in result["strength_signals"], (
                    f"Category '{cat}' has 0 skips and {counts['completed']} completions "
                    f"but missing from strength_signals"
                )
