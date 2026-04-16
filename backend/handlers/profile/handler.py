"""Profile Lambda handler.

Thin handler that extracts the user identity, delegates to
ProfileService, and returns a formatted response.
"""

import json
import logging
from typing import Any, Dict

from backend.handlers.shared.auth import get_user_id
from backend.handlers.shared.responses import error_response, success_response
from backend.handlers.shared.structured_log import get_logger
from backend.handlers.profile.service import ProfileService

logger = logging.getLogger(__name__)

_VALID_MODES = {"immediate", "scheduled"}


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handle profile requests (PATCH /profile, DELETE /profile, POST /profile/recover).

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

        if http_method == "PATCH" and resource == "/profile":
            raw_body = event.get("body")
            if not raw_body:
                return error_response(
                    "Missing request body", 400, error_kind="VALIDATION",
                )
            try:
                body = json.loads(raw_body)
            except (json.JSONDecodeError, TypeError):
                return error_response(
                    "Invalid JSON body", 400, error_kind="VALIDATION",
                )

            target_role = body.get("targetRole")
            if not isinstance(target_role, str):
                return error_response(
                    "Missing or invalid field: targetRole",
                    400,
                    error_kind="VALIDATION",
                )

            try:
                result = service.update_target_role(user_id, target_role)
            except ValueError as exc:
                return error_response(str(exc), 400, error_kind="VALIDATION")
            return success_response(result)

        if http_method == "DELETE":
            raw_body = event.get("body")
            if not raw_body:
                return error_response(
                    "Missing required field: mode", 400, error_kind="VALIDATION",
                )
            try:
                body = json.loads(raw_body)
            except (json.JSONDecodeError, TypeError):
                return error_response(
                    "Invalid JSON body", 400, error_kind="VALIDATION",
                )

            mode = body.get("mode")
            if mode not in _VALID_MODES:
                return error_response(
                    "Invalid mode. Must be 'immediate' or 'scheduled'",
                    400,
                    error_kind="VALIDATION",
                )

            if mode == "immediate":
                result = service.hard_delete_user_account(user_id)
            else:
                result = service.soft_delete_user_account(user_id)
            return success_response(result)

        return error_response("Not found", 404)
    except Exception:
        slog.exception("Profile handler failed for user %s", user_id)
        return error_response("Internal server error", 500)
