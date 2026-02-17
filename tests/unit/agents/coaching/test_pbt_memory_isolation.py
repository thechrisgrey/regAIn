"""Property-based tests for memory namespace isolation.

# Feature: coaching-agent, Property 8: Memory namespace isolation

**Validates: Requirements 9.5, 10.3**

For any two distinct user_ids, storing a memory entry for user A and then
recalling with user B's namespace should use different namespaces, ensuring
no cross-user data leakage.

Since AgentCore Memory cannot be mocked with moto, these tests use
unittest.mock.patch to mock the boto3 bedrock-agent-runtime client.
The @tool decorator from strands is stubbed as in other test modules.
"""

import importlib
import os
import sys
import types
from unittest.mock import MagicMock, patch

from hypothesis import given, settings, assume
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Stub the strands module so tools.py can be imported without strands-agents
# ---------------------------------------------------------------------------
_strands_stub = types.ModuleType("strands")
_strands_stub.tool = lambda fn: fn  # @tool is a no-op passthrough
sys.modules.setdefault("strands", _strands_stub)

# Strategy for generating user IDs: non-empty strings of letters, digits, dashes
_user_id_strategy = st.text(
    min_size=1,
    max_size=50,
    alphabet=st.characters(whitelist_categories=("L", "N", "Pd")),
)


def _load_tools():
    """Import tools module with a fresh module state."""
    mod_name = "backend.agents.coaching.tools"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    mod = importlib.import_module(mod_name)
    mod._memory_client = None
    return mod


class TestMemoryNamespaceIsolation:
    """Property 8: Memory namespace isolation.

    For any two distinct user_ids, store_memory for user A and
    recall_memory for user B must operate on different namespaces,
    preventing cross-user data leakage.
    """

    @given(user_a=_user_id_strategy, user_b=_user_id_strategy)
    @settings(max_examples=100)
    def test_distinct_users_get_distinct_namespaces(
        self, user_a: str, user_b: str
    ) -> None:
        """store_memory(user_a) and recall_memory(user_b) use different namespaces.

        # Feature: coaching-agent, Property 8: Memory namespace isolation
        **Validates: Requirements 9.5, 10.3**
        """
        assume(user_a != user_b)

        mock_client = MagicMock()
        mock_client.create_memory.return_value = {}
        mock_client.retrieve_memory.return_value = {"memoryEntries": []}

        with patch("boto3.client", return_value=mock_client):
            os.environ["AGENTCORE_MEMORY_ID"] = "test-memory-id"
            tools = _load_tools()

            # Store memory for user A
            tools.store_memory(user_id=user_a, content="User A session summary")

            # Recall memory for user B
            tools.recall_memory(user_id=user_b, query="session summary")

        # Extract the namespaces used in each call
        store_kwargs = mock_client.create_memory.call_args[1]
        recall_kwargs = mock_client.retrieve_memory.call_args[1]

        store_namespace = store_kwargs["namespace"]
        recall_namespace = recall_kwargs["namespace"]

        # Core isolation guarantee: different users → different namespaces
        assert store_namespace != recall_namespace, (
            f"Namespace collision: store_memory(user_a={user_a!r}) used "
            f"{store_namespace!r}, recall_memory(user_b={user_b!r}) used "
            f"{recall_namespace!r}"
        )

        # Verify correct namespace format
        assert store_namespace == f"regain-coaching-{user_a}"
        assert recall_namespace == f"regain-coaching-{user_b}"

    @given(user_a=_user_id_strategy, user_b=_user_id_strategy)
    @settings(max_examples=100)
    def test_recall_for_user_b_does_not_return_user_a_content(
        self, user_a: str, user_b: str
    ) -> None:
        """recall_memory(user_b) returns no content from user A's namespace.

        Simulates a namespace-aware memory service: the mock only returns
        entries when the recall namespace matches the store namespace.

        # Feature: coaching-agent, Property 8: Memory namespace isolation
        **Validates: Requirements 9.5, 10.3**
        """
        assume(user_a != user_b)

        stored_content = "User A confidential session data"
        store_namespace = f"regain-coaching-{user_a}"

        def mock_retrieve_memory(**kwargs):
            """Return entries only if the namespace matches user A's store."""
            if kwargs.get("namespace") == store_namespace:
                return {
                    "memoryEntries": [
                        {"content": stored_content, "metadata": {}}
                    ]
                }
            return {"memoryEntries": []}

        mock_client = MagicMock()
        mock_client.create_memory.return_value = {}
        mock_client.retrieve_memory.side_effect = mock_retrieve_memory

        with patch("boto3.client", return_value=mock_client):
            os.environ["AGENTCORE_MEMORY_ID"] = "test-memory-id"
            tools = _load_tools()

            # Store for user A
            tools.store_memory(user_id=user_a, content=stored_content)

            # Recall as user B
            result = tools.recall_memory(user_id=user_b, query="session data")

        # User B must NOT see user A's content
        for entry in result:
            assert entry.get("content") != stored_content, (
                f"Cross-user leakage: user_b={user_b!r} received content "
                f"from user_a={user_a!r}"
            )
