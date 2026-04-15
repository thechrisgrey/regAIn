"""Unit tests for the O*NET coaching agent tools.

Tests validation, happy paths, and error mapping for onet_search_careers
and onet_career_detail. The @tool decorator from strands is stubbed since
strands-agents is not installed in the unit test environment.
All O*NET HTTP traffic is mocked at the service boundary.
"""

import importlib
import sys
import types
import urllib.error
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Stub strands so tools.py can be imported without strands-agents installed
# ---------------------------------------------------------------------------
_strands_stub = types.ModuleType("strands")
_strands_stub.tool = lambda fn: fn
sys.modules.setdefault("strands", _strands_stub)


def _load_tools():
    """Import tools module fresh so we control its module-level state."""
    mod_name = "backend.agents.coaching.tools"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    return importlib.import_module(mod_name)


class TestOnetSearchCareers:
    """Tests for onet_search_careers."""

    def test_happy_path_returns_service_payload(self) -> None:
        """A valid keyword returns whatever service.search_careers returns."""
        tools = _load_tools()
        fake_payload = {
            "career": [
                {"code": "15-1252.00", "title": "Software Developers"},
                {"code": "15-1251.00", "title": "Computer Programmers"},
            ],
            "start": 1,
            "end": 2,
        }
        with patch(
            "backend.handlers.onet.service.search_careers",
            return_value=fake_payload,
        ) as mock_search:
            result = tools.onet_search_careers("software engineer")

        assert result == fake_payload
        mock_search.assert_called_once_with("software engineer")

    def test_rejects_empty_keyword(self) -> None:
        """Empty string returns validation error without calling service."""
        tools = _load_tools()
        with patch("backend.handlers.onet.service.search_careers") as mock_search:
            result = tools.onet_search_careers("")

        assert result["error_kind"] == tools.ERR_VALIDATION
        mock_search.assert_not_called()

    def test_rejects_whitespace_keyword(self) -> None:
        """Whitespace-only keyword returns validation error."""
        tools = _load_tools()
        with patch("backend.handlers.onet.service.search_careers") as mock_search:
            result = tools.onet_search_careers("   \t\n  ")

        assert result["error_kind"] == tools.ERR_VALIDATION
        mock_search.assert_not_called()

    def test_strips_whitespace_before_calling_service(self) -> None:
        """Leading/trailing whitespace is stripped before delegation."""
        tools = _load_tools()
        with patch(
            "backend.handlers.onet.service.search_careers",
            return_value={"career": []},
        ) as mock_search:
            tools.onet_search_careers("  nurse  ")
        mock_search.assert_called_once_with("nurse")

    def test_404_maps_to_not_found(self) -> None:
        """HTTP 404 from O*NET maps to ERR_NOT_FOUND."""
        tools = _load_tools()
        err = urllib.error.HTTPError(
            url="u", code=404, msg="Not Found", hdrs=None, fp=None
        )
        with patch(
            "backend.handlers.onet.service.search_careers", side_effect=err
        ):
            result = tools.onet_search_careers("nonsense")
        assert result["error_kind"] == tools.ERR_NOT_FOUND

    def test_4xx_maps_to_permanent(self) -> None:
        """Non-404 4xx from O*NET maps to ERR_PERMANENT."""
        tools = _load_tools()
        err = urllib.error.HTTPError(
            url="u", code=403, msg="Forbidden", hdrs=None, fp=None
        )
        with patch(
            "backend.handlers.onet.service.search_careers", side_effect=err
        ):
            result = tools.onet_search_careers("nurse")
        assert result["error_kind"] == tools.ERR_PERMANENT

    def test_5xx_maps_to_transient(self) -> None:
        """5xx from O*NET maps to ERR_TRANSIENT."""
        tools = _load_tools()
        err = urllib.error.HTTPError(
            url="u", code=502, msg="Bad Gateway", hdrs=None, fp=None
        )
        with patch(
            "backend.handlers.onet.service.search_careers", side_effect=err
        ):
            result = tools.onet_search_careers("nurse")
        assert result["error_kind"] == tools.ERR_TRANSIENT

    def test_network_error_maps_to_transient(self) -> None:
        """URLError (DNS, connection refused, timeout) maps to ERR_TRANSIENT."""
        tools = _load_tools()
        with patch(
            "backend.handlers.onet.service.search_careers",
            side_effect=urllib.error.URLError("connection refused"),
        ):
            result = tools.onet_search_careers("nurse")
        assert result["error_kind"] == tools.ERR_TRANSIENT
