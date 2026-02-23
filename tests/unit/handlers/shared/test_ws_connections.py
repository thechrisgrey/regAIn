"""Unit tests for the WebSocket connection state persistence module."""

import os
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _reset_module():
    """Reset the module-level _table before each test."""
    import backend.handlers.shared.ws_connections as mod

    mod._table = None
    yield
    mod._table = None


@pytest.fixture()
def mock_table():
    """Provide a mock DynamoDB Table and patch the env var."""
    table = MagicMock()
    with patch.dict(os.environ, {"WS_CONNECTIONS_TABLE": "TestConnections"}), \
         patch("boto3.resource") as mock_resource:
        mock_resource.return_value.Table.return_value = table
        yield table


class TestStoreConnection:
    """Tests for store_connection."""

    def test_stores_item_in_dynamodb(self, mock_table: MagicMock) -> None:
        from backend.handlers.shared.ws_connections import store_connection

        store_connection("conn-1", {
            "user_id": "user-abc",
            "jwt_token": "tok-xyz",
            "session_type": "interview",
        })

        mock_table.put_item.assert_called_once()
        item = mock_table.put_item.call_args[1]["Item"]
        assert item["connectionId"] == "conn-1"
        assert item["userId"] == "user-abc"
        assert item["jwtToken"] == "tok-xyz"
        assert item["sessionType"] == "interview"
        assert "ttl" in item

    def test_silent_failure_on_error(self, mock_table: MagicMock) -> None:
        from backend.handlers.shared.ws_connections import store_connection

        mock_table.put_item.side_effect = Exception("DynamoDB error")
        # Should not raise
        store_connection("conn-1", {"user_id": "u1"})


class TestLoadConnection:
    """Tests for load_connection."""

    def test_returns_connection_data(self, mock_table: MagicMock) -> None:
        from backend.handlers.shared.ws_connections import load_connection

        mock_table.get_item.return_value = {
            "Item": {
                "connectionId": "conn-2",
                "userId": "user-def",
                "jwtToken": "tok-abc",
                "sessionType": "mission_discussion",
            }
        }

        result = load_connection("conn-2")

        assert result == {
            "user_id": "user-def",
            "jwt_token": "tok-abc",
            "session_type": "mission_discussion",
        }

    def test_returns_none_when_not_found(self, mock_table: MagicMock) -> None:
        from backend.handlers.shared.ws_connections import load_connection

        mock_table.get_item.return_value = {}

        result = load_connection("conn-nonexistent")
        assert result is None

    def test_silent_failure_on_error(self, mock_table: MagicMock) -> None:
        from backend.handlers.shared.ws_connections import load_connection

        mock_table.get_item.side_effect = Exception("DynamoDB error")
        result = load_connection("conn-2")
        assert result is None


class TestDeleteConnection:
    """Tests for delete_connection."""

    def test_deletes_item_from_dynamodb(self, mock_table: MagicMock) -> None:
        from backend.handlers.shared.ws_connections import delete_connection

        delete_connection("conn-3")

        mock_table.delete_item.assert_called_once_with(
            Key={"connectionId": "conn-3"}
        )

    def test_silent_failure_on_error(self, mock_table: MagicMock) -> None:
        from backend.handlers.shared.ws_connections import delete_connection

        mock_table.delete_item.side_effect = Exception("DynamoDB error")
        # Should not raise
        delete_connection("conn-3")


class TestMissingEnvVar:
    """Tests for missing WS_CONNECTIONS_TABLE env var."""

    def test_store_connection_fails_silently(self) -> None:
        from backend.handlers.shared.ws_connections import store_connection

        # No env var set, should not raise
        store_connection("conn-x", {"user_id": "u1"})

    def test_load_connection_returns_none(self) -> None:
        from backend.handlers.shared.ws_connections import load_connection

        result = load_connection("conn-x")
        assert result is None

    def test_delete_connection_fails_silently(self) -> None:
        from backend.handlers.shared.ws_connections import delete_connection

        # No env var set, should not raise
        delete_connection("conn-x")
