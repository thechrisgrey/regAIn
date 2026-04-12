"""Unit tests for CalendarService."""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from backend.handlers.calendar.service import CalendarService


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def service(mock_db):
    return CalendarService(db_client=mock_db)


class TestListEntries:
    def test_queries_with_date_range(self, service, mock_db):
        mock_db.query_all.return_value = []
        result = service.list_entries("user-1", "2026-04-01", "2026-04-30")
        mock_db.query_all.assert_called_once()
        call_args = mock_db.query_all.call_args
        assert call_args[0][0] == "calendar_entries"
        assert result == []

    def test_returns_entries_in_range(self, service, mock_db):
        entries = [
            {"dateEntryId": "2026-04-10#abc", "date": "2026-04-10", "content": "b"},
            {"dateEntryId": "2026-04-05#def", "date": "2026-04-05", "content": "a"},
        ]
        mock_db.query_all.return_value = entries
        result = service.list_entries("user-1", "2026-04-01", "2026-04-30")
        assert len(result) == 2


class TestCreateEntry:
    def test_creates_entry_with_uuid(self, service, mock_db):
        mock_db.put_item.return_value = {}
        result = service.create_entry("user-1", "2026-04-12", "task", "Do something", "user")
        mock_db.put_item.assert_called_once()
        item = mock_db.put_item.call_args[0][1]
        assert item["userId"] == "user-1"
        assert item["date"] == "2026-04-12"
        assert item["category"] == "task"
        assert item["author"] == "user"
        assert item["content"] == "Do something"
        assert item["dateEntryId"].startswith("2026-04-12#")
        assert "dateEntryId" in result

    def test_rejects_invalid_category(self, service, mock_db):
        with pytest.raises(ValueError, match="category"):
            service.create_entry("user-1", "2026-04-12", "event", "Bad", "user")

    def test_rejects_invalid_author(self, service, mock_db):
        with pytest.raises(ValueError, match="author"):
            service.create_entry("user-1", "2026-04-12", "task", "Bad", "system")


class TestUpdateEntry:
    def test_updates_user_entry(self, service, mock_db):
        mock_db.get_item.return_value = {
            "userId": "user-1",
            "dateEntryId": "2026-04-12#abc",
            "author": "user",
        }
        mock_db.update_item.return_value = {}
        service.update_entry("user-1", "2026-04-12#abc", "Updated content")
        mock_db.update_item.assert_called_once()

    def test_rejects_agent_entry_update(self, service, mock_db):
        mock_db.get_item.return_value = {
            "userId": "user-1",
            "dateEntryId": "2026-04-12#abc",
            "author": "agent",
        }
        with pytest.raises(PermissionError):
            service.update_entry("user-1", "2026-04-12#abc", "Updated content")

    def test_rejects_missing_entry(self, service, mock_db):
        mock_db.get_item.return_value = None
        with pytest.raises(LookupError):
            service.update_entry("user-1", "2026-04-12#abc", "Updated content")


class TestDeleteEntry:
    def test_deletes_entry(self, service, mock_db):
        mock_db.get_item.return_value = {
            "userId": "user-1",
            "dateEntryId": "2026-04-12#abc",
        }
        mock_db.delete_item.return_value = {}
        service.delete_entry("user-1", "2026-04-12#abc")
        mock_db.delete_item.assert_called_once_with(
            "calendar_entries",
            {"userId": "user-1", "dateEntryId": "2026-04-12#abc"},
        )

    def test_rejects_missing_entry(self, service, mock_db):
        mock_db.get_item.return_value = None
        with pytest.raises(LookupError):
            service.delete_entry("user-1", "2026-04-12#abc")


class TestGetHeatmap:
    def test_returns_date_count_map(self, service, mock_db):
        mock_db.query_all.return_value = [
            {"dateEntryId": "2026-04-10#a"},
            {"dateEntryId": "2026-04-10#b"},
            {"dateEntryId": "2026-04-12#c"},
        ]
        result = service.get_heatmap("user-1", "2026")
        assert result == {"2026-04-10": 2, "2026-04-12": 1}
