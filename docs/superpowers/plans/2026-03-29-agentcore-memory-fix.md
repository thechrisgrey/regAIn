# AgentCore Memory Subsystem Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewire coaching memory from broken hand-rolled boto3 calls to the official Strands `AgentCoreMemorySessionManager`, provision the memory resource via CDK, and fix profile deletion cleanup.

**Architecture:** A CDK custom resource creates the AgentCore Memory resource and exports the real memory ID. The coaching agent uses `AgentCoreMemorySessionManager` for automatic turn storage + retrieval. `store_memory` is removed; `recall_memory` is rewritten to use `bedrock-agentcore` data client. Profile deletion iterates strategy namespaces with the correct memory ID.

**Tech Stack:** Python 3.12 (Lambda), AWS CDK, `bedrock-agentcore` SDK, Strands Agents SDK, pytest

**Spec:** `docs/superpowers/specs/2026-03-29-agentcore-memory-fix-design.md`

---

### Task 1: Add `bedrock-agentcore` to Lambda layer

**Files:**
- Modify: `infra/build_layer.sh`

- [ ] **Step 1: Update the pip install line**

In `infra/build_layer.sh`, change line 22 from:

```bash
  bash -c "pip install strands-agents strands-agents-tools aws-sdk-bedrock-runtime 'PyJWT[crypto]' --target /out --no-cache-dir && find /out -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true"
```

To:

```bash
  bash -c "pip install strands-agents strands-agents-tools aws-sdk-bedrock-runtime 'PyJWT[crypto]' bedrock-agentcore --target /out --no-cache-dir && find /out -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true"
```

- [ ] **Step 2: Rebuild the layer**

Run: `bash infra/build_layer.sh`
Expected: Build completes, layer includes `bedrock_agentcore` package.

- [ ] **Step 3: Verify the package is present**

Run: `ls infra/layer_build/python/ | grep bedrock_agentcore`
Expected: `bedrock_agentcore` and `bedrock_agentcore-*.dist-info` directories present.

- [ ] **Step 4: Commit**

```bash
git add infra/build_layer.sh
git commit -m "chore: add bedrock-agentcore to Lambda layer

Required for AgentCoreMemorySessionManager integration in coaching agent.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Rewrite `recall_memory` and remove `store_memory` from tools.py

**Files:**
- Modify: `backend/agents/coaching/tools.py`
- Modify: `tests/unit/agents/coaching/test_memory_tools.py`

- [ ] **Step 1: Write the new tests**

Replace the entire content of `tests/unit/agents/coaching/test_memory_tools.py` with:

```python
"""Unit tests for recall_memory tool.

Since AgentCore Memory cannot be mocked with moto, these tests use
unittest.mock.patch to mock the boto3 bedrock-agentcore client.
The @tool decorator from strands is stubbed as in other test modules.
"""

import importlib
import os
import sys
import types
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Stub the strands module so tools.py can be imported without strands-agents
# ---------------------------------------------------------------------------
_strands_stub = types.ModuleType("strands")
_strands_stub.tool = lambda fn: fn  # @tool is a no-op passthrough
sys.modules.setdefault("strands", _strands_stub)


def _load_tools():
    """Import tools module with a fresh module state."""
    mod_name = "backend.agents.coaching.tools"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    return importlib.import_module(mod_name)


