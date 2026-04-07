# Always-On Coaching Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the coaching agent stateful across messages with real-time action awareness, user-controlled attention modes, and token-budgeted memory compaction.

**Architecture:** A new `ConversationThreads` DynamoDB table stores the full ordered conversation (including tool calls) per user. The existing WebSocket `$default` handler loads the thread on every invocation, giving the agent full context. Frontend MutationBus events flow to the backend as action events, and the agent responds based on the user's attention mode (DnD/Focus/Explore). A compaction mechanism summarizes the thread when it approaches the token budget.

**Tech Stack:** Python 3.12 (Lambda), DynamoDB, S3, Strands SDK, React 19, TypeScript, Tailwind v4

**Spec:** `docs/superpowers/specs/2026-04-06-always-on-coaching-agent-design.md`

---

## File Structure

### New Files

| File | Responsibility |
|------|---------------|
| `backend/handlers/shared/thread.py` | Thread CRUD: load, append, compact, attention mode, pending messages, token estimation |
| `tests/unit/handlers/shared/test_thread.py` | Unit tests for thread module |
| `tests/unit/handlers/shared/test_thread_properties.py` | Property-based tests for token estimation and compaction |
| `frontend/src/hooks/useAgentEventBridge.ts` | MutationBus -> WebSocket action event forwarding with dedup + batching |
| `frontend/src/hooks/useAgentEventBridge.test.ts` | Tests for event bridge hook |

### Modified Files

| File | Change |
|------|--------|
| `infra/stacks/data_stack.py` | Add ConversationThreads table + thread-archives S3 bucket |
| `infra/stacks/agent_stack.py` | Grant ChatStream Lambda permissions on new table + bucket, add env vars |
| `infra/stacks/api_stack.py` | Grant Coaching Lambda permissions on new table + bucket, add env vars |
| `backend/handlers/shared/dynamodb.py` | Add `conversation_threads` to `TABLE_ENV_VARS` |
| `backend/handlers/coaching/stream_handler.py` | Add action_event/compact/attention_mode/sync dispatch; load/save thread per invocation |
| `backend/agents/coaching/agent.py` | Accept + pass `conversation_history` to Strands `Agent()` |
| `backend/agents/coaching/prompts.py` | Add attention mode instructions to system prompt |
| `backend/handlers/profile/service.py` | Add ConversationThreads + thread-archives to cascade deletion |
| `frontend/src/hooks/MutationBusContext.tsx` | Expand `MutationEventType` union with new event types |
| `frontend/src/hooks/CoachingContext.tsx` | Handle new WebSocket message types (proactive, thread_meta, action_event, compact, sync) |
| `frontend/src/components/CoachModal.tsx` | Add attention mode toggle, token budget indicator, compact button |
| `tests/unit/stacks/test_on_demand_billing.py` | Bump `EXPECTED_TABLE_COUNT` from 8 to 9 |
| `tests/unit/stacks/test_table_output_completeness.py` | Bump `EXPECTED_TABLE_COUNT` and add to `known_tables` |

---

## Task 1: ConversationThreads DynamoDB Table + S3 Bucket (CDK)

**Files:**
- Modify: `infra/stacks/data_stack.py`
- Modify: `tests/unit/stacks/test_on_demand_billing.py:14`
- Modify: `tests/unit/stacks/test_table_output_completeness.py:14,63`

- [ ] **Step 1: Write the table creation method in DataStack**

Add to `infra/stacks/data_stack.py`, after `_create_idempotency_keys_table` call in `__init__`:

```python
self._create_conversation_threads_table()
self._create_thread_archives_bucket()
```

Add the methods:

```python
def _create_conversation_threads_table(self) -> None:
    """Create ConversationThreads table (PK: userId, SK: threadId)."""
    self.tables["ConversationThreads"] = dynamodb.Table(
        self,
        "RegainConversationThreads",
        table_name="RegainConversationThreads",
        partition_key=dynamodb.Attribute(
            name="userId", type=dynamodb.AttributeType.STRING
        ),
        sort_key=dynamodb.Attribute(
            name="threadId", type=dynamodb.AttributeType.STRING
        ),
        billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
        removal_policy=self._removal_policy,
        point_in_time_recovery=True,
    )

def _create_thread_archives_bucket(self) -> None:
    """Create S3 bucket for compacted thread archives."""
    from aws_cdk import aws_s3 as s3

    self.thread_archives_bucket = s3.Bucket(
        self,
        "RegainThreadArchives",
        bucket_name=f"regain-thread-archives-{self.account}-{self.region}",
        versioned=True,
        encryption=s3.BucketEncryption.S3_MANAGED,
        removal_policy=self._removal_policy,
        lifecycle_rules=[
            s3.LifecycleRule(
                transitions=[
                    s3.Transition(
                        storage_class=s3.StorageClass.GLACIER,
                        transition_after=cdk.Duration.days(30),
                    )
                ],
            )
        ],
    )
```

Also add the S3 import at the top of the file:

```python
from aws_cdk import (
    aws_cloudwatch as cloudwatch,
    aws_cloudwatch_actions as cw_actions,
    aws_dynamodb as dynamodb,
    aws_s3 as s3,
    aws_sns as sns,
)
```

And add a bucket name output in `_create_outputs`, after the table loop:

```python
cdk.CfnOutput(
    self,
    "ThreadArchivesBucketName",
    value=self.thread_archives_bucket.bucket_name,
    export_name="RegainThreadArchivesBucketName",
)
```

- [ ] **Step 2: Update infra test counts**

In `tests/unit/stacks/test_on_demand_billing.py` line 14:
```python
EXPECTED_TABLE_COUNT = 9
```

In `tests/unit/stacks/test_table_output_completeness.py` line 14:
```python
EXPECTED_TABLE_COUNT = 9
```

In `tests/unit/stacks/test_table_output_completeness.py` line 63, add `"ConversationThreads"` to the list:
```python
known_tables = ["UserProfiles", "Campaigns", "MissionHistory", "EvidenceVault", "MarketData", "VoiceSessions", "WebSocketConnections", "IdempotencyKeys", "ConversationThreads"]
```

- [ ] **Step 3: Run CDK synth and infra tests**

Run: `cd infra && npx cdk synth --quiet 2>&1 | tail -5`
Expected: Successful synthesis with no errors

Run: `.venv/bin/pytest tests/unit/stacks/test_on_demand_billing.py tests/unit/stacks/test_table_output_completeness.py -x -q`
Expected: All pass

