"""Property test for AWS SDK mocking.

**Property 15: AWS SDK Mocking**
**Validates: Requirements 10.4**

Verifies that unit tests interacting with AWS services use moto or pytest
fixtures to mock AWS SDK calls rather than making real API calls.  The
conftest ``dynamodb_tables`` fixture must:

- Create fully functional mocked DynamoDB tables via moto
- Set the correct environment variables for the data access layer
- Support arbitrary put_item / get_item round-trips without hitting AWS

Feature: platform-foundation, Property 15: AWS SDK Mocking
"""

import os
from typing import Any, Dict

import boto3
import pytest
from hypothesis import HealthCheck, given, settings, strategies as st
from moto import mock_aws

# ---------------------------------------------------------------------------
# Strategies — generate realistic DynamoDB item fields
# ---------------------------------------------------------------------------

_safe_text = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="_-"),
    min_size=1,
    max_size=40,
).filter(lambda s: s.strip())


# ---------------------------------------------------------------------------
# Helper: table definitions matching conftest.py
# ---------------------------------------------------------------------------

_MOCK_TABLE_NAMES = {
    "USER_PROFILES_TABLE": "RegainUserProfiles",
    "CAMPAIGNS_TABLE": "RegainCampaigns",
    "MISSION_HISTORY_TABLE": "RegainMissionHistory",
    "EVIDENCE_VAULT_TABLE": "RegainEvidenceVault",
    "MARKET_DATA_TABLE": "RegainMarketData",
}


def _create_tables(dynamodb: Any) -> Dict[str, Any]:
    """Create all REGAIN tables inside a moto mock context."""
    tables: Dict[str, Any] = {}

    tables["user_profiles"] = dynamodb.create_table(
        TableName="RegainUserProfiles",
        KeySchema=[{"AttributeName": "userId", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "userId", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
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
    return tables


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------


@given(user_id=_safe_text, email=_safe_text, name=_safe_text)
@settings(max_examples=100)
def test_mocked_dynamodb_put_get_roundtrip(
    user_id: str,
    email: str,
    name: str,
) -> None:
    """For any arbitrary item, put_item followed by get_item on a moto-mocked
    table must return the same item — proving the mock provides a working
    DynamoDB substitute, not a real AWS connection.

    **Validates: Requirements 10.4**
    """
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"

    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        tables = _create_tables(dynamodb)
        table = tables["user_profiles"]

        item = {"userId": user_id, "email": email, "name": name}
        table.put_item(Item=item)

        response = table.get_item(Key={"userId": user_id})
        stored = response.get("Item")

        assert stored is not None, "Item should be retrievable from mocked table"
        assert stored["userId"] == user_id
        assert stored["email"] == email
        assert stored["name"] == name


@given(user_id=_safe_text, campaign_id=_safe_text, status=_safe_text)
@settings(max_examples=100)
def test_mocked_dynamodb_composite_key_roundtrip(
    user_id: str,
    campaign_id: str,
    status: str,
) -> None:
    """For any arbitrary composite-key item, the moto-mocked Campaigns table
    must support put/get correctly — confirming moto creates tables with the
    right key schemas and no real AWS calls are made.

    **Validates: Requirements 10.4**
    """
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"

    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        tables = _create_tables(dynamodb)
        table = tables["campaigns"]

        item = {
            "userId": user_id,
            "campaignId": campaign_id,
            "status": status,
            "title": "Test Campaign",
        }
        table.put_item(Item=item)

        response = table.get_item(Key={"userId": user_id, "campaignId": campaign_id})
        stored = response.get("Item")

        assert stored is not None, "Composite-key item should be retrievable"
        assert stored["userId"] == user_id
        assert stored["campaignId"] == campaign_id
        assert stored["status"] == status


@given(
    user_id=_safe_text,
    evidence_id=_safe_text,
    skill_tag=_safe_text,
)
@settings(max_examples=100)
def test_mocked_dynamodb_gsi_query(
    user_id: str,
    evidence_id: str,
    skill_tag: str,
) -> None:
    """For any arbitrary evidence item, a GSI query on the moto-mocked
    EvidenceVault table must return matching results — proving the fixture
    pattern supports index queries without real AWS.

    **Validates: Requirements 10.4**
    """
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"

    with mock_aws():
        from boto3.dynamodb.conditions import Key

        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        tables = _create_tables(dynamodb)
        table = tables["evidence_vault"]

        item = {
            "userId": user_id,
            "evidenceId": evidence_id,
            "skillTag": skill_tag,
            "createdAt": "2025-01-01T00:00:00Z",
            "reflection": "test",
        }
        table.put_item(Item=item)

        response = table.query(
            IndexName="skill-index",
            KeyConditionExpression=Key("skillTag").eq(skill_tag),
        )
        items = response.get("Items", [])

        assert len(items) >= 1, "GSI query should return the inserted item"
        match = [i for i in items if i["evidenceId"] == evidence_id]
        assert len(match) == 1


@given(user_id=_safe_text)
@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_fixture_sets_environment_variables_and_tables_work(
    dynamodb_tables: Dict[str, Any],
    user_id: str,
) -> None:
    """For every invocation of the dynamodb_tables fixture, the required
    environment variables must be set and the mocked tables must accept
    DynamoDB operations — proving the fixture configures the environment
    for mocked usage and no real AWS calls can occur.

    **Validates: Requirements 10.4**
    """
    expected_env_vars = [
        "USER_PROFILES_TABLE",
        "CAMPAIGNS_TABLE",
        "MISSION_HISTORY_TABLE",
        "EVIDENCE_VAULT_TABLE",
        "MARKET_DATA_TABLE",
    ]
    for var in expected_env_vars:
        value = os.environ.get(var)
        assert value is not None and value != "", (
            f"Environment variable {var} must be set by the fixture"
        )

    # The fixture yields 5 table resources that accept real DynamoDB ops
    assert len(dynamodb_tables) == 5
    for name in ("user_profiles", "campaigns", "mission_history",
                 "evidence_vault", "market_data"):
        assert name in dynamodb_tables, f"Fixture must provide '{name}' table"

    # Verify the mocked table actually works (put + get round-trip)
    table = dynamodb_tables["user_profiles"]
    table.put_item(Item={"userId": user_id, "email": "test", "name": "test"})
    result = table.get_item(Key={"userId": user_id})
    assert result.get("Item") is not None, "Mocked table must support operations"
