"""Property-based tests for Cedar policy: market data read-only enforcement.

# Feature: agentcore-platform-integration, Property 9: Market data read-only enforcement

**Validates: Requirements 8.1, 8.2**

For any tool invocation by the Coaching Agent targeting MarketData, read
operations (get_market_insights, get_alignment) SHALL be permitted, and write,
update, or delete operations SHALL be denied with a Policy Denial.

Strategy:
- Define a pure Python function that evaluates the market data read-only
  Cedar policy logic (what the Cedar engine would do at runtime).
- Use Hypothesis to generate random tool names from all 13 registered tools
  and random operation types from ["read", "write", "update", "delete"].
- Verify: market read tools always permitted, write/update/delete on
  MarketData always denied.
"""

from hypothesis import given, settings
from hypothesis import strategies as st


# ---------------------------------------------------------------------------
# Constants matching the Cedar policy and tool registry
# ---------------------------------------------------------------------------

MARKET_READ_TOOLS = frozenset({"regain_get_market_insights", "regain_get_alignment"})

ALL_TOOL_NAMES = [
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

OPERATION_TYPES = ["read", "write", "update", "delete"]


# ---------------------------------------------------------------------------
# Policy evaluation function (simulates Cedar market data read-only logic)
# ---------------------------------------------------------------------------

def evaluate_market_data_policy(
    tool_name: str, target_table: str, operation_type: str,
) -> str:
    """Evaluate the market data read-only Cedar policy.

    Mirrors the Cedar policy defined in AgentCoreStack._cedar_market_data_readonly():
        permit when resource.tool_name in
            ["regain_get_market_insights", "regain_get_alignment"]
        forbid when resource.target_table == "MarketData"
            && context.operation_type in ["write", "update", "delete"]

    Args:
        tool_name: The MCP tool name being invoked.
        target_table: The DynamoDB table being accessed.
        operation_type: The operation type ("read", "write", "update", "delete").

    Returns:
        "permit" if the tool is a market read tool, "deny" if the operation
        is a write/update/delete on MarketData, "permit" otherwise.
    """
    if tool_name in MARKET_READ_TOOLS:
        return "permit"
    if target_table == "MarketData" and operation_type in ("write", "update", "delete"):
        return "deny"
    return "permit"


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

_tool_names = st.sampled_from(ALL_TOOL_NAMES)
_operation_types = st.sampled_from(OPERATION_TYPES)


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------

class TestMarketDataReadOnlyPolicy:
    """Property 9: Market data read-only enforcement.

    For random (tool_name, operation_type) pairs, verify reads permitted
    and writes denied.
    """

    @given(tool_name=st.sampled_from(sorted(MARKET_READ_TOOLS)))
    @settings(max_examples=100)
    def test_market_read_tools_always_permitted(self, tool_name: str) -> None:
        """Market read tools (get_market_insights, get_alignment) are always permitted.

        # Feature: agentcore-platform-integration, Property 9: Market data read-only enforcement
        **Validates: Requirements 8.1, 8.2**
        """
        for op in OPERATION_TYPES:
            result = evaluate_market_data_policy(tool_name, "MarketData", op)
            assert result == "permit", (
                f"Market read tool {tool_name!r} with op={op!r} should always "
                f"permit, got {result!r}"
            )

    @given(
        operation_type=st.sampled_from(["write", "update", "delete"]),
        tool_name=_tool_names,
    )
    @settings(max_examples=100)
    def test_write_operations_on_market_data_denied_for_non_read_tools(
        self, operation_type: str, tool_name: str,
    ) -> None:
        """Write/update/delete on MarketData denied unless tool is a market read tool.

        # Feature: agentcore-platform-integration, Property 9: Market data read-only enforcement
        **Validates: Requirements 8.1, 8.2**
        """
        from hypothesis import assume

        assume(tool_name not in MARKET_READ_TOOLS)

        result = evaluate_market_data_policy(tool_name, "MarketData", operation_type)
        assert result == "deny", (
            f"Non-read tool {tool_name!r} with op={operation_type!r} on "
            f"MarketData should deny, got {result!r}"
        )

    @given(tool_name=_tool_names, operation_type=_operation_types)
    @settings(max_examples=100)
    def test_full_policy_biconditional(
        self, tool_name: str, operation_type: str,
    ) -> None:
        """Complete biconditional: market reads permitted, MarketData writes denied.

        # Feature: agentcore-platform-integration, Property 9: Market data read-only enforcement
        **Validates: Requirements 8.1, 8.2**
        """
        result = evaluate_market_data_policy(tool_name, "MarketData", operation_type)

        if tool_name in MARKET_READ_TOOLS:
            assert result == "permit", (
                f"Market read tool {tool_name!r} should permit, got {result!r}"
            )
        elif operation_type in ("write", "update", "delete"):
            assert result == "deny", (
                f"Non-read tool {tool_name!r} with op={operation_type!r} on "
                f"MarketData should deny, got {result!r}"
            )
        else:
            assert result == "permit", (
                f"Read op on MarketData by {tool_name!r} should permit, "
                f"got {result!r}"
            )
