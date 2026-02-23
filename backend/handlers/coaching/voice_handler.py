"""Voice session Lambda handler for WebSocket API Gateway.

Manages Nova 2 Sonic bidirectional streaming sessions for voice-based
coaching interactions. Handles WebSocket lifecycle events ($connect,
$default, $disconnect) and bridges audio between the frontend and
Amazon Bedrock Nova Sonic via the shared NovaSonicSession client.
"""

import base64
import importlib
import inspect
import json
import logging
import os
from typing import Any, Dict, Optional

import boto3

from backend.handlers.shared.nova_sonic import (
    NovaSonicSession,
    build_tool_specs,
    ensure_event_loop,
    run_async,
)
from backend.handlers.shared.ws_connections import (
    delete_connection,
    load_connection,
    store_connection,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Module-level state for Lambda instance reuse.
# Each WebSocket connection is sticky to one Lambda instance,
# so in-memory mappings are safe for the connection lifetime.
_connections: Dict[str, Dict[str, str]] = {}  # connection_id -> {user_id, jwt_token}
_sessions: Dict[str, Dict[str, Any]] = {}  # connection_id -> session state

# Lazy-initialized clients
_apigw_clients: Dict[str, Any] = {}  # endpoint -> client

# Load Strands tools for Nova Sonic tool registration.
_tools_mod = importlib.import_module("backend.agents.coaching.tools")
_TOOL_FUNCTIONS = [
    _tools_mod.read_user_profile,
    _tools_mod.update_user_profile,
    _tools_mod.get_campaign_status,
    _tools_mod.create_campaign,
    _tools_mod.get_current_mission,
    _tools_mod.generate_mission,
    _tools_mod.complete_mission,
    _tools_mod.log_evidence,
    _tools_mod.get_evidence_summary,
    _tools_mod.get_market_insights,
    _tools_mod.recall_memory,
    _tools_mod.store_memory,
]
_TOOL_MAP: Dict[str, Any] = {
    getattr(f, "__name__", str(f)): f for f in _TOOL_FUNCTIONS
}


def _get_apigw_client(domain_name: str, stage: str):
    """Get or create an API Gateway Management API client.

    Args:
        domain_name: WebSocket API domain from the request context.
        stage: Deployment stage from the request context.

    Returns:
        A boto3 client for apigatewaymanagementapi.
    """
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
    """Send a message back to a WebSocket client.

    Args:
        event: The original Lambda event (used to extract domain/stage).
        connection_id: The WebSocket connection ID.
        data: The payload to send as JSON.
    """
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
        logger.exception("Failed to post message to connection %s", connection_id)


def _validate_cognito_token(token: str) -> Optional[str]:
    """Validate a Cognito JWT token and extract the user ID.

    Decodes the JWT payload without full verification -- API Gateway
    authorizer handles primary auth.

    Args:
        token: The JWT token string from the query string.

    Returns:
        The user_id (sub claim) if valid, None otherwise.
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


def _get_system_prompt(user_id: str) -> str:
    """Get the coaching system prompt with the user's skill tags."""
    from backend.agents.coaching.prompts import get_system_prompt

    valid_tags = _tools_mod.get_valid_skill_tags(user_id)
    return get_system_prompt(valid_skill_tags=valid_tags or None)


def _execute_tool(user_id: str, tool_name: str, tool_use_id: str, args: dict) -> Any:
    """Execute a Strands tool function, injecting user_id as needed.

    Args:
        user_id: The authenticated user's ID.
        tool_name: The tool function name.
        tool_use_id: The Nova Sonic tool use ID (for logging).
        args: Tool arguments from Nova Sonic.

    Returns:
        The tool function's result.
    """
    func = _TOOL_MAP.get(tool_name)
    if not func:
        return {"error": f"Unknown tool: {tool_name}"}

    try:
        sig = inspect.signature(func)
    except (ValueError, TypeError):
        sig = inspect.signature(getattr(func, "__wrapped__", func))

    if "user_id" in sig.parameters:
        args["user_id"] = user_id

    logger.info("Executing tool %s for user %s", tool_name, user_id)
    return func(**args)


def _handle_connect(event: Dict[str, Any]) -> Dict[str, Any]:
    """Handle WebSocket $connect event.

    Extracts the Cognito token from the query string, validates it,
    and stores the connection_id -> user_id mapping.

    Args:
        event: API Gateway WebSocket $connect event.

    Returns:
        Response dict with statusCode 200 on success, 401 on auth failure.
    """
    connection_id = event["requestContext"]["connectionId"]
    query_params = event.get("queryStringParameters") or {}
    token = query_params.get("token", "")

    user_id = _validate_cognito_token(token)
    if not user_id:
        logger.warning("Auth failed for connection %s", connection_id)
        return {"statusCode": 401}

    conn_data = {"user_id": user_id, "jwt_token": token}
    _connections[connection_id] = conn_data
    store_connection(connection_id, conn_data)

    logger.info(
        "Connection %s established for user %s", connection_id, user_id
    )
    return {"statusCode": 200}


def _handle_default(event: Dict[str, Any]) -> Dict[str, Any]:
    """Handle WebSocket $default event (audio frames).

    On the first frame, creates a NovaSonicSession with coaching tools
    and system prompt. Subsequent frames forward audio to Nova Sonic.

    Args:
        event: API Gateway WebSocket $default event.

    Returns:
        Response dict with statusCode 200.
    """
    connection_id = event["requestContext"]["connectionId"]
    conn_info = _connections.get(connection_id)

    if not conn_info:
        conn_info = load_connection(connection_id)
        if conn_info:
            _connections[connection_id] = conn_info

    if not conn_info:
        logger.warning("No user mapping for connection %s", connection_id)
        return {"statusCode": 400}

    user_id = conn_info["user_id"]

    # Create Nova Sonic session on first audio frame.
    if connection_id not in _sessions:
        try:
            ensure_event_loop()
            session = NovaSonicSession()

            def on_audio(base64_audio: str) -> None:
                _post_to_connection(event, connection_id, {
                    "type": "audio", "data": base64_audio,
                })

            def on_transcript(role: str, text: str) -> None:
                _post_to_connection(event, connection_id, {
                    "type": "transcript", "role": role, "text": text,
                })

            def on_tool_use(
                tool_name: str, tool_use_id: str, args: dict
            ) -> Any:
                return _execute_tool(user_id, tool_name, tool_use_id, args)

            def on_state(state: str) -> None:
                if state == "interrupted":
                    _post_to_connection(event, connection_id, {
                        "type": "clear_audio",
                    })
                else:
                    _post_to_connection(event, connection_id, {
                        "type": "state",
                        "data": {"state": state},
                    })

            system_prompt = _get_system_prompt(user_id)
            tool_specs = build_tool_specs(_TOOL_FUNCTIONS)

            run_async(session.start(
                system_prompt=system_prompt,
                tool_specs=tool_specs,
                on_audio=on_audio,
                on_transcript=on_transcript,
                on_tool_use=on_tool_use,
                on_state=on_state,
            ))

            _sessions[connection_id] = {
                "user_id": user_id,
                "session": session,
                "active": True,
            }
        except Exception:
            logger.exception(
                "Failed to create Nova Sonic session for connection %s",
                connection_id,
            )
            _post_to_connection(event, connection_id, {
                "type": "fallback",
                "message": (
                    "Voice session could not be established. "
                    "Please switch to text mode."
                ),
            })
            return {"statusCode": 200}

    session_data = _sessions.get(connection_id)
    if not session_data or not session_data.get("active"):
        return {"statusCode": 200}

    # Forward audio to Nova Sonic (body is already base64).
    body = event.get("body", "")
    if body:
        try:
            run_async(session_data["session"].send_audio(body))
        except Exception:
            logger.exception(
                "Failed to send audio to Nova Sonic for connection %s",
                connection_id,
            )

    return {"statusCode": 200}


def _handle_disconnect(event: Dict[str, Any]) -> Dict[str, Any]:
    """Handle WebSocket $disconnect event.

    Closes the Nova Sonic session and stores a session summary
    in AgentCore Memory via the store_memory tool.

    Args:
        event: API Gateway WebSocket $disconnect event.

    Returns:
        Response dict with statusCode 200.
    """
    connection_id = event["requestContext"]["connectionId"]
    conn_info = _connections.pop(connection_id, None)
    session_data = _sessions.pop(connection_id, None)

    if not conn_info:
        conn_info = load_connection(connection_id)
    delete_connection(connection_id)

    user_id = conn_info["user_id"] if conn_info else None

    # Close the Nova Sonic streaming session.
    if session_data:
        session_data["active"] = False
        session = session_data.get("session")
        if session is not None:
            try:
                run_async(session.close())
            except Exception:
                logger.warning(
                    "Error closing Nova Sonic session for connection %s",
                    connection_id,
                )

    # Store session summary in AgentCore Memory.
    if user_id:
        try:
            _tools_mod.store_memory(
                user_id=user_id,
                content="Voice coaching session ended. Session conducted via Nova Sonic.",
            )
            logger.info("Session summary stored for user %s", user_id)
        except Exception:
            logger.warning(
                "Failed to store session summary for user %s", user_id
            )

    logger.info("Connection %s disconnected", connection_id)
    return {"statusCode": 200}


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """WebSocket API Gateway Lambda handler.

    Routes WebSocket lifecycle events to the appropriate handler
    based on the routeKey.

    Args:
        event: API Gateway WebSocket event.
        context: Lambda context.

    Returns:
        Response dict with appropriate statusCode.
    """
    route_key = event.get("requestContext", {}).get("routeKey", "")

    if route_key == "$connect":
        return _handle_connect(event)
    elif route_key == "$disconnect":
        return _handle_disconnect(event)
    else:
        # $default and any other routes handle audio frames.
        return _handle_default(event)
