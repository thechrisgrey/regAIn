"""Mission generation orchestrator.

Wires together the full pipeline: data retrieval → skill gap analysis →
difficulty computation → template instantiation → difficulty filtering →
duplicate exclusion → scoring → selection. Also handles mission completion
with state transitions, difficulty updates, and phase gate evaluation.
"""

from __future__ import annotations

import importlib
import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime, timedelta, timezone
from typing import Any

from boto3.dynamodb.conditions import Key

from backend.engine.difficulty import (
    compute_difficulty_state,
    filter_by_difficulty,
    update_difficulty,
)
from backend.engine.lifecycle import transition_mission
from backend.engine.models import (
    CompletionResult,
    DifficultyState,
    GenerationResult,
    MissionCandidate,
    SkillGapReport,
)
from backend.engine.phase_gates import evaluate_gate
from backend.engine.scoring import score_and_rank
from backend.engine.skill_gap import analyze_skill_gaps
from backend.engine.templates import instantiate_all_templates

# 'lambda' is a Python keyword, so we use importlib to load the module.
_dynamodb_mod = importlib.import_module("backend.handlers.shared.dynamodb")
DynamoDBClient = _dynamodb_mod.DynamoDBClient

logger = logging.getLogger(__name__)

# Campaign phase names used in external data vs engine-internal names.
_PHASE_MAP: dict[str, str] = {
    "foundation": "foundation",
    "momentum": "expansion",
    "acceleration": "expansion",
    "expansion": "expansion",
    "transition": "launch",
    "launch": "launch",
}

# Window for excluding recently completed duplicate missions.
_DUPLICATE_WINDOW_DAYS = 14

# Relaxed difficulty tolerance when insufficient candidates survive filtering.
_RELAXED_DIFFICULTY_TOLERANCE = 2


def _map_phase(raw_phase: str) -> str:
    """Map external campaign phase names to engine-internal names.

    Args:
        raw_phase: Phase string from campaign data.

    Returns:
        One of "foundation", "expansion", or "launch".
    """
    return _PHASE_MAP.get(raw_phase.lower(), "foundation")


