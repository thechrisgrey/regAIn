# AgentCore Session Fix + Agent Component Caching

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix orphaned AgentCore Memory sessions by using stable session IDs, and cache expensive agent components to avoid redundant tool discovery / model init / DynamoDB queries on every message.

**Architecture:** Two changes: (1) `_create_session_manager()` accepts an explicit `session_id` instead of generating a random UUID, so WebSocket sessions produce stable AgentCore Memory sessions. (2) `create_coaching_agent()` caches expensive components (tools, model, session manager, system prompt) keyed by an optional `cache_key`, so repeated calls within the same Lambda container skip redundant setup.

**Tech Stack:** Python, Strands SDK, AgentCore Memory SDK, pytest

---

### Task 1: Add `session_id` parameter to agent.py

**Files:**
- Modify: `backend/agents/coaching/agent.py:72-104` (`_create_session_manager`), `107-184` (`create_coaching_agent`)
- Test: `tests/unit/agents/coaching/test_agent.py`

- [ ] **Step 1: Write failing tests for session_id passthrough**

Add to `tests/unit/agents/coaching/test_agent.py`:

```python
class TestSessionId:
    """Tests for session_id passthrough to AgentCoreMemorySessionManager."""

    @pytest.mark.usefixtures("_pending_env")
    def test_session_id_passed_to_session_manager(
        self, mock_direct_tools, mock_agent, mock_bedrock_model, monkeypatch
    ):
        """When session_id is provided, it should be used instead of a UUID."""
        monkeypatch.setenv("AGENTCORE_MEMORY_ID", "mem-123")

        mock_config = MagicMock()
        mock_sm_cls = MagicMock()
        with patch.dict(sys.modules, {
            "bedrock_agentcore.memory.integrations.strands.config": MagicMock(
                AgentCoreMemoryConfig=mock_config,
                RetrievalConfig=MagicMock(),
            ),
            "bedrock_agentcore.memory.integrations.strands.session_manager": MagicMock(
                AgentCoreMemorySessionManager=mock_sm_cls,
            ),
        }):
            from backend.agents.coaching.agent import create_coaching_agent

            create_coaching_agent(
                user_id="user-123",
                jwt_token="my-jwt",
                session_id="ws-conn-abc",
            )

            mock_config.assert_called_once()
            call_kwargs = mock_config.call_args
            assert call_kwargs.kwargs.get("session_id") or call_kwargs[1].get("session_id") == "ws-conn-abc"

    @pytest.mark.usefixtures("_pending_env")
    def test_session_id_defaults_to_uuid_when_none(
        self, mock_direct_tools, mock_agent, mock_bedrock_model, monkeypatch
    ):
        """When session_id is None, a UUID-based session_id should be generated."""
        monkeypatch.setenv("AGENTCORE_MEMORY_ID", "mem-123")

        mock_config = MagicMock()
        with patch.dict(sys.modules, {
            "bedrock_agentcore.memory.integrations.strands.config": MagicMock(
                AgentCoreMemoryConfig=mock_config,
                RetrievalConfig=MagicMock(),
            ),
            "bedrock_agentcore.memory.integrations.strands.session_manager": MagicMock(
                AgentCoreMemorySessionManager=MagicMock(),
            ),
        }):
            from backend.agents.coaching.agent import create_coaching_agent

            create_coaching_agent(
                user_id="user-123",
                jwt_token="my-jwt",
            )

            call_kwargs = mock_config.call_args
            sid = call_kwargs.kwargs.get("session_id", call_kwargs[1].get("session_id", ""))
            assert sid.startswith("session-")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/agents/coaching/test_agent.py::TestSessionId -v`
Expected: FAIL — `create_coaching_agent` does not accept `session_id` parameter yet.

- [ ] **Step 3: Implement session_id passthrough**

In `backend/agents/coaching/agent.py`, modify `_create_session_manager`:

