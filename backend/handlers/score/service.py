"""Impact Scorecard computation service.

Computes the Composite Readiness Index (CRI) and its five constituent
dimension scores from existing REGAIN data:

1. Mission Velocity (MVS) — completion rate, category balance, trend
2. Evidence Density (EDS) — coverage, richness, skill breadth
3. Market Alignment (MAS) — cosine similarity vs O*NET target role
4. Phase Progression (PPS) — campaign phase advancement
5. Adaptive Difficulty (ADS) — difficulty trajectory over time

All scores are 0-100. CRI is a weighted composite:
  CRI = 0.20*MVS + 0.30*EDS + 0.25*MAS + 0.15*PPS + 0.10*ADS
"""

from __future__ import annotations

import math
import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from boto3.dynamodb.conditions import Key

logger = logging.getLogger(__name__)

# CRI dimension weights
W_MVS = 0.20
W_EDS = 0.30
W_MAS = 0.25
W_PPS = 0.15
W_ADS = 0.10

# Phase index mapping
_PHASE_INDEX: dict[str, int] = {
    "foundation": 1,
    "momentum": 2,
    "expansion": 2,
    "acceleration": 2,
    "launch": 3,
    "transition": 3,
    "complete": 4,
}

# Evidence half-life in days for recency weighting
_HALF_LIFE_DAYS = 30.0

# Target daily completion rate (missions per day)
_TARGET_DAILY_RATE = 1.0


def _sigmoid(x: float) -> float:
    """Sigmoid function clamped to avoid overflow."""
    clamped = max(-10.0, min(10.0, x))
    return 1.0 / (1.0 + math.exp(-clamped))


def _recency_weight(created_at: str, now: datetime) -> float:
    """Compute a 30-day half-life recency weight for a timestamp."""
    try:
        dt = datetime.fromisoformat(created_at)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        days = max(0, (now - dt).total_seconds() / 86400)
        return 0.5 ** (days / _HALF_LIFE_DAYS)
    except (ValueError, TypeError):
        return 0.5


def _cosine_similarity(vec_a: dict[str, float], vec_b: dict[str, float]) -> float:
    """Compute cosine similarity between two sparse vectors."""
    all_keys = set(vec_a) | set(vec_b)
    if not all_keys:
        return 0.0
    dot = sum(vec_a.get(k, 0.0) * vec_b.get(k, 0.0) for k in all_keys)
    mag_a = math.sqrt(sum(v ** 2 for v in vec_a.values()))
    mag_b = math.sqrt(sum(v ** 2 for v in vec_b.values()))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def _linear_regression_slope(points: list[tuple[float, float]]) -> float:
    """Compute the slope of a simple linear regression on (x, y) points."""
    n = len(points)
    if n < 2:
        return 0.0
    sum_x = sum(p[0] for p in points)
    sum_y = sum(p[1] for p in points)
    sum_xy = sum(p[0] * p[1] for p in points)
    sum_x2 = sum(p[0] ** 2 for p in points)
    denom = n * sum_x2 - sum_x ** 2
    if abs(denom) < 1e-10:
        return 0.0
    return (n * sum_xy - sum_x * sum_y) / denom


