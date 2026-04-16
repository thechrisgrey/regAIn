"""Unit tests for the Coaching Agent configuration.

Verifies that create_coaching_agent always uses direct @tool functions
from tools.py (Gateway tool discovery is disabled — Strands rejects
the ModuleType format).

The strands SDK is stubbed since it is not installed in the test
environment.
"""

import sys
import types
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


class TestDirectTools:
    """Tests for direct @tool function loading (always used)."""

    @pytest.mark.usefixtures("_pending_env")
    def test_always_uses_direct_tools(
        self, mock_direct_tools, mock_agent, mock_bedrock_model
    ):
        """Should always use direct tools regardless of Gateway env vars."""
        mock_fn, tools = mock_direct_tools
        from backend.agents.coaching.agent import create_coaching_agent

        create_coaching_agent(user_id="user-123", jwt_token="my-jwt")

        mock_fn.assert_called_once()
        call_kwargs = mock_agent.call_args
        assert call_kwargs.kwargs["tools"] == tools

    @pytest.mark.usefixtures("_gateway_env")
    def test_uses_direct_tools_even_with_gateway_available(
        self, mock_direct_tools, mock_agent, mock_bedrock_model
    ):
        """Even when Gateway endpoint is set, should use direct tools."""
        mock_fn, tools = mock_direct_tools
        from backend.agents.coaching.agent import create_coaching_agent

        create_coaching_agent(user_id="user-123", jwt_token="my-jwt")

        mock_fn.assert_called_once()
        call_kwargs = mock_agent.call_args
        assert call_kwargs.kwargs["tools"] == tools

    @pytest.mark.usefixtures("_pending_env")
    def test_configures_bedrock_model(
        self, mock_direct_tools, mock_agent, mock_bedrock_model
    ):
        """BedrockModel should be configured from environment variables."""
        from backend.agents.coaching.agent import create_coaching_agent

        create_coaching_agent(user_id="user-123", jwt_token="my-jwt")

        mock_bedrock_model.assert_called_once_with(
            model_id="amazon.nova-lite-v1:0",
            region_name="us-east-1",
        )

    @pytest.mark.usefixtures("_pending_env")
    def test_passes_system_prompt(
        self, mock_direct_tools, mock_agent, mock_bedrock_model
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

    @pytest.mark.usefixtures("_pending_env")
    def test_returns_agent_instance(
        self, mock_direct_tools, mock_agent, mock_bedrock_model
    ):
        """Should return the Agent instance."""
        from backend.agents.coaching.agent import create_coaching_agent

        result = create_coaching_agent(user_id="user-123", jwt_token="my-jwt")

        assert result == mock_agent.return_value


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


class TestSessionIdPassthrough:
    """Tests for session_id parameter in _create_session_manager and create_coaching_agent."""

    def test_session_id_passed_to_session_manager(self, monkeypatch):
        """When session_id='ws-conn-abc' is passed, AgentCoreMemoryConfig should receive it."""
        monkeypatch.setenv("AGENTCORE_MEMORY_ID", "mem-123")
        monkeypatch.setenv("AWS_REGION", "us-east-1")

        mock_config_cls = MagicMock(name="AgentCoreMemoryConfig")
        mock_retrieval_cls = MagicMock(name="RetrievalConfig")
        mock_session_mgr_cls = MagicMock(name="AgentCoreMemorySessionManager")

        config_mod = types.ModuleType("bedrock_agentcore.memory.integrations.strands.config")
        config_mod.AgentCoreMemoryConfig = mock_config_cls  # type: ignore[attr-defined]
        config_mod.RetrievalConfig = mock_retrieval_cls  # type: ignore[attr-defined]

        mgr_mod = types.ModuleType("bedrock_agentcore.memory.integrations.strands.session_manager")
        mgr_mod.AgentCoreMemorySessionManager = mock_session_mgr_cls  # type: ignore[attr-defined]

        with patch.dict(sys.modules, {
            "bedrock_agentcore": types.ModuleType("bedrock_agentcore"),
            "bedrock_agentcore.memory": types.ModuleType("bedrock_agentcore.memory"),
            "bedrock_agentcore.memory.integrations": types.ModuleType("bedrock_agentcore.memory.integrations"),
            "bedrock_agentcore.memory.integrations.strands": types.ModuleType("bedrock_agentcore.memory.integrations.strands"),
            "bedrock_agentcore.memory.integrations.strands.config": config_mod,
            "bedrock_agentcore.memory.integrations.strands.session_manager": mgr_mod,
        }):
            from backend.agents.coaching.agent import _create_session_manager

            _create_session_manager("user-42", session_id="ws-conn-abc")

        mock_config_cls.assert_called_once()
        call_kwargs = mock_config_cls.call_args.kwargs
        assert call_kwargs["session_id"] == "ws-conn-abc"

    def test_session_id_defaults_to_uuid_when_none(self, monkeypatch):
        """When no session_id is passed, AgentCoreMemoryConfig should get a 'session-' prefixed ID."""
        monkeypatch.setenv("AGENTCORE_MEMORY_ID", "mem-123")
        monkeypatch.setenv("AWS_REGION", "us-east-1")

        mock_config_cls = MagicMock(name="AgentCoreMemoryConfig")
        mock_retrieval_cls = MagicMock(name="RetrievalConfig")
        mock_session_mgr_cls = MagicMock(name="AgentCoreMemorySessionManager")

        config_mod = types.ModuleType("bedrock_agentcore.memory.integrations.strands.config")
        config_mod.AgentCoreMemoryConfig = mock_config_cls  # type: ignore[attr-defined]
        config_mod.RetrievalConfig = mock_retrieval_cls  # type: ignore[attr-defined]

        mgr_mod = types.ModuleType("bedrock_agentcore.memory.integrations.strands.session_manager")
        mgr_mod.AgentCoreMemorySessionManager = mock_session_mgr_cls  # type: ignore[attr-defined]

        with patch.dict(sys.modules, {
            "bedrock_agentcore": types.ModuleType("bedrock_agentcore"),
            "bedrock_agentcore.memory": types.ModuleType("bedrock_agentcore.memory"),
            "bedrock_agentcore.memory.integrations": types.ModuleType("bedrock_agentcore.memory.integrations"),
            "bedrock_agentcore.memory.integrations.strands": types.ModuleType("bedrock_agentcore.memory.integrations.strands"),
            "bedrock_agentcore.memory.integrations.strands.config": config_mod,
            "bedrock_agentcore.memory.integrations.strands.session_manager": mgr_mod,
        }):
            from backend.agents.coaching.agent import _create_session_manager

            _create_session_manager("user-42")

        mock_config_cls.assert_called_once()
        call_kwargs = mock_config_cls.call_args.kwargs
        assert call_kwargs["session_id"].startswith("session-")


class TestComponentCaching:
    """Tests for the component caching layer in create_coaching_agent."""

    def setup_method(self):
        from backend.agents.coaching.agent import _component_cache

        _component_cache.clear()

    def teardown_method(self):
        from backend.agents.coaching.agent import _component_cache

        _component_cache.clear()

    @pytest.mark.usefixtures("_pending_env")
    def test_cache_miss_stores_components(
        self, mock_direct_tools, mock_agent, mock_bedrock_model
    ):
        """First call with cache_key should store entry in _component_cache."""
        from backend.agents.coaching.agent import (
            _component_cache,
            create_coaching_agent,
        )

        create_coaching_agent(
            user_id="user-123", jwt_token="my-jwt", cache_key="conn-1"
        )

        assert "conn-1" in _component_cache
        cached = _component_cache["conn-1"]
        assert "tools" in cached
        assert "model" in cached
        assert "session_manager" in cached
        assert "system_prompt" in cached

    @pytest.mark.usefixtures("_pending_env")
    def test_cache_hit_skips_tool_loading(
        self, mock_direct_tools, mock_agent, mock_bedrock_model
    ):
        """Second call with same cache_key should NOT re-call _get_direct_tools."""
        from backend.agents.coaching.agent import create_coaching_agent

        mock_fn, _ = mock_direct_tools

        create_coaching_agent(
            user_id="user-123", jwt_token="my-jwt", cache_key="conn-1"
        )
        mock_fn.reset_mock()

        create_coaching_agent(
            user_id="user-123", jwt_token="my-jwt", cache_key="conn-1"
        )
        mock_fn.assert_not_called()

    @pytest.mark.usefixtures("_pending_env")
    def test_cache_hit_skips_model_creation(
        self, mock_direct_tools, mock_agent, mock_bedrock_model
    ):
        """Second call with same cache_key should NOT re-call BedrockModel."""
        from backend.agents.coaching.agent import create_coaching_agent

        create_coaching_agent(
            user_id="user-123", jwt_token="my-jwt", cache_key="conn-1"
        )
        mock_bedrock_model.reset_mock()

        create_coaching_agent(
            user_id="user-123", jwt_token="my-jwt", cache_key="conn-1"
        )
        mock_bedrock_model.assert_not_called()

    @pytest.mark.usefixtures("_pending_env")
    def test_no_cache_key_skips_caching(
        self, mock_direct_tools, mock_agent, mock_bedrock_model
    ):
        """Calls without cache_key should not populate cache."""
        from backend.agents.coaching.agent import (
            _component_cache,
            create_coaching_agent,
        )

        create_coaching_agent(user_id="user-123", jwt_token="my-jwt")

        assert len(_component_cache) == 0

    def test_evict_removes_cached_components(self):
        """evict_cached_components('conn-1') should remove the entry."""
        from backend.agents.coaching.agent import (
            _component_cache,
            evict_cached_components,
        )

        _component_cache["conn-1"] = {"tools": [], "model": None}

        evict_cached_components("conn-1")

        assert "conn-1" not in _component_cache

    def test_evict_nonexistent_key_is_noop(self):
        """Evicting a missing key should not raise."""
        from backend.agents.coaching.agent import evict_cached_components

        evict_cached_components("does-not-exist")


class TestSessionManagerRetrievalConfig:
    """Pydantic schema for AgentCoreMemoryConfig requires
    retrieval_config to be Optional[Dict[str, RetrievalConfig]], not
    a bare RetrievalConfig. See layer_build/.../strands/config.py.
    """

    def test_retrieval_config_is_dict_or_none(self, monkeypatch):
        """AgentCoreMemoryConfig must receive retrieval_config as
        dict or None, never a bare RetrievalConfig instance."""
        monkeypatch.setenv("AGENTCORE_MEMORY_ID", "mem-123")
        monkeypatch.setenv("AWS_REGION", "us-east-1")

        mock_config_cls = MagicMock(name="AgentCoreMemoryConfig")
        mock_retrieval_cls = MagicMock(name="RetrievalConfig")
        mock_session_mgr_cls = MagicMock(name="AgentCoreMemorySessionManager")

        config_mod = types.ModuleType(
            "bedrock_agentcore.memory.integrations.strands.config"
        )
        config_mod.AgentCoreMemoryConfig = mock_config_cls
        config_mod.RetrievalConfig = mock_retrieval_cls

        mgr_mod = types.ModuleType(
            "bedrock_agentcore.memory.integrations.strands.session_manager"
        )
        mgr_mod.AgentCoreMemorySessionManager = mock_session_mgr_cls

        with patch.dict(sys.modules, {
            "bedrock_agentcore": types.ModuleType("bedrock_agentcore"),
            "bedrock_agentcore.memory": types.ModuleType("bedrock_agentcore.memory"),
            "bedrock_agentcore.memory.integrations": types.ModuleType("bedrock_agentcore.memory.integrations"),
            "bedrock_agentcore.memory.integrations.strands": types.ModuleType("bedrock_agentcore.memory.integrations.strands"),
            "bedrock_agentcore.memory.integrations.strands.config": config_mod,
            "bedrock_agentcore.memory.integrations.strands.session_manager": mgr_mod,
        }):
            from backend.agents.coaching.agent import _create_session_manager

            _create_session_manager("user-42", session_id="ws-conn-abc")

        mock_config_cls.assert_called_once()
        call_kwargs = mock_config_cls.call_args.kwargs
        retrieval = call_kwargs.get("retrieval_config")
        assert retrieval is None or isinstance(retrieval, dict), (
            f"retrieval_config must be None or dict, got {type(retrieval).__name__}: {retrieval}"
        )


class TestConversationHistoryCap:
    """When session_manager is None, conversation_history must be
    truncated to the last N turns before appending to agent.messages.
    Long text-only replays contaminate Nova Pro's tool-calling."""

    @pytest.mark.usefixtures("_pending_env")
    def test_long_history_is_truncated_to_last_15(
        self, mock_direct_tools, mock_bedrock_model
    ):
        """Long conversation should be truncated to last 15 turns."""
        from backend.agents.coaching.agent import (
            MAX_REPLAYED_TURNS,
            create_coaching_agent,
        )

        assert MAX_REPLAYED_TURNS == 15, (
            "Cap constant must be 15 (empirically safe for Nova Pro)"
        )

        # Build 55 turns so that turns[-15] lands on a user turn
        # (index 40, even = user). This avoids the first-user-seen
        # guard dropping one turn and lets us assert exactly 15.
        turns = []
        for i in range(27):
            turns.append({"role": "user", "content": f"user msg {i}"})
            turns.append({"role": "assistant", "content": f"assistant msg {i}"})
        turns.append({"role": "user", "content": "user msg 27"})

        # Use a plain list for agent.messages so append() works.
        with patch("backend.agents.coaching.agent.Agent") as mock_agent_cls:
            agent_instance = MagicMock()
            agent_instance.messages = []
            mock_agent_cls.return_value = agent_instance

            create_coaching_agent(
                user_id="user-1",
                jwt_token="jwt",
                conversation_history=turns,
            )

        replayed = agent_instance.messages
        assert len(replayed) == MAX_REPLAYED_TURNS, (
            f"Expected {MAX_REPLAYED_TURNS} messages replayed, got {len(replayed)}"
        )
        # Content of first replayed message should be one of the LAST
        # 15 turns from the input.
        first_replayed_text = replayed[0]["content"][0]["text"]
        assert first_replayed_text in [
            t["content"] for t in turns[-MAX_REPLAYED_TURNS:]
        ]

    @pytest.mark.usefixtures("_pending_env")
    def test_short_history_is_unchanged(
        self, mock_direct_tools, mock_bedrock_model
    ):
        """Histories at or below the cap should replay fully."""
        from backend.agents.coaching.agent import create_coaching_agent

        turns = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
            {"role": "user", "content": "update target to SWE"},
        ]

        with patch("backend.agents.coaching.agent.Agent") as mock_agent_cls:
            agent_instance = MagicMock()
            agent_instance.messages = []
            mock_agent_cls.return_value = agent_instance

            create_coaching_agent(
                user_id="user-1",
                jwt_token="jwt",
                conversation_history=turns,
            )

        assert len(agent_instance.messages) == 3

    @pytest.mark.usefixtures("_pending_env")
    def test_cap_preserves_first_user_turn_rule(
        self, mock_direct_tools, mock_bedrock_model
    ):
        """Bedrock requires the first message to be role=user. After
        truncation, if the first kept turn is assistant, drop it."""
        from backend.agents.coaching.agent import create_coaching_agent

        # Build 20 turns; turn[-15] happens to be assistant (even index).
        turns = []
        for i in range(10):
            turns.append({"role": "user", "content": f"u{i}"})
            turns.append({"role": "assistant", "content": f"a{i}"})

        with patch("backend.agents.coaching.agent.Agent") as mock_agent_cls:
            agent_instance = MagicMock()
            agent_instance.messages = []
            mock_agent_cls.return_value = agent_instance

            create_coaching_agent(
                user_id="user-1",
                jwt_token="jwt",
                conversation_history=turns,
            )

        # Drop assistant turns that appear before the first user turn.
        assert len(agent_instance.messages) > 0
        assert agent_instance.messages[0]["role"] == "user", (
            "First replayed message must be role=user"
        )


