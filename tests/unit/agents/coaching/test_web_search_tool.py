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


class TestWebSearchTool:
    """@tool web_search — happy path, rate-limit, validation, HTTP errors."""

    def _service_ok(self) -> Dict[str, Any]:
        return {
            "answer": "AI roles grew 40% year-over-year.",
            "results": [
                {
                    "title": "AI Hiring Trends 2026",
                    "url": "https://example.com/ai-trends",
                    "snippet": "Demand spiked in Q1.",
                    "published_date": "2026-04-01",
                    "score": 0.92,
                }
            ],
        }

    def test_happy_path_returns_results_and_increments_counter(
        self, dynamodb_tables: Dict[str, Any]
    ) -> None:
        tools = _load_tools(dynamodb_tables)
        table = dynamodb_tables["user_profiles"]
        table.put_item(Item={"userId": "u1"})

        with patch(
            "backend.handlers.search.service.search",
            return_value=self._service_ok(),
        ) as mock_search:
            out = tools.web_search(query="ai jobs 2026", user_id="u1")

        assert "error" not in out
        assert out["answer"] == "AI roles grew 40% year-over-year."
        assert out["results"][0]["url"] == "https://example.com/ai-trends"
        assert out["remaining_today"] == 19
        mock_search.assert_called_once()
        item = table.get_item(Key={"userId": "u1"})["Item"]
        assert item["dailySearchCount"] == 1

    def test_validation_error_on_empty_query(
        self, dynamodb_tables: Dict[str, Any]
    ) -> None:
        tools = _load_tools(dynamodb_tables)
        table = dynamodb_tables["user_profiles"]
        table.put_item(Item={"userId": "u1"})

        out = tools.web_search(query="  ", user_id="u1")

        assert out["error_kind"] == "validation"
        item = table.get_item(Key={"userId": "u1"})["Item"]
        assert "dailySearchCount" not in item

    def test_rate_limit_returns_error_dict_not_raise(
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

        out = tools.web_search(query="ai jobs", user_id="u1")

        assert out["error"] == "daily_limit_reached"
        assert out["error_kind"] == "rate_limited"

    def test_http_401_returns_permanent_error(
        self, dynamodb_tables: Dict[str, Any]
    ) -> None:
        import urllib.error
        from io import BytesIO

        tools = _load_tools(dynamodb_tables)
        table = dynamodb_tables["user_profiles"]
        table.put_item(Item={"userId": "u1"})

        err = urllib.error.HTTPError(
            url="https://api.tavily.com/search",
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=BytesIO(b""),
        )
        with patch(
            "backend.handlers.search.service.search",
            side_effect=err,
        ):
            out = tools.web_search(query="anything", user_id="u1")

        assert out["error_kind"] == "permanent"

    def test_http_429_returns_rate_limited(
        self, dynamodb_tables: Dict[str, Any]
    ) -> None:
        import urllib.error
        from io import BytesIO

        tools = _load_tools(dynamodb_tables)
        table = dynamodb_tables["user_profiles"]
        table.put_item(Item={"userId": "u1"})

        err = urllib.error.HTTPError(
            url="https://api.tavily.com/search",
            code=429,
            msg="Too Many Requests",
            hdrs=None,
            fp=BytesIO(b""),
        )
        with patch(
            "backend.handlers.search.service.search",
            side_effect=err,
        ):
            out = tools.web_search(query="anything", user_id="u1")

        assert out["error_kind"] == "rate_limited"

    def test_network_error_returns_transient(
        self, dynamodb_tables: Dict[str, Any]
    ) -> None:
        import urllib.error

        tools = _load_tools(dynamodb_tables)
        table = dynamodb_tables["user_profiles"]
        table.put_item(Item={"userId": "u1"})

        with patch(
            "backend.handlers.search.service.search",
            side_effect=urllib.error.URLError("timeout"),
        ):
            out = tools.web_search(query="anything", user_id="u1")

        assert out["error_kind"] == "transient"
