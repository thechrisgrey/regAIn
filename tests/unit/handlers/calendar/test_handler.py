"""Unit tests for Calendar Lambda handler."""

import json
from unittest.mock import MagicMock, patch

import pytest


def _make_event(method, resource, body=None, query_params=None, path_params=None):
    event = {
        "httpMethod": method,
        "resource": resource,
        "requestContext": {
            "authorizer": {"claims": {"sub": "user-123"}},
        },
        "queryStringParameters": query_params,
        "pathParameters": path_params,
        "body": json.dumps(body) if body else None,
    }
    return event


@patch("backend.handlers.calendar.handler.CalendarService")
class TestCalendarHandler:
    def test_list_entries(self, MockService):
        from backend.handlers.calendar.handler import lambda_handler

        mock_svc = MockService.return_value
        mock_svc.list_entries.return_value = [{"dateEntryId": "2026-04-12#abc"}]

        event = _make_event("GET", "/calendar", query_params={"start": "2026-04-01", "end": "2026-04-30"})
        response = lambda_handler(event, None)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert len(body["entries"]) == 1
        mock_svc.list_entries.assert_called_once_with("user-123", "2026-04-01", "2026-04-30")

    def test_list_entries_missing_params(self, MockService):
        from backend.handlers.calendar.handler import lambda_handler

        event = _make_event("GET", "/calendar", query_params={})
        response = lambda_handler(event, None)
        assert response["statusCode"] == 400

    def test_create_entry(self, MockService):
        from backend.handlers.calendar.handler import lambda_handler

        mock_svc = MockService.return_value
        mock_svc.create_entry.return_value = {"dateEntryId": "2026-04-12#abc"}

        event = _make_event("POST", "/calendar", body={"date": "2026-04-12", "category": "task", "content": "Test"})
        response = lambda_handler(event, None)

        assert response["statusCode"] == 201
        body = json.loads(response["body"])
        assert body["dateEntryId"] == "2026-04-12#abc"
        mock_svc.create_entry.assert_called_once_with("user-123", "2026-04-12", "task", "Test", "user")

    def test_update_entry(self, MockService):
        from backend.handlers.calendar.handler import lambda_handler

        mock_svc = MockService.return_value
        mock_svc.update_entry.return_value = None

        event = _make_event(
            "PUT", "/calendar/{dateEntryId}",
            body={"content": "Updated"},
            path_params={"dateEntryId": "2026-04-12#abc"},
        )
        response = lambda_handler(event, None)
        assert response["statusCode"] == 200
        mock_svc.update_entry.assert_called_once_with("user-123", "2026-04-12#abc", "Updated")

    def test_update_agent_entry_returns_403(self, MockService):
        from backend.handlers.calendar.handler import lambda_handler

        mock_svc = MockService.return_value
        mock_svc.update_entry.side_effect = PermissionError("Cannot edit agent entries")

        event = _make_event(
            "PUT", "/calendar/{dateEntryId}",
            body={"content": "Updated"},
            path_params={"dateEntryId": "2026-04-12#abc"},
        )
        response = lambda_handler(event, None)
        assert response["statusCode"] == 403

    def test_delete_entry(self, MockService):
        from backend.handlers.calendar.handler import lambda_handler

        mock_svc = MockService.return_value
        mock_svc.delete_entry.return_value = None

        event = _make_event(
            "DELETE", "/calendar/{dateEntryId}",
            path_params={"dateEntryId": "2026-04-12#abc"},
        )
        response = lambda_handler(event, None)
        assert response["statusCode"] == 200

    def test_get_heatmap(self, MockService):
        from backend.handlers.calendar.handler import lambda_handler

        mock_svc = MockService.return_value
        mock_svc.get_heatmap.return_value = {"2026-04-10": 2, "2026-04-12": 1}

        event = _make_event("GET", "/calendar/heatmap", query_params={"year": "2026"})
        response = lambda_handler(event, None)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["heatmap"]["2026-04-10"] == 2

    def test_unauthorized_returns_401(self, MockService):
        from backend.handlers.calendar.handler import lambda_handler

        event = {
            "httpMethod": "GET",
            "resource": "/calendar",
            "requestContext": {"authorizer": {"claims": {}}},
            "queryStringParameters": {"start": "2026-04-01", "end": "2026-04-30"},
            "body": None,
        }
        response = lambda_handler(event, None)
        assert response["statusCode"] == 401
