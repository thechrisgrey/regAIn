"""Unit tests for the insight generation module.

Tests all five generate functions, INSIGHT_TEMPLATES completeness,
and the get_insights DynamoDB query function.
"""

import importlib
import re
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

_models_mod = importlib.import_module("backend.lambda.market_intel.models")
MarketDataRecord = _models_mod.MarketDataRecord
AlignmentResult = _models_mod.AlignmentResult
MarketInsight = _models_mod.MarketInsight

_insights_mod = importlib.import_module("backend.lambda.market_intel.insights")
INSIGHT_TEMPLATES = _insights_mod.INSIGHT_TEMPLATES
generate_role_trend_insight = _insights_mod.generate_role_trend_insight
generate_alignment_insight = _insights_mod.generate_alignment_insight
generate_gap_opportunity_insight = _insights_mod.generate_gap_opportunity_insight
generate_emerging_role_insight = _insights_mod.generate_emerging_role_insight
generate_milestone_insight = _insights_mod.generate_milestone_insight
get_insights = _insights_mod.get_insights

VALID_TYPES = {"role_trend", "alignment", "gap_opportunity", "emerging_role", "milestone"}
PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


def _make_record(**overrides) -> MarketDataRecord:
    """Build a MarketDataRecord with sensible defaults."""
    defaults = {
        "sector": "role:ai_qa_engineer",
        "timestamp": "2025-01-15",
        "role_title": "AI QA Engineer",
        "category": "technology",
        "demand_score": 78,
        "growth_rate": 22.5,
        "trend_direction": "surging",
        "top_skills": [{"skill": "Python", "frequency": 85}],
        "salary_range": {"min": 80000, "median": 110000, "max": 140000, "region": "national"},
        "posting_volume": 1200,
        "projection": "Much faster than average",
        "source": "composite",
        "insights": [],
    }
    defaults.update(overrides)
    return MarketDataRecord(**defaults)


def _make_alignment(**overrides) -> AlignmentResult:
    """Build an AlignmentResult with sensible defaults."""
    defaults = {
        "alignment_pct": 60.3,
        "skill_breakdown": [
            {"skill": "Python", "user_score": 1.0, "market_weight": 0.85, "gap": 0.0},
            {"skill": "CI/CD", "user_score": 0.3, "market_weight": 0.60, "gap": 0.42},
            {"skill": "ML", "user_score": 0.0, "market_weight": 0.45, "gap": 0.45},
        ],
        "top_gaps": [
            {"skill": "ML", "user_score": 0.0, "market_weight": 0.45, "gap": 0.45},
            {"skill": "CI/CD", "user_score": 0.3, "market_weight": 0.60, "gap": 0.42},
        ],
        "top_strengths": [
            {"skill": "Python", "user_score": 1.0, "market_weight": 0.85, "gap": 0.0},
        ],
        "target_role_id": "ai_qa_engineer",
        "user_id": "user-123",
        "calculated_at": "2025-01-15T12:00:00+00:00",
    }
    defaults.update(overrides)
    return AlignmentResult(**defaults)


def _assert_valid_insight(insight: MarketInsight, expected_type: str) -> None:
    """Shared assertions for any generated insight."""
    assert isinstance(insight, MarketInsight)
    assert insight.type == expected_type
    assert insight.type in VALID_TYPES
    assert insight.role_id
    assert insight.message_template
    assert isinstance(insight.data_payload, dict)
    assert insight.generated_date
    assert insight.shown is False

    # Property 10: all template placeholders have matching data_payload keys
    placeholders = set(PLACEHOLDER_RE.findall(insight.message_template))
    assert placeholders, "Template should have at least one placeholder"
    missing = placeholders - set(insight.data_payload.keys())
    assert not missing, f"Missing data_payload keys for placeholders: {missing}"


# --- INSIGHT_TEMPLATES ---

class TestInsightTemplates:
    def test_all_five_types_present(self):
        assert set(INSIGHT_TEMPLATES.keys()) == VALID_TYPES

    def test_templates_are_nonempty_strings(self):
        for key, tmpl in INSIGHT_TEMPLATES.items():
            assert isinstance(tmpl, str)
            assert len(tmpl) > 0, f"Template for {key} is empty"

    def test_templates_have_placeholders(self):
        for key, tmpl in INSIGHT_TEMPLATES.items():
            placeholders = PLACEHOLDER_RE.findall(tmpl)
            assert len(placeholders) > 0, f"Template {key} has no placeholders"


# --- generate_role_trend_insight ---

