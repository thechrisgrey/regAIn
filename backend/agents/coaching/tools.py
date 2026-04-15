"""Strands tools for the REGAIN Coaching Agent.

Each tool is a pure function decorated with @tool that the Coaching Agent
can invoke during conversation to read or write platform data. Tools use
the shared DynamoDBClient for all data operations and return structured
dicts — never free text.
"""

import dataclasses
import importlib
import json
import logging
import os
import urllib.error
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any

import boto3

from strands import tool

# 'lambda' is a Python keyword, so we use importlib to load the module.
from boto3.dynamodb.conditions import Attr as boto3_attr, Key

_dynamodb_mod = importlib.import_module("backend.handlers.shared.dynamodb")
DynamoDBClient = _dynamodb_mod.DynamoDBClient

from backend.engine.generator import (  # noqa: E402
    generate_daily_mission as engine_generate_mission,
    complete_mission as engine_complete_mission,
)
from backend.engine.models import GenerationResult, CompletionResult  # noqa: E402, F401

logger = logging.getLogger(__name__)

# Typed error kind constants for structured tool error responses.
# These allow the LLM to reason about retry-ability and error handling.
ERR_NOT_FOUND = "not_found"
ERR_TRANSIENT = "transient"
ERR_PERMANENT = "permanent"
ERR_RATE_LIMITED = "rate_limited"
ERR_VALIDATION = "validation"

# O*NET v2 section names recognised by onet_career_detail.
# Mirrors the sections in backend/handlers/onet/service.py::get_career_detail.
ONET_VALID_SECTIONS = frozenset({
    "knowledge",
    "skills",
    "abilities",
    "personality",
    "technology",
    "education",
    "job_outlook",
    "check_out_my_state",
    "explore_more",
})

# SOC code pattern: e.g. "15-1252.00"
import re as _re  # local alias to avoid polluting module namespace
_ONET_SOC_PATTERN = _re.compile(r"^\d{2}-\d{4}\.\d{2}$")

db = DynamoDBClient()

from backend.agents.coaching.profile_fields import ALLOWED_PROFILE_FIELDS as _PROFILE_ALLOWED_FIELDS

# Lazy-load taxonomy normalization
_taxonomy_mod = importlib.import_module("backend.handlers.market_intel.taxonomy")
_normalize_skill = _taxonomy_mod.normalize_skill


def get_valid_skill_tags(user_id: str) -> list[str]:
    """Return canonical skill tags for the user's active campaign.

    Reads the active campaign's ``skillsFocus`` list, which contains the
    curated subset of skills the agent should tag evidence with.  Returns
    an empty list when no active campaign exists or on any error.
    """
    try:
        campaigns = db.query(
            "campaigns",
            key_condition=Key("userId").eq(user_id),
            filter_expression=boto3_attr("status").eq("active"),
        )
        if campaigns:
            return campaigns[0].get("skillsFocus", [])
        return []
    except Exception:
        logger.warning("Could not load skill tags for %s", user_id)
        return []


@tool
def read_user_profile(user_id: str) -> dict[str, Any]:
    """Read a user's complete profile from the REGAIN platform.

    Use this tool to retrieve a user's profile before responding to any
    coaching interaction. The profile contains the user's name, persona
    type (veteran, ai_displaced, career_pivoter), target role, skills
    inventory, and onboarding status. Always call this tool at the start
    of a session to personalize your coaching.

    Args:
        user_id: The unique identifier of the user whose profile to read.

    Returns:
        A dict containing the user's profile fields (user_id, name, email,
        persona, target_role, skills, onboarding_completed, created_at),
        or an error dict if the profile is not found.
    """
    try:
        item = db.get_item("user_profiles", {"userId": user_id})
        if item is None:
            return {
                "error": "not_found",
                "error_kind": ERR_NOT_FOUND,
                "message": f"No profile found for user '{user_id}'.",
            }
        return item
    except ValueError as exc:
        return {"error": "invalid_input", "error_kind": ERR_VALIDATION, "message": str(exc)}
    except Exception as exc:
        logger.exception("Failed to read user profile for %s", user_id)
        return {"error": "read_failed", "error_kind": ERR_TRANSIENT, "message": str(exc)}


