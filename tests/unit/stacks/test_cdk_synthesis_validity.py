"""Property test for CDK synthesis validity.

**Property 1: CDK Synthesis Validity**
**Validates: Requirements 1.3**

Verifies that all CDK stacks in the REGAIN application produce valid
CloudFormation templates when synthesized.
"""

import aws_cdk as cdk
from hypothesis import given, settings, strategies as st

from infra.stacks.auth_stack import AuthStack
from infra.stacks.data_stack import DataStack
from infra.stacks.api_stack import ApiStack

STACK_NAMES = ["RegainAuthStack", "RegainDataStack", "RegainApiStack"]

# Every valid CloudFormation template must declare resources
_REQUIRED_CFN_KEYS = {"Resources"}

# CloudFormation template top-level keys that are allowed
_VALID_CFN_TOP_KEYS = {
    "AWSTemplateFormatVersion",
    "Description",
    "Metadata",
    "Parameters",
    "Rules",
    "Mappings",
    "Conditions",
    "Transform",
    "Resources",
    "Outputs",
}


def _synth_app(
    extra_tags: list[tuple[str, str]] | None = None,
) -> dict[str, dict]:
    """Synthesize the full CDK app and return templates keyed by stack name.

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


def _assert_valid_cfn_template(template: dict, stack_name: str) -> None:
    """Assert that a CloudFormation template dict is structurally valid.

    Checks:
    - Template is a non-empty dict
    - Contains the required 'Resources' section
    - All top-level keys are valid CloudFormation keys
    - At least one resource is defined
    - Every resource has a valid Type string
    """
    assert isinstance(template, dict), (
        f"{stack_name}: template is not a dict"
    )
    assert len(template) > 0, f"{stack_name}: template is empty"

    for key in _REQUIRED_CFN_KEYS:
        assert key in template, (
            f"{stack_name}: missing required key '{key}'"
        )

    for key in template:
        assert key in _VALID_CFN_TOP_KEYS, (
            f"{stack_name}: unexpected top-level key '{key}'"
        )

    resources = template["Resources"]
    assert isinstance(resources, dict), (
        f"{stack_name}: Resources is not a dict"
    )
    assert len(resources) > 0, (
        f"{stack_name}: Resources section is empty"
    )

    for logical_id, resource in resources.items():
        assert "Type" in resource, (
            f"{stack_name}/{logical_id}: resource missing 'Type'"
        )
        rtype = resource["Type"]
        assert isinstance(rtype, str) and "::" in rtype, (
            f"{stack_name}/{logical_id}: invalid Type '{rtype}'"
        )


# Strategy: pick a stack and optionally add extra tags to perturb synthesis
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


@given(
    stack_index=st.integers(min_value=0, max_value=len(STACK_NAMES) - 1),
    extra_tags=st.lists(
        st.tuples(_tag_key_st, _tag_value_st),
        min_size=0,
        max_size=3,
    ),
)
@settings(max_examples=100, deadline=None)
def test_stacks_produce_valid_cloudformation_templates(
    stack_index: int,
    extra_tags: list[tuple[str, str]],
) -> None:
    """For any CDK stack in the application, when synthesized with any
    combination of additional tags, it should produce a valid CloudFormation
    template.

    The stack_index selects which stack to verify. The extra_tags parameter
    adds arbitrary tags to the app before synthesis, ensuring that tag
    variations do not break template validity.

    Feature: platform-foundation, Property 1: CDK Synthesis Validity
    """
    templates = _synth_app(extra_tags=extra_tags)
    stack_name = STACK_NAMES[stack_index]
    _assert_valid_cfn_template(templates[stack_name], stack_name)
