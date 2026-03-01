"""Coaching Lambda handler.

Thin handler for POST /coaching/checkin.
"""

import json
import logging
from typing import Any, Dict

from backend.handlers.shared.auth import get_user_id
from backend.handlers.shared.responses import error_response, success_response
from backend.handlers.shared.structured_log import get_logger
from backend.handlers.shared.validation import validate_body, validate_string_field
from backend.handlers.coaching.service import CoachingService

logger = logging.getLogger(__name__)


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
    slog = get_logger(event, __name__)
    user_id = get_user_id(event)
    if not user_id:
        return error_response("Unauthorized", 401)

    jwt_token = _get_jwt_token(event)
    if not jwt_token:
        return error_response("Missing authorization token", 401)

    try:
        body = validate_body(event, max_bytes=51_200)  # 50 KB
    except ValueError as exc:
        return error_response(str(exc), 400)

    try:
        message = validate_string_field(body, "message", max_length=10_000, required=True)
    except ValueError as exc:
        return error_response(str(exc), 400)

    session_type = body.get("session_type", "checkin")

    try:
        service = CoachingService()
        result = service.checkin(user_id, message, jwt_token=jwt_token, session_type=session_type)
        return success_response(result)
    except Exception:
        slog.exception("Coaching handler failed")
        return error_response("Internal server error", 500)
