"""Missions Lambda handler.

Thin handler for GET /missions, POST /missions/{missionId}/complete,
and POST /missions/generate.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict

from backend.handlers.shared.responses import error_response, success_response
from backend.handlers.missions.service import MissionsService, _GenerateRateLimitExceeded

logger = logging.getLogger(__name__)


def _get_user_id(event: Dict[str, Any]) -> str | None:
    """Extract userId from Cognito authorizer claims."""
    try:
        return event["requestContext"]["authorizer"]["claims"]["sub"]
    except (KeyError, TypeError):
        return None


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handle missions API requests.

    Args:
        event: API Gateway event.
        context: Lambda context.

    Returns:
        API Gateway-compatible response.
    """
    user_id = _get_user_id(event)
    if not user_id:
        return error_response("Unauthorized", 401)

    http_method = event.get("httpMethod", "")
    resource = event.get("resource", "")

    try:
        service = MissionsService()

        if http_method == "GET" and resource == "/missions":
            params = event.get("queryStringParameters") or {}
            missions = service.list_missions(user_id, status=params.get("status"))
            remaining = service.get_daily_remaining(user_id)
            return success_response({"missions": missions, **remaining})

        if http_method == "POST" and resource == "/missions/generate":
            result = service.generate_mission(user_id)
            return success_response(result)

        if http_method == "POST" and "/complete" in resource:
            mission_id = (event.get("pathParameters") or {}).get("missionId")
            if not mission_id:
                return error_response("Missing missionId path parameter", 400)

            try:
                body = json.loads(event.get("body", "{}"))
            except (json.JSONDecodeError, TypeError):
                return error_response("Invalid JSON body", 400)

            result = service.complete_mission(user_id, mission_id, body)
            return success_response(result)

        return error_response("Not found", 404)

    except _GenerateRateLimitExceeded:
        tomorrow = datetime.now(timezone.utc).strftime("%Y-%m-%d") + "T00:00:00Z"
        return error_response(
            "Daily mission generation limit reached. Try again tomorrow.",
            429,
        )

    except Exception:
        logger.exception("Missions handler failed")
        return error_response("Internal server error", 500)
