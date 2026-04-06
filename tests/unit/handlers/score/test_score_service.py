"""Unit tests for the Impact Scorecard computation service."""

import math
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from backend.handlers.score.service import (
    ScoreService,
    _cosine_similarity,
    _linear_regression_slope,
    _recency_weight,
    _sigmoid,
)


# ---------------------------------------------------------------------------
# Helper math function tests
# ---------------------------------------------------------------------------


class TestSigmoid:
    def test_zero_input(self):
        assert _sigmoid(0) == 0.5

    def test_positive_large(self):
        assert _sigmoid(100) > 0.99

    def test_negative_large(self):
        assert _sigmoid(-100) < 0.01

    def test_moderate_positive(self):
        result = _sigmoid(2.0)
        assert 0.8 < result < 0.95


class TestRecencyWeight:
    def test_same_day(self):
        now = datetime(2026, 4, 5, tzinfo=timezone.utc)
        w = _recency_weight("2026-04-05T00:00:00+00:00", now)
        assert w > 0.9

    def test_30_days_ago(self):
        now = datetime(2026, 4, 5, tzinfo=timezone.utc)
        w = _recency_weight("2026-03-06T00:00:00+00:00", now)
        assert 0.45 < w < 0.55  # half-life = 30 days

    def test_60_days_ago(self):
        now = datetime(2026, 4, 5, tzinfo=timezone.utc)
        w = _recency_weight("2026-02-04T00:00:00+00:00", now)
        assert 0.2 < w < 0.3  # ~0.25

    def test_invalid_timestamp(self):
        now = datetime(2026, 4, 5, tzinfo=timezone.utc)
        assert _recency_weight("not-a-date", now) == 0.5


class TestCosineSimilarity:
    def test_identical_vectors(self):
        v = {"a": 1.0, "b": 2.0}
        assert abs(_cosine_similarity(v, v) - 1.0) < 0.001

    def test_orthogonal_vectors(self):
        a = {"x": 1.0}
        b = {"y": 1.0}
        assert _cosine_similarity(a, b) == 0.0

    def test_partial_overlap(self):
        a = {"x": 1.0, "y": 1.0}
        b = {"x": 1.0, "z": 1.0}
        result = _cosine_similarity(a, b)
        assert 0.4 < result < 0.6  # should be 0.5

    def test_empty_vectors(self):
        assert _cosine_similarity({}, {}) == 0.0


class TestLinearRegressionSlope:
    def test_perfect_upward(self):
        points = [(0, 1), (1, 2), (2, 3)]
        assert abs(_linear_regression_slope(points) - 1.0) < 0.001

    def test_flat_line(self):
        points = [(0, 3), (1, 3), (2, 3)]
        assert abs(_linear_regression_slope(points)) < 0.001

    def test_single_point(self):
        assert _linear_regression_slope([(1, 2)]) == 0.0

    def test_empty(self):
        assert _linear_regression_slope([]) == 0.0


# ---------------------------------------------------------------------------
# Score dimension tests with mock DB
# ---------------------------------------------------------------------------


def _make_mission(
    mission_id: str = "m-1",
    status: str = "completed",
    category: str = "skill_building",
    difficulty: int = 2,
    completed_at: str = "2026-04-01T10:00:00+00:00",
) -> dict:
    return {
        "userId": "user-1",
        "missionId": mission_id,
        "status": status,
        "category": category,
        "difficulty": difficulty,
        "completedAt": completed_at,
    }


def _make_evidence(
    evidence_id: str = "e-1",
    mission_id: str = "m-1",
    skill_tag: str = "Python",
    reflection: str = "I learned about decorators and context managers in Python.",
    created_at: str = "2026-04-01T10:00:00+00:00",
    artifact_url: str | None = None,
    word_count: int | None = None,
) -> dict:
    item: dict = {
        "userId": "user-1",
        "evidenceId": evidence_id,
        "missionId": mission_id,
        "skillTag": skill_tag,
        "reflection": reflection,
        "createdAt": created_at,
    }
    if artifact_url:
        item["artifactUrl"] = artifact_url
    if word_count is not None:
        item["wordCount"] = word_count
    return item


