"""WebSocket connection state persistence via DynamoDB.

API Gateway WebSocket does not guarantee Lambda instance affinity
across $connect, $default, and $disconnect routes. This module
stores connection metadata in DynamoDB so any Lambda container
can retrieve it.
"""

import logging
import os
import time
from typing import Any, Dict, Optional

import boto3

logger = logging.getLogger(__name__)


class ConnectionGoneError(Exception):
    """Raised when a WebSocket client has already disconnected."""


_table = None


def _get_table():
    """Lazily initialize the DynamoDB Table resource."""
    global _table
    if _table is None:
        table_name = os.environ.get("WS_CONNECTIONS_TABLE", "")
        if not table_name:
            raise ValueError("WS_CONNECTIONS_TABLE environment variable not set")
        _table = boto3.resource("dynamodb").Table(table_name)
    return _table


def store_connection(connection_id: str, data: Dict[str, str]) -> None:
    """Store connection metadata in DynamoDB.

    Args:
        connection_id: WebSocket connection ID.
        data: Dict with user_id and optionally session_type and authenticated.
    """
    try:
        item: Dict[str, Any] = {
            "connectionId": connection_id,
            "userId": data.get("user_id", ""),
            "sessionType": data.get("session_type", ""),
            "authenticated": data.get("authenticated", "true"),
            "ttl": int(time.time()) + 3 * 3600,  # 3-hour TTL
        }
        if "auth_deadline" in data:
            item["authDeadline"] = data["auth_deadline"]
        _get_table().put_item(Item=item)
    except Exception:
        logger.exception("Failed to store connection %s in DynamoDB", connection_id)


def update_connection(connection_id: str, data: Dict[str, str]) -> None:
    """Update connection metadata in DynamoDB after authentication.

    Args:
        connection_id: WebSocket connection ID.
        data: Dict with fields to update (user_id, authenticated, etc.).
    """
    try:
        update_parts = []
        expr_values: Dict[str, Any] = {}
        expr_names: Dict[str, str] = {}

        if "user_id" in data:
            update_parts.append("#uid = :uid")
            expr_values[":uid"] = data["user_id"]
            expr_names["#uid"] = "userId"

        if "authenticated" in data:
            update_parts.append("#auth = :auth")
            expr_values[":auth"] = data["authenticated"]
            expr_names["#auth"] = "authenticated"

        if not update_parts:
            return

        _get_table().update_item(
            Key={"connectionId": connection_id},
            UpdateExpression="SET " + ", ".join(update_parts),
            ExpressionAttributeValues=expr_values,
            ExpressionAttributeNames=expr_names,
        )
    except Exception:
        logger.exception("Failed to update connection %s in DynamoDB", connection_id)


def load_connection(connection_id: str) -> Optional[Dict[str, str]]:
    """Load connection metadata from DynamoDB.

    Args:
        connection_id: WebSocket connection ID.

    Returns:
        Dict with user_id and session_type, or None if not found.
    """
    try:
        response = _get_table().get_item(Key={"connectionId": connection_id})
        item = response.get("Item")
        if not item:
            return None
        return {
            "user_id": item.get("userId", ""),
            "session_type": item.get("sessionType", ""),
            "authenticated": item.get("authenticated", "false"),
            "auth_deadline": item.get("authDeadline", ""),
        }
    except Exception:
        logger.exception("Failed to load connection %s from DynamoDB", connection_id)
        return None


def delete_connection(connection_id: str) -> None:
    """Delete connection metadata from DynamoDB.

    Args:
        connection_id: WebSocket connection ID.
    """
    try:
        _get_table().delete_item(Key={"connectionId": connection_id})
    except Exception:
        logger.exception("Failed to delete connection %s from DynamoDB", connection_id)
