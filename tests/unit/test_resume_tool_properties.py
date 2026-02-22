"""Property-based tests for coaching agent resume tool response shapes.

Uses Hypothesis to validate that generate_resume and get_resume tools
always return responses containing the required fields: content,
generatedAt, version, and downloadUrl.

Feature: agent-friendly-resume, Property 12: API and tool responses contain required fields
Validates: Requirements 7.3, 8.1, 8.3
"""

import io
import json
import os
import sys
import types
from unittest.mock import MagicMock, patch

from hypothesis import given, settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Stub the 'strands' package so tools.py can be imported without the SDK.
# ---------------------------------------------------------------------------

_strands_stub = types.ModuleType("strands")
_strands_stub.tool = lambda fn: fn  # @tool is a no-op decorator in tests
if "strands" not in sys.modules:
    sys.modules["strands"] = _strands_stub

# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

_REQUIRED_KEYS = {"content", "generatedAt", "version", "downloadUrl"}

iso_timestamps = st.from_regex(
    r"2025-0[1-9]-[012][1-9]T[01][0-9]:[0-5][0-9]:[0-5][0-9]Z",
    fullmatch=True,
)

resume_content_st = st.text(
    min_size=10,
    max_size=200,
    alphabet=st.characters(whitelist_categories=("L", "N", "Zs")),
).filter(lambda s: s.strip())

versions_st = st.integers(min_value=1, max_value=500)

presigned_urls = st.from_regex(
    r"https://s3\.amazonaws\.com/bucket/[a-z0-9]{5,10}/resume/latest\.md",
    fullmatch=True,
)


# ===========================================================================
# Property 12 — generate_resume tool response shape
# Feature: agent-friendly-resume, Property 12: API and tool responses contain required fields
# Validates: Requirements 7.3, 8.1, 8.3
# ===========================================================================


class TestProperty12GenerateResumeResponseShape:
    """generate_resume tool returns all required fields on success."""

    @given(
        content=resume_content_st,
        generated_at=iso_timestamps,
        version=versions_st,
        download_url=presigned_urls,
    )
    @settings(max_examples=100)
    def test_generate_resume_contains_required_fields(
        self,
        content: str,
        generated_at: str,
        version: int,
        download_url: str,
    ) -> None:
        """**Validates: Requirements 7.3, 8.1, 8.3**"""
        lambda_body = json.dumps({
            "content": content,
            "generatedAt": generated_at,
            "version": version,
            "downloadUrl": download_url,
        })
        lambda_result = json.dumps({"statusCode": 200, "body": lambda_body})

        mock_lambda_client = MagicMock()
        mock_lambda_client.invoke.return_value = {
            "Payload": io.BytesIO(lambda_result.encode("utf-8")),
        }

        os.environ["RESUME_LAMBDA_ARN"] = "arn:aws:lambda:us-east-1:123:function:resume"
        try:
            with patch("backend.agents.coaching.tools.boto3") as mock_boto3:
                mock_boto3.client.return_value = mock_lambda_client

                from backend.agents.coaching.tools import generate_resume

                result = generate_resume(user_id="test-user")
        finally:
            os.environ.pop("RESUME_LAMBDA_ARN", None)

        assert "error" not in result, f"Unexpected error: {result}"
        assert _REQUIRED_KEYS.issubset(result.keys()), (
            f"Missing keys: {_REQUIRED_KEYS - result.keys()}"
        )
        assert result["content"] == content
        assert result["generatedAt"] == generated_at
        assert result["version"] == version
        assert result["downloadUrl"] == download_url


# ===========================================================================
# Property 12 — get_resume tool response shape
# Feature: agent-friendly-resume, Property 12: API and tool responses contain required fields
# Validates: Requirements 7.3, 8.1, 8.3
# ===========================================================================


class TestProperty12GetResumeResponseShape:
    """get_resume tool returns all required fields when resume exists."""

    @given(
        content=resume_content_st,
        generated_at=iso_timestamps,
        version=versions_st,
        download_url=presigned_urls,
    )
    @settings(max_examples=100)
    def test_get_resume_contains_required_fields(
        self,
        content: str,
        generated_at: str,
        version: int,
        download_url: str,
    ) -> None:
        """**Validates: Requirements 7.3, 8.1, 8.3**"""
        s3_key = "test-user/resume/latest.md"

        mock_s3_client = MagicMock()
        mock_s3_client.get_object.return_value = {
            "Body": io.BytesIO(content.encode("utf-8")),
        }
        mock_s3_client.generate_presigned_url.return_value = download_url

        mock_db = MagicMock()
        mock_db.get_item.return_value = {
            "userId": "test-user",
            "resumeS3Key": s3_key,
            "lastResumeGeneratedAt": generated_at,
            "resumeVersion": version,
        }

        os.environ["RESUME_BUCKET_NAME"] = "test-bucket"
        try:
            with (
                patch("backend.agents.coaching.tools.db", mock_db),
                patch("backend.agents.coaching.tools.boto3") as mock_boto3,
            ):
                mock_boto3.client.return_value = mock_s3_client

                from backend.agents.coaching.tools import get_resume

                result = get_resume(user_id="test-user")
        finally:
            os.environ.pop("RESUME_BUCKET_NAME", None)

        assert "error" not in result, f"Unexpected error: {result}"
        assert "message" not in result or "No resume" not in result.get("message", ""), (
            f"Unexpected no-resume message: {result}"
        )
        assert _REQUIRED_KEYS.issubset(result.keys()), (
            f"Missing keys: {_REQUIRED_KEYS - result.keys()}"
        )
        assert result["content"] == content
        assert result["generatedAt"] == generated_at
        assert result["version"] == version
        assert result["downloadUrl"] == download_url
