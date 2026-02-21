"""USAJobs API ingestion module for the Market Intelligence System.

Fetches federal job posting volumes and skill requirements from the
USAJobs API, transforms responses into MarketDataRecord format, and
merges into the MarketData DynamoDB table.

API docs: https://developer.usajobs.gov/API-Reference
Endpoint: GET https://data.usajobs.gov/api/search
Authentication: Authorization-Key header + User-Agent header.
"""

from __future__ import annotations

import importlib
import logging
import os
from datetime import date
from typing import Any

import requests

# 'lambda' is a Python keyword — use importlib for sibling imports.
_retry_mod = importlib.import_module("backend.handlers.market_intel.ingestion.retry")
retry_with_backoff = _retry_mod.retry_with_backoff

_models_mod = importlib.import_module("backend.handlers.market_intel.models")
MarketDataRecord = _models_mod.MarketDataRecord

_taxonomy_mod = importlib.import_module("backend.handlers.market_intel.taxonomy")
normalize_skill = _taxonomy_mod.normalize_skill

_db_mod = importlib.import_module("backend.handlers.shared.dynamodb")
DynamoDBClient = _db_mod.DynamoDBClient

logger = logging.getLogger(__name__)

USAJOBS_API_URL = "https://data.usajobs.gov/api/search"


def _get_headers() -> dict[str, str]:
    """Build request headers from environment variables.

    Returns:
        Dict with Authorization-Key and User-Agent headers.

    Raises:
        ValueError: If required environment variables are not set.
    """
    api_key = os.environ.get("USAJOBS_API_KEY", "")
    if not api_key:
        raise ValueError("USAJOBS_API_KEY environment variable is not set")

    user_agent = os.environ.get("USAJOBS_USER_AGENT", "")
    if not user_agent:
        raise ValueError("USAJOBS_USER_AGENT environment variable is not set")

    return {
        "Authorization-Key": api_key,
        "User-Agent": user_agent,
        "Host": "data.usajobs.gov",
    }


