"""Tests for voice practice API handler."""
import json
import pytest
from unittest.mock import patch, MagicMock

# Set env vars before importing handler
import os
os.environ.setdefault("VOICE_SESSIONS_TABLE", "test-voice-sessions")
os.environ.setdefault("VOICE_PRACTICE_BUCKET_NAME", "test-bucket")

from backend.handlers.voice_practice.api_handler import lambda_handler


def _make_event(method="GET", path="/voice-sessions", path_params=None):
    """Build a minimal API Gateway event."""
    event = {
        "httpMethod": method,
        "path": path,
        "requestContext": {
            "authorizer": {
                "claims": {"sub": "test-user-123"}
            }
        },
        "pathParameters": path_params,
    }
    return event


class TestVoicePracticeApiHandler:
    """Tests for the voice practice REST API handler."""

    def test_list_sessions_returns_200(self):
        with patch("backend.handlers.voice_practice.api_handler.VoicePracticeService") as MockService:
            mock_svc = MockService.return_value
            mock_svc.list_sessions.return_value = {"items": [], "nextCursor": None}

            response = lambda_handler(_make_event(), None)

            assert response["statusCode"] == 200
            body = json.loads(response["body"])
            assert "sessions" in body

    def test_get_session_detail_returns_200(self):
        with patch("backend.handlers.voice_practice.api_handler.VoicePracticeService") as MockService:
            mock_svc = MockService.return_value
            mock_svc.get_session_detail.return_value = {
                "session": {"sessionId": "abc-123"},
                "transcript": None,
                "assessment": None,
            }

            event = _make_event(
                path="/voice-sessions/abc-123",
                path_params={"sessionId": "abc-123"},
            )
            response = lambda_handler(event, None)

            assert response["statusCode"] == 200

    def test_missing_auth_returns_401(self):
        event = _make_event()
        event["requestContext"]["authorizer"]["claims"] = {}

        response = lambda_handler(event, None)
        assert response["statusCode"] == 401

    def test_unsupported_method_returns_400(self):
        response = lambda_handler(_make_event(method="POST"), None)
        assert response["statusCode"] == 400
