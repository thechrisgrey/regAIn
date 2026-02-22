"""Voice practice REST API Lambda handler.

Thin handler that routes by httpMethod + path:
- GET /voice-sessions → list sessions
- GET /voice-sessions/{sessionId} → get session detail
"""

import logging
from typing import Any, Dict

from backend.handlers.shared.auth import get_user_id
from backend.handlers.shared.responses import error_response, success_response
from backend.handlers.voice_practice.service import VoicePracticeService

logger = logging.getLogger(__name__)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Route to list sessions or get session detail.

    Args:
        event: API Gateway event.
        context: Lambda context.

    Returns:
        API Gateway-compatible response dict.
    """
    user_id = get_user_id(event)
    if not user_id:
        return error_response("Unauthorized", 401)

    http_method = event.get("httpMethod", "")
    path_params = event.get("pathParameters") or {}

    if http_method != "GET":
        return error_response("Method not allowed", 400)

    service = VoicePracticeService()

    try:
        session_id = path_params.get("sessionId")
        if session_id:
            result = service.get_session_detail(user_id, session_id)
            if result is None:
                return error_response("Session not found", 404)
            return success_response(result)
        else:
            sessions = service.list_sessions(user_id)
            return success_response({"sessions": sessions})
    except Exception:
        logger.exception("Voice practice handler failed")
        return error_response("Internal server error", 500)
