"""Integration tests for cascade deletion.

Verifies ProfileService.hard_delete_user_account() correctly deletes across
all DynamoDB tables, S3 buckets, and Cognito.
"""

import uuid
from typing import Any, Dict

import boto3
import pytest
from moto import mock_aws

from backend.handlers.shared.dynamodb import DynamoDBClient
from backend.handlers.shared.models import Campaign, Evidence, Mission, UserProfile
from backend.handlers.profile.service import ProfileService


def _seed_full_user(
    db: DynamoDBClient,
    user_id: str,
    s3_client: Any = None,
    buckets: Dict[str, str] | None = None,
) -> Dict[str, int]:
    """Seed a complete user across all DynamoDB tables and optionally S3.

    Returns a dict with expected item counts per resource.
    """
    now = "2026-01-15T10:00:00+00:00"

    # UserProfiles: 1 item
    profile = UserProfile(
        user_id=user_id,
        email=f"{user_id}@test.com",
        name="Test User",
        persona="veteran",
        onboarding_completed=True,
        created_at=now,
        target_role="Data Engineer",
        skills=["Python", "SQL"],
    )
    db.put_item("user_profiles", profile.to_dynamodb_item())

    # Campaigns: 2 items
    for i in range(2):
        campaign = Campaign(
            user_id=user_id,
            campaign_id=f"campaign-{user_id}-{i}",
            title=f"Campaign {i}",
            phase="foundation",
            status="active" if i == 0 else "paused",
            start_date=now,
            target_role="Data Engineer",
            skills_focus=["Python"],
        )
        db.put_item("campaigns", campaign.to_dynamodb_item())

    # MissionHistory: 5 items
    for i in range(5):
        mission = Mission(
            user_id=user_id,
            mission_id=f"mission-{user_id}-{i}",
            campaign_id=f"campaign-{user_id}-0",
            title=f"Mission {i}",
            description=f"Test mission {i}",
            status="pending",
        )
        db.put_item("mission_history", mission.to_dynamodb_item())

    # EvidenceVault: 3 items
    for i in range(3):
        evidence = Evidence(
            user_id=user_id,
            evidence_id=f"evidence-{user_id}-{i}",
            mission_id=f"mission-{user_id}-{i}",
            skill_tag="Python",
            reflection=f"Reflection {i}",
            created_at=now,
        )
        db.put_item("evidence_vault", evidence.to_dynamodb_item())

    # VoiceSessions: 2 items
    voice_table = db._get_table("voice_sessions")
    for i in range(2):
        voice_table.put_item(
            Item={
                "userId": user_id,
                "sessionId": f"session-{user_id}-{i}",
                "sessionType": "mock_interview",
                "createdAt": now,
                "transcript": f"Test transcript {i}",
            }
        )

    # S3 objects in 3 buckets (if provided).
    if s3_client and buckets:
        for env_var, bucket_name in buckets.items():
            if "VOICE" in env_var:
                prefix = f"{user_id}/voice-practice/"
            elif "RESUME" in env_var:
                prefix = f"{user_id}/resume/"
            else:
                prefix = f"{user_id}/"
            s3_client.put_object(
                Bucket=bucket_name,
                Key=f"{prefix}file1.json",
                Body=b'{"test": true}',
            )
            s3_client.put_object(
                Bucket=bucket_name,
                Key=f"{prefix}file2.json",
                Body=b'{"test": true}',
            )

    return {
        "user_profiles": 1,
        "campaigns": 2,
        "mission_history": 5,
        "evidence_vault": 3,
        "voice_sessions": 2,
        "s3_objects_per_bucket": 2,
    }


def _make_profile_service(db: DynamoDBClient) -> ProfileService:
    """Build a ProfileService with S3/Cognito env vars cleared.

    Prevents stale env vars from other tests triggering real S3/Cognito calls.
    """
    import os
    for var in [
        "VOICE_PRACTICE_BUCKET_NAME", "RESUME_BUCKET_NAME",
        "CODE_INTERPRETER_BUCKET_NAME", "USER_POOL_ID", "AGENTCORE_MEMORY_ID",
    ]:
        os.environ.pop(var, None)
    return ProfileService(db_client=db, cognito_client=None, s3_client=None)


