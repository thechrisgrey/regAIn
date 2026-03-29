"""Unit tests for chat stream handler disconnect cleanup.

Verifies that _handle_disconnect completes without error for both
known and unknown connections, cleans up state, and loads from DynamoDB
when the connection is not in the module-level dict.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from backend.handlers.coaching.stream_handler import _handle_disconnect, _connections


def _make_event(connection_id: str = "conn-1") -> dict:
    return {"requestContext": {"connectionId": connection_id}}


class TestHandleDisconnect:
    """Tests for _handle_disconnect cleanup after store_memory removal."""

    def setup_method(self) -> None:
        _connections.clear()

    def teardown_method(self) -> None:
        _connections.clear()

    @patch("backend.handlers.coaching.stream_handler.delete_connection")
    @patch("backend.handlers.coaching.stream_handler.load_connection")
    def test_disconnect_succeeds_with_known_user(
        self,
        mock_load: MagicMock,
        mock_delete: MagicMock,
    ) -> None:
        """Disconnect should return 200 when a user_id is known."""
        _connections["conn-1"] = {
            "user_id": "user-abc",
            "authenticated": "true",
            "session_type": "checkin",
        }

        result = _handle_disconnect(_make_event("conn-1"))

        assert result["statusCode"] == 200

    @patch("backend.handlers.coaching.stream_handler.delete_connection")
    @patch("backend.handlers.coaching.stream_handler.load_connection", return_value=None)
    def test_disconnect_succeeds_with_no_user(
        self,
        mock_load: MagicMock,
        mock_delete: MagicMock,
    ) -> None:
        """Disconnect should return 200 when no user is associated."""
        result = _handle_disconnect(_make_event("conn-unknown"))

        assert result["statusCode"] == 200

    @patch("backend.handlers.coaching.stream_handler.delete_connection")
    @patch("backend.handlers.coaching.stream_handler.load_connection")
    def test_disconnect_cleans_up_connection(
        self,
        mock_load: MagicMock,
        mock_delete: MagicMock,
    ) -> None:
        """Disconnect should remove the connection from the module-level dict."""
        _connections["conn-1"] = {
            "user_id": "user-abc",
            "authenticated": "true",
        }

        _handle_disconnect(_make_event("conn-1"))

        assert "conn-1" not in _connections
        mock_delete.assert_called_once_with("conn-1")

    @patch("backend.handlers.coaching.stream_handler.delete_connection")
    @patch("backend.handlers.coaching.stream_handler.load_connection")
    def test_loads_from_dynamo_when_not_in_memory(
        self,
        mock_load: MagicMock,
        mock_delete: MagicMock,
    ) -> None:
        """When connection is not in module-level dict, should load from DynamoDB."""
        mock_load.return_value = {
            "user_id": "user-xyz",
            "authenticated": "true",
            "session_type": "onboarding",
        }

        result = _handle_disconnect(_make_event("conn-2"))

        assert result["statusCode"] == 200
        mock_load.assert_called_once_with("conn-2")