class TestRoleTrendInsight:
    def test_basic_generation(self):
        record = _make_record()
        insight = generate_role_trend_insight(record)
        _assert_valid_insight(insight, "role_trend")
        assert insight.role_id == "ai_qa_engineer"
        assert insight.data_payload["role_title"] == "AI QA Engineer"
        assert insight.data_payload["trend_direction"] == "surging"
        assert insight.data_payload["growth_rate"] == 22.5
        assert insight.data_payload["demand_score"] == 78
        assert insight.user_id is None

    def test_strips_role_prefix(self):
        record = _make_record(sector="role:project_manager")
        insight = generate_role_trend_insight(record)
        assert insight.role_id == "project_manager"

    def test_sector_without_prefix(self):
        record = _make_record(sector="data_analyst")
        insight = generate_role_trend_insight(record)
        assert insight.role_id == "data_analyst"


# --- generate_alignment_insight ---

class TestAlignmentInsight:
    def test_basic_generation(self):
        alignment = _make_alignment()
        insight = generate_alignment_insight(alignment, "AI QA Engineer")
        _assert_valid_insight(insight, "alignment")
        assert insight.role_id == "ai_qa_engineer"
        assert insight.user_id == "user-123"
        assert insight.data_payload["alignment_pct"] == 60.3
        assert "Python" in insight.data_payload["top_strengths"]
        assert "ML" in insight.data_payload["top_gaps"]

    def test_empty_strengths_and_gaps(self):
        alignment = _make_alignment(top_strengths=[], top_gaps=[])
        insight = generate_alignment_insight(alignment, "Test Role")
        assert insight.data_payload["top_strengths"] == "none"
        assert insight.data_payload["top_gaps"] == "none"


# --- generate_gap_opportunity_insight ---

class TestGapOpportunityInsight:
    def test_basic_generation(self):
        insight = generate_gap_opportunity_insight(
            skill_name="Machine Learning",
            frequency=45.0,
            evidence_count=0,
            role_id="ai_qa_engineer",
            role_title="AI QA Engineer",
            user_id="user-123",
        )
        _assert_valid_insight(insight, "gap_opportunity")
        assert insight.role_id == "ai_qa_engineer"
        assert insight.user_id == "user-123"
        assert insight.data_payload["skill_name"] == "Machine Learning"
        assert insight.data_payload["frequency"] == 45.0
        assert insight.data_payload["evidence_count"] == 0

    def test_no_user_id(self):
        insight = generate_gap_opportunity_insight(
            skill_name="Python",
            frequency=85.0,
            evidence_count=3,
            role_id="data_analyst",
            role_title="Data Analyst",
        )
        assert insight.user_id is None


# --- generate_emerging_role_insight ---

class TestEmergingRoleInsight:
    def test_basic_generation(self):
        record = _make_record(demand_score=85)
        insight = generate_emerging_role_insight(record, alignment_pct=42.7)
        _assert_valid_insight(insight, "emerging_role")
        assert insight.role_id == "ai_qa_engineer"
        assert insight.data_payload["demand_score"] == 85
        assert insight.data_payload["alignment_pct"] == 42.7
        assert insight.user_id is None


# --- generate_milestone_insight ---

class TestMilestoneInsight:
    def test_basic_generation(self):
        previous = _make_alignment(alignment_pct=45.0)
        current = _make_alignment(
            alignment_pct=60.3,
            skill_breakdown=[
                {"skill": "Python", "user_score": 1.0, "market_weight": 0.85, "gap": 0.0},
                {"skill": "CI/CD", "user_score": 0.6, "market_weight": 0.60, "gap": 0.24},
                {"skill": "ML", "user_score": 0.3, "market_weight": 0.45, "gap": 0.315},
            ],
        )
        insight = generate_milestone_insight(previous, current, "AI QA Engineer")
        _assert_valid_insight(insight, "milestone")
        assert insight.data_payload["previous_pct"] == 45.0
        assert insight.data_payload["current_pct"] == 60.3
        assert insight.user_id == "user-123"
        # CI/CD went 0.3→0.6, ML went 0.0→0.3
        improved = insight.data_payload["skills_improved"]
        assert "CI/CD" in improved
        assert "ML" in improved
        # Python stayed at 1.0 — should NOT be in improved
        assert "Python" not in improved

    def test_no_improvement(self):
        previous = _make_alignment(alignment_pct=60.0)
        current = _make_alignment(alignment_pct=60.0)
        insight = generate_milestone_insight(previous, current, "Test Role")
        assert insight.data_payload["skills_improved"] == "none"

    def test_new_skill_in_current(self):
        """A skill present in current but not in previous counts as improved."""
        previous = _make_alignment(
            alignment_pct=30.0,
            skill_breakdown=[
                {"skill": "Python", "user_score": 0.6, "market_weight": 0.85, "gap": 0.34},
            ],
        )
        current = _make_alignment(
            alignment_pct=50.0,
            skill_breakdown=[
                {"skill": "Python", "user_score": 0.6, "market_weight": 0.85, "gap": 0.34},
                {"skill": "Docker", "user_score": 0.3, "market_weight": 0.40, "gap": 0.28},
            ],
        )
        insight = generate_milestone_insight(previous, current, "Test Role")
        # Docker is new (prev_score defaults to 0.0, current is 0.3)
        assert "Docker" in insight.data_payload["skills_improved"]
        assert "Python" not in insight.data_payload["skills_improved"]


