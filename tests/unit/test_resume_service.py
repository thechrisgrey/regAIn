"""Unit tests for ResumeService.

Tests data gathering from all 5 DynamoDB tables (moto-backed),
parallel execution, error handling for zero missions and missing
resumes, and presigned URL expiry.

Requirements: 3.1, 3.2, 3.4, 3.5, 7.4, 11.5
"""

import os
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch

import pytest

from backend.handlers.shared.dynamodb import DynamoDBClient
from backend.handlers.resume.service import (
    ResumeGenerationError,
    ResumeService,
)


# ---------------------------------------------------------------------------
# Test data helpers
# ---------------------------------------------------------------------------

TEST_USER_ID = "user-test-001"
TEST_BUCKET = "regain-resume-test"
TEST_MODEL_ID = "us.amazon.nova-lite-v2:0"


def _populate_all_tables(tables: dict) -> None:
    """Insert test data into all 5 moto DynamoDB tables."""
    tables["user_profiles"].put_item(Item={
        "userId": TEST_USER_ID,
        "email": "[email]",
        "name": "Jane Smith",
        "persona": "veteran",
        "onboardingCompleted": True,
        "createdAt": "2025-01-01T00:00:00Z",
        "targetRole": "AI QA Engineer",
        "skills": ["Python", "Testing"],
    })

    tables["campaigns"].put_item(Item={
        "userId": TEST_USER_ID,
        "campaignId": "camp-001",
        "title": "AI QA Transition",
        "phase": "expansion",
        "status": "active",
        "startDate": "2025-01-10T00:00:00Z",
        "targetRole": "AI QA Engineer",
        "skillsFocus": ["Python", "Testing"],
    })

    tables["mission_history"].put_item(Item={
        "userId": TEST_USER_ID,
        "missionId": "mission-001",
        "campaignId": "camp-001",
        "title": "Build a test suite",
        "description": "Create automated tests for an ML pipeline",
        "status": "completed",
        "completedDate": "2025-01-15T00:00:00Z",
    })

    tables["evidence_vault"].put_item(Item={
        "userId": TEST_USER_ID,
        "evidenceId": "ev-001",
        "missionId": "mission-001",
        "skillTag": "Python",
        "reflection": "Built comprehensive test suite covering 3 pipeline stages",
        "createdAt": "2025-01-15T00:00:00Z",
    })

    tables["market_data"].put_item(Item={
        "sector": "role:AI QA Engineer",
        "timestamp": "2025-01-20T00:00:00Z",
        "alignmentPct": 72,
        "topSkills": ["Python", "Testing", "ML"],
        "skillGaps": ["Kubernetes"],
    })


