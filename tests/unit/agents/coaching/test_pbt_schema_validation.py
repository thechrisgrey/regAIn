"""Property-based tests for input schema validation.

# Feature: agentcore-platform-integration, Property 11: Input schema validation

**Validates: Requirements 2.4, 2.5**

For any tool invocation where the input payload does not conform to the
registered MCP tool schema (missing required fields, wrong types), the
Gateway SHALL reject the request with a structured validation error without
invoking the Lambda target. For any tool invocation with a conforming input
payload, the Gateway SHALL forward the request to the Lambda target.

Strategy:
- Import TOOL_SCHEMAS from tool_schemas.py.
- Build a lightweight JSON Schema validator (jsonschema is not installed).
- Use Hypothesis to generate random VALID payloads that conform to each
  tool's input_schema → verify they pass validation.
- Use Hypothesis to generate random INVALID payloads (missing required
  fields, wrong types) → verify they fail validation.
- The test validates the CONTRACT: valid payloads accepted, invalid rejected.
"""

import sys
import types
from typing import Any

# ---------------------------------------------------------------------------
# Stub strands so tool_schemas.py can be imported
# ---------------------------------------------------------------------------
_strands_stub = types.ModuleType("strands")
_strands_stub.tool = lambda fn: fn  # type: ignore[attr-defined]
sys.modules.setdefault("strands", _strands_stub)

from hypothesis import given, settings, assume  # noqa: E402
from hypothesis import strategies as st  # noqa: E402

from backend.agents.coaching.tool_schemas import TOOL_SCHEMAS  # noqa: E402


# ---------------------------------------------------------------------------
# Lightweight JSON Schema validator
# ---------------------------------------------------------------------------

# Maps JSON Schema type strings to Python types for validation.
_JSON_TYPE_MAP: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "array": (list,),
    "object": (dict,),
}


def validate_payload(payload: Any, schema: dict[str, Any]) -> list[str]:
    """Validate a payload against a JSON Schema subset.

    Checks top-level type, required fields, and property types.
    Returns a list of validation error strings (empty means valid).

    Args:
        payload: The value to validate.
        schema: A JSON Schema dict with type, properties, required.

    Returns:
        List of error description strings. Empty if valid.
    """
    errors: list[str] = []

    expected_type = schema.get("type")
    if expected_type and expected_type in _JSON_TYPE_MAP:
        if not isinstance(payload, _JSON_TYPE_MAP[expected_type]):
            errors.append(
                f"Expected type '{expected_type}', got {type(payload).__name__}"
            )
            return errors  # Can't check properties on wrong top-level type

    if expected_type == "object" and isinstance(payload, dict):
        # Check required fields
        for field in schema.get("required", []):
            if field not in payload:
                errors.append(f"Missing required field: '{field}'")

        # Check property types
        properties = schema.get("properties", {})
        for key, value in payload.items():
            if key in properties:
                prop_schema = properties[key]
                prop_type = prop_schema.get("type")
                if prop_type and prop_type in _JSON_TYPE_MAP:
                    if not isinstance(value, _JSON_TYPE_MAP[prop_type]):
                        errors.append(
                            f"Field '{key}': expected type '{prop_type}', "
                            f"got {type(value).__name__}"
                        )

    return errors


# ---------------------------------------------------------------------------
# Gateway validation model
# ---------------------------------------------------------------------------


def gateway_validate_and_route(
    tool_name: str,
    payload: dict[str, Any],
    schema: dict[str, Any],
) -> dict[str, Any]:
    """Simulate Gateway input validation before routing to Lambda.

    Models the Gateway behavior from Requirements 2.4 and 2.5:
    - Validate input payload against the registered MCP tool schema.
    - If invalid, return a structured validation error (no Lambda invocation).
    - If valid, forward to Lambda target (simulated as success).

    Args:
        tool_name: The MCP tool name.
        payload: The input payload to validate.
        schema: The tool's input_schema from TOOL_SCHEMAS.

    Returns:
        A dict with either a success indicator or a validation error.
    """
    errors = validate_payload(payload, schema)

    if errors:
        return {
            "error": "validation_failed",
            "message": f"Input validation failed for tool '{tool_name}'",
            "details": [
                {"field": e.split("'")[1] if "'" in e else "payload", "violation": e}
                for e in errors
            ],
        }

    return {"status": "routed", "tool_name": tool_name}


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALL_TOOL_NAMES: list[str] = [s["name"] for s in TOOL_SCHEMAS]

