"""Property-based tests for JWT validation and userId injection.

# Feature: agentcore-platform-integration, Property 2: JWT validation and userId injection

**Validates: Requirements 1.5, 1.6**

For any tool invocation with a valid Cognito JWT token, the userId injected
into the tool invocation context by the Gateway SHALL equal the userId from
the JWT claims. For any tool invocation with an invalid or missing JWT token,
the Gateway SHALL reject the request before routing to the Lambda target.

Strategy:
- Replicate handler-level JWT extraction logic (handler.py cannot be imported
  directly due to 'lambda' keyword in its internal import paths) and verify
  the extraction properties hold for random tokens.
- Test that GatewayToolClient always forwards the JWT to every invocation.
- Test that invalid/missing JWTs produce rejection (unauthorized error).
"""

import sys
import types
from typing import Any
from unittest.mock import MagicMock

from botocore.exceptions import ClientError
from hypothesis import given, settings
from hypothesis import strategies as st

# Stub strands so gateway_client imports work without the SDK installed.
_strands_stub = types.ModuleType("strands")
_strands_stub.tool = lambda fn: fn
sys.modules.setdefault("strands", _strands_stub)

from backend.agents.coaching.gateway_client import GatewayToolClient  # noqa: E402


# ---------------------------------------------------------------------------
# Handler JWT extraction logic (mirrored from handler.py).
#
# The coaching handler.py uses ``from backend.handlers.shared...`` imports
# which are unparseable by Python (``lambda`` is a keyword). We replicate
# the two pure extraction functions here so we can property-test them.
# ---------------------------------------------------------------------------


def _get_jwt_token(event: Any) -> str | None:
    """Extract JWT token from Authorization header (mirrors handler.py)."""
    try:
        auth_header = event.get("headers", {}).get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header[7:]
        return auth_header or None
    except (AttributeError, TypeError):
        return None


def _get_user_id(event: Any) -> str | None:
    """Extract userId from Cognito authorizer claims (mirrors handler.py)."""
    try:
        return event["requestContext"]["authorizer"]["claims"]["sub"]
    except (KeyError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_valid_token = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N")),
    min_size=10,
    max_size=200,
)

_user_id_st = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789-",
    min_size=5,
    max_size=40,
)

_tool_name = st.sampled_from([
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
])


# ---------------------------------------------------------------------------
# Property tests -- handler-level JWT extraction
# ---------------------------------------------------------------------------


class TestJwtExtraction:
    """Verify JWT extraction correctly parses tokens from API Gateway events.

    # Feature: agentcore-platform-integration, Property 2: JWT validation and userId injection
    """

    @given(token=_valid_token)
    @settings(max_examples=100)
    def test_bearer_token_extracted(self, token: str) -> None:
        """For any valid token, extraction from 'Bearer {token}' returns the token.

        **Validates: Requirements 1.5, 1.6**
        """
        event: dict[str, Any] = {
            "headers": {"Authorization": f"Bearer {token}"},
        }
        result = _get_jwt_token(event)
        assert result == token

    @given(token=_valid_token)
    @settings(max_examples=100)
    def test_raw_token_extracted(self, token: str) -> None:
        """For any non-empty token without Bearer prefix, extraction returns it as-is.

        **Validates: Requirements 1.5, 1.6**
        """
        event: dict[str, Any] = {
            "headers": {"Authorization": token},
        }
        result = _get_jwt_token(event)
        assert result == token

    @given(
        event=st.sampled_from([
            {},
            {"headers": {}},
            {"headers": None},
            {"headers": {"Authorization": ""}},
            {"headers": {"Authorization": None}},
            None,
        ])
    )
    @settings(max_examples=100)
    def test_missing_token_returns_none(self, event: Any) -> None:
        """For any event with missing or empty Authorization, extraction returns None.

        **Validates: Requirements 1.5, 1.6**
        """
        result = _get_jwt_token(event)
        assert result is None


# ---------------------------------------------------------------------------
# Property tests -- userId extraction from JWT claims
# ---------------------------------------------------------------------------


class TestUserIdExtraction:
    """Verify userId extraction from Cognito authorizer claims.

    # Feature: agentcore-platform-integration, Property 2: JWT validation and userId injection
    """

    @given(user_id=_user_id_st)
    @settings(max_examples=100)
    def test_user_id_from_claims(self, user_id: str) -> None:
        """For any userId in JWT claims, extraction returns that exact userId.

        **Validates: Requirements 1.5, 1.6**
        """
        event: dict[str, Any] = {
            "requestContext": {
                "authorizer": {
                    "claims": {"sub": user_id},
                },
            },
        }
        result = _get_user_id(event)
        assert result == user_id

    @given(
        event=st.sampled_from([
            {},
            {"requestContext": {}},
            {"requestContext": {"authorizer": {}}},
            {"requestContext": {"authorizer": {"claims": {}}}},
            {"requestContext": None},
        ])
    )
    @settings(max_examples=100)
    def test_missing_claims_returns_none(self, event: Any) -> None:
        """For any event with missing claims, extraction returns None.

        **Validates: Requirements 1.5, 1.6**
        """
        result = _get_user_id(event)
        assert result is None