def _build_evidence_by_skill(
    evidence_records: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Group evidence records by their skill tags.

    Args:
        evidence_records: Raw evidence items from DynamoDB.

    Returns:
        Dict mapping skill name to list of evidence records for that skill.
    """
    by_skill: dict[str, list[dict[str, Any]]] = {}
    for record in evidence_records:
        tags = (
            record.get("skillTags")
            or record.get("skill_tags")
            or ([record["skillTag"]] if record.get("skillTag") else [])
        )
        for tag in tags:
            by_skill.setdefault(tag, []).append(record)
    return by_skill


def _compute_streak_info(
    mission_history: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compute streak information from mission history.

    Looks at the tail of the history (sorted by timestamp) to determine
    whether the user is on a completion streak or a broken streak, and
    which categories were recently completed.

    Args:
        mission_history: List of mission dicts with status and timestamps.

    Returns:
        Dict with keys 'type' ("completion" or "broken"), 'count' (int),
        and 'recent_categories' (list[str]).
    """
    if not mission_history:
        return {"type": "", "count": 0, "recent_categories": []}

    def _sort_key(m: dict[str, Any]) -> str:
        return m.get("completedAt") or m.get("updatedAt") or ""

    sorted_history = sorted(mission_history, key=_sort_key)

    # Walk backwards to find the current streak.
    streak_type = ""
    streak_count = 0
    for mission in reversed(sorted_history):
        status = mission.get("status", "")
        if status == "completed":
            if streak_type == "" or streak_type == "completion":
                streak_type = "completion"
                streak_count += 1
            else:
                break
        elif status == "skipped":
            if streak_type == "" or streak_type == "broken":
                streak_type = "broken"
                streak_count += 1
            else:
                break
        else:
            break

    # Recent categories from last 5 completions.
    recent_categories: list[str] = []
    for mission in reversed(sorted_history):
        if mission.get("status") == "completed" and mission.get("category"):
            recent_categories.append(mission["category"])
            if len(recent_categories) >= 5:
                break

    return {
        "type": streak_type,
        "count": streak_count,
        "recent_categories": recent_categories,
    }


def _exclude_recent_duplicates(
    candidates: list[MissionCandidate],
    mission_history: list[dict[str, Any]],
    window_days: int = _DUPLICATE_WINDOW_DAYS,
) -> list[MissionCandidate]:
    """Exclude candidates that duplicate a recently completed mission.

    A duplicate is defined as matching both template_id AND primary skill tag
    (first element of skill_tags) with a mission completed within the window.

    Args:
        candidates: Mission candidates to filter.
        mission_history: Past mission dicts with status, completedAt,
            templateId, and skillTags.
        window_days: Number of days to look back.

    Returns:
        Filtered list of candidates with duplicates removed.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)

    recent_keys: set[tuple[str, str]] = set()
    for mission in mission_history:
        if mission.get("status") != "completed":
            continue
        completed_at = mission.get("completedAt", "")
        if not completed_at:
            continue
        try:
            completed_dt = datetime.fromisoformat(completed_at)
            if completed_dt.tzinfo is None:
                completed_dt = completed_dt.replace(tzinfo=timezone.utc)
            if completed_dt < cutoff:
                continue
        except (ValueError, TypeError):
            continue

        template_id = mission.get("templateId") or mission.get("template_id", "")
        skill_tags = mission.get("skillTags") or mission.get("skill_tags") or []
        primary_tag = skill_tags[0] if skill_tags else ""
        if template_id:
            recent_keys.add((template_id, primary_tag))

    result: list[MissionCandidate] = []
    for candidate in candidates:
        primary_tag = candidate.skill_tags[0] if candidate.skill_tags else ""
        key = (candidate.template_id, primary_tag)
        if key not in recent_keys:
            result.append(candidate)

    return result


def _filter_by_difficulty_relaxed(
    candidates: list[MissionCandidate],
    state: DifficultyState,
    tolerance: int = _RELAXED_DIFFICULTY_TOLERANCE,
) -> list[MissionCandidate]:
    """Filter candidates with a relaxed difficulty tolerance (±2).

    Args:
        candidates: Mission candidates to filter.
        state: Current difficulty state.
        tolerance: Maximum allowed distance from user level.

    Returns:
        Filtered list of candidates within the relaxed range.
    """
    result: list[MissionCandidate] = []
    for candidate in candidates:
        user_level = state.levels.get(candidate.category, 1)
        if abs(candidate.difficulty - user_level) <= tolerance:
            result.append(candidate)
    return result


def generate_daily_mission(
    user_id: str,
    campaign_id: str,
    db: DynamoDBClient | None = None,
) -> GenerationResult | dict[str, str]:
    """Run the full mission generation pipeline.

    Pipeline steps:
        1. Fetch user profile, campaign, mission history, evidence, market data
        2. Compute skill gaps via analyze_skill_gaps
        3. Compute difficulty state via compute_difficulty_state
        4. Instantiate templates for current phase via instantiate_all_templates
        5. Filter by difficulty via filter_by_difficulty
        6. Exclude recently completed duplicates (14-day window)
        7. Score and rank via score_and_rank
        8. Return top 3 (primary + 2 alternates) as GenerationResult

    Args:
        user_id: The user's identifier.
        campaign_id: The active campaign identifier.
        db: Optional DynamoDBClient instance. Created if not provided.

    Returns:
        GenerationResult on success, or a dict with an "error" key on failure.
    """
    if db is None:
        db = DynamoDBClient()

    # --- Step 1: Fetch data from DynamoDB ---
    profile = db.get_item("user_profiles", {"userId": user_id})
    if not profile:
        return {"error": f"User profile not found for user_id={user_id}"}

    campaign = db.get_item(
        "campaigns", {"userId": user_id, "campaignId": campaign_id}
    )
    if not campaign:
        return {"error": f"Campaign not found for campaign_id={campaign_id}"}

    mission_history = db.query(
        "mission_history",
        Key("userId").eq(user_id),
    )

    evidence_records = db.query(
        "evidence_vault",
        Key("userId").eq(user_id),
    )

    # Market data keyed by role title via GSI.
    target_role = profile.get("targetRole") or profile.get("target_role", "")
    try:
        market_items = db.query(
            "market_data",
            Key("roleTitle").eq(target_role),
            index_name="role-title-index",
        ) if target_role else []
    except Exception:
        logger.warning("Market data lookup failed for role=%s", target_role)
        market_items = []

    # --- Prepare inputs ---
    user_skills: list[str] = profile.get("skills", [])
    evidence_by_skill = _build_evidence_by_skill(evidence_records)

    # Build target requirements and market demand from market data.
    target_requirements: list[dict[str, Any]] = []
    market_demand: dict[str, float] = {}
    market_data_dict: dict[str, Any] = {}

    if market_items:
        market_data_dict = market_items[0]
        # Support both test format (required_skills/demand) and
        # DynamoDB format (topSkills/frequency).
        skills_list = (
            market_data_dict.get("required_skills")
            or market_data_dict.get("topSkills")
            or []
        )
        for skill_info in skills_list:
            target_requirements.append(skill_info)
            skill_name = skill_info.get("skill", "")
            demand = skill_info.get("demand") or skill_info.get("frequency", 1.0)
            if skill_name:
                market_demand[skill_name] = float(demand) / 100.0 if float(demand) > 1.0 else float(demand)
    else:
        # Fallback: equal demand for all user skills.
        for skill in user_skills:
            market_demand[skill] = 1.0

    raw_phase = campaign.get("phase", "foundation")
    current_phase = _map_phase(raw_phase)

    # --- Step 2: Skill gap analysis ---
    skill_gap_report = analyze_skill_gaps(
        user_skills=user_skills,
        evidence_by_skill=evidence_by_skill,
        target_requirements=target_requirements,
        market_demand=market_demand,
    )

    # --- Step 3: Difficulty state ---
    difficulty_state = compute_difficulty_state(user_id, mission_history)

    # --- Step 4: Instantiate templates ---
    candidates = instantiate_all_templates(
        profile=profile,
        skill_gaps=skill_gap_report,
        market_data=market_data_dict,
        phase=current_phase,
    )

    # --- Step 5: Filter by difficulty ---
    filtered = filter_by_difficulty(candidates, difficulty_state)

    # --- Step 6: Exclude recent duplicates ---
    filtered = _exclude_recent_duplicates(filtered, mission_history)

    # If insufficient candidates, relax difficulty filter and retry.
    if len(filtered) < 3:
        filtered = _filter_by_difficulty_relaxed(candidates, difficulty_state)
        filtered = _exclude_recent_duplicates(filtered, mission_history)

    # If still insufficient after relaxing, use all non-duplicate candidates.
    if len(filtered) < 3:
        filtered = _exclude_recent_duplicates(candidates, mission_history)

    if not filtered:
        return {"error": "No mission candidates available after filtering"}

    # --- Step 7: Score and rank ---
    streak_info = _compute_streak_info(mission_history)
    ranked = score_and_rank(
        candidates=filtered,
        skill_gaps=skill_gap_report,
        mission_history=mission_history,
        current_phase=current_phase,
        streak_info=streak_info,
        difficulty_state=difficulty_state,
    )

    # --- Step 8: Return top 3 ---
    primary = ranked[0]
    alternates = ranked[1:3] if len(ranked) >= 3 else ranked[1:]

    return GenerationResult(
        primary=primary,
        alternates=alternates,
        skill_gap_report=skill_gap_report,
    )


def complete_mission(
    user_id: str,
    mission_id: str,
    evidence_ids: list[str],
    db: DynamoDBClient | None = None,
) -> CompletionResult | dict[str, str]:
    """Handle mission completion: state transition, difficulty update, gate check.

    Pipeline steps:
        1. Fetch mission from DynamoDB
        2. Transition mission to completed via transition_mission
        3. Update difficulty state via update_difficulty
        4. Evaluate phase gate via evaluate_gate
        5. Save updated mission and difficulty state to DynamoDB
        6. Return CompletionResult

    Args:
        user_id: The user's identifier.
        mission_id: The mission to complete.
        evidence_ids: Evidence record IDs to link to the mission.
        db: Optional DynamoDBClient instance. Created if not provided.

    Returns:
        CompletionResult on success, or a dict with an "error" key on failure.
    """
    if db is None:
        db = DynamoDBClient()

    # --- Step 1: Fetch mission ---
    mission = db.get_item(
        "mission_history", {"userId": user_id, "missionId": mission_id}
    )
    if not mission:
        return {"error": f"Mission not found for mission_id={mission_id}"}

    # --- Step 2: Transition to completed ---
    now = datetime.now(timezone.utc).isoformat()
    updated_mission = transition_mission(
        mission=mission,
        target_status="completed",
        evidence_ids=evidence_ids,
        timestamp=now,
    )

    # --- Steps 3+4: Parallel fetch (independent after transition) ---
    category = updated_mission.get("category", "")
    campaign_id = updated_mission.get("campaignId") or updated_mission.get("campaign_id", "")

    with ThreadPoolExecutor(max_workers=3) as executor:
        history_future = executor.submit(
            db.query, "mission_history", Key("userId").eq(user_id),
        )
        campaign_future = executor.submit(
            db.get_item, "campaigns", {"userId": user_id, "campaignId": campaign_id},
        )
        evidence_future = executor.submit(
            db.query, "evidence_vault", Key("userId").eq(user_id),
        )

        try:
            mission_history = history_future.result(timeout=8)
            campaign = campaign_future.result(timeout=8)
            evidence_records = evidence_future.result(timeout=8)
        except FuturesTimeoutError:
            logger.error("complete_mission parallel fetch timed out for user=%s", user_id)
            raise

    # Difficulty update
    difficulty_state = compute_difficulty_state(user_id, mission_history)

    old_level = difficulty_state.levels.get(category)
    new_difficulty_state = update_difficulty(
        state=difficulty_state,
        category=category,
        outcome="completed",
        current_date=now,
    )
    new_level = new_difficulty_state.levels.get(category)

    difficulty_change: dict[str, int] | None = None
    if old_level is not None and new_level is not None and old_level != new_level:
        difficulty_change = {category: new_level}

    # Phase gate evaluation
    raw_phase = (campaign or {}).get("phase", "foundation")
    current_phase = _map_phase(raw_phase)

    # Build completed missions list (include the just-completed one).
    completed_missions = [
        m for m in mission_history if m.get("status") == "completed"
    ]
    # Add the current mission if not already in history.
    if not any(m.get("missionId") == mission_id for m in completed_missions):
        completed_missions.append(updated_mission)

    evidence_by_skill = _build_evidence_by_skill(evidence_records)

    gate_result = evaluate_gate(
        current_phase=current_phase,
        completed_missions=completed_missions,
        evidence_by_skill=evidence_by_skill,
        market_alignment_pct=0.0,  # Recompute below if possible.
    )

    # Recompute market alignment for a more accurate gate evaluation.
    target_role = (
        (campaign or {}).get("targetRole")
        or (campaign or {}).get("target_role", "")
    )
    if not target_role:
        profile = db.get_item("user_profiles", {"userId": user_id})
        target_role = (
            (profile or {}).get("targetRole")
            or (profile or {}).get("target_role", "")
        )
    try:
        market_items = db.query(
            "market_data",
            Key("roleTitle").eq(target_role),
            index_name="role-title-index",
        ) if target_role else []
    except Exception:
        logger.warning("Market data lookup failed for role=%s", target_role)
        market_items = []

    market_demand: dict[str, float] = {}
    target_requirements: list[dict[str, Any]] = []
    if market_items:
        skills_list = (
            market_items[0].get("required_skills")
            or market_items[0].get("topSkills")
            or []
        )
        for skill_info in skills_list:
            target_requirements.append(skill_info)
            skill_name = skill_info.get("skill", "")
            demand = skill_info.get("demand") or skill_info.get("frequency", 1.0)
            if skill_name:
                market_demand[skill_name] = float(demand) / 100.0 if float(demand) > 1.0 else float(demand)

    if market_demand:
        user_skills = list(evidence_by_skill.keys())
        gap_report = analyze_skill_gaps(
            user_skills=user_skills,
            evidence_by_skill=evidence_by_skill,
            target_requirements=target_requirements,
            market_demand=market_demand,
        )
        gate_result = evaluate_gate(
            current_phase=current_phase,
            completed_missions=completed_missions,
            evidence_by_skill=evidence_by_skill,
            market_alignment_pct=gap_report.market_alignment_pct,
        )

    # --- Step 5: Save to DynamoDB ---
    db.put_item("mission_history", updated_mission)

    # Save updated difficulty state to campaign.
    if campaign_id:
        updates: dict[str, Any] = {
            "difficultyState": new_difficulty_state.to_dict(),
        }
        # If gate passed, advance the phase.
        if gate_result.passed and gate_result.next_phase:
            updates["phase"] = gate_result.next_phase
        db.update_item(
            "campaigns", {"userId": user_id, "campaignId": campaign_id}, updates
        )

    # --- Step 6: Return result ---
    return CompletionResult(
        mission_id=mission_id,
        difficulty_change=difficulty_change,
        gate_result=gate_result,
        behavioral_update={
            "category": category,
            "outcome": "completed",
            "new_difficulty_state": new_difficulty_state.to_dict(),
        },
    )
