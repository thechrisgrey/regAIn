# O*NET Agent Tool Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable the REGAIN coaching agent to query the O*NET career database via two new Strands `@tool` functions, grounding career advice in authoritative government data.

**Architecture:** Add two thin `@tool` wrappers (`onet_search_careers`, `onet_career_detail`) in `backend/agents/coaching/tools.py` that delegate to the existing `backend/handlers/onet/service.py`. Register them with the coaching agent. Extend the system prompt with an O*NET section including the user's target role. Grant `ssm:GetParameter` on `/regain/onet/*` to all three agent Lambdas.

**Tech Stack:** Python 3.12, Strands Agents SDK, AWS Lambda, boto3/SSM, urllib (stdlib, used by O*NET service), pytest, moto, AWS CDK (Python).

**Spec:** `docs/superpowers/specs/2026-04-14-onet-agent-tools-design.md`

---

## File Structure

### Files to create
- `tests/unit/agents/coaching/test_onet_tools.py` — unit tests for the two new tools (validation, happy path, error mapping)

### Files to modify
- `backend/agents/coaching/tools.py` — add `onet_search_careers`, `onet_career_detail`, and an allowlist constant
- `backend/agents/coaching/prompts.py` — add `target_role` parameter and O*NET section
- `backend/agents/coaching/agent.py` — pass target_role to `get_system_prompt()`; include new tools in `_get_direct_tools()`
- `backend/handlers/coaching/voice_handler.py` — pass target_role to `get_system_prompt()`
- `infra/stacks/agent_stack.py` — add `_onet_ssm_policy()` helper; attach to voice, chat_stream, and coaching Lambdas
- `tests/unit/agents/coaching/test_prompts.py` — add test for `target_role` interpolation

---

## Task 1: Define valid sections allowlist

**Files:**
- Modify: `backend/agents/coaching/tools.py`

- [ ] **Step 1: Add the allowlist constant**

Open `backend/agents/coaching/tools.py`. Find the typed error constants near the top (around line 38-44, the lines defining `ERR_NOT_FOUND`, `ERR_TRANSIENT`, etc.). Add the allowlist immediately after them:

```python
# Typed error kind constants for structured tool error responses.
# These allow the LLM to reason about retry-ability and error handling.
ERR_NOT_FOUND = "not_found"
ERR_TRANSIENT = "transient"
ERR_PERMANENT = "permanent"
ERR_RATE_LIMITED = "rate_limited"
ERR_VALIDATION = "validation"

# O*NET v2 section names recognised by onet_career_detail.
# Mirrors the sections in backend/handlers/onet/service.py::get_career_detail.
ONET_VALID_SECTIONS = frozenset({
    "knowledge",
    "skills",
    "abilities",
    "personality",
    "technology",
    "education",
    "job_outlook",
    "check_out_my_state",
    "explore_more",
})

# SOC code pattern: e.g. "15-1252.00"
import re as _re  # local alias to avoid polluting module namespace
_ONET_SOC_PATTERN = _re.compile(r"^\d{2}-\d{4}\.\d{2}$")
```

- [ ] **Step 2: Verify the file still imports**

Run: `.venv/bin/python -c "import backend.agents.coaching.tools"`
Expected: no output, exit code 0.

- [ ] **Step 3: Commit**

```bash
git add backend/agents/coaching/tools.py
git commit -m "feat(agent): add O*NET section allowlist and SOC regex"
```

---

## Task 2: Write failing test for `onet_search_careers` happy path

**Files:**
- Create: `tests/unit/agents/coaching/test_onet_tools.py`

- [ ] **Step 1: Create the test file with the strands stub pattern**

Create `tests/unit/agents/coaching/test_onet_tools.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/pytest tests/unit/agents/coaching/test_onet_tools.py::TestOnetSearchCareers::test_happy_path_returns_service_payload -v`
Expected: FAIL with `AttributeError: module ... has no attribute 'onet_search_careers'`.

---

## Task 3: Implement `onet_search_careers`

**Files:**
- Modify: `backend/agents/coaching/tools.py`

- [ ] **Step 1: Add the tool at the end of the file**

Append to `backend/agents/coaching/tools.py` (after the last existing `@tool` function, before any trailing whitespace):