```python
def _create_session_manager(user_id: str, session_id: str | None = None):
    """Create an AgentCoreMemorySessionManager for automatic turn storage.

    Args:
        user_id: The authenticated user's ID (used as actor_id).
        session_id: Stable session identifier. If None, a random UUID is used.

    Returns None if the memory ID is not configured or initialization fails.
    The agent will run without memory in that case (graceful degradation).
    """
    memory_id = os.environ.get("AGENTCORE_MEMORY_ID", "")
    if not memory_id or memory_id == _PENDING:
        logger.info("AGENTCORE_MEMORY_ID not set; running without memory")
        return None

    try:
        from bedrock_agentcore.memory.integrations.strands.config import (
            AgentCoreMemoryConfig,
            RetrievalConfig,
        )
        from bedrock_agentcore.memory.integrations.strands.session_manager import (
            AgentCoreMemorySessionManager,
        )

        resolved_session_id = session_id or f"session-{uuid.uuid4().hex[:12]}"
        config = AgentCoreMemoryConfig(
            memory_id=memory_id,
            actor_id=user_id,
            session_id=resolved_session_id,
            retrieval_config=RetrievalConfig(),
        )
        return AgentCoreMemorySessionManager(
            agentcore_memory_config=config,
            region_name=os.environ.get("AWS_REGION", "us-east-1"),
        )
    except Exception:
        logger.warning("Failed to create AgentCoreMemorySessionManager", exc_info=True)
        return None
```

In `create_coaching_agent`, add the parameter and pass it through:

```python
def create_coaching_agent(
    user_id: str,
    jwt_token: str,
    callback_handler=None,
    hooks: list | None = None,
    conversation_history: list | None = None,
    attention_mode: str = "focus",
    session_id: str | None = None,
) -> Agent:
```

And change line 159:

```python
    session_manager = _create_session_manager(user_id, session_id=session_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/agents/coaching/test_agent.py -v`
Expected: All tests PASS (new + existing).

- [ ] **Step 5: Commit**

```bash
git add backend/agents/coaching/agent.py tests/unit/agents/coaching/test_agent.py
git commit -m "feat: add session_id parameter to create_coaching_agent

Allows callers to pass a stable session_id for AgentCore Memory
instead of generating a random UUID per call. WebSocket handlers
will pass connection_id to anchor memory sessions."
```

---

### Task 2: Add component caching to agent.py

**Files:**
- Modify: `backend/agents/coaching/agent.py`
- Test: `tests/unit/agents/coaching/test_agent.py`

The cache stores the expensive-to-compute pieces: tools, model, session_manager, system_prompt, attention_mode. A new `Agent()` is still constructed per call (cheap), but the components it's built from are reused.

- [ ] **Step 1: Write failing tests for component caching**

Add to `tests/unit/agents/coaching/test_agent.py`:

```python
class TestComponentCaching:
    """Tests for agent component caching via cache_key."""

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
        """First call with cache_key should store components in cache."""
        from backend.agents.coaching.agent import create_coaching_agent, _component_cache

        create_coaching_agent(
            user_id="user-123",
            jwt_token="my-jwt",
            cache_key="conn-1",
        )

        assert "conn-1" in _component_cache
        assert "tools" in _component_cache["conn-1"]
        assert "model" in _component_cache["conn-1"]
        assert "system_prompt" in _component_cache["conn-1"]

    @pytest.mark.usefixtures("_pending_env")
    def test_cache_hit_skips_tool_loading(
        self, mock_direct_tools, mock_agent, mock_bedrock_model
    ):
        """Second call with same cache_key should not re-load tools."""
        mock_fn, tools = mock_direct_tools
        from backend.agents.coaching.agent import create_coaching_agent

        create_coaching_agent(user_id="user-123", jwt_token="my-jwt", cache_key="conn-1")
        mock_fn.reset_mock()

        create_coaching_agent(user_id="user-123", jwt_token="my-jwt", cache_key="conn-1")
        mock_fn.assert_not_called()

    @pytest.mark.usefixtures("_pending_env")
    def test_cache_hit_skips_model_creation(
        self, mock_direct_tools, mock_agent, mock_bedrock_model
    ):
        """Second call with same cache_key should not re-create BedrockModel."""
        from backend.agents.coaching.agent import create_coaching_agent

        create_coaching_agent(user_id="user-123", jwt_token="my-jwt", cache_key="conn-1")
        mock_bedrock_model.reset_mock()

        create_coaching_agent(user_id="user-123", jwt_token="my-jwt", cache_key="conn-1")
        mock_bedrock_model.assert_not_called()

    @pytest.mark.usefixtures("_pending_env")
    def test_no_cache_key_skips_caching(
        self, mock_direct_tools, mock_agent, mock_bedrock_model
    ):
        """Calls without cache_key should not use or populate cache."""
        from backend.agents.coaching.agent import create_coaching_agent, _component_cache

        create_coaching_agent(user_id="user-123", jwt_token="my-jwt")

        assert len(_component_cache) == 0

    @pytest.mark.usefixtures("_pending_env")
    def test_evict_removes_cached_components(
        self, mock_direct_tools, mock_agent, mock_bedrock_model
    ):
        """evict_cached_components should remove the entry."""
        from backend.agents.coaching.agent import (
            create_coaching_agent,
            evict_cached_components,
            _component_cache,
        )

        create_coaching_agent(user_id="user-123", jwt_token="my-jwt", cache_key="conn-1")
        assert "conn-1" in _component_cache

        evict_cached_components("conn-1")
        assert "conn-1" not in _component_cache

    @pytest.mark.usefixtures("_pending_env")
    def test_evict_nonexistent_key_is_noop(
        self, mock_direct_tools, mock_agent, mock_bedrock_model
    ):
        """Evicting a key that doesn't exist should not raise."""
        from backend.agents.coaching.agent import evict_cached_components

        evict_cached_components("nonexistent")  # should not raise
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/agents/coaching/test_agent.py::TestComponentCaching -v`
Expected: FAIL — `_component_cache`, `cache_key`, and `evict_cached_components` don't exist yet.

- [ ] **Step 3: Implement component caching**

In `backend/agents/coaching/agent.py`, add at module level (after `_PENDING`):

```python
# Component cache: keyed by caller-supplied cache_key (e.g. WebSocket connection_id).
# Stores expensive-to-compute pieces so repeated calls skip tool discovery,
# model init, DynamoDB queries, and session manager creation.
_component_cache: Dict[str, Dict[str, Any]] = {}


def evict_cached_components(cache_key: str) -> None:
    """Remove cached agent components for the given key."""
    _component_cache.pop(cache_key, None)
```

Add `from typing import Any, Dict` to imports.

Modify `create_coaching_agent` to accept `cache_key` and use the cache:

```python
def create_coaching_agent(
    user_id: str,
    jwt_token: str,
    callback_handler=None,
    hooks: list | None = None,
    conversation_history: list | None = None,
    attention_mode: str = "focus",
    session_id: str | None = None,
    cache_key: str | None = None,
) -> Agent:
```

Replace the body (tool loading through Agent construction) with:

```python
    cached = _component_cache.get(cache_key) if cache_key else None

    if cached:
        tools = cached["tools"]
        system_prompt = cached["system_prompt"]
        model = cached["model"]
        session_manager = cached["session_manager"]
    else:
        from backend.agents.coaching.circuit_breaker import gateway_circuit

        if _is_gateway_available() and not gateway_circuit.is_open:
            try:
                logger.info("Using AgentCore Gateway tools")
                tools = _get_gateway_tools(jwt_token)
                gateway_circuit.record_success()
            except Exception:
                logger.warning("Gateway tool discovery failed, falling back to direct tools")
                gateway_circuit.record_failure()
                tools = _get_direct_tools()
        else:
            if gateway_circuit.is_open:
                logger.info("Gateway circuit open, using direct tool invocation")
            else:
                logger.info("Gateway not provisioned, using direct tool invocation")
            tools = _get_direct_tools()

        from backend.agents.coaching.tools import get_valid_skill_tags

        valid_tags = get_valid_skill_tags(user_id)
        system_prompt = get_system_prompt(
            valid_skill_tags=valid_tags,
            attention_mode=attention_mode,
        )

        model = BedrockModel(
            model_id=os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0"),
            region_name=os.environ.get("AWS_REGION", "us-east-1"),
        )

        session_manager = _create_session_manager(user_id, session_id=session_id)

        if cache_key:
            _component_cache[cache_key] = {
                "tools": tools,
                "system_prompt": system_prompt,
                "model": model,
                "session_manager": session_manager,
            }

    kwargs: dict = {
        "model": model,
        "system_prompt": system_prompt,
        "tools": tools,
    }
    if session_manager is not None:
        kwargs["session_manager"] = session_manager
    if callback_handler is not None:
        kwargs["callback_handler"] = callback_handler
    if hooks:
        kwargs["hooks"] = hooks

    agent = Agent(**kwargs)

    if conversation_history:
        for turn in conversation_history:
            role = turn.get("role", "")
            content = turn.get("content", "")
            if role == "user":
                agent.messages.append({"role": "user", "content": [{"text": content}]})
            elif role == "assistant":
                agent.messages.append({"role": "assistant", "content": [{"text": content}]})

    return agent
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/agents/coaching/test_agent.py -v`
Expected: All tests PASS (new + existing).

- [ ] **Step 5: Commit**

```bash
git add backend/agents/coaching/agent.py tests/unit/agents/coaching/test_agent.py
git commit -m "feat: add component caching to create_coaching_agent

Cache tools, model, session_manager, and system_prompt keyed by
cache_key. Repeated calls with the same key skip tool discovery,
DynamoDB queries, and model/session manager construction."
```

---

### Task 3: Wire up session_id and caching in stream_handler.py

**Files:**
- Modify: `backend/handlers/coaching/stream_handler.py`
- Test: `tests/unit/handlers/coaching/test_stream_handler_cache.py` (new)

- [ ] **Step 1: Write failing tests for cache wiring and eviction**

Create `tests/unit/handlers/coaching/test_stream_handler_cache.py`:

```python
"""Unit tests for agent component cache wiring in stream_handler.

Verifies that:
- _handle_disconnect evicts cached components
- attention_mode messages evict cached components
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from backend.handlers.coaching.stream_handler import (
    _connections,
    _handle_disconnect,
    _handle_default,
)


def _make_event(connection_id: str = "conn-1", body: str = "{}") -> dict:
    return {
        "requestContext": {
            "connectionId": connection_id,
            "domainName": "ws.example.com",
            "stage": "prod",
        },
        "body": body,
    }


class TestDisconnectEvictsCache:
    """Disconnect should clean up both _connections and agent component cache."""

    def setup_method(self) -> None:
        _connections.clear()

    def teardown_method(self) -> None:
        _connections.clear()

    @patch("backend.handlers.coaching.stream_handler.delete_connection")
    @patch("backend.handlers.coaching.stream_handler.load_connection", return_value=None)
    @patch("backend.agents.coaching.agent.evict_cached_components")
    def test_disconnect_evicts_agent_cache(
        self,
        mock_evict: MagicMock,
        mock_load: MagicMock,
        mock_delete: MagicMock,
    ) -> None:
        """Disconnect should call evict_cached_components with connection_id."""
        _connections["conn-1"] = {
            "user_id": "user-abc",
            "authenticated": "true",
        }

        _handle_disconnect(_make_event("conn-1"))

        mock_evict.assert_called_once_with("conn-1")


class TestAttentionModeEvictsCache:
    """Attention mode changes should evict cached agent components."""

    def setup_method(self) -> None:
        _connections.clear()

    def teardown_method(self) -> None:
        _connections.clear()

    @patch("backend.handlers.coaching.stream_handler._post_to_connection")
    @patch("backend.agents.coaching.agent.evict_cached_components")
    def test_attention_mode_evicts_cache(
        self,
        mock_evict: MagicMock,
        mock_post: MagicMock,
    ) -> None:
        """Changing attention mode should evict the cached components."""
        import json

        _connections["conn-1"] = {
            "user_id": "user-abc",
            "authenticated": "true",
        }

        body = json.dumps({"type": "attention_mode", "mode": "explore"})
        with patch(
            "backend.handlers.shared.thread.update_attention_mode"
        ):
            _handle_default(_make_event("conn-1", body))

        mock_evict.assert_called_once_with("conn-1")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/handlers/coaching/test_stream_handler_cache.py -v`
