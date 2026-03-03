"""Evidence Lambda handler.

Thin handler for GET /evidence with optional skill_tag filtering,
and GET /evidence/suggest-tags for taxonomy-based skill suggestions.
"""

import logging
from typing import Any, Dict

from backend.handlers.shared.auth import get_user_id
from backend.handlers.shared.responses import error_response, success_response
from backend.handlers.shared.structured_log import get_logger
from backend.handlers.evidence.service import EvidenceService

logger = logging.getLogger(__name__)

_MAX_SUGGESTIONS = 8


def _suggest_tags(reflection: str) -> list[str]:
    """Return taxonomy-matched skill suggestions from reflection text.

    Does case-insensitive substring matching of taxonomy aliases against
    the reflection text, returning up to _MAX_SUGGESTIONS canonical names.
    """
    if not reflection or len(reflection.strip()) < 3:
        return []

    from backend.handlers.market_intel.taxonomy import ALIAS_INDEX

    text_lower = reflection.lower()
    seen: set[str] = set()
    suggestions: list[str] = []

    for alias, canonical in ALIAS_INDEX.items():
        if canonical in seen:
            continue
        # Only match aliases that are at least 3 chars (skip O*NET codes).
        if len(alias) < 3:
            continue
        if alias in text_lower:
            seen.add(canonical)
            suggestions.append(canonical)
            if len(suggestions) >= _MAX_SUGGESTIONS:
                break

    return suggestions


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handle evidence API requests.

    Routes:
        GET /evidence — list evidence with optional filtering
        GET /evidence/suggest-tags — taxonomy-based skill suggestions

    Args:
        event: API Gateway event.
        context: Lambda context.

    Returns:
        API Gateway-compatible response.
    """
    slog = get_logger(event, __name__)
    user_id = get_user_id(event)
    if not user_id:
        return error_response("Unauthorized", 401)

    resource = event.get("resource", "")

    try:
        if resource == "/evidence/suggest-tags":
            params = event.get("queryStringParameters") or {}
            reflection = (params.get("reflection") or "")[:500]
            suggestions = _suggest_tags(reflection)
            return success_response({"suggestions": suggestions})

        params = event.get("queryStringParameters") or {}
        try:
            limit = min(int(params.get("limit", "50")), 200)
        except (ValueError, TypeError):
            return error_response("Invalid limit parameter", 400, error_kind="VALIDATION")
        cursor = params.get("cursor")
        service = EvidenceService()
        page = service.list_evidence(
            user_id, skill_tag=params.get("skill_tag"), limit=limit, cursor=cursor,
        )
        return success_response({
            "evidence": page["items"],
            "items": page["items"],
            "nextCursor": page["nextCursor"],
        })
    except Exception:
        slog.exception("Evidence handler failed")
        return error_response("Internal server error", 500)
