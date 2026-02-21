"""Profile Lambda handler.

Thin handler that extracts the user identity, delegates to
ProfileService, and returns a formatted response.
"""

import logging
from typing import Any, Dict

from backend.handlers.shared.responses import error_response, success_response
from backend.handlers.profile.service import ProfileService

logger = logging.getLogger(__name__)


def _get_user_id(event: Dict[str, Any]) -> str | None:
    """Extract userId from Cognito authorizer claims."""
    try:
        return event["requestContext"]["authorizer"]["claims"]["sub"]
    except (KeyError, TypeError):
        return None


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handle DELETE /profile requests.

    Args:
        event: API Gateway event.
        context: Lambda context.

    Returns:
        API Gateway-compatible response.
    """
    user_id = _get_user_id(event)
    if not user_id:
        return error_response("Unauthorized", 401)

    try:
        service = ProfileService()
        result = service.delete_user_account(user_id)
        return success_response({"message": "Account deleted", "details": result})
    except Exception:
        logger.exception("Account deletion failed for user %s", user_id)
        return error_response("Internal server error", 500)
