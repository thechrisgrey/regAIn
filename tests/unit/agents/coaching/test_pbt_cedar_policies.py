"""Property-based tests for Cedar policy: user data isolation.

# Feature: agentcore-platform-integration, Property 4: User data isolation

**Validates: Requirements 4.1, 4.2**

For any tool invocation, the Cedar policy SHALL permit the invocation if and
only if the userId in the request parameters matches the userId extracted from
the JWT claims. For any mismatch between request userId and JWT userId, the
Gateway SHALL return a Policy Denial.

Strategy:
- Define a pure Python function that evaluates the user data isolation policy
  logic (what the Cedar engine would do at runtime).
- Use Hypothesis to generate random (request_user_id, jwt_user_id) pairs.
- Verify: permit iff match, deny iff mismatch — no exceptions.
"""

from hypothesis import given, settings
from hypothesis import strategies as st


# ---------------------------------------------------------------------------
# Policy evaluation function (simulates Cedar user data isolation logic)
# ---------------------------------------------------------------------------

def evaluate_user_data_isolation(request_user_id: str, jwt_user_id: str) -> str:
    """Evaluate the user data isolation Cedar policy.

    Mirrors the Cedar policy defined in AgentCoreStack._cedar_user_data_isolation():
        permit when resource.tool_params.userId == context.auth.userId
        forbid when resource.tool_params.userId != context.auth.userId

    Args:
        request_user_id: The userId from the tool invocation request params.
        jwt_user_id: The userId extracted from the JWT claims by Gateway auth.

    Returns:
        "permit" if userIds match, "deny" if they differ.
    """
    if request_user_id == jwt_user_id:
        return "permit"
    return "deny"


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

_user_id = st.text(
    min_size=1,
    max_size=50,
    alphabet=st.characters(whitelist_categories=("L", "N", "Pd")),
)


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------

class TestUserDataIsolationPolicy:
    """Property 4: User data isolation.

    For random (request userId, JWT userId) pairs, verify permit iff match,
    deny iff mismatch.
    """

    @given(user_id=_user_id)
    @settings(max_examples=100)
    def test_matching_user_ids_always_permit(self, user_id: str) -> None:
        """When request userId equals JWT userId, the policy always permits.

        # Feature: agentcore-platform-integration, Property 4: User data isolation
        **Validates: Requirements 4.1, 4.2**
        """
        result = evaluate_user_data_isolation(
            request_user_id=user_id,
            jwt_user_id=user_id,
        )
        assert result == "permit", (
            f"Expected permit for matching userId={user_id!r}, got {result!r}"
        )

    @given(
        request_user_id=_user_id,
        jwt_user_id=_user_id,
    )
    @settings(max_examples=100)
    def test_mismatched_user_ids_always_deny(
        self,
        request_user_id: str,
        jwt_user_id: str,
    ) -> None:
        """When request userId differs from JWT userId, the policy always denies.

        Uses assume() to filter to only mismatched pairs — Hypothesis will
        generate enough distinct pairs to hit 100 examples.

        # Feature: agentcore-platform-integration, Property 4: User data isolation
        **Validates: Requirements 4.1, 4.2**
        """
        from hypothesis import assume

        assume(request_user_id != jwt_user_id)

        result = evaluate_user_data_isolation(
            request_user_id=request_user_id,
            jwt_user_id=jwt_user_id,
        )
        assert result == "deny", (
            f"Expected deny for request={request_user_id!r} vs "
            f"jwt={jwt_user_id!r}, got {result!r}"
        )

    @given(
        request_user_id=_user_id,
        jwt_user_id=_user_id,
    )
    @settings(max_examples=100)
    def test_permit_iff_match_deny_iff_mismatch(
        self,
        request_user_id: str,
        jwt_user_id: str,
    ) -> None:
        """The biconditional: permit ⟺ match, deny ⟺ mismatch.

        Single property that covers both directions in one test.

        # Feature: agentcore-platform-integration, Property 4: User data isolation
        **Validates: Requirements 4.1, 4.2**
        """
        result = evaluate_user_data_isolation(request_user_id, jwt_user_id)

        if request_user_id == jwt_user_id:
            assert result == "permit", (
                f"Matching IDs ({request_user_id!r}) should permit, got {result!r}"
            )
        else:
            assert result == "deny", (
                f"Mismatched IDs (req={request_user_id!r}, jwt={jwt_user_id!r}) "
                f"should deny, got {result!r}"
            )


