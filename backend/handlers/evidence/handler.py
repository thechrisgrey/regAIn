"""Evidence Lambda handler.

Thin handler for GET /evidence with optional skill_tag filtering.
"""

import logging
from typing import Any, Dict

from backend.handlers.shared.auth import get_user_id
from backend.handlers.shared.responses import error_response, success_response
from backend.handlers.shared.structured_log import get_logger
from backend.handlers.evidence.service import EvidenceService

logger = logging.getLogger(__name__)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handle GET /evidence requests.

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
        params = event.get("queryStringParameters") or {}
        limit = min(int(params.get("limit", "50")), 200)
        cursor = params.get("cursor")
        service = EvidenceService()
        page = service.list_evidence(
            user_id, skill_tag=params.get("skill_tag"), limit=limit, cursor=cursor,
        )
        return success_response({
            "evidence": page["items"],
            "items": page["items"],
            "nextCursor": page["nextCursor"],
        })
    except Exception:
        slog.exception("Evidence handler failed")
        return error_response("Internal server error", 500)