- [ ] **Step 4: Commit**

```bash
git add infra/stacks/data_stack.py tests/unit/stacks/test_on_demand_billing.py tests/unit/stacks/test_table_output_completeness.py
git commit -m "feat: add ConversationThreads table and thread-archives S3 bucket"
```

---

## Task 2: Thread Management Module (Backend)

**Files:**
- Create: `backend/handlers/shared/thread.py`
- Modify: `backend/handlers/shared/dynamodb.py:26-33`
- Test: `tests/unit/handlers/shared/test_thread.py`

- [ ] **Step 1: Register table in DynamoDB client**

In `backend/handlers/shared/dynamodb.py`, add to `TABLE_ENV_VARS` dict:

```python
TABLE_ENV_VARS = {
    "user_profiles": "USER_PROFILES_TABLE",
    "campaigns": "CAMPAIGNS_TABLE",
    "mission_history": "MISSION_HISTORY_TABLE",
    "evidence_vault": "EVIDENCE_VAULT_TABLE",
    "market_data": "MARKET_DATA_TABLE",
    "voice_sessions": "VOICE_SESSIONS_TABLE",
    "conversation_threads": "CONVERSATION_THREADS_TABLE",
}
```

- [ ] **Step 2: Write failing tests for thread module**

Create `tests/unit/handlers/shared/test_thread.py`:

```python
"""Tests for conversation thread management."""

import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

# Set env vars before import.
os.environ.setdefault("CONVERSATION_THREADS_TABLE", "test-threads")
os.environ.setdefault("THREAD_ARCHIVE_BUCKET", "test-archives")


def _make_thread_module():
    """Import the module fresh to pick up env vars."""
    import importlib
    import backend.handlers.shared.thread as mod
    importlib.reload(mod)
    return mod


class TestEstimateTokens:
    def test_empty_string(self):
        mod = _make_thread_module()
        assert mod.estimate_tokens("") == 0

    def test_short_string(self):
        mod = _make_thread_module()
        # "hello world" = 11 chars -> 11 // 4 = 2
        assert mod.estimate_tokens("hello world") == 2

    def test_longer_string(self):
        mod = _make_thread_module()
        text = "a" * 400
        assert mod.estimate_tokens(text) == 100


class TestLoadActiveThread:
    @patch("backend.handlers.shared.thread._get_threads_table")
    def test_returns_empty_when_no_thread(self, mock_table_fn):
        mod = _make_thread_module()
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}
        mock_table_fn.return_value = mock_table

        result = mod.load_active_thread("user-1")
        assert result["turns"] == []
        assert result["tokenEstimate"] == 0
        assert result["attentionMode"] == "focus"

    @patch("backend.handlers.shared.thread._get_threads_table")
    def test_returns_existing_thread(self, mock_table_fn):
        mod = _make_thread_module()
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {
                "userId": "user-1",
                "threadId": "active",
                "turns": [{"role": "user", "content": "hello"}],
                "tokenEstimate": Decimal("10"),
                "maxTokenBudget": Decimal("27000"),
                "attentionMode": "explore",
                "lastActivityAt": "2026-04-06T00:00:00Z",
                "pendingMessages": [],
            }
        }
        mock_table_fn.return_value = mock_table

        result = mod.load_active_thread("user-1")
        assert len(result["turns"]) == 1
        assert result["attentionMode"] == "explore"
        assert result["tokenEstimate"] == 10


class TestAppendTurns:
    @patch("backend.handlers.shared.thread._get_threads_table")
    def test_appends_and_updates_token_estimate(self, mock_table_fn):
        mod = _make_thread_module()
        mock_table = MagicMock()
        mock_table_fn.return_value = mock_table

        turns = [
            {"role": "user", "content": "hello world", "timestamp": "2026-04-06T00:00:00Z", "source": "chat"},
        ]
        mod.append_turns("user-1", turns)

        mock_table.update_item.assert_called_once()
        call_kwargs = mock_table.update_item.call_args[1]
        assert call_kwargs["Key"] == {"userId": "user-1", "threadId": "active"}


class TestUpdateAttentionMode:
    @patch("backend.handlers.shared.thread._get_threads_table")
    def test_updates_mode(self, mock_table_fn):
        mod = _make_thread_module()
        mock_table = MagicMock()
        mock_table_fn.return_value = mock_table

        mod.update_attention_mode("user-1", "dnd")

        mock_table.update_item.assert_called_once()
        call_kwargs = mock_table.update_item.call_args[1]
        assert ":mode" in call_kwargs["ExpressionAttributeValues"]
        assert call_kwargs["ExpressionAttributeValues"][":mode"] == "dnd"

    @patch("backend.handlers.shared.thread._get_threads_table")
    def test_rejects_invalid_mode(self, mock_table_fn):
        mod = _make_thread_module()
        with pytest.raises(ValueError, match="Invalid attention mode"):
            mod.update_attention_mode("user-1", "invalid")


class TestCompactThread:
    @patch("backend.handlers.shared.thread.boto3")
    @patch("backend.handlers.shared.thread._get_threads_table")
    def test_archives_and_replaces(self, mock_table_fn, mock_boto3):
        mod = _make_thread_module()
        mock_table = MagicMock()
        mock_table_fn.return_value = mock_table
        mock_s3 = MagicMock()
        mock_boto3.client.return_value = mock_s3

        old_turns = [
            {"role": "user", "content": "hello", "timestamp": "2026-04-06T00:00:00Z", "source": "chat"},
            {"role": "assistant", "content": "hi there", "timestamp": "2026-04-06T00:00:01Z", "source": "chat"},
        ]
        summary = "User greeted, assistant responded."

        mod.compact_thread("user-1", old_turns, summary)

        # Should have written archive to S3
        mock_s3.put_object.assert_called_once()
        s3_call = mock_s3.put_object.call_args[1]
        assert s3_call["Bucket"] == "test-archives"
        assert "user-1/" in s3_call["Key"]

        # Should have replaced thread in DynamoDB
        mock_table.put_item.assert_called_once()
        put_item = mock_table.put_item.call_args[1]["Item"]
        assert put_item["userId"] == "user-1"
        assert put_item["threadId"] == "active"
        assert len(put_item["turns"]) == 1
        assert put_item["turns"][0]["source"] == "compaction"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/handlers/shared/test_thread.py -x -q`