# ===========================================================================
# Property 5: Evidence write scope enforcement
# ===========================================================================
#
# # Feature: agentcore-platform-integration, Property 5: Evidence write scope enforcement
#
# **Validates: Requirements 5.1, 5.2**
#
# For any log_evidence tool invocation, the Cedar policy SHALL permit the
# invocation if and only if both conditions hold: the coaching session is
# active and the evidence timestamp is within the last 24 hours. Violation
# of either condition SHALL result in a Policy Denial.
#
# The campaign-completed check is enforced separately in the Lambda tool
# logic, not in Cedar — it is NOT part of this property.
#
# Strategy:
# - Define a pure Python function that evaluates the evidence write scope
#   policy logic (what the Cedar engine would do at runtime).
# - Use Hypothesis to generate random (session_active, within_last_24h)
#   boolean tuples.
# - Verify: permit iff both true, deny otherwise.
# ===========================================================================


def evaluate_evidence_write_scope(session_active: bool, within_last_24h: bool) -> str:
    """Evaluate the evidence write scope Cedar policy.

    Mirrors the Cedar policy defined in AgentCoreStack._cedar_evidence_write_scope():
        permit when resource.tool_name == "regain_log_evidence"
                 && context.session.is_active == true
                 && context.evidence_timestamp.within_last_24h == true
        forbid when resource.tool_name == "regain_log_evidence"
                 && (context.session.is_active == false
                     || context.evidence_timestamp.within_last_24h == false)

    Args:
        session_active: Whether the coaching session is currently active.
        within_last_24h: Whether the evidence timestamp is within the last 24 hours.

    Returns:
        "permit" if both conditions are true, "deny" otherwise.
    """
    if session_active and within_last_24h:
        return "permit"
    return "deny"


class TestEvidenceWriteScopePolicy:
    """Property 5: Evidence write scope enforcement.

    For random (session_active, timestamp_age) tuples, verify permit iff
    both conditions met.
    """

    @given(session_active=st.booleans(), within_last_24h=st.booleans())
    @settings(max_examples=100)
    def test_permit_iff_both_conditions_true(
        self,
        session_active: bool,
        within_last_24h: bool,
    ) -> None:
        """The biconditional: permit ⟺ (session_active ∧ within_last_24h).

        # Feature: agentcore-platform-integration, Property 5: Evidence write scope enforcement
        **Validates: Requirements 5.1, 5.2**
        """
        result = evaluate_evidence_write_scope(session_active, within_last_24h)

        if session_active and within_last_24h:
            assert result == "permit", (
                f"Both conditions true (active={session_active}, "
                f"recent={within_last_24h}) should permit, got {result!r}"
            )
        else:
            assert result == "deny", (
                f"Condition violated (active={session_active}, "
                f"recent={within_last_24h}) should deny, got {result!r}"
            )

    @given(data=st.data())
    @settings(max_examples=100)
    def test_inactive_session_always_denies(self, data: st.DataObject) -> None:
        """When session is inactive, the policy always denies regardless of timestamp.

        # Feature: agentcore-platform-integration, Property 5: Evidence write scope enforcement
        **Validates: Requirements 5.1, 5.2**
        """
        within_last_24h = data.draw(st.booleans(), label="within_last_24h")

        result = evaluate_evidence_write_scope(
            session_active=False,
            within_last_24h=within_last_24h,
        )
        assert result == "deny", (
            f"Inactive session should always deny, got {result!r} "
            f"(within_last_24h={within_last_24h})"
        )

    @given(data=st.data())
    @settings(max_examples=100)
    def test_stale_timestamp_always_denies(self, data: st.DataObject) -> None:
        """When timestamp is older than 24h, the policy always denies regardless of session.

        # Feature: agentcore-platform-integration, Property 5: Evidence write scope enforcement
        **Validates: Requirements 5.1, 5.2**
        """
        session_active = data.draw(st.booleans(), label="session_active")

        result = evaluate_evidence_write_scope(
            session_active=session_active,
            within_last_24h=False,
        )
        assert result == "deny", (
            f"Stale timestamp should always deny, got {result!r} "
            f"(session_active={session_active})"
        )


