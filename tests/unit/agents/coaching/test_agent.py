"""Unit tests for the Coaching Agent configuration.

Verifies that create_coaching_agent detects Gateway availability and
selects the correct tool source:
- Gateway provisioned → GatewayToolClient for tool discovery.
- Gateway pending     → direct @tool functions from tools.py.

The strands SDK is stubbed since it is not installed in the test
environment.
"""

import sys
import types
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Stub the strands module tree so agent.py can be imported
# ---------------------------------------------------------------------------
_strands_stub = types.ModuleType("strands")
_strands_stub.Agent = MagicMock  # type: ignore[attr-defined]
_strands_stub.tool = lambda f: f  # type: ignore[attr-defined]

_models_stub = types.ModuleType("strands.models")
_bedrock_stub = types.ModuleType("strands.models.bedrock")
_bedrock_stub.BedrockModel = MagicMock  # type: ignore[attr-defined]

_strands_stub.models = _models_stub  # type: ignore[attr-defined]
_models_stub.bedrock = _bedrock_stub  # type: ignore[attr-defined]

sys.modules["strands"] = _strands_stub
sys.modules["strands.models"] = _models_stub
sys.modules["strands.models.bedrock"] = _bedrock_stub


@pytest.fixture()
def _gateway_env(monkeypatch):
    """Set environment variables for Gateway-available mode."""
    monkeypatch.setenv("AGENTCORE_GATEWAY_ID", "regain-coaching-gateway")
    monkeypatch.setenv("AGENTCORE_GATEWAY_ENDPOINT", "https://gateway.example.com")
    monkeypatch.setenv("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")
    monkeypatch.setenv("AWS_REGION", "us-east-1")


@pytest.fixture()
def _pending_env(monkeypatch):
    """Set environment variables for Gateway-pending (fallback) mode."""
    monkeypatch.setenv("AGENTCORE_GATEWAY_ID", "pending-agentcore-deploy")
    monkeypatch.setenv("AGENTCORE_GATEWAY_ENDPOINT", "pending-agentcore-deploy")
    monkeypatch.setenv("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")
    monkeypatch.setenv("AWS_REGION", "us-east-1")


@pytest.fixture()
def mock_gateway_tools():
    """Patch _get_gateway_tools and return a list with a fake tool module."""
    fake_tool = ModuleType("regain_read_user_profile")
    fake_tool.TOOL_SPEC = {  # type: ignore[attr-defined]
        "name": "regain_read_user_profile",
        "description": "Read a user profile.",
        "inputSchema": {"json": {"type": "object", "properties": {}}},
    }
    with patch(
        "backend.agents.coaching.agent._get_gateway_tools",
        return_value=[fake_tool],
    ) as mock_fn:
        yield mock_fn, [fake_tool]


@pytest.fixture()
def mock_direct_tools():
    """Patch _get_direct_tools and return a list of sentinel tool functions."""
    sentinel_tools = [MagicMock(name=f"tool_{i}") for i in range(13)]
    with patch(
        "backend.agents.coaching.agent._get_direct_tools",
        return_value=sentinel_tools,
    ) as mock_fn:
        yield mock_fn, sentinel_tools


@pytest.fixture()
def mock_agent():
    """Patch the Strands Agent class."""
    with patch("backend.agents.coaching.agent.Agent") as mock_cls:
        yield mock_cls


@pytest.fixture()
def mock_bedrock_model():
    """Patch BedrockModel."""
    with patch("backend.agents.coaching.agent.BedrockModel") as mock_cls:
        yield mock_cls


