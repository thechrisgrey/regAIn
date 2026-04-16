# Profile Target Role Edit — Phased Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Validate the deployed O*NET agent tools end-to-end, then ship a Profile-page UI that lets the user edit their `targetRole` directly (with atomic dual-write to `UserProfiles` + active `Campaign`).

**Architecture:** Two phases on two branches. Phase 1 is a runbook that proves the just-deployed `feat/onet-agent-tools` work renders a usable career-research loop via the coaching agent — no new code. Phase 2 is a self-contained PR on a fresh branch (`feat/profile-target-role-edit`) that adds `PATCH /profile` returning `{targetRole}`, an inline pencil-edit affordance on the Profile page, and a single DynamoDB `transact_write_items` call that updates `UserProfiles.targetRole` and the active campaign's `Campaigns.targetRole` atomically to prevent drift.

**Tech Stack:** Python 3.12 / boto3 / AWS CDK (Python) / DynamoDB TransactWriteItems / Strands Agents (Bedrock Nova Lite) / React 19 / Tailwind v4 / Vitest / pytest / hypothesis / moto.

---

## Pre-Flight

- [ ] **Step 0.1: Verify branch state**

Run: `cd /Users/cperez/Desktop/altivum-dev/regain && git status && git branch --show-current`
Expected: On branch `feat/onet-agent-tools` (Phase 1 runs against the deployed code on this branch). Working tree clean except for the untracked items already in `git status` snapshot.

- [ ] **Step 0.2: Confirm latest deploy is live**

Run: `eval "$(AWS_PROFILE=regain aws configure export-credentials --format env)" && AWS_DEFAULT_REGION=us-east-1 aws lambda get-function --function-name RegainChatStream --query 'Configuration.LastModified' --output text`
Expected: Timestamp from after the `effdcaf` deploy (the SSM IAM grant rollout). If older, redeploy `RegainAgentStack` per CLAUDE.md before continuing.

---

## Phase 1 — O*NET Validation (no code changes)

This phase is a 5-minute manual smoke test that proves the `regain_onet_search_careers` and `regain_onet_career_detail` tools work end-to-end through the coaching agent. No commits — output is a brief written record appended to this plan and pasted into the eventual PR description for traceability.

### Task 1: Confirm tools registered on the deployed agent

**Files:**
- Read-only check via CloudWatch Logs / Lambda invoke

- [ ] **Step 1.1: Tail coaching stream logs**

Run: `eval "$(AWS_PROFILE=regain aws configure export-credentials --format env)" && AWS_DEFAULT_REGION=us-east-1 aws logs tail /aws/lambda/RegainChatStream --since 1m --follow`
Expected: Logs stream live (Ctrl+C to stop after Step 1.4 confirms tools loaded).

- [ ] **Step 1.2: Open the deployed app and start a coaching session**

Open https://regain.altivum.ai in a browser, sign in, navigate to the Coaching page, send a single user turn: `What tools do you have available?`

- [ ] **Step 1.3: Verify O*NET tools are listed in the log line**

In the tailed logs, look for the `Loaded N direct tools:` log line emitted by `backend/agents/coaching/agent.py:181`. The tool list MUST contain `onet_search_careers` and `onet_career_detail`.

Expected log fragment:
```
Loaded 18 direct tools: ['read_user_profile', ..., 'onet_search_careers', 'onet_career_detail']
```

If those two names are missing, STOP — the deploy didn't pick up the new tools. Re-run `cdk deploy RegainAgentStack` (see CLAUDE.md commands) and retry.

- [ ] **Step 1.4: Stop log tail**

Press Ctrl+C in the terminal running `aws logs tail`.

### Task 2: Set targetRole via existing agent tool

