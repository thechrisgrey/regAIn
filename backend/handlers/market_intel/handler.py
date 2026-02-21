"""Lambda handler entry points for the Market Intelligence scheduled pipeline.

Each handler is a thin wrapper: validate input, delegate to the
appropriate service module, and return a structured response. No
business logic lives here.

Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 9.3
"""

from __future__ import annotations

import importlib
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Sibling imports via importlib ('lambda' is a Python keyword in the path).
_onet_mod = importlib.import_module("backend.handlers.market_intel.ingestion.onet")
_bls_mod = importlib.import_module("backend.handlers.market_intel.ingestion.bls")
_usajobs_mod = importlib.import_module("backend.handlers.market_intel.ingestion.usajobs")
_scoring_mod = importlib.import_module("backend.handlers.market_intel.scoring")
_seed_mod = importlib.import_module("backend.handlers.market_intel.seed")


def _response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    """Build a standard Lambda response dict.

    Args:
        status_code: HTTP-style status code.
        body: Response payload.

    Returns:
        Dict with statusCode and JSON-serialised body.
    """
    return {
        "statusCode": status_code,
        "body": json.dumps(body, default=str),
    }


def onet_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Triggered monthly on the 1st. Ingests O*NET data then recalculates scores.

    Event payload:
        role_ids (list[str], optional): O*NET SOC codes to ingest.
            Defaults to an empty list (no-op) when omitted.

    Args:
        event: EventBridge or direct invocation payload.
        context: Lambda context object.

    Returns:
        Structured response with ingestion and scoring results.
    """
    logger.info("onet_handler invoked")

    role_ids: list[str] = event.get("role_ids", [])
    if not isinstance(role_ids, list):
        return _response(400, {"error": "role_ids must be a list"})

    try:
        ingest_result = _onet_mod.ingest(role_ids)
        succeeded_roles = ingest_result.get("succeeded", [])

        score_result: dict[str, Any] = {"succeeded": [], "failed": []}
        if succeeded_roles:
            score_result = _scoring_mod.recalculate_scores(succeeded_roles)

        return _response(200, {
            "ingestion": ingest_result,
            "scoring": score_result,
        })
    except Exception as exc:
        logger.exception("onet_handler failed")
        return _response(500, {"error": str(exc)})


def bls_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Triggered monthly on the 15th. Ingests BLS data then recalculates scores.

    Event payload:
        series_ids (list[str], optional): BLS series identifiers.
            Defaults to an empty list when omitted.

    Args:
        event: EventBridge or direct invocation payload.
        context: Lambda context object.

    Returns:
        Structured response with ingestion and scoring results.
    """
    logger.info("bls_handler invoked")

    series_ids: list[str] = event.get("series_ids", [])
    if not isinstance(series_ids, list):
        return _response(400, {"error": "series_ids must be a list"})

    try:
        ingest_result = _bls_mod.ingest(series_ids)
        succeeded_series = ingest_result.get("succeeded", [])

        score_result: dict[str, Any] = {"succeeded": [], "failed": []}
        if succeeded_series:
            score_result = _scoring_mod.recalculate_scores(succeeded_series)

        return _response(200, {
            "ingestion": ingest_result,
            "scoring": score_result,
        })
    except Exception as exc:
        logger.exception("bls_handler failed")
        return _response(500, {"error": str(exc)})


def usajobs_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Triggered weekly on Monday. Ingests USAJobs data then recalculates scores.

    Event payload:
        keywords (list[str], optional): Search keywords for USAJobs.
            Defaults to an empty list when omitted.

    Args:
        event: EventBridge or direct invocation payload.
        context: Lambda context object.

    Returns:
        Structured response with ingestion and scoring results.
    """
    logger.info("usajobs_handler invoked")

    keywords: list[str] = event.get("keywords", [])
    if not isinstance(keywords, list):
        return _response(400, {"error": "keywords must be a list"})

    try:
        ingest_result = _usajobs_mod.ingest(keywords)
        succeeded_keywords = ingest_result.get("succeeded", [])

        # USAJobs keywords map to role keys via lowercase + underscore.
        role_ids = [kw.lower().replace(" ", "_") for kw in succeeded_keywords]

        score_result: dict[str, Any] = {"succeeded": [], "failed": []}
        if role_ids:
            score_result = _scoring_mod.recalculate_scores(role_ids)

        return _response(200, {
            "ingestion": ingest_result,
            "scoring": score_result,
        })
    except Exception as exc:
        logger.exception("usajobs_handler failed")
        return _response(500, {"error": str(exc)})


def seed_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """One-time seed data loader. Loads pre-built market data for demo roles.

    No input parameters required.

    Args:
        event: EventBridge or direct invocation payload (ignored).
        context: Lambda context object.

    Returns:
        Structured response with seed loading results.
    """
    logger.info("seed_handler invoked")

    try:
        result = _seed_mod.load_seed_data()
        return _response(200, {"seed": result})
    except Exception as exc:
        logger.exception("seed_handler failed")
        return _response(500, {"error": str(exc)})
