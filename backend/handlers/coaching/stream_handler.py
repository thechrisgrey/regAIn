"""Chat streaming Lambda handler for WebSocket API Gateway.

Handles WebSocket lifecycle events ($connect, $default, $disconnect)
for text-based coaching with progressive token streaming. Uses the
Strands SDK callback_handler to push text chunks to the client as
they are generated, and Strands hooks to send tool execution status.
"""

import json
import logging
import os
import threading
import time
from typing import Any, Callable, Dict, Optional

import boto3

from backend.handlers.shared.ws_connections import (
    delete_connection,
    load_connection,
    store_connection,
    update_connection,
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

# Auth deadline: max seconds to send auth message after unauthenticated $connect.
_AUTH_DEADLINE_SECONDS = 10


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
    """Validate a Cognito JWT token and extract the user ID.

    Verifies the RS256 signature against the Cognito JWKS endpoint,
    checks expiry, issuer, and token_use claims.
    """
    from backend.handlers.shared.jwt import verify_cognito_token

    return verify_cognito_token(token)


def _handle_connect(event: Dict[str, Any]) -> Dict[str, Any]:
    """Accept WebSocket connection and store connection metadata.

    Supports both query-param auth (legacy) and first-message auth.
    If a token is present in query params, validate immediately.
    Otherwise, accept unauthenticated and require auth in $default.
    """
    connection_id = event["requestContext"]["connectionId"]
    query_params = event.get("queryStringParameters") or {}
    token = query_params.get("token", "")

    # Try query-param auth first (legacy path).
    if token:
        user_id = _validate_cognito_token(token)
        if not user_id:
            logger.warning("Auth failed for chat connection %s", connection_id)
            return {"statusCode": 401}

        conn_data = {
            "user_id": user_id,
            "authenticated": "true",
            "connect_time": str(time.time()),
        }
        _connections[connection_id] = conn_data
        store_connection(connection_id, conn_data)

        from backend.handlers.shared.metrics import emit_metric
        emit_metric("coaching_session_started")

        logger.info("Chat connection %s established for user %s", connection_id, user_id)
        return {"statusCode": 200}

    # No token in query params — accept unauthenticated, require first-message auth.
    conn_data = {
        "user_id": "",
        "authenticated": "false",
        "auth_deadline": str(time.time() + _AUTH_DEADLINE_SECONDS),
    }
    _connections[connection_id] = conn_data
    store_connection(connection_id, conn_data)

    logger.info("Chat connection %s accepted unauthenticated (first-message auth required)", connection_id)
    return {"statusCode": 200}


def _handle_disconnect(event: Dict[str, Any]) -> Dict[str, Any]:
    """Clean up on WebSocket disconnect and persist session memory."""
    connection_id = event["requestContext"]["connectionId"]
    conn_info = _connections.pop(connection_id, None)

    # Also try DynamoDB in case module-level dict missed the connection.
    if not conn_info:
        conn_info = load_connection(connection_id)

    delete_connection(connection_id)

    # Store session-end memory for continuity across sessions.
    user_id = conn_info.get("user_id", "") if conn_info else ""
    if user_id:
        try:
            from backend.agents.coaching.tools import store_memory

            session_type = conn_info.get("session_type", "general") if conn_info else "general"
            store_memory(
                user_id=user_id,
                content=f"Text coaching session ended. Session type: {session_type}. "
                "The user disconnected from the chat interface.",
            )
        except Exception:
            logger.exception(
                "Failed to store disconnect memory for user %s", user_id
            )

    # Emit coaching session duration metric.
    connect_time_str = conn_info.get("connect_time", "") if conn_info else ""
    if connect_time_str:
        try:
            duration = time.time() - float(connect_time_str)
            from backend.handlers.shared.metrics import emit_metric
            emit_metric("coaching_session_duration", value=duration, unit="Seconds")
        except (ValueError, TypeError):
            pass

    logger.info("Chat connection %s disconnected", connection_id)
    return {"statusCode": 200}


def _handle_default(event: Dict[str, Any]) -> Dict[str, Any]:
    """Handle incoming chat messages with streaming response.

    Expects a JSON body with:
      - message: str (the user's text)
      - session_type: str (onboarding | checkin | general)
      - token: str (JWT, used if not already cached from $connect)

    Or, for first-message auth:
      - type: "auth"
      - token: str (JWT)
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

    # Parse the incoming message payload.
    try:
        body = json.loads(event.get("body", "{}"))
    except (json.JSONDecodeError, TypeError):
        _post_to_connection(event, connection_id, {
            "type": "error",
            "message": "Invalid JSON payload",
        })
        return {"statusCode": 200}

    # Handle first-message auth for unauthenticated connections.
    if conn_info.get("authenticated") == "false":
        if body.get("type") == "auth":
            token = body.get("token", "")
            # Check auth deadline.
            deadline = float(conn_info.get("auth_deadline", "0"))
            if deadline and time.time() > deadline:
                _post_to_connection(event, connection_id, {
                    "type": "error",
                    "message": "Authentication deadline exceeded. Please reconnect.",
                })
                return {"statusCode": 200}

            user_id = _validate_cognito_token(token)
            if not user_id:
                _post_to_connection(event, connection_id, {
                    "type": "error",
                    "message": "Authentication failed. Please reconnect.",
                })
                return {"statusCode": 200}

            # Update connection as authenticated.
            conn_info["user_id"] = user_id
            conn_info["authenticated"] = "true"
            conn_info["connect_time"] = str(time.time())
            _connections[connection_id] = conn_info
            update_connection(connection_id, {
                "user_id": user_id,
                "authenticated": "true",
                "connect_time": conn_info["connect_time"],
            })

            _post_to_connection(event, connection_id, {
                "type": "auth_success",
            })

            from backend.handlers.shared.metrics import emit_metric
            emit_metric("coaching_session_started")

            logger.info("Chat connection %s authenticated via first-message for user %s", connection_id, user_id)
            return {"statusCode": 200}
        else:
            _post_to_connection(event, connection_id, {
                "type": "error",
                "message": "Authentication required. Send {\"type\":\"auth\",\"token\":\"...\"} first.",
            })
            return {"statusCode": 200}

    user_id = conn_info["user_id"]

    message = body.get("message", "").strip()
    if not message:
        _post_to_connection(event, connection_id, {
            "type": "error",
            "message": "Missing required field: message",
        })
        return {"statusCode": 200}

    session_type = body.get("session_type", "checkin")

    # Track session type on the connection for disconnect memory.
    if conn_info and "session_type" not in conn_info:
        conn_info["session_type"] = session_type
        _connections[connection_id] = conn_info

    # Token from payload (used by create_coaching_agent for REST API calls).
    jwt_token = body.get("token", "")

    # Helper that captures event/connection_id for WebSocket sends.
    def send_ws(data: Dict[str, Any]) -> None:
        _post_to_connection(event, connection_id, data)

    # Build a streaming callback that pushes delta chunks to the client.
    # The connection_stale flag is set by the heartbeat thread if a send fails.
    connection_stale = threading.Event()

    def stream_callback(**kwargs):
        if connection_stale.is_set():
            return
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

    # Heartbeat thread: send {"type":"heartbeat"} every 30s to keep the
    # connection alive and detect stale clients early.
    streaming_done = threading.Event()

    def _heartbeat_loop():
        while not streaming_done.wait(timeout=30):
            try:
                send_ws({"type": "heartbeat"})
            except Exception:
                logger.warning("Heartbeat failed for connection %s, marking stale", connection_id)
                connection_stale.set()
                break

    heartbeat_thread = threading.Thread(target=_heartbeat_loop, daemon=True)
    heartbeat_thread.start()

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
        if not timed_out.is_set() and not connection_stale.is_set():
            send_ws({"type": "done", "text": str(result)})
    except Exception:
        logger.exception("Chat stream failed for user %s", user_id)
        if not timed_out.is_set() and not connection_stale.is_set():
            send_ws({
                "type": "error",
                "message": "Coaching agent is temporarily unavailable. Please try again.",
            })
    finally:
        safety_timer.cancel()
        streaming_done.set()

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