class TestRecallMemory:
    """Tests for the recall_memory tool using bedrock-agentcore client."""

    def test_returns_entries_from_all_namespaces(self) -> None:
        """recall_memory queries summaries, preferences, and facts namespaces."""
        mock_client = MagicMock()

        def mock_retrieve(**kwargs):
            ns = kwargs.get("namespace", "")
            if "summaries" in ns:
                return {"memoryRecordSummaries": [
                    {"content": "Session summary: discussed Python.", "metadata": {}},
                ]}
            if "facts" in ns:
                return {"memoryRecordSummaries": [
                    {"content": "User is a veteran.", "metadata": {}},
                ]}
            return {"memoryRecordSummaries": []}

        mock_client.retrieve_memory_records.side_effect = mock_retrieve

        with patch("boto3.client", return_value=mock_client):
            os.environ["AGENTCORE_MEMORY_ID"] = "regain-coaching-a1b2c3d4e5"
            tools = _load_tools()
            result = tools.recall_memory(user_id="user-1", query="previous session")

        assert result["source"] == "memory"
        assert len(result["entries"]) == 2
        assert mock_client.retrieve_memory_records.call_count == 3

    def test_returns_empty_entries_with_memory_source(self) -> None:
        """recall_memory returns source=memory with empty entries when nothing matches."""
        mock_client = MagicMock()
        mock_client.retrieve_memory_records.return_value = {"memoryRecordSummaries": []}

        with patch("boto3.client", return_value=mock_client):
            os.environ["AGENTCORE_MEMORY_ID"] = "regain-coaching-a1b2c3d4e5"
            tools = _load_tools()
            result = tools.recall_memory(user_id="user-1", query="anything")

        assert result["source"] == "memory"
        assert result["entries"] == []

    def test_returns_unavailable_on_api_failure(self) -> None:
        """recall_memory returns source=unavailable when the API raises."""
        mock_client = MagicMock()
        mock_client.retrieve_memory_records.side_effect = Exception("Service down")

        with patch("boto3.client", return_value=mock_client):
            os.environ["AGENTCORE_MEMORY_ID"] = "regain-coaching-a1b2c3d4e5"
            tools = _load_tools()
            result = tools.recall_memory(user_id="user-1", query="anything")

        assert result["source"] == "unavailable"
        assert result["entries"] == []

    def test_returns_unavailable_when_memory_id_not_set(self) -> None:
        """recall_memory returns source=unavailable when AGENTCORE_MEMORY_ID is empty."""
        os.environ.pop("AGENTCORE_MEMORY_ID", None)
        tools = _load_tools()
        result = tools.recall_memory(user_id="user-1", query="anything")

        assert result["source"] == "unavailable"
        assert result["entries"] == []

    def test_queries_correct_namespaces(self) -> None:
        """recall_memory searches summaries, preferences, and facts namespaces."""
        mock_client = MagicMock()
        mock_client.retrieve_memory_records.return_value = {"memoryRecordSummaries": []}

        with patch("boto3.client", return_value=mock_client):
            os.environ["AGENTCORE_MEMORY_ID"] = "mem-abc1234567"
            tools = _load_tools()
            tools.recall_memory(user_id="user-xyz", query="test")

        namespaces_queried = [
            call[1]["namespace"]
            for call in mock_client.retrieve_memory_records.call_args_list
        ]
        assert "/summaries/user-xyz/" in namespaces_queried
        assert "/preferences/user-xyz/" in namespaces_queried
        assert "/facts/user-xyz/" in namespaces_queried

    def test_passes_correct_search_criteria(self) -> None:
        """recall_memory passes the query as searchCriteria."""
        mock_client = MagicMock()
        mock_client.retrieve_memory_records.return_value = {"memoryRecordSummaries": []}

        with patch("boto3.client", return_value=mock_client):
            os.environ["AGENTCORE_MEMORY_ID"] = "mem-abc1234567"
            tools = _load_tools()
            tools.recall_memory(user_id="user-1", query="networking avoidance")

        first_call = mock_client.retrieve_memory_records.call_args_list[0]
        assert first_call[1]["searchCriteria"] == {"query": {"text": "networking avoidance"}}
        assert first_call[1]["memoryId"] == "mem-abc1234567"


class TestStoreMemoryRemoved:
    """Verify store_memory no longer exists."""

    def test_store_memory_not_in_module(self) -> None:
        """store_memory should not be defined in tools.py."""
        tools = _load_tools()
        assert not hasattr(tools, "store_memory")

    def test_memory_client_helper_removed(self) -> None:
        """_get_memory_client and _memory_client should not exist."""
        tools = _load_tools()
        assert not hasattr(tools, "_get_memory_client")
        assert not hasattr(tools, "_memory_client")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/agents/coaching/test_memory_tools.py -v`
Expected: FAIL — `store_memory` still exists, `recall_memory` uses wrong client/API.

- [ ] **Step 3: Implement the changes in tools.py**

In `backend/agents/coaching/tools.py`, replace the entire "AgentCore Memory tools" section (lines 845–979, from `# AgentCore Memory tools` through the end of `store_memory`) with:

