"""O*NET API proxy service.

Proxies requests to the O*NET My Next Move API using stdlib urllib.
Credentials are fetched from SSM Parameter Store (SecureString) at runtime
and cached for the lifetime of the Lambda container.
"""

import base64
import json
import logging
import urllib.request
import urllib.parse
from typing import Any, Dict

import boto3

logger = logging.getLogger(__name__)

ONET_BASE_URL = "https://services.onetcenter.org/ws/mnm"

# Module-level cache — survives across invocations in the same container
_cached_credentials: Dict[str, str] | None = None


def _get_credentials() -> Dict[str, str]:
    """Fetch O*NET credentials from SSM Parameter Store (cached)."""
    global _cached_credentials
    if _cached_credentials is not None:
        return _cached_credentials

    ssm = boto3.client("ssm")
    username = ssm.get_parameter(
        Name="/regain/onet/username", WithDecryption=True
    )["Parameter"]["Value"]
    password = ssm.get_parameter(
        Name="/regain/onet/password", WithDecryption=True
    )["Parameter"]["Value"]

    _cached_credentials = {"username": username, "password": password}
    return _cached_credentials


def _auth_header() -> str:
    """Build HTTP Basic auth header from SSM credentials."""
    creds = _get_credentials()
    encoded = base64.b64encode(
        f"{creds['username']}:{creds['password']}".encode()
    ).decode()
    return f"Basic {encoded}"


def _onet_request(path: str) -> Dict[str, Any]:
    """Make an authenticated GET request to the O*NET API.

    Args:
        path: URL path relative to the base (e.g. "/search?keyword=nurse").

    Returns:
        Parsed JSON response.
    """
    url = f"{ONET_BASE_URL}{path}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": _auth_header(),
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
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
    """Get full career report for a SOC code.

    Args:
        soc_code: O*NET SOC code (e.g. "15-1252.00").

    Returns:
        Full career report with all 13 sections.
    """
    encoded = urllib.parse.quote(soc_code, safe="")
    return _onet_request(f"/careers/{encoded}/report")
