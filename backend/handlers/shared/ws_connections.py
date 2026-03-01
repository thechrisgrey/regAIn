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
        data: Dict with user_id and optionally session_type.
    """
    try:
        item: Dict[str, Any] = {
            "connectionId": connection_id,
            "userId": data["user_id"],
            "sessionType": data.get("session_type", ""),
            "ttl": int(time.time()) + 3 * 3600,  # 3-hour TTL
        }
        _get_table().put_item(Item=item)
    except Exception:
        logger.exception("Failed to store connection %s in DynamoDB", connection_id)


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
            "user_id": item["userId"],
            "session_type": item.get("sessionType", ""),
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
