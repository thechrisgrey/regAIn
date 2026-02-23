"""Voice practice assessment service.

Generates structured assessments from session transcripts using
Amazon Bedrock Nova Lite.
"""

import json
import logging
import os
from typing import Any, Dict

import boto3

from backend.handlers.voice_practice.prompts import get_assessment_prompt

logger = logging.getLogger(__name__)


class AssessmentService:
    """Generates post-session assessments via Bedrock Nova Lite.

    Analyzes voice practice transcripts and produces structured JSON
    with scores, feedback, and improvement suggestions.
    """

    def __init__(self, bedrock_client: Any = None) -> None:
        self.bedrock_client = bedrock_client or boto3.client(
            "bedrock-runtime",
            region_name=os.environ.get("AWS_REGION", "us-east-1"),
        )
        self.model_id = os.environ.get(
            "BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0"
        )

    def generate_assessment(
        self,
        transcript: list[dict],
        session_type: str,
        target_role: str,
        skills_focus: list[str],
    ) -> dict:
        """Generate a structured assessment from a session transcript.

        Args:
            transcript: List of transcript entries with role, text, timestamp.
            session_type: Either "interview" or "mission_discussion".
            target_role: The user's target job role.
            skills_focus: List of skill tags from the user's campaign.

        Returns:
            Parsed assessment dict with overallScore, sections, strengths,
            areasForImprovement, and summary.
        """
        try:
            prompt = get_assessment_prompt(session_type, target_role)
            transcript_text = self._format_transcript(transcript)
            prompt_with_transcript = prompt + transcript_text

            response = self.bedrock_client.invoke_model(
                modelId=self.model_id,
                body=json.dumps({
                    "messages": [
                        {
                            "role": "user",
                            "content": [{"text": prompt_with_transcript}],
                        }
                    ],
                    "inferenceConfig": {
                        "maxTokens": 4096,
                        "temperature": 0.3,
                    },
                }),
                contentType="application/json",
                accept="application/json",
            )

            result = json.loads(response["body"].read())
            text = result["output"]["message"]["content"][0]["text"]

            # Extract JSON from the response (handle potential markdown wrapping)
            assessment = self._parse_json_response(text)
            return assessment

        except Exception:
            logger.exception("Assessment generation failed")
            return self._fallback_assessment()

    def _format_transcript(self, transcript: list[dict]) -> str:
        """Format transcript entries into readable text.

        Args:
            transcript: List of transcript entries.

        Returns:
            Formatted transcript string.
        """
        lines = []
        for entry in transcript:
            role = entry.get("role", "unknown").upper()
            text = entry.get("text", "")
            lines.append(f"{role}: {text}")
        return "\n".join(lines)

    def _parse_json_response(self, text: str) -> dict:
        """Parse JSON from the model response, handling markdown wrapping.

        Args:
            text: Raw model output text.

        Returns:
            Parsed assessment dict.

        Raises:
            json.JSONDecodeError: If JSON parsing fails after cleanup.
        """
        cleaned = text.strip()
        # Strip markdown code fences if present
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            # Remove first line (```json or ```) and last line (```)
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines)

        return json.loads(cleaned)

    def _fallback_assessment(self) -> dict:
        """Return a fallback assessment when generation fails.

        Returns:
            Minimal assessment dict with zero scores.
        """
        return {
            "overallScore": 0,
            "sections": [],
            "strengths": [],
            "areasForImprovement": [],
            "summary": "Assessment generation failed",
        }
