"""Secrets Manager client with in-memory caching and env var fallback.

Usage:
    from backend.handlers.shared.secrets import get_secret

    api_key = get_secret("regain/onet-api-key")

Resolution order:
1. In-memory cache (5-minute TTL)
2. AWS Secrets Manager
3. Fallback environment variable (derived from secret name)
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import boto3

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 300  # 5 minutes
_cache: dict[str, tuple[str, float]] = {}

_client: Any = None


def _get_client() -> Any:
    """Return a lazily-initialised Secrets Manager client."""
    global _client  # noqa: PLW0603
    if _client is None:
        _client = boto3.client("secretsmanager")
    return _client


def _env_var_name(secret_name: str) -> str:
    """Derive an environment variable name from a secret name.

    Examples:
        "regain/onet-api-key"     -> "ONET_API_KEY"
        "regain/usajobs-api-key"  -> "USAJOBS_API_KEY"
    """
    # Take the last segment after '/', replace hyphens with underscores, uppercase
    key = secret_name.rsplit("/", 1)[-1]
    return key.replace("-", "_").upper()


def get_secret(secret_name: str) -> str:
    """Retrieve a secret value with caching and env var fallback.

    Args:
        secret_name: Full Secrets Manager secret name (e.g. "regain/onet-api-key").

    Returns:
        The secret string value.

    Raises:
        ValueError: If the secret cannot be resolved from any source.
    """
    # 1. Check cache
    now = time.time()
    if secret_name in _cache:
        value, expires_at = _cache[secret_name]
        if now < expires_at:
            return value

    # 2. Try Secrets Manager
    try:
        client = _get_client()
        response = client.get_secret_value(SecretId=secret_name)
        value = response["SecretString"]
        _cache[secret_name] = (value, now + _CACHE_TTL_SECONDS)
        return value
    except Exception:
        logger.warning(
            "Failed to fetch secret '%s' from Secrets Manager, "
            "falling back to environment variable",
            secret_name,
        )

    # 3. Fallback to environment variable (not cached — env vars may change)
    env_key = _env_var_name(secret_name)
    value = os.environ.get(env_key, "")
    if value:
        return value

    raise ValueError(
        f"Secret '{secret_name}' not found in Secrets Manager or "
        f"environment variable '{env_key}'"
    )
