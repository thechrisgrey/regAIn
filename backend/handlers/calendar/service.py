"""Calendar service module.

Contains business logic for calendar entry CRUD operations.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from boto3.dynamodb.conditions import Key

from backend.handlers.shared.dynamodb import DynamoDBClient

_VALID_CATEGORIES = {"task", "note"}
_VALID_AUTHORS = {"user", "agent"}


class CalendarService:
    """Handles calendar entry business logic."""

    def __init__(self, db_client: DynamoDBClient | None = None) -> None:
        self.db = db_client or DynamoDBClient()

    def list_entries(
        self,
        user_id: str,
        start: str,
        end: str,
    ) -> List[Dict[str, Any]]:
        """List calendar entries for a date range.

        Uses sort key range query: dateEntryId between start and end+chr(255).

        Args:
            user_id: Authenticated user ID.
            start: Start date (YYYY-MM-DD).
            end: End date (YYYY-MM-DD), inclusive.

        Returns:
            List of entry dicts.
        """
        return self.db.query_all(
            "calendar_entries",
            Key("userId").eq(user_id)
            & Key("dateEntryId").between(start, end + "\xff"),
        )

    def create_entry(
        self,
        user_id: str,
        date: str,
        category: str,
        content: str,
        author: str,
    ) -> Dict[str, Any]:
        """Create a new calendar entry.

        Args:
            user_id: Authenticated user ID.
            date: ISO date (YYYY-MM-DD).
            category: 'task' or 'note'.
            content: Plain text body.
            author: 'user' or 'agent'.

        Returns:
            Dict with dateEntryId of the created entry.

        Raises:
            ValueError: If category or author is invalid.
        """
        if category not in _VALID_CATEGORIES:
            raise ValueError(f"Invalid category: {category}. Must be one of {_VALID_CATEGORIES}")
        if author not in _VALID_AUTHORS:
            raise ValueError(f"Invalid author: {author}. Must be one of {_VALID_AUTHORS}")

        now = datetime.now(timezone.utc).isoformat()
        entry_id = f"{date}#{uuid.uuid4().hex[:12]}"

        item = {
            "userId": user_id,
            "dateEntryId": entry_id,
            "date": date,
            "category": category,
            "author": author,
            "content": content,
            "createdAt": now,
            "updatedAt": now,
        }
        self.db.put_item("calendar_entries", item)
        return {"dateEntryId": entry_id}

    def update_entry(
        self,
        user_id: str,
        date_entry_id: str,
        content: str,
    ) -> None:
        """Update a calendar entry's content. User-authored entries only.

        Args:
            user_id: Authenticated user ID.
            date_entry_id: Composite sort key.
            content: New content text.

        Raises:
            LookupError: If entry not found.
            PermissionError: If entry is agent-authored.
        """
        entry = self.db.get_item(
            "calendar_entries",
            {"userId": user_id, "dateEntryId": date_entry_id},
        )
        if not entry:
            raise LookupError("Entry not found")
        if entry.get("author") != "user":
            raise PermissionError("Cannot edit agent entries")

        now = datetime.now(timezone.utc).isoformat()
        self.db.update_item(
            "calendar_entries",
            {"userId": user_id, "dateEntryId": date_entry_id},
            {"content": content, "updatedAt": now},
        )

    def delete_entry(
        self,
        user_id: str,
        date_entry_id: str,
    ) -> None:
        """Delete a calendar entry. Any author allowed (user can dismiss agent entries).

        Args:
            user_id: Authenticated user ID.
            date_entry_id: Composite sort key.

        Raises:
            LookupError: If entry not found.
        """
        entry = self.db.get_item(
            "calendar_entries",
            {"userId": user_id, "dateEntryId": date_entry_id},
        )
        if not entry:
            raise LookupError("Entry not found")

        self.db.delete_item(
            "calendar_entries",
            {"userId": user_id, "dateEntryId": date_entry_id},
        )

    def get_heatmap(
        self,
        user_id: str,
        year: str,
    ) -> Dict[str, int]:
        """Get entry counts per day for a year (heat-map data).

        Uses a projected query on dateEntryId only to minimize read cost.

        Args:
            user_id: Authenticated user ID.
            year: Four-digit year string.

        Returns:
            Dict mapping date strings to entry counts.
        """
        entries = self.db.query_all(
            "calendar_entries",
            Key("userId").eq(user_id)
            & Key("dateEntryId").begins_with(year),
        )
        counts: Dict[str, int] = {}
        for entry in entries:
            date = entry["dateEntryId"].split("#")[0]
            counts[date] = counts.get(date, 0) + 1
        return counts
