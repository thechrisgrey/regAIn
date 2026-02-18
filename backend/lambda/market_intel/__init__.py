"""Market Intelligence System — public API.

Exposes functions for the Coaching Agent and Mission Engine to retrieve
demand scores, calculate alignment, query insights, normalize skills,
and get role skill requirements. All reads come from DynamoDB — external
APIs are never called from these functions.

Requirements: 10.1, 10.2, 10.3, 10.4, 10.5
"""

from __future__ import annotations

import importlib
import logging
from typing import Any, Optional

from boto3.dynamodb.conditions import Key

logger = logging.getLogger(__name__)

# Sibling imports via importlib ('lambda' is a Python keyword in the path).
_alignment_mod = importlib.import_module("backend.lambda.market_intel.alignment")
_insights_mod = importlib.import_module("backend.lambda.market_intel.insights")
_taxonomy_mod = importlib.import_module("backend.lambda.market_intel.taxonomy")
_dynamodb_mod = importlib.import_module("backend.lambda.shared.dynamodb")
DynamoDBClient = _dynamodb_mod.DynamoDBClient


def get_demand_score(role_id: str) -> dict[str, Any] | None:
    """Retrieve the latest demand score record for a role.

    Queries the MarketData table by sector="role:{role_id}" and returns
    the most recent record's scoring fields.

    Args:
        role_id: Role identifier without the "role:" prefix.

    Returns:
        Dict with demand_score, trend_direction, growth_rate, top_skills,
        and salary_range — or None if no data exists for the role.
    """
    try:
        db = DynamoDBClient()
        items = db.query(
            "market_data",
            Key("sector").eq(f"role:{role_id}"),
        )
    except Exception:
        logger.exception("Failed to query demand score for role %s", role_id)
        return None

    if not items:
        return None

    latest = sorted(items, key=lambda i: i.get("timestamp", ""))[-1]

    return {
        "role_id": role_id,
        "demand_score": int(latest.get("demandScore", 0)),
        "trend_direction": latest.get("trendDirection", "stable"),
        "growth_rate": float(latest.get("growthRate", 0.0)),
        "top_skills": latest.get("topSkills", []),
        "salary_range": latest.get("salaryRange", {}),
        "posting_volume": int(latest.get("postingVolume", 0)),
        "projection": latest.get("projection", ""),
        "source": latest.get("source", ""),
        "timestamp": latest.get("timestamp", ""),
    }


def calculate_alignment(user_id: str, target_role_id: str) -> dict[str, Any]:
    """Calculate user-to-market alignment for a target role.

    Delegates to the alignment module which reads user skills, evidence,
    and role requirements from DynamoDB.

    Args:
        user_id: The user whose skills are evaluated.
        target_role_id: Role identifier without the "role:" prefix.

    Returns:
        Dict with alignment_pct, skill_breakdown, top_gaps,
        top_strengths, target_role_id, user_id, and calculated_at.
    """
    result = _alignment_mod.calculate_alignment(user_id, target_role_id)
    return {
        "alignment_pct": result.alignment_pct,
        "skill_breakdown": result.skill_breakdown,
        "top_gaps": result.top_gaps,
        "top_strengths": result.top_strengths,
        "target_role_id": result.target_role_id,
        "user_id": result.user_id,
        "calculated_at": result.calculated_at,
    }


def get_insights(
    role_id: Optional[str] = None,
    user_id: Optional[str] = None,
    insight_type: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Query market insights filtered by role, user, or type.

    Delegates to the insights module which reads from DynamoDB.

    Args:
        role_id: Filter by role identifier (without "role:" prefix).
        user_id: Filter by user identifier.
        insight_type: Filter by insight type string.

    Returns:
        List of insight dicts matching the filters. Empty list on
        error or no matches.
    """
    return _insights_mod.get_insights(
        role_id=role_id,
        user_id=user_id,
        insight_type=insight_type,
    )


def normalize_skill(skill_string: str) -> str | None:
    """Normalize a skill string to a canonical skill name.

    Delegates to the taxonomy module for case-insensitive alias lookup.

    Args:
        skill_string: Raw skill string from any source.

    Returns:
        Canonical skill name, or None if no match found.
    """
    return _taxonomy_mod.normalize_skill(skill_string)


def get_role_skills(role_id: str) -> list[dict[str, Any]]:
    """Get the ranked skill requirements for a role.

    Queries the MarketData table for the latest record and returns
    the top_skills list sorted by frequency descending.

    Args:
        role_id: Role identifier without the "role:" prefix.

    Returns:
        List of skill dicts with skill, frequency, and canonical keys.
        Empty list if no data exists for the role.
    """
    try:
        db = DynamoDBClient()
        items = db.query(
            "market_data",
            Key("sector").eq(f"role:{role_id}"),
        )
    except Exception:
        logger.exception("Failed to query role skills for %s", role_id)
        return []

    if not items:
        return []

    latest = sorted(items, key=lambda i: i.get("timestamp", ""))[-1]
    top_skills = latest.get("topSkills", [])

    return sorted(top_skills, key=lambda s: s.get("frequency", 0), reverse=True)
