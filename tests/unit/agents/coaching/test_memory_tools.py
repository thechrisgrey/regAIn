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

_strands_stub = types.ModuleType("strands")
_strands_stub.tool = lambda fn: fn
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