```python
# ---------------------------------------------------------------------------
# AgentCore Memory tools
# ---------------------------------------------------------------------------

_MEMORY_NAMESPACES = ["/summaries/{user_id}/", "/preferences/{user_id}/", "/facts/{user_id}/"]


@tool
def recall_memory(user_id: str, query: str) -> dict[str, Any]:
    """Retrieve relevant past conversation context for a user.

    Use this tool for targeted mid-conversation memory queries when you
    need specific context beyond what was automatically recalled at
    session start (e.g. "what did we discuss about Python skills?").

    Searches across all memory strategy namespaces (summaries, preferences,
    facts) and returns combined results ranked by relevance.

    Args:
        user_id: The authenticated user's ID.
        query: A natural-language description of what context to
            retrieve (e.g. "previous coaching session summary",
            "networking avoidance pattern").

    Returns:
        A dict with "entries" (list of memory entry dicts, each with
        content and metadata) and "source" indicating the result origin:
        - source="memory": The memory service responded successfully.
          An empty entries list means no relevant memories exist.
        - source="unavailable": The memory service could not be reached.
    """
    memory_id = os.environ.get("AGENTCORE_MEMORY_ID", "")
    if not memory_id:
        return {"entries": [], "source": "unavailable"}

    try:
        client = boto3.client(
            "bedrock-agentcore",
            region_name=os.environ.get("AWS_REGION", "us-east-1"),
        )
        all_records = []
        for ns_template in _MEMORY_NAMESPACES:
            ns = ns_template.format(user_id=user_id)
            response = client.retrieve_memory_records(
                memoryId=memory_id,
                namespace=ns,
                searchCriteria={"query": {"text": query}},
            )
            all_records.extend(response.get("memoryRecordSummaries", []))

        return {
            "entries": [
                {
                    "content": record.get("content", ""),
                    "metadata": record.get("metadata", {}),
                }
                for record in all_records
            ],
            "source": "memory",
        }
    except Exception as exc:
        logger.warning(
            "AgentCore Memory recall failed for user %s: %s", user_id, exc
        )
        return {"entries": [], "source": "unavailable"}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/agents/coaching/test_memory_tools.py -v`
Expected: All 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/agents/coaching/tools.py tests/unit/agents/coaching/test_memory_tools.py
git commit -m "feat: rewrite recall_memory to use bedrock-agentcore, remove store_memory

recall_memory now queries all strategy namespaces (summaries, preferences,
facts) via the bedrock-agentcore data client. store_memory removed entirely
— the AgentCoreMemorySessionManager handles turn storage automatically.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Wire `AgentCoreMemorySessionManager` into coaching agent

**Files:**
- Modify: `backend/agents/coaching/agent.py`

- [ ] **Step 1: Update agent.py**

Replace the full content of `backend/agents/coaching/agent.py` with:

```python
"""Coaching Agent configuration for the REGAIN platform.

Creates and configures the Strands Coaching Agent with model, tools,
session manager (AgentCore Memory), and system prompt.

Agent configuration lives here; business logic lives in tools.py;
persona definition lives in prompts.py.
"""

import logging
import os
import uuid

from strands import Agent
from strands.models.bedrock import BedrockModel

from backend.agents.coaching.prompts import get_system_prompt

logger = logging.getLogger(__name__)

_PENDING = "pending-agentcore-deploy"


def _is_gateway_available() -> bool:
    """Check if AgentCore Gateway is provisioned and ready."""
    endpoint = os.environ.get("AGENTCORE_GATEWAY_ENDPOINT", "")
    return bool(endpoint) and endpoint != _PENDING


def _get_gateway_tools(jwt_token: str):
    """Discover tools from AgentCore Gateway (lazy import)."""
    from backend.agents.coaching.gateway_client import GatewayToolClient

    gateway_id = os.environ.get("AGENTCORE_GATEWAY_ID", "regain-coaching-gateway")
    client = GatewayToolClient(gateway_id, jwt_token)
    return client.discover_tools()


def _get_direct_tools() -> list:
    """Return direct @tool functions for local invocation (lazy import)."""
    from backend.agents.coaching.tools import (
        read_user_profile,
        update_user_profile,
        get_campaign_status,
        create_campaign,
        get_current_mission,
        generate_mission,
        complete_mission,
        log_evidence,
        get_evidence_summary,
        get_market_insights,
        get_alignment,
        recall_memory,
    )

    return [
        read_user_profile,
        update_user_profile,
        get_campaign_status,
        create_campaign,
        get_current_mission,
        generate_mission,
        complete_mission,
        log_evidence,
        get_evidence_summary,
        get_market_insights,
        get_alignment,
        recall_memory,
    ]


def _create_session_manager(user_id: str):
    """Create an AgentCoreMemorySessionManager for automatic turn storage.

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

        config = AgentCoreMemoryConfig(
            memory_id=memory_id,
            actor_id=user_id,
            session_id=f"session-{uuid.uuid4().hex[:12]}",
            retrieval_config=RetrievalConfig(),
        )
        return AgentCoreMemorySessionManager(
            agentcore_memory_config=config,
            region_name=os.environ.get("AWS_REGION", "us-east-1"),
        )
    except Exception:
        logger.warning("Failed to create AgentCoreMemorySessionManager", exc_info=True)
        return None


def create_coaching_agent(
    user_id: str,
    jwt_token: str,
    callback_handler=None,
    hooks: list | None = None,
) -> Agent:
    """Create a Coaching Agent with tools, memory session manager, and system prompt.

    Args:
        user_id: The authenticated user's ID.
        jwt_token: The user's Cognito JWT for Gateway authorization.
        callback_handler: Optional callback for streaming text chunks.
        hooks: Optional list of HookProvider instances for lifecycle events.

    Returns:
        A configured Strands Agent.
    """
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
    system_prompt = get_system_prompt(valid_skill_tags=valid_tags)

    model = BedrockModel(
        model_id=os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0"),
        region_name=os.environ.get("AWS_REGION", "us-east-1"),
    )

    session_manager = _create_session_manager(user_id)

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

    return Agent(**kwargs)
```

- [ ] **Step 2: Verify no import errors**

Run: `.venv/bin/pytest tests/unit/agents/coaching/test_memory_tools.py -v`
Expected: All tests still PASS (tools.py unchanged by this task, agent.py is imported lazily).

- [ ] **Step 3: Commit**

```bash
git add backend/agents/coaching/agent.py
git commit -m "feat: add AgentCoreMemorySessionManager to coaching agent

Automatic turn storage and retrieval via Strands session manager.
Gracefully degrades to no-memory mode if AGENTCORE_MEMORY_ID is unset.
Removes store_memory from the direct tools list.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Remove `store_memory` calls from disconnect handlers

**Files:**
- Modify: `backend/handlers/coaching/stream_handler.py`
- Modify: `backend/handlers/coaching/voice_handler.py` (if it calls `store_memory`)
- Modify: `backend/handlers/voice_practice/ws_handler.py` (if it calls `store_memory`)

- [ ] **Step 1: Remove store_memory from stream_handler.py**

In `backend/handlers/coaching/stream_handler.py`, find the disconnect handler section (around lines 215-228) that calls `store_memory` and remove the entire block:

```python
    # Only store memory for fully authenticated connections.
    user_id = conn_info.get("user_id", "") if conn_info else ""
    authenticated = conn_info.get("authenticated", "false") if conn_info else "false"
    if user_id and authenticated == "true":
        try:
            from backend.agents.coaching.tools import store_memory

            session_type = conn_info.get("session_type", "general") if conn_info else "general"
            store_memory(
                user_id=user_id,
                content=f"Text coaching session ended. Session type: {session_type}. "
                "The user disconnected from the chat interface.",
            )
        except Exception:
```

Replace with a simple log statement:

```python
    user_id = conn_info.get("user_id", "") if conn_info else ""
    if user_id:
        logger.info("Coaching session ended for user %s", user_id)
