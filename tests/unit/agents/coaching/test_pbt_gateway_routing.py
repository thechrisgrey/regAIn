"""Property-based tests for Gateway routing equivalence.

# Feature: agentcore-platform-integration, Property 3: Gateway routing equivalence

**Validates: Requirements 3.3, 3.4**

For any tool invocation with valid parameters and a valid JWT, routing the
invocation through AgentCore Gateway SHALL produce a response equivalent to
invoking the same tool function directly with the same parameters.

Strategy: mock the boto3 Gateway ``invoke_tool`` call to forward to the
actual @tool function, capture the raw tool result, then verify that
``GatewayToolClient.invoke_tool()`` returns an identical result — proving
the client's response parsing does not lose or transform data.
"""

import importlib
import os
import re
import sys
import types
from typing import Any, Callable
from unittest.mock import MagicMock

import boto3
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from moto import mock_aws

# ---------------------------------------------------------------------------
# Stub strands so tools.py can be imported without the SDK installed
# ---------------------------------------------------------------------------
_strands_stub = types.ModuleType("strands")
_strands_stub.tool = lambda fn: fn
sys.modules.setdefault("strands", _strands_stub)

from backend.agents.coaching.tool_schemas import TOOL_SCHEMAS  # noqa: E402
from backend.agents.coaching.gateway_client import GatewayToolClient  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _camel_to_snake(name: str) -> str:
    """Convert camelCase to snake_case."""
    s1 = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def _get_tool_function(schema_name: str) -> Callable[..., Any]:
    """Resolve the @tool function for a given schema name."""
    func_name = schema_name.removeprefix("regain_")
    import backend.agents.coaching.tools as tools_mod
    return getattr(tools_mod, func_name)


def _call_tool_directly(schema: dict[str, Any], params: dict[str, Any]) -> Any:
    """Call the @tool function with schema params mapped to snake_case."""
    func = _get_tool_function(schema["name"])
    kwargs = {_camel_to_snake(k): v for k, v in params.items()}
    return func(**kwargs)


# ---------------------------------------------------------------------------
# Testable tool subset — DynamoDB-only tools that work with moto
# ---------------------------------------------------------------------------

_EXCLUDED_TOOLS = {
    "regain_get_market_insights",
    "regain_get_alignment",
    "regain_recall_memory",
    "regain_store_memory",  # Removed — memory writes handled by AgentCore session manager
    "regain_generate_mission",
    "regain_complete_mission",
    "regain_code_interpreter",  # Gateway-managed service, not a @tool function
}

_TESTABLE_SCHEMAS = [s for s in TOOL_SCHEMAS if s["name"] not in _EXCLUDED_TOOLS]
_SCHEMA_LOOKUP = {s["name"]: s for s in TOOL_SCHEMAS}


# ---------------------------------------------------------------------------
# Hypothesis strategies for valid tool parameters
# ---------------------------------------------------------------------------

_safe_text = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
    min_size=1,
    max_size=50,
)

_user_id = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_",
    min_size=5,
    max_size=30,
)


def _params_strategy_for(schema: dict[str, Any]) -> st.SearchStrategy[dict[str, Any]]:
    """Build a Hypothesis strategy that generates valid params for a tool."""
    name = schema["name"]

    if name == "regain_read_user_profile":
        return st.fixed_dictionaries({"userId": _user_id})

    if name == "regain_update_user_profile":
        return st.fixed_dictionaries({
            "userId": _user_id,
            "updates": st.fixed_dictionaries({"target_role": _safe_text}),
        })

    if name == "regain_get_campaign_status":
        return st.fixed_dictionaries({"userId": _user_id})

    if name == "regain_create_campaign":
        return st.fixed_dictionaries({
            "userId": _user_id,
            "title": _safe_text,
            "targetRole": _safe_text,
            "skillsFocus": st.lists(_safe_text, min_size=1, max_size=3),
        })

    if name == "regain_get_current_mission":
        return st.fixed_dictionaries({"userId": _user_id})

    if name == "regain_log_evidence":
        return st.fixed_dictionaries({
            "userId": _user_id,
            "missionId": _safe_text,
            "skillTag": _safe_text,
            "reflection": _safe_text,
        })

    if name == "regain_get_evidence_summary":
        return st.fixed_dictionaries({"userId": _user_id})

    _date = st.from_regex(r"^20[2-3][0-9]-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])$", fullmatch=True)

    if name == "regain_read_calendar":
        return st.fixed_dictionaries({
            "userId": _user_id,
            "start_date": _date,
            "end_date": _date,
        })

    if name == "regain_write_calendar_entry":
        return st.fixed_dictionaries({
            "userId": _user_id,
            "date": _date,
            "category": st.sampled_from(["task", "note"]),
            "content": _safe_text,
        })

    return st.fixed_dictionaries({"userId": _user_id})


