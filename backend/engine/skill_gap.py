"""Skill gap analysis for the Mission Engine.

Compares a user's demonstrated skills (from EvidenceVault) against target role
requirements (from MarketIntel) to produce per-skill gap scores and an overall
market alignment percentage.
"""

from __future__ import annotations

import importlib
import math
from datetime import datetime, timezone
from typing import Any

from backend.engine.models import SkillGapReport

# 'lambda' is a Python keyword, so we use importlib for the market_intel path.
_market_intel = importlib.import_module("backend.handlers.market_intel")
_normalize_skill = _market_intel.normalize_skill

# Evidence items needed for a full score on a skill.
EVIDENCE_THRESHOLD = 3

# Recency half-life in days — evidence weight halves every 90 days.
RECENCY_HALF_LIFE_DAYS = 90


def _recency_weight(evidence_date: str, reference_date: datetime) -> float:
    """Compute a recency decay weight for a single evidence record.

    Weight = 0.5 ^ (age_days / RECENCY_HALF_LIFE_DAYS).
    Recent evidence scores close to 1.0; older evidence decays toward 0.

    Args:
        evidence_date: ISO-format timestamp of the evidence record.
        reference_date: The "now" reference point (UTC).

    Returns:
        A float in (0.0, 1.0].
    """
    try:
        ev_dt = datetime.fromisoformat(evidence_date)
        if ev_dt.tzinfo is None:
            ev_dt = ev_dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        # Unparseable date — treat as very old evidence.
        return 0.0

    age_days = max(0.0, (reference_date - ev_dt).total_seconds() / 86400)
    return math.pow(0.5, age_days / RECENCY_HALF_LIFE_DAYS)


def _compute_skill_score(
    evidence_records: list[dict[str, Any]],
    reference_date: datetime,
) -> float:
    """Compute a single skill's evidence score.

    score = min(1.0, sum(recency_weight_i) / EVIDENCE_THRESHOLD)

    Args:
        evidence_records: Evidence dicts, each expected to have a "date" or
            "completedAt" key with an ISO timestamp.
        reference_date: The "now" reference point (UTC).

    Returns:
        A float between 0.0 and 1.0 inclusive.
    """
    if not evidence_records:
        return 0.0

    total_weight = 0.0
    for record in evidence_records:
        date_str = record.get("date") or record.get("completedAt") or ""
        total_weight += _recency_weight(date_str, reference_date)

    return min(1.0, total_weight / EVIDENCE_THRESHOLD)


def analyze_skill_gaps(
    user_skills: list[str],
    evidence_by_skill: dict[str, list[dict[str, Any]]],
    target_requirements: list[dict[str, Any]],
    market_demand: dict[str, float],
    reference_date: datetime | None = None,
) -> SkillGapReport:
    """Compare user evidence against target role requirements.

    Args:
        user_skills: Skills from the user's Transition Profile.
        evidence_by_skill: Evidence records grouped by skill tag.
            Each record should contain a "date" or "completedAt" ISO timestamp.
        target_requirements: Required skills with importance weights from
            MarketIntel. Each dict should have at least a "skill" key.
        market_demand: Skill name → demand weight (0.0–1.0).
        reference_date: Optional "now" override for deterministic testing.
            Defaults to UTC now.

    Returns:
        SkillGapReport with per-skill scores, market alignment percentage,
        priority skills sorted by gap × demand descending, and evidence density.
    """
    if reference_date is None:
        reference_date = datetime.now(timezone.utc)

    # Normalize all skill identifiers through the canonical taxonomy so that
    # gap analysis uses the same skill names as market intelligence data.
    user_skills = [_normalize_skill(s) or s for s in user_skills]
    target_requirements = [
        {**req, "skill": _normalize_skill(req.get("skill", "")) or req.get("skill", "")}
        for req in target_requirements
    ]
    market_demand = {
        _normalize_skill(k) or k: v for k, v in market_demand.items()
    }
    evidence_by_skill = {
        _normalize_skill(k) or k: v for k, v in evidence_by_skill.items()
    }

    # Build the set of all skills we care about.
    target_skill_names = {req.get("skill", "") for req in target_requirements}
    all_skills = set(user_skills) | target_skill_names | set(market_demand.keys())
    all_skills.discard("")

    # Compute per-skill scores and evidence density.
    skill_scores: dict[str, float] = {}
    evidence_density: dict[str, int] = {}

    for skill in all_skills:
        records = evidence_by_skill.get(skill, [])
        evidence_density[skill] = len(records)
        skill_scores[skill] = _compute_skill_score(records, reference_date)

    # Market alignment: weighted average of skill scores by demand,
    # considering only skills present in target requirements or market demand.
    target_skills = target_skill_names | set(market_demand.keys())
    target_skills.discard("")

    total_weighted_score = 0.0
    total_demand = 0.0
    for skill in target_skills:
        demand = market_demand.get(skill, 0.0)
        total_weighted_score += skill_scores.get(skill, 0.0) * demand
        total_demand += demand

    if total_demand > 0:
        market_alignment_pct = (total_weighted_score / total_demand) * 100
    else:
        market_alignment_pct = 0.0

    # Priority skills: sorted by gap × demand descending.
    # gap = 1.0 - skill_score (bigger gap = more priority).
    priority_skills = sorted(
        target_skills,
        key=lambda s: (1.0 - skill_scores.get(s, 0.0)) * market_demand.get(s, 0.0),
        reverse=True,
    )

    return SkillGapReport(
        skill_scores=skill_scores,
        market_alignment_pct=market_alignment_pct,
        priority_skills=list(priority_skills),
        evidence_density=evidence_density,
    )