```python
# ---------------------------------------------------------------------------
# O*NET career data tools
# ---------------------------------------------------------------------------


@tool
def onet_search_careers(keyword: str) -> dict[str, Any]:
    """Search O*NET for careers matching a keyword.

    Use this when you need to find the O*NET SOC code for a role the user
    mentions (e.g. "software engineer", "nurse"). Returns candidate careers
    with SOC codes and titles. Follow up with onet_career_detail to pull
    rich data for a specific career.

    Args:
        keyword: Free-text role or occupation query.

    Returns:
        Raw O*NET search response dict with a "career" list, or an error
        dict with ``error_kind``.
    """
    if not keyword or not keyword.strip():
        return {
            "error": "invalid_keyword",
            "error_kind": ERR_VALIDATION,
            "message": "keyword must be a non-empty string.",
        }

    from backend.handlers.onet import service as _onet_service  # lazy import

    try:
        return _onet_service.search_careers(keyword.strip())
    except urllib.error.HTTPError as exc:
        kind = ERR_NOT_FOUND if exc.code == 404 else (
            ERR_PERMANENT if 400 <= exc.code < 500 else ERR_TRANSIENT
        )
        return {
            "error": "onet_http_error",
            "error_kind": kind,
            "message": f"O*NET API returned HTTP {exc.code}.",
        }
    except urllib.error.URLError as exc:
        return {
            "error": "onet_network_error",
            "error_kind": ERR_TRANSIENT,
            "message": f"Could not reach O*NET: {exc.reason}",
        }
    except Exception as exc:
        logger.exception("onet_search_careers failed")
        return {
            "error": "onet_unknown",
            "error_kind": ERR_TRANSIENT,
            "message": str(exc),
        }
```

Also add the `urllib.error` stdlib import at the top of the file. Find the existing stdlib import block in `backend/agents/coaching/tools.py` (the lines starting with `import dataclasses` through `from typing import Any`), and add `import urllib.error` after the other `import` statements in that block:

```python
import dataclasses
import importlib
import json
import logging
import os
import urllib.error
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any
```

- [ ] **Step 2: Run the test to verify it passes**

Run: `.venv/bin/pytest tests/unit/agents/coaching/test_onet_tools.py::TestOnetSearchCareers::test_happy_path_returns_service_payload -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/agents/coaching/tools.py tests/unit/agents/coaching/test_onet_tools.py
git commit -m "feat(agent): add onet_search_careers tool"
```

---

## Task 4: Add validation and error mapping tests for `onet_search_careers`

**Files:**
- Modify: `tests/unit/agents/coaching/test_onet_tools.py`

- [ ] **Step 1: Append validation and error tests**

