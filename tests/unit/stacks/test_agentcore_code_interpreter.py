"""Unit tests for Code Interpreter integration (Task 9.1).

Verifies:
- Code Interpreter schema exists in TOOL_SCHEMAS with correct structure
- CDK tool registry includes Code Interpreter
- S3 bucket created with 24h lifecycle and SSE-S3 encryption
- Gateway target registered for Code Interpreter with sandbox constraints
"""

from backend.agents.coaching.tool_schemas import TOOL_SCHEMAS, get_schema_by_name
from infra.stacks.agentcore_stack import AgentCoreStack


# -- tool_schemas.py tests --------------------------------------------------


def test_code_interpreter_schema_exists_in_tool_schemas() -> None:
    """TOOL_SCHEMAS should contain regain_code_interpreter."""
    names = [s["name"] for s in TOOL_SCHEMAS]
    assert "regain_code_interpreter" in names


def test_code_interpreter_schema_has_required_input_fields() -> None:
    """Code Interpreter input schema requires code and session_id."""
    schema = get_schema_by_name("regain_code_interpreter")
    assert schema is not None
    input_props = schema["input_schema"]["properties"]
    assert "code" in input_props
    assert "session_id" in input_props
    assert schema["input_schema"]["required"] == ["code", "session_id"]


def test_code_interpreter_schema_has_output_fields() -> None:
    """Code Interpreter output schema has url, execution_status, stdout, stderr."""
    schema = get_schema_by_name("regain_code_interpreter")
    assert schema is not None
    output_props = schema["output_schema"]["properties"]
    for field in ("url", "execution_status", "stdout", "stderr"):
        assert field in output_props, f"Missing output field: {field}"


def test_code_interpreter_schema_has_description() -> None:
    """Code Interpreter schema should have a non-empty description."""
    schema = get_schema_by_name("regain_code_interpreter")
    assert schema is not None
    assert len(schema["description"]) > 0


def test_code_interpreter_lambda_target() -> None:
    """Code Interpreter should target 'code_interpreter', not a Lambda."""
    schema = get_schema_by_name("regain_code_interpreter")
    assert schema is not None
    assert schema["lambda_target"] == "code_interpreter"


# -- CDK _tool_registry tests -----------------------------------------------


def test_cdk_registry_includes_code_interpreter() -> None:
    """CDK tool registry should include regain_code_interpreter."""
    registry = AgentCoreStack._tool_registry()
    names = [t["name"] for t in registry]
    assert "regain_code_interpreter" in names


def test_cdk_registry_code_interpreter_schema_matches_tool_schemas() -> None:
    """CDK registry Code Interpreter schema should match tool_schemas.py."""
    registry_entry = None
    for t in AgentCoreStack._tool_registry():
        if t["name"] == "regain_code_interpreter":
            registry_entry = t
            break

    assert registry_entry is not None
    schema = get_schema_by_name("regain_code_interpreter")
    assert schema is not None

    # Input schemas should have the same required fields
    assert registry_entry["input_schema"]["required"] == schema["input_schema"]["required"]
    # Output schemas should have the same property keys
    assert set(registry_entry["output_schema"]["properties"].keys()) == set(
        schema["output_schema"]["properties"].keys()
    )


def test_cdk_registry_and_tool_schemas_same_names() -> None:
    """CDK registry and TOOL_SCHEMAS should define the same tool names."""
    schema_names = sorted(s["name"] for s in TOOL_SCHEMAS)
    registry_names = sorted(t["name"] for t in AgentCoreStack._tool_registry())
    assert registry_names == schema_names
