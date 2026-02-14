"""Property test for resource naming convention.

**Property 13: Resource Naming Convention**
**Validates: Requirements 8.4**

Verifies that all AWS resources created by the CDK application have names
prefixed with "Regain".
"""

import aws_cdk as cdk
from hypothesis import given, settings, strategies as st

from infra.stacks.auth_stack import AuthStack
from infra.stacks.data_stack import DataStack
from infra.stacks.api_stack import ApiStack

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

# Strategy for extra tags to perturb synthesis across iterations
_tag_key_st = st.text(
    alphabet=st.characters(whitelist_categories=("L",)),
    min_size=1,
    max_size=20,
)
_tag_value_st = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N")),
    min_size=1,
    max_size=50,
)


def _synth_app(
    extra_tags: list[tuple[str, str]] | None = None,
) -> dict[str, dict]:
    """Synthesize the full CDK app and return templates keyed by stack name.

    Note: Tests must be run from the infra/ directory (or with cwd=infra/)
    so that Code.from_asset("../backend") resolves correctly.

    Args:
        extra_tags: Optional additional tags to apply alongside required ones.

    Returns:
        Dict mapping stack name to its CloudFormation template.
    """
    app = cdk.App()

    auth_stack = AuthStack(app, "RegainAuthStack")
    data_stack = DataStack(app, "RegainDataStack")
    ApiStack(
        app,
        "RegainApiStack",
        user_pool=auth_stack.user_pool,
        tables=data_stack.tables,
    )

    cdk.Tags.of(app).add("Project", "REGAIN")
    cdk.Tags.of(app).add("Environment", "dev")

    for key, value in (extra_tags or []):
        cdk.Tags.of(app).add(key, value)

    assembly = app.synth()
    return {
        name: assembly.get_stack_by_name(name).template
        for name in STACK_NAMES
    }


@given(
    stack_index=st.integers(min_value=0, max_value=len(STACK_NAMES) - 1),
    extra_tags=st.lists(
        st.tuples(_tag_key_st, _tag_value_st),
        min_size=0,
        max_size=3,
    ),
)
@settings(max_examples=100, deadline=None)
def test_resource_names_prefixed_with_regain(
    stack_index: int,
    extra_tags: list[tuple[str, str]],
) -> None:
    """For all AWS resources with explicit physical names, each name should
    be prefixed with 'Regain'.

    The extra_tags parameter adds arbitrary tags before synthesis, ensuring
    that tag variations do not break the naming convention.

    Feature: platform-foundation, Property 13: Resource Naming Convention
    """
    templates = _synth_app(extra_tags=extra_tags)
    stack_name = STACK_NAMES[stack_index]
    template = templates[stack_name]

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
    extra_tags=st.lists(
        st.tuples(_tag_key_st, _tag_value_st),
        min_size=0,
        max_size=3,
    ),
)
@settings(max_examples=100, deadline=None)
def test_cloudformation_export_names_prefixed_with_regain(
    stack_index: int,
    extra_tags: list[tuple[str, str]],
) -> None:
    """For all CloudFormation exports, each export name should be prefixed
    with 'Regain'.

    The extra_tags parameter adds arbitrary tags before synthesis, ensuring
    that tag variations do not break the export naming convention.

    Feature: platform-foundation, Property 13: Resource Naming Convention
    """
    templates = _synth_app(extra_tags=extra_tags)
    stack_name = STACK_NAMES[stack_index]
    template = templates[stack_name]

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
