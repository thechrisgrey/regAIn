"""Tests for voice practice service."""
import json
import pytest
from unittest.mock import MagicMock, patch
import os

os.environ.setdefault("VOICE_SESSIONS_TABLE", "test-voice-sessions")
os.environ.setdefault("VOICE_PRACTICE_BUCKET_NAME", "test-bucket")

from backend.handlers.voice_practice.service import VoicePracticeService


class TestVoicePracticeService:
    """Tests for VoicePracticeService."""

    def setup_method(self):
        self.mock_db = MagicMock()
        self.mock_s3 = MagicMock()
        self.service = VoicePracticeService(
            db_client=self.mock_db,
            s3_client=self.mock_s3,
        )
        self.service.bucket_name = "test-bucket"

    def test_list_sessions_returns_sorted(self):
        self.mock_db.query.return_value = [
            {"sessionId": "a", "createdAt": "2024-01-02T00:00:00Z"},
            {"sessionId": "b", "createdAt": "2024-01-01T00:00:00Z"},
        ]

        result = self.service.list_sessions("user-123")

        assert len(result) == 2
        self.mock_db.query.assert_called_once()

    def test_list_sessions_empty(self):
        self.mock_db.query.return_value = []

        result = self.service.list_sessions("user-123")

        assert result == []

    def test_get_session_detail_with_transcript(self):
        self.mock_db.get_item.return_value = {
            "sessionId": "abc-123",
            "userId": "user-123",
            "s3TranscriptKey": "user-123/voice-practice/interview/2024-01-01/abc-123/transcript.json",
            "s3AssessmentKey": "user-123/voice-practice/interview/2024-01-01/abc-123/assessment.json",
        }
        self.mock_s3.get_object.return_value = {
            "Body": MagicMock(read=MagicMock(return_value=json.dumps({"turns": []}).encode()))
        }

        result = self.service.get_session_detail("user-123", "abc-123")

        assert result["sessionId"] == "abc-123"

    def test_get_session_detail_not_found(self):
        self.mock_db.get_item.return_value = None

        result = self.service.get_session_detail("user-123", "abc-123")

        assert result is None
