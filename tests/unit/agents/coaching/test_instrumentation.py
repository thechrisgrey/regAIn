"""Unit tests for agent-level trace instrumentation (Task 7.1).

Verifies that SessionTracer creates correct span hierarchies for
coaching sessions, model inference, memory operations, and tool
invocations. Tests both enabled and disabled tracing modes.

Requirements: 10.1, 10.2, 10.3, 10.4
"""

import time

import pytest

from backend.agents.coaching.instrumentation import (
    SessionTracer,
    SpanRecorder,
    _tracing_enabled,
)


@pytest.fixture()
def _enable_tracing(monkeypatch):
    """Enable tracing via environment variable."""
    monkeypatch.setenv("REGAIN_TRACING_ENABLED", "true")


@pytest.fixture()
def _disable_tracing(monkeypatch):
    """Disable tracing via environment variable."""
    monkeypatch.setenv("REGAIN_TRACING_ENABLED", "false")


class TestTracingEnabled:
    """Tests for the _tracing_enabled helper."""

    def test_enabled_true(self, monkeypatch) -> None:
        monkeypatch.setenv("REGAIN_TRACING_ENABLED", "true")
        assert _tracing_enabled() is True

    def test_enabled_one(self, monkeypatch) -> None:
        monkeypatch.setenv("REGAIN_TRACING_ENABLED", "1")
        assert _tracing_enabled() is True

    def test_enabled_yes(self, monkeypatch) -> None:
        monkeypatch.setenv("REGAIN_TRACING_ENABLED", "yes")
        assert _tracing_enabled() is True

    def test_disabled_false(self, monkeypatch) -> None:
        monkeypatch.setenv("REGAIN_TRACING_ENABLED", "false")
        assert _tracing_enabled() is False

    def test_disabled_unset(self, monkeypatch) -> None:
        monkeypatch.delenv("REGAIN_TRACING_ENABLED", raising=False)
        assert _tracing_enabled() is False


class TestSpanRecorder:
    """Tests for the SpanRecorder data class."""

    def test_set_attribute(self) -> None:
        span = SpanRecorder("test_span")
        span.set_attribute("key", "value")
        assert span.attributes["key"] == "value"

    def test_start_end_timing(self) -> None:
        span = SpanRecorder("test_span")
        span.start()
        time.sleep(0.01)
        span.end()
        assert span.end_time > span.start_time
        assert span.attributes["duration_ms"] >= 0

    def test_to_dict(self) -> None:
        span = SpanRecorder("test_span", parent_span_id="parent")
        span.set_attribute("foo", "bar")
        span.start()
        span.end()
        d = span.to_dict()
        assert d["span_name"] == "test_span"
        assert d["parent_span_id"] == "parent"
        assert d["attributes"]["foo"] == "bar"
        assert "duration_ms" in d["attributes"]


class TestSessionTracerDisabled:
    """Tests for SessionTracer when tracing is disabled."""

    @pytest.mark.usefixtures("_disable_tracing")
    def test_is_active_false(self) -> None:
        tracer = SessionTracer("sess-1", "user-1")
        assert tracer.is_active is False

    @pytest.mark.usefixtures("_disable_tracing")
    def test_coaching_session_noop(self) -> None:
        tracer = SessionTracer("sess-1", "user-1")
        with tracer.coaching_session() as t:
            assert t is tracer
        assert len(tracer.spans) == 0

    @pytest.mark.usefixtures("_disable_tracing")
    def test_model_inference_noop(self) -> None:
        tracer = SessionTracer("sess-1", "user-1")
        with tracer.model_inference("nova-lite") as span:
            span.set_attribute("input_tokens", 100)
        assert len(tracer.spans) == 0

    @pytest.mark.usefixtures("_disable_tracing")
    def test_memory_operation_noop(self) -> None:
        tracer = SessionTracer("sess-1", "user-1")
        with tracer.memory_operation("memory_recall") as span:
            span.set_attribute("query", "test")
        assert len(tracer.spans) == 0


