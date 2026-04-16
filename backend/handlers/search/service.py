"""Tavily web-search client for the REGAIN Coaching Agent.

Mirrors backend/handlers/onet/service.py: stdlib urllib, SSM-stored API
key, module-level key cache. Called from the `web_search` @tool in
backend/agents/coaching/tools.py.
"""
from __future__ import annotations

import json
import logging
import urllib.request
from typing import Any

import boto3

logger = logging.getLogger(__name__)

TAVILY_URL = "https://api.tavily.com/search"
SSM_PARAM_NAME = "/regain/search/tavily-api-key"
REQUEST_TIMEOUT_SECONDS = 8

_api_key_cache: str | None = None


def _load_api_key() -> str:
    global _api_key_cache
    if _api_key_cache is not None:
        return _api_key_cache
    ssm = boto3.client("ssm")
    resp = ssm.get_parameter(Name=SSM_PARAM_NAME, WithDecryption=True)
    _api_key_cache = resp["Parameter"]["Value"]
    return _api_key_cache


def search(query: str, max_results: int = 5, topic: str = "general") -> dict[str, Any]:
    """Call Tavily search and return a normalized response dict.

    Args:
        query: Non-empty search string.
        max_results: 1-10.
        topic: "general" or "news".

    Returns:
        {"answer": str | None, "results": [{"title", "url", "snippet",
        "published_date", "score"}, ...]}

    Raises:
        ValueError: invalid arguments.
        urllib.error.HTTPError / URLError: network or API errors.
    """
    if not query or not query.strip():
        raise ValueError("query must be a non-empty string")
    if not 1 <= max_results <= 10:
        raise ValueError("max_results must be between 1 and 10")
    if topic not in ("general", "news"):
        raise ValueError("topic must be 'general' or 'news'")

    payload = {
        "api_key": _load_api_key(),
        "query": query.strip(),
        "max_results": max_results,
        "topic": topic,
        "search_depth": "basic",
        "include_answer": True,
        "include_raw_content": False,
        "include_images": False,
    }

    req = urllib.request.Request(
        TAVILY_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
        raw = json.loads(resp.read().decode("utf-8"))

    results = [
        {
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "snippet": r.get("content", ""),
            "published_date": r.get("published_date"),
            "score": r.get("score"),
        }
        for r in raw.get("results", [])
    ]

    return {
        "answer": raw.get("answer"),
        "results": results,
    }