Expected: FAIL — module `backend.handlers.shared.thread` not found

- [ ] **Step 4: Write the thread module**

Create `backend/handlers/shared/thread.py`:

```python
"""Conversation thread management for the coaching agent.

Provides CRUD operations on the ConversationThreads DynamoDB table,
token estimation, compaction (summarization + S3 archival), and
attention mode management.
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import boto3

logger = logging.getLogger(__name__)

_DEFAULT_TOKEN_BUDGET = 27_000
_VALID_ATTENTION_MODES = {"explore", "focus", "dnd"}

_threads_table = None


def _get_threads_table():
    """Lazily initialize the DynamoDB Table resource."""
    global _threads_table
    if _threads_table is None:
        table_name = os.environ.get("CONVERSATION_THREADS_TABLE", "")
        if not table_name:
            raise ValueError("CONVERSATION_THREADS_TABLE environment variable not set")
        _threads_table = boto3.resource("dynamodb").Table(table_name)
    return _threads_table


def estimate_tokens(content: str) -> int:
    """Approximate token count from string length.

    Uses a simple char/4 heuristic — good enough for budget tracking,
    not meant to be exact.
    """
    return len(content) // 4


def load_active_thread(user_id: str) -> Dict[str, Any]:
    """Load the active conversation thread for a user.

    Returns a dict with turns, tokenEstimate, maxTokenBudget,
    attentionMode, lastActivityAt, and pendingMessages.
    Creates a default empty thread structure if none exists.
    """
    table = _get_threads_table()
    response = table.get_item(Key={"userId": user_id, "threadId": "active"})
    item = response.get("Item")

    if not item:
        return {
            "turns": [],
            "tokenEstimate": 0,
            "maxTokenBudget": _DEFAULT_TOKEN_BUDGET,
            "attentionMode": "focus",
            "lastActivityAt": "",
            "pendingMessages": [],
        }

    return {
        "turns": item.get("turns", []),
        "tokenEstimate": int(item.get("tokenEstimate", 0)),
        "maxTokenBudget": int(item.get("maxTokenBudget", _DEFAULT_TOKEN_BUDGET)),
        "attentionMode": item.get("attentionMode", "focus"),
        "lastActivityAt": item.get("lastActivityAt", ""),
        "pendingMessages": item.get("pendingMessages", []),
    }


def append_turns(user_id: str, turns: List[Dict[str, Any]]) -> int:
    """Append turns to the active thread and update token estimate.

    Creates the thread row if it doesn't exist (upsert).

    Args:
        user_id: The authenticated user's ID.
        turns: List of turn dicts to append.

    Returns:
        The new token estimate after appending.
    """
    added_tokens = sum(estimate_tokens(t.get("content", "")) for t in turns)
    now = datetime.now(timezone.utc).isoformat()

    table = _get_threads_table()
    table.update_item(
        Key={"userId": user_id, "threadId": "active"},
        UpdateExpression=(
            "SET lastActivityAt = :now, "
            "maxTokenBudget = if_not_exists(maxTokenBudget, :budget), "
            "attentionMode = if_not_exists(attentionMode, :default_mode), "
            "pendingMessages = if_not_exists(pendingMessages, :empty_list) "
            "ADD tokenEstimate :tokens "
            "SET turns = list_append(if_not_exists(turns, :empty_list), :new_turns)"
        ),
        ExpressionAttributeValues={
            ":now": now,
            ":tokens": added_tokens,
            ":new_turns": turns,
            ":budget": _DEFAULT_TOKEN_BUDGET,
            ":default_mode": "focus",
            ":empty_list": [],
        },
    )
    return added_tokens


def update_attention_mode(user_id: str, mode: str) -> None:
    """Update the attention mode on the active thread.

    Args:
        user_id: The authenticated user's ID.
        mode: One of 'explore', 'focus', 'dnd'.

    Raises:
        ValueError: If mode is not valid.
    """
    if mode not in _VALID_ATTENTION_MODES:
        raise ValueError(f"Invalid attention mode: {mode}. Must be one of {_VALID_ATTENTION_MODES}")

    table = _get_threads_table()
    table.update_item(
        Key={"userId": user_id, "threadId": "active"},
        UpdateExpression="SET attentionMode = :mode",
        ExpressionAttributeValues={":mode": mode},
    )


def add_pending_message(user_id: str, message: Dict[str, Any]) -> None:
    """Queue a proactive message for delivery on next sync.

    Used when the agent generates a proactive response but the
    WebSocket connection is not available.
    """
    table = _get_threads_table()
    table.update_item(
        Key={"userId": user_id, "threadId": "active"},
        UpdateExpression="SET pendingMessages = list_append(if_not_exists(pendingMessages, :empty), :msg)",
        ExpressionAttributeValues={
            ":msg": [message],
            ":empty": [],
        },
    )


def flush_pending_messages(user_id: str) -> List[Dict[str, Any]]:
    """Retrieve and clear pending messages.

    Returns:
        List of pending message dicts.
    """
    thread = load_active_thread(user_id)
    pending = thread.get("pendingMessages", [])
    if not pending:
        return []

    table = _get_threads_table()
    table.update_item(
        Key={"userId": user_id, "threadId": "active"},
        UpdateExpression="SET pendingMessages = :empty",
        ExpressionAttributeValues={":empty": []},
    )
    return pending


def compact_thread(
    user_id: str,
    old_turns: List[Dict[str, Any]],
    summary: str,
) -> int:
    """Archive the current thread to S3 and replace with a compacted summary.

    Args:
        user_id: The authenticated user's ID.
        old_turns: The full turn list being compacted.
        summary: The agent-generated summary text.

    Returns:
        The new token estimate (summary only).
    """
    bucket = os.environ.get("THREAD_ARCHIVE_BUCKET", "")
    now = datetime.now(timezone.utc)
    archive_id = now.strftime("%Y%m%dT%H%M%SZ")

    # Archive old turns to S3.
    if bucket:
        archive_key = f"{user_id}/{archive_id}.jsonl"
        body = "\n".join(json.dumps(t, default=str) for t in old_turns)
        try:
            s3 = boto3.client("s3")
            s3.put_object(Bucket=bucket, Key=archive_key, Body=body.encode("utf-8"))
        except Exception:
            logger.exception("Failed to archive thread to S3 for user %s", user_id)

    # Build the compacted thread.
    summary_turn = {
        "role": "system",
        "content": summary,
        "timestamp": now.isoformat(),
        "source": "compaction",
    }
    new_token_estimate = estimate_tokens(summary)

    table = _get_threads_table()
    table.put_item(
        Item={
            "userId": user_id,
            "threadId": "active",
            "turns": [summary_turn],
            "tokenEstimate": new_token_estimate,
            "maxTokenBudget": _DEFAULT_TOKEN_BUDGET,
            "attentionMode": load_active_thread(user_id).get("attentionMode", "focus"),
            "lastActivityAt": now.isoformat(),
            "pendingMessages": [],
            "compactedFrom": archive_id,
        }
    )

    # Also archive as a separate DynamoDB row for history.
    table.put_item(
        Item={
            "userId": user_id,
            "threadId": archive_id,
            "turns": [summary_turn],
            "tokenEstimate": new_token_estimate,
            "compactedFrom": archive_id,
            "lastActivityAt": now.isoformat(),
        }
    )

    return new_token_estimate
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/handlers/shared/test_thread.py -x -v`
Expected: All 7 tests pass

