"""Profile Lambda handler.

Thin handler that extracts the user identity, delegates to
ProfileService, and returns a formatted response.
"""

import logging
from typing import Any, Dict

from backend.handlers.shared.auth import get_user_id
from backend.handlers.shared.responses import error_response, success_response
from backend.handlers.shared.structured_log import get_logger
from backend.handlers.profile.service import ProfileService

logger = logging.getLogger(__name__)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handle profile requests (DELETE /profile, POST /profile/recover).

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

    http_method = event.get("httpMethod", "")
    resource = event.get("resource", "")

    try:
        service = ProfileService()

        if http_method == "POST" and resource == "/profile/recover":
            result = service.recover_user_account(user_id)
            return success_response(result)

        if http_method == "DELETE":
            result = service.soft_delete_user_account(user_id)
            return success_response(result)

        return error_response("Not found", 404)
    except Exception:
        slog.exception("Profile handler failed for user %s", user_id)
        return error_response("Internal server error", 500)
