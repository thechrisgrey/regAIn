"""Coaching Lambda handler.

Thin handler for POST /coaching/checkin.
"""

import json
import logging
from typing import Any, Dict

from backend.handlers.shared.responses import error_response, success_response
from backend.handlers.coaching.service import CoachingService

logger = logging.getLogger(__name__)


def _get_user_id(event: Dict[str, Any]) -> str | None:
    """Extract userId from Cognito authorizer claims."""
    try:
        return event["requestContext"]["authorizer"]["claims"]["sub"]
    except (KeyError, TypeError):
        return None

def _get_jwt_token(event: Dict[str, Any]) -> str | None:
    """Extract JWT token from Authorization header.

    Args:
        event: API Gateway event containing headers.

    Returns:
        The raw JWT token string, or None if not present.
    """
    try:
        auth_header = event.get("headers", {}).get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header[7:]
        return auth_header or None
    except (AttributeError, TypeError):
        return None



def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handle POST /coaching/checkin requests.

    Args:
        event: API Gateway event.
        context: Lambda context.

    Returns:
        API Gateway-compatible response.
    """
    user_id = _get_user_id(event)
    if not user_id:
        return error_response("Unauthorized", 401)

    jwt_token = _get_jwt_token(event)
    if not jwt_token:
        return error_response("Missing authorization token", 401)

    try:
        body = json.loads(event.get("body", "{}"))
    except (json.JSONDecodeError, TypeError):
        return error_response("Invalid JSON body", 400)

    message = body.get("message", "")
    if not message:
        return error_response("Missing required field: message", 400)

    session_type = body.get("session_type", "checkin")

    try:
        service = CoachingService()
        result = service.checkin(user_id, message, jwt_token=jwt_token, session_type=session_type)
        return success_response(result)
    except Exception:
        logger.exception("Coaching handler failed")
        return error_response("Internal server error", 500)
