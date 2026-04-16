"""Unit tests for the GatewayToolClient module.

Tests cover: tool discovery, tool invocation, error handling for all
Gateway error types, and Strands-compatible tool module construction.
"""

import os
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import BotoCoreError, ClientError

from backend.agents.coaching.gateway_client import GatewayToolClient


@pytest.fixture()
def _gateway_env(monkeypatch):
    """Set required environment variables for GatewayToolClient."""
    monkeypatch.setenv("AGENTCORE_GATEWAY_ENDPOINT", "https://gateway.example.com")
    monkeypatch.setenv("AWS_REGION", "us-east-1")


@pytest.fixture()
def client(_gateway_env):
    """Return a GatewayToolClient with a mocked boto3 client."""
    with patch("backend.agents.coaching.gateway_client.boto3") as mock_boto3:
        mock_service = MagicMock()
        mock_boto3.client.return_value = mock_service
        gw = GatewayToolClient(
            gateway_id="regain-coaching-gateway",
            jwt_token="test-jwt-token",
        )
        # Expose the mock for assertions.
        gw._mock_service = mock_service  # noqa: SLF001
        yield gw


# -- discover_tools tests ---------------------------------------------------


class TestDiscoverTools:
    """Tests for GatewayToolClient.discover_tools()."""

    def test_returns_strands_compatible_modules(self, client):
        """Each discovered tool should be a ModuleType with TOOL_SPEC and handler."""
        client._mock_service.list_tools.return_value = {
            "tools": [
                {
                    "name": "regain_read_user_profile",
                    "description": "Read a user profile.",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "userId": {
                                "type": "string",
                                "x-jwt-injected": True,
                            },
                        },
                        "required": ["userId"],
                    },
                },
            ],
        }

        tools = client.discover_tools()

        assert len(tools) == 1
        tool_mod = tools[0]
        assert isinstance(tool_mod, ModuleType)
        assert hasattr(tool_mod, "TOOL_SPEC")
        assert hasattr(tool_mod, "regain_read_user_profile")

    def test_filters_jwt_injected_params_from_spec(self, client):
        """JWT-injected params should not appear in the TOOL_SPEC inputSchema."""
        client._mock_service.list_tools.return_value = {
            "tools": [
                {
                    "name": "regain_read_user_profile",
                    "description": "Read a user profile.",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "userId": {
                                "type": "string",
                                "x-jwt-injected": True,
                            },
                        },
                        "required": ["userId"],
                    },
                },
            ],
        }

        tools = client.discover_tools()
        spec = tools[0].TOOL_SPEC
        props = spec["inputSchema"]["json"]["properties"]

        assert "userId" not in props

    def test_preserves_non_injected_params(self, client):
        """Non-injected params should appear in the TOOL_SPEC."""
        client._mock_service.list_tools.return_value = {
            "tools": [
                {
                    "name": "regain_get_market_insights",
                    "description": "Get market insights.",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "roleId": {"type": "string"},
                        },
                        "required": ["roleId"],
                    },
                },
            ],
        }

        tools = client.discover_tools()
        spec = tools[0].TOOL_SPEC
        props = spec["inputSchema"]["json"]["properties"]

        assert "roleId" in props

    def test_falls_back_to_local_schemas_on_gateway_error(self, client):
        """If Gateway discovery fails, local schemas should be used."""
        client._mock_service.list_tools.side_effect = ClientError(
            {"Error": {"Code": "ServiceUnavailableException", "Message": "down"}},
            "ListTools",
        )

        tools = client.discover_tools()

        # Should get tools from local schemas. Grows with TOOL_SCHEMAS —
        # read directly to avoid churn when tools are added.
        from backend.agents.coaching.tool_schemas import TOOL_SCHEMAS

        assert len(tools) == len(TOOL_SCHEMAS)

    def test_tool_handler_routes_through_invoke_tool(self, client):
        """The handler function on a discovered tool should call invoke_tool."""
        client._mock_service.list_tools.return_value = {
            "tools": [
                {
                    "name": "regain_read_user_profile",
                    "description": "Read a user profile.",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "userId": {
                                "type": "string",
                                "x-jwt-injected": True,
                            },
                        },
                        "required": ["userId"],
                    },
                },
            ],
        }
        client._mock_service.invoke_tool.return_value = {
            "output": {"userId": "u1", "name": "Test User"},
        }

        tools = client.discover_tools()
        handler = getattr(tools[0], "regain_read_user_profile")
        result = handler({"toolUseId": "tu-1", "input": {}})

        assert result["status"] == "success"
        assert result["content"][0]["json"]["userId"] == "u1"


# -- invoke_tool tests ------------------------------------------------------