# Build a lookup from tool name to its input_schema.
_SCHEMA_BY_NAME: dict[str, dict[str, Any]] = {
    s["name"]: s["input_schema"] for s in TOOL_SCHEMAS
}


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

_tool_schema = st.sampled_from(TOOL_SCHEMAS)

# Values that conform to JSON Schema types.
_string_value = st.text(min_size=1, max_size=30)
_integer_value = st.integers(min_value=0, max_value=10_000)
_number_value = st.one_of(
    st.integers(min_value=0, max_value=10_000),
    st.floats(min_value=0.0, max_value=10_000.0, allow_nan=False, allow_infinity=False),
)
_boolean_value = st.booleans()
_array_of_strings = st.lists(_string_value, min_size=0, max_size=5)
_object_value = st.dictionaries(
    keys=st.text(min_size=1, max_size=10),
    values=_string_value,
    min_size=0,
    max_size=3,
)

_VALUE_BY_TYPE: dict[str, st.SearchStrategy[Any]] = {
    "string": _string_value,
    "integer": _integer_value,
    "number": _number_value,
    "boolean": _boolean_value,
    "array": _array_of_strings,
    "object": _object_value,
}

# Values that are the WRONG type for a given JSON Schema type.
_WRONG_TYPE_VALUES: dict[str, st.SearchStrategy[Any]] = {
    "string": st.integers(min_value=0, max_value=100),
    "integer": st.text(min_size=1, max_size=10),
    "number": st.text(min_size=1, max_size=10),
    "boolean": st.text(min_size=1, max_size=10),
    "array": st.text(min_size=1, max_size=10),
    "object": st.text(min_size=1, max_size=10),
}


def _build_valid_payload(schema: dict[str, Any], draw: st.DrawFn) -> dict[str, Any]:
    """Build a payload that conforms to the given input_schema.

    Args:
        schema: A tool's input_schema dict.
        draw: Hypothesis draw function for generating values.

    Returns:
        A dict with all required fields set to correctly-typed values.
    """
    payload: dict[str, Any] = {}
    properties = schema.get("properties", {})
    required = schema.get("required", [])

    for field_name in required:
        prop = properties.get(field_name, {})
        prop_type = prop.get("type", "string")
        strategy = _VALUE_BY_TYPE.get(prop_type, _string_value)
        payload[field_name] = draw(strategy)

    return payload


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------