# --- get_insights ---

class TestGetInsights:
    @patch.object(_insights_mod, "DynamoDBClient")
    def test_filters_by_role(self, mock_db_cls):
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db
        mock_db.query.return_value = [
            {
                "sector": "role:ai_qa_engineer",
                "timestamp": "2025-01-15",
                "insights": [
                    {"type": "role_trend", "role_id": "ai_qa_engineer"},
                    {"type": "alignment", "role_id": "ai_qa_engineer", "user_id": "u1"},
                ],
            }
        ]

        results = get_insights(role_id="ai_qa_engineer")
        assert len(results) == 2
        mock_db.query.assert_called_once()

    @patch.object(_insights_mod, "DynamoDBClient")
    def test_filters_by_user_id(self, mock_db_cls):
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db
        mock_db.query.return_value = [
            {
                "sector": "role:ai_qa_engineer",
                "insights": [
                    {"type": "alignment", "user_id": "u1"},
                    {"type": "alignment", "user_id": "u2"},
                ],
            }
        ]

        results = get_insights(role_id="ai_qa_engineer", user_id="u1")
        assert len(results) == 1
        assert results[0]["user_id"] == "u1"

    @patch.object(_insights_mod, "DynamoDBClient")
    def test_filters_by_insight_type(self, mock_db_cls):
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db
        mock_db.query.return_value = [
            {
                "sector": "role:pm",
                "insights": [
                    {"type": "role_trend"},
                    {"type": "milestone", "user_id": "u1"},
                ],
            }
        ]

        results = get_insights(role_id="pm", insight_type="milestone")
        assert len(results) == 1
        assert results[0]["type"] == "milestone"

    @patch.object(_insights_mod, "DynamoDBClient")
    def test_returns_empty_on_error(self, mock_db_cls):
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db
        mock_db.query.side_effect = Exception("DynamoDB error")

        results = get_insights(role_id="ai_qa_engineer")
        assert results == []

    @patch.object(_insights_mod, "DynamoDBClient")
    def test_scan_when_no_role_id(self, mock_db_cls):
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db
        mock_table = MagicMock()
        mock_db._get_table.return_value = mock_table
        mock_table.scan.return_value = {
            "Items": [
                {"sector": "role:pm", "insights": [{"type": "role_trend"}]},
            ]
        }

        results = get_insights()
        assert len(results) == 1
        mock_table.scan.assert_called_once()


# ---------------------------------------------------------------------------
# Property-Based Tests (hypothesis)
# ---------------------------------------------------------------------------

from hypothesis import given, settings
from hypothesis import strategies as st


# --- Strategies ---

# Valid trend directions from the design doc
_TREND_DIRECTIONS = ["surging", "growing", "stable", "declining"]

