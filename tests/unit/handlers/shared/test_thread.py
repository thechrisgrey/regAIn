"""Unit tests for thread.py — conversation thread management."""

import json
import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

# Reset module-level state before importing
import sys
if "backend.handlers.shared.thread" in sys.modules:
    del sys.modules["backend.handlers.shared.thread"]

import backend.handlers.shared.thread as thread_mod


@pytest.fixture(autouse=True)
def reset_module_state():
    """Reset module-level table reference between tests."""
    thread_mod._threads_table = None
    yield
    thread_mod._threads_table = None


@pytest.fixture(autouse=True)
def set_env_vars(monkeypatch):
    """Set required environment variables for all tests."""
    monkeypatch.setenv("CONVERSATION_THREADS_TABLE", "test-threads")
    monkeypatch.setenv("THREAD_ARCHIVE_BUCKET", "test-archives")


# --- estimate_tokens tests ---


def test_estimate_tokens_empty_string():
    """Empty string returns 0 tokens."""
    assert thread_mod.estimate_tokens("") == 0


def test_estimate_tokens_hello_world():
    """'hello world' (11 chars) returns 2 tokens."""
    assert thread_mod.estimate_tokens("hello world") == 2


def test_estimate_tokens_400_chars():
    """400 chars returns 100 tokens."""
    content = "a" * 400
    assert thread_mod.estimate_tokens(content) == 100


# --- load_active_thread tests ---


@patch("backend.handlers.shared.thread._get_threads_table")
def test_load_active_thread_not_exists(mock_get_table):
    """Returns empty defaults when thread does not exist."""
    mock_table = MagicMock()
    mock_table.get_item.return_value = {}
    mock_get_table.return_value = mock_table

    result = thread_mod.load_active_thread("user123")

    mock_table.get_item.assert_called_once_with(Key={"userId": "user123", "threadId": "active"})
    assert result == {
        "turns": [],
        "tokenEstimate": 0,
        "maxTokenBudget": 27_000,
        "attentionMode": "focus",
        "lastActivityAt": "",
        "pendingMessages": [],
    }


@patch("backend.handlers.shared.thread._get_threads_table")
def test_load_active_thread_exists(mock_get_table):
    """Returns existing thread data from DynamoDB."""
    mock_table = MagicMock()
    mock_table.get_item.return_value = {
        "Item": {
            "userId": "user123",
            "threadId": "active",
            "turns": [{"role": "user", "content": "hello"}],
            "tokenEstimate": 500,
            "maxTokenBudget": 30_000,
            "attentionMode": "explore",
            "lastActivityAt": "2026-04-06T12:00:00Z",
            "pendingMessages": [{"type": "reminder", "text": "check this"}],
        }
    }
    mock_get_table.return_value = mock_table

    result = thread_mod.load_active_thread("user123")

    assert result["turns"] == [{"role": "user", "content": "hello"}]
    assert result["tokenEstimate"] == 500
    assert result["maxTokenBudget"] == 30_000
    assert result["attentionMode"] == "explore"
    assert result["lastActivityAt"] == "2026-04-06T12:00:00Z"
    assert result["pendingMessages"] == [{"type": "reminder", "text": "check this"}]


# --- append_turns tests ---


@patch("backend.handlers.shared.thread._get_threads_table")
def test_append_turns_single_turn(mock_get_table):
    """Appends a single turn and returns added tokens."""
    mock_table = MagicMock()
    mock_get_table.return_value = mock_table

    turns = [{"role": "user", "content": "test"}]
    added = thread_mod.append_turns("user123", turns)

    # "test" = 4 chars = 1 token
    assert added == 1
    mock_table.update_item.assert_called_once()
    call_kwargs = mock_table.update_item.call_args.kwargs
    assert call_kwargs["Key"] == {"userId": "user123", "threadId": "active"}
    assert ":tokens" in call_kwargs["ExpressionAttributeValues"]
    assert call_kwargs["ExpressionAttributeValues"][":tokens"] == 1
    assert call_kwargs["ExpressionAttributeValues"][":new_turns"] == turns


@patch("backend.handlers.shared.thread._get_threads_table")
def test_append_turns_multiple_turns(mock_get_table):
    """Appends multiple turns and sums tokens."""
    mock_table = MagicMock()
    mock_get_table.return_value = mock_table

    turns = [
        {"role": "user", "content": "hello"},  # 5 chars = 1 token
        {"role": "assistant", "content": "world!"},  # 6 chars = 1 token
    ]
    added = thread_mod.append_turns("user123", turns)

    assert added == 2
    mock_table.update_item.assert_called_once()


# --- update_attention_mode tests ---


