"""Unit tests for backend.handlers.shared.idempotency module."""

import json
import os
import time
from typing import Any, Dict
from unittest.mock import patch

import boto3
import pytest
from moto import mock_aws

from backend.handlers.shared.idempotency import with_idempotency


@pytest.fixture()
def idempotency_env(aws_credentials: None):
    """Create a mocked DynamoDB idempotency table and set the env var."""
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        table = dynamodb.create_table(
            TableName="RegainIdempotencyKeys",
            KeySchema=[{"AttributeName": "idempotencyKey", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "idempotencyKey", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        os.environ["IDEMPOTENCY_TABLE"] = "RegainIdempotencyKeys"
        yield table
        os.environ.pop("IDEMPOTENCY_TABLE", None)


def _make_event(key: str = "test-key-1") -> Dict[str, Any]:
    """Build a minimal API Gateway event with an Idempotency-Key header."""
    return {
        "headers": {"Idempotency-Key": key},
        "body": None,
    }


def _ok_handler(event: Dict[str, Any]) -> Dict[str, Any]:
    return {"statusCode": 200, "body": json.dumps({"ok": True})}


def _conflict_handler(event: Dict[str, Any]) -> Dict[str, Any]:
    return {"statusCode": 409, "body": json.dumps({"error": "conflict"})}


def _server_error_handler(event: Dict[str, Any]) -> Dict[str, Any]:
    return {"statusCode": 500, "body": json.dumps({"error": "internal"})}


class TestIdempotency:
    def test_cache_hit_returns_cached_2xx(self, idempotency_env) -> None:
        """Duplicate key returns cached 200 without re-executing handler."""
        event = _make_event("dedup-200")
        call_count = 0

        def counting_handler(e):
            nonlocal call_count
            call_count += 1
            return _ok_handler(e)

        r1 = with_idempotency(event, counting_handler)
        r2 = with_idempotency(event, counting_handler)

        assert r1["statusCode"] == 200
        assert r2["statusCode"] == 200
        assert call_count == 1  # handler only called once

    def test_does_not_cache_5xx(self, idempotency_env) -> None:
        """Handler returning 500 is not cached; same key re-executes handler."""
        event = _make_event("no-cache-500")
        call_count = 0

        def counting_handler(e):
            nonlocal call_count
            call_count += 1
            return _server_error_handler(e)

        r1 = with_idempotency(event, counting_handler)
        r2 = with_idempotency(event, counting_handler)

        assert r1["statusCode"] == 500
        assert r2["statusCode"] == 500
        assert call_count == 2  # handler called twice (not cached)

    def test_caches_4xx(self, idempotency_env) -> None:
        """Handler returning 409 IS cached (intentional dedup)."""
        event = _make_event("cache-409")
        call_count = 0

        def counting_handler(e):
            nonlocal call_count
            call_count += 1
            return _conflict_handler(e)

        r1 = with_idempotency(event, counting_handler)
        r2 = with_idempotency(event, counting_handler)

        assert r1["statusCode"] == 409
        assert r2["statusCode"] == 409
        assert call_count == 1  # handler only called once

    def test_expired_entry_re_executes(self, idempotency_env) -> None:
        """TTL-expired entry does not block re-execution."""
        event = _make_event("expired-key")

        # Manually insert an expired cache entry
        table = idempotency_env
        table.put_item(
            Item={
                "idempotencyKey": "expired-key",
                "responseBody": json.dumps({"statusCode": 200, "body": "old"}),
                "statusCode": 200,
                "expiresAt": int(time.time()) - 100,  # expired
            }
        )

        call_count = 0

        def counting_handler(e):
            nonlocal call_count
            call_count += 1
            return _ok_handler(e)

        result = with_idempotency(event, counting_handler)
        assert result["statusCode"] == 200
        assert call_count == 1  # handler was called (not using expired cache)

    def test_missing_table_env_bypasses(self, aws_credentials) -> None:
        """No IDEMPOTENCY_TABLE runs handler directly."""
        os.environ.pop("IDEMPOTENCY_TABLE", None)
        event = _make_event("bypass-key")
        call_count = 0

        def counting_handler(e):
            nonlocal call_count
            call_count += 1
            return _ok_handler(e)

        result = with_idempotency(event, counting_handler)
        assert result["statusCode"] == 200
        assert call_count == 1

    def test_missing_key_header_bypasses(self, idempotency_env) -> None:
        """No Idempotency-Key header runs handler directly."""
        event = {"headers": {}, "body": None}
        call_count = 0

        def counting_handler(e):
            nonlocal call_count
            call_count += 1
            return _ok_handler(e)

        result = with_idempotency(event, counting_handler)
        assert result["statusCode"] == 200
        assert call_count == 1
