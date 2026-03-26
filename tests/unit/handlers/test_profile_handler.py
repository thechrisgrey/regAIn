"""Unit tests for profile handler mode routing."""

from unittest.mock import patch

from backend.handlers.profile.handler import lambda_handler


def _make_event(method="DELETE", resource="/profile", body=None, user_id="user-123"):
    """Build a minimal API Gateway event."""
    event = {
        "httpMethod": method,
        "resource": resource,
        "body": body,
        "requestContext": {
            "authorizer": {"claims": {"sub": user_id}},
            "requestId": "test-req",
        },
    }
    return event


class TestDeleteModeRouting:
    """Verify DELETE /profile routes to correct service method based on mode."""

    @patch("backend.handlers.profile.handler.ProfileService")
    def test_immediate_mode_calls_hard_delete(self, MockService):
        service = MockService.return_value
        service.hard_delete_user_account.return_value = {
            "status": "deleted",
            "deleted": {"user_profiles": 1},
        }

        event = _make_event(body='{"mode": "immediate"}')
        result = lambda_handler(event, None)

        service.hard_delete_user_account.assert_called_once_with("user-123")
        assert result["statusCode"] == 200

    @patch("backend.handlers.profile.handler.ProfileService")
    def test_scheduled_mode_calls_soft_delete(self, MockService):
        service = MockService.return_value
        service.soft_delete_user_account.return_value = {
            "status": "scheduled",
            "deletionDate": "2026-04-25T00:00:00+00:00",
        }

        event = _make_event(body='{"mode": "scheduled"}')
        result = lambda_handler(event, None)

        service.soft_delete_user_account.assert_called_once_with("user-123")
        assert result["statusCode"] == 200

    @patch("backend.handlers.profile.handler.ProfileService")
    def test_missing_mode_returns_400(self, MockService):
        event = _make_event(body='{}')
        result = lambda_handler(event, None)

        assert result["statusCode"] == 400
        service = MockService.return_value
        service.hard_delete_user_account.assert_not_called()
        service.soft_delete_user_account.assert_not_called()

    @patch("backend.handlers.profile.handler.ProfileService")
    def test_invalid_mode_returns_400(self, MockService):
        event = _make_event(body='{"mode": "invalid"}')
        result = lambda_handler(event, None)

        assert result["statusCode"] == 400

    @patch("backend.handlers.profile.handler.ProfileService")
    def test_no_body_returns_400(self, MockService):
        event = _make_event(body=None)
        result = lambda_handler(event, None)

        assert result["statusCode"] == 400

    @patch("backend.handlers.profile.handler.ProfileService")
    def test_recover_endpoint_unchanged(self, MockService):
        service = MockService.return_value
        service.recover_user_account.return_value = {"status": "recovered"}

        event = _make_event(method="POST", resource="/profile/recover")
        result = lambda_handler(event, None)

        service.recover_user_account.assert_called_once_with("user-123")
        assert result["statusCode"] == 200
