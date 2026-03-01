"""Dashboard Lambda handler.

Thin handler for GET /dashboard.
"""

import logging
from typing import Any, Dict

from backend.handlers.shared.auth import get_user_id
from backend.handlers.shared.responses import error_response, success_response
from backend.handlers.shared.structured_log import get_logger
from backend.handlers.dashboard.service import DashboardService

logger = logging.getLogger(__name__)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handle GET /dashboard requests.

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

    try:
        service = DashboardService()
        result = service.get_dashboard(user_id)
        return success_response(result)
    except Exception:
        slog.exception("Dashboard handler failed")
        return error_response("Internal server error", 500)