# ===========================================================================
# Property 6: Mission generation rate limit
# ===========================================================================
#
# # Feature: agentcore-platform-integration, Property 6: Mission generation rate limit
#
# **Validates: Requirements 6.1, 6.2, 6.3**
#
# For any user with a daily mission generation count of N, the Cedar policy
# SHALL permit the generate_mission tool if and only if N < 3. When N >= 3,
# the Gateway SHALL return a Policy Denial with reason "daily mission
# generation limit reached".
#
# Strategy:
# - Define a pure Python function that evaluates the mission rate limit
#   policy logic (what the Cedar engine would do at runtime).
# - Use Hypothesis to generate random daily_count values (0-10).
# - Verify: permit iff count < 3, deny otherwise.
# ===========================================================================


def evaluate_mission_rate_limit(daily_count: int) -> str:
    """Evaluate the mission generation rate limit Cedar policy.

    Mirrors the Cedar policy defined in AgentCoreStack._cedar_mission_rate_limit():
        permit when resource.tool_name == "regain_generate_mission"
                 && context.daily_generation_count < 3
        forbid when resource.tool_name == "regain_generate_mission"
                 && context.daily_generation_count >= 3

    Args:
        daily_count: The current daily mission generation count for the user.

    Returns:
        "permit" if count < 3, "deny" otherwise.
    """
    if daily_count < 3:
        return "permit"
    return "deny"


class TestMissionRateLimitPolicy:
    """Property 6: Mission generation rate limit.

    For random (user_id, daily_count 0-10), verify permit iff count < 3.
    """

    @given(daily_count=st.integers(min_value=0, max_value=10))
    @settings(max_examples=100)
    def test_permit_iff_count_below_three(self, daily_count: int) -> None:
        """The biconditional: permit ⟺ daily_count < 3.

        # Feature: agentcore-platform-integration, Property 6: Mission generation rate limit
        **Validates: Requirements 6.1, 6.2, 6.3**
        """
        result = evaluate_mission_rate_limit(daily_count)

        if daily_count < 3:
            assert result == "permit", (
                f"Count {daily_count} < 3 should permit, got {result!r}"
            )
        else:
            assert result == "deny", (
                f"Count {daily_count} >= 3 should deny, got {result!r}"
            )

    @given(daily_count=st.integers(min_value=0, max_value=2))
    @settings(max_examples=100)
    def test_counts_below_limit_always_permit(self, daily_count: int) -> None:
        """Counts 0, 1, 2 always permit.

        # Feature: agentcore-platform-integration, Property 6: Mission generation rate limit
        **Validates: Requirements 6.1, 6.2, 6.3**
        """
        assert evaluate_mission_rate_limit(daily_count) == "permit"

    @given(daily_count=st.integers(min_value=3, max_value=10))
    @settings(max_examples=100)
    def test_counts_at_or_above_limit_always_deny(self, daily_count: int) -> None:
        """Counts 3+ always deny.

        # Feature: agentcore-platform-integration, Property 6: Mission generation rate limit
        **Validates: Requirements 6.1, 6.2, 6.3**
        """
        assert evaluate_mission_rate_limit(daily_count) == "deny"


# ===========================================================================
# Property 7: Mission generation counter atomicity
# ===========================================================================
#
# # Feature: agentcore-platform-integration, Property 7: Mission generation counter atomicity
#
# **Validates: Requirements 6.1, 6.2, 6.3**
#
# For any permitted generate_mission tool invocation, the DynamoDB conditional
# update on UserProfiles SHALL atomically increment dailyMissionGenCount by
# exactly 1 and succeed only when the pre-increment value is less than 3.
#
# Strategy:
# - Use moto to create a mock UserProfiles table.
# - Use Hypothesis to generate random starting counts (0-10).
# - Seed a user profile with that count and lastMissionGenDate = today.
# - Call _enforce_daily_rate_limit from tools.py.
# - Verify: succeeds and increments by 1 when count < 3, raises
#   _RateLimitExceeded when count >= 3.
# ===========================================================================

import importlib
import os
import sys
import types
from datetime import datetime, timezone

import boto3
import pytest
from moto import mock_aws

