"""Unit tests for the shared Nova Sonic bidirectional streaming client.

Tests cover event protocol ordering, tool spec generation, response
event dispatching, and session lifecycle.
"""

import asyncio
import json
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Stub the aws_sdk_bedrock_runtime dependencies.
# ---------------------------------------------------------------------------
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

from backend.handlers.shared.nova_sonic import (
    NovaSonicSession,
    build_tool_specs,
)


# ---------------------------------------------------------------------------
# build_tool_specs tests
# ---------------------------------------------------------------------------


class TestBuildToolSpecs:
    """Tests for the build_tool_specs utility."""

    def test_simple_function_no_extra_params(self) -> None:
        """Function with only user_id produces empty properties."""
        def read_profile(user_id: str) -> dict:
            """Read a user profile."""
            return {}

        specs = build_tool_specs([read_profile])
        assert len(specs) == 1
        spec = specs[0]["toolSpec"]
        assert spec["name"] == "read_profile"
        assert spec["description"] == "Read a user profile."
        schema = spec["inputSchema"]["json"]
        assert schema["type"] == "object"
        assert schema["properties"] == {}
        assert schema["required"] == []

    def test_function_with_extra_params(self) -> None:
        """Function with multiple params generates correct schema."""
        def create_campaign(
            user_id: str,
            title: str,
            target_role: str,
            skills_focus: list,
        ) -> dict:
            """Create a new campaign."""
            return {}

        specs = build_tool_specs([create_campaign])
        spec = specs[0]["toolSpec"]
        schema = spec["inputSchema"]["json"]
        assert "title" in schema["properties"]
        assert "target_role" in schema["properties"]
        assert "skills_focus" in schema["properties"]
        assert "user_id" not in schema["properties"]
        assert schema["properties"]["title"]["type"] == "string"
        assert schema["properties"]["skills_focus"]["type"] == "array"
        assert "title" in schema["required"]
        assert "target_role" in schema["required"]

    def test_optional_param_not_required(self) -> None:
        """Parameters with defaults are not in the required list."""
        def log_evidence(
            user_id: str,
            mission_id: str,
            skill_tag: str,
            artifact_url: str = "",
        ) -> dict:
            """Log evidence."""
            return {}

        specs = build_tool_specs([log_evidence])
        schema = specs[0]["toolSpec"]["inputSchema"]["json"]
        assert "mission_id" in schema["required"]
        assert "skill_tag" in schema["required"]
        assert "artifact_url" not in schema["required"]

    def test_function_without_user_id(self) -> None:
        """Function without user_id includes all params in schema."""
        def get_market_insights(role_id: str) -> dict:
            """Get market insights for a role."""
            return {}

        specs = build_tool_specs([get_market_insights])
        schema = specs[0]["toolSpec"]["inputSchema"]["json"]
        assert "role_id" in schema["properties"]
        assert "role_id" in schema["required"]

    def test_multiple_functions(self) -> None:
        """Multiple functions produce multiple tool specs."""
        def tool_a(user_id: str) -> dict:
            """Tool A."""
            return {}

        def tool_b(user_id: str, query: str) -> dict:
            """Tool B."""
            return {}

        specs = build_tool_specs([tool_a, tool_b])
        assert len(specs) == 2
        assert specs[0]["toolSpec"]["name"] == "tool_a"
        assert specs[1]["toolSpec"]["name"] == "tool_b"

    def test_custom_exclude_params(self) -> None:
        """Custom exclude_params skips specified parameters."""
        def my_tool(user_id: str, session_id: str, query: str) -> dict:
            """My tool."""
            return {}

        specs = build_tool_specs(
            [my_tool], exclude_params={"user_id", "session_id"}
        )
        schema = specs[0]["toolSpec"]["inputSchema"]["json"]
        assert "user_id" not in schema["properties"]
        assert "session_id" not in schema["properties"]
        assert "query" in schema["properties"]


# ---------------------------------------------------------------------------
# NovaSonicSession tests
# ---------------------------------------------------------------------------


