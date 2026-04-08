"""Conversation thread management for the coaching agent.

Provides CRUD operations on the ConversationThreads DynamoDB table,
token estimation, compaction (summarization + S3 archival), and
attention mode management.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List

import boto3

logger = logging.getLogger(__name__)

_DEFAULT_TOKEN_BUDGET = 27_000
_VALID_ATTENTION_MODES = {"explore", "dnd"}

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
    """Approximate token count from string length."""
    return len(content) // 4


def load_active_thread(user_id: str) -> Dict[str, Any]:
    """Load the active conversation thread for a user.

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
            "attentionMode": "explore",
            "lastActivityAt": "",
            "pendingMessages": [],
        }

    return {
        "turns": item.get("turns", []),
        "tokenEstimate": int(item.get("tokenEstimate", 0)),
        "maxTokenBudget": int(item.get("maxTokenBudget", _DEFAULT_TOKEN_BUDGET)),
        "attentionMode": item.get("attentionMode", "explore"),
        "lastActivityAt": item.get("lastActivityAt", ""),
        "pendingMessages": item.get("pendingMessages", []),
    }


def append_turns(user_id: str, turns: List[Dict[str, Any]]) -> int:
    """Append turns to the active thread and update token estimate.

    Creates the thread row if it doesn't exist (upsert).

    Returns:
        The added token count.
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
            "pendingMessages = if_not_exists(pendingMessages, :empty_list), "
            "turns = list_append(if_not_exists(turns, :empty_list), :new_turns) "
            "ADD tokenEstimate :tokens"
        ),
        ExpressionAttributeValues={
            ":now": now,
            ":tokens": added_tokens,
            ":new_turns": turns,
            ":budget": _DEFAULT_TOKEN_BUDGET,
            ":default_mode": "explore",
            ":empty_list": [],
        },
    )
    return added_tokens


def update_attention_mode(user_id: str, mode: str) -> None:
    """Update the attention mode on the active thread.

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
    """Queue a proactive message for delivery on next sync."""
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
    """Retrieve and clear pending messages."""
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

    # Preserve the current attention mode.
    current_thread = load_active_thread(user_id)
    current_mode = current_thread.get("attentionMode", "explore")

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
            "attentionMode": current_mode,
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
