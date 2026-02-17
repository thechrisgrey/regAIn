"""Unit tests for backend.engine.generator module."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from backend.engine.generator import (
    _build_evidence_by_skill,
    _compute_streak_info,
    _exclude_recent_duplicates,
    _map_phase,
    complete_mission,
    generate_daily_mission,
)
from backend.engine.models import GenerationResult, CompletionResult, MissionCandidate


NOW = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
NOW_ISO = NOW.isoformat()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_profile(**overrides) -> dict:
    base = {
        "userId": "u1",
        "name": "Test User",
        "target_role": "Data Analyst",
        "skills": ["python", "sql", "communication"],
        "experience": [{"company": "Acme Corp", "role": "Analyst"}],
    }
    base.update(overrides)
    return base


def _make_campaign(**overrides) -> dict:
    base = {
        "campaignId": "c1",
        "userId": "u1",
        "phase": "foundation",
        "target_role": "Data Analyst",
    }
    base.update(overrides)
    return base


def _make_market_data(**overrides) -> dict:
    base = {
        "role": "Data Analyst",
        "sector": "Technology",
        "top_skills": ["python", "sql", "tableau"],
        "required_skills": [
            {"skill": "python", "demand": 0.9},
            {"skill": "sql", "demand": 0.8},
            {"skill": "tableau", "demand": 0.7},
        ],
    }
    base.update(overrides)
    return base


def _make_mission_history_item(
    mission_id: str = "m1",
    category: str = "reflection",
    status: str = "completed",
    template_id: str = "reflection_d1_foundation",
    skill_tags: list[str] | None = None,
    completed_at: str = "",
    **kwargs,
) -> dict:
    item = {
        "missionId": mission_id,
        "userId": "u1",
        "category": category,
        "status": status,
        "templateId": template_id,
        "skillTags": skill_tags or ["python"],
        "difficulty": 1,
    }
    if completed_at:
        item["completedAt"] = completed_at
    item.update(kwargs)
    return item


def _make_mock_db(
    profile=None,
    campaign=None,
    mission_history=None,
    evidence=None,
    market_data=None,
) -> MagicMock:
    """Create a mock DynamoDBClient with configurable return values."""
    db = MagicMock()

    def get_item_side_effect(table_name, key):
        if table_name == "user_profiles":
            return profile
        if table_name == "campaigns":
            return campaign
        if table_name == "mission_history":
            return (mission_history or [{}])[0] if mission_history else None
        return None

    def query_side_effect(table_name, key_condition, **kwargs):
        if table_name == "mission_history":
            return mission_history or []
        if table_name == "evidence_vault":
            return evidence or []
        if table_name == "market_data":
            return market_data if market_data else []
        return []

    db.get_item.side_effect = get_item_side_effect
    db.query.side_effect = query_side_effect
    db.put_item.return_value = {}
    db.update_item.return_value = {}
    return db


# ---------------------------------------------------------------------------
# _map_phase
# ---------------------------------------------------------------------------


class TestMapPhase:
    def test_foundation(self):
        assert _map_phase("foundation") == "foundation"

    def test_momentum_maps_to_expansion(self):
        assert _map_phase("momentum") == "expansion"

    def test_acceleration_maps_to_expansion(self):
        assert _map_phase("acceleration") == "expansion"

    def test_expansion(self):
        assert _map_phase("expansion") == "expansion"

    def test_transition_maps_to_launch(self):
        assert _map_phase("transition") == "launch"

    def test_launch(self):
        assert _map_phase("launch") == "launch"

    def test_unknown_defaults_to_foundation(self):
        assert _map_phase("unknown") == "foundation"

    def test_case_insensitive(self):
        assert _map_phase("Foundation") == "foundation"
        assert _map_phase("MOMENTUM") == "expansion"


# ---------------------------------------------------------------------------
# _build_evidence_by_skill
# ---------------------------------------------------------------------------


class TestBuildEvidenceBySkill:
    def test_groups_by_skill_tags(self):
        records = [
            {"skillTags": ["python", "sql"], "date": NOW_ISO},
            {"skillTags": ["python"], "date": NOW_ISO},
        ]
        result = _build_evidence_by_skill(records)
        assert len(result["python"]) == 2
        assert len(result["sql"]) == 1

    def test_empty_records(self):
        assert _build_evidence_by_skill([]) == {}

    def test_handles_skill_tags_key_variant(self):
        records = [{"skill_tags": ["java"], "date": NOW_ISO}]
        result = _build_evidence_by_skill(records)
        assert len(result["java"]) == 1

    def test_handles_missing_tags(self):
        records = [{"date": NOW_ISO}]
        result = _build_evidence_by_skill(records)
        assert result == {}


# ---------------------------------------------------------------------------
# _compute_streak_info
# ---------------------------------------------------------------------------


class TestComputeStreakInfo:
    def test_empty_history(self):
        result = _compute_streak_info([])
        assert result["type"] == ""
        assert result["count"] == 0

    def test_completion_streak(self):
        history = [
            _make_mission_history_item(status="completed", completed_at="2025-06-13T12:00:00+00:00"),
            _make_mission_history_item(status="completed", completed_at="2025-06-14T12:00:00+00:00"),
            _make_mission_history_item(status="completed", completed_at="2025-06-15T12:00:00+00:00"),
        ]
        result = _compute_streak_info(history)
        assert result["type"] == "completion"
        assert result["count"] == 3

    def test_broken_streak(self):
        history = [
            _make_mission_history_item(status="completed", completed_at="2025-06-13T12:00:00+00:00"),
            _make_mission_history_item(status="skipped", completed_at="2025-06-14T12:00:00+00:00", updatedAt="2025-06-14T12:00:00+00:00"),
            _make_mission_history_item(status="skipped", completed_at="", updatedAt="2025-06-15T12:00:00+00:00"),
        ]
        result = _compute_streak_info(history)
        assert result["type"] == "broken"
        assert result["count"] == 2

    def test_recent_categories(self):
        history = [
            _make_mission_history_item(category="reflection", status="completed", completed_at="2025-06-14T12:00:00+00:00"),
            _make_mission_history_item(category="portfolio", status="completed", completed_at="2025-06-15T12:00:00+00:00"),
        ]
        result = _compute_streak_info(history)
        assert "portfolio" in result["recent_categories"]
        assert "reflection" in result["recent_categories"]


# ---------------------------------------------------------------------------
# _exclude_recent_duplicates
# ---------------------------------------------------------------------------


class TestExcludeRecentDuplicates:
    def test_excludes_matching_template_and_skill(self):
        recent = datetime.now(timezone.utc).isoformat()
        candidates = [
            MissionCandidate(
                template_id="t1", category="reflection", title="T", description="D",
                rationale="R", skill_tags=["python"], difficulty=1,
                estimated_minutes=20, expected_evidence_type="reflection",
                phase="foundation",
            ),
            MissionCandidate(
                template_id="t2", category="skill_building", title="T2", description="D2",
                rationale="R2", skill_tags=["sql"], difficulty=1,
                estimated_minutes=20, expected_evidence_type="artifact",
                phase="foundation",
            ),
        ]
        history = [
            _make_mission_history_item(
                template_id="t1", skill_tags=["python"],
                status="completed", completed_at=recent,
            ),
        ]
        result = _exclude_recent_duplicates(candidates, history)
        assert len(result) == 1
        assert result[0].template_id == "t2"

    def test_keeps_old_duplicates(self):
        old_date = (datetime.now(timezone.utc) - timedelta(days=15)).isoformat()
        candidates = [
            MissionCandidate(
                template_id="t1", category="reflection", title="T", description="D",
                rationale="R", skill_tags=["python"], difficulty=1,
                estimated_minutes=20, expected_evidence_type="reflection",
                phase="foundation",
            ),
        ]
        history = [
            _make_mission_history_item(
                template_id="t1", skill_tags=["python"],
                status="completed", completed_at=old_date,
            ),
        ]
        result = _exclude_recent_duplicates(candidates, history)
        assert len(result) == 1

    def test_different_primary_skill_not_excluded(self):
        recent = datetime.now(timezone.utc).isoformat()
        candidates = [
            MissionCandidate(
                template_id="t1", category="reflection", title="T", description="D",
                rationale="R", skill_tags=["sql"], difficulty=1,
                estimated_minutes=20, expected_evidence_type="reflection",
                phase="foundation",
            ),
        ]
        history = [
            _make_mission_history_item(
                template_id="t1", skill_tags=["python"],
                status="completed", completed_at=recent,
            ),
        ]
        result = _exclude_recent_duplicates(candidates, history)
        assert len(result) == 1

    def test_skipped_missions_not_counted(self):
        recent = datetime.now(timezone.utc).isoformat()
        candidates = [
            MissionCandidate(
                template_id="t1", category="reflection", title="T", description="D",
                rationale="R", skill_tags=["python"], difficulty=1,
                estimated_minutes=20, expected_evidence_type="reflection",
                phase="foundation",
            ),
        ]
        history = [
            _make_mission_history_item(
                template_id="t1", skill_tags=["python"],
                status="skipped", completed_at=recent,
            ),
        ]
        result = _exclude_recent_duplicates(candidates, history)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# generate_daily_mission
# ---------------------------------------------------------------------------


class TestGenerateDailyMission:
    def test_returns_generation_result(self):
        db = _make_mock_db(
            profile=_make_profile(),
            campaign=_make_campaign(),
            mission_history=[],
            evidence=[],
            market_data=[_make_market_data()],
        )
        result = generate_daily_mission("u1", "c1", db=db)
        assert isinstance(result, GenerationResult)
        assert result.primary is not None
        assert result.primary.priority_score > 0

    def test_returns_primary_and_alternates(self):
        db = _make_mock_db(
            profile=_make_profile(),
            campaign=_make_campaign(),
            mission_history=[],
            evidence=[],
            market_data=[_make_market_data()],
        )
        result = generate_daily_mission("u1", "c1", db=db)
        assert isinstance(result, GenerationResult)
        assert len(result.alternates) == 2

    def test_primary_has_highest_score(self):
        db = _make_mock_db(
            profile=_make_profile(),
            campaign=_make_campaign(),
            mission_history=[],
            evidence=[],
            market_data=[_make_market_data()],
        )
        result = generate_daily_mission("u1", "c1", db=db)
        assert isinstance(result, GenerationResult)
        for alt in result.alternates:
            assert result.primary.priority_score >= alt.priority_score

    def test_missing_profile_returns_error(self):
        db = _make_mock_db(profile=None, campaign=_make_campaign())
        result = generate_daily_mission("u1", "c1", db=db)
        assert isinstance(result, dict)
        assert "error" in result

    def test_missing_campaign_returns_error(self):
        db = _make_mock_db(profile=_make_profile(), campaign=None)
        result = generate_daily_mission("u1", "c1", db=db)
        assert isinstance(result, dict)
        assert "error" in result

    def test_phase_mapping_momentum(self):
        db = _make_mock_db(
            profile=_make_profile(),
            campaign=_make_campaign(phase="momentum"),
            mission_history=[],
            evidence=[],
            market_data=[_make_market_data()],
        )
        result = generate_daily_mission("u1", "c1", db=db)
        assert isinstance(result, GenerationResult)
        # Momentum maps to expansion — templates should be expansion-phase
        assert result.primary.phase == "expansion"

    def test_no_market_data_uses_fallback(self):
        db = _make_mock_db(
            profile=_make_profile(),
            campaign=_make_campaign(),
            mission_history=[],
            evidence=[],
            market_data=[],
        )
        result = generate_daily_mission("u1", "c1", db=db)
        assert isinstance(result, GenerationResult)

    def test_includes_skill_gap_report(self):
        db = _make_mock_db(
            profile=_make_profile(),
            campaign=_make_campaign(),
            mission_history=[],
            evidence=[],
            market_data=[_make_market_data()],
        )
        result = generate_daily_mission("u1", "c1", db=db)
        assert isinstance(result, GenerationResult)
        assert result.skill_gap_report is not None
        assert isinstance(result.skill_gap_report.market_alignment_pct, float)


# ---------------------------------------------------------------------------
# complete_mission
# ---------------------------------------------------------------------------


class TestCompleteMission:
    def test_returns_completion_result(self):
        mission = _make_mission_history_item(
            mission_id="m1",
            status="in_progress",
            category="reflection",
            campaignId="c1",
        )
        db = _make_mock_db(
            profile=_make_profile(),
            campaign=_make_campaign(),
            mission_history=[mission],
            evidence=[],
            market_data=[_make_market_data()],
        )
        # Override get_item to return the mission for mission_history lookup
        original_get = db.get_item.side_effect

        def get_item_with_mission(table_name, key):
            if table_name == "mission_history":
                return mission
            return original_get(table_name, key)

        db.get_item.side_effect = get_item_with_mission

        result = complete_mission("u1", "m1", ["ev1"], db=db)
        assert isinstance(result, CompletionResult)
        assert result.mission_id == "m1"

    def test_missing_mission_returns_error(self):
        db = _make_mock_db(profile=_make_profile(), campaign=_make_campaign())
        # get_item returns None for mission_history by default when no history
        db.get_item.side_effect = lambda table, key: None

        result = complete_mission("u1", "m_missing", ["ev1"], db=db)
        assert isinstance(result, dict)
        assert "error" in result

    def test_saves_updated_mission(self):
        mission = _make_mission_history_item(
            mission_id="m1",
            status="in_progress",
            category="reflection",
            campaignId="c1",
        )
        db = _make_mock_db(
            profile=_make_profile(),
            campaign=_make_campaign(),
            mission_history=[mission],
            evidence=[],
            market_data=[_make_market_data()],
        )
        db.get_item.side_effect = lambda table, key: (
            mission if table == "mission_history"
            else _make_campaign() if table == "campaigns"
            else _make_profile() if table == "user_profiles"
            else None
        )

        complete_mission("u1", "m1", ["ev1"], db=db)
        db.put_item.assert_called_once()
        saved = db.put_item.call_args[0][1]
        assert saved["status"] == "completed"
        assert saved["evidenceIds"] == ["ev1"]

    def test_updates_campaign_difficulty_state(self):
        mission = _make_mission_history_item(
            mission_id="m1",
            status="in_progress",
            category="reflection",
            campaignId="c1",
        )
        db = _make_mock_db(
            profile=_make_profile(),
            campaign=_make_campaign(),
            mission_history=[mission],
            evidence=[],
            market_data=[_make_market_data()],
        )
        db.get_item.side_effect = lambda table, key: (
            mission if table == "mission_history"
            else _make_campaign() if table == "campaigns"
            else _make_profile() if table == "user_profiles"
            else None
        )

        complete_mission("u1", "m1", ["ev1"], db=db)
        db.update_item.assert_called_once()
        update_args = db.update_item.call_args
        assert update_args[0][0] == "campaigns"
        updates = update_args[0][2]
        assert "difficultyState" in updates

    def test_gate_result_included(self):
        mission = _make_mission_history_item(
            mission_id="m1",
            status="in_progress",
            category="reflection",
            campaignId="c1",
        )
        db = _make_mock_db(
            profile=_make_profile(),
            campaign=_make_campaign(),
            mission_history=[mission],
            evidence=[],
            market_data=[_make_market_data()],
        )
        db.get_item.side_effect = lambda table, key: (
            mission if table == "mission_history"
            else _make_campaign() if table == "campaigns"
            else _make_profile() if table == "user_profiles"
            else None
        )

        result = complete_mission("u1", "m1", ["ev1"], db=db)
        assert isinstance(result, CompletionResult)
        assert result.gate_result is not None
        assert result.gate_result.current_phase == "foundation"


# ---------------------------------------------------------------------------
# Relaxed difficulty fallback
# ---------------------------------------------------------------------------


class TestRelaxedDifficultyFallback:
    """Test that the generator relaxes the difficulty filter when < 3 candidates
    survive the normal ±1 filter, falling back to ±2."""

    def test_relaxed_filter_used_when_few_candidates_survive(self):
        """When normal ±1 filtering leaves < 3 candidates, the generator
        relaxes to ±2 and still produces a valid GenerationResult."""
        # User at difficulty level 1 for all categories.
        # Create a campaign with foundation phase so templates are generated
        # for foundation. Then we mock the template instantiation to return
        # candidates that are mostly at difficulty 3+ (outside ±1 of level 1,
        # but within ±2).
        from unittest.mock import patch

        from backend.engine.models import DifficultyState, SkillGapReport

        db = _make_mock_db(
            profile=_make_profile(),
            campaign=_make_campaign(),
            mission_history=[],
            evidence=[],
            market_data=[_make_market_data()],
        )

        # Candidates: 1 at difficulty 1 (passes ±1), 4 at difficulty 3 (fail ±1, pass ±2)
        fake_candidates = [
            MissionCandidate(
                template_id=f"t{i}",
                category="skill_building",
                title=f"Mission {i}",
                description="Desc",
                rationale="Rationale",
                skill_tags=["python"],
                difficulty=3,
                estimated_minutes=20,
                expected_evidence_type="artifact",
                phase="foundation",
            )
            for i in range(4)
        ] + [
            MissionCandidate(
                template_id="t_easy",
                category="reflection",
                title="Easy Mission",
                description="Desc",
                rationale="Rationale",
                skill_tags=["sql"],
                difficulty=1,
                estimated_minutes=15,
                expected_evidence_type="reflection",
                phase="foundation",
            ),
        ]

        with patch(
            "backend.engine.generator.instantiate_all_templates",
            return_value=fake_candidates,
        ):
            result = generate_daily_mission("u1", "c1", db=db)

        assert isinstance(result, GenerationResult)
        # Should have primary + 2 alternates even though normal filter
        # would only keep 1 candidate (difficulty 1).
        assert result.primary is not None
        assert len(result.alternates) == 2