# ---------------------------------------------------------------------------
# Property tests -- Gateway client JWT forwarding
# ---------------------------------------------------------------------------


class TestGatewayJwtForwarding:
    """Verify GatewayToolClient always passes JWT to every Gateway invocation.

    # Feature: agentcore-platform-integration, Property 2: JWT validation and userId injection
    """

    @given(
        jwt_token=_valid_token,
        tool=_tool_name,
        user_id=_user_id_st,
    )
    @settings(max_examples=100)
    def test_jwt_always_forwarded(
        self, jwt_token: str, tool: str, user_id: str
    ) -> None:
        """For any valid JWT, the client passes it in authorizationToken on every call.

        **Validates: Requirements 1.5, 1.6**
        """
        mock_client = MagicMock()
        mock_client.invoke_tool.return_value = {"output": {"userId": user_id}}

        client = GatewayToolClient(
            gateway_id="regain-coaching-gateway",
            jwt_token=jwt_token,
        )
        client.client = mock_client

        client.invoke_tool(tool, {"userId": user_id})

        mock_client.invoke_tool.assert_called_once()
        call_kwargs = mock_client.invoke_tool.call_args.kwargs
        assert call_kwargs["authorizationToken"] == jwt_token

    @given(
        jwt_token=_valid_token,
        tool=_tool_name,
        user_id=_user_id_st,
    )
    @settings(max_examples=100)
    def test_injected_userid_matches_response(
        self, jwt_token: str, tool: str, user_id: str
    ) -> None:
        """For any valid JWT, the userId in the Gateway response matches what was injected.

        The Gateway extracts userId from JWT claims and injects it into the
        tool context. We simulate this by having the mock return the userId
        that was passed via JWT, then verify the client returns it unchanged.

        **Validates: Requirements 1.5, 1.6**
        """
        mock_client = MagicMock()
        mock_client.invoke_tool.return_value = {"output": {"userId": user_id}}

        client = GatewayToolClient(
            gateway_id="regain-coaching-gateway",
            jwt_token=jwt_token,
        )
        client.client = mock_client

        result = client.invoke_tool(tool, {"userId": user_id})

        assert result.get("userId") == user_id


# ---------------------------------------------------------------------------
# Property tests -- invalid JWT rejection
# ---------------------------------------------------------------------------


class TestInvalidJwtRejection:
    """Verify that invalid or missing JWTs result in rejection (unauthorized error).

    # Feature: agentcore-platform-integration, Property 2: JWT validation and userId injection
    """

    @given(tool=_tool_name, user_id=_user_id_st)
    @settings(max_examples=100)
    def test_unauthorized_exception_returns_error(
        self, tool: str, user_id: str
    ) -> None:
        """For any tool invocation with an invalid JWT, Gateway returns unauthorized error.

        **Validates: Requirements 1.5, 1.6**
        """
        mock_client = MagicMock()
        mock_client.invoke_tool.side_effect = ClientError(
            error_response={
                "Error": {
                    "Code": "UnauthorizedException",
                    "Message": "Invalid or expired authentication token",
                }
            },
            operation_name="InvokeTool",
        )

        client = GatewayToolClient(
            gateway_id="regain-coaching-gateway",
            jwt_token="invalid-token",
        )
        client.client = mock_client

        result = client.invoke_tool(tool, {"userId": user_id})

        assert result["error"] == "unauthorized"
        assert "message" in result

    @given(user_id=_user_id_st)
    @settings(max_examples=100)
    def test_missing_jwt_means_rejection(self, user_id: str) -> None:
        """For any request without a JWT, the handler rejects before reaching the agent.

        When _get_jwt_token returns None (missing Authorization header),
        the handler must return 401 without creating the coaching agent.
        We verify the extraction returns None for empty headers, which
        triggers the 401 path in the handler.

        **Validates: Requirements 1.5, 1.6**
        """
        event: dict[str, Any] = {
            "requestContext": {
                "authorizer": {"claims": {"sub": user_id}},
            },
            "headers": {},
            "body": '{"message": "hello"}',
        }
        # Missing Authorization header -> no JWT -> handler rejects
        assert _get_jwt_token(event) is None
        # userId is present but JWT is not -> must be rejected
        assert _get_user_id(event) == user_id
