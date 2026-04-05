"""Public Score Lambda handler.

Serves read-only scorecard data for public share links (unauthenticated).
"""

import json
import logging
import os
from typing import Any, Dict

import boto3

logger = logging.getLogger(__name__)

_CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "GET,OPTIONS",
}


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handle GET /score/public/{shortCode} requests.

    No authentication required. Returns privacy-filtered score data.
    """
    path_params = event.get("pathParameters") or {}
    short_code = path_params.get("shortCode", "")

    if not short_code:
        return {
            "statusCode": 400,
            "headers": _CORS_HEADERS,
            "body": json.dumps({"error": "Missing shortCode"}),
        }

    dynamodb = boto3.resource("dynamodb")

    # Look up the short code
    links_table = dynamodb.Table(
        os.environ.get("PUBLIC_SCORE_LINKS_TABLE", "RegainPublicScoreLinks"),
    )
    link = links_table.get_item(Key={"shortCode": short_code}).get("Item")
    if not link:
        return {
            "statusCode": 404,
            "headers": _CORS_HEADERS,
            "body": json.dumps({"error": "Scorecard not found"}),
        }

    user_id = link.get("userId", "")

    # Fetch latest score
    scores_table = dynamodb.Table(
        os.environ.get("IMPACT_SCORES_TABLE", "RegainImpactScores"),
    )
    score = scores_table.get_item(
        Key={"userId": user_id, "sk": "LATEST"},
    ).get("Item")

    if not score:
        return {
            "statusCode": 404,
            "headers": _CORS_HEADERS,
            "body": json.dumps({"error": "No score data available"}),
        }

    # Privacy filter: only return dimensions the user chose to share
    visible = link.get("visibleDimensions") or []
    if visible:
        detail = score.get("dimensionDetail", {})
        filtered_detail = {k: v for k, v in detail.items() if k in visible}
        score["dimensionDetail"] = filtered_detail

    # Remove internal fields
    score.pop("userId", None)
    score.pop("sk", None)
    score.pop("ttl", None)

    return {
        "statusCode": 200,
        "headers": _CORS_HEADERS,
        "body": json.dumps(score, default=str),
    }