Add to the `TestOnetSearchCareers` class in `tests/unit/agents/coaching/test_onet_tools.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify all pass**

Run: `.venv/bin/pytest tests/unit/agents/coaching/test_onet_tools.py::TestOnetSearchCareers -v`
Expected: 8 passed (1 from Task 2 + 7 new ones added above).

- [ ] **Step 3: Commit**

```bash
git add tests/unit/agents/coaching/test_onet_tools.py
git commit -m "test(agent): cover onet_search_careers validation and error mapping"
```

---

## Task 5: Write failing test for `onet_career_detail` happy path

**Files:**
- Modify: `tests/unit/agents/coaching/test_onet_tools.py`

- [ ] **Step 1: Append a new test class**

Add to `tests/unit/agents/coaching/test_onet_tools.py`:

```python
class TestOnetCareerDetail:
    """Tests for onet_career_detail."""

    def test_happy_path_returns_overview_plus_requested_sections(self) -> None:
        """Overview is always included; only requested sections are fetched."""
        tools = _load_tools()
        # Fake _onet_request: dispatch by path
        def fake_request(path: str):
            if path == "/careers/15-1252.00/":
                return {"code": "15-1252.00", "title": "Software Developers",
                        "what_they_do": "Write code.", "on_the_job": {}}
            if path == "/careers/15-1252.00/skills":
                return {"element": [{"name": "Programming"}]}
            if path == "/careers/15-1252.00/job_outlook":
                return {"outlook": {"category": "Bright"}}
            raise AssertionError(f"Unexpected path: {path}")

        with patch(
            "backend.handlers.onet.service._onet_request",
            side_effect=fake_request,
        ):
            result = tools.onet_career_detail(
                "15-1252.00", ["skills", "job_outlook"]
            )

        assert result["code"] == "15-1252.00"
        assert result["title"] == "Software Developers"
        assert result["skills"] == {"element": [{"name": "Programming"}]}
        assert result["job_outlook"] == {"outlook": {"category": "Bright"}}
        # Unrequested sections must NOT be present
        assert "knowledge" not in result
        assert "abilities" not in result
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/pytest tests/unit/agents/coaching/test_onet_tools.py::TestOnetCareerDetail::test_happy_path_returns_overview_plus_requested_sections -v`
Expected: FAIL with `AttributeError: module ... has no attribute 'onet_career_detail'`.

---

## Task 6: Implement `onet_career_detail`

**Files:**
- Modify: `backend/agents/coaching/tools.py`

- [ ] **Step 1: Add the tool immediately after `onet_search_careers`**

Append to `backend/agents/coaching/tools.py` (after `onet_search_careers`):

```python
@tool
def onet_career_detail(soc_code: str, sections: list[str]) -> dict[str, Any]:
    """Fetch authoritative O*NET data for a specific career.

    ``sections`` is REQUIRED — pick only what you need to avoid bloating
    context. Valid sections: "knowledge", "skills", "abilities",
    "personality", "technology", "education", "job_outlook",
    "check_out_my_state", "explore_more". The overview (code, title,
    what_they_do, on_the_job) is always included.

    Args:
        soc_code: O*NET SOC code like "15-1252.00" (obtain via onet_search_careers).
        sections: Explicit non-empty list of section names from the list above.

    Returns:
        Dict with overview fields plus one key per requested section, or
        an error dict with ``error_kind``.
    """
    if not soc_code or not _ONET_SOC_PATTERN.match(soc_code.strip()):
        return {
            "error": "invalid_soc_code",
            "error_kind": ERR_VALIDATION,
            "message": (
                "soc_code must match the pattern '##-####.##' "
                "(e.g. '15-1252.00')."
            ),
        }

    if not sections or not isinstance(sections, list):
        return {
            "error": "missing_sections",
            "error_kind": ERR_VALIDATION,
            "message": (
                "sections must be a non-empty list. Valid names: "
                + ", ".join(sorted(ONET_VALID_SECTIONS))
            ),
        }

    unknown = [s for s in sections if s not in ONET_VALID_SECTIONS]
    if unknown:
        return {
            "error": "unknown_section",
            "error_kind": ERR_VALIDATION,
            "message": (
                f"Unknown section(s): {unknown}. Valid names: "
                + ", ".join(sorted(ONET_VALID_SECTIONS))
            ),
        }

    from backend.handlers.onet import service as _onet_service  # lazy import

    code = soc_code.strip()
    try:
        base_path = f"/careers/{code}"
        result = dict(_onet_service._onet_request(f"{base_path}/"))
        for section in sections:
            try:
                result[section] = _onet_service._onet_request(
                    f"{base_path}/{section}"
                )
            except urllib.error.HTTPError as exc:
                logger.warning(
                    "onet_career_detail: section %s HTTP %s for %s",
                    section, exc.code, code,
                )
                result[section] = None
        return result
    except urllib.error.HTTPError as exc:
        kind = ERR_NOT_FOUND if exc.code == 404 else (
            ERR_PERMANENT if 400 <= exc.code < 500 else ERR_TRANSIENT
        )
        return {
            "error": "onet_http_error",
            "error_kind": kind,
            "message": f"O*NET API returned HTTP {exc.code} for {code}.",
        }
    except urllib.error.URLError as exc:
        return {
            "error": "onet_network_error",
            "error_kind": ERR_TRANSIENT,
            "message": f"Could not reach O*NET: {exc.reason}",
        }
    except Exception as exc:
        logger.exception("onet_career_detail failed")
        return {
            "error": "onet_unknown",
            "error_kind": ERR_TRANSIENT,
            "message": str(exc),
        }
