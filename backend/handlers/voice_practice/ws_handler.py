"""Voice practice WebSocket Lambda handler.

Manages Nova 2 Sonic bidirectional streaming sessions for voice-based
interview practice and mission discussion. Handles WebSocket lifecycle
events ($connect, $default, $disconnect), accumulates transcripts,
and generates post-session assessments via the shared NovaSonicSession.
"""

import base64
import importlib
import inspect
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

import boto3
from boto3.dynamodb.conditions import Attr, Key

from backend.handlers.shared.dynamodb import DynamoDBClient
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
_connections: Dict[str, Dict[str, str]] = {}  # connection_id -> {user_id, jwt_token, session_type}
_sessions: Dict[str, Dict[str, Any]] = {}  # connection_id -> session state

# Lazy-initialized clients
_s3_client = None
_apigw_clients: Dict[str, Any] = {}  # endpoint -> client

# Load Strands tools for Nova Sonic tool registration.
_tools_mod = importlib.import_module("backend.agents.coaching.tools")

VALID_SESSION_TYPES = {"interview", "mission_discussion"}


def _get_tool_functions(session_type: str) -> list:
    """Return the appropriate tool functions for the given session type.

    Interview sessions get profile, campaign, evidence, market, and memory tools.
    Mission discussion sessions additionally get the current mission tool.

    Args:
        session_type: Either "interview" or "mission_discussion".

    Returns:
        List of tool function references.
    """
    base_tools = [
        _tools_mod.read_user_profile,
        _tools_mod.get_campaign_status,
        _tools_mod.get_evidence_summary,
        _tools_mod.get_market_insights,
        _tools_mod.recall_memory,
        _tools_mod.store_memory,
    ]

    if session_type == "mission_discussion":
        base_tools.insert(2, _tools_mod.get_current_mission)

    return base_tools


def _get_s3_client():
    """Lazily initialize the S3 boto3 client."""
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client("s3")
    return _s3_client


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


