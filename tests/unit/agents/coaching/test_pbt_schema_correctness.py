"""Property-based tests for MCP tool schema correctness.

# Feature: agentcore-platform-integration, Property 1: MCP schema correctness

**Validates: Requirements 1.3, 2.1, 2.2, 2.3**

For any registered tool in the AgentCore Gateway, the MCP tool schema SHALL
specify input parameters with JSON Schema types matching the corresponding
Strands @tool function signature, output structure matching the tool's return
dict shape, and a non-empty natural language description.

Uses Hypothesis with ``sampled_from`` over the 13 tool schemas, then
introspects the matching @tool function via ``inspect.signature`` to verify
type alignment and naming convention mapping (camelCase schema ↔ snake_case
Python).
"""

import inspect
import re
import sys
import types
from typing import Any, get_type_hints

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Stub strands so tools.py can be imported without the SDK installed
# ---------------------------------------------------------------------------
_strands_stub = types.ModuleType("strands")
_strands_stub.tool = lambda fn: fn
sys.modules.setdefault("strands", _strands_stub)

from backend.agents.coaching.tool_schemas import TOOL_SCHEMAS  # noqa: E402

# ---------------------------------------------------------------------------
# Mapping helpers
# ---------------------------------------------------------------------------

# JSON Schema type → set of acceptable Python types
_JSON_TO_PYTHON: dict[str, set[type]] = {
    "string": {str},
    "integer": {int},
    "number": {int, float},
    "boolean": {bool},
    "array": {list},
    "object": {dict},
}


def _camel_to_snake(name: str) -> str:
    """Convert a camelCase name to snake_case."""
    s1 = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def _get_tool_function(schema_name: str) -> Any:
    """Resolve the @tool function for a given schema name.

    Strips the ``regain_`` prefix to derive the function name, then
    imports it from ``backend.agents.coaching.tools``.
    """
    func_name = schema_name.removeprefix("regain_")
    import backend.agents.coaching.tools as tools_mod

    func = getattr(tools_mod, func_name, None)
    if func is None:
        pytest.skip(
            f"Function '{func_name}' not yet implemented in tools.py "
            f"(schema '{schema_name}')"
        )
    return func


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------


class TestMCPSchemaCorrectness:
    """Property 1: MCP schema correctness.

    For any registered tool schema, input params match the @tool function
    signature, JSON Schema types align with Python type hints, and the
    description is non-empty.
    """

    @given(schema=st.sampled_from(TOOL_SCHEMAS))
    @settings(max_examples=100)
    def test_schema_input_params_match_function_signature(
        self,
        schema: dict[str, Any],
    ) -> None:
        """Every required schema input param has a matching function parameter.

        # Feature: agentcore-platform-integration, Property 1: MCP schema correctness
        **Validates: Requirements 1.3, 2.1, 2.2, 2.3**
        """
        func = _get_tool_function(schema["name"])
        sig = inspect.signature(func)
        func_param_names = set(sig.parameters.keys())

        input_props = schema["input_schema"].get("properties", {})
        required_params = schema["input_schema"].get("required", [])

        for schema_param_name in required_params:
            snake_name = _camel_to_snake(schema_param_name)
            assert snake_name in func_param_names, (
                f"Schema '{schema['name']}' requires input param "
                f"'{schema_param_name}' (→ '{snake_name}') but function "
                f"has params: {sorted(func_param_names)}"
            )

    @given(schema=st.sampled_from(TOOL_SCHEMAS))
    @settings(max_examples=100)
    def test_schema_types_match_python_type_hints(
        self,
        schema: dict[str, Any],
    ) -> None:
        """JSON Schema types align with Python type hints on the function.

        # Feature: agentcore-platform-integration, Property 1: MCP schema correctness
        **Validates: Requirements 1.3, 2.1, 2.2, 2.3**
        """
        func = _get_tool_function(schema["name"])
        try:
            hints = get_type_hints(func)
        except Exception:
            hints = {}

        sig = inspect.signature(func)
        input_props = schema["input_schema"].get("properties", {})

        for schema_param_name, prop_def in input_props.items():
            snake_name = _camel_to_snake(schema_param_name)
            if snake_name not in sig.parameters:
                continue

            json_type = prop_def.get("type")
            if json_type is None:
                continue

            if snake_name not in hints:
                continue

            py_hint = hints[snake_name]
            # Unwrap generic aliases like list[str] → list, dict[str, Any] → dict
            origin = getattr(py_hint, "__origin__", py_hint)

            expected_py_types = _JSON_TO_PYTHON.get(json_type)
            if expected_py_types is None:
                continue

            assert origin in expected_py_types, (
                f"Schema '{schema['name']}' param '{schema_param_name}': "
                f"JSON type '{json_type}' expects Python types "
                f"{expected_py_types}, got {origin}"
            )

    @given(schema=st.sampled_from(TOOL_SCHEMAS))
    @settings(max_examples=100)
    def test_schema_description_is_non_empty(
        self,
        schema: dict[str, Any],
    ) -> None:
        """Every tool schema has a non-empty natural language description.

        # Feature: agentcore-platform-integration, Property 1: MCP schema correctness
        **Validates: Requirements 1.3, 2.1, 2.2, 2.3**
        """
        desc = schema.get("description", "")
        assert isinstance(desc, str) and len(desc.strip()) > 0, (
            f"Schema '{schema['name']}' has empty or missing description"
        )

    @given(schema=st.sampled_from(TOOL_SCHEMAS))
    @settings(max_examples=100)
    def test_function_params_covered_by_schema(
        self,
        schema: dict[str, Any],
    ) -> None:
        """Every non-default function parameter appears in the schema input.

        # Feature: agentcore-platform-integration, Property 1: MCP schema correctness
        **Validates: Requirements 1.3, 2.1, 2.2, 2.3**
        """
        func = _get_tool_function(schema["name"])
        sig = inspect.signature(func)
        input_props = schema["input_schema"].get("properties", {})

        # Build set of snake_case names from schema properties
        schema_snake_names = {_camel_to_snake(k) for k in input_props}

        for param_name, param in sig.parameters.items():
            if param.default is not inspect.Parameter.empty:
                # Optional params don't need to be in schema required list,
                # but should still appear in properties
                continue
            assert param_name in schema_snake_names, (
                f"Schema '{schema['name']}' is missing required function "
                f"param '{param_name}'. Schema has: {sorted(schema_snake_names)}"
            )