class TestMissionVelocity:
    def test_no_completed_missions(self):
        service = ScoreService(db_client=MagicMock())
        now = datetime(2026, 4, 5, tzinfo=timezone.utc)
        score, detail = service._compute_mission_velocity([], now)
        assert score == 0.0
        assert detail["totalCompleted"] == 0

    def test_active_week(self):
        now = datetime(2026, 4, 5, tzinfo=timezone.utc)
        missions = [
            _make_mission(f"m-{i}", completed_at=(now - timedelta(days=i)).isoformat())
            for i in range(5)
        ]
        service = ScoreService(db_client=MagicMock())
        score, detail = service._compute_mission_velocity(missions, now)
        assert score > 30  # 5 missions in 7 days is decent
        assert detail["last7d"] == 5

    def test_category_balance_matters(self):
        now = datetime(2026, 4, 5, tzinfo=timezone.utc)
        # All same category
        unbalanced = [
            _make_mission(f"m-{i}", category="reflection",
                         completed_at=(now - timedelta(days=i)).isoformat())
            for i in range(5)
        ]
        # Spread across categories
        categories = ["reflection", "skill_building", "portfolio", "networking", "market_research"]
        balanced = [
            _make_mission(f"m-{i}", category=categories[i],
                         completed_at=(now - timedelta(days=i)).isoformat())
            for i in range(5)
        ]
        service = ScoreService(db_client=MagicMock())
        s_unbal, _ = service._compute_mission_velocity(unbalanced, now)
        s_bal, _ = service._compute_mission_velocity(balanced, now)
        assert s_bal > s_unbal


class TestEvidenceDensity:
    def test_no_evidence(self):
        service = ScoreService(db_client=MagicMock())
        now = datetime(2026, 4, 5, tzinfo=timezone.utc)
        score, detail = service._compute_evidence_density(
            [_make_mission()], [], now
        )
        assert score == 0.0

    def test_full_coverage(self):
        now = datetime(2026, 4, 5, tzinfo=timezone.utc)
        missions = [_make_mission("m-1"), _make_mission("m-2")]
        evidence = [
            _make_evidence("e-1", "m-1", "Python", word_count=200),
            _make_evidence("e-2", "m-2", "Leadership", word_count=180),
        ]
        service = ScoreService(db_client=MagicMock())
        score, detail = service._compute_evidence_density(missions, evidence, now)
        assert score > 40  # good coverage + richness
        assert detail["ecr"] == 1.0  # 100% coverage
        assert detail["uniqueSkills"] == 2

    def test_artifact_bonus(self):
        now = datetime(2026, 4, 5, tzinfo=timezone.utc)
        missions = [_make_mission()]
        without = [_make_evidence(word_count=150)]
        with_art = [_make_evidence(word_count=150, artifact_url="https://example.com/doc.pdf")]
        service = ScoreService(db_client=MagicMock())
        s_without, _ = service._compute_evidence_density(missions, without, now)
        s_with, _ = service._compute_evidence_density(missions, with_art, now)
        assert s_with > s_without


