"""Unit tests for AgentCore Gateway tool registration (Task 1.3).

Verifies that AgentCoreStack registers all 13 tool schemas with correct
Lambda target mappings, schema structure, and descriptions. Tests the
_tool_registry() static method directly to avoid CDK synthesis asset-path
issues in CI (Lambda code asset paths are environment-dependent).
"""

from infra.stacks.agentcore_stack import AgentCoreStack


# -- Expected tool-to-target mapping ----------------------------------------

EXPECTED_TOOLS: dict[str, list[str]] = {
    "coaching": [
        "regain_read_user_profile",
        "regain_update_user_profile",
        "regain_get_campaign_status",
        "regain_create_campaign",
        "regain_recall_memory",
        "regain_store_memory",
    ],
    "missions": [
        "regain_get_current_mission",
        "regain_generate_mission",
    ],
    "evidence": [
        "regain_complete_mission",
        "regain_log_evidence",
        "regain_get_evidence_summary",
    ],
    "market_intel": [
        "regain_get_market_insights",
        "regain_get_alignment",
    ],
    "code_interpreter": [
        "regain_code_interpreter",
    ],
}

ALL_TOOL_NAMES = sorted(
    name for names in EXPECTED_TOOLS.values() for name in names
)


def test_registry_contains_exactly_14_tools() -> None:
    """Tool registry should define exactly 14 tool schemas (13 + Code Interpreter)."""
    registry = AgentCoreStack._tool_registry()
    assert len(registry) == 14


def test_all_expected_tool_names_present() -> None:
    """Every expected tool name should appear in the registry."""
    registry = AgentCoreStack._tool_registry()
    registered_names = sorted(t["name"] for t in registry)
    assert registered_names == ALL_TOOL_NAMES


def test_tool_to_lambda_target_mapping() -> None:
    """Each tool should map to the correct Lambda target key."""
    registry = AgentCoreStack._tool_registry()
    by_target: dict[str, list[str]] = {}
    for tool in registry:
        by_target.setdefault(tool["lambda_target"], []).append(tool["name"])

    for target, expected_tools in EXPECTED_TOOLS.items():
        actual = sorted(by_target.get(target, []))
        assert actual == sorted(expected_tools), (
            f"Target '{target}': expected {sorted(expected_tools)}, got {actual}"
        )


def test_each_tool_has_required_schema_fields() -> None:
    """Each tool must have name, description, input_schema, output_schema, and lambda_target."""
    registry = AgentCoreStack._tool_registry()
    required_keys = {"name", "description", "lambda_target", "input_schema", "output_schema"}

    for tool in registry:
        missing = required_keys - tool.keys()
        assert not missing, f"{tool.get('name', '?')}: missing keys {missing}"
        assert len(tool["description"]) > 0, f"{tool['name']}: empty description"
        assert isinstance(tool["input_schema"], dict), f"{tool['name']}: input_schema not dict"
        assert isinstance(tool["output_schema"], dict), f"{tool['name']}: output_schema not dict"


def test_input_schemas_have_type_object() -> None:
    """All input schemas should be JSON Schema type 'object'."""
    registry = AgentCoreStack._tool_registry()
    for tool in registry:
        schema = tool["input_schema"]
        assert schema.get("type") == "object", (
            f"{tool['name']}: input_schema type is '{schema.get('type')}', expected 'object'"
        )


def test_registry_matches_tool_schemas_module() -> None:
    """CDK tool registry should define the same 13 tools as tool_schemas.py."""
    from backend.agents.coaching.tool_schemas import TOOL_SCHEMAS

    schema_names = sorted(s["name"] for s in TOOL_SCHEMAS)
    registry_names = sorted(t["name"] for t in AgentCoreStack._tool_registry())
    assert registry_names == schema_names


def test_registry_lambda_targets_match_schemas_module() -> None:
    """CDK tool registry lambda_target keys should match tool_schemas.py."""
    from backend.agents.coaching.tool_schemas import TOOL_SCHEMAS

    schema_targets = {s["name"]: s["lambda_target"] for s in TOOL_SCHEMAS}
    registry_targets = {
        t["name"]: t["lambda_target"]
        for t in AgentCoreStack._tool_registry()
    }
    assert registry_targets == schema_targets
