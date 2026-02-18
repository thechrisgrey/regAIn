"""O*NET API ingestion module for the Market Intelligence System.

Fetches occupation data and skill requirements from the O*NET Web Services
API, transforms responses into MarketDataRecord format, and writes to the
MarketData DynamoDB table.

API docs: https://services.onetcenter.org/reference/
Authentication: HTTP Basic Auth (API key as username, empty password).
"""

from __future__ import annotations

import importlib
import logging
import os
from datetime import date
from typing import Any

import requests

# 'lambda' is a Python keyword — use importlib for sibling imports.
_retry_mod = importlib.import_module("backend.lambda.market_intel.ingestion.retry")
retry_with_backoff = _retry_mod.retry_with_backoff

_models_mod = importlib.import_module("backend.lambda.market_intel.models")
MarketDataRecord = _models_mod.MarketDataRecord

_taxonomy_mod = importlib.import_module("backend.lambda.market_intel.taxonomy")
normalize_skill = _taxonomy_mod.normalize_skill

_db_mod = importlib.import_module("backend.lambda.shared.dynamodb")
DynamoDBClient = _db_mod.DynamoDBClient

logger = logging.getLogger(__name__)

ONET_BASE_URL = "https://services.onetcenter.org/ws/"


def _get_auth() -> tuple[str, str]:
    """Return HTTP Basic Auth tuple from environment variable.

    Returns:
        Tuple of (api_key, empty_string) for requests auth parameter.

    Raises:
        ValueError: If ONET_API_KEY is not set.
    """
    api_key = os.environ.get("ONET_API_KEY", "")
    if not api_key:
        raise ValueError("ONET_API_KEY environment variable is not set")
    return (api_key, "")


def _fetch_occupation(role_id: str, auth: tuple[str, str]) -> dict[str, Any]:
    """Fetch occupation data from O*NET for a given SOC code.

    Args:
        role_id: O*NET SOC code (e.g. "15-1256.00").
        auth: HTTP Basic Auth credentials tuple.

    Returns:
        Parsed JSON response dict.

    Raises:
        requests.HTTPError: On non-2xx response.
    """
    url = f"{ONET_BASE_URL}online/occupations/{role_id}"
    headers = {"Accept": "application/json"}

    def _call() -> dict[str, Any]:
        resp = requests.get(url, auth=auth, headers=headers, timeout=15)
        resp.raise_for_status()
        return resp.json()

    return retry_with_backoff(_call)


def _fetch_skills(role_id: str, auth: tuple[str, str]) -> list[dict[str, Any]]:
    """Fetch skill requirements from O*NET for a given SOC code.

    Args:
        role_id: O*NET SOC code.
        auth: HTTP Basic Auth credentials tuple.

    Returns:
        List of skill dicts from the API response.

    Raises:
        requests.HTTPError: On non-2xx response.
    """
    url = f"{ONET_BASE_URL}online/occupations/{role_id}/skills"
    headers = {"Accept": "application/json"}

    def _call() -> list[dict[str, Any]]:
        resp = requests.get(url, auth=auth, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return data.get("element", [])

    return retry_with_backoff(_call)


def _transform(
    role_id: str,
    occupation: dict[str, Any],
    skills: list[dict[str, Any]],
) -> MarketDataRecord:
    """Transform O*NET API responses into a MarketDataRecord.

    Args:
        role_id: O*NET SOC code used as the role identifier.
        occupation: Parsed occupation JSON from O*NET.
        skills: List of skill element dicts from O*NET.

    Returns:
        A MarketDataRecord ready for DynamoDB storage.
    """
    role_title = occupation.get("title", role_id)
    category = occupation.get("tags", {}).get("bright_outlook", "general")

    # Build top_skills from O*NET skill elements, sorted by score descending.
    top_skills: list[dict[str, Any]] = []
    for skill in sorted(skills, key=lambda s: float(s.get("score", {}).get("value", 0)), reverse=True):
        skill_name = skill.get("name", "")
        score_value = float(skill.get("score", {}).get("value", 0))
        canonical = normalize_skill(skill_name)
        top_skills.append({
            "skill": skill_name,
            "frequency": round(score_value, 1),
            "canonical": canonical,
        })

    # Extract salary info from occupation tags if available.
    salary_range = {
        "min": 0,
        "median": 0,
        "max": 0,
        "region": "national",
    }

    # Job zone maps roughly to complexity; use as a proxy for projection.
    job_zone = occupation.get("job_zone", 3)
    projection_map = {
        1: "Slower",
        2: "Average",
        3: "Average",
        4: "Faster",
        5: "Much faster than average",
    }
    projection = projection_map.get(job_zone, "Average")

    today = date.today().isoformat()

    return MarketDataRecord(
        sector=f"role:{role_id}",
        timestamp=today,
        role_title=role_title,
        category=str(category),
        demand_score=0,  # Calculated later by scoring.recalculate_scores()
        growth_rate=0.0,
        trend_direction="stable",
        top_skills=top_skills,
        salary_range=salary_range,
        posting_volume=0,
        projection=projection,
        source="onet",
        insights=[],
    )


def ingest(role_ids: list[str]) -> dict[str, Any]:
    """Fetch O*NET data for given roles, transform, and write to DynamoDB.

    For each role_id, fetches occupation data and skill requirements from
    the O*NET API, transforms the response into a MarketDataRecord, and
    writes it to the MarketData DynamoDB table. Per-role failures are
    caught and logged — processing continues for remaining roles.

    Args:
        role_ids: List of O*NET SOC codes to ingest.

    Returns:
        Dict with 'succeeded' (list of role_ids) and 'failed' (list of
        dicts with 'role_id' and 'error' keys).
    """
    auth = _get_auth()
    db = DynamoDBClient()

    succeeded: list[str] = []
    failed: list[dict[str, str]] = []

    for role_id in role_ids:
        try:
            occupation = _fetch_occupation(role_id, auth)
            skills = _fetch_skills(role_id, auth)
            record = _transform(role_id, occupation, skills)
            db.put_item("market_data", record.to_dynamodb_item())
            succeeded.append(role_id)
            logger.info("Successfully ingested O*NET data for role %s", role_id)
        except Exception as exc:
            logger.error(
                "Failed to ingest O*NET data for role %s: %s",
                role_id,
                exc,
            )
            failed.append({"role_id": role_id, "error": str(exc)})

    return {"succeeded": succeeded, "failed": failed}