class ScoreService:
    """Computes Impact Scorecard dimensions and CRI."""

    def __init__(self, db_client: Any = None) -> None:
        if db_client is None:
            import importlib
            _mod = importlib.import_module("backend.handlers.shared.dynamodb")
            db_client = _mod.DynamoDBClient()
        self.db = db_client

    def compute_scorecard(self, user_id: str) -> dict[str, Any]:
        """Compute full scorecard for a user.

        Returns a dict with cri, all 5 dimension scores, dimension detail,
        and metadata (evidence count, missions completed, computed timestamp).
        """
        now = datetime.now(timezone.utc)

        # Fetch all needed data
        profile = self.db.get_item("user_profiles", {"userId": user_id}) or {}
        campaigns = self.db.query(
            "campaigns",
            Key("userId").eq(user_id),
        )
        active_campaign = next(
            (c for c in campaigns if c.get("status") == "active"), None
        )
        missions = self.db.query_all(
            "mission_history",
            key_condition=Key("userId").eq(user_id),
        )
        evidence = self.db.query_all(
            "evidence_vault",
            key_condition=Key("userId").eq(user_id),
        )

        # Market data for the user's target role
        target_role = (
            (active_campaign or {}).get("targetRole")
            or profile.get("targetRole", "")
        )
        market_data = self._fetch_market_data(target_role)

        completed = [m for m in missions if m.get("status") == "completed"]

        # Compute dimensions
        mvs, mvs_detail = self._compute_mission_velocity(completed, now)
        eds, eds_detail = self._compute_evidence_density(completed, evidence, now)
        mas, mas_detail = self._compute_market_alignment(
            evidence, market_data, target_role, now,
        )
        pps, pps_detail = self._compute_phase_progression(active_campaign, completed)
        ads, ads_detail = self._compute_adaptive_difficulty(completed, now)

        # Amplifiers
        eds_amplified = eds
        if ads_detail.get("peak_difficulty_avg", 0) >= 4:
            eds_amplified = min(100.0, eds * 1.05)

        mas_amplified = mas
        if mas_detail.get("demand_multiplier", 1.0) > 1.15:
            mas_amplified = min(100.0, mas * 1.10)

        # Composite
        cri = (
            W_MVS * mvs
            + W_EDS * eds_amplified
            + W_MAS * mas_amplified
            + W_PPS * pps
            + W_ADS * ads
        )
        cri = round(min(100.0, max(0.0, cri)), 1)

        return {
            "cri": cri,
            "missionVelocityScore": round(mvs, 1),
            "evidenceDensityScore": round(eds, 1),
            "marketAlignmentScore": round(mas, 1),
            "phaseProgressionScore": round(pps, 1),
            "adaptiveDifficultyScore": round(ads, 1),
            "dimensionDetail": {
                "missionVelocity": mvs_detail,
                "evidenceDensity": eds_detail,
                "marketAlignment": mas_detail,
                "phaseProgression": pps_detail,
                "adaptiveDifficulty": ads_detail,
            },
            "evidenceCount": len(evidence),
            "missionsCompleted": len(completed),
            "targetRole": target_role,
            "computedAt": now.isoformat(),
        }

    def _fetch_market_data(self, target_role: str) -> dict[str, Any]:
        """Fetch market data for the user's target role."""
        if not target_role:
            return {}
        try:
            items = self.db.query(
                "market_data",
                Key("roleTitle").eq(target_role),
                index_name="role-title-index",
            )
            return items[0] if items else {}
        except Exception:
            logger.warning("Market data lookup failed for role=%s", target_role)
            return {}

    def _compute_mission_velocity(
        self,
        completed: list[dict[str, Any]],
        now: datetime,
    ) -> tuple[float, dict[str, Any]]:
        """Compute Mission Velocity Score (MVS).

        Sub-signals: WCR (weekly completion rate), CDS (category distribution),
        VT (velocity trend).
        """
        if not completed:
            return 0.0, {"wcr": 0, "cds": 0, "velocityTrend": 0, "totalCompleted": 0}

        # Count completions in last 7 days and prior 7 days
        seven_days_ago = now - timedelta(days=7)
        fourteen_days_ago = now - timedelta(days=14)

        last_7 = 0
        prior_7 = 0
        category_counts: dict[str, int] = {}

        for m in completed:
            ts_str = m.get("completedAt") or m.get("completedDate", "")
            category = m.get("category", "general")
            category_counts[category] = category_counts.get(category, 0) + 1

            if not ts_str:
                continue
            try:
                ts = datetime.fromisoformat(ts_str)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if ts >= seven_days_ago:
                    last_7 += 1
                elif ts >= fourteen_days_ago:
                    prior_7 += 1
            except (ValueError, TypeError):
                continue

        # WCR: normalized against target of 1/day (7/week)
        wcr = min(1.0, (last_7 / 7) / _TARGET_DAILY_RATE)

        # CDS: category balance via coefficient of variation
        counts = list(category_counts.values())
        if len(counts) >= 2:
            mean_c = sum(counts) / len(counts)
            std_c = math.sqrt(sum((c - mean_c) ** 2 for c in counts) / len(counts))
            cds = max(0.0, 1.0 - (std_c / mean_c)) if mean_c > 0 else 0.0
        elif len(counts) == 1:
            cds = 0.2  # single category gets a low balance score
        else:
            cds = 0.0

        # VT: velocity trend (sigmoid-capped)
        if prior_7 > 0:
            vt_raw = (last_7 - prior_7) / max(prior_7, 0.01)
        else:
            vt_raw = 1.0 if last_7 > 0 else 0.0
        vt = _sigmoid(vt_raw)

        mvs = (0.5 * wcr + 0.3 * cds + 0.2 * vt) * 100
        mvs = min(100.0, max(0.0, mvs))

        return mvs, {
            "wcr": round(wcr, 3),
            "cds": round(cds, 3),
            "velocityTrend": round(vt_raw, 3),
            "categoryBreakdown": category_counts,
            "last7d": last_7,
            "prior7d": prior_7,
            "totalCompleted": len(completed),
        }

    def _compute_evidence_density(
        self,
        completed: list[dict[str, Any]],
        evidence: list[dict[str, Any]],
        now: datetime,
    ) -> tuple[float, dict[str, Any]]:
        """Compute Evidence Density Score (EDS).

        Sub-signals: ECR (coverage ratio), ERS (richness), STB (skill breadth).
        """
        if not completed or not evidence:
            return 0.0, {
                "ecr": 0, "ers": 0, "stb": 0,
                "uniqueSkills": 0, "totalEntries": 0,
            }

        # ECR: missions with at least one evidence entry
        mission_ids_with_evidence = {e.get("missionId") for e in evidence if e.get("missionId")}
        completed_ids = {m.get("missionId") for m in completed if m.get("missionId")}
        covered = len(completed_ids & mission_ids_with_evidence)
        ecr = covered / len(completed_ids) if completed_ids else 0.0

        # ERS: evidence richness with recency weighting
        richness_scores: list[float] = []
        skill_tags: set[str] = set()
        skills_by_entry: dict[str, list[str]] = {}

        for e in evidence:
            wc = int(e.get("wordCount") or len(e.get("reflection", "").split()))
            has_artifact = 1.3 if e.get("artifactUrl") else 1.0
            length_factor = min(1.0, wc / 150)
            recency = _recency_weight(e.get("createdAt", ""), now)
            richness = length_factor * has_artifact * recency
            richness_scores.append(richness)

            tag = e.get("skillTag", "")
            if tag:
                skill_tags.add(tag)
            eid = e.get("evidenceId", "")
            if eid and tag:
                skills_by_entry[eid] = [tag]

        ers = sum(richness_scores) / len(richness_scores) if richness_scores else 0.0

        # STB: skill tag breadth
        stb = len(skill_tags) / len(evidence) if evidence else 0.0
        stb = min(1.0, stb)

        eds = (0.4 * ecr + 0.4 * ers + 0.2 * stb) * 100
        eds = min(100.0, max(0.0, eds))

        # Skill detail for constellation
        skill_counts: dict[str, int] = {}
        skill_last_date: dict[str, str] = {}
        for e in evidence:
            tag = e.get("skillTag", "")
            if not tag:
                continue
            skill_counts[tag] = skill_counts.get(tag, 0) + 1
            created = e.get("createdAt", "")
            if created > skill_last_date.get(tag, ""):
                skill_last_date[tag] = created

        return eds, {
            "ecr": round(ecr, 3),
            "ers": round(ers, 3),
            "stb": round(stb, 3),
            "uniqueSkills": len(skill_tags),
            "totalEntries": len(evidence),
            "skillDetail": [
                {
                    "skill": skill,
                    "count": skill_counts[skill],
                    "lastDate": skill_last_date.get(skill, ""),
                }
                for skill in sorted(skill_counts, key=lambda s: -skill_counts[s])
            ],
        }

    def _compute_market_alignment(
        self,
        evidence: list[dict[str, Any]],
        market_data: dict[str, Any],
        target_role: str,
        now: datetime,
    ) -> tuple[float, dict[str, Any]]:
        """Compute Market Alignment Score (MAS) via cosine similarity."""
        if not market_data or not evidence:
            detail: dict[str, Any] = {
                "cosine": 0, "demandMultiplier": 1.0,
                "matchedSkills": 0, "totalTargetSkills": 0,
                "hotSkillsGap": [], "hasMarketData": bool(market_data),
            }
            return 0.0, detail

        # Build target role skill vector from market data
        skills_list = (
            market_data.get("required_skills")
            or market_data.get("topSkills")
            or []
        )
        target_vector: dict[str, float] = {}
        for s in skills_list:
            name = s.get("skill", "")
            demand = s.get("demand") or s.get("frequency", 1.0)
            weight = float(demand) / 100.0 if float(demand) > 1.0 else float(demand)
            if name:
                target_vector[name.lower()] = weight

        if not target_vector:
            return 0.0, {
                "cosine": 0, "demandMultiplier": 1.0,
                "matchedSkills": 0, "totalTargetSkills": 0,
                "hotSkillsGap": [], "hasMarketData": True,
            }

        # Build user skill vector from evidence with recency weighting
        user_vector: dict[str, float] = {}
        for e in evidence:
            tag = (e.get("skillTag") or "").lower()
            if not tag:
                continue
            recency = _recency_weight(e.get("createdAt", ""), now)
            user_vector[tag] = user_vector.get(tag, 0.0) + recency

        # Cosine similarity
        cos_sim = _cosine_similarity(target_vector, user_vector)

        # Demand multiplier from posting volume
        posting_volume = int(market_data.get("posting_volume") or market_data.get("postingVolume", 0))
        dm = min(1.2, 1.0 + (posting_volume / 10000.0)) if posting_volume > 0 else 1.0

        mas = 100.0 * cos_sim * dm
        mas = min(100.0, max(0.0, mas))

        # Hot skills gap: top 3 target skills where user has least evidence
        gaps: list[dict[str, Any]] = []
        for skill, weight in sorted(target_vector.items(), key=lambda x: -x[1]):
            user_weight = user_vector.get(skill, 0.0)
            gap = weight - user_weight
            if gap > 0:
                gaps.append({"skill": skill, "gap": round(gap, 3), "demand": round(weight, 3)})
        hot_gaps = gaps[:3]

        matched = len(set(target_vector) & set(user_vector))

        return mas, {
            "cosine": round(cos_sim, 3),
            "demandMultiplier": round(dm, 3),
            "matchedSkills": matched,
            "totalTargetSkills": len(target_vector),
            "hotSkillsGap": hot_gaps,
            "hasMarketData": True,
            "targetRole": target_role,
        }

    def _compute_phase_progression(
        self,
        campaign: dict[str, Any] | None,
        completed: list[dict[str, Any]],
    ) -> tuple[float, dict[str, Any]]:
        """Compute Phase Progression Score (PPS)."""
        if not campaign:
            return 0.0, {"phase": "none", "phaseIndex": 0, "gatesMet": {}}

        phase = campaign.get("phase", "foundation")
        idx = _PHASE_INDEX.get(phase.lower(), 1)
        pps = (idx / 4) * 100

        # Gate criteria tracking
        total = len(completed)
        gates: dict[str, dict[str, Any]] = {
            "foundation_to_expansion": {
                "required": 10,
                "current": min(total, 10),
                "met": total >= 10,
            },
            "expansion_to_launch": {
                "required": 20,
                "current": min(total, 20),
                "met": total >= 20,
            },
            "launch_to_complete": {
                "required": 30,
                "current": min(total, 30),
                "met": total >= 30,
            },
        }

        return pps, {
            "phase": phase,
            "phaseIndex": idx,
            "gatesMet": gates,
            "startDate": campaign.get("startDate", ""),
        }

    def _compute_adaptive_difficulty(
        self,
        completed: list[dict[str, Any]],
        now: datetime,
    ) -> tuple[float, dict[str, Any]]:
        """Compute Adaptive Difficulty Score (ADS).

        Sub-signals: AR (adaptation rate via regression slope), DC (difficulty ceiling).
        """
        if not completed:
            return 0.0, {
                "adaptationRates": {},
                "difficultyCeilings": {},
                "peak_difficulty_avg": 0,
            }

        # Group missions by category with (days_since_start, difficulty)
        category_points: dict[str, list[tuple[float, float]]] = {}
        category_ceilings: dict[str, int] = {}

        # Find earliest completion for x-axis normalization
        earliest = now
        for m in completed:
            ts_str = m.get("completedAt") or m.get("completedDate", "")
            if ts_str:
                try:
                    ts = datetime.fromisoformat(ts_str)
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    if ts < earliest:
                        earliest = ts
                except (ValueError, TypeError):
                    pass

        for m in completed:
            category = m.get("category", "")
            difficulty = m.get("difficulty")
            if not category or difficulty is None:
                continue
            difficulty = int(difficulty)

            ts_str = m.get("completedAt") or m.get("completedDate", "")
            if not ts_str:
                continue
            try:
                ts = datetime.fromisoformat(ts_str)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                days = (ts - earliest).total_seconds() / 86400
            except (ValueError, TypeError):
                continue

            category_points.setdefault(category, []).append((days, float(difficulty)))
            current_max = category_ceilings.get(category, 0)
            if difficulty > current_max:
                category_ceilings[category] = difficulty

        if not category_points:
            return 0.0, {
                "adaptationRates": {},
                "difficultyCeilings": {},
                "peak_difficulty_avg": 0,
            }

        # AR: regression slope per category, normalized to 0-1
        adaptation_rates: dict[str, float] = {}
        for cat, points in category_points.items():
            slope = _linear_regression_slope(points)
            # Normalize: a slope of 0.1 difficulty/day over 30 days = ~3 levels = strong
            adaptation_rates[cat] = min(1.0, max(0.0, slope * 10))

        # DC: difficulty ceiling per category, normalized to 0-1
        ceilings_normalized: dict[str, float] = {
            cat: ceiling / 5.0 for cat, ceiling in category_ceilings.items()
        }

        # ADS: mean of (AR*50 + DC*50) across categories
        scores: list[float] = []
        all_cats = set(adaptation_rates) | set(ceilings_normalized)
        for cat in all_cats:
            ar = adaptation_rates.get(cat, 0.0)
            dc = ceilings_normalized.get(cat, 0.0)
            scores.append(ar * 50 + dc * 50)

        ads = sum(scores) / len(scores) if scores else 0.0
        ads = min(100.0, max(0.0, ads))

        peak_avg = (
            sum(category_ceilings.values()) / len(category_ceilings)
            if category_ceilings
            else 0
        )

        # Difficulty history for frontend chart
        history_by_category: dict[str, list[dict[str, Any]]] = {}
        for cat, points in category_points.items():
            history_by_category[cat] = [
                {"day": round(p[0], 1), "difficulty": int(p[1])}
                for p in sorted(points, key=lambda x: x[0])
            ]

        return ads, {
            "adaptationRates": {k: round(v, 3) for k, v in adaptation_rates.items()},
            "difficultyCeilings": category_ceilings,
            "peak_difficulty_avg": round(peak_avg, 1),
            "historyByCategory": history_by_category,
        }
