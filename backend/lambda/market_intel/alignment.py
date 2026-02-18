"""User-to-market alignment calculation.

Compares a user's demonstrated skills against a target role's market
requirements to produce a weighted alignment percentage, per-skill
breakdown, and ranked gaps/strengths.
"""

import importlib
import logging
from datetime import datetime, timezone
from typing import Optional

from boto3.dynamodb.conditions import Key

logger = logging.getLogger(__name__)

_models_mod = importlib.import_module("backend.lambda.market_intel.models")
AlignmentResult = _models_mod.AlignmentResult

_taxonomy_mod = importlib.import_module("backend.lambda.market_intel.taxonomy")
normalize_skill = _taxonomy_mod.normalize_skill

_dynamodb_mod = importlib.import_module("backend.lambda.shared.dynamodb")
DynamoDBClient = _dynamodb_mod.DynamoDBClient


def compute_evidence_strength(
    has_skill: bool,
    evidence_count: int,
    has_recent_evidence: bool,
) -> float:
    """Compute an evidence strength score for a single skill.

    Args:
        has_skill: Whether the user claims the skill.
        evidence_count: Number of evidence items for this skill.
        has_recent_evidence: Whether any evidence was created in the
            last 30 days.

    Returns:
        Score from 0.0 to 1.0:
        - 0.0 — user does not have the skill
        - 0.3 — claimed but no evidence
        - 0.6 — 1–2 evidence items (emerging proof)
        - 0.9 — 3+ evidence items, none recent (strong proof)
        - 1.0 — 3+ evidence items with recent activity
    """
    if not has_skill:
        return 0.0
    if evidence_count == 0:
        return 0.3
    if evidence_count <= 2:
        return 0.6
    # evidence_count >= 3
    if has_recent_evidence:
        return 1.0
    return 0.9


def calculate_alignment(
    user_id: str,
    target_role_id: str,
    reference_date: Optional[datetime] = None,
) -> AlignmentResult:
    """Calculate user-to-market alignment for a target role.

    Reads the user's skills from UserProfiles, evidence from
    EvidenceVault, and role requirements from MarketData. All skills
    are normalized through the taxonomy before comparison.

    Args:
        user_id: The user whose skills are evaluated.
        target_role_id: Role identifier (without "role:" prefix).
        reference_date: Optional fixed datetime for "recent" evidence
            calculation. Defaults to now (UTC).

    Returns:
        AlignmentResult with alignment_pct, per-skill breakdown,
        top 3 gaps, and top 3 strengths. Returns 0.0% alignment
        with empty breakdown when the role has no data.
    """
    if reference_date is None:
        reference_date = datetime.now(timezone.utc)

    calculated_at = reference_date.isoformat()

    empty_result = AlignmentResult(
        alignment_pct=0.0,
        skill_breakdown=[],
        top_gaps=[],
        top_strengths=[],
        target_role_id=target_role_id,
        user_id=user_id,
        calculated_at=calculated_at,
    )

    db = DynamoDBClient()

    # --- Fetch role requirements from MarketData ---
    try:
        role_items = db.query(
            "market_data",
            Key("sector").eq(f"role:{target_role_id}"),
        )
    except Exception:
        logger.exception("Failed to query MarketData for role %s", target_role_id)
        return empty_result

    if not role_items:
        return empty_result

    # Use the latest record (highest timestamp)
    latest_record = sorted(role_items, key=lambda r: r.get("timestamp", ""))[-1]
    top_skills = latest_record.get("topSkills", [])

    if not top_skills:
        return empty_result

    # --- Fetch user profile ---
    try:
        user_profile = db.get_item("user_profiles", {"userId": user_id})
    except Exception:
        logger.exception("Failed to get UserProfile for %s", user_id)
        return empty_result

    user_skills_raw: list[str] = []
    if user_profile:
        user_skills_raw = user_profile.get("skills", [])

    # Normalize user skills to canonical names
    user_skills_normalized: set[str] = set()
    for skill_str in user_skills_raw:
        canonical = normalize_skill(skill_str)
        if canonical:
            user_skills_normalized.add(canonical)

    # --- Fetch evidence from EvidenceVault ---
    try:
        evidence_items = db.query(
            "evidence_vault",
            Key("userId").eq(user_id),
        )
    except Exception:
        logger.exception("Failed to query EvidenceVault for %s", user_id)
        evidence_items = []

    # Build a mapping: normalized skill tag → list of evidence items
    evidence_by_skill: dict[str, list[dict]] = {}
    for item in evidence_items:
        tag = item.get("skillTag", "")
        canonical_tag = normalize_skill(tag) if tag else None
        if canonical_tag:
            evidence_by_skill.setdefault(canonical_tag, []).append(item)

    # --- Compute per-skill scores ---
    thirty_days_ago = reference_date.timestamp() - (30 * 24 * 60 * 60)

    skill_breakdown: list[dict] = []
    for skill_entry in top_skills:
        skill_name = skill_entry.get("skill", "")
        frequency = float(skill_entry.get("frequency", 0))
        canonical_name = normalize_skill(skill_name)

        # If normalization fails, use the raw name for display but
        # treat as unmatched for scoring
        display_name = canonical_name or skill_name
        has_skill = canonical_name is not None and canonical_name in user_skills_normalized

        # Gather evidence for this skill
        evidence_list = evidence_by_skill.get(canonical_name, []) if canonical_name else []
        evidence_count = len(evidence_list)

        # Determine recency
        has_recent = False
        for ev in evidence_list:
            created = ev.get("createdAt", "")
            try:
                ev_ts = datetime.fromisoformat(created).timestamp()
                if ev_ts >= thirty_days_ago:
                    has_recent = True
                    break
            except (ValueError, TypeError):
                continue

        user_score = compute_evidence_strength(has_skill, evidence_count, has_recent)
        market_weight = frequency / 100.0
        gap = market_weight * (1.0 - user_score)

        skill_breakdown.append({
            "skill": display_name,
            "user_score": user_score,
            "market_weight": market_weight,
            "gap": gap,
        })

    # --- Compute alignment percentage ---
    total_weighted_score = sum(s["user_score"] * s["market_weight"] for s in skill_breakdown)
    total_weight = sum(s["market_weight"] for s in skill_breakdown)

    if total_weight > 0:
        alignment_pct = (total_weighted_score / total_weight) * 100.0
    else:
        alignment_pct = 0.0

    # --- Rank gaps and strengths ---
    sorted_by_gap = sorted(
        skill_breakdown,
        key=lambda s: s["market_weight"] * (1.0 - s["user_score"]),
        reverse=True,
    )
    top_gaps = sorted_by_gap[:3]

    sorted_by_strength = sorted(
        skill_breakdown,
        key=lambda s: s["market_weight"] * s["user_score"],
        reverse=True,
    )
    top_strengths = sorted_by_strength[:3]

    return AlignmentResult(
        alignment_pct=alignment_pct,
        skill_breakdown=skill_breakdown,
        top_gaps=top_gaps,
        top_strengths=top_strengths,
        target_role_id=target_role_id,
        user_id=user_id,
        calculated_at=calculated_at,
    )
