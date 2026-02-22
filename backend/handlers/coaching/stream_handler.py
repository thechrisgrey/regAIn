"""Chat streaming Lambda handler for WebSocket API Gateway.

Handles WebSocket lifecycle events ($connect, $default, $disconnect)
for text-based coaching with progressive token streaming. Uses the
Strands SDK callback_handler to push text chunks to the client as
they are generated.
"""

import base64
import json
import logging
import os
from typing import Any, Dict, Optional

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Module-level state for Lambda instance reuse.
_connections: Dict[str, Dict[str, str]] = {}  # connection_id -> {user_id, jwt_token}

# Lazy-initialized API Gateway management client cache.
_apigw_clients: Dict[str, Any] = {}


def _get_apigw_client(domain_name: str, stage: str):
    """Get or create an API Gateway Management API client."""
    endpoint = f"https://{domain_name}/{stage}"
    if endpoint not in _apigw_clients:
        _apigw_clients[endpoint] = boto3.client(
            "apigatewaymanagementapi", endpoint_url=endpoint
        )
    return _apigw_clients[endpoint]


def _post_to_connection(
    event: Dict[str, Any],
    connection_id: str,
    data: Dict[str, Any],
) -> None:
    """Send a JSON message back to a WebSocket client."""
    request_ctx = event.get("requestContext", {})
    domain = request_ctx.get("domainName", "")
    stage = request_ctx.get("stage", "")
    if not domain or not stage:
        logger.warning("Missing domainName or stage in requestContext")
        return

    client = _get_apigw_client(domain, stage)
    try:
        client.post_to_connection(
            ConnectionId=connection_id,
            Data=json.dumps(data).encode("utf-8"),
        )
    except Exception:
        logger.exception("Failed to post to connection %s", connection_id)


def _validate_cognito_token(token: str) -> Optional[str]:
    """Decode a Cognito JWT and return the sub claim.

    Full signature verification is handled by API Gateway; this
    extracts the user ID from an already-authenticated token.
    """
    if not token:
        return None
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        payload = parts[1]
        padding = 4 - len(payload) % 4
        if padding != 4:
            payload += "=" * padding
        decoded = json.loads(base64.urlsafe_b64decode(payload))
        user_id = decoded.get("sub")
        return user_id if user_id else None
    except Exception:
        logger.warning("Token validation failed")
        return None


def _handle_connect(event: Dict[str, Any]) -> Dict[str, Any]:
    """Accept WebSocket connection and store connection metadata."""
    connection_id = event["requestContext"]["connectionId"]
    query_params = event.get("queryStringParameters") or {}
    token = query_params.get("token", "")

    user_id = _validate_cognito_token(token)
    if not user_id:
        logger.warning("Auth failed for chat connection %s", connection_id)
        return {"statusCode": 401}

    _connections[connection_id] = {"user_id": user_id, "jwt_token": token}
    logger.info("Chat connection %s established for user %s", connection_id, user_id)
    return {"statusCode": 200}


def _handle_disconnect(event: Dict[str, Any]) -> Dict[str, Any]:
    """Clean up on WebSocket disconnect."""
    connection_id = event["requestContext"]["connectionId"]
    _connections.pop(connection_id, None)
    logger.info("Chat connection %s disconnected", connection_id)
    return {"statusCode": 200}


def _handle_default(event: Dict[str, Any]) -> Dict[str, Any]:
    """Handle incoming chat messages with streaming response.

    Expects a JSON body with:
      - message: str (the user's text)
      - session_type: str (onboarding | checkin | general)
      - token: str (JWT, used if not already cached from $connect)
    """
    connection_id = event["requestContext"]["connectionId"]
    conn_info = _connections.get(connection_id)

    if not conn_info:
        logger.warning("No user mapping for chat connection %s", connection_id)
        return {"statusCode": 400}

    user_id = conn_info["user_id"]
    jwt_token = conn_info["jwt_token"]

    # Parse the incoming message payload.
    try:
        body = json.loads(event.get("body", "{}"))
    except (json.JSONDecodeError, TypeError):
        _post_to_connection(event, connection_id, {
            "type": "error",
            "message": "Invalid JSON payload",
        })
        return {"statusCode": 200}

    message = body.get("message", "").strip()
    if not message:
        _post_to_connection(event, connection_id, {
            "type": "error",
            "message": "Missing required field: message",
        })
        return {"statusCode": 200}

    session_type = body.get("session_type", "checkin")

    # Override token from payload if provided (reconnection scenario).
    if body.get("token"):
        jwt_token = body["token"]

    # Build a streaming callback that pushes delta chunks to the client.
    def stream_callback(**kwargs):
        if "data" in kwargs:
            _post_to_connection(event, connection_id, {
                "type": "delta",
                "text": kwargs["data"],
            })

    try:
        from backend.agents.coaching.agent import create_coaching_agent

        agent = create_coaching_agent(
            user_id=user_id,
            jwt_token=jwt_token,
            callback_handler=stream_callback,
        )
        result = agent(
            f"[session_type={session_type}] [user_id={user_id}] {message}"
        )

        # Send final done message with the complete response.
        _post_to_connection(event, connection_id, {
            "type": "done",
            "text": str(result),
        })
    except Exception:
        logger.exception("Chat stream failed for user %s", user_id)
        _post_to_connection(event, connection_id, {
            "type": "error",
            "message": "Coaching agent is temporarily unavailable. Please try again.",
        })

    return {"statusCode": 200}


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """WebSocket API Gateway Lambda handler for chat streaming."""
    route_key = event.get("requestContext", {}).get("routeKey", "")

    if route_key == "$connect":
        return _handle_connect(event)
    elif route_key == "$disconnect":
        return _handle_disconnect(event)
    else:
        return _handle_default(event)
