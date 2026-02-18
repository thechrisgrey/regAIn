"""Insight generation for the Market Intelligence System.

Generates structured MarketInsight objects with templates and data
payloads for five insight types: role_trend, alignment, gap_opportunity,
emerging_role, and milestone. The Coaching Agent consumes these to
deliver personalized, data-driven guidance.
"""

import importlib
import logging
from datetime import datetime, timezone
from typing import Optional

from boto3.dynamodb.conditions import Attr, Key

logger = logging.getLogger(__name__)

_models_mod = importlib.import_module("backend.lambda.market_intel.models")
MarketDataRecord = _models_mod.MarketDataRecord
AlignmentResult = _models_mod.AlignmentResult
MarketInsight = _models_mod.MarketInsight

_dynamodb_mod = importlib.import_module("backend.lambda.shared.dynamodb")
DynamoDBClient = _dynamodb_mod.DynamoDBClient


INSIGHT_TEMPLATES: dict[str, str] = {
    "role_trend": (
        "{role_title} roles are {trend_direction} — {growth_rate}% "
        "year-over-year. Demand score: {demand_score}/100."
    ),
    "alignment": (
        "Your skill overlap with {role_title} is {alignment_pct}%. "
        "Strongest matches: {top_strengths}. Biggest gaps: {top_gaps}."
    ),
    "gap_opportunity": (
        "The skill '{skill_name}' appears in {frequency}% of "
        "{role_title} postings but you have {evidence_count} evidence "
        "items. Tomorrow's mission targets this."
    ),
    "emerging_role": (
        "{role_title} is a new high-demand role (demand score "
        "{demand_score}) that overlaps {alignment_pct}% with your "
        "current skills. Worth exploring?"
    ),
    "milestone": (
        "Your market alignment increased from {previous_pct}% to "
        "{current_pct}% this week. You closed gaps in {skills_improved}."
    ),
}


def generate_role_trend_insight(record: MarketDataRecord) -> MarketInsight:
    """Generate a role trend insight from a market data record.

    Args:
        record: A MarketDataRecord with demand score and growth data.

    Returns:
        MarketInsight with type "role_trend" and populated data_payload.
    """
    role_id = record.sector.removeprefix("role:")

    data_payload = {
        "role_title": record.role_title,
        "trend_direction": record.trend_direction,
        "growth_rate": record.growth_rate,
        "demand_score": record.demand_score,
    }

    return MarketInsight(
        type="role_trend",
        role_id=role_id,
        message_template=INSIGHT_TEMPLATES["role_trend"],
        data_payload=data_payload,
        generated_date=datetime.now(timezone.utc).isoformat(),
        shown=False,
    )


def generate_alignment_insight(
    alignment: AlignmentResult,
    role_title: str,
) -> MarketInsight:
    """Generate an alignment insight from an alignment result.

    Args:
        alignment: The computed AlignmentResult for a user and role.
        role_title: Human-readable role name for the template.

    Returns:
        MarketInsight with type "alignment" and populated data_payload.
    """
    top_strengths = ", ".join(
        s["skill"] for s in alignment.top_strengths
    ) or "none"
    top_gaps = ", ".join(
        g["skill"] for g in alignment.top_gaps
    ) or "none"

    data_payload = {
        "role_title": role_title,
        "alignment_pct": round(alignment.alignment_pct, 1),
        "top_strengths": top_strengths,
        "top_gaps": top_gaps,
    }

    return MarketInsight(
        type="alignment",
        role_id=alignment.target_role_id,
        message_template=INSIGHT_TEMPLATES["alignment"],
        data_payload=data_payload,
        generated_date=datetime.now(timezone.utc).isoformat(),
        shown=False,
        user_id=alignment.user_id,
    )


def generate_gap_opportunity_insight(
    skill_name: str,
    frequency: float,
    evidence_count: int,
    role_id: str,
    role_title: str,
    user_id: Optional[str] = None,
) -> MarketInsight:
    """Generate a gap opportunity insight for a specific skill.

    Args:
        skill_name: The canonical skill name with a gap.
        frequency: Percentage frequency of this skill in postings.
        evidence_count: Number of evidence items the user has.
        role_id: Target role identifier.
        role_title: Human-readable role name.
        user_id: Optional user identifier for scoping.

    Returns:
        MarketInsight with type "gap_opportunity" and populated
        data_payload.
    """
    data_payload = {
        "skill_name": skill_name,
        "frequency": frequency,
        "role_title": role_title,
        "evidence_count": evidence_count,
    }

    return MarketInsight(
        type="gap_opportunity",
        role_id=role_id,
        message_template=INSIGHT_TEMPLATES["gap_opportunity"],
        data_payload=data_payload,
        generated_date=datetime.now(timezone.utc).isoformat(),
        shown=False,
        user_id=user_id,
    )