def _make_service(s3_client=None, bedrock_client=None) -> ResumeService:
    """Create a ResumeService backed by moto DynamoDB tables.

    The DynamoDBClient reads table names from env vars set by the
    dynamodb_tables fixture.
    """
    os.environ["RESUME_BUCKET_NAME"] = TEST_BUCKET
    os.environ["BEDROCK_MODEL_ID"] = TEST_MODEL_ID
    db = DynamoDBClient()
    return ResumeService(
        db_client=db,
        s3_client=s3_client or MagicMock(),
        bedrock_client=bedrock_client or MagicMock(),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGatherDataReadsAllFiveTables:
    """Verify _gather_data reads UserProfiles, Campaigns, MissionHistory,
    EvidenceVault, and MarketData (Req 3.1, 3.2)."""

    def test_gather_data_returns_data_from_all_tables(self, dynamodb_tables):
        """Populate all 5 tables and verify ResumeData has data from each."""
        _populate_all_tables(dynamodb_tables)
        service = _make_service()

        data = service._gather_data(TEST_USER_ID)

        assert data.profile.name == "Jane Smith"
        assert data.campaign.title == "AI QA Transition"
        assert len(data.completed_missions) == 1
        assert data.completed_missions[0].title == "Build a test suite"
        assert len(data.evidence_entries) == 1
        assert data.evidence_entries[0].skill_tag == "Python"
        assert data.market_alignment["target_role"] == "AI QA Engineer"
        assert data.market_alignment["alignment_pct"] == 72


class TestParallelExecution:
    """Verify _gather_data uses ThreadPoolExecutor for parallel queries (Req 3.2)."""

    def test_gather_data_uses_thread_pool_executor(self, dynamodb_tables):
        """Patch ThreadPoolExecutor to confirm it is invoked during data gathering."""
        _populate_all_tables(dynamodb_tables)
        service = _make_service()

        with patch(
            "backend.handlers.resume.service.ThreadPoolExecutor",
            wraps=ThreadPoolExecutor,
        ) as mock_executor:
            service._gather_data(TEST_USER_ID)
            mock_executor.assert_called_once_with(max_workers=4)


class TestZeroMissionsError:
    """Verify error when user has zero completed missions (Req 3.5)."""

    def test_zero_completed_missions_raises_error(self, dynamodb_tables):
        """User with profile and campaign but no completed missions gets an error."""
        dynamodb_tables["user_profiles"].put_item(Item={
            "userId": TEST_USER_ID,
            "email": "[email]",
            "name": "Jane Smith",
            "persona": "veteran",
            "onboardingCompleted": True,
            "createdAt": "2025-01-01T00:00:00Z",
            "targetRole": "AI QA Engineer",
            "skills": [],
        })
        dynamodb_tables["campaigns"].put_item(Item={
            "userId": TEST_USER_ID,
            "campaignId": "camp-001",
            "title": "AI QA Transition",
            "phase": "foundation",
            "status": "active",
            "startDate": "2025-01-10T00:00:00Z",
            "targetRole": "AI QA Engineer",
            "skillsFocus": [],
        })
        # No missions inserted — zero completed missions
        service = _make_service()

        with pytest.raises(ResumeGenerationError, match="Complete your first mission"):
            service._gather_data(TEST_USER_ID)


class TestGetResumeNoExistingResume:
    """Verify get_resume returns 404 when user has no resume (Req 7.4)."""

    def test_no_resume_s3_key_raises_404(self, dynamodb_tables):
        """User profile without resumeS3Key triggers a 404 error."""
        dynamodb_tables["user_profiles"].put_item(Item={
            "userId": TEST_USER_ID,
            "email": "[email]",
            "name": "Jane Smith",
            "persona": "veteran",
            "onboardingCompleted": True,
            "createdAt": "2025-01-01T00:00:00Z",
        })
        service = _make_service()

        with pytest.raises(ResumeGenerationError) as exc_info:
            service.get_resume(TEST_USER_ID)

        assert exc_info.value.status_code == 404
        assert "Complete your first mission" in str(exc_info.value)


class TestPresignedUrlExpiry:
    """Verify presigned URL is generated with 1-hour (3600s) expiry (Req 11.5)."""

    def test_get_resume_presigned_url_has_one_hour_expiry(self, dynamodb_tables):
        """Mock S3 client and verify generate_presigned_url called with ExpiresIn=3600."""
        dynamodb_tables["user_profiles"].put_item(Item={
            "userId": TEST_USER_ID,
            "email": "[email]",
            "name": "Jane Smith",
            "persona": "veteran",
            "onboardingCompleted": True,
            "createdAt": "2025-01-01T00:00:00Z",
            "resumeS3Key": f"{TEST_USER_ID}/resume/latest.md",
            "resumeVersion": 3,
            "lastResumeGeneratedAt": "2025-01-20T10:00:00Z",
        })

        mock_s3 = MagicMock()
        mock_body = MagicMock()
        mock_body.read.return_value = b"---\nschema_version: '1.0'\n---\n## Professional Summary\nTest"
        mock_s3.get_object.return_value = {"Body": mock_body}
        mock_s3.generate_presigned_url.return_value = "https://s3.example.com/presigned"

        service = _make_service(s3_client=mock_s3)
        result = service.get_resume(TEST_USER_ID)

        mock_s3.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={
                "Bucket": TEST_BUCKET,
                "Key": f"{TEST_USER_ID}/resume/latest.md",
            },
            ExpiresIn=3600,
        )
        assert result.presigned_url == "https://s3.example.com/presigned"
        assert result.version == 3
        assert result.generated_at == "2025-01-20T10:00:00Z"


class TestGetResumeReturnsContentAndMetadata:
    """Verify get_resume returns correct ResumeResult fields."""

    def test_returns_content_version_and_timestamp(self, dynamodb_tables):
        """Full get_resume flow returns content, version, generated_at, and URL."""
        resume_content = "---\nname: Jane\n---\n## Professional Summary\nGreat candidate."
        dynamodb_tables["user_profiles"].put_item(Item={
            "userId": TEST_USER_ID,
            "email": "[email]",
            "name": "Jane Smith",
            "persona": "veteran",
            "onboardingCompleted": True,
            "createdAt": "2025-01-01T00:00:00Z",
            "resumeS3Key": f"{TEST_USER_ID}/resume/latest.md",
            "resumeVersion": 5,
            "lastResumeGeneratedAt": "2025-01-22T08:00:00Z",
        })

        mock_s3 = MagicMock()
        mock_body = MagicMock()
        mock_body.read.return_value = resume_content.encode("utf-8")
        mock_s3.get_object.return_value = {"Body": mock_body}
        mock_s3.generate_presigned_url.return_value = "https://s3.example.com/url"

        service = _make_service(s3_client=mock_s3)
        result = service.get_resume(TEST_USER_ID)

        assert result.content == resume_content
        assert result.s3_key == f"{TEST_USER_ID}/resume/latest.md"
        assert result.version == 5
        assert result.generated_at == "2025-01-22T08:00:00Z"
        assert result.presigned_url == "https://s3.example.com/url"
