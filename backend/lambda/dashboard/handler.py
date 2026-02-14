"""Dashboard Lambda handler.

Thin handler for GET /dashboard.
"""

import logging
from typing import Any, Dict

from backend.lambda.shared.responses import error_response, success_response
from backend.lambda.dashboard.service import DashboardService

logger = logging.getLogger(__name__)


def _get_user_id(event: Dict[str, Any]) -> str | None:
    """Extract userId from Cognito authorizer claims."""
    try:
        return event["requestContext"]["authorizer"]["claims"]["sub"]
    except (KeyError, TypeError):
        return None


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handle GET /dashboard requests.

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
        service = DashboardService()
        result = service.get_dashboard(user_id)
        return success_response(result)
    except Exception:
        logger.exception("Dashboard handler failed")
        return error_response("Internal server error", 500)
