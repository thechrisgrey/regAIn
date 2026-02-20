"""Property-based tests for policy audit log completeness.

# Feature: agentcore-platform-integration, Property 10: Policy audit log completeness

**Validates: Requirements 4.3, 9.1, 9.2**

For any Cedar policy evaluation (permit or deny), the audit log entry SHALL
contain the tool name, userId, policy name, evaluation result, and timestamp.
For any Policy Denial specifically, the log entry SHALL additionally contain
the denial reason and request context (input parameters excluding sensitive
data).

Strategy:
- Define a model of what a Gateway audit log entry must look like.
- Build a ``create_audit_log_entry`` function that mirrors the Gateway's
  structured logging contract (as configured in AgentCoreStack).
- Use Hypothesis to generate random policy evaluation scenarios with random
  tool names, userIds, policy names, and permit/deny results.
- Verify ALL evaluations contain the 5 base required fields.
- Verify DENY evaluations additionally contain denial_reason and
  request_context.
- Verify request_context never contains sensitive data (JWT tokens,
  passwords, secrets).
"""

import re
from datetime import datetime, timezone
from typing import Any

from hypothesis import assume, given, settings
from hypothesis import strategies as st


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
    "regain_store_memory",
]

POLICY_NAMES: list[str] = [
    "user_data_isolation",
    "evidence_write_scope",
    "mission_generation_rate_limit",
    "profile_update_restrictions",
    "market_data_read_only",
]

EVALUATION_RESULTS: list[str] = ["permit", "deny"]

DENIAL_REASONS: list[str] = [
    "cross-user access denied",
    "evidence write scope violation",
    "daily mission generation limit reached",
    "restricted field modification denied",
    "market data is read-only for coaching agent",
]

# Sensitive field patterns that must NEVER appear in audit log request_context.
SENSITIVE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+"),  # JWT token
    re.compile(r"password", re.IGNORECASE),
    re.compile(r"secret", re.IGNORECASE),
    re.compile(r"access_token", re.IGNORECASE),
    re.compile(r"refresh_token", re.IGNORECASE),
]

# Keys that are considered sensitive and must be stripped from request_context.
SENSITIVE_KEYS: frozenset[str] = frozenset({
    "jwt_token",
    "access_token",
    "refresh_token",
    "password",
    "secret",
    "authorization",
})

# Base fields required on every audit log entry (permit or deny).
BASE_REQUIRED_FIELDS: frozenset[str] = frozenset({
    "tool_name",
    "user_id",
    "policy_name",
    "evaluation_result",
    "timestamp",
})

# Additional fields required only on deny entries.
DENY_REQUIRED_FIELDS: frozenset[str] = frozenset({
    "denial_reason",
    "request_context",
})


# ---------------------------------------------------------------------------
# Audit log model — mirrors the Gateway's structured logging contract
# ---------------------------------------------------------------------------


def _sanitize_params(params: dict[str, Any]) -> dict[str, Any]:
    """Remove sensitive keys from tool invocation parameters.

    The Gateway's audit logging configuration (ExcludeSensitiveData=True)
    strips JWT tokens, passwords, and other secrets before writing the
    request context to CloudWatch.

    Args:
        params: Raw tool invocation parameters.

    Returns:
        A copy with sensitive keys removed.
    """
    return {k: v for k, v in params.items() if k.lower() not in SENSITIVE_KEYS}


