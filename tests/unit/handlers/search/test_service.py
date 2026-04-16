"""Unit tests for the Tavily web-search service layer."""
from __future__ import annotations

import json
import urllib.error
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest


class TestTavilySearch:
    """Exercise backend.handlers.search.service.search()."""

    def _fake_response(self, body: dict, status: int = 200):
        resp = MagicMock()
        resp.read.return_value = json.dumps(body).encode("utf-8")
        resp.status = status
        resp.__enter__ = lambda self_: self_
        resp.__exit__ = lambda self_, *_: None
        return resp

    @patch("backend.handlers.search.service._load_api_key", return_value="tvly-test")
    @patch("backend.handlers.search.service.urllib.request.urlopen")
    def test_search_returns_normalized_results(self, mock_open, _mock_key):
        from backend.handlers.search import service

        mock_open.return_value = self._fake_response({
            "answer": "AI jobs are booming.",
            "results": [
                {
                    "title": "The rise of AI roles",
                    "url": "https://example.com/ai",
                    "content": "Demand is up 40%.",
                    "published_date": "2026-04-01",
                    "score": 0.95,
                }
            ],
        })

        out = service.search("AI job trends", max_results=3, topic="news")

        assert out["answer"] == "AI jobs are booming."
        assert len(out["results"]) == 1
        assert out["results"][0]["url"] == "https://example.com/ai"
        assert out["results"][0]["snippet"] == "Demand is up 40%."
        assert out["results"][0]["published_date"] == "2026-04-01"

    @patch("backend.handlers.search.service._load_api_key", return_value="tvly-test")
    @patch("backend.handlers.search.service.urllib.request.urlopen")
    def test_search_raises_httperror_on_4xx(self, mock_open, _mock_key):
        from backend.handlers.search import service

        mock_open.side_effect = urllib.error.HTTPError(
            url="https://api.tavily.com/search",
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=BytesIO(b""),
        )

        with pytest.raises(urllib.error.HTTPError) as exc:
            service.search("anything")
        assert exc.value.code == 401

    @patch("backend.handlers.search.service._load_api_key", return_value="tvly-test")
    @patch("backend.handlers.search.service.urllib.request.urlopen")
    def test_search_sends_correct_body(self, mock_open, _mock_key):
        from backend.handlers.search import service

        mock_open.return_value = self._fake_response({"results": []})

        service.search("AWS Lambda pricing", max_results=7, topic="general")

        call_args = mock_open.call_args
        req = call_args[0][0]
        body = json.loads(req.data.decode("utf-8"))
        assert body["api_key"] == "tvly-test"
        assert body["query"] == "AWS Lambda pricing"
        assert body["max_results"] == 7
        assert body["topic"] == "general"
        assert body["include_answer"] is True

    def test_search_validates_max_results_bounds(self):
        from backend.handlers.search import service

        with pytest.raises(ValueError):
            service.search("q", max_results=0)
        with pytest.raises(ValueError):
            service.search("q", max_results=11)

    def test_search_rejects_empty_query(self):
        from backend.handlers.search import service
        with pytest.raises(ValueError):
            service.search("")


class TestApiKeyLoader:
    @patch("backend.handlers.search.service.boto3.client")
    def test_load_api_key_calls_ssm_with_decryption(self, mock_client):
        from backend.handlers.search import service
        service._api_key_cache = None

        ssm = MagicMock()
        ssm.get_parameter.return_value = {"Parameter": {"Value": "tvly-secret"}}
        mock_client.return_value = ssm

        key = service._load_api_key()

        ssm.get_parameter.assert_called_once_with(
            Name="/regain/search/tavily-api-key", WithDecryption=True
        )
        assert key == "tvly-secret"

    @patch("backend.handlers.search.service.boto3.client")
    def test_load_api_key_is_cached(self, mock_client):
        from backend.handlers.search import service
        service._api_key_cache = None

        ssm = MagicMock()
        ssm.get_parameter.return_value = {"Parameter": {"Value": "tvly-secret"}}
        mock_client.return_value = ssm

        service._load_api_key()
        service._load_api_key()

        assert ssm.get_parameter.call_count == 1