- [ ] **Step 6: Commit**

```bash
git add backend/handlers/shared/thread.py backend/handlers/shared/dynamodb.py tests/unit/handlers/shared/test_thread.py
git commit -m "feat: add conversation thread management module"
```

---

## Task 3: Agent Conversation History Support (Backend)

**Files:**
- Modify: `backend/agents/coaching/agent.py:107-166`
- Modify: `backend/agents/coaching/prompts.py`

- [ ] **Step 1: Update `create_coaching_agent` to accept conversation history**

In `backend/agents/coaching/agent.py`, update the function signature and body:

```python
def create_coaching_agent(
    user_id: str,
    jwt_token: str,
    callback_handler=None,
    hooks: list | None = None,
    conversation_history: list | None = None,
    attention_mode: str = "focus",
) -> Agent:
```

Pass `attention_mode` to the system prompt:

```python
    valid_tags = get_valid_skill_tags(user_id)
    system_prompt = get_system_prompt(
        valid_skill_tags=valid_tags,
        attention_mode=attention_mode,
    )
```

After constructing the Agent, if `conversation_history` is provided, load it into the agent's messages:

```python
    agent = Agent(**kwargs)

    if conversation_history:
        for turn in conversation_history:
            role = turn.get("role", "")
            content = turn.get("content", "")
            if role == "user":
                agent.messages.append({"role": "user", "content": [{"text": content}]})
            elif role == "assistant":
                agent.messages.append({"role": "assistant", "content": [{"text": content}]})

    return agent
```

- [ ] **Step 2: Add attention mode to system prompt**

In `backend/agents/coaching/prompts.py`, update the function signature:

```python
def get_system_prompt(
    valid_skill_tags: list[str] | None = None,
    attention_mode: str = "focus",
) -> str:
```

Before the `return base` at the end, add:

```python
    base += f"""## Attention Mode

Current mode: **{attention_mode}**

- **dnd** (Do Not Disturb): You should NOT have been invoked for action events in this mode. If you were invoked for a chat message, respond normally — the user can always chat regardless of mode.
- **focus**: For action events, respond ONLY if the action represents a significant milestone, a pattern break, or requires the user's attention. Otherwise respond with exactly "[no_response]". For chat messages, respond normally but be concise and analytical.
- **explore**: For action events, surface insights, connections, and encouragement. For chat messages, be thorough, proactive, and offer related context.

When you see a turn with source "action_event", that is a user action — not a chat message. Apply the attention mode rules above.
"""
```

- [ ] **Step 3: Run existing agent tests**

Run: `.venv/bin/pytest tests/unit/agents/coaching/test_agent.py -x -q`
Expected: All pass (new params have defaults, backward compatible)

- [ ] **Step 4: Commit**

```bash
git add backend/agents/coaching/agent.py backend/agents/coaching/prompts.py
git commit -m "feat: add conversation history and attention mode to coaching agent"
```

---

## Task 4: Stream Handler — Thread Loading and New Message Types (Backend)

**Files:**
- Modify: `backend/handlers/coaching/stream_handler.py`

This is the largest task. The stream handler's `_handle_default` function gets new dispatch branches for `action_event`, `compact`, `attention_mode`, and `sync`.

- [ ] **Step 1: Add thread load/save to the existing chat message path**

At the top of `_handle_default`, after extracting `user_id` and `message`, load the thread:

```python
    from backend.handlers.shared.thread import (
        load_active_thread,
        append_turns,
        update_attention_mode as set_attention_mode,
        flush_pending_messages,
        compact_thread,
        estimate_tokens,
    )

    thread = load_active_thread(user_id)
```

Before `create_coaching_agent`, pass the thread's conversation history and attention mode:

```python
            agent = create_coaching_agent(
                user_id=user_id,
                jwt_token=jwt_token,
                callback_handler=stream_callback,
                hooks=[tool_hooks],
                conversation_history=thread["turns"],
                attention_mode=thread["attentionMode"],
            )
```

After the agent returns, append the user message and assistant response as turns:

```python
        now = datetime.now(timezone.utc).isoformat()
        new_turns = [
            {"role": "user", "content": message, "timestamp": now, "source": "chat"},
            {"role": "assistant", "content": str(result), "timestamp": now, "source": "chat"},
        ]
        append_turns(user_id, new_turns)

        # Send thread metadata to frontend.
        updated_thread = load_active_thread(user_id)
        try:
            send_ws({
                "type": "thread_meta",
                "tokenEstimate": updated_thread["tokenEstimate"],
                "tokenBudget": updated_thread["maxTokenBudget"],
                "attentionMode": updated_thread["attentionMode"],
            })
        except ConnectionGoneError:
            connection_stale.set()
```

- [ ] **Step 2: Add `action_event` handler**

In `_handle_default`, after the auth check block but before the chat message processing, add dispatch for the new message types:

```python
    msg_type = body.get("type", "")

    # --- New message type dispatch ---

    if msg_type == "action_event":
        action = body.get("action", "")
        payload = body.get("payload", {})
        if not action:
            return {"statusCode": 200}

        # Append action event to thread as system turn.
        now = datetime.now(timezone.utc).isoformat()
        event_content = f"User action: {action}"
        if payload:
            details = ", ".join(f"{k}={v}" for k, v in payload.items())
            event_content += f" ({details})"

        event_turn = {"role": "system", "content": event_content, "timestamp": now, "source": "action_event"}
        append_turns(user_id, [event_turn])

        thread = load_active_thread(user_id)
        mode = thread["attentionMode"]

        # DnD: append only, no agent invocation.
        if mode == "dnd":
            return {"statusCode": 200}

        # Focus/Explore: invoke agent.
        try:
            from backend.agents.coaching.agent import create_coaching_agent

            agent = create_coaching_agent(
                user_id=user_id,
                jwt_token=body.get("token", ""),
                conversation_history=thread["turns"],
                attention_mode=mode,
            )
            result = agent(f"[action_event] {event_content}")
            response_text = str(result)

            # Filter "[no_response]" from focus mode.
            if "[no_response]" in response_text:
                return {"statusCode": 200}

            # Append assistant turn.
            append_turns(user_id, [
                {"role": "assistant", "content": response_text, "timestamp": datetime.now(timezone.utc).isoformat(), "source": "chat"},
            ])

            try:
                send_ws({"type": "proactive", "text": response_text})
            except ConnectionGoneError:
                from backend.handlers.shared.thread import add_pending_message
                add_pending_message(user_id, {"type": "proactive", "text": response_text})

        except Exception:
            slog.exception("Action event agent invocation failed for user %s", user_id)

        return {"statusCode": 200}

    if msg_type == "attention_mode":
        mode = body.get("mode", "")
        try:
            set_attention_mode(user_id, mode)
        except ValueError:
            _post_to_connection(event, connection_id, {"type": "error", "message": f"Invalid mode: {mode}"})
        return {"statusCode": 200}

    if msg_type == "compact":
        thread = load_active_thread(user_id)
        if not thread["turns"]:
            return {"statusCode": 200}

        try:
            from backend.agents.coaching.agent import create_coaching_agent

            agent = create_coaching_agent(
                user_id=user_id,
                jwt_token=body.get("token", ""),
                conversation_history=thread["turns"],
                attention_mode=thread["attentionMode"],
            )
            summary_result = agent(
                "[system] Summarize the conversation so far into the most important context needed to continue coaching this user. "
                "Preserve: active mission state, recent evidence logged, behavioral patterns observed, commitments made, and unresolved topics. "
                "Target ~15% of current thread length. Output ONLY the summary, no preamble."
            )

            new_estimate = compact_thread(user_id, thread["turns"], str(summary_result))

            send_ws({
                "type": "thread_meta",
                "tokenEstimate": new_estimate,
                "tokenBudget": thread["maxTokenBudget"],
                "attentionMode": thread["attentionMode"],
            })
        except Exception:
            slog.exception("Compaction failed for user %s", user_id)
            _post_to_connection(event, connection_id, {"type": "error", "message": "Compaction failed. Please try again."})

        return {"statusCode": 200}

    if msg_type == "sync":
        thread = load_active_thread(user_id)
        pending = flush_pending_messages(user_id)
        try:
            send_ws({
                "type": "thread_meta",
                "tokenEstimate": thread["tokenEstimate"],
                "tokenBudget": thread["maxTokenBudget"],
                "attentionMode": thread["attentionMode"],
                "pendingMessages": pending,
            })
        except ConnectionGoneError:
            pass
        return {"statusCode": 200}

    if msg_type == "auth":
        # Existing auth handling — already implemented above.
        pass  # Falls through to existing auth code.
```

- [ ] **Step 3: Add auto-compaction check before chat processing**

Before invoking the agent for a chat message, check if the thread is at budget:

```python
        # Auto-compact if at token budget.
        if thread["tokenEstimate"] >= thread["maxTokenBudget"] and thread["turns"]:
            try:
                compact_agent = create_coaching_agent(
                    user_id=user_id,
                    jwt_token=jwt_token,
                    conversation_history=thread["turns"],
                    attention_mode=thread["attentionMode"],
                )
                summary_result = compact_agent(
                    "[system] Summarize the conversation so far. Preserve: active mission state, recent evidence, behavioral patterns, commitments, unresolved topics. Output ONLY the summary."
                )
                compact_thread(user_id, thread["turns"], str(summary_result))
                thread = load_active_thread(user_id)  # Reload compacted thread.
            except Exception:
                slog.warning("Auto-compaction failed for user %s, proceeding with full thread", user_id)
```

- [ ] **Step 4: Add the datetime import at top of stream_handler.py**

```python
from datetime import datetime, timezone
```

- [ ] **Step 5: Run existing stream handler tests**

Run: `.venv/bin/pytest tests/unit/handlers/coaching/ -x -q`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add backend/handlers/coaching/stream_handler.py
git commit -m "feat: add thread persistence and action event handling to stream handler"
```

---

## Task 5: CDK Permissions — AgentStack + ApiStack

**Files:**
- Modify: `infra/stacks/agent_stack.py`
- Modify: `infra/stacks/api_stack.py`

- [ ] **Step 1: Grant ChatStream Lambda permissions in AgentStack**

In `_grant_chat_stream_lambda_permissions`, after the existing table grants, add:

```python
        if "ConversationThreads" in self.tables:
            self.tables["ConversationThreads"].grant_read_write_data(chat_stream_lambda)

        # Thread archives S3 bucket.
        thread_archive_bucket_name = cdk.Fn.import_value("RegainThreadArchivesBucketName")
        chat_stream_lambda.add_environment("CONVERSATION_THREADS_TABLE",
            self.tables["ConversationThreads"].table_name if "ConversationThreads" in self.tables else "")
        chat_stream_lambda.add_environment("THREAD_ARCHIVE_BUCKET", thread_archive_bucket_name)

        chat_stream_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["s3:PutObject"],
                resources=[f"arn:aws:s3:::regain-thread-archives-{self.account}-{self.region}/*"],
            )
        )
```

- [ ] **Step 2: Grant Coaching Lambda permissions in ApiStack**

In `_grant_permissions`, after the existing Coaching grants, add:

```python
        # Coaching: read/write ConversationThreads for thread persistence
        if "ConversationThreads" in self.tables:
            self.tables["ConversationThreads"].grant_read_write_data(lambdas["Coaching"])
