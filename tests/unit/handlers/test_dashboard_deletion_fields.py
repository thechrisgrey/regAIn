"""Tests for deletedAt/deletionScheduledFor passthrough in dashboard response."""

from unittest.mock import MagicMock

from backend.handlers.dashboard.service import DashboardService


def _make_db_client(profile=None, campaigns=None, missions=None, evidence=None):
    """Build a mock DynamoDBClient."""
    db = MagicMock()
    db.get_item.return_value = profile
    db.query_all.side_effect = lambda table, *a, **kw: {
        "campaigns": campaigns or [],
        "mission_history": missions or [],
        "evidence_vault": evidence or [],
    }.get(table, [])
    return db


class TestDashboardDeletionFields:
    """Verify deletedAt/deletionScheduledFor appear in dashboard response."""

    def test_includes_deletion_fields_when_soft_deleted(self):
        profile = {
            "userId": "u1",
            "deletedAt": "2026-03-26T12:00:00+00:00",
            "deletionScheduledFor": "2026-04-25T12:00:00+00:00",
        }
        db = _make_db_client(profile=profile)
        service = DashboardService(db_client=db)

        result = service.get_dashboard("u1")

        assert result["deletedAt"] == "2026-03-26T12:00:00+00:00"
        assert result["deletionScheduledFor"] == "2026-04-25T12:00:00+00:00"

    def test_omits_deletion_fields_when_not_deleted(self):
        profile = {"userId": "u1", "name": "Jane"}
        db = _make_db_client(profile=profile)
        service = DashboardService(db_client=db)

        result = service.get_dashboard("u1")

        assert "deletedAt" not in result
        assert "deletionScheduledFor" not in result

    def test_omits_deletion_fields_when_profile_not_found(self):
        db = _make_db_client(profile=None)
        service = DashboardService(db_client=db)

        result = service.get_dashboard("u1")

        assert "deletedAt" not in result
        assert "deletionScheduledFor" not in result