@tool
def update_user_profile(user_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    """Update fields on a user's profile in the REGAIN platform.

    Use this tool to persist changes to a user's profile — for example,
    after extracting skills from a conversation, setting the target role,
    updating the persona classification, or marking onboarding as complete.
    Pass only the fields that need to change; existing fields are preserved.

    Args:
        user_id: The unique identifier of the user whose profile to update.
        updates: A dict of field names to new values. Valid fields include
            skills, target_role, persona, onboarding_completed, first_name,
            last_name, current_role, company, years_in_role, highest_position,
            story, coach_notes, experience, and Transition Profile fields
            (transferable_skills, technical_skills, domain_knowledge,
            experience_years, industry, role_history).

    Returns:
        A dict containing the full updated profile (all attributes after
        the update), or an error dict if the update fails.
    """
    if not updates:
        return {"error": "invalid_input", "error_kind": ERR_VALIDATION, "message": "No updates provided."}

    forbidden = set(updates.keys()) - _PROFILE_ALLOWED_FIELDS
    if forbidden:
        return {
            "error": "invalid_input",
            "error_kind": ERR_VALIDATION,
            "message": f"Protected field(s) cannot be updated: {sorted(forbidden)}",
        }

    try:
        response = db.update_item(
            "user_profiles",
            key={"userId": user_id},
            updates=updates,
        )
        return response.get("Attributes", {})
    except ValueError as exc:
        return {"error": "invalid_input", "error_kind": ERR_VALIDATION, "message": str(exc)}
    except Exception as exc:
        logger.exception("Failed to update user profile for %s", user_id)
        return {"error": "write_failed", "error_kind": ERR_TRANSIENT, "message": str(exc)}


@tool
def get_campaign_status(user_id: str) -> dict[str, Any]:
    """Get the active campaign for a user on the REGAIN platform.

    Use this tool to check whether a user already has an active reskilling
    campaign. Returns the campaign record including its current phase
    (foundation, expansion, or launch), title, target role, and skills
    focus. Call this before creating a new campaign or when reviewing
    progress during a check-in session.

    Args:
        user_id: The unique identifier of the user whose campaign to retrieve.

    Returns:
        A dict containing the active campaign fields (userId, campaignId,
        title, phase, status, startDate, targetRole, skillsFocus), or an
        error dict if no active campaign is found.
    """
    try:
        items = db.query(
            "campaigns",
            key_condition=Key("userId").eq(user_id),
            filter_expression=boto3_attr("status").eq("active"),
        )
        if not items:
            return {
                "error": "not_found",
                "error_kind": ERR_NOT_FOUND,
                "message": f"No active campaign found for user '{user_id}'.",
            }
        return items[0]
    except ValueError as exc:
        return {"error": "invalid_input", "error_kind": ERR_VALIDATION, "message": str(exc)}
    except Exception as exc:
        logger.exception("Failed to get campaign status for %s", user_id)
        return {"error": "read_failed", "error_kind": ERR_TRANSIENT, "message": str(exc)}


@tool
def create_campaign(
    user_id: str,
    title: str,
    target_role: str,
    skills_focus: list,
) -> dict[str, Any]:
    """Create a new reskilling campaign for a user on the REGAIN platform.

    Use this tool after completing onboarding and building a Transition
    Profile. Creates a campaign starting in the foundation phase with
    active status. Each campaign represents a structured three-phase
    reskilling plan (Foundation → Expansion → Launch) tailored to the
    user's target role and skill gaps.

    Args:
        user_id: The unique identifier of the user to create the campaign for.
        title: A descriptive title for the campaign (e.g. "Transition to AI QA Engineer").
        target_role: The job role the user is working toward.
        skills_focus: A list of 3-6 specific skill names extracted from the
            onboarding conversation, normalized to title case (e.g.
            ["Python Programming", "Test Automation", "CI/CD"]). These
            become the prescribed skill tags for all evidence and missions
            in this campaign — the agent will be constrained to use only
            these tags.

    Returns:
        A dict containing the created campaign fields including the
        generated campaignId, or an error dict if creation fails.
    """
    campaign_id = f"campaign-{uuid.uuid4()}"
    item = {
        "userId": user_id,
        "campaignId": campaign_id,
        "title": title,
        "phase": "foundation",
        "status": "active",
        "startDate": datetime.now(timezone.utc).isoformat(),
        "targetRole": target_role,
        "skillsFocus": skills_focus,
    }
    try:
        db.put_item("campaigns", item)
        return item
    except ValueError as exc:
        return {"error": "invalid_input", "error_kind": ERR_VALIDATION, "message": str(exc)}
    except Exception as exc:
        logger.exception("Failed to create campaign for %s", user_id)
        return {"error": "write_failed", "error_kind": ERR_TRANSIENT, "message": str(exc)}


def _analyze_patterns(missions: list[dict[str, Any]]) -> dict[str, Any]:
    """Analyze mission completion patterns for behavioral signals.

    Examines a user's full mission history to detect avoidance patterns,
    strength signals, and completion rates by skill category. Pure function
    with no side effects — operates only on the provided mission list.

    Args:
        missions: List of mission records for the user. Each dict should
            contain at least 'status' (one of "pending", "in_progress",
            "completed", "skipped") and 'skillTag' (str).

    Returns:
        Dict with pattern analysis including total counts, per-category
        breakdowns, avoidance_signals (categories with >50% skip rate),
        and strength_signals (categories with 0% skip rate and >=1 completion).
    """
    total = len(missions)
    completed = 0
    skipped = 0
    pending = 0
    in_progress = 0
    by_category: dict[str, dict[str, int]] = {}

    for mission in missions:
        status = mission.get("status", "")
        skill_tag = mission.get("skillTag", "unknown")

        if status == "completed":
            completed += 1
        elif status == "skipped":
            skipped += 1
        elif status == "pending":
            pending += 1
        elif status == "in_progress":
            in_progress += 1

        if skill_tag not in by_category:
            by_category[skill_tag] = {"assigned": 0, "completed": 0, "skipped": 0}

        by_category[skill_tag]["assigned"] += 1
        if status == "completed":
            by_category[skill_tag]["completed"] += 1
        elif status == "skipped":
            by_category[skill_tag]["skipped"] += 1

    avoidance_signals: list[str] = []
    strength_signals: list[str] = []

    for category, counts in by_category.items():
        assigned = counts["assigned"]
        if assigned > 0 and counts["skipped"] / assigned > 0.5:
            avoidance_signals.append(category)
        if counts["skipped"] == 0 and counts["completed"] >= 1:
            strength_signals.append(category)

    return {
        "total_missions": total,
        "completed": completed,
        "skipped": skipped,
        "pending": pending,
        "in_progress": in_progress,
        "by_category": by_category,
        "avoidance_signals": sorted(avoidance_signals),
        "strength_signals": sorted(strength_signals),
    }


@tool
def get_current_mission(user_id: str) -> dict[str, Any]:
    """Get the current pending or in-progress mission for a user.

    Use this tool during check-in sessions to see what mission the user
    is currently working on or has queued up next. Also returns behavioral
    pattern analysis from the user's full mission history so you can
    detect avoidance, identify strengths, and adapt coaching accordingly.

    Args:
        user_id: The unique identifier of the user whose mission to retrieve.

    Returns:
        A dict containing the current mission fields (userId, missionId,
        campaignId, title, description, status, skillTag) and a patterns
        key with behavioral analysis, or an error dict if no current
        mission is found.
    """
    try:
        all_missions = db.query_all(
            "mission_history",
            key_condition=Key("userId").eq(user_id),
        )

        patterns = _analyze_patterns(all_missions)

        current = [
            m for m in all_missions
            if m.get("status") in ("pending", "in_progress")
        ]

        if not current:
            return {
                "error": "not_found",
                "error_kind": ERR_NOT_FOUND,
                "message": f"No pending or in-progress mission for user '{user_id}'.",
                "patterns": patterns,
            }

        mission = current[0]
        mission["patterns"] = patterns
        return mission
    except ValueError as exc:
        return {"error": "invalid_input", "error_kind": ERR_VALIDATION, "message": str(exc)}
    except Exception as exc:
        logger.exception("Failed to get current mission for %s", user_id)
        return {"error": "read_failed", "error_kind": ERR_TRANSIENT, "message": str(exc)}


class _RateLimitExceeded(Exception):
    """Raised when the daily mission generation limit is reached."""


def _enforce_daily_rate_limit(user_id: str) -> None:
    """Atomically increment the daily mission generation counter.

    Uses a DynamoDB conditional update on UserProfiles to ensure no more
    than 3 missions are generated per user per day. Resets the counter
    when the date changes.

    Args:
        user_id: The user whose counter to increment.

    Raises:
        _RateLimitExceeded: If the user has already generated 3 missions today.
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    table = db._get_table("user_profiles")

    # First, reset the counter if the date has changed.
    try:
        table.update_item(
            Key={"userId": user_id},
            UpdateExpression="SET dailyMissionGenCount = :zero, lastMissionGenDate = :today",
            ConditionExpression=(
                "attribute_not_exists(lastMissionGenDate) OR lastMissionGenDate <> :today"
            ),
            ExpressionAttributeValues={
                ":zero": 0,
                ":today": today,
            },
        )
    except table.meta.client.exceptions.ConditionalCheckFailedException:
        # Date already matches today — counter is current, no reset needed.
        pass

    # Atomically increment, but only if count < 3.
    try:
        table.update_item(
            Key={"userId": user_id},
            UpdateExpression="ADD dailyMissionGenCount :inc",
            ConditionExpression="dailyMissionGenCount < :limit",
            ExpressionAttributeValues={
                ":inc": 1,
                ":limit": 3,
            },
        )
    except table.meta.client.exceptions.ConditionalCheckFailedException:
        raise _RateLimitExceeded()


@tool
def generate_mission(
    user_id: str,
    campaign_id: str,
) -> dict[str, Any]:
    """Generate a personalized daily mission for a user's reskilling campaign.

    IMPORTANT: Rate-limited to 3 missions per user per day. The counter
    resets at midnight UTC. If the limit is reached, returns an error with
    error_kind='rate_limited'. Before calling this tool, consider informing
    the user how many missions they have remaining today.

    Runs the full Mission Engine pipeline: skill gap analysis, template
    instantiation, difficulty filtering, priority scoring, and ranking.
    Returns the top-scored mission as the primary recommendation plus two
    alternates. The engine handles all intelligence — just provide the user
    and campaign identifiers.

    Args:
        user_id: The unique identifier of the user to generate a mission for.
        campaign_id: The active campaign this mission belongs to.

    Returns:
        A dict with "primary" (the recommended mission with all fields),
        "alternates" (list of 2 backup missions), and "skill_gap_report"
        (current gap analysis). Returns an error dict if generation fails
        or the daily limit is reached.
    """
    try:
        _enforce_daily_rate_limit(user_id)
    except _RateLimitExceeded:
        return {
            "error": "daily_limit_reached",
            "error_kind": ERR_RATE_LIMITED,
            "message": "Daily mission generation limit reached (3 per day).",
        }
    except Exception as exc:
        logger.exception("Rate limit check failed for %s", user_id)
        return {"error": "rate_limit_check_failed", "error_kind": ERR_TRANSIENT, "message": str(exc)}

    try:
        result = engine_generate_mission(
            user_id=user_id,
            campaign_id=campaign_id,
            db=db,
        )

        # Engine returns a dict with "error" key on failure.
        if isinstance(result, dict):
            return result

        return dataclasses.asdict(result)
    except Exception as exc:
        logger.exception("Failed to generate mission for %s", user_id)
        return {"error": "generation_failed", "error_kind": ERR_TRANSIENT, "message": str(exc)}


@tool
def log_evidence(
    user_id: str,
    mission_id: str,
    skill_tag: str,
    reflection: str,
    artifact_url: str = "",
) -> dict[str, Any]:
    """Log a piece of evidence to the user's Evidence Vault.

    Use this tool whenever a user describes a completed action, skill
    demonstration, or reflection during conversation. Creates a timestamped
    evidence record tagged with the relevant skill. After logging, returns
    the cumulative count of evidence for that skill so you can tell the
    user how much proof they've built.

    PRECONDITION: Requires at least one active campaign. If all campaigns
    are completed, returns error_kind='permanent' with message 'Cannot log
    evidence — all campaigns completed. Start a new campaign first.' Check
    campaign status before calling if the user may have finished their
    campaign.

    Args:
        user_id: The unique identifier of the user who produced the evidence.
        mission_id: The mission this evidence relates to.
        skill_tag: The skill this evidence demonstrates (e.g. "python",
            "networking", "systematic_debugging").
        reflection: The user's own words describing what they did or learned.
        artifact_url: Optional URL to an artifact (document, repo, screenshot)
            that supports the evidence.

    Returns:
        A dict with evidence_id (the new record's ID) and
        skill_evidence_count (total evidence records for this user and
        skill_tag), or an error dict if logging fails.
    """
    # Requirement 5.3 — reject evidence writes when campaign is completed.
    # This check lives in Lambda tool logic (not Cedar) to avoid giving
    # Gateway DynamoDB access to the Campaigns table.
    try:
        campaigns = db.query(
            "campaigns",
            key_condition=Key("userId").eq(user_id),
        )
        completed = [c for c in campaigns if c.get("status") == "completed"]
        active = [c for c in campaigns if c.get("status") == "active"]
        if completed and not active:
            return {
                "error": "campaign_completed",
                "error_kind": ERR_PERMANENT,
                "message": (
                    "Cannot log evidence — all campaigns for this user are "
                    "completed. Start a new campaign first."
                ),
            }
    except Exception as exc:
        logger.exception("Failed to check campaign status for %s", user_id)
        return {"error": "read_failed", "error_kind": ERR_TRANSIENT, "message": str(exc)}

    # Normalize the skill tag to a canonical name when possible.
    normalized = _normalize_skill(skill_tag)
    if normalized:
        skill_tag = normalized

    evidence_id = f"evidence-{uuid.uuid4()}"
    item: dict[str, Any] = {
        "userId": user_id,
        "evidenceId": evidence_id,
        "missionId": mission_id,
        "skillTag": skill_tag,
        "reflection": reflection,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "wordCount": len(reflection.split()) if reflection else 0,
    }
    if artifact_url:
        item["artifactUrl"] = artifact_url

    try:
        db.put_item("evidence_vault", item)

        from backend.handlers.shared.metrics import emit_metric
        emit_metric("evidence_logged")

        # Count evidence for this user+skill using Select=COUNT to avoid
        # transferring item data (only the count is returned).
        skill_count_resp = db._get_table("evidence_vault").query(
            KeyConditionExpression=Key("userId").eq(user_id),
            FilterExpression=boto3_attr("skillTag").eq(skill_tag),
            Select="COUNT",
        )
        skill_evidence_count = skill_count_resp.get("Count", 0)

        return {
            "evidence_id": evidence_id,
            "skill_evidence_count": skill_evidence_count,
        }
    except ValueError as exc:
        return {"error": "invalid_input", "error_kind": ERR_VALIDATION, "message": str(exc)}
    except Exception as exc:
        logger.exception("Failed to log evidence for %s", user_id)
        return {"error": "write_failed", "error_kind": ERR_TRANSIENT, "message": str(exc)}


# Phase transitions that should trigger resume regeneration.
_RESUME_PHASE_TRIGGERS = {"expansion", "launch"}


def _trigger_resume_generation(user_id: str, trigger: str) -> None:
    """Fire-and-forget invocation of the Resume Lambda.

    Silently returns on any failure so the calling code path is never
    blocked by resume generation issues.
    """
    arn = os.environ.get("RESUME_LAMBDA_ARN")
    if not arn:
        return
    try:
        lambda_client = boto3.client("lambda")
        lambda_client.invoke(
            FunctionName=arn,
            InvocationType="Event",
            Payload=json.dumps({"user_id": user_id, "trigger": trigger}),
        )
    except Exception:
        logger.warning(
            "Async resume generation failed for user %s (trigger=%s)",
            user_id,
            trigger,
            exc_info=True,
        )


@tool
def complete_mission(
    user_id: str,
    mission_id: str,
    reflection: str,
    skill_tag: str,
    artifact_url: str = "",
) -> dict[str, Any]:
    """Mark a mission as completed, log evidence, and update campaign progress.

    Logs the user's evidence first (reflection, skill tag, optional artifact),
    then delegates to the Mission Engine for state transition, difficulty
    adjustment, and phase gate evaluation. Returns completion details
    including any difficulty changes and phase transition info so you can
    share progress with the user.

    SIDE EFFECT: On successful completion, asynchronously triggers resume
    regeneration in the background. If the completion causes a phase
    advancement to Expansion or Launch, an additional resume regeneration
    is triggered. These are fire-and-forget — the user will not see the
    updated resume immediately but can check it later on the Resume page.

    Args:
        user_id: The unique identifier of the user completing the mission.
        mission_id: The mission being completed.
        reflection: The user's reflection on what they did or learned.
        skill_tag: The skill demonstrated by completing this mission.
        artifact_url: Optional URL to a supporting artifact.

    Returns:
        A dict with mission_id, difficulty_change (if any),
        gate_result (phase gate evaluation with progress), and
        behavioral_update. Also includes evidence_id from the logged
        evidence. Returns an error dict if the operation fails.
    """
    try:
        # Log evidence first — the engine needs evidence_ids.
        evidence_result = log_evidence(
            user_id=user_id,
            mission_id=mission_id,
            skill_tag=skill_tag,
            reflection=reflection,
            artifact_url=artifact_url,
        )

        if "error" in evidence_result:
            return evidence_result

        evidence_id = evidence_result["evidence_id"]

        # If the mission is still in "pending" status, transition it to
        # "in_progress" first so the engine's lifecycle state machine
        # accepts the completed transition.
        mission_item = db.get_item(
            "mission_history", {"userId": user_id, "missionId": mission_id}
        )
        if mission_item and mission_item.get("status") == "pending":
            from backend.engine.lifecycle import transition_mission
            updated = transition_mission(mission_item, "in_progress")
            db.put_item("mission_history", updated)

        # Delegate completion logic to the Mission Engine.
        result = engine_complete_mission(
            user_id=user_id,
            mission_id=mission_id,
            evidence_ids=[evidence_id],
            db=db,
        )

        # Engine returns a dict with "error" key on failure.
        if isinstance(result, dict):
            return result

        completion_dict = dataclasses.asdict(result)
        completion_dict["evidence_id"] = evidence_id
        completion_dict["skill_evidence_count"] = evidence_result.get(
            "skill_evidence_count", 0
        )

        from backend.handlers.shared.metrics import emit_metric
        emit_metric("missions_completed")

        # --- Async resume triggers (fire-and-forget) ---
        _trigger_resume_generation(user_id, "mission_completion")

        gate = completion_dict.get("gate_result") or {}
        if gate.get("passed") and gate.get("next_phase") in _RESUME_PHASE_TRIGGERS:
            _trigger_resume_generation(user_id, "phase_advancement")

        return completion_dict
    except Exception as exc:
        logger.exception("Failed to complete mission %s for %s", mission_id, user_id)
        return {"error": "completion_failed", "error_kind": ERR_TRANSIENT, "message": str(exc)}


@tool
def get_evidence_summary(user_id: str) -> dict[str, Any]:
    """Get a summary of all evidence in a user's Evidence Vault.

    Use this tool to understand the breadth and depth of a user's
    documented skill evidence. Returns a breakdown of evidence counts
    by skill tag and the most recent evidence entries. Call this during
    check-ins to reference the user's accumulated proof, or when
    generating missions to identify skill gaps.

    Args:
        user_id: The unique identifier of the user whose evidence to summarize.

    Returns:
        A dict with by_skill (dict mapping skill tags to counts),
        recent (list of the 5 most recent evidence entries), and
        total_count (total number of evidence records), or an error
        dict if the query fails.
    """
    try:
        items = db.query_all(
            "evidence_vault",
            key_condition=Key("userId").eq(user_id),
        )

        by_skill: dict[str, int] = {}
        for item in items:
            tag = item.get("skillTag", "unknown")
            by_skill[tag] = by_skill.get(tag, 0) + 1

        sorted_items = sorted(
            items,
            key=lambda x: x.get("createdAt", ""),
            reverse=True,
        )
        recent = sorted_items[:5]

        return {
            "by_skill": by_skill,
            "recent": recent,
            "total_count": len(items),
        }
    except ValueError as exc:
        return {"error": "invalid_input", "error_kind": ERR_VALIDATION, "message": str(exc)}
    except Exception as exc:
        logger.exception("Failed to get evidence summary for %s", user_id)
        return {"error": "read_failed", "error_kind": ERR_TRANSIENT, "message": str(exc)}


@tool
def get_market_insights(role_id: str) -> dict[str, Any]:
    """Get the latest market intelligence data for a target role.

    Use this tool when you need current demand scores, growth trends,
    in-demand skills, and salary ranges for a specific role. Reference
    this data when coaching users on which skills to prioritize, when
    generating market-aligned missions, or when discussing career
    trajectory and market positioning with the user.

    Args:
        role_id: A snake_case identifier derived from the target role
            name (e.g. "ai_qa_engineer" for "AI QA Engineer",
            "project_manager" for "Project Manager", "data_analyst"
            for "Data Analyst"). Use the user's targetRole from their
            profile, converted to lowercase with spaces replaced by
            underscores.

    Returns:
        A dict with demand_score, trend_direction, growth_rate,
        top_skills, salary_range, and relevant market insights for the
        role — or an error dict if no data is found.
    """
    try:
        _market_intel = importlib.import_module("backend.handlers.market_intel")

        demand = _market_intel.get_demand_score(role_id)
        if demand is None:
            return {
                "error": "not_found",
                "error_kind": ERR_NOT_FOUND,
                "message": f"No market data found for role '{role_id}'.",
            }

        insights = _market_intel.get_insights(role_id=role_id)

        return {
            "role_id": role_id,
            "demand_score": demand.get("demand_score", 0),
            "trend_direction": demand.get("trend_direction", "stable"),
            "growth_rate": demand.get("growth_rate", 0.0),
            "top_skills": demand.get("top_skills", []),
            "salary_range": demand.get("salary_range", {}),
            "insights": insights,
        }
    except Exception as exc:
        logger.exception("Failed to get market insights for role %s", role_id)
        return {"error": "read_failed", "error_kind": ERR_TRANSIENT, "message": str(exc)}


@tool
def get_alignment(user_id: str, target_role_id: str) -> dict[str, Any]:
    """Calculate how well a user's demonstrated skills match a target role.

    Use this tool during alignment checks, progress reviews, or gap
    discussions to show the user a concrete percentage of how their
    evidence-backed skills overlap with market requirements for a role.
    The result includes a per-skill breakdown, top gaps to close, and
    top strengths to leverage.

    Args:
        user_id: The user whose skills and evidence are evaluated.
        target_role_id: The role identifier to align against
            (e.g. "ai_qa_engineer", "project_manager").

    Returns:
        A dict with alignment_pct (0-100), skill_breakdown list,
        top_gaps (3 highest-impact missing skills), top_strengths
        (3 strongest matches), target_role_id, user_id, and
        calculated_at timestamp.
    """
    try:
        _market_intel = importlib.import_module("backend.handlers.market_intel")
        return _market_intel.calculate_alignment(user_id, target_role_id)
    except Exception as exc:
        logger.exception(
            "Failed to calculate alignment for user %s, role %s",
            user_id,
            target_role_id,
        )
        return {"error": "alignment_failed", "error_kind": ERR_TRANSIENT, "message": str(exc)}


# ---------------------------------------------------------------------------
# AgentCore Memory tools
# ---------------------------------------------------------------------------

_MEMORY_NAMESPACES = ["/summaries/{user_id}/", "/preferences/{user_id}/", "/facts/{user_id}/"]


@tool
def recall_memory(user_id: str, query: str) -> dict[str, Any]:
    """Retrieve relevant past conversation context for a user.

    Use this tool for targeted mid-conversation memory queries when you
    need specific context beyond what was automatically recalled at
    session start (e.g. "what did we discuss about Python skills?").

    Searches across all memory strategy namespaces (summaries, preferences,
    facts) and returns combined results ranked by relevance.

    Args:
        user_id: The authenticated user's ID.
        query: A natural-language description of what context to
            retrieve (e.g. "previous coaching session summary",
            "networking avoidance pattern").

    Returns:
        A dict with "entries" (list of memory entry dicts, each with
        content and metadata) and "source" indicating the result origin:
        - source="memory": The memory service responded successfully.
          An empty entries list means no relevant memories exist.
        - source="unavailable": The memory service could not be reached.
    """
    memory_id = os.environ.get("AGENTCORE_MEMORY_ID", "")
    if not memory_id:
        return {"entries": [], "source": "unavailable"}

    try:
        client = boto3.client(
            "bedrock-agentcore",
            region_name=os.environ.get("AWS_REGION", "us-east-1"),
        )
        def _search_namespace(ns_template):
            ns = ns_template.format(user_id=user_id)
            resp = client.retrieve_memory_records(
                memoryId=memory_id,
                namespace=ns,
                searchCriteria={"query": {"text": query}},
            )
            return resp.get("memoryRecordSummaries", [])

        all_records = []
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {
                pool.submit(_search_namespace, ns): ns
                for ns in _MEMORY_NAMESPACES
            }
            for future in as_completed(futures):
                all_records.extend(future.result())

        return {
            "entries": [
                {
                    "content": record.get("content", ""),
                    "metadata": record.get("metadata", {}),
                }
                for record in all_records
            ],
            "source": "memory",
        }
    except Exception as exc:
        logger.warning(
            "AgentCore Memory recall failed for user %s: %s", user_id, exc
        )
        return {"entries": [], "source": "unavailable"}


@tool
def generate_resume(user_id: str) -> dict[str, Any]:
    """Generate a fresh resume for the user and return it immediately.

    Invokes the Resume Generation Lambda synchronously to gather all
    platform data (profile, campaign, missions, evidence, market
    alignment), synthesize a professionally written markdown resume
    with YAML frontmatter via Nova Lite, and store it in S3.

    Use this tool when the user explicitly asks to create, regenerate,
    or update their resume during a coaching session. Do NOT use this
    for simply viewing an existing resume — use get_resume instead.

    Args:
        user_id: The authenticated user's ID.

    Returns:
        A dict with keys content (markdown string), generatedAt
        (ISO 8601 timestamp), version (integer), and downloadUrl
        (presigned S3 URL valid for 1 hour). Returns an error dict
        with key "error" on failure.
    """
    arn = os.environ.get("RESUME_LAMBDA_ARN")
    if not arn:
        return {"error": "resume_unavailable", "error_kind": ERR_PERMANENT, "message": "Resume service is not configured."}

    try:
        lambda_client = boto3.client("lambda")
        response = lambda_client.invoke(
            FunctionName=arn,
            InvocationType="RequestResponse",
            Payload=json.dumps({"user_id": user_id, "trigger": "on_demand"}),
        )
        result = json.loads(response["Payload"].read())
        body = json.loads(result["body"])

        if result.get("statusCode", 200) != 200:
            return {
                "error": "generation_failed",
                "error_kind": ERR_TRANSIENT,
                "message": body.get("error", "Resume generation failed."),
            }

        return {
            "content": body["content"],
            "generatedAt": body["generatedAt"],
            "version": body["version"],
            "downloadUrl": body["downloadUrl"],
        }
    except Exception as exc:
        logger.exception("generate_resume tool failed for user %s", user_id)
        return {"error": "generation_failed", "error_kind": ERR_TRANSIENT, "message": str(exc)}


@tool
def get_resume(user_id: str) -> dict[str, Any]:
    """Retrieve the user's latest resume without regenerating it.

    Reads the resume pointer from UserProfiles, fetches the markdown
    content from S3, and generates a fresh presigned download URL.
    Returns the full resume content and metadata.

    Use this tool when the user wants to view, review, or discuss
    their existing resume. If no resume exists yet, returns a
    message prompting the user to complete a mission first.

    Args:
        user_id: The authenticated user's ID.

    Returns:
        A dict with keys content (markdown string), generatedAt
        (ISO 8601 timestamp), version (integer), and downloadUrl
        (presigned S3 URL valid for 1 hour). Returns a message dict
        if no resume exists, or an error dict on failure.
    """
    try:
        profile = db.get_item("user_profiles", {"userId": user_id})
        if not profile:
            return {"error": "not_found", "error_kind": ERR_NOT_FOUND, "message": "User profile not found."}

        s3_key = profile.get("resumeS3Key")
        if not s3_key:
            return {
                "message": "No resume exists yet. Complete your first mission to generate one."
            }

        bucket = os.environ.get("RESUME_BUCKET_NAME", "")
        s3_client = boto3.client("s3")

        obj = s3_client.get_object(Bucket=bucket, Key=s3_key)
        content = obj["Body"].read().decode("utf-8")

        download_url = s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": s3_key},
            ExpiresIn=3600,
        )

        return {
            "content": content,
            "generatedAt": profile.get("lastResumeGeneratedAt", ""),
            "version": profile.get("resumeVersion", 0),
            "downloadUrl": download_url,
        }
    except Exception as exc:
        logger.exception("get_resume tool failed for user %s", user_id)
        return {"error": "retrieval_failed", "error_kind": ERR_TRANSIENT, "message": str(exc)}


@tool
def read_calendar(user_id: str, start_date: str, end_date: str) -> dict[str, Any]:
    """Read calendar entries for a user within a date range.

    Use this tool to check what tasks and notes the user has scheduled
    before suggesting new activities or responding to calendar-related
    questions. Returns entries sorted by date.

    Args:
        user_id: The user's unique identifier.
        start_date: Start of range (YYYY-MM-DD).
        end_date: End of range (YYYY-MM-DD), inclusive.

    Returns:
        A dict with 'entries' list containing calendar items.
    """
    logger.info("read_calendar CALLED — user=%s range=%s to %s", user_id, start_date, end_date)
    try:
        entries = db.query_all(
            "calendar_entries",
            Key("userId").eq(user_id)
            & Key("dateEntryId").between(start_date, end_date + "\xff"),
        )
        return {"entries": entries}
    except ValueError:
        return {"error": "Calendar table not configured", "error_kind": ERR_TRANSIENT}
    except Exception as e:
        logger.exception("read_calendar failed for user %s", user_id)
        return {"error": str(e), "error_kind": ERR_TRANSIENT}


@tool
def write_calendar_entry(
    user_id: str, date: str, category: str, content: str
) -> dict[str, Any]:
    """Write a new calendar entry for the user as the coaching agent.

    Use this tool to:
    - Schedule a task after generating a mission
    - Write a coaching note with observations after a session
    - Add reminders when the user asks ("Remind me to do X on Thursday")
    - Track progress ("You've completed 3 missions this week")

    The entry is always authored as 'agent'. The user can delete it but
    neither the agent nor the user can edit agent entries after creation.

    Args:
        user_id: The user's unique identifier.
        date: Target date for the entry (YYYY-MM-DD).
        category: Entry type — must be 'task' or 'note'.
        content: Plain text body of the entry.

    Returns:
        A dict with 'success' and 'entryId' on success, or 'error' on failure.
    """
    logger.info("write_calendar_entry CALLED — user=%s date=%s cat=%s content=%s", user_id, date, category, content[:80])
    if category not in ("task", "note"):
        return {"error": f"Invalid category '{category}'. Use 'task' or 'note'.", "error_kind": ERR_VALIDATION}

    try:
        now = datetime.now(timezone.utc).isoformat()
        entry_id = f"{date}#{uuid.uuid4().hex[:12]}"

        db.put_item("calendar_entries", {
            "userId": user_id,
            "dateEntryId": entry_id,
            "date": date,
            "category": category,
            "author": "agent",
            "content": content,
            "createdAt": now,
            "updatedAt": now,
        })
        return {"success": True, "entryId": entry_id}
    except ValueError:
        return {"error": "Calendar table not configured", "error_kind": ERR_TRANSIENT}
    except Exception as e:
        logger.exception("write_calendar_entry failed for user %s", user_id)
        return {"error": str(e), "error_kind": ERR_TRANSIENT}


# ---------------------------------------------------------------------------
# O*NET career data tools
# ---------------------------------------------------------------------------


@tool
def onet_search_careers(keyword: str) -> dict[str, Any]:
    """Search O*NET for careers matching a keyword.

    Use this when you need to find the O*NET SOC code for a role the user
    mentions (e.g. "software engineer", "nurse"). Returns candidate careers
    with SOC codes and titles. Follow up with onet_career_detail to pull
    rich data for a specific career.

    Args:
        keyword: Free-text role or occupation query.

    Returns:
        Raw O*NET search response dict with a "career" list, or an error
        dict with ``error_kind``.
    """
    if not keyword or not keyword.strip():
        return {
            "error": "invalid_keyword",
            "error_kind": ERR_VALIDATION,
            "message": "keyword must be a non-empty string.",
        }

    from backend.handlers.onet import service as _onet_service  # lazy import

    try:
        return _onet_service.search_careers(keyword.strip())
    except urllib.error.HTTPError as exc:
        kind = ERR_NOT_FOUND if exc.code == 404 else (
            ERR_PERMANENT if 400 <= exc.code < 500 else ERR_TRANSIENT
        )
        return {
            "error": "onet_http_error",
            "error_kind": kind,
            "message": f"O*NET API returned HTTP {exc.code}.",
        }
    except urllib.error.URLError as exc:
        return {
            "error": "onet_network_error",
            "error_kind": ERR_TRANSIENT,
            "message": f"Could not reach O*NET: {exc.reason}",
        }
    except Exception as exc:
        logger.exception("onet_search_careers failed")
        return {
            "error": "onet_unknown",
            "error_kind": ERR_TRANSIENT,
            "message": str(exc),
        }


@tool
def onet_career_detail(soc_code: str, sections: list[str]) -> dict[str, Any]:
    """Fetch authoritative O*NET data for a specific career.

    ``sections`` is REQUIRED — pick only what you need to avoid bloating
    context. Valid sections: "knowledge", "skills", "abilities",
    "personality", "technology", "education", "job_outlook",
    "check_out_my_state", "explore_more". The overview (code, title,
    what_they_do, on_the_job) is always included.

    Args:
        soc_code: O*NET SOC code like "15-1252.00" (obtain via onet_search_careers).
        sections: Explicit non-empty list of section names from the list above.

    Returns:
        Dict with overview fields plus one key per requested section, or
        an error dict with ``error_kind``.
    """
    if not soc_code or not _ONET_SOC_PATTERN.match(soc_code.strip()):
        return {
            "error": "invalid_soc_code",
            "error_kind": ERR_VALIDATION,
            "message": (
                "soc_code must match the pattern '##-####.##' "
                "(e.g. '15-1252.00')."
            ),
        }

    if not sections or not isinstance(sections, list):
        return {
            "error": "missing_sections",
            "error_kind": ERR_VALIDATION,
            "message": (
                "sections must be a non-empty list. Valid names: "
                + ", ".join(sorted(ONET_VALID_SECTIONS))
            ),
        }

    unknown = [s for s in sections if s not in ONET_VALID_SECTIONS]
    if unknown:
        return {
            "error": "unknown_section",
            "error_kind": ERR_VALIDATION,
            "message": (
                f"Unknown section(s): {unknown}. Valid names: "
                + ", ".join(sorted(ONET_VALID_SECTIONS))
            ),
        }

    from backend.handlers.onet import service as _onet_service  # lazy import

    code = soc_code.strip()
    try:
        base_path = f"/careers/{code}"
        result = dict(_onet_service._onet_request(f"{base_path}/"))
        for section in sections:
            try:
                result[section] = _onet_service._onet_request(
                    f"{base_path}/{section}"
                )
            except urllib.error.HTTPError as exc:
                logger.warning(
                    "onet_career_detail: section %s HTTP %s for %s",
                    section, exc.code, code,
                )
                result[section] = None
        return result
    except urllib.error.HTTPError as exc:
        kind = ERR_NOT_FOUND if exc.code == 404 else (
            ERR_PERMANENT if 400 <= exc.code < 500 else ERR_TRANSIENT
        )
        return {
            "error": "onet_http_error",
            "error_kind": kind,
            "message": f"O*NET API returned HTTP {exc.code} for {code}.",
        }
    except urllib.error.URLError as exc:
        return {
            "error": "onet_network_error",
            "error_kind": ERR_TRANSIENT,
            "message": f"Could not reach O*NET: {exc.reason}",
        }
    except Exception as exc:
        logger.exception("onet_career_detail failed")
        return {
            "error": "onet_unknown",
            "error_kind": ERR_TRANSIENT,
            "message": str(exc),
        }
