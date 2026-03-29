"""Property-based tests for trace span completeness.

# Feature: agentcore-platform-integration, Property 12: Trace span completeness

**Validates: Requirements 10.2, 10.3**

For any model inference operation, the trace span SHALL contain model ID,
input token count, output token count, and inference latency. For any tool
invocation routed through Gateway, the trace span SHALL contain tool name
(and other attributes set by the caller). For any coaching session, the root
span SHALL contain session_id, user_id, and duration_ms. For any memory
operation, the span SHALL contain the operation attribute.

Strategy:
- Use the actual SessionTracer from instrumentation.py.
- Generate random model IDs, token counts, tool names, latency values.
- Create sessions with random combinations of operations.
- Verify each span type contains its required fields.
- Enable tracing via os.environ before creating SessionTracer instances.
"""

import os
from typing import Any

from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from backend.agents.coaching.instrumentation import SessionTracer


# ---------------------------------------------------------------------------
# Enable tracing globally for this test module
# ---------------------------------------------------------------------------
os.environ["REGAIN_TRACING_ENABLED"] = "true"


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALL_TOOL_NAMES: list[str] = [
    "regain_read_user_profile",
    "regain_update_user_profile",
    "regain_get_campaign_status",
    "regain_create_campaign",
    "regain_get_current_mission",
    "regain_generate_mission",
    "regain_complete_mission",
    "regain_log_evidence",
    "regain_get_evidence_summary",
    "regain_get_market_insights",
    "regain_get_alignment",
    "regain_recall_memory",
]

MODEL_IDS: list[str] = [
    "amazon.nova-lite-v1:0",
    "amazon.nova-sonic-v1:0",
    "amazon.nova-pro-v1:0",
    "anthropic.claude-3-haiku-20240307-v1:0",
]

MEMORY_OPERATIONS: list[str] = ["memory_recall", "memory_store"]


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

_session_id = st.text(
    min_size=1,
    max_size=40,
    alphabet=st.characters(whitelist_categories=("L", "N", "Pd")),
)

_user_id = st.text(
    min_size=1,
    max_size=40,
    alphabet=st.characters(whitelist_categories=("L", "N", "Pd")),
)

_model_id = st.sampled_from(MODEL_IDS)
_tool_name = st.sampled_from(ALL_TOOL_NAMES)
_memory_op = st.sampled_from(MEMORY_OPERATIONS)

_token_count = st.integers(min_value=0, max_value=100_000)
_latency_ms = st.integers(min_value=0, max_value=30_000)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_spans(spans: list[dict[str, Any]], name: str) -> list[dict[str, Any]]:
    """Filter spans by span_name."""
    return [s for s in spans if s["span_name"] == name]


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------


