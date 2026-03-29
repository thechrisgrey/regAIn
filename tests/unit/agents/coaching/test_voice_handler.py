"""Unit tests for the voice session WebSocket handler.

Tests cover $connect authentication, $disconnect cleanup, and
Nova Sonic fallback on session creation failure.
"""

import base64
import importlib
import json
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Stub the strands module so tools.py can be imported without strands-agents
# ---------------------------------------------------------------------------
_strands_stub = types.ModuleType("strands")
_strands_stub.tool = lambda fn: fn
sys.modules.setdefault("strands", _strands_stub)

# Stub the aws_sdk_bedrock_runtime dependencies so nova_sonic.py can import.
for mod_name in [
    "aws_sdk_bedrock_runtime",
    "aws_sdk_bedrock_runtime.client",
    "aws_sdk_bedrock_runtime.models",
    "aws_sdk_bedrock_runtime.config",
    "smithy_aws_core",
    "smithy_aws_core.identity",
    "smithy_aws_core.identity.environment",
]:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = types.ModuleType(mod_name)

# Add expected classes to stubs.
_sdk_client = sys.modules["aws_sdk_bedrock_runtime.client"]
_sdk_client.BedrockRuntimeClient = MagicMock
_sdk_client.InvokeModelWithBidirectionalStreamOperationInput = MagicMock
_sdk_models = sys.modules["aws_sdk_bedrock_runtime.models"]
_sdk_models.InvokeModelWithBidirectionalStreamInputChunk = MagicMock
_sdk_models.BidirectionalInputPayloadPart = MagicMock
_sdk_config = sys.modules["aws_sdk_bedrock_runtime.config"]
_sdk_config.Config = MagicMock
_env_resolver = sys.modules["smithy_aws_core.identity.environment"]
_env_resolver.EnvironmentCredentialsResolver = MagicMock


def _make_token(sub: str = "test-user-123") -> str:
    """Build a valid-looking JWT with the given sub claim."""
    header = base64.urlsafe_b64encode(
        json.dumps({"alg": "RS256"}).encode()
    ).decode().rstrip("=")
    payload = base64.urlsafe_b64encode(
        json.dumps({"sub": sub}).encode()
    ).decode().rstrip("=")
    signature = base64.urlsafe_b64encode(b"fake-signature").decode().rstrip("=")
    return f"{header}.{payload}.{signature}"


def _load_voice_handler():
    """Import voice_handler with a fresh module state."""
    mod_name = "backend.handlers.coaching.voice_handler"
    # Also ensure tools module is loadable
    tools_name = "backend.agents.coaching.tools"
    if tools_name in sys.modules:
        del sys.modules[tools_name]
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    mod = importlib.import_module(mod_name)
    # Reset module-level state
    mod._connections.clear()
    mod._sessions.clear()
    mod._apigw_clients.clear()
    return mod


def _connect_event(connection_id: str = "conn-123", token: str = "") -> dict:
    """Build a $connect WebSocket event."""
    event = {
        "requestContext": {
            "routeKey": "$connect",
            "connectionId": connection_id,
            "domainName": "abc123.execute-api.us-east-1.amazonaws.com",
            "stage": "prod",
        },
    }
    if token:
        event["queryStringParameters"] = {"token": token}
    return event


def _disconnect_event(connection_id: str = "conn-123") -> dict:
    """Build a $disconnect WebSocket event."""
    return {
        "requestContext": {
            "routeKey": "$disconnect",
            "connectionId": connection_id,
        },
    }


def _default_event(connection_id: str = "conn-123", body: str = "") -> dict:
    """Build a $default WebSocket event."""
    return {
        "requestContext": {
            "routeKey": "$default",
            "connectionId": connection_id,
            "domainName": "abc123.execute-api.us-east-1.amazonaws.com",
            "stage": "prod",
        },
        "body": body,
    }


# -- $connect tests --------------------------------------------------------


class TestConnectSuccess:
    """Test $connect with valid authentication."""

    def test_connect_success(self) -> None:
        """Valid JWT token returns 200 and stores connection mapping."""
        vh = _load_voice_handler()
        token = _make_token("user-abc")
        event = _connect_event(connection_id="conn-1", token=token)

        with patch("backend.handlers.shared.jwt.verify_cognito_token", return_value="user-abc"):
            result = vh.lambda_handler(event, None)

        assert result["statusCode"] == 200
        assert vh._connections["conn-1"]["user_id"] == "user-abc"
        assert vh._connections["conn-1"]["authenticated"] == "true"