class TestNovaSonicSessionInit:
    """Tests for NovaSonicSession initialization."""

    def test_default_model_id(self) -> None:
        """Default model ID is Nova 2 Sonic."""
        session = NovaSonicSession()
        assert session.model_id == "amazon.nova-2-sonic-v1:0"

    def test_custom_model_id(self) -> None:
        """Custom model ID overrides the default."""
        session = NovaSonicSession(model_id="custom-model")
        assert session.model_id == "custom-model"

    def test_env_model_id(self) -> None:
        """Model ID from environment variable."""
        with patch.dict("os.environ", {"NOVA_SONIC_MODEL_ID": "env-model"}):
            session = NovaSonicSession()
            assert session.model_id == "env-model"

    def test_initial_state(self) -> None:
        """Session starts as inactive."""
        session = NovaSonicSession()
        assert session.is_active is False
        assert session._stream is None


class TestResponseHandlers:
    """Tests for individual response event handlers."""

    def test_handle_audio_output(self) -> None:
        """Audio output event dispatches to on_audio callback."""
        session = NovaSonicSession()
        received = []
        session._on_audio = lambda audio: received.append(audio)

        session._handle_audio_output({"content": "base64audiocontent"})

        assert received == ["base64audiocontent"]

    def test_handle_audio_output_empty(self) -> None:
        """Empty audio content does not trigger callback."""
        session = NovaSonicSession()
        received = []
        session._on_audio = lambda audio: received.append(audio)

        session._handle_audio_output({"content": ""})

        assert received == []

    def test_handle_text_output_user(self) -> None:
        """User text output (ASR) dispatches with role 'user'."""
        session = NovaSonicSession()
        received = []
        session._on_transcript = lambda role, text: received.append((role, text))
        session._current_role = "USER"

        session._handle_text_output({"content": "Hello world"})

        assert received == [("user", "Hello world")]

    def test_handle_text_output_assistant(self) -> None:
        """Non-speculative assistant text dispatches."""
        session = NovaSonicSession()
        received = []
        session._on_transcript = lambda role, text: received.append((role, text))
        session._on_state = MagicMock()
        session._current_role = "ASSISTANT"
        session._is_speculative = False

        session._handle_text_output({"content": "I can help"})

        assert received == [("assistant", "I can help")]
        session._on_state.assert_called_with("speaking")

    def test_handle_text_output_speculative(self) -> None:
        """Speculative assistant text is not dispatched."""
        session = NovaSonicSession()
        received = []
        session._on_transcript = lambda role, text: received.append((role, text))
        session._current_role = "ASSISTANT"
        session._is_speculative = True

        session._handle_text_output({"content": "Speculative text"})

        assert received == []

    def test_handle_content_start_user_triggers_listening(self) -> None:
        """USER contentStart triggers 'listening' state."""
        session = NovaSonicSession()
        session._on_state = MagicMock()

        session._handle_content_start({"role": "USER"})

        assert session._current_role == "USER"
        session._on_state.assert_called_with("listening")

    def test_handle_content_start_speculative_detection(self) -> None:
        """Detects SPECULATIVE generation stage in additionalModelFields."""
        session = NovaSonicSession()
        session._on_state = MagicMock()

        session._handle_content_start({
            "role": "ASSISTANT",
            "additionalModelFields": '{"generationStage": "SPECULATIVE"}',
        })

        assert session._is_speculative is True

    def test_handle_interrupted(self) -> None:
        """Interrupted text output triggers 'interrupted' state."""
        session = NovaSonicSession()
        session._on_state = MagicMock()
        session._current_role = "ASSISTANT"

        session._handle_text_output({"content": '{"interrupted": true}'})

        session._on_state.assert_called_with("interrupted")

    def test_handle_tool_use_event(self) -> None:
        """Tool use event captures tool details."""
        session = NovaSonicSession()

        session._handle_tool_use_event({
            "toolName": "read_user_profile",
            "toolUseId": "tu-123",
            "content": '{"user_id": "abc"}',
        })

        assert session._tool_name == "read_user_profile"
        assert session._tool_use_id == "tu-123"