Expected: FAIL — `evict_cached_components` is not called in the handler yet.

- [ ] **Step 3: Wire up session_id, cache_key, and eviction in stream_handler.py**

**3a. Add import at top of `stream_handler.py` (after existing imports):**

No new top-level import needed — `evict_cached_components` and `create_coaching_agent` are already lazily imported inside functions.

**3b. In `_handle_disconnect` (around line 211), add eviction before the delete:**

```python
    # Evict cached agent components for this connection.
    from backend.agents.coaching.agent import evict_cached_components
    evict_cached_components(connection_id)

    delete_connection(connection_id)
```

**3c. In `attention_mode` handler (around line 345-352), add eviction after updating mode:**

```python
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
```

**3d. In the regular chat handler, pass `session_id` and `cache_key` to all `create_coaching_agent` calls.**

For the auto-compact agent (~line 525):

```python
                compact_agent = create_coaching_agent(
                    user_id=user_id,
                    jwt_token=jwt_token,
                    conversation_history=thread["turns"],
                    attention_mode=thread["attentionMode"],
                    session_id=connection_id,
                )
```

For the main chat agent (~line 540):

```python
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
```

Note: only the main chat agent uses `cache_key`. The compact agent is throwaway (special prompt).

**3e. After auto-compaction succeeds (~line 535), evict the cache since the thread changed:**

```python
                compact_thread(user_id, thread["turns"], str(summary_result))
                # Evict cache — conversation history changed after compaction.
                from backend.agents.coaching.agent import evict_cached_components
                evict_cached_components(connection_id)
                thread = load_active_thread(user_id)
```

**3f. In the `compact` message handler (~line 363), pass `session_id`:**

```python
            agent = create_coaching_agent(
                user_id=user_id,
                jwt_token=body.get("token", ""),
                conversation_history=thread["turns"],
                attention_mode=thread["attentionMode"],
                session_id=connection_id,
            )
```

**3g. In the `action_event` handler (~line 414), pass `session_id`:**

```python
            agent = create_coaching_agent(
                user_id=user_id,
                jwt_token=body.get("token", ""),
                conversation_history=thread["turns"],
                attention_mode=mode,
                session_id=connection_id,
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/handlers/coaching/test_stream_handler_cache.py tests/unit/handlers/coaching/test_stream_disconnect.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Run the full backend test suite**

Run: `.venv/bin/pytest tests/ -x -q`
Expected: All existing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add backend/handlers/coaching/stream_handler.py tests/unit/handlers/coaching/test_stream_handler_cache.py
git commit -m "feat: wire up stable session_id and component caching in stream handler

Pass connection_id as session_id to all create_coaching_agent calls
so AgentCore Memory sessions persist across messages. Use cache_key
for the main chat path to skip redundant tool/model/session setup.
Evict cache on attention_mode change, compaction, and disconnect."
```

---

### Task 4: Verify full test suite and push

- [ ] **Step 1: Run full backend tests**

Run: `.venv/bin/pytest tests/ -x -q`
Expected: All ~665 tests pass.

- [ ] **Step 2: Run frontend tests (sanity check — no frontend changes)**

Run: `cd frontend && npx vitest --run 2>&1 | tail -5`
Expected: All 240 tests pass.

- [ ] **Step 3: Push branch**

```bash
git push -u origin feat/agentcore-session-fix
```
