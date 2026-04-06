"""API response helpers.

Provides consistent response formatting with CORS headers
for all Lambda handlers.
"""

import json
import os
from decimal import Decimal
from typing import Any, Dict

_ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "https://regain.altivum.ai")

CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": _ALLOWED_ORIGIN,
    "Access-Control-Allow-Headers": "Content-Type,Authorization,Idempotency-Key",
    "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
}


def _default_serializer(obj: Any) -> Any:
    """Handle types that json.dumps cannot serialize natively."""
    if isinstance(obj, Decimal):
        return int(obj) if obj == obj.to_integral_value() else float(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def success_response(data: Dict[str, Any], status_code: int = 200) -> Dict[str, Any]:
    """Return a successful API response.

    Args:
        data: Response payload.
        status_code: HTTP status code (default 200).

    Returns:
        API Gateway-compatible response dict.
    """
    return {
        "statusCode": status_code,
        "headers": CORS_HEADERS,
        "body": json.dumps(data, default=_default_serializer),
    }


def error_response(
    message: str,
    status_code: int = 400,
    error_kind: str | None = None,
) -> Dict[str, Any]:
    """Return an error API response.

    Args:
        message: Human-readable error message.
        status_code: HTTP status code (default 400).
        error_kind: Optional machine-readable error category
            (e.g. NOT_FOUND, CONFLICT, RATE_LIMITED, TRANSIENT).

    Returns:
        API Gateway-compatible response dict.
    """
    body: Dict[str, Any] = {"error": message}
    if error_kind is not None:
        body["errorKind"] = error_kind
    return {
        "statusCode": status_code,
        "headers": CORS_HEADERS,
        "body": json.dumps(body),
    }