The current Profile UI has no edit button (that's what Phase 2 fixes). Use `update_user_profile` — already exposed to the agent — as the only route to write `targetRole` until Phase 2 ships.

**Files:**
- Read-only — interacting via Coaching chat UI

- [ ] **Step 2.1: Send the directive to the agent**

In the Coaching page chat box, send exactly: `Please set my target role to "Senior Cloud Solutions Architect" using update_user_profile.`

- [ ] **Step 2.2: Confirm agent acknowledged the write**

Wait for the agent's reply. The `AgentActivityFeed` should show a `update_user_profile` tool step transition to "done". The reply should confirm the field was updated. If the agent paraphrases without calling the tool, send: `Run update_user_profile now with updates={"target_role": "Senior Cloud Solutions Architect"}.`

- [ ] **Step 2.3: Verify persistence in DynamoDB**

Run: `eval "$(AWS_PROFILE=regain aws configure export-credentials --format env)" && AWS_DEFAULT_REGION=us-east-1 aws dynamodb get-item --table-name RegainUserProfiles --key "{\"userId\": {\"S\": \"<your-cognito-sub>\"}}" --query 'Item.targetRole' --output text`

Replace `<your-cognito-sub>` with your Cognito user ID (visible in browser devtools: `localStorage` → look for the `CognitoIdentityServiceProvider...idToken` payload, decode JWT, take `sub` claim).

Expected output: `Senior Cloud Solutions Architect`

If the field is `None` or missing, the tool failed silently (Nova Lite hallucination — see CLAUDE.md gotcha). Check CloudWatch logs for the `update_user_profile` invocation; expect `Failed to update user profile`. Fix the underlying cause before continuing.

### Task 3: Exercise O*NET search tool

- [ ] **Step 3.1: Send a search request to the agent**

In Coaching chat, send: `Use onet_search_careers to find careers matching "cloud architect". Show me the first three results with their SOC codes.`

- [ ] **Step 3.2: Verify tool ran and returned valid SOC codes**

Expected: AgentActivityFeed shows `onet_search_careers` → done. The reply lists 3 entries, each with a SOC code matching the regex `\d{2}-\d{4}\.\d{2}` (e.g. `15-1299.08`).

- [ ] **Step 3.3: Capture one SOC code for Task 4**

Note the SOC code of the most relevant result (likely `15-1299.08` "Computer Systems Engineers/Architects" or `15-1244.00` "Network and Computer Systems Administrators"). Use it verbatim in the next task.

### Task 4: Exercise O*NET career detail tool

- [ ] **Step 4.1: Send a detail request**

In Coaching chat, send (substitute the SOC code from Step 3.3): `Use onet_career_detail with soc_code="15-1299.08" and tell me the top 3 technology skills required.`

- [ ] **Step 4.2: Verify response shape**

Expected: AgentActivityFeed shows `onet_career_detail` → done. The reply lists 3 specific technologies (e.g. "Amazon Web Services", "Kubernetes", "Terraform"). If the reply says "I couldn't find data for that code", check CloudWatch for the actual O*NET API response — likely an SSM permissions issue or expired credentials.

### Task 5: Verify targetRole is in the system prompt

- [ ] **Step 5.1: Open a fresh coaching session**

Click "New thread" or refresh the Coaching page so the agent re-instantiates with a fresh prompt.

- [ ] **Step 5.2: Ask the agent to recite its context**

Send: `Without calling any tools, what is my current target role and what's my reskilling focus?`

Expected: The agent answers with "Senior Cloud Solutions Architect" (proving `_get_system_prompt` in `backend/agents/coaching/agent.py:191-201` and `backend/handlers/coaching/voice_handler.py:131-150` correctly wired the field through). If the agent says "you haven't told me yet" or makes one up, the prompt grounding broke — investigate `prompts.py` and the `target_role` parameter wiring.

### Task 6: Document Phase 1 findings

- [ ] **Step 6.1: Append findings to this plan**

Open `docs/superpowers/plans/2026-04-15-profile-target-role-edit.md` and append a `## Phase 1 Results` section at the end with:
- Date/time of validation
- Tool names confirmed loaded (from Step 1.3)
- DynamoDB targetRole value after write (from Step 2.3)
- One sample SOC code returned (from Step 3.3)
- One technology returned (from Step 4.2)
- Whether the fresh-thread context grounding worked (from Step 5.2)

- [ ] **Step 6.2: Commit the runbook results**

```bash
cd /Users/cperez/Desktop/altivum-dev/regain
git add docs/superpowers/plans/2026-04-15-profile-target-role-edit.md
git commit -m "docs(plan): record Phase 1 O*NET validation results"
```

**Phase 1 exit criteria:** Steps 1.3, 2.3, 3.2, 4.2, and 5.2 all pass. If any fail, fix the underlying issue before starting Phase 2 — Phase 2 assumes O*NET tools are reliable so the new targetRole-edit flow can drive O*NET research conversations.

---

## Phase 2 — Profile Edit UI (separate branch)

### Task 7: Create the Phase 2 branch from main

**Files:** None (branching only)

- [ ] **Step 7.1: Confirm Phase 1 work is committed and the O*NET PR is open**

Run: `cd /Users/cperez/Desktop/altivum-dev/regain && git log --oneline -3 && gh pr list --head feat/onet-agent-tools --json url --jq '.[0].url'`
Expected: Top commit is the Phase 1 results doc; the URL of the open O*NET PR is printed.

- [ ] **Step 7.2: Branch from origin/main**

```bash
git fetch origin main
git switch -c feat/profile-target-role-edit origin/main
```
Expected: New branch tracks `origin/main`; working tree clean.

### Task 8: Backend service test — happy path

**Files:**
- Create: `tests/unit/handlers/profile/test_service_update_target_role.py`
- Test target: `backend/handlers/profile/service.py` (function added in Task 9)

- [ ] **Step 8.1: Write the failing test**

Create `tests/unit/handlers/profile/test_service_update_target_role.py`:

```python
"""Unit tests for ProfileService.update_target_role."""

from __future__ import annotations

import os
import boto3
import pytest
from moto import mock_aws

from backend.handlers.profile.service import ProfileService
from backend.handlers.shared.dynamodb import DynamoDBClient


@pytest.fixture(autouse=True)
def _aws_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("USER_PROFILES_TABLE", "RegainUserProfiles")
    monkeypatch.setenv("CAMPAIGNS_TABLE", "RegainCampaigns")


@pytest.fixture
def _tables() -> None:
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        ddb.create_table(
            TableName="RegainUserProfiles",
            KeySchema=[{"AttributeName": "userId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "userId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        ddb.create_table(
            TableName="RegainCampaigns",
            KeySchema=[
                {"AttributeName": "userId", "KeyType": "HASH"},
                {"AttributeName": "campaignId", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "userId", "AttributeType": "S"},
                {"AttributeName": "campaignId", "AttributeType": "S"},
                {"AttributeName": "status", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[{
                "IndexName": "status-index",
                "KeySchema": [
                    {"AttributeName": "status", "KeyType": "HASH"},
                    {"AttributeName": "userId", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }],
            BillingMode="PAY_PER_REQUEST",
        )
        yield


def test_update_target_role_writes_both_tables_atomically(_tables) -> None:
    db = DynamoDBClient()
    db._get_table("user_profiles").put_item(
        Item={"userId": "user-1", "targetRole": "Old Role"},
    )
    db._get_table("campaigns").put_item(
        Item={
            "userId": "user-1",
            "campaignId": "camp-1",
            "status": "active",
            "targetRole": "Old Role",
            "skillsFocus": ["Python"],
        },
    )

    service = ProfileService(db_client=db)
    result = service.update_target_role("user-1", "Senior Cloud Architect")

    assert result == {"targetRole": "Senior Cloud Architect"}
    profile = db.get_item("user_profiles", {"userId": "user-1"})
    campaign = db.get_item("campaigns", {"userId": "user-1", "campaignId": "camp-1"})
    assert profile["targetRole"] == "Senior Cloud Architect"
    assert campaign["targetRole"] == "Senior Cloud Architect"


def test_update_target_role_when_no_active_campaign(_tables) -> None:
    db = DynamoDBClient()
    db._get_table("user_profiles").put_item(Item={"userId": "user-2"})

    service = ProfileService(db_client=db)
    result = service.update_target_role("user-2", "Data Engineer")

    assert result == {"targetRole": "Data Engineer"}
    profile = db.get_item("user_profiles", {"userId": "user-2"})
    assert profile["targetRole"] == "Data Engineer"


@pytest.mark.parametrize("bad_value", ["", "   ", "x" * 201])
def test_update_target_role_rejects_invalid_input(_tables, bad_value: str) -> None:
    service = ProfileService(db_client=DynamoDBClient())
    with pytest.raises(ValueError):
        service.update_target_role("user-3", bad_value)
```

- [ ] **Step 8.2: Run the test to confirm it fails**

Run: `.venv/bin/pytest tests/unit/handlers/profile/test_service_update_target_role.py -x -v`
Expected: All four tests FAIL with `AttributeError: 'ProfileService' object has no attribute 'update_target_role'`.

### Task 9: Implement `ProfileService.update_target_role`

**Files:**
- Modify: `backend/handlers/profile/service.py` (add new method)

- [ ] **Step 9.1: Add the method**

Append to `backend/handlers/profile/service.py` (before the final `hard_delete_user_account` method or anywhere inside the class — keep it grouped with the other write methods near `recover_user_account`):

```python
    _MAX_TARGET_ROLE_LEN = 200

    def update_target_role(self, user_id: str, target_role: str) -> Dict[str, Any]:
        """Atomically update targetRole on UserProfiles and the active Campaign.

        Both writes happen inside a single DynamoDB TransactWriteItems call,
        so either both succeed or both fail. If the user has no active
        campaign, only UserProfiles is written.

        Args:
            user_id: Cognito sub from JWT claims.
            target_role: New target role string. Trimmed; must be 1–200 chars.

        Returns:
            ``{"targetRole": <trimmed value>}``.

        Raises:
            ValueError: When ``target_role`` is empty after trimming or
                exceeds 200 characters.
        """
        trimmed = (target_role or "").strip()
        if not trimmed:
            raise ValueError("target_role must not be empty")
        if len(trimmed) > self._MAX_TARGET_ROLE_LEN:
            raise ValueError(
                f"target_role exceeds {self._MAX_TARGET_ROLE_LEN} characters"
            )

        active_campaign = self._find_active_campaign(user_id)

        profiles_table = os.environ["USER_PROFILES_TABLE"]
        campaigns_table = os.environ["CAMPAIGNS_TABLE"]

        items: list[Dict[str, Any]] = [{
            "Update": {
                "TableName": profiles_table,
                "Key": {"userId": {"S": user_id}},
                "UpdateExpression": "SET targetRole = :v",
                "ExpressionAttributeValues": {":v": {"S": trimmed}},
            }
        }]
        if active_campaign:
            items.append({
                "Update": {
                    "TableName": campaigns_table,
                    "Key": {
                        "userId": {"S": user_id},
                        "campaignId": {"S": active_campaign["campaignId"]},
                    },
                    "UpdateExpression": "SET targetRole = :v",
                    "ExpressionAttributeValues": {":v": {"S": trimmed}},
                }
            })

        client = boto3.client("dynamodb")
        client.transact_write_items(TransactItems=items)
        logger.info("Updated targetRole for user %s", user_id)
        return {"targetRole": trimmed}

    def _find_active_campaign(self, user_id: str) -> Dict[str, Any] | None:
        """Return the user's active campaign row, or None if none exists."""
        from boto3.dynamodb.conditions import Attr, Key

        items = self.db.query(
            "campaigns",
            key_condition=Key("userId").eq(user_id),
            filter_expression=Attr("status").eq("active"),
        )
        return items[0] if items else None
```

- [ ] **Step 9.2: Run the tests to confirm they pass**

Run: `.venv/bin/pytest tests/unit/handlers/profile/test_service_update_target_role.py -x -v`
Expected: All four tests PASS.

- [ ] **Step 9.3: Commit**

```bash
git add backend/handlers/profile/service.py tests/unit/handlers/profile/test_service_update_target_role.py
git commit -m "feat(profile): add update_target_role with atomic dual-table write"
```

### Task 10: Backend handler test — PATCH route

**Files:**
- Create: `tests/unit/handlers/profile/test_handler_patch.py`

- [ ] **Step 10.1: Write the failing test**

Create `tests/unit/handlers/profile/test_handler_patch.py`:

```python
"""Unit tests for PATCH /profile route in profile handler."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from backend.handlers.profile import handler as profile_handler


def _patch_event(body: dict | str | None) -> dict:
    return {
        "httpMethod": "PATCH",
        "resource": "/profile",
        "body": body if isinstance(body, str) or body is None else json.dumps(body),
        "requestContext": {
            "authorizer": {"claims": {"sub": "user-1"}},
            "requestId": "rid-1",
        },
    }


def test_patch_profile_updates_target_role() -> None:
    fake_service = MagicMock()
    fake_service.update_target_role.return_value = {"targetRole": "Cloud Architect"}

    with patch.object(profile_handler, "ProfileService", return_value=fake_service):
        result = profile_handler.lambda_handler(
            _patch_event({"targetRole": "Cloud Architect"}), None
        )

    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["targetRole"] == "Cloud Architect"
    fake_service.update_target_role.assert_called_once_with("user-1", "Cloud Architect")


def test_patch_profile_rejects_missing_body() -> None:
    result = profile_handler.lambda_handler(_patch_event(None), None)
    assert result["statusCode"] == 400


def test_patch_profile_rejects_invalid_json() -> None:
    result = profile_handler.lambda_handler(_patch_event("not-json"), None)
    assert result["statusCode"] == 400


def test_patch_profile_rejects_missing_target_role() -> None:
    result = profile_handler.lambda_handler(_patch_event({"foo": "bar"}), None)
    assert result["statusCode"] == 400


def test_patch_profile_rejects_non_string_target_role() -> None:
    result = profile_handler.lambda_handler(_patch_event({"targetRole": 42}), None)
    assert result["statusCode"] == 400


def test_patch_profile_returns_400_on_value_error() -> None:
    fake_service = MagicMock()
    fake_service.update_target_role.side_effect = ValueError("too long")

    with patch.object(profile_handler, "ProfileService", return_value=fake_service):
        result = profile_handler.lambda_handler(
            _patch_event({"targetRole": "x"}), None
        )

    assert result["statusCode"] == 400
    assert "too long" in json.loads(result["body"])["error"]


def test_patch_profile_requires_auth() -> None:
    event = _patch_event({"targetRole": "x"})
    event["requestContext"] = {"requestId": "rid-2"}
    result = profile_handler.lambda_handler(event, None)
    assert result["statusCode"] == 401
```

- [ ] **Step 10.2: Run the test to confirm it fails**

Run: `.venv/bin/pytest tests/unit/handlers/profile/test_handler_patch.py -x -v`
Expected: All seven tests FAIL — the handler returns 404 because PATCH is not a recognized method/resource yet.

### Task 11: Implement PATCH handling in the profile Lambda

**Files:**
- Modify: `backend/handlers/profile/handler.py`

- [ ] **Step 11.1: Add PATCH branch and validation**

Edit `backend/handlers/profile/handler.py`. Replace the current `try:` block in `lambda_handler` with the version below (keeps existing POST/DELETE behavior, adds PATCH):

```python
    try:
        service = ProfileService()

        if http_method == "POST" and resource == "/profile/recover":
            result = service.recover_user_account(user_id)
            return success_response(result)

        if http_method == "PATCH" and resource == "/profile":
            raw_body = event.get("body")
            if not raw_body:
                return error_response(
                    "Missing request body", 400, error_kind="VALIDATION",
                )
            try:
                body = json.loads(raw_body)
            except (json.JSONDecodeError, TypeError):
                return error_response(
                    "Invalid JSON body", 400, error_kind="VALIDATION",
                )

            target_role = body.get("targetRole")
            if not isinstance(target_role, str):
                return error_response(
                    "Missing or invalid field: targetRole",
                    400,
                    error_kind="VALIDATION",
                )

            try:
                result = service.update_target_role(user_id, target_role)
            except ValueError as exc:
                return error_response(str(exc), 400, error_kind="VALIDATION")
            return success_response(result)

        if http_method == "DELETE":
            raw_body = event.get("body")
            if not raw_body:
                return error_response(
                    "Missing required field: mode", 400, error_kind="VALIDATION",
                )
            try:
                body = json.loads(raw_body)
            except (json.JSONDecodeError, TypeError):
                return error_response(
                    "Invalid JSON body", 400, error_kind="VALIDATION",
                )

            mode = body.get("mode")
            if mode not in _VALID_MODES:
                return error_response(
                    "Invalid mode. Must be 'immediate' or 'scheduled'",
                    400,
                    error_kind="VALIDATION",
                )

            if mode == "immediate":
                result = service.hard_delete_user_account(user_id)
            else:
                result = service.soft_delete_user_account(user_id)
            return success_response(result)

        return error_response("Not found", 404)
    except Exception:
        slog.exception("Profile handler failed for user %s", user_id)
        return error_response("Internal server error", 500)
```

- [ ] **Step 11.2: Run the handler tests to confirm they pass**

Run: `.venv/bin/pytest tests/unit/handlers/profile/test_handler_patch.py -x -v`
Expected: All seven tests PASS.

- [ ] **Step 11.3: Run the full profile handler suite to ensure no regressions**

Run: `.venv/bin/pytest tests/unit/handlers/profile/ -x -q`
Expected: All tests in that directory PASS (existing + new).

- [ ] **Step 11.4: Commit**

```bash
git add backend/handlers/profile/handler.py tests/unit/handlers/profile/test_handler_patch.py
git commit -m "feat(profile): add PATCH /profile route for targetRole edits"
```

### Task 12: Wire PATCH /profile into API Gateway

**Files:**
- Modify: `infra/stacks/api_stack.py:342-354`

- [ ] **Step 12.1: Add PATCH method to the existing `/profile` resource**

Edit `infra/stacks/api_stack.py`. Find the block that adds DELETE on `/profile` (currently around line 342-354) and add a PATCH method to the same `profile` resource immediately after the DELETE call:

```python
        # DELETE /profile + PATCH /profile + POST /profile/recover
        profile = self.api.root.add_resource("profile")
        profile.add_method(
            "DELETE",
            apigw.LambdaIntegration(lambdas["Profile"]),
            **auth_kwargs,
        )
        profile.add_method(
            "PATCH",
            apigw.LambdaIntegration(lambdas["Profile"]),
            **auth_kwargs,
        )
        profile_recover = profile.add_resource("recover")
        profile_recover.add_method(
            "POST",
            apigw.LambdaIntegration(lambdas["Profile"]),
            **auth_kwargs,
        )
```

`apigw.Cors.ALL_METHODS` (api_stack.py:254) already includes PATCH, so the existing CORS preflight covers the new route.

- [ ] **Step 12.2: Run cdk synth to validate**

```bash
cd infra && eval "$(AWS_PROFILE=regain aws configure export-credentials --format env)" && AWS_DEFAULT_REGION=us-east-1 npx cdk synth RegainApiStack > /dev/null
```
Expected: synth completes with no errors.

### Task 13: Update infra test count

**Files:**
- Modify: `tests/unit/stacks/test_api_authorization.py:51`

- [ ] **Step 13.1: Bump EXPECTED_METHOD_COUNT from 18 to 19**

Edit `tests/unit/stacks/test_api_authorization.py` line 51:

```python
EXPECTED_METHOD_COUNT = 19
```

- [ ] **Step 13.2: Run the api authorization test**

Run: `.venv/bin/pytest tests/unit/stacks/test_api_authorization.py -x -q`
Expected: PASS. Property test confirms all 19 non-OPTIONS methods carry `COGNITO_USER_POOLS` authorization.

- [ ] **Step 13.3: Run the full infra suite**

Run: `.venv/bin/pytest tests/unit/stacks/ -x -q`
Expected: All PASS. (`EXPECTED_LAMBDA_COUNT = 9` is unchanged because we reuse the existing Profile Lambda.)

- [ ] **Step 13.4: Commit infra changes**

```bash
cd /Users/cperez/Desktop/altivum-dev/regain
git add infra/stacks/api_stack.py tests/unit/stacks/test_api_authorization.py
git commit -m "infra(api): expose PATCH /profile route"
```

### Task 14: Frontend API client method

**Files:**
- Modify: `frontend/src/services/api.ts` (the `profile:` block at lines 242-255)

- [ ] **Step 14.1: Add `updateTargetRole` to the api.profile namespace**

Edit `frontend/src/services/api.ts`. Replace the existing `profile:` block (lines 242-255) with:

```typescript
  profile: {
    delete: (token: string, mode: 'immediate' | 'scheduled' = 'immediate') =>
      apiRequest<{ status: string; deletionDate?: string; deleted?: Record<string, number> }>(
        '/profile',
        { method: 'DELETE', body: { mode } },
        token,
      ),
    recover: (token: string) =>
      apiRequest<{ status: string }>(
        '/profile/recover',
        { method: 'POST' },
        token,
      ),
    updateTargetRole: (targetRole: string, token: string) =>
      apiRequest<{ targetRole: string }>(
        '/profile',
        { method: 'PATCH', body: { targetRole } },
        token,
      ).then((res) => {
        invalidateCache('/dashboard');
        return res;
      }),
  },
```

`PATCH` must also be allowed by the `ApiRequestOptions.method` union. Check the type definition near line 36 — if `'PATCH'` is missing, add it:

```typescript
interface ApiRequestOptions {
  method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  body?: unknown;
  headers?: Record<string, string>;
}
```

- [ ] **Step 14.2: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: Zero errors.

### Task 15: EditableTargetRole component test

**Files:**
- Create: `frontend/src/components/profile/EditableTargetRole.test.tsx`

- [ ] **Step 15.1: Write the failing test**

Create `frontend/src/components/profile/EditableTargetRole.test.tsx`:

```tsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';

import { EditableTargetRole } from './EditableTargetRole';

describe('EditableTargetRole', () => {
  it('renders the current value with an Edit button', () => {
    render(
      <EditableTargetRole value="Senior Cloud Architect" onSave={vi.fn()} />,
    );
    expect(screen.getByText('Senior Cloud Architect')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /edit target role/i })).toBeInTheDocument();
  });

  it('switches to edit mode when Edit is clicked', async () => {
    const user = userEvent.setup();
    render(
      <EditableTargetRole value="Senior Cloud Architect" onSave={vi.fn()} />,
    );
    await user.click(screen.getByRole('button', { name: /edit target role/i }));
    expect(screen.getByLabelText(/target role/i)).toHaveValue('Senior Cloud Architect');
    expect(screen.getByRole('button', { name: /^save$/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument();
  });

  it('calls onSave with the trimmed new value', async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<EditableTargetRole value="Old Role" onSave={onSave} />);

    await user.click(screen.getByRole('button', { name: /edit target role/i }));
    const input = screen.getByLabelText(/target role/i);
    await user.clear(input);
    await user.type(input, '  Data Engineer  ');
    await user.click(screen.getByRole('button', { name: /^save$/i }));

    await waitFor(() => expect(onSave).toHaveBeenCalledWith('Data Engineer'));
  });

  it('disables Save when value is empty or unchanged', async () => {
    const user = userEvent.setup();
    render(<EditableTargetRole value="Old" onSave={vi.fn()} />);
    await user.click(screen.getByRole('button', { name: /edit target role/i }));

    const save = screen.getByRole('button', { name: /^save$/i });
    expect(save).toBeDisabled();

    const input = screen.getByLabelText(/target role/i);
    await user.clear(input);
    expect(save).toBeDisabled();

    await user.type(input, 'New');
    expect(save).toBeEnabled();
  });

  it('exits edit mode and discards changes on Cancel', async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();
    render(<EditableTargetRole value="Old" onSave={onSave} />);

    await user.click(screen.getByRole('button', { name: /edit target role/i }));
    const input = screen.getByLabelText(/target role/i);
    await user.clear(input);
    await user.type(input, 'Should be discarded');
    await user.click(screen.getByRole('button', { name: /cancel/i }));

    expect(screen.getByText('Old')).toBeInTheDocument();
    expect(onSave).not.toHaveBeenCalled();
  });

  it('shows an error message when onSave rejects', async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockRejectedValue(new Error('Server is angry'));
    render(<EditableTargetRole value="Old" onSave={onSave} />);

    await user.click(screen.getByRole('button', { name: /edit target role/i }));
    const input = screen.getByLabelText(/target role/i);
    await user.clear(input);
    await user.type(input, 'New');
    await user.click(screen.getByRole('button', { name: /^save$/i }));

    expect(await screen.findByText(/server is angry/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/target role/i)).toBeInTheDocument();
  });

  it('saves on Enter key and cancels on Escape', async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<EditableTargetRole value="Old" onSave={onSave} />);

    await user.click(screen.getByRole('button', { name: /edit target role/i }));
    const input = screen.getByLabelText(/target role/i);
    await user.clear(input);
    await user.type(input, 'New{Enter}');
    await waitFor(() => expect(onSave).toHaveBeenCalledWith('New'));

    onSave.mockClear();
    await user.click(screen.getByRole('button', { name: /edit target role/i }));
    const input2 = screen.getByLabelText(/target role/i);
    fireEvent.keyDown(input2, { key: 'Escape' });
    expect(screen.getByText('New')).toBeInTheDocument();
    expect(onSave).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 15.2: Run the test to confirm it fails**

Run: `cd frontend && npx vitest --run src/components/profile/EditableTargetRole.test.tsx`
Expected: All tests FAIL with "Cannot find module './EditableTargetRole'".

### Task 16: Implement EditableTargetRole component

**Files:**
- Create: `frontend/src/components/profile/EditableTargetRole.tsx`

- [ ] **Step 16.1: Create the component**

Create `frontend/src/components/profile/EditableTargetRole.tsx`:

```tsx
import { useEffect, useRef, useState } from 'react';

import { Button } from '../ui/Button';
import { Input } from '../ui/Input';

interface EditableTargetRoleProps {
  value: string;
  onSave: (next: string) => Promise<void> | void;
}

export function EditableTargetRole({ value, onSave }: EditableTargetRoleProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editing) {
      setDraft(value);
      setError(null);
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [editing, value]);

  const trimmed = draft.trim();
  const dirty = trimmed.length > 0 && trimmed !== value;

  const cancel = () => {
    setEditing(false);
    setDraft(value);
    setError(null);
  };

  const save = async () => {
    if (!dirty || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      await onSave(trimmed);
      setEditing(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save target role');
    } finally {
      setSubmitting(false);
    }
  };

  if (!editing) {
    return (
      <div className="mt-5 flex items-start gap-3">
        <p className="text-2xl font-semibold tracking-tight text-neutral-900">
          {value || 'Set a target role'}
        </p>
        <button
          type="button"
          onClick={() => setEditing(true)}
          aria-label="Edit target role"
          className="mt-1 rounded-md p-1 text-neutral-400 hover:bg-surface-2 hover:text-primary-600 transition-colors"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 20 20"
            fill="currentColor"
            className="h-4 w-4"
            aria-hidden="true"
          >
            <path d="M13.586 3.586a2 2 0 1 1 2.828 2.828l-.793.793-2.828-2.828.793-.793zM11.379 5.793 3 14.172V17h2.828l8.379-8.379-2.828-2.828z" />
          </svg>
        </button>
      </div>
    );
  }

  return (
    <div className="mt-5 space-y-2">
      <Input
        ref={inputRef}
        label="Target role"
        value={draft}
        maxLength={200}
        disabled={submitting}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault();
            void save();
          } else if (e.key === 'Escape') {
            e.preventDefault();
            cancel();
          }
        }}
        error={error ?? undefined}
      />
      <div className="flex gap-2">
        <Button
          variant="primary"
          size="sm"
          onClick={() => void save()}
          disabled={!dirty || submitting}
        >
          {submitting ? 'Saving…' : 'Save'}
        </Button>
        <Button variant="ghost" size="sm" onClick={cancel} disabled={submitting}>
          Cancel
        </Button>
      </div>
    </div>
  );
}
```

If `Input` doesn't already forward `ref` (check `frontend/src/components/ui/Input.tsx`), wrap its definition in `forwardRef` first. The CLAUDE.md notes that `Button` supports `forwardRef`; `Input` should already too — verify before writing tests run.

- [ ] **Step 16.2: Confirm Input supports ref forwarding**

Run: `grep -n "forwardRef" frontend/src/components/ui/Input.tsx`
Expected: A match. If empty, edit `Input.tsx` to wrap the component in `forwardRef<HTMLInputElement, InputProps>`. Otherwise no change needed.

- [ ] **Step 16.3: Run component tests to confirm they pass**

Run: `cd frontend && npx vitest --run src/components/profile/EditableTargetRole.test.tsx`
Expected: All seven tests PASS.

- [ ] **Step 16.4: Commit**

```bash
cd /Users/cperez/Desktop/altivum-dev/regain
git add frontend/src/components/profile/EditableTargetRole.tsx \
        frontend/src/components/profile/EditableTargetRole.test.tsx \
        frontend/src/services/api.ts