```

- [ ] **Step 2: Run the test to verify it passes**

Run: `.venv/bin/pytest tests/unit/agents/coaching/test_onet_tools.py::TestOnetCareerDetail::test_happy_path_returns_overview_plus_requested_sections -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/agents/coaching/tools.py tests/unit/agents/coaching/test_onet_tools.py
git commit -m "feat(agent): add onet_career_detail tool with section filtering"
```

---

## Task 7: Add validation and error tests for `onet_career_detail`

**Files:**
- Modify: `tests/unit/agents/coaching/test_onet_tools.py`

- [ ] **Step 1: Append validation tests**

Add to the `TestOnetCareerDetail` class in `tests/unit/agents/coaching/test_onet_tools.py`:

```python
    @pytest.mark.parametrize("bad_soc", ["", "15-1252", "abc", "1-1.0", None])
    def test_rejects_invalid_soc(self, bad_soc) -> None:
        """Invalid SOC format returns ERR_VALIDATION without HTTP calls."""
        tools = _load_tools()
        with patch("backend.handlers.onet.service._onet_request") as mock_req:
            result = tools.onet_career_detail(bad_soc, ["skills"])
        assert result["error_kind"] == tools.ERR_VALIDATION
        mock_req.assert_not_called()

    def test_rejects_empty_sections(self) -> None:
        """Empty sections list returns ERR_VALIDATION."""
        tools = _load_tools()
        with patch("backend.handlers.onet.service._onet_request") as mock_req:
            result = tools.onet_career_detail("15-1252.00", [])
        assert result["error_kind"] == tools.ERR_VALIDATION
        mock_req.assert_not_called()

    def test_rejects_non_list_sections(self) -> None:
        """Passing a string instead of a list returns ERR_VALIDATION."""
        tools = _load_tools()
        with patch("backend.handlers.onet.service._onet_request") as mock_req:
            result = tools.onet_career_detail("15-1252.00", "skills")  # type: ignore[arg-type]
        assert result["error_kind"] == tools.ERR_VALIDATION
        mock_req.assert_not_called()

    def test_rejects_unknown_section(self) -> None:
        """Unknown section names are rejected with ERR_VALIDATION."""
        tools = _load_tools()
        with patch("backend.handlers.onet.service._onet_request") as mock_req:
            result = tools.onet_career_detail(
                "15-1252.00", ["skills", "bogus_section"]
            )
        assert result["error_kind"] == tools.ERR_VALIDATION
        assert "bogus_section" in result["message"]
        mock_req.assert_not_called()

    def test_404_on_overview_maps_to_not_found(self) -> None:
        """HTTP 404 on overview fetch maps to ERR_NOT_FOUND."""
        tools = _load_tools()
        err = urllib.error.HTTPError(
            url="u", code=404, msg="Not Found", hdrs=None, fp=None
        )
        with patch(
            "backend.handlers.onet.service._onet_request", side_effect=err
        ):
            result = tools.onet_career_detail("99-9999.99", ["skills"])
        assert result["error_kind"] == tools.ERR_NOT_FOUND

    def test_section_fetch_failure_returns_null_for_that_section(self) -> None:
        """If a single section fails, it's set to None; others still returned."""
        tools = _load_tools()
        def fake_request(path: str):
            if path == "/careers/15-1252.00/":
                return {"code": "15-1252.00", "title": "Software Developers"}
            if path == "/careers/15-1252.00/skills":
                return {"element": [{"name": "Programming"}]}
            if path == "/careers/15-1252.00/technology":
                raise urllib.error.HTTPError(
                    url="u", code=500, msg="Server Error", hdrs=None, fp=None
                )
            raise AssertionError(f"Unexpected path: {path}")

        with patch(
            "backend.handlers.onet.service._onet_request",
            side_effect=fake_request,
        ):
            result = tools.onet_career_detail(
                "15-1252.00", ["skills", "technology"]
            )

        assert result["skills"] == {"element": [{"name": "Programming"}]}
        assert result["technology"] is None
        assert result["code"] == "15-1252.00"
