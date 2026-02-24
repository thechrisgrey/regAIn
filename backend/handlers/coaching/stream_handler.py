"""Chat streaming Lambda handler for WebSocket API Gateway.

Handles WebSocket lifecycle events ($connect, $default, $disconnect)
for text-based coaching with progressive token streaming. Uses the
Strands SDK callback_handler to push text chunks to the client as
they are generated, and Strands hooks to send tool execution status.
"""

import base64
import json
import logging
import os
import threading
from typing import Any, Callable, Dict, Optional

import boto3

from backend.handlers.shared.ws_connections import (
    delete_connection,
    load_connection,
    store_connection,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Module-level state for Lambda instance reuse.
_connections: Dict[str, Dict[str, str]] = {}  # connection_id -> {user_id, jwt_token}

# Lazy-initialized API Gateway management client cache.
_apigw_clients: Dict[str, Any] = {}

# Lambda timeout minus safety margin (seconds).
_LAMBDA_TIMEOUT = int(os.environ.get("LAMBDA_TIMEOUT_SECONDS", "120"))
_SAFETY_MARGIN = 10


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


class _StreamingToolHooks:
    """Strands HookProvider that sends WebSocket messages during tool execution.

    This keeps the frontend informed when the agent is calling tools (reading
    profile, checking missions, etc.) so it can display a "thinking" indicator
    instead of appearing stuck.
    """

    def __init__(self, send_fn: Callable[[Dict[str, Any]], None]) -> None:
        self._send = send_fn

    def register_hooks(self, registry: Any, **kwargs: Any) -> None:
        from strands.hooks import BeforeToolCallEvent, AfterToolCallEvent

        registry.add_callback(BeforeToolCallEvent, self._on_before_tool)
        registry.add_callback(AfterToolCallEvent, self._on_after_tool)

    def _on_before_tool(self, event: Any) -> None:
        tool_name = event.tool_use.get("name", "")
        logger.info("Agent calling tool: %s", tool_name)
        self._send({"type": "thinking", "tool": tool_name})

    def _on_after_tool(self, event: Any) -> None:
        tool_name = event.tool_use.get("name", "")
        logger.info("Tool completed: %s", tool_name)
        self._send({"type": "thinking_complete", "tool": tool_name})


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

    conn_data = {"user_id": user_id, "jwt_token": token}
    _connections[connection_id] = conn_data
    store_connection(connection_id, conn_data)

    logger.info("Chat connection %s established for user %s", connection_id, user_id)
    return {"statusCode": 200}


def _handle_disconnect(event: Dict[str, Any]) -> Dict[str, Any]:
    """Clean up on WebSocket disconnect."""
    connection_id = event["requestContext"]["connectionId"]
    _connections.pop(connection_id, None)
    delete_connection(connection_id)
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
        conn_info = load_connection(connection_id)
        if conn_info:
            _connections[connection_id] = conn_info

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

    # Helper that captures event/connection_id for WebSocket sends.
    def send_ws(data: Dict[str, Any]) -> None:
        _post_to_connection(event, connection_id, data)

    # Build a streaming callback that pushes delta chunks to the client.
    def stream_callback(**kwargs):
        if "data" in kwargs:
            send_ws({"type": "delta", "text": kwargs["data"]})

    # Safety timer: send an error before Lambda is killed by timeout.
    timed_out = threading.Event()

    def _on_timeout():
        timed_out.set()
        logger.warning("Safety timeout fired for user %s", user_id)
        send_ws({
            "type": "error",
            "message": "Response took too long. Please try a simpler question.",
        })

    safety_timer = threading.Timer(_LAMBDA_TIMEOUT - _SAFETY_MARGIN, _on_timeout)
    safety_timer.daemon = True
    safety_timer.start()

    try:
        from backend.agents.coaching.agent import create_coaching_agent
        from backend.agents.coaching.instrumentation import SessionTracer

        tool_hooks = _StreamingToolHooks(send_fn=send_ws)

        tracer = SessionTracer(session_id=connection_id, user_id=user_id)
        with tracer.coaching_session():
            agent = create_coaching_agent(
                user_id=user_id,
                jwt_token=jwt_token,
                callback_handler=stream_callback,
                hooks=[tool_hooks],
            )
            result = agent(
                f"[session_type={session_type}] [user_id={user_id}] {message}"
            )

        # Only send done if we haven't already sent a timeout error.
        if not timed_out.is_set():
            send_ws({"type": "done", "text": str(result)})
    except Exception:
        logger.exception("Chat stream failed for user %s", user_id)
        if not timed_out.is_set():
            send_ws({
                "type": "error",
                "message": "Coaching agent is temporarily unavailable. Please try again.",
            })
    finally:
        safety_timer.cancel()

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
