"""Strands tools for the REGAIN Coaching Agent.

Each tool is a pure function decorated with @tool that the Coaching Agent
can invoke during conversation to read or write platform data. Tools use
the shared DynamoDBClient for all data operations and return structured
dicts — never free text.
"""

import dataclasses
import importlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from strands import tool

# 'lambda' is a Python keyword, so we use importlib to load the module.
from boto3.dynamodb.conditions import Attr as boto3_attr, Key

_dynamodb_mod = importlib.import_module("backend.lambda.shared.dynamodb")
DynamoDBClient = _dynamodb_mod.DynamoDBClient

from backend.engine.generator import (
    generate_daily_mission as engine_generate_mission,
    complete_mission as engine_complete_mission,
)
from backend.engine.models import GenerationResult, CompletionResult

logger = logging.getLogger(__name__)

db = DynamoDBClient()


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
                "message": f"No profile found for user '{user_id}'.",
            }
        return item
    except ValueError as exc:
        return {"error": "invalid_input", "message": str(exc)}
    except Exception as exc:
        logger.exception("Failed to read user profile for %s", user_id)
        return {"error": "read_failed", "message": str(exc)}


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
            skills, target_role, persona, onboarding_completed, and any
            Transition Profile fields (transferable_skills, technical_skills,
            domain_knowledge, experience_years, industry, role_history).

    Returns:
        A dict containing the full updated profile (all attributes after
        the update), or an error dict if the update fails.
    """
    if not updates:
        return {"error": "invalid_input", "message": "No updates provided."}

    try:
        response = db.update_item(
            "user_profiles",
            key={"userId": user_id},
            updates=updates,
        )
        return response.get("Attributes", {})
    except ValueError as exc:
        return {"error": "invalid_input", "message": str(exc)}
    except Exception as exc:
        logger.exception("Failed to update user profile for %s", user_id)
        return {"error": "write_failed", "message": str(exc)}


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
                "message": f"No active campaign found for user '{user_id}'.",
            }
        return items[0]
    except ValueError as exc:
        return {"error": "invalid_input", "message": str(exc)}
    except Exception as exc:
        logger.exception("Failed to get campaign status for %s", user_id)
        return {"error": "read_failed", "message": str(exc)}


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
        skills_focus: A list of skill names the campaign will develop.

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
        return {"error": "invalid_input", "message": str(exc)}
    except Exception as exc:
        logger.exception("Failed to create campaign for %s", user_id)
        return {"error": "write_failed", "message": str(exc)}


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
        all_missions = db.query(
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
                "message": f"No pending or in-progress mission for user '{user_id}'.",
                "patterns": patterns,
            }

        mission = current[0]
        mission["patterns"] = patterns
        return mission
    except ValueError as exc:
        return {"error": "invalid_input", "message": str(exc)}
    except Exception as exc:
        logger.exception("Failed to get current mission for %s", user_id)
        return {"error": "read_failed", "message": str(exc)}


@tool
def generate_mission(
    user_id: str,
    campaign_id: str,
) -> dict[str, Any]:
    """Generate a personalized daily mission for a user's reskilling campaign.

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
        (current gap analysis). Returns an error dict if generation fails.
    """
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
        return {"error": "generation_failed", "message": str(exc)}


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
    evidence_id = f"evidence-{uuid.uuid4()}"
    item: dict[str, Any] = {
        "userId": user_id,
        "evidenceId": evidence_id,
        "missionId": mission_id,
        "skillTag": skill_tag,
        "reflection": reflection,
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }
    if artifact_url:
        item["artifactUrl"] = artifact_url

    try:
        db.put_item("evidence_vault", item)

        # Count all evidence for this user + skill_tag
        all_evidence = db.query(
            "evidence_vault",
            key_condition=Key("userId").eq(user_id),
            filter_expression=boto3_attr("skillTag").eq(skill_tag),
        )
        skill_evidence_count = len(all_evidence)

        return {
            "evidence_id": evidence_id,
            "skill_evidence_count": skill_evidence_count,
        }
    except ValueError as exc:
        return {"error": "invalid_input", "message": str(exc)}
    except Exception as exc:
        logger.exception("Failed to log evidence for %s", user_id)
        return {"error": "write_failed", "message": str(exc)}


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
        return completion_dict
    except Exception as exc:
        logger.exception("Failed to complete mission %s for %s", mission_id, user_id)
        return {"error": "completion_failed", "message": str(exc)}


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
        items = db.query(
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
        return {"error": "invalid_input", "message": str(exc)}
    except Exception as exc:
        logger.exception("Failed to get evidence summary for %s", user_id)
        return {"error": "read_failed", "message": str(exc)}


@tool
def get_market_insights(role_id: str) -> dict[str, Any]:
    """Get the latest market intelligence data for a target role.

    Use this tool when you need current demand scores, growth trends,
    in-demand skills, and salary ranges for a specific role. Reference
    this data when coaching users on which skills to prioritize, when
    generating market-aligned missions, or when discussing career
    trajectory and market positioning with the user.

    Args:
        role_id: The role identifier to query (e.g. "ai_qa_engineer",
            "project_manager", "data_analyst").

    Returns:
        A dict with demand_score, trend_direction, growth_rate,
        top_skills, salary_range, and relevant market insights for the
        role — or an error dict if no data is found.
    """
    try:
        _market_intel = importlib.import_module("backend.lambda.market_intel")

        demand = _market_intel.get_demand_score(role_id)
        if demand is None:
            return {
                "error": "not_found",
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
        return {"error": "read_failed", "message": str(exc)}


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
        _market_intel = importlib.import_module("backend.lambda.market_intel")
        return _market_intel.calculate_alignment(user_id, target_role_id)
    except Exception as exc:
        logger.exception(
            "Failed to calculate alignment for user %s, role %s",
            user_id,
            target_role_id,
        )
        return {"error": "alignment_failed", "message": str(exc)}


# ---------------------------------------------------------------------------
# AgentCore Memory tools
# ---------------------------------------------------------------------------

import os
import boto3

_memory_client = None


def _get_memory_client():
    """Lazily initialize the bedrock-agent-runtime boto3 client.

    Returns:
        A boto3 client for bedrock-agent-runtime, or None if creation fails.
    """
    global _memory_client
    if _memory_client is None:
        try:
            region = os.environ.get("AWS_REGION", "us-east-1")
            _memory_client = boto3.client(
                "bedrock-agent-runtime", region_name=region
            )
        except Exception as exc:
            logger.exception("Failed to create bedrock-agent-runtime client")
            return None
    return _memory_client


@tool
def recall_memory(user_id: str, query: str) -> list[dict[str, Any]]:
    """Retrieve relevant past conversation context for a user.

    Use this tool at the start of every coaching session to recall
    prior session summaries, key decisions, and detected patterns.
    Results are ranked by semantic relevance to the query and recency.

    Args:
        user_id: The authenticated user's ID.
        query: A natural-language description of what context to
            retrieve (e.g. "previous coaching session summary",
            "networking avoidance pattern").

    Returns:
        A list of memory entry dicts, each containing content and
        metadata. Returns an empty list if the memory service is
        unavailable or no relevant memories are found.
    """
    namespace = f"regain-coaching-{user_id}"
    memory_id = os.environ.get("AGENTCORE_MEMORY_ID", "")

    client = _get_memory_client()
    if client is None:
        return []

    try:
        response = client.retrieve_memory(
            memoryId=memory_id,
            namespace=namespace,
            query={"text": query},
        )
        entries = response.get("memoryEntries", [])
        return [
            {
                "content": entry.get("content", ""),
                "metadata": entry.get("metadata", {}),
            }
            for entry in entries
        ]
    except Exception as exc:
        logger.warning(
            "AgentCore Memory recall failed for user %s: %s", user_id, exc
        )
        return []


@tool
def store_memory(user_id: str, content: str) -> dict[str, Any]:
    """Store a coaching session summary or key observation for a user.

    Use this tool at the end of every coaching session to persist a
    summary of what was discussed, decisions made, evidence logged,
    missions delivered, and any detected behavioral patterns. This
    enables conversational continuity across sessions.

    Args:
        user_id: The authenticated user's ID.
        content: The text content to store (e.g. a session summary
            or a key coaching observation).

    Returns:
        A confirmation dict with status and namespace on success,
        or a dict with status "unavailable" and a message on failure.
    """
    namespace = f"regain-coaching-{user_id}"
    memory_id = os.environ.get("AGENTCORE_MEMORY_ID", "")
    timestamp = datetime.now(timezone.utc).isoformat()

    client = _get_memory_client()
    if client is None:
        return {
            "status": "unavailable",
            "message": "Memory service client could not be initialized.",
        }

    try:
        client.create_memory(
            memoryId=memory_id,
            namespace=namespace,
            content={"text": content},
            metadata={"timestamp": timestamp, "user_id": user_id},
        )
        return {"status": "stored", "namespace": namespace}
    except Exception as exc:
        logger.warning(
            "AgentCore Memory store failed for user %s: %s", user_id, exc
        )
        return {
            "status": "unavailable",
            "message": f"Memory service unavailable: {exc}",
        }
