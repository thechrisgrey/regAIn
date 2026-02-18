"""Property-based tests for the REGAIN demand scoring module.

Tests Property 7 from the Market Intelligence design document using
Hypothesis for property-based testing.

**Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5**
"""

import importlib

from hypothesis import given, settings
from hypothesis import strategies as st

# 'lambda' is a Python keyword — use importlib to import the scoring module.
_scoring_mod = importlib.import_module("backend.lambda.market_intel.scoring")

calculate_demand_score = _scoring_mod.calculate_demand_score
get_trend_direction = _scoring_mod.get_trend_direction
_growth_rate_score = _scoring_mod._growth_rate_score
_projection_score = _scoring_mod._projection_score
_percentile_rank = _scoring_mod._percentile_rank

# Valid BLS projection categories
_VALID_PROJECTIONS = [
    "Much faster than average",
    "Faster than average",
    "Average",
    "Slower than average",
    "Decline",
    "Unknown",
]

# Strategy: top_skills list — dicts with "skill" and "frequency" keys
_skill_entry_st = st.fixed_dictionaries({
    "skill": st.text(min_size=1, max_size=30),
    "frequency": st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
})

_top_skills_st = st.lists(_skill_entry_st, min_size=0, max_size=15)

# Strategy: salary_range dict where min <= median <= max
_salary_range_st = st.tuples(
    st.integers(min_value=20000, max_value=300000),
    st.integers(min_value=20000, max_value=300000),
    st.integers(min_value=20000, max_value=300000),
).map(lambda t: sorted(t)).map(
    lambda vals: {"min": vals[0], "median": vals[1], "max": vals[2], "region": "national"}
)


# ---------------------------------------------------------------------------
# Property 7: Demand score invariants
# Feature: market-intelligence, Property 7: Demand score invariants
# For any valid inputs: score in [0,100], components in their ranges,
# components sum to score, trend_direction matches growth_rate,
# top_skills sorted by frequency desc, salary min <= median <= max.
# **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5**
# ---------------------------------------------------------------------------


@given(
    posting_volume=st.integers(min_value=0, max_value=10000),
    growth_rate=st.floats(min_value=-50.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    median_salary=st.integers(min_value=20000, max_value=300000),
    projection=st.sampled_from(_VALID_PROJECTIONS),
    all_posting_volumes=st.lists(st.integers(min_value=0, max_value=10000), min_size=1, max_size=20),
    all_median_salaries=st.lists(st.integers(min_value=20000, max_value=300000), min_size=1, max_size=20),
    top_skills=_top_skills_st,
    salary_range=_salary_range_st,
)
@settings(max_examples=100)
def test_property7_demand_score_invariants(
    posting_volume: int,
    growth_rate: float,
    median_salary: int,
    projection: str,
    all_posting_volumes: list[int],
    all_median_salaries: list[int],
    top_skills: list[dict],
    salary_range: dict,
) -> None:
    """All demand score invariants hold for any valid inputs."""
    result = calculate_demand_score(
        posting_volume=posting_volume,
        growth_rate=growth_rate,
        median_salary=median_salary,
        projection=projection,
        all_posting_volumes=all_posting_volumes,
        all_median_salaries=all_median_salaries,
        top_skills=top_skills,
        salary_range=salary_range,
    )

    # 1. demand_score is int in [0, 100]
    assert isinstance(result["demand_score"], int)
    assert 0 <= result["demand_score"] <= 100, (
        f"demand_score {result['demand_score']} out of [0, 100]"
    )

    components = result["components"]

    # 2. posting_volume component in [0, 25]
    assert 0 <= components["posting_volume"] <= 25, (
        f"posting_volume component {components['posting_volume']} out of [0, 25]"
    )

    # 3. growth_rate component in [0, 30]
    assert 0 <= components["growth_rate"] <= 30, (
        f"growth_rate component {components['growth_rate']} out of [0, 30]"
    )

    # 4. salary_signal component in [0, 20]
    assert 0 <= components["salary_signal"] <= 20, (
        f"salary_signal component {components['salary_signal']} out of [0, 20]"
    )

    # 5. projection component in [0, 25]
    assert 0 <= components["projection"] <= 25, (
        f"projection component {components['projection']} out of [0, 25]"
    )

    # 6. Sum of 4 components equals demand_score
    component_sum = (
        components["posting_volume"]
        + components["growth_rate"]
        + components["salary_signal"]
        + components["projection"]
    )
    assert component_sum == result["demand_score"], (
        f"Component sum {component_sum} != demand_score {result['demand_score']}"
    )

    # 7. trend_direction matches growth_rate thresholds
    td = result["trend_direction"]
    if growth_rate > 20:
        assert td == "surging", f"Expected 'surging' for growth_rate={growth_rate}, got '{td}'"
    elif growth_rate >= 5:
        assert td == "growing", f"Expected 'growing' for growth_rate={growth_rate}, got '{td}'"
    elif growth_rate >= -5:
        assert td == "stable", f"Expected 'stable' for growth_rate={growth_rate}, got '{td}'"
    else:
        assert td == "declining", f"Expected 'declining' for growth_rate={growth_rate}, got '{td}'"

    # 8. top_skills sorted by frequency descending
    returned_skills = result["top_skills"]
    frequencies = [s.get("frequency", 0) for s in returned_skills]
    for i in range(len(frequencies) - 1):
        assert frequencies[i] >= frequencies[i + 1], (
            f"top_skills not sorted by frequency desc at index {i}: "
            f"{frequencies[i]} < {frequencies[i + 1]}"
        )

    # 9. salary_range min <= median <= max (when provided)
    sr = result["salary_range"]
    if sr:
        assert sr["min"] <= sr["median"] <= sr["max"], (
            f"salary_range ordering violated: min={sr['min']}, "
            f"median={sr['median']}, max={sr['max']}"
        )