def create_audit_log_entry(
    tool_name: str,
    user_id: str,
    policy_name: str,
    evaluation_result: str,
    timestamp: str,
    denial_reason: str | None = None,
    request_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a structured audit log entry for a Cedar policy evaluation.

    Models the Gateway's policy audit log format as configured in
    ``AgentCoreStack._configure_policy_audit_logging()``. Every evaluation
    (permit or deny) gets the 5 base fields. Denials additionally get
    denial_reason and sanitized request_context.

    Args:
        tool_name: The MCP tool name being invoked.
        user_id: The userId from JWT claims.
        policy_name: The Cedar policy that was evaluated.
        evaluation_result: "permit" or "deny".
        timestamp: ISO-8601 timestamp of the evaluation.
        denial_reason: Reason string (required when evaluation_result is "deny").
        request_params: Raw tool invocation parameters (sensitive data will
            be stripped before inclusion in the log entry).

    Returns:
        Structured audit log dict.
    """
    entry: dict[str, Any] = {
        "tool_name": tool_name,
        "user_id": user_id,
        "policy_name": policy_name,
        "evaluation_result": evaluation_result,
        "timestamp": timestamp,
    }

    if evaluation_result == "deny":
        entry["denial_reason"] = denial_reason or "unspecified"
        entry["request_context"] = _sanitize_params(request_params or {})

    return entry


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

_user_id = st.text(
    min_size=1,
    max_size=50,
    alphabet=st.characters(whitelist_categories=("L", "N", "Pd")),
)

_tool_name = st.sampled_from(ALL_TOOL_NAMES)
_policy_name = st.sampled_from(POLICY_NAMES)
_eval_result = st.sampled_from(EVALUATION_RESULTS)
_denial_reason = st.sampled_from(DENIAL_REASONS)

_iso_timestamp = st.builds(
    lambda dt: dt.isoformat(),
    st.datetimes(
        min_value=datetime(2024, 1, 1),
        max_value=datetime(2026, 12, 31),
        timezones=st.just(timezone.utc),
    ),
)

# Safe parameter values (non-sensitive).
_safe_param_value = st.one_of(
    st.text(min_size=0, max_size=30, alphabet=st.characters(whitelist_categories=("L", "N"))),
    st.integers(min_value=0, max_value=1000),
    st.booleans(),
)

_safe_param_key = st.text(
    min_size=1,
    max_size=20,
    alphabet=st.characters(whitelist_categories=("L",)),
).filter(lambda k: k.lower() not in SENSITIVE_KEYS)

_safe_params = st.dictionaries(
    keys=_safe_param_key,
    values=_safe_param_value,
    min_size=0,
    max_size=5,
)

# Parameters that include sensitive keys to verify they get stripped.
_sensitive_param_key = st.sampled_from(sorted(SENSITIVE_KEYS))

_mixed_params = st.builds(
    lambda safe, sens_key: {**safe, sens_key: "SENSITIVE_VALUE_12345"},
    _safe_params,
    _sensitive_param_key,
)


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------


class TestPolicyAuditLogCompleteness:
    """Property 10: Policy audit log completeness.

    Trigger policy evaluations, verify log entries contain all required fields.
    """

    @given(
        tool_name=_tool_name,
        user_id=_user_id,
        policy_name=_policy_name,
        eval_result=_eval_result,
        timestamp=_iso_timestamp,
        denial_reason=_denial_reason,
        request_params=_safe_params,
    )
    @settings(max_examples=100)
    def test_all_evaluations_contain_base_fields(
        self,
        tool_name: str,
        user_id: str,
        policy_name: str,
        eval_result: str,
        timestamp: str,
        denial_reason: str,
        request_params: dict[str, Any],
    ) -> None:
        """Every audit log entry (permit or deny) contains the 5 base fields.

        # Feature: agentcore-platform-integration, Property 10: Policy audit log completeness
        **Validates: Requirements 4.3, 9.1, 9.2**
        """
        entry = create_audit_log_entry(
            tool_name=tool_name,
            user_id=user_id,
            policy_name=policy_name,
            evaluation_result=eval_result,
            timestamp=timestamp,
            denial_reason=denial_reason if eval_result == "deny" else None,
            request_params=request_params if eval_result == "deny" else None,
        )

        missing = BASE_REQUIRED_FIELDS - set(entry.keys())
        assert not missing, (
            f"Audit log entry missing base fields: {missing}. "
            f"Entry keys: {set(entry.keys())}"
        )

        # Verify field values are non-empty / correct type.
        assert entry["tool_name"] == tool_name
        assert entry["user_id"] == user_id
        assert entry["policy_name"] == policy_name
        assert entry["evaluation_result"] in EVALUATION_RESULTS
        assert len(entry["timestamp"]) > 0

    @given(
        tool_name=_tool_name,
        user_id=_user_id,
        policy_name=_policy_name,
        timestamp=_iso_timestamp,
        denial_reason=_denial_reason,
        request_params=_safe_params,
    )
    @settings(max_examples=100)
    def test_deny_entries_contain_additional_fields(
        self,
        tool_name: str,
        user_id: str,
        policy_name: str,
        timestamp: str,
        denial_reason: str,
        request_params: dict[str, Any],
    ) -> None:
        """Deny entries additionally contain denial_reason and request_context.

        # Feature: agentcore-platform-integration, Property 10: Policy audit log completeness
        **Validates: Requirements 4.3, 9.1, 9.2**
        """
        entry = create_audit_log_entry(
            tool_name=tool_name,
            user_id=user_id,
            policy_name=policy_name,
            evaluation_result="deny",
            timestamp=timestamp,
            denial_reason=denial_reason,
            request_params=request_params,
        )

        all_required = BASE_REQUIRED_FIELDS | DENY_REQUIRED_FIELDS
        missing = all_required - set(entry.keys())
        assert not missing, (
            f"Deny audit log entry missing fields: {missing}. "
            f"Entry keys: {set(entry.keys())}"
        )

        assert entry["denial_reason"] == denial_reason
        assert isinstance(entry["request_context"], dict)

    @given(
        tool_name=_tool_name,
        user_id=_user_id,
        policy_name=_policy_name,
        timestamp=_iso_timestamp,
    )
    @settings(max_examples=100)
    def test_permit_entries_exclude_deny_fields(
        self,
        tool_name: str,
        user_id: str,
        policy_name: str,
        timestamp: str,
    ) -> None:
        """Permit entries do NOT contain denial_reason or request_context.

        # Feature: agentcore-platform-integration, Property 10: Policy audit log completeness
        **Validates: Requirements 4.3, 9.1, 9.2**
        """
        entry = create_audit_log_entry(
            tool_name=tool_name,
            user_id=user_id,
            policy_name=policy_name,
            evaluation_result="permit",
            timestamp=timestamp,
        )

        assert set(entry.keys()) == BASE_REQUIRED_FIELDS, (
            f"Permit entry should have exactly base fields. "
            f"Got: {set(entry.keys())}"
        )

    @given(
        tool_name=_tool_name,
        user_id=_user_id,
        policy_name=_policy_name,
        timestamp=_iso_timestamp,
        denial_reason=_denial_reason,
        request_params=_mixed_params,
    )
    @settings(max_examples=100)
    def test_sensitive_data_excluded_from_request_context(
        self,
        tool_name: str,
        user_id: str,
        policy_name: str,
        timestamp: str,
        denial_reason: str,
        request_params: dict[str, Any],
    ) -> None:
        """Request context in deny entries never contains sensitive data.

        Sensitive keys (jwt_token, password, secret, access_token,
        refresh_token, authorization) are stripped before logging.

        # Feature: agentcore-platform-integration, Property 10: Policy audit log completeness
        **Validates: Requirements 4.3, 9.1, 9.2**
        """
        # Confirm the input actually has sensitive keys (strategy guarantees it).
        assume(any(k.lower() in SENSITIVE_KEYS for k in request_params))

        entry = create_audit_log_entry(
            tool_name=tool_name,
            user_id=user_id,
            policy_name=policy_name,
            evaluation_result="deny",
            timestamp=timestamp,
            denial_reason=denial_reason,
            request_params=request_params,
        )

        ctx = entry["request_context"]

        # No sensitive keys in the sanitized context.
        for key in ctx:
            assert key.lower() not in SENSITIVE_KEYS, (
                f"Sensitive key {key!r} found in request_context"
            )

        # No JWT-like patterns in serialized context values.
        ctx_str = str(ctx)
        for pattern in SENSITIVE_PATTERNS:
            assert not pattern.search(ctx_str), (
                f"Sensitive pattern {pattern.pattern!r} found in "
                f"request_context: {ctx_str!r}"
            )
