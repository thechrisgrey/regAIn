"""Shared fixtures for REGAIN backend integration tests.

Extends the base unit test conftest with additional tables, S3 buckets,
Cognito user pool, and a fully seeded user via OnboardingService.
"""

import json
import os
import uuid
from typing import Any, Dict, Generator
from unittest.mock import MagicMock, patch

import boto3
import pytest
from moto import mock_aws

from tests.unit.conftest import MOCK_TABLE_NAMES


# Re-export base fixtures so they are available in integration tests.
from tests.unit.conftest import aws_credentials, lambda_context, api_gateway_event  # noqa: F401


# Additional table names for integration tests.
INTEGRATION_TABLE_NAMES = {
    **MOCK_TABLE_NAMES,
    "VOICE_SESSIONS_TABLE": "RegainVoiceSessions",
    "CONVERSATION_THREADS_TABLE": "RegainConversationThreads",
}


def make_event(
    method: str = "GET",
    resource: str = "/",
    body: Dict[str, Any] | None = None,
    user_id: str = "test-user-id-123",
    path_params: Dict[str, str] | None = None,
    query_params: Dict[str, str] | None = None,
) -> Dict[str, Any]:
    """Build a minimal API Gateway proxy event."""
    return {
        "httpMethod": method,
        "path": resource,
        "resource": resource,
        "pathParameters": path_params,
        "queryStringParameters": query_params,
        "headers": {
            "Content-Type": "application/json",
            "Authorization": "Bearer mock-jwt-token",
        },
        "requestContext": {
            "authorizer": {
                "claims": {
                    "sub": user_id,
                    "email": f"{user_id}@test.com",
                },
            },
            "httpMethod": method,
            "resourcePath": resource,
        },
        "body": json.dumps(body) if body else None,
        "isBase64Encoded": False,
    }


def count_items(table_name: str, region: str = "us-east-1") -> int:
    """Scan a DynamoDB table and return total item count."""
    dynamodb = boto3.resource("dynamodb", region_name=region)
    table = dynamodb.Table(table_name)
    result = table.scan(Select="COUNT")
    return result["Count"]


