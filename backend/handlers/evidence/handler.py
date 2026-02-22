"""Evidence Lambda handler.

Thin handler for GET /evidence with optional skill_tag filtering.
"""

import logging
from typing import Any, Dict

from backend.handlers.shared.auth import get_user_id
from backend.handlers.shared.responses import error_response, success_response
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
    user_id = get_user_id(event)
    if not user_id:
        return error_response("Unauthorized", 401)

    try:
        params = event.get("queryStringParameters") or {}
        service = EvidenceService()
        evidence = service.list_evidence(user_id, skill_tag=params.get("skill_tag"))
        return success_response({"evidence": evidence})
    except Exception:
        logger.exception("Evidence handler failed")
        return error_response("Internal server error", 500)