# ---------------------------------------------------------------------------
# Gateway mock that captures the raw tool result
# ---------------------------------------------------------------------------

def _make_capturing_gateway_mock(
    schema_lookup: dict[str, dict[str, Any]],
    captured: dict[str, Any],
) -> MagicMock:
    """Create a mock boto3 client that calls the real tool and captures its result.

    The mock wraps the tool result in the Gateway response format
    (``{"output": result}``). The raw tool result is stored in
    ``captured["raw"]`` so the test can compare it against what
    GatewayToolClient returns after parsing.
    """
    mock_client = MagicMock()

    def mock_invoke_tool(**kwargs: Any) -> dict[str, Any]:
        tool_name = kwargs["toolName"]
        params = kwargs["input"]
        schema = schema_lookup[tool_name]
        result = _call_tool_directly(schema, params)
        captured["raw"] = result
        return {"output": result}

    mock_client.invoke_tool.side_effect = mock_invoke_tool
    mock_client.list_tools.side_effect = Exception("mocked — use local schemas")
    return mock_client


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MOCK_TABLE_NAMES = {
    "USER_PROFILES_TABLE": "RegainUserProfiles",
    "CAMPAIGNS_TABLE": "RegainCampaigns",
    "MISSION_HISTORY_TABLE": "RegainMissionHistory",
    "EVIDENCE_VAULT_TABLE": "RegainEvidenceVault",
    "MARKET_DATA_TABLE": "RegainMarketData",
}