```

- [ ] **Step 3: Run CDK synth**

Run: `cd infra && npx cdk synth --quiet 2>&1 | tail -5`
Expected: Successful synthesis

- [ ] **Step 4: Commit**

```bash
git add infra/stacks/agent_stack.py infra/stacks/api_stack.py
git commit -m "feat: grant thread table and archive bucket permissions to coaching Lambdas"
```

---

## Task 6: Profile Cascade Deletion

**Files:**
- Modify: `backend/handlers/profile/service.py`

- [ ] **Step 1: Add ConversationThreads to hard_delete_user_account**

After the VoiceSessions deletion (step 5) in `hard_delete_user_account`, add:

```python
        # 6. ConversationThreads — PK=userId, SK=threadId
        deleted["conversation_threads"] = self.db.delete_all_by_partition_key(
            "conversation_threads",
            partition_key_name="userId",
            partition_key_value=user_id,
            sort_key_name="threadId",
        )
```

Renumber the subsequent steps (6->7, 7->8, etc.).

After the code interpreter S3 cleanup, add:

```python
        # Thread archives S3 cleanup
        thread_archive_bucket = os.environ.get("THREAD_ARCHIVE_BUCKET", "")
        if thread_archive_bucket:
            deleted["thread_archives_s3"] = self._delete_s3_prefix(
                thread_archive_bucket, f"{user_id}/"
            )
        else:
            deleted["thread_archives_s3"] = 0
```

- [ ] **Step 2: Run cascade deletion tests**

Run: `.venv/bin/pytest tests/integration/test_cascade_deletion.py -x -v`
Expected: Existing tests pass (new table not in mocked setup, won't break existing assertions)

- [ ] **Step 3: Commit**

```bash
git add backend/handlers/profile/service.py
git commit -m "feat: add ConversationThreads and thread-archives to cascade deletion"
```

---

## Task 7: MutationBus Event Types (Frontend)

**Files:**
- Modify: `frontend/src/hooks/MutationBusContext.tsx:3`

- [ ] **Step 1: Expand the MutationEventType union**

Replace line 3:

```typescript
export type MutationEventType =
  | 'mission:completed'
  | 'mission:generated'
  | 'evidence:logged'
  | 'campaign:created'
  | 'resume:generated'
  | 'voice:session_completed'
  | 'scorecard:viewed'
  | 'profile:updated'
  | 'page:navigated';
```

Also update `MutationEvent` to carry an optional payload:

```typescript
export interface MutationEvent {
  type: MutationEventType;
  payload?: Record<string, unknown>;
}
```

Update the `emit` callback to forward the payload:

```typescript
  const emit = useCallback((event: MutationEvent) => {
    listenersRef.current.get(event.type)?.forEach((cb) => cb());
  }, []);
```

And update `subscribe` and `useOnMutation` — no changes needed since they already use `MutationEventType` and `() => void` callbacks.

- [ ] **Step 2: Run frontend build to check types**

Run: `cd frontend && npx tsc --noEmit`
Expected: No type errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/hooks/MutationBusContext.tsx
git commit -m "feat: expand MutationBus event types for action awareness"
```

---

## Task 8: Agent Event Bridge Hook (Frontend)

**Files:**
- Create: `frontend/src/hooks/useAgentEventBridge.ts`
- Test: `frontend/src/hooks/useAgentEventBridge.test.ts`

- [ ] **Step 1: Write the event bridge hook**

Create `frontend/src/hooks/useAgentEventBridge.ts`:

```typescript
import { useEffect, useRef, useCallback } from 'react';
import { useOnMutation, type MutationEventType } from './useMutationBus';

const DEDUP_WINDOW_MS = 5_000;
const BATCH_DEBOUNCE_MS = 2_000;

interface ActionEvent {
  action: MutationEventType;
  payload?: Record<string, unknown>;
  timestamp: number;
}

/**
 * Bridges MutationBus events to the coaching WebSocket as action_events.
 * Handles deduplication (same action+payload within 5s) and batching
 * (3+ events within 2s are combined into a single message).
 */
export function useAgentEventBridge(
  sendWs: ((data: Record<string, unknown>) => void) | null,
  getToken: () => Promise<string>,
) {
  const lastEventRef = useRef<{ key: string; time: number }>({ key: '', time: 0 });
  const batchRef = useRef<ActionEvent[]>([]);
  const batchTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const flush = useCallback(async () => {
    batchTimerRef.current = undefined;
    const events = batchRef.current;
    batchRef.current = [];

    if (!events.length || !sendWs) return;

    const token = await getToken();

    if (events.length >= 3) {
      // Batch: send as combined action
      sendWs({
        type: 'action_event',
        action: 'batch',
        payload: { events: events.map(e => ({ action: e.action, payload: e.payload })) },
        token,
      });
    } else {
      // Send individually
      for (const e of events) {
        sendWs({
          type: 'action_event',
          action: e.action,
          payload: e.payload || {},
          token,
        });
      }
    }
  }, [sendWs, getToken]);

  const enqueue = useCallback((action: MutationEventType, payload?: Record<string, unknown>) => {
    const now = Date.now();
    const key = `${action}:${JSON.stringify(payload || {})}`;

    // Dedup: skip if same event within window.
    if (lastEventRef.current.key === key && now - lastEventRef.current.time < DEDUP_WINDOW_MS) {
      return;
    }
    lastEventRef.current = { key, time: now };

    batchRef.current.push({ action, payload, timestamp: now });

    // Reset batch timer.
    clearTimeout(batchTimerRef.current);
    batchTimerRef.current = setTimeout(flush, BATCH_DEBOUNCE_MS);
  }, [flush]);

  // Subscribe to all action-relevant events.
  const events: MutationEventType[] = [
    'mission:completed',
    'mission:generated',
    'evidence:logged',
    'campaign:created',
    'resume:generated',
    'voice:session_completed',
    'scorecard:viewed',
    'profile:updated',
    'page:navigated',
  ];

  for (const eventType of events) {
    // eslint-disable-next-line react-hooks/rules-of-hooks
    useOnMutation(eventType, () => enqueue(eventType));
  }

  // Cleanup on unmount.
  useEffect(() => {
    return () => {
      clearTimeout(batchTimerRef.current);
    };
  }, []);
}
```

- [ ] **Step 2: Run frontend build to check types**

Run: `cd frontend && npx tsc --noEmit`
Expected: No type errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/hooks/useAgentEventBridge.ts
git commit -m "feat: add agent event bridge hook for MutationBus -> WebSocket forwarding"
```

---

## Task 9: CoachingContext — New WebSocket Message Types (Frontend)

**Files:**
- Modify: `frontend/src/hooks/CoachingContext.tsx`

- [ ] **Step 1: Add thread metadata state and new message handling**

Add new state variables after the existing ones:

```typescript
  const [tokenEstimate, setTokenEstimate] = useState(0);
  const [tokenBudget, setTokenBudget] = useState(27_000);
  const [attentionMode, setAttentionMode] = useState<'explore' | 'focus' | 'dnd'>('focus');
