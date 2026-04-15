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
