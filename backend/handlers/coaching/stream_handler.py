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
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

import boto3

from backend.handlers.shared.structured_log import get_logger
from botocore.exceptions import ClientError

from backend.handlers.shared.ws_connections import (
    ConnectionGoneError,
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
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "GoneException":
            raise ConnectionGoneError(connection_id) from exc
        logger.exception("Failed to post to connection %s", connection_id)
    except Exception:
        logger.exception("Failed to post to connection %s", connection_id)


class _StreamingToolHooks:
    """Strands HookProvider that sends WebSocket messages during tool execution.

    This keeps the frontend informed when the agent is calling tools (reading
    profile, checking missions, etc.) so it can display a "thinking" indicator
    instead of appearing stuck.
    """

    def __init__(self, send_fn: Callable[[Dict[str, Any]], None], tracer: Any = None) -> None:
        self._send = send_fn
        self._tracer = tracer
        self._tool_spans: Dict[str, Any] = {}
        self._tool_start_times: Dict[str, float] = {}

    def register_hooks(self, registry: Any, **kwargs: Any) -> None:
        from strands.hooks import BeforeToolCallEvent, AfterToolCallEvent

        registry.add_callback(BeforeToolCallEvent, self._on_before_tool)
        registry.add_callback(AfterToolCallEvent, self._on_after_tool)

    def _on_before_tool(self, event: Any) -> None:
        tool_name = event.tool_use.get("name", "")
        logger.info("Agent calling tool: %s", tool_name)
        if self._tracer:
            cm = self._tracer.tool_invocation(tool_name)
            cm.__enter__()
            self._tool_spans[tool_name] = cm
        self._tool_start_times[tool_name] = time.time()
        try:
            self._send({"type": "thinking", "tool": tool_name})
        except ConnectionGoneError:
            pass

    def _on_after_tool(self, event: Any) -> None:
        tool_name = event.tool_use.get("name", "")
        logger.info("Tool completed: %s", tool_name)
        cm = self._tool_spans.pop(tool_name, None)
        if cm:
            cm.__exit__(None, None, None)
        start = self._tool_start_times.pop(tool_name, None)
        if start:
            duration_ms = (time.time() - start) * 1000
            try:
                from backend.handlers.shared.metrics import emit_metric
                emit_metric("ToolInvocationCount", dimensions={"ToolName": tool_name}, namespace="REGAIN/Coaching")
                emit_metric("ToolInvocationLatency", value=duration_ms, unit="Milliseconds", dimensions={"ToolName": tool_name}, namespace="REGAIN/Coaching")
            except Exception:
                pass
        try:
            self._send({"type": "thinking_complete", "tool": tool_name})
        except ConnectionGoneError:
            pass


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
    slog = get_logger(event, __name__)
    connection_id = event["requestContext"]["connectionId"]
    query_params = event.get("queryStringParameters") or {}
    token = query_params.get("token", "")

    # Try query-param auth first (legacy path).
    if token:
        user_id = _validate_cognito_token(token)
        if not user_id:
            slog.warning("Auth failed for chat connection %s", connection_id)
            return {"statusCode": 401}

        trace_id = str(uuid.uuid4())
        conn_data = {
            "user_id": user_id,
            "authenticated": "true",
            "connect_time": str(time.time()),
            "trace_id": trace_id,
        }
        _connections[connection_id] = conn_data
        store_connection(connection_id, conn_data)

        from backend.handlers.shared.metrics import emit_metric
        emit_metric("coaching_session_started")
        emit_metric("SessionCount", namespace="REGAIN/Coaching")

        slog.info("Chat connection %s established for user %s (trace=%s)", connection_id, user_id, trace_id)
        return {"statusCode": 200}

    # No token in query params — accept unauthenticated, require first-message auth.
    trace_id = str(uuid.uuid4())
    conn_data = {
        "user_id": "",
        "authenticated": "false",
        "auth_deadline": str(time.time() + _AUTH_DEADLINE_SECONDS),
        "trace_id": trace_id,
    }
    _connections[connection_id] = conn_data
    store_connection(connection_id, conn_data)

    slog.info("Chat connection %s accepted unauthenticated (first-message auth required)", connection_id)
    return {"statusCode": 200}


def _handle_disconnect(event: Dict[str, Any]) -> Dict[str, Any]:
    """Clean up on WebSocket disconnect and persist session memory."""
    slog = get_logger(event, __name__)
    connection_id = event["requestContext"]["connectionId"]
    conn_info = _connections.pop(connection_id, None)

    # Also try DynamoDB in case module-level dict missed the connection.
    if not conn_info:
        conn_info = load_connection(connection_id)

    # Evict cached agent components for this connection.
    from backend.agents.coaching.agent import evict_cached_components
    evict_cached_components(connection_id)

    delete_connection(connection_id)

    trace_id = conn_info.get("trace_id", "") if conn_info else ""

    user_id = conn_info.get("user_id", "") if conn_info else ""
    authenticated = conn_info.get("authenticated", "false") if conn_info else "false"
    if user_id:
        slog.info("Coaching session ended for user %s", user_id)

    # Emit coaching session duration metric (only for authenticated sessions).
    connect_time_str = conn_info.get("connect_time", "") if conn_info else ""
    if connect_time_str and authenticated == "true":
        try:
            duration = time.time() - float(connect_time_str)
            from backend.handlers.shared.metrics import emit_metric
            emit_metric("coaching_session_duration", value=duration, unit="Seconds")
        except (ValueError, TypeError):
            pass

    slog.info("Chat connection %s disconnected (trace=%s)", connection_id, trace_id)
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
    slog = get_logger(event, __name__)
    connection_id = event["requestContext"]["connectionId"]
    conn_info = _connections.get(connection_id)

    if not conn_info:
        conn_info = load_connection(connection_id)
        if conn_info:
            _connections[connection_id] = conn_info

    if not conn_info:
        slog.warning("No user mapping for chat connection %s", connection_id)
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
            emit_metric("SessionCount", namespace="REGAIN/Coaching")

            slog.info("Chat connection %s authenticated via first-message for user %s", connection_id, user_id)
            return {"statusCode": 200}
        else:
            _post_to_connection(event, connection_id, {
                "type": "error",
                "message": "Authentication required. Send {\"type\":\"auth\",\"token\":\"...\"} first.",
            })
            return {"statusCode": 200}

    user_id = conn_info["user_id"]
    trace_id = conn_info.get("trace_id", "")

    # Helper that captures event/connection_id for WebSocket sends.
    # Defined early so new message type handlers can use it.
    def send_ws(data: Dict[str, Any]) -> None:
        _post_to_connection(event, connection_id, data)

    # --- New message type dispatch ---
    msg_type = body.get("type", "")

    if msg_type == "sync":
        from backend.handlers.shared.thread import load_active_thread, flush_pending_messages
        thread = load_active_thread(user_id)
        pending = flush_pending_messages(user_id)
        try:
            send_ws({
                "type": "thread_meta",
                "tokenEstimate": thread["tokenEstimate"],
                "tokenBudget": thread["maxTokenBudget"],
                "attentionMode": thread["attentionMode"],
                "pendingMessages": pending,
            })
        except ConnectionGoneError:
            pass
        return {"statusCode": 200}

    if msg_type == "attention_mode":
        mode = body.get("mode", "")
        try:
            from backend.handlers.shared.thread import update_attention_mode as set_attention_mode
            set_attention_mode(user_id, mode)
            # Evict cached agent — system prompt depends on attention_mode.
            from backend.agents.coaching.agent import evict_cached_components
            evict_cached_components(connection_id)
        except ValueError:
            _post_to_connection(event, connection_id, {"type": "error", "message": f"Invalid mode: {mode}"})
        return {"statusCode": 200}

    if msg_type == "compact":
        from backend.handlers.shared.thread import load_active_thread, compact_thread
        thread = load_active_thread(user_id)
        if not thread["turns"]:
            return {"statusCode": 200}

        try:
            from backend.agents.coaching.agent import create_coaching_agent

            agent = create_coaching_agent(
                user_id=user_id,
                jwt_token=body.get("token", ""),
                conversation_history=thread["turns"],
                attention_mode=thread["attentionMode"],
                session_id=connection_id,
            )
            summary_result = agent(
                "[system] Summarize the conversation so far into the most important context needed to continue coaching this user. "
                "Preserve: active mission state, recent evidence logged, behavioral patterns observed, commitments made, and unresolved topics. "
                "Target ~15% of current thread length. Output ONLY the summary, no preamble."
            )

            new_estimate = compact_thread(user_id, thread["turns"], str(summary_result))

            send_ws({
                "type": "thread_meta",
                "tokenEstimate": new_estimate,
                "tokenBudget": thread["maxTokenBudget"],
                "attentionMode": thread["attentionMode"],
            })
        except Exception:
            slog.exception("Compaction failed for user %s", user_id)
            _post_to_connection(event, connection_id, {"type": "error", "message": "Compaction failed. Please try again."})

        return {"statusCode": 200}

    if msg_type == "action_event":
        action = body.get("action", "")
        payload = body.get("payload", {})
        if not action:
            return {"statusCode": 200}

        from backend.handlers.shared.thread import load_active_thread, append_turns, add_pending_message
        now = datetime.now(timezone.utc).isoformat()
        event_content = f"User action: {action}"
        if payload:
            details = ", ".join(f"{k}={v}" for k, v in payload.items())
            event_content += f" ({details})"

        event_turn = {"role": "system", "content": event_content, "timestamp": now, "source": "action_event"}
        append_turns(user_id, [event_turn])

        thread = load_active_thread(user_id)
        mode = thread["attentionMode"]

        if mode == "dnd":
            return {"statusCode": 200}

        try:
            from backend.agents.coaching.agent import create_coaching_agent

            agent = create_coaching_agent(
                user_id=user_id,
                jwt_token=body.get("token", ""),
                conversation_history=thread["turns"],
                attention_mode=mode,
                session_id=connection_id,
            )
            result = agent(f"[action_event] {event_content}")
            response_text = str(result)

            if "[no_response]" in response_text:
                return {"statusCode": 200}

            append_turns(user_id, [
                {"role": "assistant", "content": response_text, "timestamp": datetime.now(timezone.utc).isoformat(), "source": "chat"},
            ])

            try:
                send_ws({"type": "proactive", "text": response_text})
            except ConnectionGoneError:
                add_pending_message(user_id, {"type": "proactive", "text": response_text})

        except Exception:
            slog.exception("Action event agent invocation failed for user %s", user_id)

        return {"statusCode": 200}

    # --- End new message type dispatch ---

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

    # Load the conversation thread for context.
    from backend.handlers.shared.thread import load_active_thread, append_turns, compact_thread
    thread = load_active_thread(user_id)

    # Build a streaming callback that pushes delta chunks to the client.
    # The connection_stale flag is set by the heartbeat thread if a send fails.
    connection_stale = threading.Event()

    def stream_callback(**kwargs):
        if connection_stale.is_set():
            return
        if "data" in kwargs:
            try:
                send_ws({"type": "delta", "text": kwargs["data"]})
            except ConnectionGoneError:
                connection_stale.set()

    # Safety timer: send an error before Lambda is killed by timeout.
    timed_out = threading.Event()

    def _on_timeout():
        timed_out.set()
        slog.warning("Safety timeout fired for user %s", user_id)
        try:
            send_ws({
                "type": "error",
                "message": "Response took too long. Please try a simpler question.",
            })
        except ConnectionGoneError:
            pass

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
            except ConnectionGoneError:
                logger.info("Client disconnected (heartbeat), marking stale: %s", connection_id)
                connection_stale.set()
                break
            except Exception:
                logger.warning("Heartbeat failed for connection %s, marking stale", connection_id)
                connection_stale.set()
                break

    heartbeat_thread = threading.Thread(target=_heartbeat_loop, daemon=True)
    heartbeat_thread.start()

    try:
        from backend.agents.coaching.agent import create_coaching_agent
        from backend.agents.coaching.instrumentation import SessionTracer

        tracer = SessionTracer(session_id=connection_id, user_id=user_id)
        tool_hooks = _StreamingToolHooks(send_fn=send_ws, tracer=tracer)

        # Auto-compact if at token budget.
        if thread["tokenEstimate"] >= thread["maxTokenBudget"] and thread["turns"]:
            try:
                compact_agent = create_coaching_agent(
                    user_id=user_id,
                    jwt_token=jwt_token,
                    conversation_history=thread["turns"],
                    attention_mode=thread["attentionMode"],
                    session_id=connection_id,
                )
                summary_result = compact_agent(
                    "[system] Summarize the conversation so far. Preserve: active mission state, recent evidence, behavioral patterns, commitments, unresolved topics. Output ONLY the summary."
                )
                compact_thread(user_id, thread["turns"], str(summary_result))
                # Evict cache — conversation history changed after compaction.
                from backend.agents.coaching.agent import evict_cached_components
                evict_cached_components(connection_id)
                thread = load_active_thread(user_id)
            except Exception:
                slog.warning("Auto-compaction failed for user %s, proceeding with full thread", user_id)

        with tracer.coaching_session():
            agent = create_coaching_agent(
                user_id=user_id,
                jwt_token=jwt_token,
                callback_handler=stream_callback,
                hooks=[tool_hooks],
                conversation_history=thread["turns"],
                attention_mode=thread["attentionMode"],
                session_id=connection_id,
                cache_key=connection_id,
            )
            result = agent(
                f"[session_type={session_type}] [user_id={user_id}] {message}"
            )

        # Only send done if we haven't already sent a timeout error.
        if not timed_out.is_set() and not connection_stale.is_set():
            try:
                send_ws({"type": "done", "text": str(result)})
            except ConnectionGoneError:
                connection_stale.set()

            # Persist the user/assistant turn pair and send thread metadata.
            now_ts = datetime.now(timezone.utc).isoformat()
            new_turns = [
                {"role": "user", "content": message, "timestamp": now_ts, "source": "chat"},
                {"role": "assistant", "content": str(result), "timestamp": now_ts, "source": "chat"},
            ]
            append_turns(user_id, new_turns)

            updated_thread = load_active_thread(user_id)
            try:
                send_ws({
                    "type": "thread_meta",
                    "tokenEstimate": updated_thread["tokenEstimate"],
                    "tokenBudget": updated_thread["maxTokenBudget"],
                    "attentionMode": updated_thread["attentionMode"],
                })
            except ConnectionGoneError:
                connection_stale.set()
    except Exception:
        slog.exception("Chat stream failed for user %s (trace=%s)", user_id, trace_id)
        try:
            from backend.handlers.shared.metrics import emit_metric
            emit_metric("ErrorCount", namespace="REGAIN/Coaching")
        except Exception:
            pass
        if not timed_out.is_set() and not connection_stale.is_set():
            try:
                send_ws({
                    "type": "error",
                    "message": "Coaching agent is temporarily unavailable. Please try again.",
                })
            except ConnectionGoneError:
                connection_stale.set()
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
