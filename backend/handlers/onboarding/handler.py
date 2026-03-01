"""Onboarding Lambda handler.

Thin handler that validates input, delegates to OnboardingService,
and returns a formatted response.
"""

import json
import logging
from typing import Any, Dict

from backend.handlers.shared.auth import get_user_id
from backend.handlers.shared.responses import error_response, success_response
from backend.handlers.shared.structured_log import get_logger
from backend.handlers.shared.validation import validate_body
from backend.handlers.onboarding.service import OnboardingService

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = ["email", "first_name", "last_name", "persona", "target_role"]
VALID_PERSONAS = {"veteran", "ai_displaced", "career_pivoter"}

# Frontend sends camelCase; backend uses snake_case.
_CAMEL_TO_SNAKE = {
    "targetRole": "target_role",
    "firstName": "first_name",
    "lastName": "last_name",
    "currentRole": "current_role",
    "yearsExperience": "years_experience",
    "yearsInRole": "years_in_role",
    "highestPosition": "highest_position",
    "coachNotes": "coach_notes",
}


def _normalize_keys(body: Dict[str, Any]) -> Dict[str, Any]:
    """Convert known camelCase keys to snake_case."""
    return {_CAMEL_TO_SNAKE.get(k, k): v for k, v in body.items()}


def _validate_input(body: Dict[str, Any]) -> str | None:
    """Return an error message if input is invalid, else None."""
    for field in REQUIRED_FIELDS:
        if field not in body:
            return f"Missing required field: {field}"

    if body["persona"] not in VALID_PERSONAS:
        return f"Invalid persona: {body['persona']}"

    return None


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handle POST /onboarding requests.

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
        body = _normalize_keys(validate_body(event))
    except ValueError as exc:
        return error_response(str(exc), 400)

    validation_error = _validate_input(body)
    if validation_error:
        return error_response(validation_error, 400)

    try:
        service = OnboardingService()
        result = service.create_profile(user_id, body)
        return success_response(result, 201)
    except Exception:
        slog.exception("Onboarding failed")
        return error_response("Internal server error", 500)