class TestInvokeTool:
    """Tests for GatewayToolClient.invoke_tool()."""

    def test_successful_invocation(self, client):
        """A successful Gateway call should return the tool output dict."""
        client._mock_service.invoke_tool.return_value = {
            "output": {"userId": "u1", "name": "Test"},
        }

        result = client.invoke_tool("regain_read_user_profile", {"userId": "u1"})

        assert result == {"userId": "u1", "name": "Test"}
        client._mock_service.invoke_tool.assert_called_once_with(
            gatewayId="regain-coaching-gateway",
            toolName="regain_read_user_profile",
            input={"userId": "u1"},
            authorizationToken="test-jwt-token",
        )

    def test_unauthorized_error(self, client):
        """An UnauthorizedException should map to an 'unauthorized' error dict."""
        client._mock_service.invoke_tool.side_effect = ClientError(
            {"Error": {"Code": "UnauthorizedException", "Message": "bad token"}},
            "InvokeTool",
        )

        result = client.invoke_tool("regain_read_user_profile", {})

        assert result["error"] == "unauthorized"
        assert "authentication token" in result["message"].lower()

    def test_access_denied_error(self, client):
        """An AccessDeniedException should map to a 'policy_denied' error dict."""
        client._mock_service.invoke_tool.side_effect = ClientError(
            {
                "Error": {
                    "Code": "AccessDeniedException",
                    "Message": "cross-user access denied",
                }
            },
            "InvokeTool",
        )

        result = client.invoke_tool("regain_read_user_profile", {})

        assert result["error"] == "policy_denied"

    def test_resource_not_found_error(self, client):
        """A ResourceNotFoundException should map to 'tool_not_found'."""
        client._mock_service.invoke_tool.side_effect = ClientError(
            {"Error": {"Code": "ResourceNotFoundException", "Message": "no such tool"}},
            "InvokeTool",
        )

        result = client.invoke_tool("regain_nonexistent", {})

        assert result["error"] == "tool_not_found"
        assert "regain_nonexistent" in result["message"]

    def test_validation_error(self, client):
        """A ValidationException should map to 'validation_failed'."""
        client._mock_service.invoke_tool.side_effect = ClientError(
            {"Error": {"Code": "ValidationException", "Message": "bad input"}},
            "InvokeTool",
        )

        result = client.invoke_tool("regain_read_user_profile", {})

        assert result["error"] == "validation_failed"

    def test_service_unavailable_error(self, client):
        """A ServiceUnavailableException should map to 'gateway_unavailable'."""
        client._mock_service.invoke_tool.side_effect = ClientError(
            {"Error": {"Code": "ServiceUnavailableException", "Message": ""}},
            "InvokeTool",
        )

        result = client.invoke_tool("regain_read_user_profile", {})

        assert result["error"] == "gateway_unavailable"

    def test_botocore_error_returns_gateway_unavailable(self, client):
        """A BotoCoreError (connection issue) should return 'gateway_unavailable'."""
        client._mock_service.invoke_tool.side_effect = BotoCoreError()

        result = client.invoke_tool("regain_read_user_profile", {})

        assert result["error"] == "gateway_unavailable"

    def test_unexpected_exception_returns_gateway_unavailable(self, client):
        """Any unexpected exception should return 'gateway_unavailable'."""
        client._mock_service.invoke_tool.side_effect = RuntimeError("boom")

        result = client.invoke_tool("regain_read_user_profile", {})

        assert result["error"] == "gateway_unavailable"

    def test_unknown_client_error_returns_tool_execution_failed(self, client):
        """An unmapped ClientError code should return 'tool_execution_failed'."""
        client._mock_service.invoke_tool.side_effect = ClientError(
            {"Error": {"Code": "InternalServerError", "Message": "oops"}},
            "InvokeTool",
        )

        result = client.invoke_tool("regain_read_user_profile", {})

        assert result["error"] == "tool_execution_failed"


# -- Tool handler error propagation -----------------------------------------


class TestToolHandlerErrors:
    """Verify that tool handler functions propagate errors correctly."""

    def test_handler_returns_error_status_on_gateway_failure(self, client):
        """When invoke_tool returns an error, the handler should set status='error'."""
        client._mock_service.list_tools.return_value = {
            "tools": [
                {
                    "name": "regain_read_user_profile",
                    "description": "Read profile.",
                    "input_schema": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                    },
                },
            ],
        }
        client._mock_service.invoke_tool.side_effect = ClientError(
            {"Error": {"Code": "UnauthorizedException", "Message": "bad"}},
            "InvokeTool",
        )

        tools = client.discover_tools()
        handler = getattr(tools[0], "regain_read_user_profile")
        result = handler({"toolUseId": "tu-1", "input": {}})

        assert result["status"] == "error"
        assert result["toolUseId"] == "tu-1"
        assert len(result["content"]) == 1
        assert "unauthorized" in result["content"][0]["text"]


