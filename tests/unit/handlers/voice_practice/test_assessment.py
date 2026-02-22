"""Tests for voice practice assessment service."""
import json
import pytest
from unittest.mock import MagicMock, patch
import os

os.environ.setdefault("BEDROCK_MODEL_ID", "us.amazon.nova-lite-v2:0")

from backend.handlers.voice_practice.assessment import AssessmentService


class TestAssessmentService:
    """Tests for AssessmentService."""

    def setup_method(self):
        self.mock_bedrock = MagicMock()
        self.service = AssessmentService()
        self.service.bedrock_client = self.mock_bedrock

    def test_generate_assessment_success(self):
        assessment_json = {
            "overallScore": 7,
            "sections": [
                {"title": "Communication", "score": 8, "feedback": "Good", "suggestions": ["More detail"]}
            ],
            "strengths": ["Clear speaking"],
            "areasForImprovement": ["Needs examples"],
            "summary": "Solid performance overall",
        }
        self.mock_bedrock.invoke_model.return_value = {
            "body": MagicMock(read=MagicMock(return_value=json.dumps({
                "output": {"message": {"content": [{"text": json.dumps(assessment_json)}]}}
            }).encode()))
        }

        result = self.service.generate_assessment(
            transcript=[{"role": "user", "text": "Hello"}],
            session_type="interview",
            target_role="Software Engineer",
            skills_focus=["Python"],
        )

        assert result["overallScore"] == 7
        assert len(result["sections"]) == 1

    def test_generate_assessment_handles_failure(self):
        self.mock_bedrock.invoke_model.side_effect = Exception("Bedrock error")

        result = self.service.generate_assessment(
            transcript=[],
            session_type="interview",
            target_role="Software Engineer",
            skills_focus=[],
        )

        assert result["overallScore"] == 0
        assert "failed" in result["summary"].lower()
