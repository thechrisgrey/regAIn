"""O*NET API v2 proxy service.

Proxies requests to the O*NET Web Services API v2 using stdlib urllib.
Credentials are fetched from SSM Parameter Store (SecureString) at runtime
and cached for the lifetime of the Lambda container.
"""

import json
import logging
import urllib.request
import urllib.parse
from typing import Any, Dict

import boto3

logger = logging.getLogger(__name__)

ONET_BASE_URL = "https://api-v2.onetcenter.org/mnm"

# Module-level cache — survives across invocations in the same container
_cached_api_key: str | None = None


def _get_api_key() -> str:
    """Fetch O*NET API key from SSM Parameter Store (cached)."""
    global _cached_api_key
    if _cached_api_key is not None:
        return _cached_api_key

    ssm = boto3.client("ssm")
    _cached_api_key = ssm.get_parameter(
        Name="/regain/onet/api-key", WithDecryption=True
    )["Parameter"]["Value"]
    return _cached_api_key


def _onet_request(path: str) -> Dict[str, Any]:
    """Make an authenticated GET request to the O*NET v2 API.

    Args:
        path: URL path relative to the base (e.g. "/search?keyword=nurse").

    Returns:
        Parsed JSON response.
    """
    url = f"{ONET_BASE_URL}{path}"
    req = urllib.request.Request(
        url,
        headers={
            "X-API-Key": _get_api_key(),
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:  # nosec B310
        return json.loads(resp.read().decode())


def search_careers(keyword: str) -> Dict[str, Any]:
    """Search O*NET careers by keyword.

    Args:
        keyword: Search term (e.g. "software engineer").

    Returns:
        Search results from the O*NET API.
    """
    encoded = urllib.parse.quote(keyword, safe="")
    return _onet_request(f"/search?keyword={encoded}")


def get_career_detail(soc_code: str) -> Dict[str, Any]:
    """Get full career detail by fetching the overview + all section endpoints.

    The v2 API has separate endpoints per section. We fetch them in parallel
    (via sequential calls for simplicity in Lambda) and merge into one response.

    Args:
        soc_code: O*NET SOC code (e.g. "15-1252.00").

    Returns:
        Merged career report with all sections.
    """
    encoded = urllib.parse.quote(soc_code, safe="")
    base = f"/careers/{encoded}"

    # Fetch overview (code, title, tags, what_they_do, on_the_job)
    overview = _onet_request(f"{base}/")

    # Fetch each section
    sections = ["knowledge", "skills", "abilities", "personality",
                "technology", "education", "job_outlook",
                "check_out_my_state", "explore_more"]

    for section in sections:
        try:
            overview[section] = _onet_request(f"{base}/{section}")
        except Exception:
            logger.warning("Failed to fetch section %s for %s", section, soc_code)
            overview[section] = None

    return overview