class TestConnectMissingToken:
    """Test $connect with missing token accepts unauthenticated (first-message auth)."""

    def test_connect_missing_token(self) -> None:
        """No token in query string returns 200 (unauthenticated, awaiting first-message auth)."""
        vh = _load_voice_handler()
        event = _connect_event(connection_id="conn-2")
        # No queryStringParameters at all

        result = vh.lambda_handler(event, None)

        assert result["statusCode"] == 200
        assert "conn-2" in vh._connections
        assert vh._connections["conn-2"]["authenticated"] == "false"
        assert vh._connections["conn-2"]["user_id"] == ""


class TestConnectInvalidToken:
    """Test $connect with malformed token."""

    def test_connect_invalid_token(self) -> None:
        """Malformed token (not a valid JWT) returns 401."""
        vh = _load_voice_handler()
        event = _connect_event(connection_id="conn-3", token="not-a-jwt")

        result = vh.lambda_handler(event, None)

        assert result["statusCode"] == 401
        assert "conn-3" not in vh._connections


# -- $disconnect tests -----------------------------------------------------


class TestDisconnectCleanup:
    """Test $disconnect cleans up connection and session state."""

    def test_disconnect_cleanup(self) -> None:
        """Disconnect removes connection, closes session, returns 200."""
        vh = _load_voice_handler()

        # Pre-populate state as if a connection + session exist.
        vh._connections["conn-4"] = {"user_id": "user-xyz"}
        mock_session = MagicMock()
        mock_session.close = MagicMock(return_value=MagicMock())
        vh._sessions["conn-4"] = {
            "user_id": "user-xyz",
            "session": mock_session,
            "active": True,
        }

        event = _disconnect_event(connection_id="conn-4")

        with patch.object(vh, "run_async") as mock_run_async:
            result = vh.lambda_handler(event, None)

        assert result["statusCode"] == 200
        assert "conn-4" not in vh._connections
        assert "conn-4" not in vh._sessions
        mock_run_async.assert_called_once()


class TestDisconnectNoSession:
    """Test $disconnect when there's no active session."""

    def test_disconnect_no_session(self) -> None:
        """Disconnect without active session returns 200, no error."""
        vh = _load_voice_handler()

        # Connection exists but no Nova Sonic session was created.
        vh._connections["conn-5"] = {"user_id": "user-solo"}

        event = _disconnect_event(connection_id="conn-5")

        result = vh.lambda_handler(event, None)

        assert result["statusCode"] == 200
        assert "conn-5" not in vh._connections
        assert "conn-5" not in vh._sessions


# -- $default fallback test ------------------------------------------------


class TestDefaultFallbackOnSessionFailure:
    """Test $default sends fallback when Nova Sonic session creation fails."""

    def test_default_fallback_on_session_failure(self) -> None:
        """When Nova Sonic session creation fails, client gets fallback message."""
        vh = _load_voice_handler()

        # Pre-populate connection mapping (as if $connect succeeded).
        vh._connections["conn-6"] = {"user_id": "user-fallback"}

        audio_data = base64.b64encode(b"fake-audio-bytes").decode()
        event = _default_event(connection_id="conn-6", body=audio_data)

        mock_apigw = MagicMock()

        with patch.object(vh, "ensure_event_loop"), \
             patch.object(vh, "NovaSonicSession", side_effect=Exception("SDK unavailable")), \
             patch.object(vh, "_get_apigw_client", return_value=mock_apigw):
            result = vh.lambda_handler(event, None)

        assert result["statusCode"] == 200
        # Verify fallback message was posted to the client.
        mock_apigw.post_to_connection.assert_called_once()
        call_kwargs = mock_apigw.post_to_connection.call_args[1]
        assert call_kwargs["ConnectionId"] == "conn-6"
        posted_data = json.loads(call_kwargs["Data"].decode("utf-8"))
        assert posted_data["type"] == "fallback"
        assert "text mode" in posted_data["message"].lower()