@pytest.fixture(autouse=True)
def _moto_env(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Set up moto DynamoDB tables and env vars for every test."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    for env_var, table_name in MOCK_TABLE_NAMES.items():
        monkeypatch.setenv(env_var, table_name)

    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")

        dynamodb.create_table(
            TableName="RegainUserProfiles",
            KeySchema=[{"AttributeName": "userId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "userId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        dynamodb.create_table(
            TableName="RegainCampaigns",
            KeySchema=[
                {"AttributeName": "userId", "KeyType": "HASH"},
                {"AttributeName": "campaignId", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "userId", "AttributeType": "S"},
                {"AttributeName": "campaignId", "AttributeType": "S"},
                {"AttributeName": "status", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[{
                "IndexName": "status-index",
                "KeySchema": [
                    {"AttributeName": "status", "KeyType": "HASH"},
                    {"AttributeName": "userId", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }],
            BillingMode="PAY_PER_REQUEST",
        )
        dynamodb.create_table(
            TableName="RegainMissionHistory",
            KeySchema=[
                {"AttributeName": "userId", "KeyType": "HASH"},
                {"AttributeName": "missionId", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "userId", "AttributeType": "S"},
                {"AttributeName": "missionId", "AttributeType": "S"},
                {"AttributeName": "status", "AttributeType": "S"},
                {"AttributeName": "completedDate", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "status-index",
                    "KeySchema": [
                        {"AttributeName": "status", "KeyType": "HASH"},
                        {"AttributeName": "userId", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
                {
                    "IndexName": "date-index",
                    "KeySchema": [
                        {"AttributeName": "userId", "KeyType": "HASH"},
                        {"AttributeName": "completedDate", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        dynamodb.create_table(
            TableName="RegainEvidenceVault",
            KeySchema=[
                {"AttributeName": "userId", "KeyType": "HASH"},
                {"AttributeName": "evidenceId", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "userId", "AttributeType": "S"},
                {"AttributeName": "evidenceId", "AttributeType": "S"},
                {"AttributeName": "skillTag", "AttributeType": "S"},
                {"AttributeName": "createdAt", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[{
                "IndexName": "skill-index",
                "KeySchema": [
                    {"AttributeName": "skillTag", "KeyType": "HASH"},
                    {"AttributeName": "createdAt", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }],
            BillingMode="PAY_PER_REQUEST",
        )
        dynamodb.create_table(
            TableName="RegainMarketData",
            KeySchema=[
                {"AttributeName": "sector", "KeyType": "HASH"},
                {"AttributeName": "timestamp", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "sector", "AttributeType": "S"},
                {"AttributeName": "timestamp", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # Re-initialize DynamoDBClient so it picks up moto tables
        import backend.agents.coaching.tools as tools_mod
        _dynamodb_mod = importlib.import_module("backend.handlers.shared.dynamodb")
        tools_mod.db = _dynamodb_mod.DynamoDBClient()

        yield


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------


class TestGatewayRoutingEquivalence:
    """Property 3: Gateway routing equivalence.

    For any tool invocation with valid parameters and a valid JWT,
    routing through AgentCore Gateway produces a response equivalent
    to invoking the tool function directly.

    The mock Gateway calls the real tool function once and captures
    the raw result. The test then verifies that GatewayToolClient's
    response parsing returns that exact same result — proving the
    client does not lose or transform data during parsing.
    """

    @given(
        schema=st.sampled_from(_TESTABLE_SCHEMAS),
        data=st.data(),
    )
    @settings(max_examples=100)
    def test_gateway_client_preserves_tool_result(
        self,
        schema: dict[str, Any],
        data: st.DataObject,
    ) -> None:
        """GatewayToolClient.invoke_tool returns the exact tool result.

        The mock Gateway forwards to the real @tool function and wraps
        the result in ``{"output": result}``. The client's
        ``_parse_response`` must extract and return the result unchanged.

        # Feature: agentcore-platform-integration, Property 3: Gateway routing equivalence
        **Validates: Requirements 3.3, 3.4**
        """
        params = data.draw(_params_strategy_for(schema), label="tool_params")

        captured: dict[str, Any] = {}
        gateway_mock = _make_capturing_gateway_mock(_SCHEMA_LOOKUP, captured)

        client = GatewayToolClient(
            gateway_id="regain-coaching-gateway",
            jwt_token="mock-jwt-token",
        )
        client.client = gateway_mock

        gateway_result = client.invoke_tool(schema["name"], params)

        # The raw tool result captured by the mock must equal what the
        # client returned after parsing the Gateway response.
        raw_result = captured["raw"]

        assert type(raw_result) == type(gateway_result), (
            f"Type mismatch for {schema['name']}: "
            f"raw={type(raw_result)}, gateway={type(gateway_result)}"
        )

        if isinstance(raw_result, dict):
            assert raw_result.keys() == gateway_result.keys(), (
                f"Key mismatch for {schema['name']}: "
                f"raw keys={sorted(raw_result.keys())}, "
                f"gateway keys={sorted(gateway_result.keys())}"
            )
            for key in raw_result:
                assert raw_result[key] == gateway_result[key], (
                    f"Value mismatch for {schema['name']}['{key}']: "
                    f"raw={raw_result[key]!r}, gateway={gateway_result[key]!r}"
                )
        elif isinstance(raw_result, list):
            assert raw_result == gateway_result
        else:
            assert raw_result == gateway_result

    @given(
        schema=st.sampled_from(_TESTABLE_SCHEMAS),
        data=st.data(),
    )
    @settings(max_examples=100)
    def test_gateway_forwards_all_params_to_tool(
        self,
        schema: dict[str, Any],
        data: st.DataObject,
    ) -> None:
        """Gateway mock receives the exact params the client was given.

        Verifies that GatewayToolClient passes tool_name and params
        through to the boto3 invoke_tool call without modification.

        # Feature: agentcore-platform-integration, Property 3: Gateway routing equivalence
        **Validates: Requirements 3.3, 3.4**
        """
        params = data.draw(_params_strategy_for(schema), label="tool_params")

        captured: dict[str, Any] = {}
        gateway_mock = _make_capturing_gateway_mock(_SCHEMA_LOOKUP, captured)

        client = GatewayToolClient(
            gateway_id="regain-coaching-gateway",
            jwt_token="mock-jwt-token",
        )
        client.client = gateway_mock

        client.invoke_tool(schema["name"], params)

        # Verify the mock was called with the correct arguments
        gateway_mock.invoke_tool.assert_called_once()
        call_kwargs = gateway_mock.invoke_tool.call_args.kwargs

        assert call_kwargs["toolName"] == schema["name"], (
            f"Tool name mismatch: expected {schema['name']}, "
            f"got {call_kwargs['toolName']}"
        )
        assert call_kwargs["input"] == params, (
            f"Params mismatch for {schema['name']}: "
            f"expected {params}, got {call_kwargs['input']}"
        )
        assert call_kwargs["authorizationToken"] == "mock-jwt-token", (
            "JWT token not forwarded to Gateway"
        )
        assert call_kwargs["gatewayId"] == "regain-coaching-gateway", (
            "Gateway ID not forwarded correctly"
        )
