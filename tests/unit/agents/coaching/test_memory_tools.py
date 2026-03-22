"""Unit tests for recall_memory and store_memory tools.

Since AgentCore Memory cannot be mocked with moto, these tests use
unittest.mock.patch to mock the boto3 bedrock-agent-runtime client.
The @tool decorator from strands is stubbed as in other test modules.
"""

import importlib
import os
import sys
import types
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

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
    # Reset the lazy client so each test starts clean
    mod = importlib.import_module(mod_name)
    mod._memory_client = None
    return mod


class TestRecallMemory:
    """Tests for the recall_memory tool."""

    def test_returns_memory_entries_on_success(self) -> None:
        """recall_memory returns parsed entries from the API response."""
        mock_client = MagicMock()
        mock_client.retrieve_memory.return_value = {
            "memoryEntries": [
                {
                    "content": "User avoided networking missions last session.",
                    "metadata": {"timestamp": "2025-01-15T09:00:00+00:00"},
                },
                {
                    "content": "User completed 3 python missions in a row.",
                    "metadata": {"timestamp": "2025-01-14T09:00:00+00:00"},
                },
            ]
        }

        with patch("boto3.client", return_value=mock_client):
            os.environ["AGENTCORE_MEMORY_ID"] = "test-memory-id"
            tools = _load_tools()
            result = tools.recall_memory(user_id="user-1", query="previous session")

        assert result["source"] == "memory"
        assert len(result["entries"]) == 2
        assert result["entries"][0]["content"] == "User avoided networking missions last session."
        assert "timestamp" in result["entries"][0]["metadata"]

        mock_client.retrieve_memory.assert_called_once_with(
            memoryId="test-memory-id",
            namespace="regain-coaching-user-1",
            query={"text": "previous session"},
        )

    def test_returns_empty_entries_with_memory_source_on_no_results(self) -> None:
        """recall_memory returns source=memory with empty entries when no memories match."""
        mock_client = MagicMock()
        mock_client.retrieve_memory.return_value = {"memoryEntries": []}

        with patch("boto3.client", return_value=mock_client):
            os.environ["AGENTCORE_MEMORY_ID"] = "test-memory-id"
            tools = _load_tools()
            result = tools.recall_memory(user_id="user-1", query="nonexistent topic")

        assert result["source"] == "memory"
        assert result["entries"] == []

    def test_returns_unavailable_source_on_api_failure(self) -> None:
        """recall_memory returns source=unavailable when the API call raises an exception."""
        mock_client = MagicMock()
        mock_client.retrieve_memory.side_effect = Exception("Service unavailable")

        with patch("boto3.client", return_value=mock_client):
            os.environ["AGENTCORE_MEMORY_ID"] = "test-memory-id"
            tools = _load_tools()
            result = tools.recall_memory(user_id="user-1", query="anything")

        assert result["source"] == "unavailable"
        assert result["entries"] == []

    def test_returns_unavailable_source_when_client_init_fails(self) -> None:
        """recall_memory returns source=unavailable when the boto3 client cannot be created."""
        with patch("boto3.client", side_effect=Exception("Cannot create client")):
            os.environ["AGENTCORE_MEMORY_ID"] = "test-memory-id"
            tools = _load_tools()
            result = tools.recall_memory(user_id="user-1", query="anything")

        assert result["source"] == "unavailable"
        assert result["entries"] == []

    def test_uses_correct_namespace(self) -> None:
        """recall_memory scopes the query to regain-coaching-{user_id}."""
        mock_client = MagicMock()
        mock_client.retrieve_memory.return_value = {"memoryEntries": []}

        with patch("boto3.client", return_value=mock_client):
            os.environ["AGENTCORE_MEMORY_ID"] = "mem-abc"
            tools = _load_tools()
            tools.recall_memory(user_id="user-xyz-789", query="test")

        call_kwargs = mock_client.retrieve_memory.call_args[1]
        assert call_kwargs["namespace"] == "regain-coaching-user-xyz-789"


class TestStoreMemory:
    """Tests for the store_memory tool."""

    def test_returns_stored_on_success(self) -> None:
        """store_memory returns status=stored with the correct namespace."""
        mock_client = MagicMock()
        mock_client.create_memory.return_value = {}

        with patch("boto3.client", return_value=mock_client):
            os.environ["AGENTCORE_MEMORY_ID"] = "test-memory-id"
            tools = _load_tools()
            result = tools.store_memory(
                user_id="user-1",
                content="Session summary: discussed networking avoidance.",
            )

        assert result["status"] == "stored"
        assert result["namespace"] == "regain-coaching-user-1"

        mock_client.create_memory.assert_called_once()
        call_kwargs = mock_client.create_memory.call_args[1]
        assert call_kwargs["memoryId"] == "test-memory-id"
        assert call_kwargs["namespace"] == "regain-coaching-user-1"
        assert call_kwargs["content"] == {"text": "Session summary: discussed networking avoidance."}
        assert "timestamp" in call_kwargs["metadata"]
        assert call_kwargs["metadata"]["user_id"] == "user-1"

    def test_returns_unavailable_on_api_failure(self) -> None:
        """store_memory returns status=unavailable when the API call fails."""
        mock_client = MagicMock()
        mock_client.create_memory.side_effect = Exception("Service unavailable")

        with patch("boto3.client", return_value=mock_client):
            os.environ["AGENTCORE_MEMORY_ID"] = "test-memory-id"
            tools = _load_tools()
            result = tools.store_memory(user_id="user-1", content="test content")

        assert result["status"] == "unavailable"
        assert "message" in result

    def test_returns_unavailable_when_client_init_fails(self) -> None:
        """store_memory returns status=unavailable when boto3 client creation fails."""
        with patch("boto3.client", side_effect=Exception("Cannot create client")):
            os.environ["AGENTCORE_MEMORY_ID"] = "test-memory-id"
            tools = _load_tools()
            result = tools.store_memory(user_id="user-1", content="test content")

        assert result["status"] == "unavailable"
        assert "message" in result

    def test_uses_correct_namespace(self) -> None:
        """store_memory scopes storage to regain-coaching-{user_id}."""
        mock_client = MagicMock()
        mock_client.create_memory.return_value = {}

        with patch("boto3.client", return_value=mock_client):
            os.environ["AGENTCORE_MEMORY_ID"] = "mem-abc"
            tools = _load_tools()
            tools.store_memory(user_id="user-xyz-789", content="test")

        call_kwargs = mock_client.create_memory.call_args[1]
        assert call_kwargs["namespace"] == "regain-coaching-user-xyz-789"
