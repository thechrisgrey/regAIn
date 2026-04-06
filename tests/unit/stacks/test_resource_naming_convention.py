"""Property test for resource naming convention.

**Property 13: Resource Naming Convention**
**Validates: Requirements 8.4**

Verifies that all AWS resources created by the CDK application have names
prefixed with "Regain".
"""

from hypothesis import given, settings, strategies as st

from tests.unit.stacks.conftest import _synth_all_templates

STACK_NAMES = ["RegainAuthStack", "RegainDataStack", "RegainApiStack"]

# Resource types that carry explicit physical names we control
_NAMED_RESOURCE_PROPS = {
    "AWS::Cognito::UserPool": "UserPoolName",
    "AWS::Cognito::UserPoolClient": "ClientName",
    "AWS::DynamoDB::Table": "TableName",
    "AWS::Lambda::Function": "FunctionName",
    "AWS::ApiGateway::RestApi": "Name",
    "AWS::ApiGateway::Authorizer": "Name",
}

# Synthesize once — naming convention is deterministic regardless of tags
_CACHED_TEMPLATES = _synth_all_templates()


@given(
    stack_index=st.integers(min_value=0, max_value=len(STACK_NAMES) - 1),
)
@settings(deadline=None)
def test_resource_names_prefixed_with_regain(stack_index: int) -> None:
    """For all AWS resources with explicit physical names, each name should
    be prefixed with 'Regain'.

    Feature: platform-foundation, Property 13: Resource Naming Convention
    """
    stack_name = STACK_NAMES[stack_index]
    template = _CACHED_TEMPLATES[stack_name]

    for logical_id, resource in template.get("Resources", {}).items():
        resource_type = resource.get("Type", "")
        props = resource.get("Properties", {})

        name_key = _NAMED_RESOURCE_PROPS.get(resource_type)
        if name_key is None:
            continue

        physical_name = props.get(name_key)
        if physical_name is None:
            continue

        # Skip names that are CloudFormation intrinsic functions (Ref, Fn::Join, etc.)
        if isinstance(physical_name, dict):
            continue

        assert str(physical_name).startswith("Regain"), (
            f"{stack_name}/{logical_id} ({resource_type}): "
            f"physical name '{physical_name}' does not start with 'Regain'"
        )


@given(
    stack_index=st.integers(min_value=0, max_value=len(STACK_NAMES) - 1),
)
@settings(deadline=None)
def test_cloudformation_export_names_prefixed_with_regain(stack_index: int) -> None:
    """For all CloudFormation exports, each export name should be prefixed
    with 'Regain'.

    Feature: platform-foundation, Property 13: Resource Naming Convention
    """
    stack_name = STACK_NAMES[stack_index]
    template = _CACHED_TEMPLATES[stack_name]

    outputs = template.get("Outputs", {})
    for output_id, output_def in outputs.items():
        export = output_def.get("Export", {})
        export_name = export.get("Name")
        if export_name is None:
            continue

        # Skip intrinsic functions
        if isinstance(export_name, dict):
            continue

        assert str(export_name).startswith("Regain"), (
            f"{stack_name}/{output_id}: export name '{export_name}' "
            f"does not start with 'Regain'"
        )
