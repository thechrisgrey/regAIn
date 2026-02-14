"""Missions Lambda handler.

Thin handler for GET /missions and POST /missions/{missionId}/complete.
"""

import json
import logging
from typing import Any, Dict

from backend.lambda.shared.responses import error_response, success_response
from backend.lambda.missions.service import MissionsService

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
            return success_response({"missions": missions})

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

    except Exception:
        logger.exception("Missions handler failed")
        return error_response("Internal server error", 500)
