"""Idempotency middleware for mutation endpoints.

Uses a DynamoDB table to cache responses for duplicate requests
identified by an Idempotency-Key header. Cached responses expire
after 24 hours (enforced by DynamoDB TTL).
"""

import json
import logging
import os
import time
from typing import Any, Callable, Dict, Optional

import boto3

logger = logging.getLogger(__name__)

_TTL_SECONDS = 86400  # 24 hours


def with_idempotency(
    event: Dict[str, Any],
    handler_fn: Callable[[Dict[str, Any]], Dict[str, Any]],
) -> Dict[str, Any]:
    """Execute handler_fn with idempotency guarantee.

    If an Idempotency-Key header is present and a cached response exists,
    returns the cached response without re-executing handler_fn.

    Args:
        event: API Gateway event.
        handler_fn: The actual handler logic to execute.

    Returns:
        API Gateway-compatible response dict.
    """
    table_name = os.environ.get("IDEMPOTENCY_TABLE")
    if not table_name:
        return handler_fn(event)

    key = _extract_key(event)
    if not key:
        return handler_fn(event)

    table = boto3.resource("dynamodb").Table(table_name)

    # Check for cached response.
    cached = table.get_item(Key={"idempotencyKey": key}).get("Item")
    if cached and cached.get("expiresAt", 0) > int(time.time()):
        logger.info("Idempotency cache hit for key: %s", key)
        return json.loads(cached["responseBody"])

    # Execute and cache (only cache non-5xx responses).
    response = handler_fn(event)

    status_code = response.get("statusCode", 200)
    if status_code < 500:
        try:
            table.put_item(
                Item={
                    "idempotencyKey": key,
                    "responseBody": json.dumps(response, default=str),
                    "statusCode": status_code,
                    "expiresAt": int(time.time()) + _TTL_SECONDS,
                }
            )
        except Exception:
            logger.warning("Failed to cache idempotency response for key: %s", key)

    return response


def _extract_key(event: Dict[str, Any]) -> Optional[str]:
    """Extract idempotency key from the request header.

    Args:
        event: API Gateway event.

    Returns:
        Idempotency key string, or None if no header present.
    """
    headers = event.get("headers") or {}
    return headers.get("Idempotency-Key") or headers.get("idempotency-key")
