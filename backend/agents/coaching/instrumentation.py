"""Agent-level trace instrumentation for the REGAIN Coaching Agent.

Provides lightweight span wrappers that attach to the AgentCore
Observability trace context. Gateway auto-captures routing, policy,
and Lambda spans; this module adds the agent-side spans:

- coaching_session (root span encompassing the full session)
- model_inference (captures model ID, token counts, latency)
- memory_recall / memory_store (AgentCore Memory read/write)
- tool_invocation (agent-side view of each tool call)

Tracing is enabled via the REGAIN_TRACING_ENABLED environment variable.
When disabled, all context managers are no-ops for zero overhead.

Requirements: 10.1, 10.2, 10.3, 10.4
"""

import logging
import os
import time
from contextlib import contextmanager
from typing import Any, Generator

logger = logging.getLogger(__name__)


def _tracing_enabled() -> bool:
    """Check whether tracing is enabled via environment variable."""
    return os.environ.get("REGAIN_TRACING_ENABLED", "false").lower() in (
        "true",
        "1",
        "yes",
    )


class SpanRecorder:
    """Records span attributes for a single trace span.

    Collects timing and metadata that AgentCore Observability exports
    to CloudWatch via OpenTelemetry. Spans are structured as dicts
    for easy serialization into the trace export format.
    """

    def __init__(self, span_name: str, parent_span_id: str | None = None) -> None:
        self.span_name = span_name
        self.parent_span_id = parent_span_id
        self.attributes: dict[str, Any] = {}
        self.start_time: float = 0.0
        self.end_time: float = 0.0

    def set_attribute(self, key: str, value: Any) -> None:
        """Set a span attribute."""
        self.attributes[key] = value

    def start(self) -> None:
        """Mark span start time."""
        self.start_time = time.time()

    def end(self) -> None:
        """Mark span end time and compute duration."""
        self.end_time = time.time()
        self.attributes["duration_ms"] = int(
            (self.end_time - self.start_time) * 1000
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize span to dict for trace export."""
        return {
            "span_name": self.span_name,
            "parent_span_id": self.parent_span_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "attributes": dict(self.attributes),
        }


class SessionTracer:
    """Manages trace spans for a single coaching session.

    Creates the root coaching_session span and provides context managers
    for child spans (model inference, memory ops, tool invocations).
    Collected spans are flushed to the AgentCore Observability export
    when the session ends.

    Args:
        session_id: Unique identifier for this coaching session.
        user_id: Authenticated user ID from JWT claims.
    """

    def __init__(self, session_id: str, user_id: str) -> None:
        self.session_id = session_id
        self.user_id = user_id
        self.spans: list[SpanRecorder] = []
        self._root_span: SpanRecorder | None = None
        self._active = _tracing_enabled()

    @property
    def is_active(self) -> bool:
        """Whether tracing is enabled for this session."""
        return self._active

    @contextmanager
    def coaching_session(self) -> Generator["SessionTracer", None, None]:
        """Root span encompassing the entire coaching session.

        Yields:
            This SessionTracer instance for creating child spans.

        Requirements: 10.1
        """
        if not self._active:
            yield self
            return

        span = SpanRecorder("coaching_session")
        span.set_attribute("session_id", self.session_id)
        span.set_attribute("user_id", self.user_id)
        span.start()
        self._root_span = span

        try:
            yield self
        finally:
            span.end()
            self.spans.append(span)
            self._flush_spans()

    @contextmanager
    def model_inference(
        self,
        model_id: str,
    ) -> Generator[SpanRecorder, None, None]:
        """Child span for a model inference call.

        Caller should set input_tokens, output_tokens on the yielded
        SpanRecorder after the inference completes.

        Args:
            model_id: The Bedrock model identifier.

        Yields:
            SpanRecorder to attach token counts and latency.

        Requirements: 10.2
        """
        if not self._active:
            yield SpanRecorder("model_inference")
            return

        parent_id = self._root_span.span_name if self._root_span else None
        span = SpanRecorder("model_inference", parent_span_id=parent_id)
        span.set_attribute("model_id", model_id)
        span.start()

        try:
            yield span
        finally:
            span.end()
            span.set_attribute("latency_ms", span.attributes.get("duration_ms", 0))
            self.spans.append(span)

    @contextmanager
    def memory_operation(
        self,
        operation: str,
    ) -> Generator[SpanRecorder, None, None]:
        """Child span for an AgentCore Memory read or write.

        Args:
            operation: Either "memory_recall" or "memory_store".

        Yields:
            SpanRecorder to attach operation-specific attributes.

        Requirements: 10.1
        """
        if not self._active:
            yield SpanRecorder(operation)
            return

        parent_id = self._root_span.span_name if self._root_span else None
        span = SpanRecorder(operation, parent_span_id=parent_id)
        span.set_attribute("operation", operation)
        span.start()

        try:
            yield span
        finally:
            span.end()
            self.spans.append(span)

    @contextmanager
    def tool_invocation(
        self,
        tool_name: str,
    ) -> Generator[SpanRecorder, None, None]:
        """Child span for a tool invocation (agent-side view).

        Gateway auto-captures its own routing/policy/Lambda spans.
        This span records the agent's perspective of the call.

        Args:
            tool_name: The MCP tool name being invoked.

        Yields:
            SpanRecorder to attach tool-specific attributes.

        Requirements: 10.3
        """
        if not self._active:
            yield SpanRecorder("tool_invocation")
            return

        parent_id = self._root_span.span_name if self._root_span else None
        span = SpanRecorder("tool_invocation", parent_span_id=parent_id)
        span.set_attribute("tool_name", tool_name)
        span.start()

        try:
            yield span
        finally:
            span.end()
            self.spans.append(span)

    def _flush_spans(self) -> None:
        """Export collected spans to AgentCore Observability.

        In production, this sends spans via the OpenTelemetry exporter
        configured by AgentCore. In the current implementation, spans
        are logged for the AgentCore collector to pick up.
        """
        if not self.spans:
            return

        logger.info(
            "Flushing %d trace spans for session %s",
            len(self.spans),
            self.session_id,
        )
        for span in self.spans:
            logger.debug("Span: %s", span.to_dict())

    def get_spans(self) -> list[dict[str, Any]]:
        """Return all collected spans as dicts (useful for testing)."""
        return [s.to_dict() for s in self.spans]