```

- [ ] **Step 2: Remove store_memory from voice_handler.py**

In `backend/handlers/coaching/voice_handler.py`, find and remove the `store_memory` import and call. Replace with a log statement. Also remove `store_memory` from any tool lists passed to Nova Sonic.

- [ ] **Step 3: Remove store_memory from voice_practice/ws_handler.py**

In `backend/handlers/voice_practice/ws_handler.py`, find and remove the `store_memory` call on disconnect. Replace with a log statement.

- [ ] **Step 4: Run existing disconnect tests**

Run: `.venv/bin/pytest tests/unit/handlers/coaching/test_stream_disconnect.py -v`
Expected: Some tests FAIL (they assert `store_memory` was called). These will be updated in Task 5.

- [ ] **Step 5: Commit**

```bash
git add backend/handlers/coaching/stream_handler.py backend/handlers/coaching/voice_handler.py backend/handlers/voice_practice/ws_handler.py
git commit -m "refactor: remove store_memory calls from disconnect handlers

Session manager handles turn storage automatically. Disconnect no
longer needs to explicitly store a summary.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Update tests referencing `store_memory`

**Files:**
- Modify: `tests/unit/handlers/coaching/test_stream_disconnect.py`
- Modify: `tests/unit/agents/coaching/test_pbt_memory_isolation.py`
- Modify: `tests/unit/agents/coaching/test_pbt_audit_log.py`
- Modify: `tests/unit/agents/coaching/test_pbt_gateway_routing.py`
- Modify: `tests/unit/agents/coaching/test_pbt_jwt_validation.py`
- Modify: `tests/unit/agents/coaching/test_pbt_trace_spans.py`
- Modify: `tests/unit/agents/coaching/test_pbt_market_readonly.py`
- Modify: `tests/unit/agents/coaching/test_voice_handler.py`

- [ ] **Step 1: Update test_stream_disconnect.py**

Remove all `store_memory` assertions from disconnect tests. Tests that assert `store_memory` was called should now assert the disconnect completes without error (the logging replaces the storage). Remove the `_patch_store_memory` helper. Update the test names to reflect the new behavior.

- [ ] **Step 2: Update PBT tests that list gateway tool names**

In `test_pbt_audit_log.py`, `test_pbt_gateway_routing.py`, `test_pbt_jwt_validation.py`, `test_pbt_trace_spans.py`, and `test_pbt_market_readonly.py`: remove `"regain_store_memory"` from the tool name lists.

- [ ] **Step 3: Update test_pbt_memory_isolation.py**

Replace the existing property-based tests. Since `store_memory` is removed, the isolation test should verify that `recall_memory` for two different users queries different namespaces:

```python
"""Property-based tests for memory namespace isolation.

For any two distinct user_ids, recall_memory for user A and user B
must query different namespaces, ensuring no cross-user data leakage.
"""

import importlib
import os
import sys
import types
from unittest.mock import MagicMock, patch

from hypothesis import given, settings, assume
from hypothesis import strategies as st

_strands_stub = types.ModuleType("strands")
_strands_stub.tool = lambda fn: fn
sys.modules.setdefault("strands", _strands_stub)

_user_id_strategy = st.text(
    min_size=1,
    max_size=50,
    alphabet=st.characters(whitelist_categories=("L", "N", "Pd")),
)


def _load_tools():
    mod_name = "backend.agents.coaching.tools"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    return importlib.import_module(mod_name)


class TestMemoryNamespaceIsolation:
    """For any two distinct user_ids, recall_memory must query different namespaces."""

    @given(user_a=_user_id_strategy, user_b=_user_id_strategy)
    @settings(max_examples=100)
    def test_distinct_users_query_distinct_namespaces(
        self, user_a: str, user_b: str
    ) -> None:
        assume(user_a != user_b)

        mock_client = MagicMock()
        mock_client.retrieve_memory_records.return_value = {"memoryRecordSummaries": []}

        with patch("boto3.client", return_value=mock_client):
            os.environ["AGENTCORE_MEMORY_ID"] = "test-memory-id1234"
            tools = _load_tools()

            tools.recall_memory(user_id=user_a, query="session summary")
            namespaces_a = {
                call[1]["namespace"]
                for call in mock_client.retrieve_memory_records.call_args_list
            }

            mock_client.reset_mock()

            tools.recall_memory(user_id=user_b, query="session summary")
            namespaces_b = {
                call[1]["namespace"]
                for call in mock_client.retrieve_memory_records.call_args_list
            }

        assert namespaces_a.isdisjoint(namespaces_b), (
            f"Namespace overlap: user_a={user_a!r} namespaces {namespaces_a} "
            f"overlap with user_b={user_b!r} namespaces {namespaces_b}"
        )
```