@patch("backend.handlers.shared.thread._get_threads_table")
def test_update_attention_mode_valid(mock_get_table):
    """Updates attention mode with valid value."""
    mock_table = MagicMock()
    mock_get_table.return_value = mock_table

    thread_mod.update_attention_mode("user123", "dnd")

    mock_table.update_item.assert_called_once()
    call_kwargs = mock_table.update_item.call_args.kwargs
    assert call_kwargs["Key"] == {"userId": "user123", "threadId": "active"}
    assert call_kwargs["ExpressionAttributeValues"][":mode"] == "dnd"


@patch("backend.handlers.shared.thread._get_threads_table")
def test_update_attention_mode_invalid(mock_get_table):
    """Raises ValueError for invalid attention mode."""
    mock_table = MagicMock()
    mock_get_table.return_value = mock_table

    with pytest.raises(ValueError, match="Invalid attention mode: invalid"):
        thread_mod.update_attention_mode("user123", "invalid")

    mock_table.update_item.assert_not_called()


# --- add_pending_message tests ---


@patch("backend.handlers.shared.thread._get_threads_table")
def test_add_pending_message(mock_get_table):
    """Appends a message to pendingMessages list."""
    mock_table = MagicMock()
    mock_get_table.return_value = mock_table

    message = {"type": "reminder", "text": "check this"}
    thread_mod.add_pending_message("user123", message)

    mock_table.update_item.assert_called_once()
    call_kwargs = mock_table.update_item.call_args.kwargs
    assert call_kwargs["Key"] == {"userId": "user123", "threadId": "active"}
    assert call_kwargs["ExpressionAttributeValues"][":msg"] == [message]


# --- flush_pending_messages tests ---


@patch("backend.handlers.shared.thread._get_threads_table")
def test_flush_pending_messages_with_pending(mock_get_table):
    """Retrieves and clears pending messages."""
    mock_table = MagicMock()
    mock_table.get_item.return_value = {
        "Item": {
            "userId": "user123",
            "threadId": "active",
            "turns": [],
            "tokenEstimate": 0,
            "maxTokenBudget": 27_000,
            "attentionMode": "focus",
            "lastActivityAt": "",
            "pendingMessages": [{"type": "reminder", "text": "check this"}],
        }
    }
    mock_get_table.return_value = mock_table

    result = thread_mod.flush_pending_messages("user123")

    assert result == [{"type": "reminder", "text": "check this"}]
    mock_table.update_item.assert_called_once()
    call_kwargs = mock_table.update_item.call_args.kwargs
    assert call_kwargs["ExpressionAttributeValues"][":empty"] == []


@patch("backend.handlers.shared.thread._get_threads_table")
def test_flush_pending_messages_empty(mock_get_table):
    """Returns empty list when no pending messages."""
    mock_table = MagicMock()
    mock_table.get_item.return_value = {
        "Item": {
            "userId": "user123",
            "threadId": "active",
            "turns": [],
            "tokenEstimate": 0,
            "maxTokenBudget": 27_000,
            "attentionMode": "focus",
            "lastActivityAt": "",
            "pendingMessages": [],
        }
    }
    mock_get_table.return_value = mock_table

    result = thread_mod.flush_pending_messages("user123")

    assert result == []
    mock_table.update_item.assert_not_called()


# --- compact_thread tests ---


@patch("backend.handlers.shared.thread.boto3")
@patch("backend.handlers.shared.thread._get_threads_table")
def test_compact_thread_archives_to_s3_and_replaces_thread(mock_get_table, mock_boto3):
    """Archives old turns to S3 and replaces active thread with summary."""
    # Mock S3
    mock_s3 = MagicMock()
    mock_boto3.client.return_value = mock_s3

    # Mock DynamoDB
    mock_table = MagicMock()
    # First call: load_active_thread inside compact_thread
    mock_table.get_item.return_value = {
        "Item": {
            "userId": "user123",
            "threadId": "active",
            "turns": [{"role": "user", "content": "old message"}],
            "tokenEstimate": 100,
            "maxTokenBudget": 27_000,
            "attentionMode": "dnd",
            "lastActivityAt": "2026-04-05T12:00:00Z",
            "pendingMessages": [],
        }
    }
    mock_get_table.return_value = mock_table

    old_turns = [
        {"role": "user", "content": "turn 1"},
        {"role": "assistant", "content": "turn 2"},
    ]
    summary = "This is a summary"  # 18 chars = 4 tokens

    result = thread_mod.compact_thread("user123", old_turns, summary)

    # Check return value
    assert result == 4

    # Check S3 upload
    mock_s3.put_object.assert_called_once()
    s3_call = mock_s3.put_object.call_args.kwargs
    assert s3_call["Bucket"] == "test-archives"
    assert s3_call["Key"].startswith("user123/")
    assert s3_call["Key"].endswith(".jsonl")
    body = s3_call["Body"].decode("utf-8")
    lines = body.strip().split("\n")
    assert len(lines) == 2
    assert json.loads(lines[0])["role"] == "user"
    assert json.loads(lines[1])["role"] == "assistant"

    # Check DynamoDB put_item calls (2 total: active + archive)
    assert mock_table.put_item.call_count == 2

    # First call: replace active thread
    first_call = mock_table.put_item.call_args_list[0].kwargs
    active_item = first_call["Item"]
    assert active_item["userId"] == "user123"
    assert active_item["threadId"] == "active"
    assert len(active_item["turns"]) == 1
    assert active_item["turns"][0]["role"] == "system"
    assert active_item["turns"][0]["content"] == summary
    assert active_item["turns"][0]["source"] == "compaction"
    assert active_item["tokenEstimate"] == 4
    assert active_item["attentionMode"] == "dnd"  # Preserved from current thread
    assert active_item["pendingMessages"] == []

    # Second call: archive row
    second_call = mock_table.put_item.call_args_list[1].kwargs
    archive_item = second_call["Item"]
    assert archive_item["userId"] == "user123"
    assert archive_item["threadId"] != "active"
    assert len(archive_item["turns"]) == 1
    assert archive_item["turns"][0]["content"] == summary


