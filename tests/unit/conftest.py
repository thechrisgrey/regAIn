"""Shared test fixtures for REGAIN backend unit tests.

Provides moto-based mocks for DynamoDB tables, Cognito User Pool,
and Lambda event/context objects used across all test modules.
"""

import os
from typing import Any, Dict, Generator
from unittest.mock import MagicMock

import boto3
import pytest
from moto import mock_aws


# ---------------------------------------------------------------------------
# DynamoDB table names used in fixtures (match CDK DataStack definitions)
# ---------------------------------------------------------------------------
MOCK_TABLE_NAMES = {
    "USER_PROFILES_TABLE": "RegainUserProfiles",
    "CAMPAIGNS_TABLE": "RegainCampaigns",
    "MISSION_HISTORY_TABLE": "RegainMissionHistory",
    "EVIDENCE_VAULT_TABLE": "RegainEvidenceVault",
    "MARKET_DATA_TABLE": "RegainMarketData",
}


# ---------------------------------------------------------------------------
# DynamoDB fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def aws_credentials() -> None:
    """Set dummy AWS credentials for moto."""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"


@pytest.fixture()
def dynamodb_tables(aws_credentials: None) -> Generator[Dict[str, Any], None, None]:
    """Create all REGAIN DynamoDB tables in moto and set env vars.

    Yields a dict mapping logical names to boto3 Table resources.
    Tables match the schema defined in infra/stacks/data_stack.py.
    """
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")

        # Set environment variables so DynamoDBClient can resolve tables
        for env_var, table_name in MOCK_TABLE_NAMES.items():
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

        # MissionHistory (PK: userId, SK: missionId, GSIs: status-index, date-index)
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

        # EvidenceVault (PK: userId, SK: evidenceId, GSI: skill-index)
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

        # MarketData (PK: sector, SK: timestamp, GSI: role-title-index)
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

        yield tables

        # Clean up env vars
        for env_var in MOCK_TABLE_NAMES:
            os.environ.pop(env_var, None)


# ---------------------------------------------------------------------------
# Cognito fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def cognito_user_pool(aws_credentials: None) -> Generator[Dict[str, str], None, None]:
    """Create a mocked Cognito User Pool.

    Yields a dict with 'user_pool_id' and 'client_id'.
    """
    with mock_aws():
        client = boto3.client("cognito-idp", region_name="us-east-1")

        pool = client.create_user_pool(
            PoolName="RegainUserPool",
            AutoVerifiedAttributes=["email"],
            UsernameAttributes=["email"],
        )
        user_pool_id = pool["UserPool"]["Id"]

        pool_client = client.create_user_pool_client(
            UserPoolId=user_pool_id,
            ClientName="RegainWebClient",
            ExplicitAuthFlows=["ALLOW_USER_SRP_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"],
            GenerateSecret=False,
        )
        client_id = pool_client["UserPoolClient"]["ClientId"]

        yield {
            "user_pool_id": user_pool_id,
            "client_id": client_id,
            "cognito_client": client,
        }


# ---------------------------------------------------------------------------
# Lambda event / context fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def api_gateway_event() -> Dict[str, Any]:
    """Return a minimal API Gateway proxy event.

    Callers can override fields as needed for specific tests.
    """
    return {
        "httpMethod": "GET",
        "path": "/",
        "resource": "/",
        "pathParameters": None,
        "queryStringParameters": None,
        "headers": {
            "Content-Type": "application/json",
            "Authorization": "Bearer mock-jwt-token",
        },
        "requestContext": {
            "authorizer": {
                "claims": {
                    "sub": "test-user-id-123",
                    "email": "[email]",
                },
            },
            "httpMethod": "GET",
            "resourcePath": "/",
        },
        "body": None,
        "isBase64Encoded": False,
    }


@pytest.fixture()
def lambda_context() -> MagicMock:
    """Return a mock Lambda context object."""
    context = MagicMock()
    context.function_name = "test-function"
    context.memory_limit_in_mb = 128
    context.invoked_function_arn = (
        "arn:aws:lambda:us-east-1:563170906428:function:test-function"
    )
    context.aws_request_id = "test-request-id-abc123"
    context.get_remaining_time_in_millis.return_value = 30000
    return context