```

Add to `StreamEvent` type:

```typescript
interface StreamEvent {
  type: 'delta' | 'done' | 'error' | 'thinking' | 'thinking_complete' | 'heartbeat' | 'auth_success' | 'proactive' | 'thread_meta';
  text?: string;
  message?: string;
  tool?: string;
  tokenEstimate?: number;
  tokenBudget?: number;
  attentionMode?: 'explore' | 'focus' | 'dnd';
  pendingMessages?: Array<{ type: string; text: string }>;
}
```

In the `ws.onmessage` handler, add cases for the new types after the existing `auth_success` handler:

```typescript
          if (data.type === 'proactive') {
            setMessages((prev) => [
              ...prev,
              { role: 'assistant', content: data.text || '' },
            ]);
            return;
          }

          if (data.type === 'thread_meta') {
            if (data.tokenEstimate !== undefined) setTokenEstimate(data.tokenEstimate);
            if (data.tokenBudget !== undefined) setTokenBudget(data.tokenBudget);
            if (data.attentionMode) setAttentionMode(data.attentionMode);
            // Deliver any pending messages from while we were disconnected.
            if (data.pendingMessages?.length) {
              for (const msg of data.pendingMessages) {
                setMessages((prev) => [...prev, { role: 'assistant', content: msg.text }]);
              }
            }
            return;
          }
```

After `auth_success`, send sync:

```typescript
          if (data.type === 'auth_success') {
            reconnectAttempt.current = 0;
            setConnectionStatus('connected');
            setError(null);

            // Sync thread state on reconnect.
            ws.send(JSON.stringify({ type: 'sync' }));
            // ... existing auto-resend and greeting logic
```

- [ ] **Step 2: Add `sendActionEvent` and `sendCompact` and `setAttentionModeWs` to context**

Add methods that send over the WebSocket:

```typescript
  const sendActionEvent = useCallback((action: string, payload: Record<string, unknown>) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    getTokenRef.current().then(token => {
      wsRef.current?.send(JSON.stringify({ type: 'action_event', action, payload, token }));
    });
  }, []);

  const sendCompact = useCallback(async () => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    const token = await getTokenRef.current();
    wsRef.current.send(JSON.stringify({ type: 'compact', token }));
  }, []);

  const changeAttentionMode = useCallback(async (mode: 'explore' | 'focus' | 'dnd') => {
    setAttentionMode(mode);
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    wsRef.current.send(JSON.stringify({ type: 'attention_mode', mode }));
  }, []);
```

- [ ] **Step 3: Expose new state and methods via context value**

Update the `CoachingContextType` interface and Provider value to include:

```typescript
export interface CoachingContextType {
  // ... existing fields
  tokenEstimate: number;
  tokenBudget: number;
  attentionMode: 'explore' | 'focus' | 'dnd';
  sendActionEvent: (action: string, payload: Record<string, unknown>) => void;
  sendCompact: () => Promise<void>;
  changeAttentionMode: (mode: 'explore' | 'focus' | 'dnd') => Promise<void>;
}
```

- [ ] **Step 4: Mount the event bridge hook inside CoachingProvider**

Import and call `useAgentEventBridge` inside the provider component:

```typescript
import { useAgentEventBridge } from './useAgentEventBridge';

// Inside CoachingProvider, after sendActionEvent is defined:
const sendWsRaw = useCallback((data: Record<string, unknown>) => {
  if (wsRef.current?.readyState === WebSocket.OPEN) {
    wsRef.current.send(JSON.stringify(data));
  }
}, []);

useAgentEventBridge(
  connectionStatus === 'connected' ? sendWsRaw : null,
  getTokenRef.current,
);
```

- [ ] **Step 5: Run frontend build**

Run: `cd frontend && npx tsc --noEmit`
Expected: No type errors

- [ ] **Step 6: Commit**

```bash
git add frontend/src/hooks/CoachingContext.tsx
git commit -m "feat: add thread persistence, attention mode, and compaction to CoachingContext"
```

---

## Task 10: CoachModal UI — Attention Mode Toggle, Token Indicator, Compact Button (Frontend)

**Files:**
- Modify: `frontend/src/components/CoachModal.tsx`

- [ ] **Step 1: Add attention mode toggle to modal header**

Import the new context values:

```typescript
const {
  // ... existing destructuring
  tokenEstimate,
  tokenBudget,
  attentionMode,
  changeAttentionMode,
  sendCompact,
} = useCoaching();
```

Add a segmented control in the header, after the "Coach" title:

```typescript
{/* Attention mode toggle */}
<div className="flex rounded-[var(--radius-button)] border border-neutral-200 text-[10px]">
  {(['dnd', 'focus', 'explore'] as const).map((mode) => (
    <button
      key={mode}
      type="button"
      onClick={() => changeAttentionMode(mode)}
      className={`px-2 py-0.5 transition-colors first:rounded-l-[var(--radius-button)] last:rounded-r-[var(--radius-button)] ${
        attentionMode === mode
          ? 'bg-primary-500 text-white'
          : 'text-neutral-500 hover:bg-neutral-100'
      }`}
    >
      {mode === 'dnd' ? 'DnD' : mode === 'focus' ? 'Focus' : 'Explore'}
    </button>
  ))}
</div>
```

- [ ] **Step 2: Add token budget indicator**

Calculate percentage and color:

```typescript
const tokenPct = tokenBudget > 0 ? Math.round((tokenEstimate / tokenBudget) * 100) : 0;
const tokenColor = tokenPct >= 90 ? 'var(--color-error-500)' : tokenPct >= 75 ? 'var(--color-warning-500)' : 'var(--color-success-500)';
```

Add indicator next to the connection status dot:

```typescript
{/* Token budget indicator */}
<button
  type="button"
  onClick={() => { if (tokenPct > 0) sendCompact(); }}
  className="flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] hover:bg-neutral-100 transition-colors"
  title={`${tokenPct}% context used. Click to compact.`}
  disabled={tokenPct === 0}
>
  <span style={{ color: tokenColor }} className="font-mono tabular-nums">{tokenPct}%</span>
