"""Unit tests for backend.engine.skill_gap module."""

import importlib
from datetime import datetime, timedelta, timezone

import pytest

from backend.engine.skill_gap import (
    EVIDENCE_THRESHOLD,
    RECENCY_HALF_LIFE_DAYS,
    _compute_skill_score,
    _recency_weight,
    analyze_skill_gaps,
)

_taxonomy = importlib.import_module("backend.lambda.market_intel.taxonomy")
_norm = _taxonomy.normalize_skill


NOW = datetime(2025, 6, 1, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# _recency_weight
# ---------------------------------------------------------------------------

class TestRecencyWeight:
    def test_same_day_evidence_is_near_one(self):
        weight = _recency_weight(NOW.isoformat(), NOW)
        assert weight == pytest.approx(1.0, abs=0.01)

    def test_90_day_old_evidence_is_half(self):
        old = (NOW - timedelta(days=90)).isoformat()
        weight = _recency_weight(old, NOW)
        assert weight == pytest.approx(0.5, abs=0.01)

    def test_180_day_old_evidence_is_quarter(self):
        old = (NOW - timedelta(days=180)).isoformat()
        weight = _recency_weight(old, NOW)
        assert weight == pytest.approx(0.25, abs=0.01)

    def test_unparseable_date_returns_zero(self):
        assert _recency_weight("not-a-date", NOW) == 0.0

    def test_none_date_returns_zero(self):
        assert _recency_weight(None, NOW) == 0.0


# ---------------------------------------------------------------------------
# _compute_skill_score
# ---------------------------------------------------------------------------

class TestComputeSkillScore:
    def test_no_evidence_returns_zero(self):
        assert _compute_skill_score([], NOW) == 0.0

    def test_three_recent_items_returns_one(self):
        records = [{"date": NOW.isoformat()} for _ in range(3)]
        score = _compute_skill_score(records, NOW)
        assert score == pytest.approx(1.0, abs=0.01)

    def test_one_recent_item_returns_one_third(self):
        records = [{"date": NOW.isoformat()}]
        score = _compute_skill_score(records, NOW)
        assert score == pytest.approx(1.0 / EVIDENCE_THRESHOLD, abs=0.01)

    def test_capped_at_one(self):
        records = [{"date": NOW.isoformat()} for _ in range(10)]
        score = _compute_skill_score(records, NOW)
        assert score == 1.0

    def test_old_evidence_scores_lower(self):
        old_date = (NOW - timedelta(days=180)).isoformat()
        records = [{"date": old_date} for _ in range(3)]
        score = _compute_skill_score(records, NOW)
        # Each record has weight ~0.25, so total ~0.75/3 = 0.25
        assert score < 0.5

    def test_uses_completedAt_fallback(self):
        records = [{"completedAt": NOW.isoformat()}]
        score = _compute_skill_score(records, NOW)
        assert score > 0.0


# ---------------------------------------------------------------------------
# analyze_skill_gaps
# ---------------------------------------------------------------------------

class TestAnalyzeSkillGaps:
    def test_no_evidence_all_zeros(self):
        report = analyze_skill_gaps(
            user_skills=["python", "sql"],
            evidence_by_skill={},
            target_requirements=[{"skill": "python"}, {"skill": "sql"}],
            market_demand={"python": 0.8, "sql": 0.6},
            reference_date=NOW,
        )
        assert report.skill_scores[_norm("python")] == 0.0
        assert report.skill_scores[_norm("sql")] == 0.0
        assert report.market_alignment_pct == 0.0

    def test_full_evidence_high_alignment(self):
        evidence = {
            "python": [{"date": NOW.isoformat()} for _ in range(3)],
            "sql": [{"date": NOW.isoformat()} for _ in range(3)],
        }
        report = analyze_skill_gaps(
            user_skills=["python", "sql"],
            evidence_by_skill=evidence,
            target_requirements=[{"skill": "python"}, {"skill": "sql"}],
            market_demand={"python": 0.8, "sql": 0.6},
            reference_date=NOW,
        )
        assert report.market_alignment_pct == pytest.approx(100.0, abs=0.5)

    def test_partial_evidence_partial_alignment(self):
        evidence = {
            "python": [{"date": NOW.isoformat()} for _ in range(3)],
        }
        report = analyze_skill_gaps(
            user_skills=["python", "sql"],
            evidence_by_skill=evidence,
            target_requirements=[{"skill": "python"}, {"skill": "sql"}],
            market_demand={"python": 0.5, "sql": 0.5},
            reference_date=NOW,
        )
        # python score ~1.0, sql score 0.0
        # alignment = (1.0*0.5 + 0.0*0.5) / (0.5+0.5) * 100 = 50%
        assert report.market_alignment_pct == pytest.approx(50.0, abs=1.0)

    def test_priority_skills_sorted_by_gap_times_demand(self):
        evidence = {
            "python": [{"date": NOW.isoformat()} for _ in range(3)],
        }
        report = analyze_skill_gaps(
            user_skills=["python", "sql", "aws"],
            evidence_by_skill=evidence,
            target_requirements=[
                {"skill": "python"},
                {"skill": "sql"},
                {"skill": "aws"},
            ],
            market_demand={"python": 0.3, "sql": 0.9, "aws": 0.5},
            reference_date=NOW,
        )
        # python: gap=0, sql: gap=1.0*0.9=0.9, aws: gap=1.0*0.5=0.5
        assert report.priority_skills[0] == _norm("sql")
        assert report.priority_skills[1] == _norm("aws")

    def test_evidence_density_counts(self):
        evidence = {
            "python": [{"date": NOW.isoformat()}, {"date": NOW.isoformat()}],
            "sql": [{"date": NOW.isoformat()}],
        }
        report = analyze_skill_gaps(
            user_skills=["python", "sql"],
            evidence_by_skill=evidence,
            target_requirements=[{"skill": "python"}, {"skill": "sql"}],
            market_demand={"python": 0.5, "sql": 0.5},
            reference_date=NOW,
        )
        assert report.evidence_density[_norm("python")] == 2
        assert report.evidence_density[_norm("sql")] == 1

    def test_empty_inputs(self):
        report = analyze_skill_gaps(
            user_skills=[],
            evidence_by_skill={},
            target_requirements=[],
            market_demand={},
            reference_date=NOW,
        )
        assert report.skill_scores == {}
        assert report.market_alignment_pct == 0.0
        assert report.priority_skills == []

    def test_zero_demand_avoids_division_by_zero(self):
        report = analyze_skill_gaps(
            user_skills=["python"],
            evidence_by_skill={"python": [{"date": NOW.isoformat()}]},
            target_requirements=[{"skill": "python"}],
            market_demand={"python": 0.0},
            reference_date=NOW,
        )
        assert report.market_alignment_pct == 0.0

    def test_skills_union_from_all_sources(self):
        """Skills appear from user_skills, target_requirements, and market_demand."""
        report = analyze_skill_gaps(
            user_skills=["skill_a"],
            evidence_by_skill={},
            target_requirements=[{"skill": "skill_b"}],
            market_demand={"skill_c": 0.5},
            reference_date=NOW,
        )
        assert "skill_a" in report.skill_scores
        assert "skill_b" in report.skill_scores
        assert "skill_c" in report.skill_scores
