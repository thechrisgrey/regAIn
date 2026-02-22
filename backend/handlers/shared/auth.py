"""Shared authentication utilities."""

from typing import Any, Dict, Optional


def get_user_id(event: Dict[str, Any]) -> Optional[str]:
    """Extract userId from Cognito authorizer claims."""
    try:
        return event["requestContext"]["authorizer"]["claims"]["sub"]
    except (KeyError, TypeError):
        return None
