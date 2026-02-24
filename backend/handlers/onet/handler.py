"""O*NET Lambda handler.

Thin handler routing search and career detail requests to the O*NET API proxy.
"""

import logging
from typing import Any, Dict

from backend.handlers.shared.auth import get_user_id
from backend.handlers.shared.responses import error_response, success_response
from backend.handlers.onet import service

logger = logging.getLogger(__name__)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handle O*NET API requests.

    Routes:
        GET /onet/search?keyword=...  -> search_careers
        GET /onet/careers/{soc_code}   -> get_career_detail

    Args:
        event: API Gateway event.
        context: Lambda context.

    Returns:
        API Gateway-compatible response.
    """
    user_id = get_user_id(event)
    if not user_id:
        return error_response("Unauthorized", 401)

    resource = event.get("resource", "")

    try:
        if resource == "/onet/search":
            params = event.get("queryStringParameters") or {}
            keyword = params.get("keyword", "").strip()
            if not keyword:
                return error_response("keyword query parameter is required", 400)
            result = service.search_careers(keyword)
            return success_response(result)

        if resource == "/onet/careers/{soc_code}":
            path_params = event.get("pathParameters") or {}
            soc_code = path_params.get("soc_code", "").strip()
            if not soc_code:
                return error_response("soc_code path parameter is required", 400)
            result = service.get_career_detail(soc_code)
            return success_response(result)

        return error_response("Not found", 404)

    except Exception:
        logger.exception("O*NET handler failed")
        return error_response("Internal server error", 500)