class TestDynamoDBCascadeDeletion:
    """Tests for DynamoDB cascade deletion across all tables."""

    def test_deletes_all_user_profiles(self, integration_tables):
        """Profile row is removed after deletion."""
        db = DynamoDBClient()
        user_id = f"del-profile-{uuid.uuid4().hex[:8]}"
        _seed_full_user(db, user_id)

        service = _make_profile_service(db)
        result = service.hard_delete_user_account(user_id)

        assert result["deleted"]["user_profiles"] == 1
        assert db.get_item("user_profiles", {"userId": user_id}) is None

    def test_deletes_all_campaigns(self, integration_tables):
        """Both campaign items are removed (composite key deletion)."""
        db = DynamoDBClient()
        user_id = f"del-camp-{uuid.uuid4().hex[:8]}"
        _seed_full_user(db, user_id)

        service = _make_profile_service(db)
        result = service.hard_delete_user_account(user_id)

        assert result["deleted"]["campaigns"] == 2
        from boto3.dynamodb.conditions import Key
        remaining = db.query_all("campaigns", Key("userId").eq(user_id))
        assert len(remaining) == 0

    def test_deletes_all_missions(self, integration_tables):
        """All 5 mission items are removed (composite key deletion)."""
        db = DynamoDBClient()
        user_id = f"del-miss-{uuid.uuid4().hex[:8]}"
        _seed_full_user(db, user_id)

        service = _make_profile_service(db)
        result = service.hard_delete_user_account(user_id)

        assert result["deleted"]["mission_history"] == 5
        from boto3.dynamodb.conditions import Key
        remaining = db.query_all("mission_history", Key("userId").eq(user_id))
        assert len(remaining) == 0

    def test_deletes_all_evidence(self, integration_tables):
        """All 3 evidence items are removed (composite key deletion)."""
        db = DynamoDBClient()
        user_id = f"del-evid-{uuid.uuid4().hex[:8]}"
        _seed_full_user(db, user_id)

        service = _make_profile_service(db)
        result = service.hard_delete_user_account(user_id)

        assert result["deleted"]["evidence_vault"] == 3
        from boto3.dynamodb.conditions import Key
        remaining = db.query_all("evidence_vault", Key("userId").eq(user_id))
        assert len(remaining) == 0

    def test_deletes_all_voice_sessions(self, integration_tables):
        """Both voice session items are removed (composite key deletion)."""
        db = DynamoDBClient()
        user_id = f"del-voice-{uuid.uuid4().hex[:8]}"
        _seed_full_user(db, user_id)

        service = _make_profile_service(db)
        result = service.hard_delete_user_account(user_id)

        assert result["deleted"]["voice_sessions"] == 2
        from boto3.dynamodb.conditions import Key
        remaining = db.query_all("voice_sessions", Key("userId").eq(user_id))
        assert len(remaining) == 0

    def test_other_user_data_untouched(self, integration_tables):
        """Deleting user-A does not affect user-B's data."""
        db = DynamoDBClient()
        user_a = f"del-a-{uuid.uuid4().hex[:8]}"
        user_b = f"del-b-{uuid.uuid4().hex[:8]}"
        _seed_full_user(db, user_a)
        _seed_full_user(db, user_b)

        service = _make_profile_service(db)
        service.hard_delete_user_account(user_a)

        # user-B data should remain intact.
        assert db.get_item("user_profiles", {"userId": user_b}) is not None
        from boto3.dynamodb.conditions import Key
        assert len(db.query_all("campaigns", Key("userId").eq(user_b))) == 2
        assert len(db.query_all("mission_history", Key("userId").eq(user_b))) == 5
        assert len(db.query_all("evidence_vault", Key("userId").eq(user_b))) == 3
        assert len(db.query_all("voice_sessions", Key("userId").eq(user_b))) == 2

    def test_full_cascade_counts(self, integration_tables):
        """Verify the complete result dict matches expected counts."""
        db = DynamoDBClient()
        user_id = f"del-full-{uuid.uuid4().hex[:8]}"
        _seed_full_user(db, user_id)

        service = _make_profile_service(db)
        result = service.hard_delete_user_account(user_id)

        assert result["deleted"]["user_profiles"] == 1
        assert result["deleted"]["campaigns"] == 2
        assert result["deleted"]["mission_history"] == 5
        assert result["deleted"]["evidence_vault"] == 3
        assert result["deleted"]["voice_sessions"] == 2
        # S3 and Cognito not configured -> 0
        assert result["deleted"]["voice_practice_s3"] == 0
        assert result["deleted"]["resume_s3"] == 0
        assert result["deleted"]["code_interpreter_s3"] == 0
        assert result["deleted"]["cognito"] == 0