git commit -m "feat(profile): add EditableTargetRole inline edit component"
```

### Task 17: Wire EditableTargetRole into the Profile page

**Files:**
- Modify: `frontend/src/pages/Profile.tsx:96-148` (the `IdentitySummary` component)

- [ ] **Step 17.1: Replace the static target role line with the editable component**

Edit `frontend/src/pages/Profile.tsx`. At the top of the file, add the new imports alongside the existing UI imports (place the `EditableTargetRole` import near other component imports, and add `api`/`useAuth` if not already imported in this scope):

```typescript
import { EditableTargetRole } from '../components/profile/EditableTargetRole';
import { api } from '../services/api';
import { useMutationBus } from '../hooks/useMutationBus';
```

(`useAuth` and `useMutationBus` are already imported per the existing file — the duplicate import line will be a no-op at the top, but `EditableTargetRole` is new.)

Update `IdentitySummary` to accept the save callback and call `EditableTargetRole`. Replace the existing block (lines 109-122 region):

```tsx
function IdentitySummary({
  username,
  campaign,
  stats,
  onSaveTargetRole,
}: {
  username: string;
  campaign: Campaign;
  stats: { missionsCompleted: number; evidenceCount: number };
  onSaveTargetRole: (next: string) => Promise<void>;
}) {
  const days = daysActive(campaign.startDate);
  const idx = phaseIndex(campaign.phase);

  return (
    <Card className="p-8">
      <SectionLabel>Transition Profile</SectionLabel>

      <EditableTargetRole
        value={campaign.targetRole}
        onSave={onSaveTargetRole}
      />

      <div className="mt-2.5 flex flex-wrap items-center gap-3">
        <Badge variant="primary">
          {DISPLAY_PHASES[idx]}
        </Badge>
        <span className="text-sm text-neutral-400">{username}</span>
      </div>

      {/* ...keep the existing stats grid + start-date paragraph below unchanged... */}
```

Keep the existing 3-column stats grid and "Campaign started …" paragraph below the new block — only the headline `<p>{campaign.targetRole}</p>` is replaced.

- [ ] **Step 17.2: Pass the save callback from the parent `Profile` component**

In `frontend/src/pages/Profile.tsx`, inside the `Profile` function (currently around line 568), add a `handleSaveTargetRole` and pass it to `IdentitySummary`. Replace the JSX return block (lines 568-585) with:

```tsx
  const { emit } = useMutationBus();

  const handleSaveTargetRole = async (next: string) => {
    const token = await getToken();
    if (!token) throw new Error('Not signed in');
    await api.profile.updateTargetRole(next, token);
    emit({ type: 'profile:targetRole:updated' });
    await fetchDashboard();
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <IdentitySummary
        username={user?.username ?? ''}
        campaign={campaign}
        stats={stats}
        onSaveTargetRole={handleSaveTargetRole}
      />

      <SkillsInventory skills={campaign.skillsFocus} />

      <SkillDevelopmentChart />

      <CampaignJourney campaign={campaign} />

      <DeleteAccount getToken={getToken} signOut={signOut} />
    </div>
  );
```

`useMutationBus()` returns both `setPageSnapshot` (already used above in this function) and `emit`. If the existing destructure on line 519 only pulls `setPageSnapshot`, expand it: `const { setPageSnapshot, emit } = useMutationBus();` and remove the new `const { emit } = useMutationBus();` line.

- [ ] **Step 17.3: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: Zero errors.

- [ ] **Step 17.4: Run frontend test suite**

Run: `cd frontend && npx vitest --run`
Expected: All tests PASS (existing 112 + new EditableTargetRole tests).

- [ ] **Step 17.5: Commit**

```bash
cd /Users/cperez/Desktop/altivum-dev/regain
git add frontend/src/pages/Profile.tsx
git commit -m "feat(profile): expose targetRole edit affordance on Profile page"
```

### Task 18: Build frontend

**Files:** None (build only)

- [ ] **Step 18.1: Production build**

Run: `cd frontend && npm run build`
Expected: `tsc` + `vite build` succeed; `dist/` populated; bundle warnings (if any) are not new vs main.

### Task 19: Run full backend test suite

**Files:** None (test run only)

- [ ] **Step 19.1: Backend integration tests (fast)**

Run: `cd /Users/cperez/Desktop/altivum-dev/regain && .venv/bin/pytest tests/integration/ -x -q`
Expected: All PASS in ~2-3s.

- [ ] **Step 19.2: Backend unit tests, scoped**

Run: `.venv/bin/pytest tests/unit/handlers/profile/ tests/unit/stacks/ -x -q`
Expected: All PASS. Targets the areas we touched plus stack assertions.

- [ ] **Step 19.3: Optional full backend run**

Run: `.venv/bin/pytest tests/ -x -q` (only if time allows — ~8 min)
Expected: All PASS.

### Task 20: Deploy ApiStack

**Files:** None (deploy only)

- [ ] **Step 20.1: Diff first**

```bash
cd infra && eval "$(AWS_PROFILE=regain aws configure export-credentials --format env)" && AWS_DEFAULT_REGION=us-east-1 npx cdk diff RegainApiStack
```
Expected: Diff shows one new `AWS::ApiGateway::Method` (PATCH on `/profile`) and one new permission for the Profile Lambda, plus an updated CFN integration. No other resources change.

- [ ] **Step 20.2: Deploy**

```bash
eval "$(AWS_PROFILE=regain aws configure export-credentials --format env)" && AWS_DEFAULT_REGION=us-east-1 npx cdk deploy RegainApiStack --require-approval never
```
Expected: Deploy completes successfully. Note the API URL output (should be unchanged from prior deploys).

- [ ] **Step 20.3: Smoke-test the new endpoint via curl**

```bash
TOKEN=<your-cognito-idToken>  # paste from devtools, see Phase 1 Step 2.3
curl -sS -X PATCH "https://<api-id>.execute-api.us-east-1.amazonaws.com/prod/profile" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"targetRole":"Principal Cloud Architect"}'
```
Expected: `{"targetRole":"Principal Cloud Architect"}` returned with status 200.

- [ ] **Step 20.4: Verify both tables updated**

```bash
aws dynamodb get-item --table-name RegainUserProfiles --key '{"userId": {"S": "<your-cognito-sub>"}}' --query 'Item.targetRole.S' --output text
aws dynamodb scan --table-name RegainCampaigns --filter-expression "userId = :u AND #s = :a" --expression-attribute-names '{"#s":"status"}' --expression-attribute-values '{":u":{"S":"<your-cognito-sub>"},":a":{"S":"active"}}' --query 'Items[0].targetRole.S' --output text
```
Expected: Both commands print `Principal Cloud Architect`.

### Task 21: Manual UI smoke test

**Files:** None (manual verification)

- [ ] **Step 21.1: Reload the deployed app**

Open https://regain.altivum.ai → Profile page. The current target role displays with a small pencil icon next to it.

- [ ] **Step 21.2: Edit and save**

Click the pencil → edit the field → click Save (or press Enter).
Expected: Inline edit collapses; the new role appears immediately; no page reload required.

- [ ] **Step 21.3: Verify dashboard reflects the change**

Navigate to Dashboard → Profile snapshot card shows the new role (cache invalidated by `invalidateCache('/dashboard')` in `api.profile.updateTargetRole`).

- [ ] **Step 21.4: Verify coaching agent picks up the change**

Click "New thread" on Coaching → ask: `What's my current target role?`
Expected: Agent answers with the new role, proving `_get_system_prompt` reads the updated `targetRole` field on the next session.

- [ ] **Step 21.5: Verify Cancel discards changes**

Click pencil → type a new value → click Cancel.
Expected: Field reverts; no PATCH call in Network tab; no DynamoDB change.

### Task 22: Open PR

**Files:** None (PR creation)

- [ ] **Step 22.1: Push the branch**

```bash
cd /Users/cperez/Desktop/altivum-dev/regain
git push -u origin feat/profile-target-role-edit
```

- [ ] **Step 22.2: Create the PR**

```bash
gh pr create --title "feat(profile): editable target role" --body "$(cat <<'EOF'
## Summary
- Add `PATCH /profile` endpoint that atomically updates `UserProfiles.targetRole` and the active `Campaigns.targetRole` via a single DynamoDB `TransactWriteItems` call (prevents drift).
- Add inline `EditableTargetRole` component (pencil affordance) on the Profile page; reuses shared `Input` + `Button`.
- New `api.profile.updateTargetRole` client method invalidates the dashboard cache so the change is visible everywhere immediately.

## Test plan
- [x] Backend unit tests for `ProfileService.update_target_role` (happy path, no active campaign, validation errors)
- [x] Backend unit tests for handler PATCH branch (auth, body parsing, validation)
- [x] Frontend unit tests for `EditableTargetRole` (render, edit, save, cancel, error, keyboard)
- [x] `EXPECTED_METHOD_COUNT` bumped to 19 in `test_api_authorization.py`
- [x] Manual smoke test on regain.altivum.ai (curl + UI flows confirmed both tables updated and coach picked up new role on a fresh thread)
EOF
)"
```

Expected: PR URL printed; required CI checks (backend, frontend, infra) start running.

---

## Out of Scope

- A standalone "Profile editor" page or modal — the inline pencil is sufficient and matches the existing visual language.
- Editing `skillsFocus`, `firstName`, etc. — separate concerns, separate PRs.
- Validating that the new role is a known O*NET title — that's a UX nicety, not a correctness concern.
- Backfilling `targetRole` for users whose `UserProfiles` and `Campaigns` rows are already out of sync (legacy data) — Phase 2 introduces the atomic write going forward; a one-shot reconciliation script can be a follow-up if needed.

---

## Phase 1 Results

(Append to this section after running Phase 1 — see Task 6.)
