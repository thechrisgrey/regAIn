"""Unit tests for stream_handler cache eviction and session_id wiring.

Verifies that:
- _handle_disconnect calls evict_cached_components with the connection_id.
- Changing attention_mode calls evict_cached_components with the connection_id.
"""

from __future__ import annotations

import json
import sys
import types
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Stub the strands module tree so backend.agents.coaching.agent can be imported
# lazily inside the handler under test.
# ---------------------------------------------------------------------------
_strands_stub = types.ModuleType("strands")
_strands_stub.Agent = MagicMock  # type: ignore[attr-defined]
_strands_stub.tool = lambda f: f  # type: ignore[attr-defined]

_models_stub = types.ModuleType("strands.models")
_bedrock_stub = types.ModuleType("strands.models.bedrock")
_bedrock_stub.BedrockModel = MagicMock  # type: ignore[attr-defined]

_strands_stub.models = _models_stub  # type: ignore[attr-defined]
_models_stub.bedrock = _bedrock_stub  # type: ignore[attr-defined]

_hooks_stub = types.ModuleType("strands.hooks")
_hooks_stub.BeforeToolCallEvent = type("BeforeToolCallEvent", (), {})  # type: ignore[attr-defined]
_hooks_stub.AfterToolCallEvent = type("AfterToolCallEvent", (), {})  # type: ignore[attr-defined]

sys.modules.setdefault("strands", _strands_stub)
sys.modules.setdefault("strands.models", _models_stub)
sys.modules.setdefault("strands.models.bedrock", _bedrock_stub)
sys.modules.setdefault("strands.hooks", _hooks_stub)

from backend.handlers.coaching.stream_handler import (  # noqa: E402
    _connections,
    _handle_default,
    _handle_disconnect,
)


def _make_event(connection_id: str, body: str = "") -> dict:
    return {
        "requestContext": {
            "connectionId": connection_id,
            "domainName": "test.execute-api.us-east-1.amazonaws.com",
            "stage": "prod",
        },
        "body": body,
    }


class TestDisconnectEvictsCache:
    """Tests that _handle_disconnect evicts cached agent components."""

    def setup_method(self) -> None:
        _connections.clear()

    def teardown_method(self) -> None:
        _connections.clear()

    @patch("backend.agents.coaching.agent.evict_cached_components")
    @patch("backend.handlers.coaching.stream_handler.delete_connection")
    @patch("backend.handlers.coaching.stream_handler.load_connection")
    def test_disconnect_evicts_cache(
        self,
        mock_load: MagicMock,
        mock_delete: MagicMock,
        mock_evict: MagicMock,
    ) -> None:
        """Disconnect should call evict_cached_components with the connection_id."""
        _connections["conn-1"] = {
            "user_id": "user-abc",
            "authenticated": "true",
            "session_type": "checkin",
        }

        result = _handle_disconnect(_make_event("conn-1"))

        assert result["statusCode"] == 200
        mock_evict.assert_called_once_with("conn-1")

    @patch("backend.agents.coaching.agent.evict_cached_components")
    @patch("backend.handlers.coaching.stream_handler.delete_connection")
    @patch("backend.handlers.coaching.stream_handler.load_connection", return_value=None)
    def test_disconnect_evicts_cache_even_when_no_user(
        self,
        mock_load: MagicMock,
        mock_delete: MagicMock,
        mock_evict: MagicMock,
    ) -> None:
        """Disconnect should evict cache even if no user is associated."""
        result = _handle_disconnect(_make_event("conn-2"))

        assert result["statusCode"] == 200
        mock_evict.assert_called_once_with("conn-2")

    @patch("backend.agents.coaching.agent.evict_cached_components")
    @patch("backend.handlers.coaching.stream_handler.delete_connection")
    @patch("backend.handlers.coaching.stream_handler.load_connection")
    def test_evict_called_before_delete(
        self,
        mock_load: MagicMock,
        mock_delete: MagicMock,
        mock_evict: MagicMock,
    ) -> None:
        """evict_cached_components should be called before delete_connection."""
        call_order: list[str] = []
        mock_evict.side_effect = lambda *a: call_order.append("evict")
        mock_delete.side_effect = lambda *a: call_order.append("delete")

        _connections["conn-1"] = {
            "user_id": "user-abc",
            "authenticated": "true",
        }

        _handle_disconnect(_make_event("conn-1"))

        assert call_order == ["evict", "delete"]


class TestAttentionModeEvictsCache:
    """Tests that changing attention_mode evicts cached agent components."""

    def setup_method(self) -> None:
        _connections.clear()

    def teardown_method(self) -> None:
        _connections.clear()

    @patch("backend.agents.coaching.agent.evict_cached_components")
    @patch("backend.handlers.shared.thread.update_attention_mode")
    @patch("backend.handlers.coaching.stream_handler._post_to_connection")
    def test_attention_mode_evicts_cache(
        self,
        mock_post: MagicMock,
        mock_set_mode: MagicMock,
        mock_evict: MagicMock,
    ) -> None:
        """Changing attention mode should call evict_cached_components with connection_id."""
        _connections["conn-1"] = {
            "user_id": "user-abc",
            "authenticated": "true",
        }
        body = json.dumps({"type": "attention_mode", "mode": "explore"})

        result = _handle_default(_make_event("conn-1", body))

        assert result["statusCode"] == 200
        mock_set_mode.assert_called_once_with("user-abc", "explore")
        mock_evict.assert_called_once_with("conn-1")

    @patch("backend.agents.coaching.agent.evict_cached_components")
    @patch("backend.handlers.shared.thread.update_attention_mode", side_effect=ValueError("bad mode"))
    @patch("backend.handlers.coaching.stream_handler._post_to_connection")
    def test_attention_mode_no_evict_on_invalid_mode(
        self,
        mock_post: MagicMock,
        mock_set_mode: MagicMock,
        mock_evict: MagicMock,
    ) -> None:
        """Invalid mode should NOT evict cache (ValueError is raised before evict)."""
        _connections["conn-1"] = {
            "user_id": "user-abc",
            "authenticated": "true",
        }
        body = json.dumps({"type": "attention_mode", "mode": "invalid"})

        result = _handle_default(_make_event("conn-1", body))

        assert result["statusCode"] == 200
        mock_evict.assert_not_called()