@pytest.fixture()
def integration_tables(aws_credentials: None) -> Generator[Dict[str, Any], None, None]:  # noqa: F811
    """Create all 7 REGAIN DynamoDB tables in moto and set env vars.

    Yields a dict mapping logical names to boto3 Table resources.
    """
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")

        for env_var, table_name in INTEGRATION_TABLE_NAMES.items():
            os.environ[env_var] = table_name

        tables: Dict[str, Any] = {}

        # UserProfiles (PK: userId)
        tables["user_profiles"] = dynamodb.create_table(
            TableName="RegainUserProfiles",
            KeySchema=[{"AttributeName": "userId", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "userId", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # Campaigns (PK: userId, SK: campaignId, GSI: status-index)
        tables["campaigns"] = dynamodb.create_table(
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
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "status-index",
                    "KeySchema": [
                        {"AttributeName": "status", "KeyType": "HASH"},
                        {"AttributeName": "userId", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # MissionHistory (PK: userId, SK: missionId)
        tables["mission_history"] = dynamodb.create_table(
            TableName="RegainMissionHistory",
            KeySchema=[
                {"AttributeName": "userId", "KeyType": "HASH"},
                {"AttributeName": "missionId", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "userId", "AttributeType": "S"},
                {"AttributeName": "missionId", "AttributeType": "S"},
                {"AttributeName": "status", "AttributeType": "S"},
                {"AttributeName": "completedDate", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "status-index",
                    "KeySchema": [
                        {"AttributeName": "status", "KeyType": "HASH"},
                        {"AttributeName": "userId", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
                {
                    "IndexName": "date-index",
                    "KeySchema": [
                        {"AttributeName": "userId", "KeyType": "HASH"},
                        {"AttributeName": "completedDate", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # EvidenceVault (PK: userId, SK: evidenceId)
        tables["evidence_vault"] = dynamodb.create_table(
            TableName="RegainEvidenceVault",
            KeySchema=[
                {"AttributeName": "userId", "KeyType": "HASH"},
                {"AttributeName": "evidenceId", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "userId", "AttributeType": "S"},
                {"AttributeName": "evidenceId", "AttributeType": "S"},
                {"AttributeName": "skillTag", "AttributeType": "S"},
                {"AttributeName": "createdAt", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "skill-index",
                    "KeySchema": [
                        {"AttributeName": "skillTag", "KeyType": "HASH"},
                        {"AttributeName": "createdAt", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # MarketData (PK: sector, SK: timestamp)
        tables["market_data"] = dynamodb.create_table(
            TableName="RegainMarketData",
            KeySchema=[
                {"AttributeName": "sector", "KeyType": "HASH"},
                {"AttributeName": "timestamp", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "sector", "AttributeType": "S"},
                {"AttributeName": "timestamp", "AttributeType": "S"},
                {"AttributeName": "roleTitle", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "role-title-index",
                    "KeySchema": [
                        {"AttributeName": "roleTitle", "KeyType": "HASH"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # VoiceSessions (PK: userId, SK: sessionId, GSI: type-date-index)
        tables["voice_sessions"] = dynamodb.create_table(
            TableName="RegainVoiceSessions",
            KeySchema=[
                {"AttributeName": "userId", "KeyType": "HASH"},
                {"AttributeName": "sessionId", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "userId", "AttributeType": "S"},
                {"AttributeName": "sessionId", "AttributeType": "S"},
                {"AttributeName": "sessionType", "AttributeType": "S"},
                {"AttributeName": "createdAt", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "type-date-index",
                    "KeySchema": [
                        {"AttributeName": "sessionType", "KeyType": "HASH"},
                        {"AttributeName": "createdAt", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # WebSocketConnections (PK: connectionId)
        tables["ws_connections"] = dynamodb.create_table(
            TableName="RegainWebSocketConnections",
            KeySchema=[{"AttributeName": "connectionId", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "connectionId", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # ConversationThreads (PK: userId, SK: threadId)
        tables["conversation_threads"] = dynamodb.create_table(
            TableName="RegainConversationThreads",
            KeySchema=[
                {"AttributeName": "userId", "KeyType": "HASH"},
                {"AttributeName": "threadId", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "userId", "AttributeType": "S"},
                {"AttributeName": "threadId", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        yield tables

        # Clean up env vars.
        for env_var in INTEGRATION_TABLE_NAMES:
            os.environ.pop(env_var, None)


@pytest.fixture()
def mock_s3(aws_credentials: None) -> Generator[Dict[str, str], None, None]:  # noqa: F811
    """Create moto S3 buckets used by cascade deletion and set env vars."""
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        buckets = {
            "VOICE_PRACTICE_BUCKET_NAME": "regain-voice-practice-test",
            "RESUME_BUCKET_NAME": "regain-resume-test",
            "CODE_INTERPRETER_BUCKET_NAME": "regain-code-interpreter-test",
            "THREAD_ARCHIVE_BUCKET": "regain-thread-archive-test",
        }
        for env_var, bucket_name in buckets.items():
            s3.create_bucket(Bucket=bucket_name)
            os.environ[env_var] = bucket_name

        yield buckets

        for env_var in buckets:
            os.environ.pop(env_var, None)


@pytest.fixture()
def mock_cognito(aws_credentials: None) -> Generator[Dict[str, Any], None, None]:  # noqa: F811
    """Create a moto Cognito user pool with a test user."""
    with mock_aws():
        client = boto3.client("cognito-idp", region_name="us-east-1")

        pool = client.create_user_pool(
            PoolName="RegainUserPool",
            AutoVerifiedAttributes=["email"],
            UsernameAttributes=["email"],
        )
        user_pool_id = pool["UserPool"]["Id"]
        os.environ["USER_POOL_ID"] = user_pool_id

        # Create a test user.
        client.admin_create_user(
            UserPoolId=user_pool_id,
            Username="test-user-id-123",
            UserAttributes=[
                {"Name": "email", "Value": "[email protected]"},
                {"Name": "email_verified", "Value": "true"},
            ],
            MessageAction="SUPPRESS",
        )

        yield {
            "user_pool_id": user_pool_id,
            "cognito_client": client,
        }

        os.environ.pop("USER_POOL_ID", None)


@pytest.fixture()
def seeded_user(integration_tables: Dict[str, Any]) -> Dict[str, Any]:
    """Create a fully populated user via OnboardingService.

    Patches generate_daily_mission to avoid calling Bedrock.
    Returns a dict with userId, campaignId, and the raw onboarding result.
    """
    from backend.engine.models import GenerationResult, MissionCandidate, SkillGapReport

    mock_result = GenerationResult(
        primary=MissionCandidate(
            template_id="tmpl-1",
            category="skill_building",
            title="Seeded Mission 1",
            description="First seeded mission",
            rationale="Testing",
            skill_tags=["Python"],
            difficulty=1,
            estimated_minutes=15,
            expected_evidence_type="reflection",
            phase="foundation",
        ),
        alternates=[
            MissionCandidate(
                template_id="tmpl-2",
                category="reflection",
                title="Seeded Mission 2",
                description="Second seeded mission",
                rationale="Testing",
                skill_tags=["Communication"],
                difficulty=1,
                estimated_minutes=15,
                expected_evidence_type="reflection",
                phase="foundation",
            ),
            MissionCandidate(
                template_id="tmpl-3",
                category="networking",
                title="Seeded Mission 3",
                description="Third seeded mission",
                rationale="Testing",
                skill_tags=["Networking"],
                difficulty=1,
                estimated_minutes=15,
                expected_evidence_type="reflection",
                phase="foundation",
            ),
        ],
        skill_gap_report=SkillGapReport(
            skill_scores={"Python": 0.3},
            market_alignment_pct=45.0,
            priority_skills=["Python"],
            evidence_density={"Python": 0},
        ),
    )

    user_id = f"integ-user-{uuid.uuid4().hex[:8]}"

    with patch(
        "backend.handlers.onboarding.service.generate_daily_mission",
        return_value=mock_result,
    ):
        from backend.handlers.onboarding.service import OnboardingService
        from backend.handlers.shared.dynamodb import DynamoDBClient

        service = OnboardingService(db_client=DynamoDBClient())
        result = service.create_profile(
            user_id,
            {
                "email": f"{user_id}@test.com",
                "first_name": "Test",
                "last_name": "User",
                "persona": "career_pivoter",
                "target_role": "Data Engineer",
                "skills": ["Python", "SQL"],
                "current_role": "Analyst",
                "company": "Acme Corp",
                "industry": "Technology",
            },
        )

    return {
        "user_id": user_id,
        "campaign_id": result["campaignId"],
        "result": result,
    }