```

- [ ] **Step 2: Run all tool tests to verify all pass**

Run: `.venv/bin/pytest tests/unit/agents/coaching/test_onet_tools.py -v`
Expected: 19 passed (8 in TestOnetSearchCareers from Tasks 2+4, plus 11 in TestOnetCareerDetail — the 1 from Task 5 plus 6 test functions from Task 7 where `test_rejects_invalid_soc` contributes 5 parametrized cases).

- [ ] **Step 3: Commit**

```bash
git add tests/unit/agents/coaching/test_onet_tools.py
git commit -m "test(agent): cover onet_career_detail validation and error cases"
```

---

## Task 8: Register the new tools with the agent

**Files:**
- Modify: `backend/agents/coaching/agent.py`

- [ ] **Step 1: Add imports and registrations in `_get_direct_tools()`**

Open `backend/agents/coaching/agent.py`. Find the `_get_direct_tools()` function (around line 49-87). Update the import block and the return list to include the two new tools:

```python
def _get_direct_tools() -> list:
    """Return direct @tool functions for local invocation (lazy import)."""
    from backend.agents.coaching.tools import (
        read_user_profile,
        update_user_profile,
        get_campaign_status,
        create_campaign,
        get_current_mission,
        generate_mission,
        complete_mission,
        log_evidence,
        get_evidence_summary,
        get_market_insights,
        get_alignment,
        recall_memory,
        generate_resume,
        get_resume,
        read_calendar,
        write_calendar_entry,
        onet_search_careers,
        onet_career_detail,
    )

    return [
        read_user_profile,
        update_user_profile,
        get_campaign_status,
        create_campaign,
        get_current_mission,
        generate_mission,
        complete_mission,
        log_evidence,
        get_evidence_summary,
        get_market_insights,
        get_alignment,
        recall_memory,
        generate_resume,
        get_resume,
        read_calendar,
        write_calendar_entry,
        onet_search_careers,
        onet_career_detail,
    ]
```

- [ ] **Step 2: Verify the module imports cleanly**

Run: `.venv/bin/python -c "from backend.agents.coaching.agent import _get_direct_tools; t = _get_direct_tools(); print([x.__name__ for x in t])"`
Expected: output lists all 18 tool names ending with `onet_search_careers` and `onet_career_detail`.

- [ ] **Step 3: Commit**

```bash
git add backend/agents/coaching/agent.py
git commit -m "feat(agent): register O*NET tools with coaching agent"
```

---

## Task 9: Add failing test for `target_role` prompt interpolation

**Files:**
- Modify: `tests/unit/agents/coaching/test_prompts.py`

- [ ] **Step 1: Append a test class**

Open `tests/unit/agents/coaching/test_prompts.py`. Append at the end of the file:

```python


class TestOnetSection:
    """Tests for the O*NET career data section of the system prompt."""

    def test_prompt_mentions_onet_tools(self) -> None:
        """Prompt lists both O*NET tool names."""
        prompt = get_system_prompt(target_role="Software Engineer")
        assert "onet_search_careers" in prompt
        assert "onet_career_detail" in prompt

    def test_prompt_includes_explicit_target_role(self) -> None:
        """When target_role is provided, it appears in the prompt verbatim."""
        prompt = get_system_prompt(target_role="Registered Nurse")
        assert "Registered Nurse" in prompt

    def test_prompt_falls_back_when_target_role_missing(self) -> None:
        """When target_role is None, the prompt renders a sentinel string."""
        prompt = get_system_prompt(target_role=None)
        assert "(not yet set)" in prompt

    def test_existing_skill_tags_still_work_with_target_role(self) -> None:
        """target_role is orthogonal to skill tags — both can coexist."""
        prompt = get_system_prompt(
            valid_skill_tags=["Python Programming"],
            target_role="Data Analyst",
        )
        assert "Python Programming" in prompt
        assert "Data Analyst" in prompt
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/agents/coaching/test_prompts.py::TestOnetSection -v`
Expected: FAIL — either `TypeError: get_system_prompt() got an unexpected keyword argument 'target_role'` or missing string assertions.

---

## Task 10: Add `target_role` parameter and O*NET section to the prompt

**Files:**
- Modify: `backend/agents/coaching/prompts.py`

- [ ] **Step 1: Update the function signature and docstring**

Open `backend/agents/coaching/prompts.py`. Replace the current `def get_system_prompt(...)` signature and docstring (lines 10-26) with:

```python
def get_system_prompt(
    valid_skill_tags: list[str] | None = None,
    attention_mode: str = "explore",
    target_role: str | None = None,
) -> str:
    """Return the system prompt for the Coaching Agent.

    Args:
        valid_skill_tags: Optional curated list of canonical skill tags
            from the user's active campaign.  When provided, the agent
            is instructed to use only these tags for evidence logging.
        attention_mode: The user's current attention mode ('dnd' or 'explore').
            Default 'explore'.
        target_role: The user's current target role (from their profile).
            Interpolated into the O*NET guidance. When None or empty,
            renders as "(not yet set)".

    Returns:
        The complete system prompt string that configures the agent's
        persona, philosophy, behavioral rules, and tool usage.
    """
    target_role_display = target_role.strip() if target_role and target_role.strip() else "(not yet set)"
