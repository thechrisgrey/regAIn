"""Property-based tests for the seed data loader module.

Feature: market-intelligence, Property 13: Seed data structure validity
Validates: Requirements 9.2, 9.5
"""

import importlib

from hypothesis import given, settings
from hypothesis import strategies as st

_seed_mod = importlib.import_module("backend.handlers.market_intel.seed")
_build_seed_records = _seed_mod._build_seed_records

_models_mod = importlib.import_module("backend.handlers.market_intel.models")
MarketDataRecord = _models_mod.MarketDataRecord

# All seed records (static data — built once for the module)
_SEED_RECORDS = _build_seed_records()

# Valid trend directions and their growth-rate ranges
_TREND_RULES: dict[str, tuple[str, ...]] = {
    "surging": ("growth_rate > 20",),
    "growing": ("5 <= growth_rate <= 20",),
    "stable": ("-5 <= growth_rate <= 5",),
    "declining": ("growth_rate < -5",),
}

VALID_TREND_DIRECTIONS = {"surging", "growing", "stable", "declining"}


# ---------------------------------------------------------------------------
# Property 13: Seed data structure validity
# Feature: market-intelligence, Property 13: Seed data structure validity
# Validates: Requirements 9.2, 9.5
# ---------------------------------------------------------------------------


class TestSeedDataStructureValidity:
    """Property 13 — For any seed record: all required fields present,
    top_skills has 10 entries with frequencies, salary min <= median <= max,
    source is 'synthetic'."""

    def test_exactly_five_seed_records(self) -> None:
        """Seed data covers all five transition paths."""
        assert len(_SEED_RECORDS) == 5

    def test_all_records_are_market_data_records(self) -> None:
        """Every seed record is a MarketDataRecord instance."""
        for record in _SEED_RECORDS:
            assert isinstance(record, MarketDataRecord)

    @given(record=st.sampled_from(_SEED_RECORDS))
    @settings(max_examples=100)
    def test_required_fields_present_and_nonempty(self, record: MarketDataRecord) -> None:
        """**Validates: Requirements 9.2**

        All required MarketDataRecord fields are present and non-empty.
        """
        assert isinstance(record.sector, str) and record.sector
        assert isinstance(record.timestamp, str) and record.timestamp
        assert isinstance(record.role_title, str) and record.role_title
        assert isinstance(record.category, str) and record.category
        assert isinstance(record.demand_score, int)
        assert isinstance(record.growth_rate, float)
        assert isinstance(record.trend_direction, str) and record.trend_direction
        assert isinstance(record.top_skills, list)
        assert isinstance(record.salary_range, dict)
        assert isinstance(record.posting_volume, int)
        assert isinstance(record.projection, str) and record.projection
        assert isinstance(record.source, str) and record.source

    @given(record=st.sampled_from(_SEED_RECORDS))
    @settings(max_examples=100)
    def test_top_skills_has_ten_entries(self, record: MarketDataRecord) -> None:
        """**Validates: Requirements 9.2**

        Each seed record has exactly 10 top_skills entries.
        """
        assert len(record.top_skills) == 10

    @given(record=st.sampled_from(_SEED_RECORDS))
    @settings(max_examples=100)
    def test_top_skills_have_required_keys(self, record: MarketDataRecord) -> None:
        """**Validates: Requirements 9.2**

        Each top_skill entry has 'skill', 'frequency', and 'canonical' keys.
        """
        for skill_entry in record.top_skills:
            assert "skill" in skill_entry, f"Missing 'skill' key in {skill_entry}"
            assert "frequency" in skill_entry, f"Missing 'frequency' key in {skill_entry}"
            assert "canonical" in skill_entry, f"Missing 'canonical' key in {skill_entry}"

    @given(record=st.sampled_from(_SEED_RECORDS))
    @settings(max_examples=100)
    def test_top_skills_frequencies_are_positive(self, record: MarketDataRecord) -> None:
        """**Validates: Requirements 9.2**

        Each top_skill frequency is a positive float.
        """
        for skill_entry in record.top_skills:
            freq = skill_entry["frequency"]
            assert isinstance(freq, (int, float)), f"Frequency not numeric: {freq}"
            assert freq > 0, f"Frequency not positive: {freq}"

    @given(record=st.sampled_from(_SEED_RECORDS))
    @settings(max_examples=100)
    def test_salary_range_has_required_keys(self, record: MarketDataRecord) -> None:
        """**Validates: Requirements 9.2**

        salary_range has min, median, max, and region keys.
        """
        sr = record.salary_range
        assert "min" in sr, "Missing 'min' in salary_range"
        assert "median" in sr, "Missing 'median' in salary_range"
        assert "max" in sr, "Missing 'max' in salary_range"
        assert "region" in sr, "Missing 'region' in salary_range"

    @given(record=st.sampled_from(_SEED_RECORDS))
    @settings(max_examples=100)
    def test_salary_range_ordering(self, record: MarketDataRecord) -> None:
        """**Validates: Requirements 9.2**

        salary_range: min <= median <= max.
        """
        sr = record.salary_range
        assert sr["min"] <= sr["median"] <= sr["max"], (
            f"Salary ordering violated: min={sr['min']}, "
            f"median={sr['median']}, max={sr['max']}"
        )

    @given(record=st.sampled_from(_SEED_RECORDS))
    @settings(max_examples=100)
    def test_source_is_synthetic(self, record: MarketDataRecord) -> None:
        """**Validates: Requirements 9.5**

        All seed records have source='synthetic'.
        """
        assert record.source == "synthetic"

    @given(record=st.sampled_from(_SEED_RECORDS))
    @settings(max_examples=100)
    def test_trend_direction_consistent_with_growth_rate(self, record: MarketDataRecord) -> None:
        """**Validates: Requirements 9.2**

        trend_direction is consistent with growth_rate:
        >20% surging, 5-20% growing, -5 to 5% stable, <-5% declining.
        """
        gr = record.growth_rate
        td = record.trend_direction

        if gr > 20:
            assert td == "surging", f"growth_rate={gr} should be surging, got {td}"
        elif gr >= 5:
            assert td == "growing", f"growth_rate={gr} should be growing, got {td}"
        elif gr >= -5:
            assert td == "stable", f"growth_rate={gr} should be stable, got {td}"
        else:
            assert td == "declining", f"growth_rate={gr} should be declining, got {td}"

    @given(record=st.sampled_from(_SEED_RECORDS))
    @settings(max_examples=100)
    def test_demand_score_in_valid_range(self, record: MarketDataRecord) -> None:
        """**Validates: Requirements 9.2**

        demand_score is in [0, 100].
        """
        assert 0 <= record.demand_score <= 100

    @given(record=st.sampled_from(_SEED_RECORDS))
    @settings(max_examples=100)
    def test_sector_starts_with_role_prefix(self, record: MarketDataRecord) -> None:
        """**Validates: Requirements 9.2**

        sector starts with 'role:'.
        """
        assert record.sector.startswith("role:"), (
            f"sector should start with 'role:', got '{record.sector}'"
        )