def _fetch_postings(keyword: str, headers: dict[str, str]) -> dict[str, Any]:
    """Fetch job postings from USAJobs API for a given keyword.

    Args:
        keyword: Search keyword (e.g. "data analyst", "project manager").
        headers: Pre-built request headers with auth credentials.

    Returns:
        Parsed JSON response dict from the USAJobs API.

    Raises:
        requests.HTTPError: On non-2xx response.
    """
    params = {"Keyword": keyword, "ResultsPerPage": 100}

    def _call() -> dict[str, Any]:
        resp = requests.get(
            USAJOBS_API_URL,
            headers=headers,
            params=params,
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    return retry_with_backoff(_call)


def _extract_skills(position_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract and aggregate skill requirements from USAJobs position items.

    Parses qualification summaries from job postings to identify skill
    mentions, normalizes them through the taxonomy, and calculates
    frequency percentages across all postings.

    Args:
        position_items: List of MatchedObjectDescriptor dicts from the
            USAJobs search response.

    Returns:
        List of skill dicts sorted by frequency descending, each with
        'skill', 'frequency', and 'canonical' keys.
    """
    if not position_items:
        return []

    skill_counts: dict[str, int] = {}
    total_postings = len(position_items)

    for item in position_items:
        qualifications = item.get("QualificationSummary", "")
        title = item.get("PositionTitle", "")
        combined_text = f"{title} {qualifications}".lower()

        # Check each canonical skill's aliases against the posting text.
        seen_in_posting: set[str] = set()
        for alias, canonical in _taxonomy_mod.ALIAS_INDEX.items():
            if alias in combined_text and canonical not in seen_in_posting:
                seen_in_posting.add(canonical)
                skill_counts[canonical] = skill_counts.get(canonical, 0) + 1

    # Convert counts to frequency percentages.
    top_skills: list[dict[str, Any]] = []
    for skill_name, count in skill_counts.items():
        frequency = round((count / total_postings) * 100.0, 1)
        top_skills.append({
            "skill": skill_name,
            "frequency": frequency,
            "canonical": skill_name,
        })

    top_skills.sort(key=lambda s: s["frequency"], reverse=True)
    return top_skills


def _extract_salary_range(
    position_items: list[dict[str, Any]],
) -> dict[str, Any]:
    """Extract aggregated salary range from USAJobs position items.

    Args:
        position_items: List of MatchedObjectDescriptor dicts.

    Returns:
        Dict with min, median, max, and region keys.
    """
    salaries: list[int] = []

    for item in position_items:
        remuneration = item.get("PositionRemuneration", [])
        for entry in remuneration:
            min_val = entry.get("MinimumRange", "0")
            max_val = entry.get("MaximumRange", "0")
            try:
                min_int = int(float(min_val))
                max_int = int(float(max_val))
                if min_int > 0:
                    salaries.append(min_int)
                if max_int > 0:
                    salaries.append(max_int)
            except (ValueError, TypeError):
                continue

    if not salaries:
        return {"min": 0, "median": 0, "max": 0, "region": "national"}

    salaries.sort()
    mid = len(salaries) // 2
    median = salaries[mid] if len(salaries) % 2 else (salaries[mid - 1] + salaries[mid]) // 2

    return {
        "min": salaries[0],
        "median": median,
        "max": salaries[-1],
        "region": "national",
    }


def _merge_into_record(
    keyword: str,
    posting_count: int,
    top_skills: list[dict[str, Any]],
    salary_range: dict[str, Any],
    existing_item: dict[str, Any] | None,
) -> MarketDataRecord:
    """Merge USAJobs data into an existing MarketDataRecord or create a new one.

    If an existing record is found in DynamoDB, USAJobs-sourced fields
    (posting_volume, top_skills, salary_range) are updated while
    preserving other fields. Otherwise a minimal new record is created.

    Args:
        keyword: Search keyword used as the role key.
        posting_count: Total number of matching job postings.
        top_skills: Aggregated skill requirements with frequencies.
        salary_range: Aggregated salary range dict.
        existing_item: Existing DynamoDB item dict, or None.

    Returns:
        A MarketDataRecord ready for DynamoDB storage.
    """
    today = date.today().isoformat()

    if existing_item:
        record = MarketDataRecord.from_dynamodb_item(existing_item)
        record.posting_volume = posting_count
        record.top_skills = top_skills if top_skills else record.top_skills
        record.salary_range = salary_range if salary_range.get("median", 0) > 0 else record.salary_range
        record.source = "composite" if record.source != "usajobs" else "usajobs"
        record.timestamp = today
        return record

    # No existing record — create a minimal one from USAJobs data.
    role_key = keyword.lower().replace(" ", "_")
    return MarketDataRecord(
        sector=f"role:{role_key}",
        timestamp=today,
        role_title=keyword,
        category="general",
        demand_score=0,
        growth_rate=0.0,
        trend_direction="stable",
        top_skills=top_skills,
        salary_range=salary_range,
        posting_volume=posting_count,
        projection="",
        source="usajobs",
        insights=[],
    )


def ingest(keywords: list[str]) -> dict[str, Any]:
    """Fetch USAJobs posting data, transform, and merge into DynamoDB.

    For each keyword, fetches job postings from the USAJobs API,
    extracts posting count and skill requirements, merges into any
    existing MarketData record (read-modify-write), and writes back
    to DynamoDB. Per-keyword failures are caught and logged —
    processing continues for remaining keywords.

    Args:
        keywords: List of search keywords to ingest (e.g.
            ["data analyst", "project manager"]).

    Returns:
        Dict with 'succeeded' (list of keywords) and 'failed' (list
        of dicts with 'keyword' and 'error' keys).
    """
    headers = _get_headers()
    db = DynamoDBClient()

    succeeded: list[str] = []
    failed: list[dict[str, str]] = []

    for keyword in keywords:
        try:
            # 1. Fetch from USAJobs API (with retry).
            response = _fetch_postings(keyword, headers)

            # 2. Extract posting data from the response.
            search_result = response.get("SearchResult", {})
            posting_count = int(search_result.get("SearchResultCount", 0))
            result_items = search_result.get("SearchResultItems", [])

            # Each result item wraps the actual data in MatchedObjectDescriptor.
            position_items = [
                item.get("MatchedObjectDescriptor", {})
                for item in result_items
            ]

            # 3. Extract skills and salary from postings.
            top_skills = _extract_skills(position_items)
            salary_range = _extract_salary_range(position_items)

            # 4. Read existing record for merge (if any).
            role_key = keyword.lower().replace(" ", "_")
            sector_key = f"role:{role_key}"
            today = date.today().isoformat()
            existing_item = db.get_item(
                "market_data",
                {"sector": sector_key, "timestamp": today},
            )

            # 5. Merge and write back (put_item = idempotent overwrite).
            record = _merge_into_record(
                keyword, posting_count, top_skills, salary_range, existing_item,
            )
            db.put_item("market_data", record.to_dynamodb_item())

            succeeded.append(keyword)
            logger.info(
                "Successfully ingested USAJobs data for keyword '%s': "
                "%d postings, %d skills extracted",
                keyword,
                posting_count,
                len(top_skills),
            )

        except Exception as exc:
            logger.error(
                "Failed to ingest USAJobs data for keyword '%s': %s",
                keyword,
                exc,
            )
            failed.append({"keyword": keyword, "error": str(exc)})

    return {"succeeded": succeeded, "failed": failed}
