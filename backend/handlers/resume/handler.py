"""Resume Lambda handler.

Thin handler that routes by event shape:
- API Gateway GET /resume → get_resume
- API Gateway POST /resume/generate → generate_resume
- Async event (Lambda.invoke Event) → generate_resume
"""

import logging
from typing import Any, Dict

from backend.handlers.shared.auth import get_user_id
from backend.handlers.shared.idempotency import with_idempotency
from backend.handlers.shared.responses import error_response, success_response
from backend.handlers.shared.structured_log import get_logger
from backend.handlers.resume.service import (
    ResumeGenerationError,
    ResumeResult,
    ResumeService,
)

logger = logging.getLogger(__name__)


def _is_api_gateway_event(event: Dict[str, Any]) -> bool:
    """Check if the event originated from API Gateway."""
    return "httpMethod" in event and "requestContext" in event


def _parse_frontmatter(content: str) -> Dict[str, Any] | None:
    """Parse YAML-style frontmatter from resume markdown content.

    Handles simple ``key: value`` pairs (no nested structures).

    Args:
        content: Full resume markdown with YAML frontmatter.

    Returns:
        Parsed frontmatter dict, or None if parsing fails.
    """
    if not content.startswith("---"):
        return None
    parts = content.split("---", 2)
    if len(parts) < 3:
        return None
    try:
        result: Dict[str, Any] = {}
        for line in parts[1].strip().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, _, value = line.partition(":")
            if not _:
                continue
            result[key.strip()] = value.strip()
        return result if result else None
    except Exception:
        return None


def _format_resume_response(result: ResumeResult) -> Dict[str, Any]:
    """Format a ResumeResult into the API response shape.

    Args:
        result: The resume generation or retrieval result.

    Returns:
        Dict with content, generatedAt, version, downloadUrl,
        and parsed frontmatter.
    """
    response: Dict[str, Any] = {
        "content": result.content,
        "generatedAt": result.generated_at,
        "version": result.version,
        "downloadUrl": result.presigned_url,
    }
    frontmatter = _parse_frontmatter(result.content)
    if frontmatter:
        response["frontmatter"] = frontmatter
    return response


def _handle_get(user_id: str, service: ResumeService) -> Dict[str, Any]:
    """Handle GET /resume — retrieve latest resume.

    Args:
        user_id: The authenticated user's ID.
        service: ResumeService instance.

    Returns:
        API Gateway-compatible response.
    """
    result = service.get_resume(user_id)
    return success_response(_format_resume_response(result))


def _handle_post(user_id: str, service: ResumeService) -> Dict[str, Any]:
    """Handle POST /resume/generate — on-demand generation.

    Args:
        user_id: The authenticated user's ID.
        service: ResumeService instance.

    Returns:
        API Gateway-compatible response.
    """
    result = service.generate_resume(user_id)
    return success_response(_format_resume_response(result))


def _handle_async(user_id: str, service: ResumeService) -> Dict[str, Any]:
    """Handle async invocation from mission completion or phase advancement.

    Args:
        user_id: The user ID from the async event payload.
        service: ResumeService instance.

    Returns:
        Simple dict for Lambda runtime (no API Gateway format needed).
    """
    service.generate_resume(user_id)
    return {"status": "ok"}


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Route to GET (fetch), POST (generate), or async (generate).

    Args:
        event: Lambda event — API Gateway or async invocation payload.
        context: Lambda context.

    Returns:
        API Gateway-compatible response or simple dict for async.
    """
    slog = get_logger(event if _is_api_gateway_event(event) else None, __name__)
    service = ResumeService()

    # Async event: has user_id and trigger, no httpMethod
    if not _is_api_gateway_event(event):
        user_id = event.get("user_id")
        if not user_id:
            slog.error("Async event missing user_id: %s", event)
            return {"status": "error", "message": "Missing user_id"}
        try:
            return _handle_async(user_id, service)
        except Exception:
            slog.exception("Async resume generation failed for user %s", user_id)
            return {"status": "error", "message": "Generation failed"}

    # API Gateway event: extract user from Cognito claims
    user_id = get_user_id(event)
    if not user_id:
        return error_response("Unauthorized", 401)

    http_method = event.get("httpMethod", "")

    try:
        if http_method == "GET":
            return _handle_get(user_id, service)
        if http_method == "POST":
            return with_idempotency(event, lambda e: _handle_post(user_id, service))
        return error_response("Method not allowed", 400)
    except ResumeGenerationError as exc:
        return error_response(str(exc), exc.status_code)
    except Exception:
        slog.exception("Resume handler failed")
        return error_response("Internal server error", 500)
