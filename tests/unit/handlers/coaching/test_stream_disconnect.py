"""Unit tests for chat stream handler disconnect memory persistence.

Verifies that _handle_disconnect stores session-end memory for known
users and gracefully handles cases with no user context.
"""

from __future__ import annotations

import importlib
import sys
from unittest.mock import MagicMock, patch

from backend.handlers.coaching.stream_handler import _handle_disconnect, _connections


def _make_event(connection_id: str = "conn-1") -> dict:
    return {"requestContext": {"connectionId": connection_id}}


def _patch_store_memory():
    """Patch store_memory by injecting a mock module into sys.modules.

    The disconnect handler uses a lazy `from backend.agents.coaching.tools import store_memory`.
    The tools module has heavy dependencies (strands, bedrock) that aren't available in unit
    tests. We inject a lightweight mock module so the import succeeds.
    """
    mock_store = MagicMock()
    mock_module = MagicMock()
    mock_module.store_memory = mock_store

    return mock_module, mock_store


class TestHandleDisconnect:
    """Tests for _handle_disconnect memory storage."""

    def setup_method(self) -> None:
        _connections.clear()
        # Remove cached tools module so each test gets a fresh import.
        sys.modules.pop("backend.agents.coaching.tools", None)

    def teardown_method(self) -> None:
        _connections.clear()
        sys.modules.pop("backend.agents.coaching.tools", None)

    @patch("backend.handlers.coaching.stream_handler.delete_connection")
    @patch("backend.handlers.coaching.stream_handler.load_connection")
    def test_stores_memory_on_disconnect(
        self,
        mock_load: MagicMock,
        mock_delete: MagicMock,
    ) -> None:
        """Disconnect should call store_memory when a user_id is known."""
        mock_module, mock_store = _patch_store_memory()
        sys.modules["backend.agents.coaching.tools"] = mock_module

        _connections["conn-1"] = {
            "user_id": "user-abc",
            "authenticated": "true",
            "session_type": "checkin",
        }

        result = _handle_disconnect(_make_event("conn-1"))

        assert result["statusCode"] == 200
        mock_store.assert_called_once()
        call_kwargs = mock_store.call_args
        assert call_kwargs[1]["user_id"] == "user-abc"
        assert "checkin" in call_kwargs[1]["content"]

    @patch("backend.handlers.coaching.stream_handler.delete_connection")
    @patch("backend.handlers.coaching.stream_handler.load_connection", return_value=None)
    def test_no_memory_when_no_user(
        self,
        mock_load: MagicMock,
        mock_delete: MagicMock,
    ) -> None:
        """Disconnect should NOT call store_memory when no user is associated."""
        mock_module, mock_store = _patch_store_memory()
        sys.modules["backend.agents.coaching.tools"] = mock_module

        result = _handle_disconnect(_make_event("conn-unknown"))

        assert result["statusCode"] == 200
        mock_store.assert_not_called()

    @patch("backend.handlers.coaching.stream_handler.delete_connection")
    @patch("backend.handlers.coaching.stream_handler.load_connection")
    def test_defaults_to_general_session_type(
        self,
        mock_load: MagicMock,
        mock_delete: MagicMock,
    ) -> None:
        """When session_type is not set, should default to general."""
        mock_module, mock_store = _patch_store_memory()
        sys.modules["backend.agents.coaching.tools"] = mock_module

        _connections["conn-1"] = {
            "user_id": "user-abc",
            "authenticated": "true",
        }

        _handle_disconnect(_make_event("conn-1"))

        call_kwargs = mock_store.call_args
        assert "general" in call_kwargs[1]["content"]

    @patch("backend.handlers.coaching.stream_handler.delete_connection")
    @patch("backend.handlers.coaching.stream_handler.load_connection")
    def test_store_memory_failure_does_not_raise(
        self,
        mock_load: MagicMock,
        mock_delete: MagicMock,
    ) -> None:
        """store_memory failure should be caught -- disconnect must not crash."""
        mock_module, mock_store = _patch_store_memory()
        mock_store.side_effect = RuntimeError("boom")
        sys.modules["backend.agents.coaching.tools"] = mock_module

        _connections["conn-1"] = {
            "user_id": "user-abc",
            "authenticated": "true",
        }

        result = _handle_disconnect(_make_event("conn-1"))

        assert result["statusCode"] == 200
        mock_store.assert_called_once()

    @patch("backend.handlers.coaching.stream_handler.delete_connection")
    @patch("backend.handlers.coaching.stream_handler.load_connection")
    def test_loads_from_dynamo_when_not_in_memory(
        self,
        mock_load: MagicMock,
        mock_delete: MagicMock,
    ) -> None:
        """When connection is not in module-level dict, should load from DynamoDB."""
        mock_module, mock_store = _patch_store_memory()
        sys.modules["backend.agents.coaching.tools"] = mock_module

        mock_load.return_value = {
            "user_id": "user-xyz",
            "authenticated": "true",
            "session_type": "onboarding",
        }

        result = _handle_disconnect(_make_event("conn-2"))

        assert result["statusCode"] == 200
        mock_load.assert_called_once_with("conn-2")
        mock_store.assert_called_once()
        assert "user-xyz" in mock_store.call_args[1]["user_id"]
