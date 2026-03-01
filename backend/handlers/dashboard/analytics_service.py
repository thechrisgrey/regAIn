"""Analytics service module.

Aggregates career intelligence data: skill breakdown, activity heatmap,
weekly velocity, campaign ETA, and unevidenced skill gaps.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from boto3.dynamodb.conditions import Attr as boto3_attr, Key

from backend.handlers.shared.dynamodb import DynamoDBClient

logger = logging.getLogger(__name__)

_QUERY_TIMEOUT_SECONDS = 8


class AnalyticsService:
    """Handles analytics aggregation business logic."""

    def __init__(self, db_client: DynamoDBClient | None = None) -> None:
        self.db = db_client or DynamoDBClient()

    def get_analytics(self, user_id: str) -> Dict[str, Any]:
        """Aggregate analytics data for a user.

        Runs 3 parallel DynamoDB queries (missions, evidence, campaigns)
        and computes derived analytics from the results.
        """
        key_condition = Key("userId").eq(user_id)

        with ThreadPoolExecutor(max_workers=3) as executor:
            missions_future = executor.submit(
                self.db.query_all, "mission_history", key_condition
            )
            evidence_future = executor.submit(
                self.db.query_all, "evidence_vault", key_condition
            )
            campaigns_future = executor.submit(
                self.db.query_all, "campaigns", key_condition
            )

            try:
                missions = missions_future.result(timeout=_QUERY_TIMEOUT_SECONDS)
                evidence = evidence_future.result(timeout=_QUERY_TIMEOUT_SECONDS)
                campaigns = campaigns_future.result(timeout=_QUERY_TIMEOUT_SECONDS)
            except FuturesTimeoutError:
                logger.error("Analytics query timed out after %ds", _QUERY_TIMEOUT_SECONDS)
                raise

        active_campaign = next(
            (c for c in campaigns if c.get("status") == "active"), None
        )
        completed_missions = [m for m in missions if m.get("status") == "completed"]

        return {
            "skillBreakdown": self._compute_skill_breakdown(evidence),
            "activityHeatmap": self._compute_activity_heatmap(completed_missions, evidence),
            "velocityTrend": self._compute_velocity_trend(completed_missions),
            "campaignEta": self._compute_campaign_eta(completed_missions, active_campaign),
            "skillSuggestions": self._compute_unevidenced_skills(evidence, active_campaign),
        }

    @staticmethod
    def _compute_skill_breakdown(evidence: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Group evidence by skill tag and compute count + ratio.

        Returns list sorted by frequency (descending).
        """
        counts: Dict[str, int] = {}
        for e in evidence:
            tag = e.get("skillTag", "general")
            counts[tag] = counts.get(tag, 0) + 1

        if not counts:
            return []

        max_count = max(counts.values())
        result = [
            {"skill": skill, "count": count, "ratio": round(count / max_count, 2)}
            for skill, count in counts.items()
        ]
        result.sort(key=lambda x: x["count"], reverse=True)
        return result

    @staticmethod
    def _compute_activity_heatmap(
        missions: List[Dict[str, Any]],
        evidence: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Build a 90-day activity grid with daily counts.

        Counts mission completions + evidence entries per day.
        """
        today = datetime.now(timezone.utc).date()
        start = today - timedelta(days=89)

        day_counts: Dict[str, int] = {}
        for day_offset in range(90):
            d = start + timedelta(days=day_offset)
            day_counts[d.isoformat()] = 0

        for m in missions:
            date_str = m.get("completedDate", "")
            if date_str:
                day_key = date_str[:10]
                if day_key in day_counts:
                    day_counts[day_key] += 1

        for e in evidence:
            date_str = e.get("createdAt", "")
            if date_str:
                day_key = date_str[:10]
                if day_key in day_counts:
                    day_counts[day_key] += 1

        return [
            {"date": date, "count": count}
            for date, count in sorted(day_counts.items())
        ]

    @staticmethod
    def _compute_velocity_trend(
        missions: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Compute 12-week mission completion velocity.

        Returns weekly buckets with start/end dates and completed count.
        """
        today = datetime.now(timezone.utc).date()
        # Start from 11 weeks ago (Monday), so we get 12 full or partial weeks.
        week_start = today - timedelta(days=today.weekday()) - timedelta(weeks=11)

        weeks: List[Dict[str, Any]] = []
        for i in range(12):
            ws = week_start + timedelta(weeks=i)
            we = ws + timedelta(days=6)
            weeks.append({
                "weekStart": ws.isoformat(),
                "weekEnd": we.isoformat(),
                "completed": 0,
            })

        for m in missions:
            date_str = m.get("completedDate", "")
            if not date_str:
                continue
            try:
                d = datetime.fromisoformat(date_str.replace("Z", "+00:00")).date()
            except (ValueError, AttributeError):
                continue
            days_since_start = (d - week_start).days
            if days_since_start < 0:
                continue
            week_index = days_since_start // 7
            if 0 <= week_index < 12:
                weeks[week_index]["completed"] += 1

        return {"weeks": weeks}

    @staticmethod
    def _compute_campaign_eta(
        missions: List[Dict[str, Any]],
        campaign: Dict[str, Any] | None,
    ) -> Dict[str, Any] | None:
        """Estimate days remaining to campaign completion.

        Uses weighted recent velocity (last 14 days = 2x weight).
        """
        if not campaign:
            return None

        skills_focus = campaign.get("skillsFocus", [])
        total_target = max(len(skills_focus) * 5, 20)  # rough target

        completed_count = len(missions)
        if completed_count >= total_target:
            return {
                "estimatedDaysRemaining": 0,
                "completionRate": 1.0,
                "dailyRate": 0,
                "confidence": "high",
            }

        today = datetime.now(timezone.utc).date()
        last_14_days = 0
        prev_14_days = 0

        for m in missions:
            date_str = m.get("completedDate", "")
            if not date_str:
                continue
            try:
                d = datetime.fromisoformat(date_str.replace("Z", "+00:00")).date()
            except (ValueError, AttributeError):
                continue
            delta = (today - d).days
            if delta < 14:
                last_14_days += 1
            elif delta < 28:
                prev_14_days += 1

        # Weighted daily rate: recent 14 days count 2x.
        weighted_total = (last_14_days * 2) + prev_14_days
        weighted_days = (14 * 2) + 14  # 42 weighted days
        daily_rate = weighted_total / weighted_days if weighted_days > 0 else 0

        remaining = max(0, total_target - completed_count)
        estimated_days = round(remaining / daily_rate) if daily_rate > 0 else 999

        completion_rate = round(completed_count / total_target, 2) if total_target > 0 else 0

        if daily_rate >= 0.5:
            confidence = "high"
        elif daily_rate >= 0.2:
            confidence = "medium"
        else:
            confidence = "low"

        return {
            "estimatedDaysRemaining": estimated_days,
            "completionRate": completion_rate,
            "dailyRate": round(daily_rate, 3),
            "confidence": confidence,
        }

    @staticmethod
    def _compute_unevidenced_skills(
        evidence: List[Dict[str, Any]],
        campaign: Dict[str, Any] | None,
    ) -> List[str]:
        """Return campaign skillsFocus skills not yet evidenced."""
        if not campaign:
            return []

        skills_focus = campaign.get("skillsFocus", [])
        if not skills_focus:
            return []

        evidenced_skills = {e.get("skillTag", "").lower() for e in evidence}
        unevidenced = [
            s for s in skills_focus
            if s.lower() not in evidenced_skills
        ]
        return sorted(unevidenced)
