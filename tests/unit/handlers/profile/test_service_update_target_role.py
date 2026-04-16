"""Unit tests for ProfileService.update_target_role."""

from __future__ import annotations

import os
import boto3
import pytest
from moto import mock_aws

from backend.handlers.profile.service import ProfileService
from backend.handlers.shared.dynamodb import DynamoDBClient


@pytest.fixture(autouse=True)
def _aws_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("USER_PROFILES_TABLE", "RegainUserProfiles")
    monkeypatch.setenv("CAMPAIGNS_TABLE", "RegainCampaigns")


@pytest.fixture
def _tables() -> None:
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        ddb.create_table(
            TableName="RegainUserProfiles",
            KeySchema=[{"AttributeName": "userId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "userId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        ddb.create_table(
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
        yield


def test_update_target_role_writes_both_tables_atomically(_tables) -> None:
    db = DynamoDBClient()
    db._get_table("user_profiles").put_item(
        Item={"userId": "user-1", "targetRole": "Old Role"},
    )
    db._get_table("campaigns").put_item(
        Item={
            "userId": "user-1",
            "campaignId": "camp-1",
            "status": "active",
            "targetRole": "Old Role",
            "skillsFocus": ["Python"],
        },
    )

    service = ProfileService(db_client=db)
    result = service.update_target_role("user-1", "Senior Cloud Architect")

    assert result == {"targetRole": "Senior Cloud Architect"}
    profile = db.get_item("user_profiles", {"userId": "user-1"})
    campaign = db.get_item("campaigns", {"userId": "user-1", "campaignId": "camp-1"})
    assert profile["targetRole"] == "Senior Cloud Architect"
    assert campaign["targetRole"] == "Senior Cloud Architect"


def test_update_target_role_when_no_active_campaign(_tables) -> None:
    db = DynamoDBClient()
    db._get_table("user_profiles").put_item(Item={"userId": "user-2"})

    service = ProfileService(db_client=db)
    result = service.update_target_role("user-2", "Data Engineer")

    assert result == {"targetRole": "Data Engineer"}
    profile = db.get_item("user_profiles", {"userId": "user-2"})
    assert profile["targetRole"] == "Data Engineer"


@pytest.mark.parametrize("bad_value", ["", "   ", "x" * 201])
def test_update_target_role_rejects_invalid_input(_tables, bad_value: str) -> None:
    service = ProfileService(db_client=DynamoDBClient())
    with pytest.raises(ValueError):
        service.update_target_role("user-3", bad_value)