class TestMarketAlignment:
    def test_no_market_data(self):
        service = ScoreService(db_client=MagicMock())
        now = datetime(2026, 4, 5, tzinfo=timezone.utc)
        score, detail = service._compute_market_alignment(
            [_make_evidence()], {}, "PM", now
        )
        assert score == 0.0
        assert not detail["hasMarketData"]

    def test_perfect_alignment(self):
        now = datetime(2026, 4, 5, tzinfo=timezone.utc)
        market = {
            "topSkills": [
                {"skill": "python", "frequency": 80},
                {"skill": "leadership", "frequency": 60},
            ],
        }
        evidence = [
            _make_evidence("e-1", skill_tag="python"),
            _make_evidence("e-2", skill_tag="leadership"),
        ]
        service = ScoreService(db_client=MagicMock())
        score, detail = service._compute_market_alignment(evidence, market, "PM", now)
        assert score > 50
        assert detail["matchedSkills"] == 2

    def test_hot_skills_gap_identifies_missing(self):
        now = datetime(2026, 4, 5, tzinfo=timezone.utc)
        market = {
            "topSkills": [
                {"skill": "python", "frequency": 80},
                {"skill": "leadership", "frequency": 60},
                {"skill": "figma", "frequency": 90},
            ],
        }
        evidence = [_make_evidence("e-1", skill_tag="python")]
        service = ScoreService(db_client=MagicMock())
        _, detail = service._compute_market_alignment(evidence, market, "PM", now)
        gap_skills = [g["skill"] for g in detail["hotSkillsGap"]]
        assert "figma" in gap_skills
        assert "leadership" in gap_skills


class TestPhaseProgression:
    def test_foundation_phase(self):
        service = ScoreService(db_client=MagicMock())
        campaign = {"phase": "foundation", "startDate": "2026-03-01"}
        score, detail = service._compute_phase_progression(campaign, [])
        assert score == 25.0  # foundation = index 1 of 4

    def test_launch_phase(self):
        service = ScoreService(db_client=MagicMock())
        campaign = {"phase": "launch", "startDate": "2026-03-01"}
        missions = [_make_mission(f"m-{i}") for i in range(25)]
        score, detail = service._compute_phase_progression(campaign, missions)
        assert score == 75.0
        assert detail["gatesMet"]["foundation_to_expansion"]["met"]
        assert detail["gatesMet"]["expansion_to_launch"]["met"]

    def test_no_campaign(self):
        service = ScoreService(db_client=MagicMock())
        score, _ = service._compute_phase_progression(None, [])
        assert score == 0.0


class TestAdaptiveDifficulty:
    def test_no_missions(self):
        service = ScoreService(db_client=MagicMock())
        now = datetime(2026, 4, 5, tzinfo=timezone.utc)
        score, _ = service._compute_adaptive_difficulty([], now)
        assert score == 0.0

    def test_increasing_difficulty(self):
        now = datetime(2026, 4, 5, tzinfo=timezone.utc)
        missions = [
            _make_mission(f"m-{i}", difficulty=min(5, i + 1),
                         completed_at=(now - timedelta(days=10 - i)).isoformat())
            for i in range(5)
        ]
        service = ScoreService(db_client=MagicMock())
        score, detail = service._compute_adaptive_difficulty(missions, now)
        assert score > 20  # positive slope + high ceiling
        assert detail["difficultyCeilings"]["skill_building"] == 5


class TestComputeScorecard:
    def test_full_scorecard(self):
        """Verify the full scorecard returns all expected fields."""
        db = MagicMock()
        db.get_item.return_value = {"userId": "u-1", "targetRole": "PM"}
        db.query.return_value = [
            {"userId": "u-1", "campaignId": "c-1", "status": "active",
             "phase": "expansion", "targetRole": "PM", "startDate": "2026-03-01"},
        ]
        db.query_all.side_effect = [
            # missions
            [_make_mission(f"m-{i}", completed_at=f"2026-04-0{i+1}T10:00:00+00:00")
             for i in range(5)],
            # evidence
            [_make_evidence(f"e-{i}", f"m-{i}", skill_tag="Python", word_count=120)
             for i in range(5)],
        ]

        service = ScoreService(db_client=db)
        result = service.compute_scorecard("u-1")

        assert "cri" in result
        assert 0 <= result["cri"] <= 100
        assert "missionVelocityScore" in result
        assert "evidenceDensityScore" in result
        assert "marketAlignmentScore" in result
        assert "phaseProgressionScore" in result
        assert "adaptiveDifficultyScore" in result
        assert result["missionsCompleted"] == 5
        assert result["evidenceCount"] == 5
        assert "dimensionDetail" in result