class TestSessionTracerEnabled:
    """Tests for SessionTracer when tracing is enabled."""

    @pytest.mark.usefixtures("_enable_tracing")
    def test_is_active_true(self) -> None:
        tracer = SessionTracer("sess-1", "user-1")
        assert tracer.is_active is True

    @pytest.mark.usefixtures("_enable_tracing")
    def test_coaching_session_root_span(self) -> None:
        """coaching_session should create a root span with session_id and user_id."""
        tracer = SessionTracer("sess-1", "user-1")
        with tracer.coaching_session():
            pass
        spans = tracer.get_spans()
        assert len(spans) == 1
        root = spans[0]
        assert root["span_name"] == "coaching_session"
        assert root["attributes"]["session_id"] == "sess-1"
        assert root["attributes"]["user_id"] == "user-1"
        assert root["attributes"]["duration_ms"] >= 0

    @pytest.mark.usefixtures("_enable_tracing")
    def test_model_inference_span(self) -> None:
        """model_inference should capture model_id and allow token count attributes."""
        tracer = SessionTracer("sess-1", "user-1")
        with tracer.coaching_session():
            with tracer.model_inference("amazon.nova-lite-v1:0") as span:
                span.set_attribute("input_tokens", 150)
                span.set_attribute("output_tokens", 200)

        spans = tracer.get_spans()
        inference_spans = [s for s in spans if s["span_name"] == "model_inference"]
        assert len(inference_spans) == 1
        inf = inference_spans[0]
        assert inf["attributes"]["model_id"] == "amazon.nova-lite-v1:0"
        assert inf["attributes"]["input_tokens"] == 150
        assert inf["attributes"]["output_tokens"] == 200
        assert inf["attributes"]["latency_ms"] >= 0
        assert inf["parent_span_id"] == "coaching_session"

    @pytest.mark.usefixtures("_enable_tracing")
    def test_memory_recall_span(self) -> None:
        """memory_operation('memory_recall') should create a child span."""
        tracer = SessionTracer("sess-1", "user-1")
        with tracer.coaching_session():
            with tracer.memory_operation("memory_recall") as span:
                span.set_attribute("query", "recent sessions")

        spans = tracer.get_spans()
        mem_spans = [s for s in spans if s["span_name"] == "memory_recall"]
        assert len(mem_spans) == 1
        assert mem_spans[0]["attributes"]["operation"] == "memory_recall"
        assert mem_spans[0]["parent_span_id"] == "coaching_session"

    @pytest.mark.usefixtures("_enable_tracing")
    def test_memory_store_span(self) -> None:
        """memory_operation('memory_store') should create a child span."""
        tracer = SessionTracer("sess-1", "user-1")
        with tracer.coaching_session():
            with tracer.memory_operation("memory_store") as span:
                span.set_attribute("content_length", 256)

        spans = tracer.get_spans()
        mem_spans = [s for s in spans if s["span_name"] == "memory_store"]
        assert len(mem_spans) == 1
        assert mem_spans[0]["attributes"]["operation"] == "memory_store"

    @pytest.mark.usefixtures("_enable_tracing")
    def test_tool_invocation_span(self) -> None:
        """tool_invocation should create a child span with tool_name."""
        tracer = SessionTracer("sess-1", "user-1")
        with tracer.coaching_session():
            with tracer.tool_invocation("regain_read_user_profile") as span:
                span.set_attribute("gateway_routing_ms", 12)
                span.set_attribute("policy_result", "permit")

        spans = tracer.get_spans()
        tool_spans = [s for s in spans if s["span_name"] == "tool_invocation"]
        assert len(tool_spans) == 1
        assert tool_spans[0]["attributes"]["tool_name"] == "regain_read_user_profile"
        assert tool_spans[0]["parent_span_id"] == "coaching_session"

    @pytest.mark.usefixtures("_enable_tracing")
    def test_full_session_trace_hierarchy(self) -> None:
        """A full session should produce the expected span hierarchy."""
        tracer = SessionTracer("sess-1", "user-1")
        with tracer.coaching_session():
            with tracer.memory_operation("memory_recall"):
                pass
            with tracer.model_inference("amazon.nova-lite-v1:0") as inf:
                inf.set_attribute("input_tokens", 100)
                inf.set_attribute("output_tokens", 50)
            with tracer.tool_invocation("regain_get_campaign_status"):
                pass
            with tracer.memory_operation("memory_store"):
                pass

        spans = tracer.get_spans()
        span_names = [s["span_name"] for s in spans]
        assert "memory_recall" in span_names
        assert "model_inference" in span_names
        assert "tool_invocation" in span_names
        assert "memory_store" in span_names
        assert "coaching_session" in span_names
        # Root span is last (appended in finally block of coaching_session)
        assert spans[-1]["span_name"] == "coaching_session"

    @pytest.mark.usefixtures("_enable_tracing")
    def test_multiple_tool_invocations(self) -> None:
        """Multiple tool invocations should each get their own span."""
        tracer = SessionTracer("sess-1", "user-1")
        with tracer.coaching_session():
            with tracer.tool_invocation("regain_read_user_profile"):
                pass
            with tracer.tool_invocation("regain_get_campaign_status"):
                pass

        spans = tracer.get_spans()
        tool_spans = [s for s in spans if s["span_name"] == "tool_invocation"]
        assert len(tool_spans) == 2
        tool_names = {s["attributes"]["tool_name"] for s in tool_spans}
        assert tool_names == {"regain_read_user_profile", "regain_get_campaign_status"}
