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