def generate_emerging_role_insight(
    record: MarketDataRecord,
    alignment_pct: float,
) -> MarketInsight:
    """Generate an emerging role insight for a high-demand role.

    Args:
        record: A MarketDataRecord for the emerging role.
        alignment_pct: The user's current alignment percentage with
            this role.

    Returns:
        MarketInsight with type "emerging_role" and populated
        data_payload.
    """
    role_id = record.sector.removeprefix("role:")

    data_payload = {
        "role_title": record.role_title,
        "demand_score": record.demand_score,
        "alignment_pct": round(alignment_pct, 1),
    }

    return MarketInsight(
        type="emerging_role",
        role_id=role_id,
        message_template=INSIGHT_TEMPLATES["emerging_role"],
        data_payload=data_payload,
        generated_date=datetime.now(timezone.utc).isoformat(),
        shown=False,
    )


def generate_milestone_insight(
    previous: AlignmentResult,
    current: AlignmentResult,
    role_title: str,
) -> MarketInsight:
    """Generate a milestone insight comparing two alignment results.

    Identifies skills where the user's score improved between the
    previous and current alignment calculations.

    Args:
        previous: The earlier AlignmentResult.
        current: The more recent AlignmentResult.
        role_title: Human-readable role name for the template.

    Returns:
        MarketInsight with type "milestone" and data_payload containing
        previous_pct, current_pct, and skills_improved.
    """
    # Build lookup of previous scores by normalized skill name
    prev_scores: dict[str, float] = {
        entry["skill"].strip(): entry["user_score"]
        for entry in previous.skill_breakdown
    }

    # Find skills where user_score increased
    skills_improved: list[str] = []
    for entry in current.skill_breakdown:
        skill = entry["skill"].strip()
        current_score = entry["user_score"]
        previous_score = prev_scores.get(skill, 0.0)
        if current_score > previous_score:
            skills_improved.append(skill)

    skills_improved_str = ", ".join(skills_improved) or "none"

    data_payload = {
        "previous_pct": round(previous.alignment_pct, 1),
        "current_pct": round(current.alignment_pct, 1),
        "skills_improved": skills_improved_str,
    }

    return MarketInsight(
        type="milestone",
        role_id=current.target_role_id,
        message_template=INSIGHT_TEMPLATES["milestone"],
        data_payload=data_payload,
        generated_date=datetime.now(timezone.utc).isoformat(),
        shown=False,
        user_id=current.user_id,
    )


def get_insights(
    role_id: Optional[str] = None,
    user_id: Optional[str] = None,
    insight_type: Optional[str] = None,
) -> list[dict]:
    """Query market insights from DynamoDB.

    Insights are stored as embedded attributes on MarketData records.
    This function queries by role and filters by user_id and/or
    insight_type as needed.

    Args:
        role_id: Filter by role identifier (without "role:" prefix).
        user_id: Filter by user identifier.
        insight_type: Filter by insight type string.

    Returns:
        List of insight dicts matching the filters. Returns an empty
        list if no matches or on error.
    """
    db = DynamoDBClient()
    insights: list[dict] = []

    try:
        if role_id:
            items = db.query(
                "market_data",
                Key("sector").eq(f"role:{role_id}"),
            )
        else:
            # Without a role_id we cannot do a key-condition query.
            # Scan is acceptable here since insights are few.
            table = db._get_table("market_data")
            response = table.scan()
            items = response.get("Items", [])
    except Exception:
        logger.exception("Failed to query insights")
        return []

    for item in items:
        embedded = item.get("insights", [])
        for ins in embedded:
            if user_id and ins.get("user_id") != user_id:
                continue
            if insight_type and ins.get("type") != insight_type:
                continue
            insights.append(ins)

    return insights