def _get_system_prompt(session_type: str, user_id: str) -> str:
    """Get the appropriate system prompt for the session type.

    Looks up the user's active campaign to retrieve target role and
    skills focus for prompt generation.

    Args:
        session_type: Either "interview" or "mission_discussion".
        user_id: The authenticated user's ID.

    Returns:
        System prompt string.
    """
    from backend.handlers.voice_practice.prompts import (
        get_interview_prompt,
        get_mission_discussion_prompt,
    )

    target_role = "professional"
    skills_focus: List[str] = []

    try:
        db = DynamoDBClient()
        campaigns = db.query(
            "campaigns",
            Key("userId").eq(user_id),
            filter_expression=Attr("status").eq("active"),
        )
        if campaigns:
            campaign = campaigns[0]
            target_role = campaign.get("targetRole", target_role)
            skills_focus = campaign.get("skillsFocus", [])
    except Exception:
        logger.warning("Failed to look up campaign for user %s", user_id)

    if session_type == "interview":
        return get_interview_prompt(target_role, skills_focus)
    else:
        return get_mission_discussion_prompt(skills_focus)


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
    func = getattr(_tools_mod, tool_name, None)
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

    Extracts the Cognito token and session_type from the query string,
    validates both, and stores the connection mapping.

    Args:
        event: API Gateway WebSocket $connect event.

    Returns:
        Response dict with statusCode 200 on success, 401/400 on failure.
    """
    connection_id = event["requestContext"]["connectionId"]
    query_params = event.get("queryStringParameters") or {}
    token = query_params.get("token", "")
    session_type = query_params.get("session_type", "")

    user_id = _validate_cognito_token(token)
    if not user_id:
        logger.warning("Auth failed for connection %s", connection_id)
        return {"statusCode": 401}

    if session_type not in VALID_SESSION_TYPES:
        logger.warning(
            "Invalid session_type '%s' for connection %s",
            session_type,
            connection_id,
        )
        return {"statusCode": 400}

    conn_data = {
        "user_id": user_id,
        "jwt_token": token,
        "session_type": session_type,
    }
    _connections[connection_id] = conn_data
    store_connection(connection_id, conn_data)

    logger.info(
        "Connection %s established for user %s, type %s",
        connection_id,
        user_id,
        session_type,
    )
    return {"statusCode": 200}


def _handle_default(event: Dict[str, Any]) -> Dict[str, Any]:
    """Handle WebSocket $default event (audio frames).

    On the first frame, creates a NovaSonicSession with the appropriate
    tools and system prompt. Subsequent frames forward audio to Nova Sonic.

    Args:
        event: API Gateway WebSocket $default event.

    Returns:
        Response dict with statusCode 200.
    """
    connection_id = event["requestContext"]["connectionId"]
    conn_info = _connections.get(connection_id)

    if not conn_info:
        # $default may hit a different Lambda container than $connect.
        # Fall back to DynamoDB for cross-container state.
        conn_info = load_connection(connection_id)
        if conn_info:
            _connections[connection_id] = conn_info

    if not conn_info:
        logger.warning("No user mapping for connection %s", connection_id)
        return {"statusCode": 400}

    user_id = conn_info["user_id"]
    session_type = conn_info["session_type"]

    # Create Nova Sonic session on first audio frame.
    if connection_id not in _sessions:
        try:
            ensure_event_loop()
            session = NovaSonicSession()
            transcript: List[Dict[str, str]] = []

            def on_audio(base64_audio: str) -> None:
                _post_to_connection(event, connection_id, {
                    "type": "audio", "data": base64_audio,
                })

            def on_transcript(role: str, text: str) -> None:
                _post_to_connection(event, connection_id, {
                    "type": "transcript", "role": role, "text": text,
                })
                transcript.append({
                    "role": role,
                    "text": text,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
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

            tool_functions = _get_tool_functions(session_type)
            system_prompt = _get_system_prompt(session_type, user_id)
            tool_specs = build_tool_specs(tool_functions)

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
                "session_type": session_type,
                "session": session,
                "active": True,
                "start_time": datetime.now(timezone.utc),
                "transcript": transcript,
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

    Closes the Nova Sonic session, generates an assessment from the
    accumulated transcript, stores transcript and assessment in S3,
    and writes a VoiceSessions DynamoDB record.

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

    if not conn_info or not session_data:
        logger.info("Connection %s disconnected (no session data)", connection_id)
        return {"statusCode": 200}

    user_id = conn_info["user_id"]
    session_type = conn_info["session_type"]
    transcript = session_data.get("transcript", [])
    start_time = session_data.get("start_time", datetime.now(timezone.utc))
    duration_seconds = int((datetime.now(timezone.utc) - start_time).total_seconds())

    session_id = str(uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Look up active campaign for target role and skills focus.
    target_role = "professional"
    skills_focus: List[str] = []
    try:
        db = DynamoDBClient()
        campaigns = db.query(
            "campaigns",
            Key("userId").eq(user_id),
            filter_expression=Attr("status").eq("active"),
        )
        if campaigns:
            campaign = campaigns[0]
            target_role = campaign.get("targetRole", target_role)
            skills_focus = campaign.get("skillsFocus", [])
    except Exception:
        logger.warning("Failed to look up campaign for user %s during disconnect", user_id)

    # S3 keys.
    bucket = os.environ.get("VOICE_PRACTICE_BUCKET_NAME", "")
    s3_prefix = f"{user_id}/voice-practice/{session_type}/{today}/{session_id}"
    s3_transcript_key = f"{s3_prefix}/transcript.json"
    s3_assessment_key = ""

    s3 = _get_s3_client()

    # Write transcript to S3.
    try:
        s3.put_object(
            Bucket=bucket,
            Key=s3_transcript_key,
            Body=json.dumps(transcript),
            ContentType="application/json",
        )
    except Exception:
        logger.exception("Failed to write transcript to S3 for session %s", session_id)

    # Generate assessment.
    overall_score = 0
    assessment_summary = "Assessment generation failed"
    assessment = None

    if transcript:
        try:
            from backend.handlers.voice_practice.assessment import AssessmentService

            assessment_service = AssessmentService()
            assessment = assessment_service.generate_assessment(
                transcript=transcript,
                session_type=session_type,
                target_role=target_role,
                skills_focus=skills_focus,
            )
            overall_score = assessment.get("overallScore", 0)
            assessment_summary = assessment.get("summary", "Assessment generation failed")

            # Write assessment to S3.
            if overall_score > 0:
                s3_assessment_key = f"{s3_prefix}/assessment.json"
                s3.put_object(
                    Bucket=bucket,
                    Key=s3_assessment_key,
                    Body=json.dumps(assessment),
                    ContentType="application/json",
                )
        except Exception:
            logger.exception("Assessment generation failed for session %s", session_id)

    # Write VoiceSessions DynamoDB item.
    try:
        db = DynamoDBClient()
        db.put_item("voice_sessions", {
            "userId": user_id,
            "sessionId": session_id,
            "sessionType": session_type,
            "status": "completed",
            "targetRole": target_role,
            "durationSeconds": duration_seconds,
            "turnCount": len(transcript),
            "overallScore": overall_score,
            "assessmentSummary": assessment_summary,
            "s3TranscriptKey": s3_transcript_key,
            "s3AssessmentKey": s3_assessment_key,
            "createdAt": now_iso,
        })
    except Exception:
        logger.exception("Failed to write VoiceSessions record for session %s", session_id)

    # Store memory summary.
    try:
        _tools_mod.store_memory(
            user_id=user_id,
            content=f"Voice {session_type.replace('_', ' ')} session completed. "
                    f"Duration: {duration_seconds}s, turns: {len(transcript)}, "
                    f"score: {overall_score}/10.",
        )
    except Exception:
        logger.warning("Failed to store session memory for user %s", user_id)

    logger.info(
        "Connection %s disconnected. Session %s saved (score=%d)",
        connection_id,
        session_id,
        overall_score,
    )
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
        return _handle_default(event)