- [ ] **Step 4: Update test_voice_handler.py**

Remove `store_memory` mocks and assertions from the voice handler disconnect tests. The disconnect should complete without calling `store_memory`.

- [ ] **Step 5: Run all updated tests**

Run: `.venv/bin/pytest tests/unit/agents/coaching/ tests/unit/handlers/coaching/ -v`
Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/
git commit -m "test: update all tests to remove store_memory references

Removes store_memory from tool lists, disconnect test assertions,
and PBT memory isolation tests. Namespace isolation now tested via
recall_memory namespace queries.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Update system prompt

**Files:**
- Modify: `backend/agents/coaching/prompts.py`

- [ ] **Step 1: Remove store_memory references from the prompt**

In `backend/agents/coaching/prompts.py`, make these changes:

1. In the "Behavioral Rules" section (line 85), remove rule 8:
   `8. At the end of every session, call store_memory with a summary of what was discussed, decisions made, evidence logged, and any patterns observed.`

2. In the "Tool Usage Guidelines" section (line 100), remove the `store_memory` line:
   `- store_memory: Call at session end with a concise summary of the session including key topics, evidence logged, missions delivered, and coaching observations.`

3. Update the `recall_memory` line (line 99) to:
   `- recall_memory: Call for targeted mid-conversation queries when you need specific context beyond what was automatically provided at session start (e.g. "what did we discuss about Python skills last time?").`

4. In the "Session Opening" section (line 63), update step 2 to note that memory is auto-recalled but the tool is available for follow-up:
   `2. Call recall_memory if you need targeted context beyond what was automatically provided (e.g. a specific topic or pattern from prior sessions).`

5. In "Behavioral Rules" rule 2 (line 79), update to:
   `2. Memory from prior sessions is automatically recalled at session start. Use recall_memory for targeted follow-up queries if you need specific context (e.g. "what was the avoidance pattern we discussed?"). If no prior context is available, acknowledge the limited context briefly.`

- [ ] **Step 2: Run the prompt tests**

Run: `.venv/bin/pytest tests/unit/agents/coaching/test_prompts.py -v`
Expected: Tests PASS (or update if they assert on `store_memory` text).

- [ ] **Step 3: Commit**

```bash
git add backend/agents/coaching/prompts.py
git commit -m "feat: update system prompt for automatic memory storage

Removes store_memory instructions. Updates recall_memory guidance to
reflect automatic retrieval at session start with targeted tool queries.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Update profile deletion to iterate strategy namespaces

**Files:**
- Modify: `backend/handlers/profile/service.py`
- Modify: `tests/integration/test_cascade_deletion.py`

- [ ] **Step 1: Update `_delete_agentcore_memory` in service.py**

In `backend/handlers/profile/service.py`, replace the `_delete_agentcore_memory` method (lines 249-293) with:

```python
    _MEMORY_NAMESPACES = [
        "regain-coaching-{user_id}",
        "/summaries/{user_id}/",
        "/preferences/{user_id}/",
        "/facts/{user_id}/",
    ]

    def _delete_agentcore_memory(self, user_id: str) -> int:
        """Delete all AgentCore Memory records for a user across all namespaces.

        Iterates over all strategy namespace patterns (summaries, preferences,
        facts) plus the legacy flat namespace to ensure complete cleanup.

        Args:
            user_id: Cognito sub from JWT claims.

        Returns:
            Number of memory records deleted.
        """
        memory_id = os.environ.get("AGENTCORE_MEMORY_ID", "")
        if not memory_id:
            logger.warning("AGENTCORE_MEMORY_ID not set; skipping memory cleanup")
            return 0

        try:
            client = boto3.client(
                "bedrock-agentcore",
                region_name=os.environ.get("AWS_REGION", "us-east-1"),
            )
        except Exception:
            logger.warning("bedrock-agentcore client unavailable; skipping memory cleanup")
            return 0

        deleted_count = 0
        for ns_template in self._MEMORY_NAMESPACES:
            namespace = ns_template.format(user_id=user_id)
            try:
                paginator = client.get_paginator("list_memory_records")
                for page in paginator.paginate(memoryId=memory_id, namespace=namespace):
                    for record in page.get("memoryRecordSummaries", []):
                        record_id = record.get("memoryRecordId", "")
                        if not record_id:
                            continue
                        client.delete_memory_record(
                            memoryId=memory_id,
                            memoryRecordId=record_id,
                        )
                        deleted_count += 1
            except Exception as exc:
                logger.warning(
                    "AgentCore Memory cleanup failed for namespace %s: %s",
                    namespace, exc,
                )

        return deleted_count
