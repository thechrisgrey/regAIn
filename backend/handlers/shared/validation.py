"""Input validation helpers for Lambda handlers.

Provides body size validation and field length checks to guard
against oversized payloads and excessively long field values.
"""

import json
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

DEFAULT_MAX_BODY_BYTES = 1_048_576  # 1 MB
DEFAULT_MAX_FIELD_LENGTH = 10_000


def validate_body(
    event: Dict[str, Any],
    max_bytes: int = DEFAULT_MAX_BODY_BYTES,
) -> Dict[str, Any]:
    """Parse and validate the request body size.

    Args:
        event: API Gateway event dict.
        max_bytes: Maximum allowed body size in bytes.

    Returns:
        Parsed body dict.

    Raises:
        ValueError: If body is too large, missing, or invalid JSON.
    """
    raw_body = event.get("body")
    if raw_body is None:
        raw_body = "{}"

    if isinstance(raw_body, str) and len(raw_body.encode("utf-8")) > max_bytes:
        raise ValueError(f"Request body exceeds maximum size of {max_bytes} bytes")

    try:
        body = json.loads(raw_body)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError("Invalid JSON body") from exc

    if not isinstance(body, dict):
        raise ValueError("Request body must be a JSON object")

    return body


def validate_string_field(
    body: Dict[str, Any],
    field: str,
    max_length: int = DEFAULT_MAX_FIELD_LENGTH,
    required: bool = False,
) -> str | None:
    """Validate a string field exists and is within length limits.

    Args:
        body: Parsed request body.
        field: Field name to validate.
        max_length: Maximum allowed string length.
        required: If True, raises ValueError when field is missing or empty.

    Returns:
        The field value as a string, or None if not present and not required.

    Raises:
        ValueError: If field exceeds max_length or is missing when required.
    """
    value = body.get(field)
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise ValueError(f"Missing required field: {field}")
        return None

    if not isinstance(value, str):
        value = str(value)

    if len(value) > max_length:
        raise ValueError(f"Field '{field}' exceeds maximum length of {max_length}")

    return value
