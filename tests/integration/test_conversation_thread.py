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
def thread_env(monkeypatch, aws_credentials):
    """Set up mocked DynamoDB table for thread tests."""
    with mock_aws():
        monkeypatch.setenv("CONVERSATION_THREADS_TABLE", "test-threads")
        monkeypatch.setenv("THREAD_ARCHIVE_BUCKET", "test-archives")

        # Reset module-level cache BEFORE creating the table so it picks up the mocked resource.
        import backend.handlers.shared.thread as thread_mod
        thread_mod._threads_table = None

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

        # Create S3 bucket for archive testing.
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="test-archives")

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

    pending2 = mod.flush_pending_messages("user-1")
    assert pending2 == []


def test_compact_replaces_thread(thread_env):
    mod, table = thread_env
    for i in range(10):
        mod.append_turns("user-1", [
            {"role": "user", "content": f"message {i}" * 50, "timestamp": f"t{i}", "source": "chat"},
        ])

    before = mod.load_active_thread("user-1")
    assert len(before["turns"]) == 10
    old_estimate = before["tokenEstimate"]

    new_estimate = mod.compact_thread("user-1", before["turns"], "Summary of 10 messages.")

    after = mod.load_active_thread("user-1")
    assert len(after["turns"]) == 1
    assert after["turns"][0]["source"] == "compaction"
    assert after["tokenEstimate"] < old_estimate