</button>
```

- [ ] **Step 3: Run frontend build and lint**

Run: `cd frontend && npx tsc --noEmit && npm run lint`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/CoachModal.tsx
git commit -m "feat: add attention mode toggle and token budget indicator to coach modal"
```

---

## Task 11: Emit New MutationBus Events from Pages

**Files:**
- Modify: `frontend/src/pages/Missions.tsx` (already emits `mission:completed`, add `mission:generated`)
- Modify: Other pages as needed for `resume:generated`, `voice:session_completed`, `profile:updated`

- [ ] **Step 1: Add `page:navigated` emission in Layout**

In `frontend/src/components/Layout.tsx`, emit a `page:navigated` event on route changes:

```typescript
import { useLocation } from 'react-router-dom';
import { useMutationBus } from '../hooks/useMutationBus';

// Inside Layout component:
const location = useLocation();
const { emit } = useMutationBus();

useEffect(() => {
  emit({ type: 'page:navigated', payload: { route: location.pathname } });
}, [location.pathname, emit]);
```

- [ ] **Step 2: Add emissions to other pages where missing**

Check each page and add `emit()` calls after successful mutations. Only add where the event isn't already emitted. For example, in Missions.tsx after a successful `generate` call:

```typescript
emit({ type: 'mission:generated', payload: { missionId: result.mission?.missionId, title: result.mission?.title } });
```

- [ ] **Step 3: Run frontend build**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/Layout.tsx frontend/src/pages/Missions.tsx
git commit -m "feat: emit MutationBus events for page navigation and mission generation"
```

---

## Task 12: Integration Test — Full Thread Lifecycle

**Files:**
- Create: `tests/integration/test_conversation_thread.py`

- [ ] **Step 1: Write integration test**

```python
"""Integration test for conversation thread lifecycle.

Tests the full flow: create thread, append turns, compact, and verify
state transitions using moto-mocked DynamoDB.
"""

import json
import os
import pytest
from moto import mock_aws
import boto3


@pytest.fixture
def thread_env(monkeypatch):
    """Set up mocked DynamoDB table for thread tests."""
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        table = ddb.create_table(
            TableName="test-threads",
            KeySchema=[
                {"AttributeName": "userId", "KeyType": "HASH"},
                {"AttributeName": "threadId", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "userId", "AttributeType": "S"},
                {"AttributeName": "threadId", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        monkeypatch.setenv("CONVERSATION_THREADS_TABLE", "test-threads")
        monkeypatch.setenv("THREAD_ARCHIVE_BUCKET", "test-archives")

        # Reset module-level cache.
        import backend.handlers.shared.thread as thread_mod
        thread_mod._threads_table = None

        yield thread_mod, table


def test_empty_thread_on_first_load(thread_env):
    mod, _ = thread_env
    result = mod.load_active_thread("user-new")
    assert result["turns"] == []
    assert result["tokenEstimate"] == 0
    assert result["attentionMode"] == "focus"


def test_append_and_reload(thread_env):
    mod, _ = thread_env
    turns = [
        {"role": "user", "content": "hello", "timestamp": "2026-04-06T00:00:00Z", "source": "chat"},
        {"role": "assistant", "content": "hi there friend", "timestamp": "2026-04-06T00:00:01Z", "source": "chat"},
    ]
    mod.append_turns("user-1", turns)
    result = mod.load_active_thread("user-1")
    assert len(result["turns"]) == 2
    assert result["tokenEstimate"] > 0
    assert result["attentionMode"] == "focus"


def test_attention_mode_persists(thread_env):
    mod, _ = thread_env
    # Create thread first.
    mod.append_turns("user-1", [{"role": "user", "content": "init", "timestamp": "t", "source": "chat"}])
    mod.update_attention_mode("user-1", "explore")
    result = mod.load_active_thread("user-1")
    assert result["attentionMode"] == "explore"


def test_pending_messages_roundtrip(thread_env):
    mod, _ = thread_env
    mod.append_turns("user-1", [{"role": "user", "content": "init", "timestamp": "t", "source": "chat"}])
    mod.add_pending_message("user-1", {"type": "proactive", "text": "Great work!"})
    mod.add_pending_message("user-1", {"type": "proactive", "text": "Keep going!"})

    pending = mod.flush_pending_messages("user-1")
    assert len(pending) == 2
    assert pending[0]["text"] == "Great work!"

    # After flush, pending should be empty.
    pending2 = mod.flush_pending_messages("user-1")
    assert pending2 == []


def test_compact_replaces_thread(thread_env):
    mod, table = thread_env
    # Build up a thread.
    for i in range(10):
        mod.append_turns("user-1", [
            {"role": "user", "content": f"message {i}" * 50, "timestamp": f"t{i}", "source": "chat"},
        ])

    before = mod.load_active_thread("user-1")
    assert len(before["turns"]) == 10
    old_estimate = before["tokenEstimate"]

    # Compact.
    new_estimate = mod.compact_thread("user-1", before["turns"], "Summary of 10 messages.")

    after = mod.load_active_thread("user-1")
    assert len(after["turns"]) == 1
    assert after["turns"][0]["source"] == "compaction"
    assert after["tokenEstimate"] < old_estimate
```

- [ ] **Step 2: Run integration tests**

Run: `.venv/bin/pytest tests/integration/test_conversation_thread.py -x -v`
Expected: All 5 tests pass

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_conversation_thread.py
git commit -m "test: add integration tests for conversation thread lifecycle"
```

---

## Task 13: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add ConversationThreads to the DynamoDB Table Keys section**

Add a new row:

```
| ConversationThreads | `userId` | `threadId` | — |
```

- [ ] **Step 2: Add relevant gotchas and architecture notes**

Add to the Architecture section or Key Decisions:

- `ConversationThreads` table: stores full ordered conversation turns (including tool calls) per user. `threadId = "active"` for the current thread, ISO timestamp for archived compactions
- Thread module: `backend/handlers/shared/thread.py` — load, append, compact, attention mode, pending messages
- Action events flow from frontend MutationBus -> WebSocket -> stream_handler -> thread table. Attention mode (dnd/focus/explore) controls whether the agent is invoked
- Token budget: ~27k tokens. Compaction at 100% auto-triggers; manual compaction via "Compact" button
- `THREAD_ARCHIVE_BUCKET` env var for S3 compaction archives

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add ConversationThreads and always-on agent to CLAUDE.md"
```
