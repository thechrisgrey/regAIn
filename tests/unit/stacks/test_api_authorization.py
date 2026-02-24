"""Property test for API authorization enforcement.

**Property 6: API Authorization Enforcement**
**Validates: Requirements 6.8**

Verifies that all API Gateway endpoints (excluding CORS OPTIONS methods)
have the Cognito authorizer attached to validate JWT tokens.
"""

import aws_cdk as cdk
from hypothesis import given, settings, strategies as st

from infra.stacks.auth_stack import AuthStack
from infra.stacks.data_stack import DataStack
from infra.stacks.api_stack import ApiStack


def _synth_api_template() -> dict:
    """Synthesize the full CDK app and return the ApiStack CloudFormation template.

    Note: Tests must be run from the infra/ directory (or with cwd=infra/)
    so that Code.from_asset("../backend") resolves correctly.
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
    assembly = app.synth()
    return assembly.get_stack_by_name("RegainApiStack").template


def _get_api_methods(template: dict) -> list[tuple[str, dict]]:
    """Extract all API Gateway Method resources from the template."""
    return [
        (logical_id, resource)
        for logical_id, resource in template.get("Resources", {}).items()
        if resource.get("Type") == "AWS::ApiGateway::Method"
    ]


def _get_non_options_methods(template: dict) -> list[tuple[str, dict]]:
    """Extract API Gateway Methods that are NOT OPTIONS (CORS preflight)."""
    return [
        (lid, res)
        for lid, res in _get_api_methods(template)
        if res.get("Properties", {}).get("HttpMethod") != "OPTIONS"
    ]


def _get_authorizer_ids(template: dict) -> set[str]:
    """Extract logical IDs of all Cognito authorizer resources."""
    return {
        logical_id
        for logical_id, resource in template.get("Resources", {}).items()
        if resource.get("Type") == "AWS::ApiGateway::Authorizer"
        and resource.get("Properties", {}).get("Type") == "COGNITO_USER_POOLS"
    }


# The API stack defines exactly 10 non-OPTIONS methods:
# POST /onboarding, GET /missions, POST /missions/generate,
# POST /missions/{missionId}/complete, GET /evidence,
# POST /coaching/checkin, GET /dashboard, DELETE /profile,
# GET /onet/search, GET /onet/careers/{soc_code}
EXPECTED_METHOD_COUNT = 10


@given(
    method_index=st.integers(min_value=0, max_value=EXPECTED_METHOD_COUNT - 1),
)
@settings(max_examples=100, deadline=None)
def test_all_endpoints_have_cognito_authorizer(method_index: int) -> None:
    """For all API Gateway endpoints (excluding OPTIONS), each endpoint must
    have a Cognito authorizer attached with COGNITO_USER_POOLS authorization type.

    The method_index parameter selects which method to verify on each iteration,
    ensuring every endpoint is checked across many runs.
    """
    template = _synth_api_template()

    methods = _get_non_options_methods(template)
    assert len(methods) == EXPECTED_METHOD_COUNT, (
        f"Expected {EXPECTED_METHOD_COUNT} non-OPTIONS API methods, "
        f"found {len(methods)}"
    )

    authorizer_ids = _get_authorizer_ids(template)
    assert len(authorizer_ids) > 0, "Expected at least one Cognito authorizer"

    logical_id, resource = methods[method_index % len(methods)]
    props = resource.get("Properties", {})

    # Must use COGNITO_USER_POOLS authorization type
    auth_type = props.get("AuthorizationType")
    assert auth_type == "COGNITO_USER_POOLS", (
        f"Method {logical_id} ({props.get('HttpMethod')}) has "
        f"AuthorizationType={auth_type}, expected COGNITO_USER_POOLS"
    )

    # Must reference a valid Cognito authorizer
    authorizer_ref = props.get("AuthorizerId", {})
    # CDK generates a Ref to the authorizer logical ID
    ref_value = authorizer_ref.get("Ref", "") if isinstance(authorizer_ref, dict) else ""
    assert ref_value in authorizer_ids, (
        f"Method {logical_id} ({props.get('HttpMethod')}) references "
        f"authorizer '{ref_value}' which is not a Cognito authorizer. "
        f"Known authorizers: {authorizer_ids}"
    )
