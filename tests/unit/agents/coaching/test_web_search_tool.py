"""Unit tests for the web_search @tool and its rate-limit helper.

The @tool decorator from strands is stubbed via _strands_stub so tools.py
imports without strands-agents installed. DynamoDB operations use the
shared dynamodb_tables moto fixture.
"""

import importlib
import sys
import types
from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Stub the strands module so tools.py can be imported
# ---------------------------------------------------------------------------
_strands_stub = types.ModuleType("strands")
_strands_stub.tool = lambda fn: fn
sys.modules.setdefault("strands", _strands_stub)


def _load_tools(dynamodb_tables: Dict[str, Any]):
    """Import tools module with a fresh DynamoDBClient bound to moto tables."""
    mod_name = "backend.agents.coaching.tools"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    return importlib.import_module(mod_name)


class TestSearchRateLimit:
    """Atomic daily search counter on UserProfiles."""

    def test_first_search_of_day_sets_count_to_one(
        self, dynamodb_tables: Dict[str, Any]
    ) -> None:
        tools = _load_tools(dynamodb_tables)
        table = dynamodb_tables["user_profiles"]
        table.put_item(Item={"userId": "u1"})

        tools._enforce_daily_search_limit("u1")

        item = table.get_item(Key={"userId": "u1"})["Item"]
        assert item["dailySearchCount"] == 1
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        assert item["lastSearchDate"] == today

    def test_increments_count_on_same_day(
        self, dynamodb_tables: Dict[str, Any]
    ) -> None:
        tools = _load_tools(dynamodb_tables)
        table = dynamodb_tables["user_profiles"]
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        table.put_item(
            Item={
                "userId": "u1",
                "dailySearchCount": 5,
                "lastSearchDate": today,
            }
        )

        tools._enforce_daily_search_limit("u1")

        item = table.get_item(Key={"userId": "u1"})["Item"]
        assert item["dailySearchCount"] == 6

    def test_resets_count_on_new_day(
        self, dynamodb_tables: Dict[str, Any]
    ) -> None:
        tools = _load_tools(dynamodb_tables)
        table = dynamodb_tables["user_profiles"]
        table.put_item(
            Item={
                "userId": "u1",
                "dailySearchCount": 19,
                "lastSearchDate": "1999-01-01",
            }
        )

        tools._enforce_daily_search_limit("u1")

        item = table.get_item(Key={"userId": "u1"})["Item"]
        assert item["dailySearchCount"] == 1

    def test_raises_when_limit_reached(
        self, dynamodb_tables: Dict[str, Any]
    ) -> None:
        tools = _load_tools(dynamodb_tables)
        table = dynamodb_tables["user_profiles"]
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        table.put_item(
            Item={
                "userId": "u1",
                "dailySearchCount": 20,
                "lastSearchDate": today,
            }
        )

        with pytest.raises(tools._SearchRateLimitExceeded):
            tools._enforce_daily_search_limit("u1")

        item = table.get_item(Key={"userId": "u1"})["Item"]
        assert item["dailySearchCount"] == 20

    def test_limit_constant_is_twenty(
        self, dynamodb_tables: Dict[str, Any]
    ) -> None:
        tools = _load_tools(dynamodb_tables)
        assert tools.WEB_SEARCH_DAILY_LIMIT == 20