@patch("backend.handlers.shared.thread.boto3")
@patch("backend.handlers.shared.thread._get_threads_table")
def test_compact_thread_no_bucket_env_var(mock_get_table, mock_boto3, monkeypatch):
    """Skips S3 archival when THREAD_ARCHIVE_BUCKET is not set."""
    monkeypatch.setenv("THREAD_ARCHIVE_BUCKET", "")

    # Mock DynamoDB
    mock_table = MagicMock()
    mock_table.get_item.return_value = {
        "Item": {
            "userId": "user123",
            "threadId": "active",
            "turns": [],
            "tokenEstimate": 0,
            "maxTokenBudget": 27_000,
            "attentionMode": "focus",
            "lastActivityAt": "",
            "pendingMessages": [],
        }
    }
    mock_get_table.return_value = mock_table

    old_turns = [{"role": "user", "content": "test"}]
    summary = "summary"

    thread_mod.compact_thread("user123", old_turns, summary)

    # S3 should not be called
    mock_boto3.client.assert_not_called()

    # DynamoDB put_item should still be called
    assert mock_table.put_item.call_count == 2


@patch("backend.handlers.shared.thread.boto3")
@patch("backend.handlers.shared.thread._get_threads_table")
def test_compact_thread_s3_failure_logs_and_continues(mock_get_table, mock_boto3):
    """Logs S3 failure but continues with DynamoDB operations."""
    # Mock S3 to raise exception
    mock_s3 = MagicMock()
    mock_s3.put_object.side_effect = Exception("S3 error")
    mock_boto3.client.return_value = mock_s3

    # Mock DynamoDB
    mock_table = MagicMock()
    mock_table.get_item.return_value = {
        "Item": {
            "userId": "user123",
            "threadId": "active",
            "turns": [],
            "tokenEstimate": 0,
            "maxTokenBudget": 27_000,
            "attentionMode": "focus",
            "lastActivityAt": "",
            "pendingMessages": [],
        }
    }
    mock_get_table.return_value = mock_table

    old_turns = [{"role": "user", "content": "test"}]
    summary = "summary"

    # Should not raise
    result = thread_mod.compact_thread("user123", old_turns, summary)

    assert result == 1  # len("summary") // 4
    # DynamoDB operations should still proceed
    assert mock_table.put_item.call_count == 2


# --- _get_threads_table tests ---


def test_get_threads_table_missing_env_var(monkeypatch):
    """Raises ValueError when CONVERSATION_THREADS_TABLE is not set."""
    monkeypatch.delenv("CONVERSATION_THREADS_TABLE", raising=False)
    thread_mod._threads_table = None  # Reset cached value

    with pytest.raises(ValueError, match="CONVERSATION_THREADS_TABLE environment variable not set"):
        thread_mod._get_threads_table()


@patch("backend.handlers.shared.thread.boto3")
def test_get_threads_table_lazy_initialization(mock_boto3):
    """Table is lazily initialized and cached."""
    mock_resource = MagicMock()
    mock_table = MagicMock()
    mock_resource.Table.return_value = mock_table
    mock_boto3.resource.return_value = mock_resource

    # First call
    result1 = thread_mod._get_threads_table()
    assert result1 == mock_table
    mock_boto3.resource.assert_called_once_with("dynamodb")
    mock_resource.Table.assert_called_once_with("test-threads")

    # Second call should use cached value
    result2 = thread_mod._get_threads_table()
    assert result2 == mock_table
    # boto3.resource should still only be called once
    assert mock_boto3.resource.call_count == 1