```

- [ ] **Step 2: Run integration tests**

Run: `.venv/bin/pytest tests/integration/test_cascade_deletion.py -v`
Expected: All tests PASS (memory cleanup is mocked/skipped in integration tests via env var clearing).

- [ ] **Step 3: Commit**

```bash
git add backend/handlers/profile/service.py
git commit -m "fix: iterate strategy namespaces in memory deletion

Deletion now covers summaries, preferences, facts, and legacy flat
namespaces. Each namespace is cleaned independently so a failure in
one doesn't block the others.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Update IAM permissions in agent_stack.py

**Files:**
- Modify: `infra/stacks/agent_stack.py`

- [ ] **Step 1: Update `_agentcore_memory_policy`**

In `infra/stacks/agent_stack.py`, replace the `_agentcore_memory_policy` method (lines 176-183) with:

```python
    def _agentcore_memory_policy(self) -> iam.PolicyStatement:
        """Create IAM policy statement for AgentCore Memory operations."""
        return iam.PolicyStatement(
            actions=[
                "bedrock:CreateEvent",
                "bedrock:RetrieveMemoryRecords",
                "bedrock:ListMemoryRecords",
            ],
            resources=["*"],
        )
```

- [ ] **Step 2: Update `AGENTCORE_MEMORY_ID` in `_bedrock_env`**

In `_bedrock_env()` (line 86), change the hardcoded memory ID to use `Fn.import_value` with the bootstrap fallback pattern. For now, keep the hardcoded value as a placeholder — it will be replaced when the CDK custom resource is created in Task 9:

```python
            "AGENTCORE_MEMORY_ID": cdk.Fn.import_value("RegainAgentCoreMemoryId")
                if not self.node.try_get_context("skip_alert_import")
                else "pending-memory-deploy",
```

Actually — this creates the same bootstrap chicken-and-egg problem. Keep the hardcoded string for now and update it after Task 9 deploys the memory resource. The memory ID will be set via a stack update.

Leave line 86 as-is for now:
```python
            "AGENTCORE_MEMORY_ID": "regain-coaching-memory",
```

- [ ] **Step 3: Run stack synthesis**

Run: `cd infra && .venv/bin/python -c "import app" 2>&1 | head -5`
Expected: No import errors.

- [ ] **Step 4: Commit**

