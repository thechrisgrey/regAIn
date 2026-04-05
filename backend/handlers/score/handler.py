"""Score Lambda handler.

Thin handler for GET /score, GET /score/history, POST /score/share,
and POST /score/export.
"""

import json
import logging
import os
import secrets
import time
from typing import Any, Dict

import boto3
from boto3.dynamodb.conditions import Key as DKey

from backend.handlers.shared.auth import get_user_id
from backend.handlers.shared.responses import error_response, success_response
from backend.handlers.shared.structured_log import get_logger
from backend.handlers.score.service import ScoreService

logger = logging.getLogger(__name__)

_SHARE_LINK_TTL_DAYS = 90


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Route score API requests to the appropriate handler.

    Supports:
        GET  /score          — compute current scorecard
        GET  /score/history  — daily snapshots for charts
        POST /score/share    — generate a public share link
        POST /score/export   — generate a PDF Career Evidence Report
    """
    slog = get_logger(event, __name__)
    user_id = get_user_id(event)
    if not user_id:
        return error_response("Unauthorized", 401)

    resource = event.get("resource", "")
    method = event.get("httpMethod", "")

    try:
        if resource == "/score/history" and method == "GET":
            return _handle_history(user_id)

        if resource == "/score/share" and method == "POST":
            return _handle_share(user_id, event)

        if resource == "/score/export" and method == "POST":
            return _handle_export(user_id)

        # Default: GET /score
        return _handle_get_score(user_id)
    except Exception:
        slog.exception("Score handler failed")
        return error_response("Internal server error", 500)


def _handle_get_score(user_id: str) -> Dict[str, Any]:
    """Compute and return the current scorecard."""
    service = ScoreService()
    scorecard = service.compute_scorecard(user_id)

    # Persist the LATEST score to the ImpactScores table for caching
    _persist_score(user_id, scorecard)

    return success_response(scorecard)


def _handle_history(user_id: str) -> Dict[str, Any]:
    """Return cached daily snapshots for longitudinal charts."""
    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(
        os.environ.get("IMPACT_SCORES_TABLE", "RegainImpactScores"),
    )
    result = table.query(
        KeyConditionExpression=(
            DKey("userId").eq(user_id)
            & DKey("sk").begins_with("SNAPSHOT#")
        ),
        ScanIndexForward=True,
    )
    snapshots = result.get("Items", [])
    return success_response({"snapshots": snapshots})


def _handle_share(user_id: str, event: Dict[str, Any]) -> Dict[str, Any]:
    """Generate a public share link for the scorecard."""
    body = {}
    if event.get("body"):
        try:
            body = json.loads(event["body"])
        except (json.JSONDecodeError, TypeError):
            pass

    visible_dimensions = body.get("visibleDimensions", [
        "missionVelocity", "evidenceDensity", "marketAlignment",
        "phaseProgression", "adaptiveDifficulty",
    ])

    short_code = secrets.token_urlsafe(6)  # 8 chars, URL-safe
    expires_at = int(time.time()) + (_SHARE_LINK_TTL_DAYS * 86400)

    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(
        os.environ.get("PUBLIC_SCORE_LINKS_TABLE", "RegainPublicScoreLinks"),
    )
    table.put_item(Item={
        "shortCode": short_code,
        "userId": user_id,
        "visibleDimensions": visible_dimensions,
        "createdAt": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat(),
        "expiresAt": expires_at,
    })

    # Build the public URL
    api_base = os.environ.get("API_BASE_URL", "")
    public_url = f"{api_base}/score/public/{short_code}" if api_base else short_code

    return success_response({
        "shortCode": short_code,
        "url": public_url,
        "expiresInDays": _SHARE_LINK_TTL_DAYS,
    })


def _handle_export(user_id: str) -> Dict[str, Any]:
    """Generate a PDF Career Evidence Report and return download URL."""
    service = ScoreService()

    # Compute fresh scorecard
    scorecard = service.compute_scorecard(user_id)

    # Fetch user profile for the report cover
    profile = service.db.get_item("user_profiles", {"userId": user_id}) or {}

    # Fetch evidence for highlights
    evidence = service.db.query_all(
        "evidence_vault",
        key_condition=DKey("userId").eq(user_id),
    )

    # Generate PDF
    from backend.handlers.score.pdf_service import PdfExportService
    pdf_service = PdfExportService()
    url = pdf_service.generate_report(user_id, scorecard, profile, evidence)

    return success_response({"url": url})


def _persist_score(user_id: str, scorecard: Dict[str, Any]) -> None:
    """Persist the computed scorecard to the ImpactScores table."""
    try:
        dynamodb = boto3.resource("dynamodb")
        table = dynamodb.Table(
            os.environ.get("IMPACT_SCORES_TABLE", "RegainImpactScores"),
        )

        # Write LATEST
        item = {
            "userId": user_id,
            "sk": "LATEST",
            **{k: v for k, v in scorecard.items() if k != "dimensionDetail"},
            "dimensionDetail": scorecard.get("dimensionDetail", {}),
        }
        table.put_item(Item=json.loads(json.dumps(item, default=str)))

        # Write daily snapshot
        today = scorecard.get("computedAt", "")[:10]
        snapshot = {
            "userId": user_id,
            "sk": f"SNAPSHOT#{today}",
            "cri": scorecard.get("cri"),
            "missionVelocityScore": scorecard.get("missionVelocityScore"),
            "evidenceDensityScore": scorecard.get("evidenceDensityScore"),
            "marketAlignmentScore": scorecard.get("marketAlignmentScore"),
            "phaseProgressionScore": scorecard.get("phaseProgressionScore"),
            "adaptiveDifficultyScore": scorecard.get("adaptiveDifficultyScore"),
            "computedAt": scorecard.get("computedAt"),
            "ttl": int(time.time()) + (90 * 86400),  # 90-day TTL
        }
        table.put_item(Item=json.loads(json.dumps(snapshot, default=str)))
    except Exception:
        logger.warning("Failed to persist score for user %s", user_id, exc_info=True)
