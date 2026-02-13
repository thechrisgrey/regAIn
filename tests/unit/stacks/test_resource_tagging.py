"""Property test for resource tagging consistency.

**Property 2: Resource Tagging Consistency**
**Validates: Requirements 1.4, 8.5, 8.6**

Verifies that all taggable AWS resources created by the CDK application
have Project=REGAIN and Environment=dev tags applied.
"""

import aws_cdk as cdk
from aws_cdk.assertions import Template
from hypothesis import given, settings, strategies as st

from infra.stacks.auth_stack import AuthStack

# CloudFormation resource types that support standard Tags property (list of Key/Value dicts)
_STANDARD_TAG_TYPES = {
    "AWS::DynamoDB::Table",
    "AWS::Lambda::Function",
    "AWS::ApiGateway::RestApi",
    "AWS::ApiGateway::Stage",
    "AWS::S3::Bucket",
    "AWS::IAM::Role",
    "AWS::StepFunctions::StateMachine",
}

# Resource types that use a dict-style tag property instead of the standard list
_DICT_TAG_TYPES = {
    "AWS::Cognito::UserPool": "UserPoolTags",
}

# Resource types that do not support tags at all
_UNTAGGABLE_TYPES = {
    "AWS::Cognito::UserPoolClient",
}

REQUIRED_TAGS = {"Project": "REGAIN", "Environment": "dev"}


def _synth_app_template(stack_name: str = "RegainAuthStack") -> dict:
    """Synthesize the CDK app with tags applied at the app level.

    Returns:
        Raw CloudFormation template dict.
    """
    app = cdk.App()
    AuthStack(app, "RegainAuthStack")

    for key, value in REQUIRED_TAGS.items():
        cdk.Tags.of(app).add(key, value)

    assembly = app.synth()
    return assembly.get_stack_by_name(stack_name).template


def _extract_tags_from_resource(resource: dict) -> dict[str, str]:
    """Extract tags from a CloudFormation resource regardless of tag format.

    Handles both standard Tags (list of Key/Value) and dict-style tags
    like UserPoolTags.

    Returns:
        Dict mapping tag key to tag value.
    """
    props = resource.get("Properties", {})
    rtype = resource["Type"]

    # Dict-style tags (e.g. Cognito UserPoolTags)
    if rtype in _DICT_TAG_TYPES:
        tag_prop = _DICT_TAG_TYPES[rtype]
        tag_dict = props.get(tag_prop, {})
        return dict(tag_dict)

    # Standard Tags property (list of {Key, Value} dicts)
    tag_list = props.get("Tags", [])
    return {t["Key"]: t["Value"] for t in tag_list if "Key" in t and "Value" in t}


def _get_taggable_resources(template: dict) -> list[tuple[str, dict]]:
    """Return list of (logical_id, resource) for resources that support tags."""
    results = []
    for logical_id, resource in template.get("Resources", {}).items():
        rtype = resource.get("Type", "")
        if rtype not in _UNTAGGABLE_TYPES:
            results.append((logical_id, resource))
    return results


@given(
    extra_tag_key=st.text(
        alphabet=st.characters(whitelist_categories=("L",)),
        min_size=1,
        max_size=20,
    ),
    extra_tag_value=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N")),
        min_size=1,
        max_size=50,
    ),
)
@settings(max_examples=100)
def test_required_tags_present_on_all_taggable_resources(
    extra_tag_key: str, extra_tag_value: str
) -> None:
    """For all taggable resources in the CDK app, each resource must have
    Project=REGAIN and Environment=dev tags, regardless of any additional
    tags that are also applied.

    The extra_tag_key/value parameters verify that adding arbitrary extra
    tags does not interfere with the required tags.
    """
    app = cdk.App()
    AuthStack(app, "RegainAuthStack")

    # Apply required tags
    for key, value in REQUIRED_TAGS.items():
        cdk.Tags.of(app).add(key, value)

    # Apply an arbitrary extra tag
    cdk.Tags.of(app).add(extra_tag_key, extra_tag_value)

    assembly = app.synth()
    template = assembly.get_stack_by_name("RegainAuthStack").template

    taggable = _get_taggable_resources(template)
    assert len(taggable) > 0, "Expected at least one taggable resource"

    for logical_id, resource in taggable:
        tags = _extract_tags_from_resource(resource)
        for req_key, req_value in REQUIRED_TAGS.items():
            assert req_key in tags, (
                f"Resource {logical_id} ({resource['Type']}) missing "
                f"required tag '{req_key}'"
            )
            assert tags[req_key] == req_value, (
                f"Resource {logical_id} ({resource['Type']}) has "
                f"tag '{req_key}={tags[req_key]}', expected '{req_value}'"
            )