```bash
git add infra/stacks/agent_stack.py
git commit -m "fix: update IAM permissions for AgentCore Memory data plane

Changes from bedrock:RetrieveMemory/CreateMemory (non-existent actions)
to bedrock:CreateEvent/RetrieveMemoryRecords/ListMemoryRecords (correct
AgentCore data plane actions).

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: Add memory resource custom resource to AgentCoreStack

**Files:**
- Modify: `infra/stacks/agentcore_stack.py`

- [ ] **Step 1: Add the custom resource**

In `infra/stacks/agentcore_stack.py`, add a method `_create_memory_resource` that creates:
1. An inline Lambda function that calls `bedrock-agentcore-control.create_memory()` on Create and `delete_memory()` on Delete
2. A `CfnCustomResource` that invokes the Lambda
3. A `CfnOutput` exporting the memory ID as `RegainAgentCoreMemoryId`

Also update the `AGENTCORE_MEMORY_ID` env var set on the profile Lambda (line 548) to use the custom resource's memory ID.

The inline Lambda code:

```python
MEMORY_LAMBDA_CODE = """
import json
import boto3
import cfnresponse

def handler(event, context):
    request_type = event.get("RequestType", "")
    props = event.get("ResourceProperties", {})
    try:
        client = boto3.client("bedrock-agentcore-control", region_name=props.get("Region", "us-east-1"))
        if request_type == "Create":
            resp = client.create_memory(
                name=props["MemoryName"],
                description=props.get("Description", ""),
                eventExpiryDuration=int(props.get("EventExpiryDuration", 90)),
                memoryStrategies=json.loads(props.get("MemoryStrategies", "[]")),
            )
            memory_id = resp["memory"]["id"]
            cfnresponse.send(event, context, cfnresponse.SUCCESS, {"MemoryId": memory_id}, memory_id)
        elif request_type == "Delete":
            memory_id = event.get("PhysicalResourceId", "")
            if memory_id:
                try:
                    client.delete_memory(memoryId=memory_id)
                except Exception:
                    pass  # Best effort on delete
            cfnresponse.send(event, context, cfnresponse.SUCCESS, {})
        else:
            # Update — no-op, return existing physical resource ID
            cfnresponse.send(event, context, cfnresponse.SUCCESS, {}, event.get("PhysicalResourceId", ""))
    except Exception as e:
        cfnresponse.send(event, context, cfnresponse.FAILED, {"Error": str(e)})
"""
```

Add the IAM permissions for the custom resource Lambda: `bedrock:CreateMemory`, `bedrock:DeleteMemory`, `bedrock:GetMemory`.

Export the memory ID and update the profile Lambda env var.

- [ ] **Step 2: Run CDK synthesis**

Run: `cd infra && eval "$(AWS_PROFILE=regain aws configure export-credentials --format env)" && AWS_DEFAULT_REGION=us-east-1 npx cdk synth RegainAgentCoreStack 2>&1 | grep -c "AWS::CloudFormation::CustomResource"`
Expected: Output `1` (one custom resource found).

- [ ] **Step 3: Commit**

```bash
git add infra/stacks/agentcore_stack.py
git commit -m "feat: provision AgentCore Memory resource via CDK custom resource

Creates the memory resource with summary, preference, and semantic
strategies. Exports the real memory ID for all consumers.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: Remove `store_memory` from AgentCore Gateway targets

**Files:**
- Modify: `infra/stacks/agentcore_stack.py`

- [ ] **Step 1: Remove the GatewayTargetRegainStoreMemory**

In `infra/stacks/agentcore_stack.py`, find the gateway target registration for `store_memory` (the `GatewayTargetRegainStoreMemory` resource) and remove it entirely. Keep `GatewayTargetRegainRecallMemory`.

- [ ] **Step 2: Update the dashboard tool names list**

In the `create_dashboard` method, remove `"regain_store_memory"` from the `tool_names` list.

- [ ] **Step 3: Commit**

```bash
git add infra/stacks/agentcore_stack.py
git commit -m "refactor: remove store_memory gateway target

store_memory is no longer a tool — the session manager handles storage.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 11: Full verification

- [ ] **Step 1: Run all backend tests**

Run: `.venv/bin/pytest tests/ -x -q`
Expected: All tests PASS.

- [ ] **Step 2: Run frontend tests and build**

Run: `cd frontend && npx vitest --run && npm run build && npm run lint`
Expected: All pass (no frontend changes in this plan).

- [ ] **Step 3: Synthesize all CDK stacks**

Run: `cd infra && eval "$(AWS_PROFILE=regain aws configure export-credentials --format env)" && AWS_DEFAULT_REGION=us-east-1 npx cdk synth --all 2>&1 | grep -c "template"`
Expected: 9 templates produced (8 app stacks + 1 layer stack).

- [ ] **Step 4: Final commit if any fixes needed**

Only if previous steps revealed issues.