```

Note the new line computing `target_role_display` immediately after the docstring.

- [ ] **Step 2: Insert the O*NET section as a separate f-string concat**

The existing file builds the prompt by concatenating multiple strings (`base = """..."""` then `base += f"""..."""` for tags, error handling, and attention mode). The existing `base = """..."""` triple-quoted literal ends at approximately line 109 with `"""`.

Find the existing skill-tagging block (around line 112, starting with `# Skill tagging guidance` and `if valid_skill_tags:`). Insert a new `base += f"""..."""` block immediately BEFORE that `# Skill tagging guidance` comment:

```python
    # O*NET career data guidance
    base += f"""## O*NET Career Data

You have access to authoritative U.S. Department of Labor career data via
two tools:

- onet_search_careers(keyword) - find SOC codes for a role
- onet_career_detail(soc_code, sections) - fetch rich career data

Use these when:
- The user asks about a specific career, role, or job title
- You are advising on skills, tasks, outlook, or education for their target role
- You are grounding mission suggestions in what the role actually requires

The user's target role is: {target_role_display}

Prefer to ground career advice in O*NET data rather than general knowledge.
Pull only the sections you need (e.g. "skills" + "job_outlook" for a
progress check-in, "education" + "technology" for a learning path).

"""

    # Skill tagging guidance
    if valid_skill_tags:
        ...
```

This adds the O*NET section between the main `base` literal and the skill-tagging branch, without touching the other f-string blocks (`{attention_mode}`, `{tags_list}`).

- [ ] **Step 3: Run the new tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/agents/coaching/test_prompts.py::TestOnetSection -v`
Expected: 4 passed.

- [ ] **Step 4: Run the full prompts test file to verify no regressions**

Run: `.venv/bin/pytest tests/unit/agents/coaching/test_prompts.py -v`
Expected: all pre-existing tests still pass plus the 4 new ones.

- [ ] **Step 5: Commit**

```bash
git add backend/agents/coaching/prompts.py tests/unit/agents/coaching/test_prompts.py
git commit -m "feat(agent): add O*NET section and target_role to system prompt"
```

---

## Task 11: Wire `target_role` through the agent factory

**Files:**
- Modify: `backend/agents/coaching/agent.py`

- [ ] **Step 1: Read the user's target role and pass it to `get_system_prompt`**

Open `backend/agents/coaching/agent.py`. Find the block near line 178-185 that calls `get_valid_skill_tags` and `get_system_prompt`:

```python
        from backend.agents.coaching.tools import get_valid_skill_tags

        valid_tags = get_valid_skill_tags(user_id)
        system_prompt = get_system_prompt(
            valid_skill_tags=valid_tags,
            attention_mode=attention_mode,
        )
```

Replace with:

```python
        from backend.agents.coaching.tools import (
            get_valid_skill_tags,
            db as _tools_db,
        )

        valid_tags = get_valid_skill_tags(user_id)

        # Fetch target_role for prompt grounding. Failure is non-fatal —
        # the prompt falls back to "(not yet set)".
        target_role: str | None = None
        try:
            profile = _tools_db.get_item("user_profiles", {"userId": user_id})
            if profile:
                raw = profile.get("targetRole")
                if isinstance(raw, str) and raw.strip():
                    target_role = raw.strip()
        except Exception:
            logger.warning("Could not read targetRole for %s", user_id, exc_info=True)

        system_prompt = get_system_prompt(
            valid_skill_tags=valid_tags,
            attention_mode=attention_mode,
            target_role=target_role,
        )
```

- [ ] **Step 2: Verify the module still imports cleanly**

Run: `.venv/bin/python -c "import backend.agents.coaching.agent"`
Expected: no output, exit code 0.

- [ ] **Step 3: Commit**

```bash
git add backend/agents/coaching/agent.py
git commit -m "feat(agent): pass user targetRole to coaching system prompt"
```

---

## Task 12: Wire `target_role` through the voice handler

**Files:**
- Modify: `backend/handlers/coaching/voice_handler.py`

- [ ] **Step 1: Update `_get_system_prompt` to include target_role**

Open `backend/handlers/coaching/voice_handler.py`. Find `_get_system_prompt` around line 131-136:

```python
def _get_system_prompt(user_id: str) -> str:
    from backend.agents.coaching.prompts import get_system_prompt
    from backend.agents.coaching.tools import get_valid_skill_tags
    valid_tags = get_valid_skill_tags(user_id)
    return get_system_prompt(valid_skill_tags=valid_tags or None)
```

Replace with:

```python
def _get_system_prompt(user_id: str) -> str:
    from backend.agents.coaching.prompts import get_system_prompt
    from backend.agents.coaching.tools import get_valid_skill_tags, db as _tools_db

    valid_tags = get_valid_skill_tags(user_id)

    target_role: str | None = None
    try:
        profile = _tools_db.get_item("user_profiles", {"userId": user_id})
        if profile:
            raw = profile.get("targetRole")
            if isinstance(raw, str) and raw.strip():
                target_role = raw.strip()
    except Exception:
        logger.warning("Could not read targetRole for %s", user_id, exc_info=True)

    return get_system_prompt(
        valid_skill_tags=valid_tags or None,
        target_role=target_role,
    )
```

Note: This file already imports `logger` at the top; if not, confirm the existing logger name and adjust. Use whatever logger alias is already imported.

- [ ] **Step 2: Verify the module still imports cleanly**

Run: `.venv/bin/python -c "import backend.handlers.coaching.voice_handler"`
Expected: no output, exit code 0.

- [ ] **Step 3: Commit**

```bash
git add backend/handlers/coaching/voice_handler.py
git commit -m "feat(voice): pass user targetRole to coaching system prompt"
```

---

## Task 13: Add CDK IAM helper and attach to all three agent Lambdas

**Files:**
- Modify: `infra/stacks/agent_stack.py`

- [ ] **Step 1: Add the `_onet_ssm_policy` helper**

Open `infra/stacks/agent_stack.py`. Find the `_agentcore_gateway_policy` method (around line 237). Immediately after its closing (around line 253), add:

```python
    def _onet_ssm_policy(self) -> iam.PolicyStatement:
        """Create IAM policy statement for O*NET API key retrieval from SSM.

        The O*NET v2 API key is stored at /regain/onet/api-key (SecureString).
        Granted to every agent Lambda because the coaching agent's
        onet_search_careers and onet_career_detail tools lazily fetch it.
        """
        return iam.PolicyStatement(
            actions=["ssm:GetParameter"],
            resources=[
                f"arn:aws:ssm:{cdk.Aws.REGION}:{cdk.Aws.ACCOUNT_ID}:parameter/regain/onet/*"
            ],
        )
```

- [ ] **Step 2: Attach the policy in `_grant_voice_lambda_permissions`**

Find `_grant_voice_lambda_permissions` (around line 255-289). After the `self._agentcore_gateway_policy()` call (around line 259), add:

```python
        voice_lambda.add_to_role_policy(self._onet_ssm_policy())
```

- [ ] **Step 3: Attach the policy in `_upgrade_coaching_lambda_permissions`**

Find `_upgrade_coaching_lambda_permissions` (around line 291-295). After the `self._agentcore_gateway_policy()` call, add:

```python
        self.coaching_lambda.add_to_role_policy(self._onet_ssm_policy())
```

- [ ] **Step 4: Attach the policy in `_grant_chat_stream_lambda_permissions`**

Find `_grant_chat_stream_lambda_permissions` in the same file. After the existing gateway/memory policy attachments, add:

```python
        chat_stream_lambda.add_to_role_policy(self._onet_ssm_policy())
```

(The exact line number varies — search for `chat_stream_lambda.add_to_role_policy(self._agentcore_gateway_policy())` and place the new line immediately after it.)

- [ ] **Step 5: Verify IAM tests still pass**

Run (from project root): `.venv/bin/pytest tests/unit/stacks/test_iam_least_privilege.py -v -x`
Expected: all pre-existing IAM tests still pass (no new Lambdas added, no DynamoDB changes).

- [ ] **Step 6: Synth the stack to catch obvious errors**

Run: `cd infra && npx cdk synth RegainAgentStack --quiet > /dev/null`
Expected: exit code 0.

- [ ] **Step 7: Commit**

```bash
git add infra/stacks/agent_stack.py
git commit -m "infra(agent): grant ssm:GetParameter on /regain/onet/* to agent Lambdas"
```

---

## Task 14: Run full test suites

**Files:**
- none (validation only)

- [ ] **Step 1: Run the coaching agent unit tests**

Run: `.venv/bin/pytest tests/unit/agents/coaching/ -v`
Expected: all tests pass, including 13 in `test_onet_tools.py` and the updated `test_prompts.py`.

- [ ] **Step 2: Run the infra unit tests**

Run: `.venv/bin/pytest tests/unit/stacks/ -x -q`
Expected: all pass.

- [ ] **Step 3: Run the full integration suite (fast)**

Run: `.venv/bin/pytest tests/integration/ -x -q`
Expected: all pass (no coaching flow regressions).

- [ ] **Step 4: Lint the backend**

Run: `.venv/bin/ruff check backend/ tests/`
Expected: no errors (or only pre-existing errors unrelated to these changes).

---

## Task 15: Deploy and smoke-test

**Files:**
- none (deployment verification)

- [ ] **Step 1: Inspect the CDK diff**

Run:

```bash
cd infra && eval "$(AWS_PROFILE=regain aws configure export-credentials --format env)" && AWS_DEFAULT_REGION=us-east-1 npx cdk diff RegainAgentStack
```

Expected output: three new `AWS::IAM::Policy` statements for `ssm:GetParameter` on `/regain/onet/*`. No Lambda function changes. No new resources.

- [ ] **Step 2: Deploy RegainAgentStack**

Run:

```bash
cd infra && eval "$(AWS_PROFILE=regain aws configure export-credentials --format env)" && AWS_DEFAULT_REGION=us-east-1 npx cdk deploy RegainAgentStack --require-approval never
```

Expected: deploy completes successfully.

- [ ] **Step 3: Smoke-test via the chat UI**

Open the REGAIN web app, sign in as a user with a `targetRole` set, open the chat panel, and send a message like: `What skills do I need for my target role according to the Department of Labor?`

Expected behavior:
- The `AgentActivityFeed` shows `onet_search_careers` then `onet_career_detail` tool steps.
- The agent's response references specific O*NET sections (e.g. top skills, education level, outlook).
- No errors in CloudWatch logs for the coaching Lambda or chat-stream Lambda.

If the agent does not call O*NET, re-check:
- System prompt changes deployed (redeploy if needed)
- `AGENT_TRACING_ENABLED=true` for visibility

- [ ] **Step 4: Commit any final tweaks and open a PR**

If smoke tests pass without further changes, push the branch and open a PR:

```bash
git push -u origin <feature-branch-name>
gh pr create --title "feat: O*NET agent tool integration" --body "$(cat <<'EOF'
## Summary
- Adds onet_search_careers and onet_career_detail @tool functions to the coaching agent
- Adds O*NET section + target_role interpolation to the system prompt
- Grants ssm:GetParameter on /regain/onet/* to all three agent Lambdas

## Test plan
- [ ] Unit: tests/unit/agents/coaching/test_onet_tools.py (13 tests)
- [ ] Unit: tests/unit/agents/coaching/test_prompts.py (new O*NET section tests)
- [ ] Infra: cdk diff shows only 3 new SSM policy statements
- [ ] Smoke: agent calls O*NET tools when asked about target role; AgentActivityFeed shows tool steps

Spec: docs/superpowers/specs/2026-04-14-onet-agent-tools-design.md

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

Expected: PR opens with all three required status checks pending (backend, frontend, infra CI).

---

## Completion Criteria

- [ ] All 19 new unit cases in `test_onet_tools.py` pass
- [ ] All 4 new prompt tests in `test_prompts.py` pass
- [ ] Full pytest suite green
- [ ] `cdk diff RegainAgentStack` shows only 3 new SSM policy statements
- [ ] Live chat in deployed app triggers `onet_*` tool calls visible in `AgentActivityFeed`
- [ ] No CloudWatch errors on coaching Lambda / chat-stream Lambda