class TestReplayNoiseFilter:
    """[proactive_check] and bare [page_context:X] turns are noise and
    must be filtered out before replay."""

    @pytest.mark.usefixtures("_pending_env")
    def test_proactive_check_turns_are_filtered(
        self, mock_direct_tools, mock_bedrock_model
    ):
        from backend.agents.coaching.agent import create_coaching_agent

        turns = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
            {"role": "user", "content": '[page_context: dashboard] [page_data: {"page":"dashboard"}] [proactive_check]'},
            {"role": "assistant", "content": "[no_suggestion]"},
            {"role": "user", "content": "Update my target"},
        ]

        with patch("backend.agents.coaching.agent.Agent") as mock_agent_cls:
            agent_instance = MagicMock()
            agent_instance.messages = []
            mock_agent_cls.return_value = agent_instance

            create_coaching_agent(
                user_id="user-1",
                jwt_token="jwt",
                conversation_history=turns,
            )

        texts = [m["content"][0]["text"] for m in agent_instance.messages]
        assert "Hello" in texts
        assert "Hi there" in texts
        assert "Update my target" in texts
        assert not any("[proactive_check]" in t for t in texts), (
            "proactive_check turns must be filtered"
        )
        assert "[no_suggestion]" not in texts, (
            "no_suggestion assistant responses must be filtered"
        )

    @pytest.mark.usefixtures("_pending_env")
    def test_bare_page_context_turns_are_filtered(
        self, mock_direct_tools, mock_bedrock_model
    ):
        """A turn that's ONLY a [page_context:X] prefix with no user
        text after it adds no signal."""
        from backend.agents.coaching.agent import create_coaching_agent

        turns = [
            {"role": "user", "content": "Hello"},
            {"role": "user", "content": "[page_context: dashboard]"},
            {"role": "user", "content": "[page_context: missions] What mission next?"},
        ]

        with patch("backend.agents.coaching.agent.Agent") as mock_agent_cls:
            agent_instance = MagicMock()
            agent_instance.messages = []
            mock_agent_cls.return_value = agent_instance

            create_coaching_agent(
                user_id="user-1",
                jwt_token="jwt",
                conversation_history=turns,
            )

        texts = [m["content"][0]["text"] for m in agent_instance.messages]
        assert "Hello" in texts
        assert any("What mission next?" in t for t in texts), (
            "page_context turns with real user text must be kept"
        )
        assert len(texts) == 2, (
            "bare [page_context: dashboard] turn must be filtered"
        )

    @pytest.mark.usefixtures("_pending_env")
    def test_filter_applied_before_cap(
        self, mock_direct_tools, mock_bedrock_model
    ):
        """Filter happens first, THEN cap to last 15. So noisy
        histories don't waste cap budget on filtered turns."""
        from backend.agents.coaching.agent import (
            MAX_REPLAYED_TURNS,
            create_coaching_agent,
        )

        # 20 noise turns followed by 5 real turns. After filtering,
        # only 5 turns remain and all should be replayed.
        turns = []
        for i in range(20):
            turns.append({
                "role": "user",
                "content": '[page_context: dashboard] [page_data: {"page":"dashboard"}] [proactive_check]',
            })
            turns.append({"role": "assistant", "content": "[no_suggestion]"})
        for i in range(5):
            turns.append({"role": "user", "content": f"real user turn {i}"})
            turns.append({"role": "assistant", "content": f"real asst turn {i}"})

        with patch("backend.agents.coaching.agent.Agent") as mock_agent_cls:
            agent_instance = MagicMock()
            agent_instance.messages = []
            mock_agent_cls.return_value = agent_instance

            create_coaching_agent(
                user_id="user-1",
                jwt_token="jwt",
                conversation_history=turns,
            )

        # 10 real turns (less than 15 cap), so all 10 should be replayed.
        assert len(agent_instance.messages) == 10