class TestInputSchemaValidation:
    """Property 11: Input schema validation.

    For random valid and invalid payloads per tool schema, verify
    accept/reject behavior.
    """

    @given(tool_schema=_tool_schema, data=st.data())
    @settings(max_examples=100)
    def test_valid_payloads_are_accepted(
        self,
        tool_schema: dict[str, Any],
        data: st.DataObject,
    ) -> None:
        """Valid payloads conforming to the tool's input_schema SHALL be
        forwarded to the Lambda target (not rejected).

        # Feature: agentcore-platform-integration, Property 11: Input schema validation
        **Validates: Requirements 2.4, 2.5**
        """
        input_schema = tool_schema["input_schema"]
        tool_name = tool_schema["name"]

        payload = _build_valid_payload(input_schema, data.draw)

        result = gateway_validate_and_route(tool_name, payload, input_schema)

        assert result.get("status") == "routed", (
            f"Valid payload for {tool_name} was rejected: {result}"
        )
        assert result["tool_name"] == tool_name

    @given(tool_schema=_tool_schema, data=st.data())
    @settings(max_examples=100)
    def test_missing_required_field_is_rejected(
        self,
        tool_schema: dict[str, Any],
        data: st.DataObject,
    ) -> None:
        """Payloads missing a required field SHALL be rejected with a
        structured validation error.

        # Feature: agentcore-platform-integration, Property 11: Input schema validation
        **Validates: Requirements 2.4, 2.5**
        """
        input_schema = tool_schema["input_schema"]
        tool_name = tool_schema["name"]
        required = input_schema.get("required", [])

        assume(len(required) >= 1)

        # Build a valid payload, then remove one required field.
        payload = _build_valid_payload(input_schema, data.draw)
        field_to_remove = data.draw(st.sampled_from(required))
        payload.pop(field_to_remove, None)

        result = gateway_validate_and_route(tool_name, payload, input_schema)

        assert result.get("error") == "validation_failed", (
            f"Payload missing '{field_to_remove}' for {tool_name} was not "
            f"rejected: {result}"
        )
        assert "details" in result
        assert any(
            field_to_remove in d.get("violation", "")
            for d in result["details"]
        ), (
            f"Validation error for {tool_name} does not mention missing "
            f"field '{field_to_remove}': {result['details']}"
        )

    @given(tool_schema=_tool_schema, data=st.data())
    @settings(max_examples=100)
    def test_wrong_type_field_is_rejected(
        self,
        tool_schema: dict[str, Any],
        data: st.DataObject,
    ) -> None:
        """Payloads with a wrong-typed field SHALL be rejected with a
        structured validation error.

        # Feature: agentcore-platform-integration, Property 11: Input schema validation
        **Validates: Requirements 2.4, 2.5**
        """
        input_schema = tool_schema["input_schema"]
        tool_name = tool_schema["name"]
        properties = input_schema.get("properties", {})
        required = input_schema.get("required", [])

        # Find a required field that has a concrete type we can mismatch.
        typed_fields = [
            f for f in required
            if properties.get(f, {}).get("type") in _WRONG_TYPE_VALUES
        ]
        assume(len(typed_fields) >= 1)

        payload = _build_valid_payload(input_schema, data.draw)
        field_to_corrupt = data.draw(st.sampled_from(typed_fields))
        field_type = properties[field_to_corrupt]["type"]
        payload[field_to_corrupt] = data.draw(_WRONG_TYPE_VALUES[field_type])

        result = gateway_validate_and_route(tool_name, payload, input_schema)

        assert result.get("error") == "validation_failed", (
            f"Payload with wrong type for '{field_to_corrupt}' on "
            f"{tool_name} was not rejected: {result}"
        )
        assert "details" in result

    @given(tool_schema=_tool_schema, data=st.data())
    @settings(max_examples=100)
    def test_empty_payload_is_rejected_when_fields_required(
        self,
        tool_schema: dict[str, Any],
        data: st.DataObject,
    ) -> None:
        """An empty payload SHALL be rejected when the schema has required
        fields.

        # Feature: agentcore-platform-integration, Property 11: Input schema validation
        **Validates: Requirements 2.4, 2.5**
        """
        input_schema = tool_schema["input_schema"]
        tool_name = tool_schema["name"]
        required = input_schema.get("required", [])

        assume(len(required) >= 1)

        result = gateway_validate_and_route(tool_name, {}, input_schema)

        assert result.get("error") == "validation_failed", (
            f"Empty payload for {tool_name} (requires {required}) was not "
            f"rejected: {result}"
        )
        assert len(result["details"]) >= 1

    @given(tool_schema=_tool_schema)
    @settings(max_examples=100)
    def test_non_object_payload_is_rejected(
        self,
        tool_schema: dict[str, Any],
    ) -> None:
        """A non-object payload (string, int, list) SHALL be rejected when
        the schema expects type 'object'.

        # Feature: agentcore-platform-integration, Property 11: Input schema validation
        **Validates: Requirements 2.4, 2.5**
        """
        input_schema = tool_schema["input_schema"]
        tool_name = tool_schema["name"]

        assume(input_schema.get("type") == "object")

        # Try a string payload instead of an object.
        result = gateway_validate_and_route(
            tool_name, "not_an_object", input_schema  # type: ignore[arg-type]
        )

        assert result.get("error") == "validation_failed", (
            f"Non-object payload for {tool_name} was not rejected: {result}"
        )