class TestTraceSpanCompleteness:
    """Property 12: Trace span completeness.

    For random operations, verify trace spans contain required fields
    per operation type.
    """

    @given(
        session_id=_session_id,
        user_id=_user_id,
        model_id=_model_id,
        input_tokens=_token_count,
        output_tokens=_token_count,
    )
    @settings(max_examples=100)
    def test_model_inference_spans_contain_required_fields(
        self,
        session_id: str,
        user_id: str,
        model_id: str,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        """Model inference spans SHALL contain model_id, input_tokens,
        output_tokens, and latency_ms.

        # Feature: agentcore-platform-integration, Property 12: Trace span completeness
        **Validates: Requirements 10.2, 10.3**
        """
        tracer = SessionTracer(session_id, user_id)
        with tracer.coaching_session():
            with tracer.model_inference(model_id) as span:
                span.set_attribute("input_tokens", input_tokens)
                span.set_attribute("output_tokens", output_tokens)

        spans = tracer.get_spans()
        inference_spans = _find_spans(spans, "model_inference")
        assert len(inference_spans) == 1

        attrs = inference_spans[0]["attributes"]
        assert attrs["model_id"] == model_id
        assert attrs["input_tokens"] == input_tokens
        assert attrs["output_tokens"] == output_tokens
        assert "latency_ms" in attrs
        assert isinstance(attrs["latency_ms"], int)

    @given(
        session_id=_session_id,
        user_id=_user_id,
        tool_name=_tool_name,
        gateway_routing_ms=_latency_ms,
        policy_result=st.sampled_from(["permit", "deny"]),
        lambda_execution_ms=_latency_ms,
        dynamodb_operation_ms=_latency_ms,
    )
    @settings(max_examples=100)
    def test_tool_invocation_spans_contain_required_fields(
        self,
        session_id: str,
        user_id: str,
        tool_name: str,
        gateway_routing_ms: int,
        policy_result: str,
        lambda_execution_ms: int,
        dynamodb_operation_ms: int,
    ) -> None:
        """Tool invocation spans SHALL contain tool_name, gateway_routing_ms,
        policy_result, lambda_execution_ms, and dynamodb_operation_ms.

        # Feature: agentcore-platform-integration, Property 12: Trace span completeness
        **Validates: Requirements 10.2, 10.3**
        """
        tracer = SessionTracer(session_id, user_id)
        with tracer.coaching_session():
            with tracer.tool_invocation(tool_name) as span:
                span.set_attribute("gateway_routing_ms", gateway_routing_ms)
                span.set_attribute("policy_result", policy_result)
                span.set_attribute("lambda_execution_ms", lambda_execution_ms)
                span.set_attribute("dynamodb_operation_ms", dynamodb_operation_ms)

        spans = tracer.get_spans()
        tool_spans = _find_spans(spans, "tool_invocation")
        assert len(tool_spans) == 1

        attrs = tool_spans[0]["attributes"]
        assert attrs["tool_name"] == tool_name
        assert attrs["gateway_routing_ms"] == gateway_routing_ms
        assert attrs["policy_result"] == policy_result
        assert attrs["lambda_execution_ms"] == lambda_execution_ms
        assert attrs["dynamodb_operation_ms"] == dynamodb_operation_ms

    @given(session_id=_session_id, user_id=_user_id)
    @settings(max_examples=100)
    def test_coaching_session_root_span_contains_required_fields(
        self,
        session_id: str,
        user_id: str,
    ) -> None:
        """Coaching session root span SHALL contain session_id, user_id,
        and duration_ms.

        # Feature: agentcore-platform-integration, Property 12: Trace span completeness
        **Validates: Requirements 10.2, 10.3**
        """
        tracer = SessionTracer(session_id, user_id)
        with tracer.coaching_session():
            pass

        spans = tracer.get_spans()
        root_spans = _find_spans(spans, "coaching_session")
        assert len(root_spans) == 1

        attrs = root_spans[0]["attributes"]
        assert attrs["session_id"] == session_id
        assert attrs["user_id"] == user_id
        assert "duration_ms" in attrs

    @given(
        session_id=_session_id,
        user_id=_user_id,
        operation=_memory_op,
    )
    @settings(max_examples=100)
    def test_memory_operation_spans_contain_required_fields(
        self,
        session_id: str,
        user_id: str,
        operation: str,
    ) -> None:
        """Memory operation spans SHALL contain the operation attribute.

        # Feature: agentcore-platform-integration, Property 12: Trace span completeness
        **Validates: Requirements 10.2, 10.3**
        """
        tracer = SessionTracer(session_id, user_id)
        with tracer.coaching_session():
            with tracer.memory_operation(operation):
                pass

        spans = tracer.get_spans()
        mem_spans = _find_spans(spans, operation)
        assert len(mem_spans) == 1

        attrs = mem_spans[0]["attributes"]
        assert attrs["operation"] == operation
        assert "duration_ms" in attrs

    @given(
        session_id=_session_id,
        user_id=_user_id,
        model_id=_model_id,
        input_tokens=_token_count,
        output_tokens=_token_count,
        tool_names=st.lists(_tool_name, min_size=1, max_size=4),
        mem_ops=st.lists(_memory_op, min_size=0, max_size=2),
    )
    @settings(max_examples=100)
    def test_mixed_session_all_spans_have_required_fields(
        self,
        session_id: str,
        user_id: str,
        model_id: str,
        input_tokens: int,
        output_tokens: int,
        tool_names: list[str],
        mem_ops: list[str],
    ) -> None:
        """A session with random combinations of operations produces spans
        that all contain their required fields.

        # Feature: agentcore-platform-integration, Property 12: Trace span completeness
        **Validates: Requirements 10.2, 10.3**
        """
        tracer = SessionTracer(session_id, user_id)
        with tracer.coaching_session():
            for op in mem_ops:
                if op == "memory_recall":
                    with tracer.memory_operation("memory_recall"):
                        pass

            with tracer.model_inference(model_id) as inf_span:
                inf_span.set_attribute("input_tokens", input_tokens)
                inf_span.set_attribute("output_tokens", output_tokens)

            for tn in tool_names:
                with tracer.tool_invocation(tn) as t_span:
                    t_span.set_attribute("gateway_routing_ms", 10)
                    t_span.set_attribute("policy_result", "permit")
                    t_span.set_attribute("lambda_execution_ms", 50)
                    t_span.set_attribute("dynamodb_operation_ms", 5)

            for op in mem_ops:
                if op == "memory_store":
                    with tracer.memory_operation("memory_store"):
                        pass

        spans = tracer.get_spans()

        # Root span
        root = _find_spans(spans, "coaching_session")
        assert len(root) == 1
        assert root[0]["attributes"]["session_id"] == session_id
        assert root[0]["attributes"]["user_id"] == user_id
        assert "duration_ms" in root[0]["attributes"]

        # Model inference span
        inf_spans = _find_spans(spans, "model_inference")
        assert len(inf_spans) == 1
        assert inf_spans[0]["attributes"]["model_id"] == model_id
        assert inf_spans[0]["attributes"]["input_tokens"] == input_tokens
        assert inf_spans[0]["attributes"]["output_tokens"] == output_tokens
        assert "latency_ms" in inf_spans[0]["attributes"]

        # Tool invocation spans
        t_spans = _find_spans(spans, "tool_invocation")
        assert len(t_spans) == len(tool_names)
        for ts in t_spans:
            assert "tool_name" in ts["attributes"]
            assert "gateway_routing_ms" in ts["attributes"]
            assert "policy_result" in ts["attributes"]
            assert "lambda_execution_ms" in ts["attributes"]
            assert "dynamodb_operation_ms" in ts["attributes"]

        # All child spans have correct parent
        for s in spans:
            if s["span_name"] != "coaching_session":
                assert s["parent_span_id"] == "coaching_session"
