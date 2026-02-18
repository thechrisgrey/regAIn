"""BLS Public Data API ingestion module for the Market Intelligence System.

Fetches employment projections, occupational outlook, and wage data from
the Bureau of Labor Statistics Public Data API (v1, no API key required),
transforms responses into MarketDataRecord format, and merges into the
MarketData DynamoDB table.

API docs: https://www.bls.gov/developers/api_signature_v1.htm
Endpoint: POST https://api.bls.gov/publicAPI/v1/timeseries/data/
"""

from __future__ import annotations

import importlib
import logging
from datetime import date
from typing import Any

import requests

# 'lambda' is a Python keyword — use importlib for sibling imports.
_retry_mod = importlib.import_module("backend.lambda.market_intel.ingestion.retry")
retry_with_backoff = _retry_mod.retry_with_backoff

_models_mod = importlib.import_module("backend.lambda.market_intel.models")
MarketDataRecord = _models_mod.MarketDataRecord

_db_mod = importlib.import_module("backend.lambda.shared.dynamodb")
DynamoDBClient = _db_mod.DynamoDBClient

logger = logging.getLogger(__name__)

BLS_API_URL = "https://api.bls.gov/publicAPI/v1/timeseries/data/"


def _fetch_series(series_id: str) -> dict[str, Any]:
    """Fetch time series data from the BLS Public Data API for a single series.

    Requests the most recent two years of data so that year-over-year
    growth can be derived from the response.

    Args:
        series_id: BLS series identifier (e.g. "CEU0000000001").

    Returns:
        Parsed JSON response dict from the BLS API.

    Raises:
        requests.HTTPError: On non-2xx response.
        ValueError: If the API returns a non-REQUEST_SUCCEEDED status.
    """
    current_year = date.today().year
    payload = {
        "seriesid": [series_id],
        "startyear": str(current_year - 1),
        "endyear": str(current_year),
    }

    def _call() -> dict[str, Any]:
        resp = requests.post(BLS_API_URL, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "REQUEST_SUCCEEDED":
            raise ValueError(
                f"BLS API returned status '{data.get('status')}' "
                f"for series {series_id}: {data.get('message', '')}"
            )
        return data

    return retry_with_backoff(_call)


def _extract_latest_value(series_data: list[dict[str, Any]]) -> dict[str, Any]:
    """Extract the latest data point and compute YoY growth from BLS series data.

    Args:
        series_data: List of data point dicts from a BLS series response,
            each containing 'year', 'period', and 'value' keys.

    Returns:
        Dict with 'latest_value' (float), 'latest_year' (str),
        'latest_period' (str), and 'growth_rate' (float, YoY %).
    """
    if not series_data:
        return {
            "latest_value": 0.0,
            "latest_year": "",
            "latest_period": "",
            "growth_rate": 0.0,
        }

    # BLS returns data newest-first; sort by year+period descending to be safe.
    sorted_data = sorted(
        series_data,
        key=lambda d: (d.get("year", ""), d.get("period", "")),
        reverse=True,
    )

    latest = sorted_data[0]
    latest_value = float(latest.get("value", 0))
    latest_year = latest.get("year", "")
    latest_period = latest.get("period", "")

    # Find the same period from the previous year for YoY growth.
    growth_rate = 0.0
    prev_year = str(int(latest_year) - 1) if latest_year.isdigit() else ""
    for point in sorted_data:
        if point.get("year") == prev_year and point.get("period") == latest_period:
            prev_value = float(point.get("value", 0))
            if prev_value > 0:
                growth_rate = ((latest_value - prev_value) / prev_value) * 100.0
            break

    return {
        "latest_value": latest_value,
        "latest_year": latest_year,
        "latest_period": latest_period,
        "growth_rate": round(growth_rate, 2),
    }


def _merge_into_record(
    series_id: str,
    extracted: dict[str, Any],
    existing_item: dict[str, Any] | None,
) -> MarketDataRecord:
    """Merge BLS data into an existing MarketDataRecord or create a new one.

    If an existing record is found in DynamoDB, BLS-sourced fields
    (posting_volume as employment count, growth_rate, projection) are
    updated while preserving other fields. Otherwise a minimal new
    record is created.

    Args:
        series_id: BLS series identifier used as the role key.
        extracted: Output from ``_extract_latest_value``.
        existing_item: Existing DynamoDB item dict, or None.

    Returns:
        A MarketDataRecord ready for DynamoDB storage.
    """
    today = date.today().isoformat()

    if existing_item:
        record = MarketDataRecord.from_dynamodb_item(existing_item)
        # Merge BLS-specific fields into the existing record.
        record.posting_volume = int(extracted["latest_value"])
        record.growth_rate = extracted["growth_rate"]
        record.source = "composite" if record.source != "bls" else "bls"
        record.timestamp = today
        return record

    # No existing record — create a minimal one from BLS data.
    return MarketDataRecord(
        sector=f"role:{series_id}",
        timestamp=today,
        role_title=series_id,
        category="general",
        demand_score=0,
        growth_rate=extracted["growth_rate"],
        trend_direction="stable",
        top_skills=[],
        salary_range={"min": 0, "median": 0, "max": 0, "region": "national"},
        posting_volume=int(extracted["latest_value"]),
        projection="",
        source="bls",
        insights=[],
    )


def ingest(series_ids: list[str]) -> dict[str, Any]:
    """Fetch BLS series data, transform, and merge into DynamoDB.

    For each series_id, fetches time series data from the BLS Public
    Data API, extracts the latest data point and YoY growth, merges
    into any existing MarketData record (read-modify-write), and writes
    back to DynamoDB. Per-series failures are caught and logged —
    processing continues for remaining series.

    Args:
        series_ids: List of BLS series identifiers to ingest.

    Returns:
        Dict with 'succeeded' (list of series_ids) and 'failed' (list
        of dicts with 'series_id' and 'error' keys).
    """
    db = DynamoDBClient()

    succeeded: list[str] = []
    failed: list[dict[str, str]] = []

    for series_id in series_ids:
        try:
            # 1. Fetch from BLS API (with retry).
            response = _fetch_series(series_id)

            # 2. Extract series data from the response.
            series_list = response.get("Results", {}).get("series", [])
            if not series_list:
                raise ValueError(f"No series data returned for {series_id}")

            series_data = series_list[0].get("data", [])
            extracted = _extract_latest_value(series_data)

            # 3. Read existing record for merge (if any).
            sector_key = f"role:{series_id}"
            today = date.today().isoformat()
            existing_item = db.get_item(
                "market_data",
                {"sector": sector_key, "timestamp": today},
            )

            # 4. Merge and write back (put_item = idempotent overwrite).
            record = _merge_into_record(series_id, extracted, existing_item)
            db.put_item("market_data", record.to_dynamodb_item())

            succeeded.append(series_id)
            logger.info("Successfully ingested BLS data for series %s", series_id)

        except Exception as exc:
            logger.error(
                "Failed to ingest BLS data for series %s: %s",
                series_id,
                exc,
            )
            failed.append({"series_id": series_id, "error": str(exc)})

    return {"succeeded": succeeded, "failed": failed}
