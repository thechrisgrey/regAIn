"""Missions Lambda handler.

Thin handler for GET /missions, POST /missions/{missionId}/complete,
and POST /missions/generate.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict

from backend.handlers.shared.auth import get_user_id
from backend.handlers.shared.idempotency import with_idempotency
from backend.handlers.shared.responses import error_response, success_response
from backend.handlers.shared.structured_log import get_logger
from backend.handlers.shared.validation import validate_body
from backend.handlers.missions.service import MissionsService, _GenerateRateLimitExceeded

logger = logging.getLogger(__name__)


def _generate_mission(user_id: str, service: MissionsService) -> Dict[str, Any]:
    """Execute mission generation and return API Gateway response."""
    result = service.generate_mission(user_id)
    return success_response(result)


def _complete_mission(
    user_id: str, mission_id: str, body: Dict[str, Any], service: MissionsService,
) -> Dict[str, Any]:
    """Execute mission completion and return API Gateway response."""
    result = service.complete_mission(user_id, mission_id, body)

    if result.get("success") is False:
        error_msg = result.get("error", "")
        if "not found" in error_msg.lower():
            return error_response(error_msg, 404, error_kind="NOT_FOUND")
        return error_response(error_msg, 409, error_kind="CONFLICT")

    return success_response(result)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handle missions API requests.

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
        service = MissionsService()

        if http_method == "GET" and resource == "/missions":
            params = event.get("queryStringParameters") or {}
            limit = min(int(params.get("limit", "50")), 200)
            cursor = params.get("cursor")
            page = service.list_missions(
                user_id, status=params.get("status"), limit=limit, cursor=cursor,
            )
            remaining = service.get_daily_remaining(user_id)
            return success_response({
                "missions": page["items"],
                "items": page["items"],
                "nextCursor": page["nextCursor"],
                **remaining,
            })

        if http_method == "POST" and resource == "/missions/generate":
            return with_idempotency(event, lambda e: _generate_mission(user_id, service))

        if http_method == "POST" and "/complete" in resource:
            mission_id = (event.get("pathParameters") or {}).get("missionId")
            if not mission_id:
                return error_response("Missing missionId path parameter", 400)

            try:
                body = validate_body(event)
            except ValueError as exc:
                return error_response(str(exc), 400)

            # Inject deterministic idempotency key if not provided.
            headers = event.get("headers") or {}
            if not (headers.get("Idempotency-Key") or headers.get("idempotency-key")):
                if event.get("headers") is None:
                    event["headers"] = {}
                event["headers"]["Idempotency-Key"] = f"complete:{user_id}:{mission_id}"

            def _do_complete(e):
                return _complete_mission(user_id, mission_id, body, service)

            return with_idempotency(event, _do_complete)

        return error_response("Not found", 404)

    except _GenerateRateLimitExceeded:
        return error_response(
            "Daily mission generation limit reached. Try again tomorrow.",
            429,
            error_kind="RATE_LIMITED",
        )

    except Exception:
        slog.exception("Missions handler failed")
        return error_response("Internal server error", 500, error_kind="TRANSIENT")
