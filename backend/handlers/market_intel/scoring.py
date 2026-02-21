"""Demand score calculation for the Market Intelligence System.

Computes composite demand scores (0-100) for tracked roles by combining
posting volume, growth rate, salary signal, and BLS employment projections.
Also provides trend direction labeling and batch recalculation.
"""

import importlib
import logging
from typing import Any

from boto3.dynamodb.conditions import Key

logger = logging.getLogger(__name__)

_dynamodb_mod = importlib.import_module("backend.handlers.shared.dynamodb")
DynamoDBClient = _dynamodb_mod.DynamoDBClient

# BLS projection category → score mapping
_PROJECTION_SCORES: dict[str, int] = {
    "much faster than average": 25,
    "faster than average": 20,
    "average": 15,
    "slower than average": 5,
    "decline": 0,
}


def _percentile_rank(value: float | int, all_values: list[float | int]) -> float:
    """Compute the percentile rank of *value* within *all_values*.

    Args:
        value: The value to rank.
        all_values: The full comparison set (may include *value*).

    Returns:
        Float in [0.0, 1.0]. Returns 0.0 when *all_values* is empty.
    """
    if not all_values:
        return 0.0
    count_below = sum(1 for v in all_values if v < value)
    return count_below / len(all_values)


def _growth_rate_score(growth_rate: float) -> int:
    """Map year-over-year growth rate to a score component (0-30).

    Args:
        growth_rate: YoY growth percentage (e.g. 15.0 means 15%).

    Returns:
        0 for negative, 10 for 0-10%, 20 for 10-20%, 30 for >20%.
    """
    if growth_rate > 20:
        return 30
    if growth_rate >= 10:
        return 20
    if growth_rate >= 0:
        return 10
    return 0


def _projection_score(projection: str) -> int:
    """Map a BLS projection category to a score component (0-25).

    Args:
        projection: BLS projection string (case-insensitive).

    Returns:
        Integer score: 25, 20, 15, 5, or 0. Defaults to 0 for
        unrecognised categories.
    """
    return _PROJECTION_SCORES.get(projection.lower().strip(), 0)


def get_trend_direction(growth_rate: float) -> str:
    """Derive a trend label from year-over-year growth rate.

    Args:
        growth_rate: YoY growth percentage.

    Returns:
        "surging" (>20%), "growing" (5-20%), "stable" (-5% to 5%),
        or "declining" (<-5%).
    """
    if growth_rate > 20:
        return "surging"
    if growth_rate >= 5:
        return "growing"
    if growth_rate >= -5:
        return "stable"
    return "declining"


def calculate_demand_score(
    posting_volume: int,
    growth_rate: float,
    median_salary: int,
    projection: str,
    all_posting_volumes: list[int],
    all_median_salaries: list[int],
    top_skills: list[dict] | None = None,
    salary_range: dict | None = None,
) -> dict[str, Any]:
    """Calculate a composite demand score (0-100) for a role.

    Args:
        posting_volume: Raw posting count for this role.
        growth_rate: Year-over-year growth percentage.
        median_salary: Median salary for this role.
        projection: BLS projection category string.
        all_posting_volumes: Posting volumes for all tracked roles
            (used for percentile ranking).
        all_median_salaries: Median salaries for all tracked roles
            (used for percentile ranking).
        top_skills: Optional list of skill dicts with "skill" and
            "frequency" keys. Returned sorted by frequency descending.
        salary_range: Optional salary range dict with min/median/max/region.

    Returns:
        Dict with keys: demand_score, components, trend_direction,
        top_skills, salary_range.
    """
    posting_component = round(_percentile_rank(posting_volume, all_posting_volumes) * 25)
    growth_component = _growth_rate_score(growth_rate)
    salary_component = round(_percentile_rank(median_salary, all_median_salaries) * 20)
    proj_component = _projection_score(projection)

    demand_score = posting_component + growth_component + salary_component + proj_component

    sorted_skills = sorted(
        top_skills or [],
        key=lambda s: s.get("frequency", 0),
        reverse=True,
    )

    return {
        "demand_score": demand_score,
        "components": {
            "posting_volume": posting_component,
            "growth_rate": growth_component,
            "salary_signal": salary_component,
            "projection": proj_component,
        },
        "trend_direction": get_trend_direction(growth_rate),
        "top_skills": sorted_skills,
        "salary_range": salary_range or {},
    }


def recalculate_scores(role_ids: list[str]) -> dict[str, Any]:
    """Recalculate demand scores for the given roles and persist results.

    Reads current market data from DynamoDB, gathers comparison sets
    across all roles, recalculates each role's score, and writes the
    updated records back.

    Args:
        role_ids: List of role identifiers (without the "role:" prefix).

    Returns:
        Dict with "succeeded" (list of role_ids) and "failed" (list of
        dicts with role_id and error).
    """
    db = DynamoDBClient()
    succeeded: list[str] = []
    failed: list[dict[str, str]] = []

    # Fetch latest record for each role
    records: dict[str, dict[str, Any]] = {}
    for role_id in role_ids:
        try:
            items = db.query(
                "market_data",
                Key("sector").eq(f"role:{role_id}"),
            )
            if items:
                # Use the most recent record (last by sort key)
                latest = sorted(items, key=lambda i: i.get("timestamp", ""))[-1]
                records[role_id] = latest
        except Exception as exc:
            logger.error("Failed to read market data for %s: %s", role_id, exc)
            failed.append({"role_id": role_id, "error": str(exc)})

    # Build comparison sets from all fetched records
    all_posting_volumes = [
        int(r.get("postingVolume", 0)) for r in records.values()
    ]
    all_median_salaries = [
        int(r.get("salaryRange", {}).get("median", 0)) for r in records.values()
    ]

    # Recalculate and write back
    for role_id, item in records.items():
        try:
            result = calculate_demand_score(
                posting_volume=int(item.get("postingVolume", 0)),
                growth_rate=float(item.get("growthRate", 0.0)),
                median_salary=int(item.get("salaryRange", {}).get("median", 0)),
                projection=item.get("projection", ""),
                all_posting_volumes=all_posting_volumes,
                all_median_salaries=all_median_salaries,
                top_skills=item.get("topSkills", []),
                salary_range=item.get("salaryRange", {}),
            )

            db.update_item(
                "market_data",
                key={"sector": item["sector"], "timestamp": item["timestamp"]},
                updates={
                    "demandScore": result["demand_score"],
                    "trendDirection": result["trend_direction"],
                    "topSkills": result["top_skills"],
                },
            )
            succeeded.append(role_id)
        except Exception as exc:
            logger.error("Failed to recalculate score for %s: %s", role_id, exc)
            failed.append({"role_id": role_id, "error": str(exc)})

    return {"succeeded": succeeded, "failed": failed}
