"""Cognito JWT signature verification.

Verifies JWT tokens against the Cognito JWKS endpoint with RS256
signature validation, expiry check, issuer check, and token_use check.
JWKS keys are cached in-memory with a 5-minute TTL for Lambda reuse.
"""

import json
import logging
import os
import time
import urllib.request
from typing import Optional

logger = logging.getLogger(__name__)

# Module-level JWKS cache for Lambda container reuse.
_jwks_cache: dict = {}
_jwks_cache_time: float = 0.0
_JWKS_CACHE_TTL = 300  # 5 minutes


def _get_jwks_url() -> str:
    """Build the JWKS URL from environment variables."""
    region = os.environ.get("AWS_REGION_NAME", os.environ.get("AWS_REGION", "us-east-1"))
    pool_id = os.environ.get("USER_POOL_ID", "")
    if not pool_id:
        raise ValueError("USER_POOL_ID environment variable not set")
    return f"https://cognito-idp.{region}.amazonaws.com/{pool_id}/.well-known/jwks.json"


def _get_jwks() -> dict:
    """Fetch and cache the Cognito JWKS keys."""
    global _jwks_cache, _jwks_cache_time

    now = time.time()
    if _jwks_cache and (now - _jwks_cache_time) < _JWKS_CACHE_TTL:
        return _jwks_cache

    url = _get_jwks_url()
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            _jwks_cache = json.loads(resp.read().decode("utf-8"))
            _jwks_cache_time = now
    except Exception:
        logger.exception("Failed to fetch JWKS from %s", url)
        if _jwks_cache:
            return _jwks_cache
        raise

    return _jwks_cache


def _get_signing_key(token: str) -> "jwt.algorithms.RSAAlgorithm":
    """Find the matching RSA public key for the token's kid header."""
    import jwt

    headers = jwt.get_unverified_header(token)
    kid = headers.get("kid")
    if not kid:
        raise jwt.InvalidTokenError("Token missing kid header")

    jwks = _get_jwks()
    for key_data in jwks.get("keys", []):
        if key_data.get("kid") == kid:
            return jwt.algorithms.RSAAlgorithm.from_jwk(key_data)

    raise jwt.InvalidTokenError(f"No matching key found for kid: {kid}")


def verify_cognito_token(token: str) -> Optional[str]:
    """Verify a Cognito JWT token signature and return the user ID.

    Performs full RS256 signature verification against the Cognito JWKS
    endpoint, checks expiry, issuer, and token_use claims.

    Args:
        token: The raw JWT token string.

    Returns:
        The user_id (sub claim) on success, None on any failure.
    """
    if not token:
        return None

    try:
        import jwt as pyjwt

        region = os.environ.get("AWS_REGION_NAME", os.environ.get("AWS_REGION", "us-east-1"))
        pool_id = os.environ.get("USER_POOL_ID", "")
        if not pool_id:
            logger.error("USER_POOL_ID not set; cannot verify token")
            return None

        issuer = f"https://cognito-idp.{region}.amazonaws.com/{pool_id}"
        public_key = _get_signing_key(token)

        decoded = pyjwt.decode(
            token,
            key=public_key,
            algorithms=["RS256"],
            issuer=issuer,
            options={
                "verify_exp": True,
                "verify_iss": True,
                "verify_aud": False,  # Cognito id tokens use client_id, not aud
            },
        )

        # Verify token_use is "id" (not "access")
        if decoded.get("token_use") != "id":
            logger.warning("Token has unexpected token_use: %s", decoded.get("token_use"))
            return None

        user_id = decoded.get("sub")
        return user_id if user_id else None

    except Exception:
        logger.warning("Token verification failed", exc_info=True)
        return None
