"""API response helpers.

Provides consistent response formatting with CORS headers
for all Lambda handlers.
"""

import json
from typing import Any, Dict

CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
}


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
        "body": json.dumps(data),
    }


def error_response(message: str, status_code: int = 400) -> Dict[str, Any]:
    """Return an error API response.

    Args:
        message: Human-readable error message.
        status_code: HTTP status code (default 400).

    Returns:
        API Gateway-compatible response dict.
    """
    return {
        "statusCode": status_code,
        "headers": CORS_HEADERS,
        "body": json.dumps({"error": message}),
    }