class TestS3CascadeDeletion:
    """Tests for S3 object cleanup during cascade deletion."""

    def test_deletes_s3_objects_in_all_buckets(self, aws_credentials):
        """S3 objects are deleted from all 3 buckets."""
        import os

        with mock_aws():
            # Standalone mock context with both DynamoDB and S3.
            dynamodb = boto3.resource("dynamodb", region_name="us-east-1")

            from tests.integration.conftest import INTEGRATION_TABLE_NAMES
            for env_var, table_name in INTEGRATION_TABLE_NAMES.items():
                os.environ[env_var] = table_name

            dynamodb.create_table(
                TableName="RegainUserProfiles",
                KeySchema=[{"AttributeName": "userId", "KeyType": "HASH"}],
                AttributeDefinitions=[{"AttributeName": "userId", "AttributeType": "S"}],
                BillingMode="PAY_PER_REQUEST",
            )
            dynamodb.create_table(
                TableName="RegainCampaigns",
                KeySchema=[
                    {"AttributeName": "userId", "KeyType": "HASH"},
                    {"AttributeName": "campaignId", "KeyType": "RANGE"},
                ],
                AttributeDefinitions=[
                    {"AttributeName": "userId", "AttributeType": "S"},
                    {"AttributeName": "campaignId", "AttributeType": "S"},
                    {"AttributeName": "status", "AttributeType": "S"},
                ],
                GlobalSecondaryIndexes=[{
                    "IndexName": "status-index",
                    "KeySchema": [
                        {"AttributeName": "status", "KeyType": "HASH"},
                        {"AttributeName": "userId", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                }],
                BillingMode="PAY_PER_REQUEST",
            )
            dynamodb.create_table(
                TableName="RegainMissionHistory",
                KeySchema=[
                    {"AttributeName": "userId", "KeyType": "HASH"},
                    {"AttributeName": "missionId", "KeyType": "RANGE"},
                ],
                AttributeDefinitions=[
                    {"AttributeName": "userId", "AttributeType": "S"},
                    {"AttributeName": "missionId", "AttributeType": "S"},
                ],
                BillingMode="PAY_PER_REQUEST",
            )
            dynamodb.create_table(
                TableName="RegainEvidenceVault",
                KeySchema=[
                    {"AttributeName": "userId", "KeyType": "HASH"},
                    {"AttributeName": "evidenceId", "KeyType": "RANGE"},
                ],
                AttributeDefinitions=[
                    {"AttributeName": "userId", "AttributeType": "S"},
                    {"AttributeName": "evidenceId", "AttributeType": "S"},
                ],
                BillingMode="PAY_PER_REQUEST",
            )
            dynamodb.create_table(
                TableName="RegainVoiceSessions",
                KeySchema=[
                    {"AttributeName": "userId", "KeyType": "HASH"},
                    {"AttributeName": "sessionId", "KeyType": "RANGE"},
                ],
                AttributeDefinitions=[
                    {"AttributeName": "userId", "AttributeType": "S"},
                    {"AttributeName": "sessionId", "AttributeType": "S"},
                ],
                BillingMode="PAY_PER_REQUEST",
            )

            s3_client = boto3.client("s3", region_name="us-east-1")
            buckets = {
                "VOICE_PRACTICE_BUCKET_NAME": "regain-voice-test",
                "RESUME_BUCKET_NAME": "regain-resume-test",
                "CODE_INTERPRETER_BUCKET_NAME": "regain-code-test",
            }
            for env_var, name in buckets.items():
                s3_client.create_bucket(Bucket=name)
                os.environ[env_var] = name

            db = DynamoDBClient()
            user_id = f"s3-del-{uuid.uuid4().hex[:8]}"
            _seed_full_user(db, user_id, s3_client=s3_client, buckets=buckets)

            service = ProfileService(
                db_client=db,
                cognito_client=None,
                s3_client=s3_client,
            )
            result = service.hard_delete_user_account(user_id)

            assert result["deleted"]["voice_practice_s3"] == 2
            assert result["deleted"]["resume_s3"] == 2
            assert result["deleted"]["code_interpreter_s3"] == 2

            # Verify S3 is empty for this user.
            for bucket_name in buckets.values():
                resp = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=f"{user_id}/")
                assert resp.get("KeyCount", 0) == 0

            # Clean up env vars.
            for env_var in {**INTEGRATION_TABLE_NAMES, **buckets}:
                os.environ.pop(env_var, None)

    def test_handles_missing_s3_env_vars(self, integration_tables):
        """Missing bucket env vars result in 0 deletions, not errors."""
        db = DynamoDBClient()
        user_id = f"no-s3-{uuid.uuid4().hex[:8]}"
        _seed_full_user(db, user_id)

        service = _make_profile_service(db)
        result = service.hard_delete_user_account(user_id)

        assert result["deleted"]["voice_practice_s3"] == 0
        assert result["deleted"]["resume_s3"] == 0
        assert result["deleted"]["code_interpreter_s3"] == 0


class TestCognitoCascadeDeletion:
    """Tests for Cognito user deletion during cascade deletion."""

    def test_deletes_cognito_user(self, aws_credentials):
        """Cognito user is deleted when USER_POOL_ID is set."""
        import os

        with mock_aws():
            # Standalone mock context with both DynamoDB and Cognito.
            cognito = boto3.client("cognito-idp", region_name="us-east-1")
            pool = cognito.create_user_pool(PoolName="TestPool")
            pool_id = pool["UserPool"]["Id"]
            os.environ["USER_POOL_ID"] = pool_id

            user_id = f"cog-del-{uuid.uuid4().hex[:8]}"
            cognito.admin_create_user(
                UserPoolId=pool_id,
                Username=user_id,
                MessageAction="SUPPRESS",
            )

            dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
            from tests.integration.conftest import INTEGRATION_TABLE_NAMES
            for env_var, table_name in INTEGRATION_TABLE_NAMES.items():
                os.environ[env_var] = table_name

            dynamodb.create_table(
                TableName="RegainUserProfiles",
                KeySchema=[{"AttributeName": "userId", "KeyType": "HASH"}],
                AttributeDefinitions=[{"AttributeName": "userId", "AttributeType": "S"}],
                BillingMode="PAY_PER_REQUEST",
            )
            dynamodb.create_table(
                TableName="RegainCampaigns",
                KeySchema=[
                    {"AttributeName": "userId", "KeyType": "HASH"},
                    {"AttributeName": "campaignId", "KeyType": "RANGE"},
                ],
                AttributeDefinitions=[
                    {"AttributeName": "userId", "AttributeType": "S"},
                    {"AttributeName": "campaignId", "AttributeType": "S"},
                    {"AttributeName": "status", "AttributeType": "S"},
                ],
                GlobalSecondaryIndexes=[{
                    "IndexName": "status-index",
                    "KeySchema": [
                        {"AttributeName": "status", "KeyType": "HASH"},
                        {"AttributeName": "userId", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                }],
                BillingMode="PAY_PER_REQUEST",
            )
            dynamodb.create_table(
                TableName="RegainMissionHistory",
                KeySchema=[
                    {"AttributeName": "userId", "KeyType": "HASH"},
                    {"AttributeName": "missionId", "KeyType": "RANGE"},
                ],
                AttributeDefinitions=[
                    {"AttributeName": "userId", "AttributeType": "S"},
                    {"AttributeName": "missionId", "AttributeType": "S"},
                ],
                BillingMode="PAY_PER_REQUEST",
            )
            dynamodb.create_table(
                TableName="RegainEvidenceVault",
                KeySchema=[
                    {"AttributeName": "userId", "KeyType": "HASH"},
                    {"AttributeName": "evidenceId", "KeyType": "RANGE"},
                ],
                AttributeDefinitions=[
                    {"AttributeName": "userId", "AttributeType": "S"},
                    {"AttributeName": "evidenceId", "AttributeType": "S"},
                ],
                BillingMode="PAY_PER_REQUEST",
            )
            dynamodb.create_table(
                TableName="RegainVoiceSessions",
                KeySchema=[
                    {"AttributeName": "userId", "KeyType": "HASH"},
                    {"AttributeName": "sessionId", "KeyType": "RANGE"},
                ],
                AttributeDefinitions=[
                    {"AttributeName": "userId", "AttributeType": "S"},
                    {"AttributeName": "sessionId", "AttributeType": "S"},
                ],
                BillingMode="PAY_PER_REQUEST",
            )

            db = DynamoDBClient()
            _seed_full_user(db, user_id)

            service = ProfileService(
                db_client=db,
                cognito_client=cognito,
                s3_client=None,
            )
            result = service.hard_delete_user_account(user_id)

            assert result["deleted"]["cognito"] == 1

            # Verify user no longer exists.
            with pytest.raises(cognito.exceptions.UserNotFoundException):
                cognito.admin_get_user(
                    UserPoolId=pool_id,
                    Username=user_id,
                )

            # Clean up.
            for env_var in INTEGRATION_TABLE_NAMES:
                os.environ.pop(env_var, None)
            os.environ.pop("USER_POOL_ID", None)

    def test_handles_missing_user_pool_id(self, integration_tables):
        """Missing USER_POOL_ID results in 0 Cognito deletions."""
        db = DynamoDBClient()
        user_id = f"no-cog-{uuid.uuid4().hex[:8]}"
        _seed_full_user(db, user_id)

        service = _make_profile_service(db)
        result = service.hard_delete_user_account(user_id)

        assert result["deleted"]["cognito"] == 0


class TestSoftDeleteAndRecoverCycle:
    """Tests for soft delete -> recover flow via ProfileService."""

    def test_soft_delete_sets_deletion_markers(self, integration_tables):
        """soft_delete_user_account sets deletedAt and deletionScheduledFor."""
        db = DynamoDBClient()
        user_id = f"soft-del-{uuid.uuid4().hex[:8]}"
        _seed_full_user(db, user_id)

        service = _make_profile_service(db)
        result = service.soft_delete_user_account(user_id)

        assert result["status"] == "scheduled"
        assert "deletionDate" in result

        profile = db.get_item("user_profiles", {"userId": user_id})
        assert profile is not None
        assert "deletedAt" in profile
        assert "deletionScheduledFor" in profile
        assert profile["firstName"] == "[deleted]"
        assert profile["lastName"] == "[deleted]"

    def test_recover_clears_deletion_markers(self, integration_tables):
        """recover_user_account removes deletedAt and deletionScheduledFor."""
        db = DynamoDBClient()
        user_id = f"recover-{uuid.uuid4().hex[:8]}"
        _seed_full_user(db, user_id)

        service = _make_profile_service(db)
        service.soft_delete_user_account(user_id)

        result = service.recover_user_account(user_id)
        assert result["status"] == "recovered"

        profile = db.get_item("user_profiles", {"userId": user_id})
        assert profile is not None
        assert "deletedAt" not in profile
        assert "deletionScheduledFor" not in profile

    def test_recover_non_deleted_account_returns_not_deleted(self, integration_tables):
        """recover on an active account returns not_deleted status."""
        db = DynamoDBClient()
        user_id = f"no-del-{uuid.uuid4().hex[:8]}"
        _seed_full_user(db, user_id)

        service = _make_profile_service(db)
        result = service.recover_user_account(user_id)

        assert result["status"] == "not_deleted"

    def test_data_preserved_after_soft_delete(self, integration_tables):
        """Soft delete does NOT remove campaigns, missions, or evidence."""
        from boto3.dynamodb.conditions import Key

        db = DynamoDBClient()
        user_id = f"soft-keep-{uuid.uuid4().hex[:8]}"
        _seed_full_user(db, user_id)

        service = _make_profile_service(db)
        service.soft_delete_user_account(user_id)

        assert len(db.query_all("campaigns", Key("userId").eq(user_id))) == 2
        assert len(db.query_all("mission_history", Key("userId").eq(user_id))) == 5
        assert len(db.query_all("evidence_vault", Key("userId").eq(user_id))) == 3
        assert len(db.query_all("voice_sessions", Key("userId").eq(user_id))) == 2
