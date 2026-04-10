"""Client for invoking coaching tools through AgentCore Gateway.

Provides a thin wrapper that the Coaching Agent uses to discover and invoke
tools via the AgentCore Gateway MCP endpoint instead of direct imports.
Each discovered tool is returned as a Strands-compatible module-like object
with a TOOL_SPEC and handler function.
"""

import logging
import os
import re
from types import ModuleType
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from backend.agents.coaching.tool_schemas import get_tool_schemas

logger = logging.getLogger(__name__)


class GatewayToolClient:
    """Client for invoking coaching tools through AgentCore Gateway.

    Discovers tools from the Gateway's MCP endpoint and creates Strands-
    compatible tool wrappers that route invocations through the Gateway
    with JWT authorization and Cedar policy evaluation.

    Args:
        gateway_id: The AgentCore Gateway instance identifier.
        jwt_token: The user's Cognito JWT for Gateway authorization.
    """

    def __init__(self, gateway_id: str, jwt_token: str) -> None:
        self.gateway_id = gateway_id
        self.jwt_token = jwt_token
        self.endpoint_url = os.environ.get("AGENTCORE_GATEWAY_ENDPOINT", "")
        self.client = boto3.client(
            "bedrock-agentcore",
            region_name=os.environ.get("AWS_REGION", "us-east-1"),
        )

    def discover_tools(self) -> list[ModuleType]:
        """Discover available tools from the Gateway and return Strands-compatible wrappers.

        Calls the Gateway's MCP tool discovery endpoint, then builds a
        module-like object for each tool containing a ``TOOL_SPEC`` dict
        and a handler function. The handler routes calls through
        ``invoke_tool`` so every invocation passes through Gateway auth
        and policy layers.

        Returns:
            A list of module-like objects that can be passed directly to
            ``Agent(tools=...)``.
        """
        schemas = self._fetch_tool_schemas()
        tools: list[ModuleType] = []
        for schema in schemas:
            tool_module = self._build_tool_module(schema)
            tools.append(tool_module)
        return tools

    def invoke_tool(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        """Invoke a tool through Gateway with JWT auth and policy evaluation.

        Sends the tool invocation request to the AgentCore Gateway. The
        Gateway validates the JWT, evaluates Cedar policies, and routes
        to the backing Lambda. On any Gateway or connection error, returns
        a structured error dict rather than raising an exception.

        Args:
            tool_name: The MCP tool name (e.g. "regain_read_user_profile").
            params: The tool input parameters as a dict.

        Returns:
            The tool result dict on success, or a structured error dict
            with "error" and "message" keys on failure.
        """
        try:
            response = self.client.invoke_tool(
                gatewayId=self.gateway_id,
                toolName=tool_name,
                input=params,
                authorizationToken=self.jwt_token,
            )
            return self._parse_response(response)
        except ClientError as exc:
            return self._handle_client_error(exc, tool_name)
        except BotoCoreError as exc:
            logger.exception("Gateway connection error invoking %s", tool_name)
            self._record_gateway_failure()
            return {
                "error": "gateway_unavailable",
                "message": "AgentCore Gateway is temporarily unavailable",
            }
        except Exception as exc:
            logger.exception("Unexpected error invoking %s via Gateway", tool_name)
            self._record_gateway_failure()
            return {
                "error": "gateway_unavailable",
                "message": "AgentCore Gateway is temporarily unavailable",
            }

    def execute_code(self, code: str, session_id: str) -> dict[str, Any]:
        """Execute agent-generated Python code via the Code Interpreter.

        Routes the code through AgentCore Gateway to the sandboxed Code
        Interpreter. If the execution produces an output file, uploads it
        to S3 and returns a presigned URL (1-hour expiry).

        Only agent-generated code is accepted. Empty or whitespace-only
        code is rejected. A basic safety check rejects code containing
        ``input()`` calls, which would indicate user-submitted interactive
        code rather than agent-generated visualization code.

        Args:
            code: Python source code to execute (agent-generated only).
            session_id: The coaching session ID for interpreter reuse.

        Returns:
            A dict with keys: url, execution_status, stdout, stderr.
            On validation failure, returns an error dict.
        """
        if not code or not code.strip():
            return {
                "error": "validation_failed",
                "message": "Code must not be empty",
            }

        if not self._is_agent_generated_code(code):
            return {
                "error": "validation_failed",
                "message": "Only agent-generated code is accepted",
            }

        result = self.invoke_tool(
            "regain_code_interpreter",
            {"code": code, "session_id": session_id},
        )

        if "error" in result:
            return result

        # If the interpreter produced an output file key, generate a presigned URL.
        output_key = result.get("output_key")
        if output_key:
            url = self._generate_presigned_url(output_key)
            result["url"] = url
            result.pop("output_key", None)

        return {
            "url": result.get("url", ""),
            "execution_status": result.get("execution_status", "success"),
            "stdout": result.get("stdout", ""),
            "stderr": result.get("stderr", ""),
        }

    # -- Private helpers -----------------------------------------------------

    @staticmethod
    def _record_gateway_failure() -> None:
        """Record a failure on the gateway circuit breaker.

        Lazy-imports circuit_breaker to avoid circular dependencies.
        """
        from backend.agents.coaching.circuit_breaker import gateway_circuit
        gateway_circuit.record_failure()

    @staticmethod
    def _is_agent_generated_code(code: str) -> bool:
        """Check that code appears to be agent-generated, not user-submitted.

        Rejects code containing interactive input patterns (``input()``)
        that indicate a user pasted arbitrary code rather than the agent
        generating visualization code.

        Args:
            code: The Python source to validate.

        Returns:
            True if the code passes the safety check.
        """
        # Reject interactive input() calls — agent code never uses them.
        if re.search(r"\binput\s*\(", code):
            return False
        return True

    def _generate_presigned_url(self, object_key: str, expiry: int = 3600) -> str:
        """Generate a presigned S3 URL for a Code Interpreter output file.

        Args:
            object_key: The S3 object key for the output file.
            expiry: URL expiry in seconds (default 3600 = 1 hour).

        Returns:
            A presigned URL string, or empty string on failure.
        """
        bucket = os.environ.get("CODE_INTERPRETER_BUCKET", "")
        if not bucket:
            logger.error("CODE_INTERPRETER_BUCKET environment variable not set")
            return ""

        try:
            s3_client = boto3.client(
                "s3",
                region_name=os.environ.get("AWS_REGION", "us-east-1"),
            )
            return s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": object_key},
                ExpiresIn=expiry,
            )
        except (ClientError, BotoCoreError) as exc:
            logger.error("Failed to generate presigned URL: %s", exc)
            return ""

    def _fetch_tool_schemas(self) -> list[dict[str, Any]]:
        """Fetch tool schemas from the Gateway MCP discovery endpoint.

        Calls the Gateway's list_tools API. If the Gateway is unreachable,
        falls back to the locally defined schemas so the agent can still
        build its tool list (invocations will fail at call time with a
        clear error).

        Returns:
            A list of MCP tool schema dicts.
        """
        try:
            response = self.client.list_tools(gatewayId=self.gateway_id)
            return response.get("tools", [])
        except (ClientError, BotoCoreError) as exc:
            logger.warning(
                "Gateway discovery failed, using local schemas: %s", exc
            )
            return get_tool_schemas()
        except Exception as exc:
            logger.warning(
                "Unexpected error during tool discovery, using local schemas: %s",
                exc,
            )
            return get_tool_schemas()

    def _build_tool_module(self, schema: dict[str, Any]) -> ModuleType:
        """Build a Strands-compatible module-like object from a tool schema.

        Creates a ``ModuleType`` with a ``TOOL_SPEC`` attribute and a
        handler function named after the tool. The handler delegates to
        ``invoke_tool`` so all calls route through the Gateway.

        Args:
            schema: An MCP tool schema dict with name, description, and
                input_schema keys.

        Returns:
            A module-like object usable in ``Agent(tools=[...])``.
        """
        tool_name = schema["name"]
        description = schema.get("description", "")
        input_schema = schema.get("input_schema", {"type": "object", "properties": {}})

        # Filter out JWT-injected params — the agent should not supply them.
        filtered_properties = {}
        required = []
        for key, prop in input_schema.get("properties", {}).items():
            if prop.get("x-jwt-injected"):
                continue
            filtered_properties[key] = {
                k: v for k, v in prop.items() if k != "x-jwt-injected"
            }
            if key in input_schema.get("required", []):
                required.append(key)

        tool_spec = {
            "name": tool_name,
            "description": description,
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": filtered_properties,
                    "required": required,
                }
            },
        }

        # Capture self in closure for the handler.
        client_ref = self

        def handler(tool: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
            tool_use_id = tool.get("toolUseId", "")
            tool_input = tool.get("input", {})

            result = client_ref.invoke_tool(tool_name, tool_input)

            if "error" in result:
                return {
                    "toolUseId": tool_use_id,
                    "status": "error",
                    "content": [{"text": f"{result['error']}: {result['message']}"}],
                }
            return {
                "toolUseId": tool_use_id,
                "status": "success",
                "content": [{"json": result}],
            }

        # Build the module-like object.
        module = ModuleType(tool_name)
        module.TOOL_SPEC = tool_spec  # type: ignore[attr-defined]
        setattr(module, tool_name, handler)

        return module

    def _parse_response(self, response: dict[str, Any]) -> dict[str, Any]:
        """Parse a successful Gateway invoke_tool response.

        Args:
            response: The raw boto3 response dict.

        Returns:
            The tool result dict extracted from the response.
        """
        # The Gateway response wraps the Lambda output.
        output = response.get("output", response.get("body", {}))
        if isinstance(output, dict):
            return output
        return {"result": output}

    def _handle_client_error(
        self, exc: ClientError, tool_name: str
    ) -> dict[str, Any]:
        """Map a boto3 ClientError to a structured error dict.

        Args:
            exc: The ClientError raised by the boto3 call.
            tool_name: The tool that was being invoked.

        Returns:
            A structured error dict with "error" and "message" keys.
        """
        error_code = exc.response.get("Error", {}).get("Code", "")
        error_message = exc.response.get("Error", {}).get("Message", "")

        error_map: dict[str, dict[str, str]] = {
            "UnauthorizedException": {
                "error": "unauthorized",
                "message": "Invalid or expired authentication token",
            },
            "AccessDeniedException": {
                "error": "policy_denied",
                "message": error_message or "Access denied by policy",
            },
            "ResourceNotFoundException": {
                "error": "tool_not_found",
                "message": f"Tool '{tool_name}' is not registered in the gateway",
            },
            "ValidationException": {
                "error": "validation_failed",
                "message": error_message or "Input validation failed",
            },
            "ServiceUnavailableException": {
                "error": "gateway_unavailable",
                "message": "AgentCore Gateway is temporarily unavailable",
            },
            "ThrottlingException": {
                "error": "gateway_unavailable",
                "message": "AgentCore Gateway is temporarily unavailable",
            },
        }

        mapped = error_map.get(error_code)
        if mapped:
            logger.warning("Gateway error for %s: %s", tool_name, error_code)
            if mapped["error"] == "gateway_unavailable":
                self._record_gateway_failure()
            return mapped

        logger.exception("Unhandled Gateway ClientError for %s", tool_name)
        return {
            "error": "tool_execution_failed",
            "message": error_message or f"Tool invocation failed for '{tool_name}'",
        }