# -- execute_code tests ------------------------------------------------------


class TestExecuteCode:
    """Tests for GatewayToolClient.execute_code()."""

    def test_calls_invoke_tool_with_correct_params(self, client):
        """execute_code should delegate to invoke_tool with the code interpreter tool."""
        client._mock_service.invoke_tool.return_value = {
            "output": {
                "url": "https://s3.amazonaws.com/bucket/chart.png",
                "execution_status": "success",
                "stdout": "",
                "stderr": "",
            },
        }

        result = client.execute_code(
            code="import matplotlib.pyplot as plt\nplt.plot([1,2,3])\nplt.savefig('out.png')",
            session_id="session-abc",
        )

        client._mock_service.invoke_tool.assert_called_once_with(
            gatewayId="regain-coaching-gateway",
            toolName="regain_code_interpreter",
            input={
                "code": "import matplotlib.pyplot as plt\nplt.plot([1,2,3])\nplt.savefig('out.png')",
                "session_id": "session-abc",
            },
            authorizationToken="test-jwt-token",
        )
        assert result["execution_status"] == "success"

    def test_rejects_empty_code(self, client):
        """Empty code should be rejected without calling Gateway."""
        result = client.execute_code(code="", session_id="session-abc")

        assert result["error"] == "validation_failed"
        assert "empty" in result["message"].lower()
        client._mock_service.invoke_tool.assert_not_called()

    def test_rejects_whitespace_only_code(self, client):
        """Whitespace-only code should be rejected."""
        result = client.execute_code(code="   \n\t  ", session_id="session-abc")

        assert result["error"] == "validation_failed"
        assert "empty" in result["message"].lower()

    def test_rejects_user_submitted_code_with_input(self, client):
        """Code containing input() calls should be rejected as user-submitted."""
        result = client.execute_code(
            code="x = input('Enter value: ')\nprint(x)",
            session_id="session-abc",
        )

        assert result["error"] == "validation_failed"
        assert "agent-generated" in result["message"].lower()
        client._mock_service.invoke_tool.assert_not_called()

    def test_session_id_passed_through(self, client):
        """The session_id should be forwarded to the code interpreter tool."""
        client._mock_service.invoke_tool.return_value = {
            "output": {
                "url": "https://example.com/chart.png",
                "execution_status": "success",
                "stdout": "",
                "stderr": "",
            },
        }

        client.execute_code(code="print('hello')", session_id="my-session-42")

        call_args = client._mock_service.invoke_tool.call_args
        assert call_args.kwargs["input"]["session_id"] == "my-session-42"

    def test_presigned_url_generation(self, client, monkeypatch):
        """When Gateway returns an output_key, a presigned URL should be generated."""
        monkeypatch.setenv("CODE_INTERPRETER_BUCKET", "regain-code-output-bucket")

        client._mock_service.invoke_tool.return_value = {
            "output": {
                "output_key": "sessions/abc/chart.png",
                "execution_status": "success",
                "stdout": "",
                "stderr": "",
            },
        }

        with patch("backend.agents.coaching.gateway_client.boto3") as mock_boto3:
            mock_s3 = MagicMock()
            mock_s3.generate_presigned_url.return_value = (
                "https://regain-code-output-bucket.s3.amazonaws.com/sessions/abc/chart.png?signed=1"
            )
            mock_boto3.client.return_value = mock_s3

            result = client.execute_code(code="plt.savefig('chart.png')", session_id="abc")

        assert "s3.amazonaws.com" in result["url"]
        assert result["execution_status"] == "success"
        mock_s3.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={"Bucket": "regain-code-output-bucket", "Key": "sessions/abc/chart.png"},
            ExpiresIn=3600,
        )

    def test_returns_gateway_error_on_failure(self, client):
        """If invoke_tool returns an error, execute_code should propagate it."""
        client._mock_service.invoke_tool.side_effect = ClientError(
            {"Error": {"Code": "ServiceUnavailableException", "Message": "down"}},
            "InvokeTool",
        )

        result = client.execute_code(code="print('hi')", session_id="s1")

        assert result["error"] == "gateway_unavailable"

    def test_returns_url_directly_when_present(self, client):
        """When Gateway returns a url directly (no output_key), use it as-is."""
        client._mock_service.invoke_tool.return_value = {
            "output": {
                "url": "https://presigned.example.com/chart.png",
                "execution_status": "success",
                "stdout": "done",
                "stderr": "",
            },
        }

        result = client.execute_code(code="plt.savefig('out.png')", session_id="s1")

        assert result["url"] == "https://presigned.example.com/chart.png"
        assert result["stdout"] == "done"
