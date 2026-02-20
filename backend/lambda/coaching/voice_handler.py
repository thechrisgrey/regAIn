"""Voice session Lambda handler for WebSocket API Gateway.

Manages Nova 2 Sonic bidirectional streaming sessions for voice-based
coaching interactions. Handles WebSocket lifecycle events ($connect,
$default, $disconnect) and bridges audio between the frontend and
Amazon Bedrock Nova Sonic.
"""

import base64
import importlib
import json
import logging
import os
from typing import Any, Dict, Optional

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Module-level state for Lambda instance reuse.
# Each WebSocket connection is sticky to one Lambda instance,
# so in-memory mappings are safe for the connection lifetime.
_connections: Dict[str, Dict[str, str]] = {}  # connection_id → {user_id, jwt_token}
_sessions: Dict[str, Dict[str, Any]] = {}  # connection_id → session state

# Lazy-initialized clients
_bedrock_client = None
_apigw_clients: Dict[str, Any] = {}  # endpoint → client

# Load Strands tools for Nova Sonic tool registration
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

NOVA_SONIC_MODEL_ID = os.environ.get(
    "NOVA_SONIC_MODEL_ID", "amazon.nova-sonic-v1:0"
)
AUDIO_CONTENT_TYPE = "audio/lpcm"
AUDIO_SAMPLE_RATE = 16000
AUDIO_BIT_DEPTH = 16
AUDIO_CHANNEL_COUNT = 1


def _get_bedrock_client():
    """Lazily initialize the bedrock-runtime boto3 client.

    Returns:
        A boto3 client for bedrock-runtime.
    """
    global _bedrock_client
    if _bedrock_client is None:
        region = os.environ.get("AWS_REGION", "us-east-1")
        _bedrock_client = boto3.client("bedrock-runtime", region_name=region)
    return _bedrock_client


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

    In production this would verify the JWT signature against the
    Cognito User Pool JWKS. For the initial implementation we decode
    the payload without full verification — API Gateway authorizer
    handles primary auth.

    Args:
        token: The JWT token string from the query string.

    Returns:
        The user_id (sub claim) if valid, None otherwise.
    """
    if not token:
        return None
    try:
        # JWT is three base64url-encoded segments separated by dots.
        parts = token.split(".")
        if len(parts) != 3:
            return None
        # Decode the payload (second segment).
        payload = parts[1]
        # Add padding if needed for base64 decoding.
        padding = 4 - len(payload) % 4
        if padding != 4:
            payload += "=" * padding
        decoded = json.loads(base64.urlsafe_b64decode(payload))
        user_id = decoded.get("sub")
        return user_id if user_id else None
    except Exception:
        logger.warning("Token validation failed")
        return None


def _build_tool_config() -> Dict[str, Any]:
    """Build the tool configuration for Nova Sonic session.

    Registers the Strands coaching tools so Nova Sonic can invoke
    them asynchronously during voice conversation.

    Returns:
        Tool configuration dict for the Nova Sonic session setup.
    """
    tools = []
    for func in _TOOL_FUNCTIONS:
        tool_name = getattr(func, "__name__", str(func))
        doc = getattr(func, "__doc__", "") or ""
        tools.append({
            "toolSpec": {
                "name": tool_name,
                "description": doc.split("\n")[0],
            }
        })
    return {"tools": tools}


def _create_nova_sonic_session(connection_id: str, user_id: str) -> bool:
    """Create a Nova Sonic bidirectional streaming session.

    Initializes the Bedrock streaming session and stores the session
    state in the module-level _sessions dict.

    Args:
        connection_id: The WebSocket connection ID.
        user_id: The authenticated user's ID.

    Returns:
        True if session was created successfully, False otherwise.
    """
    client = _get_bedrock_client()
    try:
        response = client.invoke_model_with_bidirectional_stream(
            modelId=NOVA_SONIC_MODEL_ID,
            body=json.dumps({
                "inputAudioFormat": {
                    "encoding": "pcm",
                    "sampleRateHertz": AUDIO_SAMPLE_RATE,
                    "bitDepth": AUDIO_BIT_DEPTH,
                    "channelCount": AUDIO_CHANNEL_COUNT,
                },
                "outputAudioFormat": {
                    "encoding": "pcm",
                    "sampleRateHertz": AUDIO_SAMPLE_RATE,
                    "bitDepth": AUDIO_BIT_DEPTH,
                    "channelCount": AUDIO_CHANNEL_COUNT,
                },
                "toolConfig": _build_tool_config(),
            }),
        )
        _sessions[connection_id] = {
            "user_id": user_id,
            "stream": response,
            "active": True,
        }
        logger.info(
            "Nova Sonic session created for connection %s, user %s",
            connection_id,
            user_id,
        )
        return True
    except Exception:
        logger.exception(
            "Failed to create Nova Sonic session for connection %s",
            connection_id,
        )
        return False


def _close_nova_sonic_session(connection_id: str) -> None:
    """Close a Nova Sonic session and clean up state.

    Args:
        connection_id: The WebSocket connection ID.
    """
    session = _sessions.pop(connection_id, None)
    if session is None:
        return

    session["active"] = False
    stream = session.get("stream")
    if stream is not None:
        try:
            if hasattr(stream, "close"):
                stream.close()
        except Exception:
            logger.warning(
                "Error closing Nova Sonic stream for connection %s",
                connection_id,
            )

    logger.info("Nova Sonic session closed for connection %s", connection_id)


def _handle_connect(event: Dict[str, Any]) -> Dict[str, Any]:
    """Handle WebSocket $connect event.

    Extracts the Cognito token from the query string, validates it,
    and stores the connection_id → user_id mapping along with the
    raw JWT token for Gateway authorization.

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

    _connections[connection_id] = {"user_id": user_id, "jwt_token": token}
    logger.info(
        "Connection %s established for user %s", connection_id, user_id
    )
    return {"statusCode": 200}


def _handle_default(event: Dict[str, Any]) -> Dict[str, Any]:
    """Handle WebSocket $default event (audio frames).

    Receives base64-encoded audio data from the client and forwards
    it to the active Nova Sonic session. On the first frame for a
    connection, creates the Nova Sonic session.

    Args:
        event: API Gateway WebSocket $default event.

    Returns:
        Response dict with statusCode 200.
    """
    connection_id = event["requestContext"]["connectionId"]
    conn_info = _connections.get(connection_id)

    if not conn_info:
        logger.warning("No user mapping for connection %s", connection_id)
        return {"statusCode": 400}

    # Create Nova Sonic session on first audio frame.
    user_id = conn_info["user_id"]
    if connection_id not in _sessions:
        success = _create_nova_sonic_session(connection_id, user_id)
        if not success:
            # Fallback: notify client to switch to text mode.
            _post_to_connection(event, connection_id, {
                "type": "fallback",
                "message": (
                    "Voice session could not be established. "
                    "Please switch to text mode."
                ),
            })
            return {"statusCode": 200}

    session = _sessions.get(connection_id)
    if not session or not session.get("active"):
        return {"statusCode": 200}

    # Decode and forward audio to Nova Sonic.
    body = event.get("body", "")
    try:
        audio_bytes = base64.b64decode(body) if body else b""
    except Exception:
        logger.warning("Invalid base64 audio data from connection %s", connection_id)
        return {"statusCode": 200}

    if audio_bytes:
        stream = session.get("stream")
        if stream and hasattr(stream, "send"):
            try:
                stream.send({"audioInput": audio_bytes})
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
    user_id = conn_info["user_id"] if conn_info else None

    # Close the Nova Sonic streaming session.
    _close_nova_sonic_session(connection_id)

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