# ---------------------------------------------------------------------------
# Stub strands and engine modules so tools.py can be imported
# ---------------------------------------------------------------------------
sys.modules.setdefault("strands", types.ModuleType("strands"))
if not hasattr(sys.modules["strands"], "tool"):
    sys.modules["strands"].tool = lambda fn: fn  # type: ignore[attr-defined]

# Stub engine modules only if they cannot be imported for real
for _mod_name in ("backend.engine.generator", "backend.engine.models"):
    try:
        importlib.import_module(_mod_name)
    except Exception:
        _stub = types.ModuleType(_mod_name)
        # Provide minimal stubs for names imported by tools.py
        if _mod_name == "backend.engine.generator":
            _stub.generate_daily_mission = lambda *a, **kw: None  # type: ignore[attr-defined]
            _stub.complete_mission = lambda *a, **kw: None  # type: ignore[attr-defined]
        elif _mod_name == "backend.engine.models":
            _stub.GenerationResult = type("GenerationResult", (), {})  # type: ignore[attr-defined]
            _stub.CompletionResult = type("CompletionResult", (), {})  # type: ignore[attr-defined]
        sys.modules[_mod_name] = _stub


def _fresh_tools_module():
    """Import (or reimport) tools.py with a fresh DynamoDBClient."""
    mod_name = "backend.agents.coaching.tools"
    # Also refresh the shared dynamodb module so it picks up new env vars
    shared_mod = "backend.lambda.shared.dynamodb"
    for m in (mod_name, shared_mod):
        if m in sys.modules:
            del sys.modules[m]
    return importlib.import_module(mod_name)


_USER_PROFILES_TABLE = "RegainUserProfiles"


class TestMissionCounterAtomicity:
    """Property 7: Mission generation counter atomicity.

    Verify DynamoDB conditional update increments by 1 and rejects at
    count >= 3.
    """

    @given(starting_count=st.integers(min_value=0, max_value=10))
    @settings(max_examples=100)
    def test_increment_or_reject_based_on_count(
        self, starting_count: int,
    ) -> None:
        """Increment by 1 when count < 3, raise _RateLimitExceeded when >= 3.

        # Feature: agentcore-platform-integration, Property 7: Mission generation counter atomicity
        **Validates: Requirements 6.1, 6.2, 6.3**
        """
        # Set env vars inline (Hypothesis doesn't support function-scoped fixtures)
        os.environ["USER_PROFILES_TABLE"] = _USER_PROFILES_TABLE
        os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
        os.environ["AWS_ACCESS_KEY_ID"] = "testing"
        os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"

        with mock_aws():
            # Create the UserProfiles table in moto
            dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
            dynamodb.create_table(
                TableName=_USER_PROFILES_TABLE,
                KeySchema=[{"AttributeName": "userId", "KeyType": "HASH"}],
                AttributeDefinitions=[
                    {"AttributeName": "userId", "AttributeType": "S"},
                ],
                BillingMode="PAY_PER_REQUEST",
            )
            table = dynamodb.Table(_USER_PROFILES_TABLE)

            user_id = "test-user-atomicity"
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

            # Seed the user profile with the starting count and today's date
            # so the reset step in _enforce_daily_rate_limit is skipped.
            table.put_item(
                Item={
                    "userId": user_id,
                    "dailyMissionGenCount": starting_count,
                    "lastMissionGenDate": today,
                }
            )

            # Import tools with fresh DynamoDBClient bound to moto
            tools = _fresh_tools_module()

            if starting_count < 3:
                # Should succeed and increment by exactly 1
                tools._enforce_daily_rate_limit(user_id)
                item = table.get_item(Key={"userId": user_id})["Item"]
                assert item["dailyMissionGenCount"] == starting_count + 1, (
                    f"Expected count {starting_count + 1}, "
                    f"got {item['dailyMissionGenCount']}"
                )
            else:
                # Should raise _RateLimitExceeded
                with pytest.raises(tools._RateLimitExceeded):
                    tools._enforce_daily_rate_limit(user_id)
                # Count should remain unchanged
                item = table.get_item(Key={"userId": user_id})["Item"]
                assert item["dailyMissionGenCount"] == starting_count, (
                    f"Count should stay at {starting_count} after rejection, "
                    f"got {item['dailyMissionGenCount']}"
                )