class TestGatewayMode:
    """Tests for when AgentCore Gateway is provisioned."""

    @pytest.mark.usefixtures("_gateway_env")
    def test_uses_gateway_tools_when_endpoint_available(
        self, mock_gateway_tools, mock_agent, mock_bedrock_model
    ):
        """When Gateway endpoint is a real URL, should use Gateway tools."""
        mock_fn, tools = mock_gateway_tools
        from backend.agents.coaching.agent import create_coaching_agent

        create_coaching_agent(user_id="user-123", jwt_token="my-jwt")

        mock_fn.assert_called_once_with("my-jwt")
        call_kwargs = mock_agent.call_args
        assert call_kwargs.kwargs["tools"] == tools

    @pytest.mark.usefixtures("_gateway_env")
    def test_configures_bedrock_model(
        self, mock_gateway_tools, mock_agent, mock_bedrock_model
    ):
        """BedrockModel should be configured from environment variables."""
        from backend.agents.coaching.agent import create_coaching_agent

        create_coaching_agent(user_id="user-123", jwt_token="my-jwt")

        mock_bedrock_model.assert_called_once_with(
            model_id="amazon.nova-lite-v1:0",
            region_name="us-east-1",
        )

    @pytest.mark.usefixtures("_gateway_env")
    def test_passes_system_prompt(
        self, mock_gateway_tools, mock_agent, mock_bedrock_model
    ):
        """Agent should receive the system prompt from get_system_prompt()."""
        from backend.agents.coaching.agent import create_coaching_agent

        with patch(
            "backend.agents.coaching.agent.get_system_prompt",
            return_value="You are a coach.",
        ):
            create_coaching_agent(user_id="user-123", jwt_token="my-jwt")

        call_kwargs = mock_agent.call_args
        assert call_kwargs.kwargs["system_prompt"] == "You are a coach."

    @pytest.mark.usefixtures("_gateway_env")
    def test_returns_agent_instance(
        self, mock_gateway_tools, mock_agent, mock_bedrock_model
    ):
        """Should return the Agent instance."""
        from backend.agents.coaching.agent import create_coaching_agent

        result = create_coaching_agent(user_id="user-123", jwt_token="my-jwt")

        assert result == mock_agent.return_value


class TestDirectToolFallback:
    """Tests for when Gateway is not provisioned (pending)."""

    @pytest.mark.usefixtures("_pending_env")
    def test_uses_direct_tools_when_pending(
        self, mock_direct_tools, mock_agent, mock_bedrock_model
    ):
        """When Gateway endpoint is 'pending-agentcore-deploy', should use direct tools."""
        mock_fn, tools = mock_direct_tools
        from backend.agents.coaching.agent import create_coaching_agent

        create_coaching_agent(user_id="user-123", jwt_token="my-jwt")

        mock_fn.assert_called_once()
        call_kwargs = mock_agent.call_args
        assert call_kwargs.kwargs["tools"] == tools

    def test_uses_direct_tools_when_env_missing(
        self, mock_direct_tools, mock_agent, mock_bedrock_model, monkeypatch
    ):
        """When AGENTCORE_GATEWAY_ENDPOINT is not set, should use direct tools."""
        monkeypatch.delenv("AGENTCORE_GATEWAY_ENDPOINT", raising=False)
        monkeypatch.setenv("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")
        monkeypatch.setenv("AWS_REGION", "us-east-1")

        mock_fn, _ = mock_direct_tools
        from backend.agents.coaching.agent import create_coaching_agent

        create_coaching_agent(user_id="user-123", jwt_token="my-jwt")

        mock_fn.assert_called_once()

    @pytest.mark.usefixtures("_pending_env")
    def test_does_not_import_gateway_client_when_pending(
        self, mock_direct_tools, mock_agent, mock_bedrock_model
    ):
        """Gateway client module should not be imported in fallback mode."""
        from backend.agents.coaching.agent import create_coaching_agent

        with patch(
            "backend.agents.coaching.agent._get_gateway_tools"
        ) as gw_mock:
            create_coaching_agent(user_id="user-123", jwt_token="my-jwt")
            gw_mock.assert_not_called()


class TestGatewayDetection:
    """Tests for _is_gateway_available helper."""

    def test_pending_value_is_not_available(self, monkeypatch):
        monkeypatch.setenv("AGENTCORE_GATEWAY_ENDPOINT", "pending-agentcore-deploy")
        from backend.agents.coaching.agent import _is_gateway_available

        assert _is_gateway_available() is False

    def test_empty_value_is_not_available(self, monkeypatch):
        monkeypatch.setenv("AGENTCORE_GATEWAY_ENDPOINT", "")
        from backend.agents.coaching.agent import _is_gateway_available

        assert _is_gateway_available() is False

    def test_real_url_is_available(self, monkeypatch):
        monkeypatch.setenv("AGENTCORE_GATEWAY_ENDPOINT", "https://gw.example.com")
        from backend.agents.coaching.agent import _is_gateway_available

        assert _is_gateway_available() is True

    def test_unset_is_not_available(self, monkeypatch):
        monkeypatch.delenv("AGENTCORE_GATEWAY_ENDPOINT", raising=False)
        from backend.agents.coaching.agent import _is_gateway_available

        assert _is_gateway_available() is False