# Strategy for a MarketDataRecord with random but valid fields
_market_record_strategy = st.builds(
    lambda sector, role_title, demand_score, growth_rate, trend_direction: _make_record(
        sector=f"role:{sector}",
        role_title=role_title,
        demand_score=demand_score,
        growth_rate=growth_rate,
        trend_direction=trend_direction,
    ),
    sector=st.text(
        min_size=3, max_size=30,
        alphabet=st.characters(whitelist_categories=("Ll", "Nd"), whitelist_characters="_"),
    ),
    role_title=st.text(min_size=1, max_size=60).filter(lambda s: s.strip()),
    demand_score=st.integers(min_value=0, max_value=100),
    growth_rate=st.floats(min_value=-50.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    trend_direction=st.sampled_from(_TREND_DIRECTIONS),
)

# Strategy for a single skill breakdown entry
# Constrain skill names to alphanumeric + spaces (no control chars, no commas)
# to avoid ambiguity when skills are joined with ", " in milestone templates.
_skill_name_strategy = st.text(
    min_size=1, max_size=40,
    alphabet=st.characters(whitelist_categories=("L", "Nd"), whitelist_characters=" _-"),
).filter(lambda s: s.strip())

_skill_entry_strategy = st.fixed_dictionaries({
    "skill": _skill_name_strategy,
    "user_score": st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    "market_weight": st.floats(min_value=0.01, max_value=1.0, allow_nan=False, allow_infinity=False),
    "gap": st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
})

# Strategy for a list of unique skill breakdown entries
_skill_breakdown_strategy = st.lists(
    _skill_entry_strategy, min_size=1, max_size=5,
).filter(lambda lst: len({e["skill"] for e in lst}) == len(lst))

# Strategy for an AlignmentResult with random fields
_alignment_strategy = st.builds(
    lambda pct, breakdown, role_id, user_id: _make_alignment(
        alignment_pct=round(pct, 1),
        skill_breakdown=breakdown,
        top_gaps=[e for e in sorted(breakdown, key=lambda x: x["market_weight"] * (1 - x["user_score"]), reverse=True)][:3],
        top_strengths=[e for e in sorted(breakdown, key=lambda x: x["market_weight"] * x["user_score"], reverse=True)][:3],
        target_role_id=role_id,
        user_id=user_id,
    ),
    pct=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    breakdown=_skill_breakdown_strategy,
    role_id=st.text(
        min_size=3, max_size=30,
        alphabet=st.characters(whitelist_categories=("Ll", "Nd"), whitelist_characters="_"),
    ),
    user_id=st.text(
        min_size=3, max_size=30,
        alphabet=st.characters(whitelist_categories=("Ll", "Nd"), whitelist_characters="_-"),
    ),
)


# ---------------------------------------------------------------------------
# Property 10: Insight structure validity
# Feature: market-intelligence, Property 10: Insight structure validity
# Validates: Requirements 7.1
# ---------------------------------------------------------------------------


class TestInsightStructureValidity:
    """Property 10 — For any generated insight: all required fields present,
    type is one of 5 valid types, all template placeholders have matching
    data_payload keys."""

    @given(record=_market_record_strategy)
    @settings(max_examples=100)
    def test_role_trend_structure(self, record: MarketDataRecord) -> None:
        """**Validates: Requirements 7.1**

        Role trend insights have valid structure for any MarketDataRecord.
        """
        insight = generate_role_trend_insight(record)
        _assert_valid_insight(insight, "role_trend")
        assert isinstance(insight.role_id, str) and insight.role_id
        assert isinstance(insight.data_payload, dict)
        assert insight.shown is False

    @given(alignment=_alignment_strategy, role_title=st.text(min_size=1, max_size=60).filter(lambda s: s.strip()))
    @settings(max_examples=100)
    def test_alignment_structure(self, alignment: AlignmentResult, role_title: str) -> None:
        """**Validates: Requirements 7.1**

        Alignment insights have valid structure for any AlignmentResult.
        """
        insight = generate_alignment_insight(alignment, role_title)
        _assert_valid_insight(insight, "alignment")
        assert isinstance(insight.role_id, str) and insight.role_id
        assert isinstance(insight.data_payload, dict)
        assert insight.shown is False

    @given(
        skill_name=st.text(min_size=1, max_size=40).filter(lambda s: s.strip()),
        frequency=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        evidence_count=st.integers(min_value=0, max_value=50),
        role_id=st.text(min_size=3, max_size=30, alphabet=st.characters(whitelist_categories=("Ll", "Nd"), whitelist_characters="_")),
        role_title=st.text(min_size=1, max_size=60).filter(lambda s: s.strip()),
    )
    @settings(max_examples=100)
    def test_gap_opportunity_structure(
        self, skill_name: str, frequency: float, evidence_count: int,
        role_id: str, role_title: str,
    ) -> None:
        """**Validates: Requirements 7.1**

        Gap opportunity insights have valid structure for any inputs.
        """
        insight = generate_gap_opportunity_insight(
            skill_name=skill_name,
            frequency=frequency,
            evidence_count=evidence_count,
            role_id=role_id,
            role_title=role_title,
        )
        _assert_valid_insight(insight, "gap_opportunity")
        assert isinstance(insight.role_id, str) and insight.role_id
        assert isinstance(insight.data_payload, dict)
        assert insight.shown is False

    @given(
        record=_market_record_strategy,
        alignment_pct=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100)
    def test_emerging_role_structure(self, record: MarketDataRecord, alignment_pct: float) -> None:
        """**Validates: Requirements 7.1**

        Emerging role insights have valid structure for any inputs.
        """
        insight = generate_emerging_role_insight(record, alignment_pct)
        _assert_valid_insight(insight, "emerging_role")
        assert isinstance(insight.role_id, str) and insight.role_id
        assert isinstance(insight.data_payload, dict)
        assert insight.shown is False

    @given(
        prev_alignment=_alignment_strategy,
        curr_alignment=_alignment_strategy,
        role_title=st.text(min_size=1, max_size=60).filter(lambda s: s.strip()),
    )
    @settings(max_examples=100)
    def test_milestone_structure(
        self, prev_alignment: AlignmentResult, curr_alignment: AlignmentResult,
        role_title: str,
    ) -> None:
        """**Validates: Requirements 7.1**

        Milestone insights have valid structure for any two AlignmentResults.
        """
        # Ensure same user/role for milestone to be meaningful
        curr_alignment.target_role_id = prev_alignment.target_role_id
        curr_alignment.user_id = prev_alignment.user_id

        insight = generate_milestone_insight(prev_alignment, curr_alignment, role_title)
        _assert_valid_insight(insight, "milestone")
        assert isinstance(insight.role_id, str) and insight.role_id
        assert isinstance(insight.data_payload, dict)
        assert insight.shown is False


# ---------------------------------------------------------------------------
# Property 11: Milestone delta correctness
# Feature: market-intelligence, Property 11: Milestone insight delta correctness
# Validates: Requirements 7.5
# ---------------------------------------------------------------------------


class TestMilestoneDeltaCorrectness:
    """Property 11 — For any two AlignmentResults, milestone insight correctly
    reports previous_pct, current_pct, and skills_improved."""

    @given(
        shared_role_id=st.text(
            min_size=3, max_size=30,
            alphabet=st.characters(whitelist_categories=("Ll", "Nd"), whitelist_characters="_"),
        ),
        shared_user_id=st.text(
            min_size=3, max_size=30,
            alphabet=st.characters(whitelist_categories=("Ll", "Nd"), whitelist_characters="_-"),
        ),
        prev_pct=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        curr_pct=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        prev_breakdown=_skill_breakdown_strategy,
        curr_breakdown=_skill_breakdown_strategy,
        role_title=st.text(min_size=1, max_size=60).filter(lambda s: s.strip()),
    )
    @settings(max_examples=100)
    def test_milestone_delta_values(
        self,
        shared_role_id: str,
        shared_user_id: str,
        prev_pct: float,
        curr_pct: float,
        prev_breakdown: list[dict],
        curr_breakdown: list[dict],
        role_title: str,
    ) -> None:
        """**Validates: Requirements 7.5**

        Verifies previous_pct, current_pct, and skills_improved are correct.
        """
        previous = _make_alignment(
            alignment_pct=round(prev_pct, 1),
            skill_breakdown=prev_breakdown,
            target_role_id=shared_role_id,
            user_id=shared_user_id,
        )
        current = _make_alignment(
            alignment_pct=round(curr_pct, 1),
            skill_breakdown=curr_breakdown,
            target_role_id=shared_role_id,
            user_id=shared_user_id,
        )

        insight = generate_milestone_insight(previous, current, role_title)

        # Check 1: previous_pct matches
        assert insight.data_payload["previous_pct"] == round(prev_pct, 1)

        # Check 2: current_pct matches
        assert insight.data_payload["current_pct"] == round(curr_pct, 1)

        # Check 3: skills_improved is correct
        # Build expected set of improved skills (normalized)
        prev_scores: dict[str, float] = {
            e["skill"].strip(): e["user_score"] for e in prev_breakdown
        }
        expected_improved: set[str] = set()
        for entry in curr_breakdown:
            skill = entry["skill"].strip()
            curr_score = entry["user_score"]
            prev_score = prev_scores.get(skill, 0.0)
            if curr_score > prev_score:
                expected_improved.add(skill)

        # Parse the skills_improved string back to a set
        skills_improved_str = insight.data_payload["skills_improved"]
        if skills_improved_str == "none":
            actual_improved: set[str] = set()
        else:
            actual_improved = {s.strip() for s in skills_improved_str.split(",")}

        assert actual_improved == expected_improved, (
            f"Expected improved={expected_improved}, got={actual_improved}"
        )

        # Check 4: Skills where score stayed same or decreased are NOT in improved
        for entry in curr_breakdown:
            skill = entry["skill"].strip()
            curr_score = entry["user_score"]
            prev_score = prev_scores.get(skill, 0.0)
            if curr_score <= prev_score:
                assert skill not in actual_improved, (
                    f"Skill '{skill}' should not be in improved "
                    f"(prev={prev_score}, curr={curr_score})"
                )
