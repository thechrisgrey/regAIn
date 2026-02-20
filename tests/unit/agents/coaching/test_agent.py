"""Unit tests for the migrated Coaching Agent configuration.

Verifies that create_coaching_agent uses GatewayToolClient for tool
discovery instead of direct tool imports, passes the JWT token through,
and configures the Strands Agent with the correct model and system prompt.

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

_models_stub = types.ModuleType("strands.models")
_bedrock_stub = types.ModuleType("strands.models.bedrock")
_bedrock_stub.BedrockModel = MagicMock  # type: ignore[attr-defined]

_strands_stub.models = _models_stub  # type: ignore[attr-defined]
_models_stub.bedrock = _bedrock_stub  # type: ignore[attr-defined]

sys.modules["strands"] = _strands_stub
sys.modules["strands.models"] = _models_stub
sys.modules["strands.models.bedrock"] = _bedrock_stub


@pytest.fixture()
def _agent_env(monkeypatch):
    """Set environment variables for agent creation."""
    monkeypatch.setenv("AGENTCORE_GATEWAY_ID", "regain-coaching-gateway")
    monkeypatch.setenv("AGENTCORE_GATEWAY_ENDPOINT", "https://gateway.example.com")
    monkeypatch.setenv("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")
    monkeypatch.setenv("AWS_REGION", "us-east-1")


@pytest.fixture()
def mock_gateway_client():
    """Patch GatewayToolClient and return the mock class."""
    with patch(
        "backend.agents.coaching.agent.GatewayToolClient"
    ) as mock_cls:
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance

        fake_tool = ModuleType("regain_read_user_profile")
        fake_tool.TOOL_SPEC = {  # type: ignore[attr-defined]
            "name": "regain_read_user_profile",
            "description": "Read a user profile.",
            "inputSchema": {"json": {"type": "object", "properties": {}}},
        }
        mock_instance.discover_tools.return_value = [fake_tool]

        yield mock_cls, mock_instance


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


class TestCreateCoachingAgent:
    """Tests for create_coaching_agent after Gateway migration."""

    @pytest.mark.usefixtures("_agent_env")
    def test_creates_gateway_client_with_correct_params(
        self, mock_gateway_client, mock_agent, mock_bedrock_model
    ):
        """GatewayToolClient should be created with gateway_id and jwt_token."""
        mock_cls, _ = mock_gateway_client
        from backend.agents.coaching.agent import create_coaching_agent

        create_coaching_agent(user_id="user-123", jwt_token="my-jwt")

        mock_cls.assert_called_once_with("regain-coaching-gateway", "my-jwt")

    @pytest.mark.usefixtures("_agent_env")
    def test_discovers_tools_from_gateway(
        self, mock_gateway_client, mock_agent, mock_bedrock_model
    ):
        """Agent should use tools discovered from the Gateway."""
        _, mock_instance = mock_gateway_client
        from backend.agents.coaching.agent import create_coaching_agent

        create_coaching_agent(user_id="user-123", jwt_token="my-jwt")

        mock_instance.discover_tools.assert_called_once()
        call_kwargs = mock_agent.call_args
        assert call_kwargs.kwargs["tools"] == mock_instance.discover_tools.return_value

    @pytest.mark.usefixtures("_agent_env")
    def test_configures_bedrock_model(
        self, mock_gateway_client, mock_agent, mock_bedrock_model
    ):
        """BedrockModel should be configured from environment variables."""
        from backend.agents.coaching.agent import create_coaching_agent

        create_coaching_agent(user_id="user-123", jwt_token="my-jwt")

        mock_bedrock_model.assert_called_once_with(
            model_id="amazon.nova-lite-v1:0",
            region_name="us-east-1",
        )

    @pytest.mark.usefixtures("_agent_env")
    def test_passes_system_prompt(
        self, mock_gateway_client, mock_agent, mock_bedrock_model
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

    @pytest.mark.usefixtures("_agent_env")
    def test_uses_default_gateway_id(
        self, mock_gateway_client, mock_agent, mock_bedrock_model, monkeypatch
    ):
        """When AGENTCORE_GATEWAY_ID is unset, default should be used."""
        monkeypatch.delenv("AGENTCORE_GATEWAY_ID", raising=False)
        mock_cls, _ = mock_gateway_client
        from backend.agents.coaching.agent import create_coaching_agent

        create_coaching_agent(user_id="user-123", jwt_token="my-jwt")

        mock_cls.assert_called_once_with("regain-coaching-gateway", "my-jwt")

    @pytest.mark.usefixtures("_agent_env")
    def test_returns_agent_instance(
        self, mock_gateway_client, mock_agent, mock_bedrock_model
    ):
        """Should return the Agent instance."""
        from backend.agents.coaching.agent import create_coaching_agent

        result = create_coaching_agent(user_id="user-123", jwt_token="my-jwt")

        assert result == mock_agent.return_value

    @pytest.mark.usefixtures("_agent_env")
    def test_no_direct_tool_imports(self):
        """agent.py should not contain direct tool imports or _ALL_TOOLS."""
        import inspect
        import backend.agents.coaching.agent as agent_mod

        source = inspect.getsource(agent_mod)
        assert "importlib" not in source
        assert "_tools_mod" not in source
        assert "_ALL_TOOLS" not in source
