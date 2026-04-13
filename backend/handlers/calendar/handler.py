"""Calendar Lambda handler.

Thin handler for calendar entry CRUD operations.
"""

import json
import logging
from typing import Any, Dict

from backend.handlers.shared.auth import get_user_id
from backend.handlers.shared.responses import error_response, success_response
from backend.handlers.shared.structured_log import get_logger
from backend.handlers.calendar.service import CalendarService


logger = logging.getLogger(__name__)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handle calendar API requests."""
    slog = get_logger(event, __name__)
    user_id = get_user_id(event)
    if not user_id:
        return error_response("Unauthorized", 401)

    method = event.get("httpMethod", "")
    resource = event.get("resource", "")
    params = event.get("queryStringParameters") or {}
    path_params = event.get("pathParameters") or {}

    try:
        service = CalendarService()

        # GET /calendar/heatmap?year=YYYY
        if resource == "/calendar/heatmap" and method == "GET":
            year = params.get("year")
            if not year or len(year) != 4:
                return error_response("Missing or invalid 'year' parameter", 400, error_kind="VALIDATION")
            heatmap = service.get_heatmap(user_id, year)
            return success_response({"heatmap": heatmap})

        # GET /calendar?start=YYYY-MM-DD&end=YYYY-MM-DD
        if resource == "/calendar" and method == "GET":
            start = params.get("start")
            end = params.get("end")
            if not start or not end:
                return error_response("Missing 'start' or 'end' parameter", 400, error_kind="VALIDATION")
            entries = service.list_entries(user_id, start, end)
            return success_response({"entries": entries})

        # POST /calendar
        if resource == "/calendar" and method == "POST":
            body = json.loads(event.get("body") or "{}")
            date = body.get("date")
            category = body.get("category")
            content = body.get("content")
            if not date or not category or not content:
                return error_response("Missing date, category, or content", 400, error_kind="VALIDATION")
            result = service.create_entry(user_id, date, category, content, "user")
            return success_response(result, 201)

        # PUT /calendar/{dateEntryId}
        if resource == "/calendar/{dateEntryId}" and method == "PUT":
            date_entry_id = path_params.get("dateEntryId")
            if not date_entry_id:
                return error_response("Missing dateEntryId", 400, error_kind="VALIDATION")
            body = json.loads(event.get("body") or "{}")
            content = body.get("content")
            if not content:
                return error_response("Missing content", 400, error_kind="VALIDATION")
            service.update_entry(user_id, date_entry_id, content)
            return success_response({"status": "updated"})

        # DELETE /calendar/{dateEntryId}
        if resource == "/calendar/{dateEntryId}" and method == "DELETE":
            date_entry_id = path_params.get("dateEntryId")
            if not date_entry_id:
                return error_response("Missing dateEntryId", 400, error_kind="VALIDATION")
            service.delete_entry(user_id, date_entry_id)
            return success_response({"status": "deleted"})

        return error_response("Not found", 404)

    except ValueError as e:
        return error_response(str(e), 400, error_kind="VALIDATION")
    except PermissionError as e:
        return error_response(str(e), 403)
    except LookupError as e:
        return error_response(str(e), 404, error_kind="NOT_FOUND")
    except Exception:
        slog.exception("Calendar handler failed")
        return error_response("Internal server error", 500)
