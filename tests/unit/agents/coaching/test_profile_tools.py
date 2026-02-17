"""Unit tests for read_user_profile and update_user_profile Strands tools.

Tests use moto-mocked DynamoDB via the shared dynamodb_tables fixture.
The @tool decorator from strands is stubbed since strands-agents is not
yet installed.
"""

import importlib
import sys
import types
from typing import Any, Dict
from unittest.mock import MagicMock

import pytest
from moto import mock_aws


# ---------------------------------------------------------------------------
# Stub the strands module so tools.py can be imported without strands-agents
# ---------------------------------------------------------------------------
_strands_stub = types.ModuleType("strands")
_strands_stub.tool = lambda fn: fn  # @tool is a no-op passthrough
sys.modules.setdefault("strands", _strands_stub)


def _load_tools(dynamodb_tables: Dict[str, Any]):
    """Import tools module with a fresh DynamoDBClient bound to moto tables."""
    # Force reimport so the module-level DynamoDBClient picks up moto env vars
    mod_name = "backend.agents.coaching.tools"
    if mod_name in sys.modules:
        del sys.modules[mod_name]

    tools = importlib.import_module(mod_name)
    return tools


class TestReadUserProfile:
    """Tests for the read_user_profile tool."""

    def test_returns_profile_when_exists(self, dynamodb_tables: Dict[str, Any]) -> None:
        """Reading an existing profile returns the full item dict."""
        table = dynamodb_tables["user_profiles"]
        table.put_item(Item={
            "userId": "user-1",
            "email": "[email]",
            "name": "Jane",
            "persona": "ai_displaced",
            "onboardingCompleted": False,
            "createdAt": "2025-01-01T00:00:00Z",
            "skills": ["python", "testing"],
        })

        tools = _load_tools(dynamodb_tables)
        result = tools.read_user_profile("user-1")

        assert result["userId"] == "user-1"
        assert result["name"] == "Jane"
        assert result["persona"] == "ai_displaced"
        assert result["skills"] == ["python", "testing"]

    def test_returns_error_when_not_found(self, dynamodb_tables: Dict[str, Any]) -> None:
        """Reading a nonexistent profile returns a not_found error dict."""
        tools = _load_tools(dynamodb_tables)
        result = tools.read_user_profile("nonexistent-user")

        assert result["error"] == "not_found"
        assert "nonexistent-user" in result["message"]

    def test_returns_error_when_table_not_configured(self, aws_credentials: None) -> None:
        """Reading when the table env var is missing returns an error dict."""
        import os
        # Clear the env var so DynamoDBClient can't resolve the table
        os.environ.pop("USER_PROFILES_TABLE", None)

        tools = _load_tools({})
        result = tools.read_user_profile("user-1")

        assert result["error"] in ("invalid_input", "read_failed")


class TestUpdateUserProfile:
    """Tests for the update_user_profile tool."""

    def test_updates_and_returns_profile(self, dynamodb_tables: Dict[str, Any]) -> None:
        """Updating fields returns the full profile with new values."""
        table = dynamodb_tables["user_profiles"]
        table.put_item(Item={
            "userId": "user-2",
            "email": "[email]",
            "name": "Alex",
            "persona": "veteran",
            "onboardingCompleted": False,
            "createdAt": "2025-01-01T00:00:00Z",
            "skills": [],
        })

        tools = _load_tools(dynamodb_tables)
        result = tools.update_user_profile("user-2", {
            "skills": ["leadership", "logistics"],
            "onboardingCompleted": True,
        })

        assert result["skills"] == ["leadership", "logistics"]
        assert result["onboardingCompleted"] is True
        assert result["name"] == "Alex"  # unchanged field preserved

    def test_returns_error_for_empty_updates(self, dynamodb_tables: Dict[str, Any]) -> None:
        """Passing an empty updates dict returns an invalid_input error."""
        tools = _load_tools(dynamodb_tables)
        result = tools.update_user_profile("user-2", {})

        assert result["error"] == "invalid_input"
        assert "No updates" in result["message"]

    def test_returns_error_when_table_not_configured(self, aws_credentials: None) -> None:
        """Updating when the table env var is missing returns an error dict."""
        import os
        os.environ.pop("USER_PROFILES_TABLE", None)

        tools = _load_tools({})
        result = tools.update_user_profile("user-1", {"name": "Test"})

        assert result["error"] in ("invalid_input", "write_failed")
