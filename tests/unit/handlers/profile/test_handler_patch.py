"""Unit tests for PATCH /profile route in profile handler."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from backend.handlers.profile import handler as profile_handler


def _patch_event(body: dict | str | None) -> dict:
    return {
        "httpMethod": "PATCH",
        "resource": "/profile",
        "body": body if isinstance(body, str) or body is None else json.dumps(body),
        "requestContext": {
            "authorizer": {"claims": {"sub": "user-1"}},
            "requestId": "rid-1",
        },
    }


def test_patch_profile_updates_target_role() -> None:
    fake_service = MagicMock()
    fake_service.update_target_role.return_value = {"targetRole": "Cloud Architect"}

    with patch.object(profile_handler, "ProfileService", return_value=fake_service):
        result = profile_handler.lambda_handler(
            _patch_event({"targetRole": "Cloud Architect"}), None
        )

    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["targetRole"] == "Cloud Architect"
    fake_service.update_target_role.assert_called_once_with("user-1", "Cloud Architect")


def test_patch_profile_rejects_missing_body() -> None:
    result = profile_handler.lambda_handler(_patch_event(None), None)
    assert result["statusCode"] == 400


def test_patch_profile_rejects_invalid_json() -> None:
    result = profile_handler.lambda_handler(_patch_event("not-json"), None)
    assert result["statusCode"] == 400


def test_patch_profile_rejects_missing_target_role() -> None:
    result = profile_handler.lambda_handler(_patch_event({"foo": "bar"}), None)
    assert result["statusCode"] == 400


def test_patch_profile_rejects_non_string_target_role() -> None:
    result = profile_handler.lambda_handler(_patch_event({"targetRole": 42}), None)
    assert result["statusCode"] == 400


def test_patch_profile_returns_400_on_value_error() -> None:
    fake_service = MagicMock()
    fake_service.update_target_role.side_effect = ValueError("too long")

    with patch.object(profile_handler, "ProfileService", return_value=fake_service):
        result = profile_handler.lambda_handler(
            _patch_event({"targetRole": "x"}), None
        )

    assert result["statusCode"] == 400
    assert "too long" in json.loads(result["body"])["error"]


def test_patch_profile_requires_auth() -> None:
    event = _patch_event({"targetRole": "x"})
    event["requestContext"] = {"requestId": "rid-2"}
    result = profile_handler.lambda_handler(event, None)
    assert result["statusCode"] == 401
