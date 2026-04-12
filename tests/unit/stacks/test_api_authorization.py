"""Property test for API authorization enforcement.

**Property 6: API Authorization Enforcement**
**Validates: Requirements 6.8**

Verifies that all API Gateway endpoints (excluding CORS OPTIONS methods)
have the Cognito authorizer attached to validate JWT tokens.
"""

from hypothesis import given, settings, strategies as st

from tests.unit.stacks.conftest import _synth_all_templates


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


# The API stack defines exactly 18 non-OPTIONS methods:
# POST /onboarding, GET /missions, POST /missions/generate,
# POST /missions/{missionId}/complete, GET /evidence,
# GET /evidence/suggest-tags, POST /coaching/checkin,
# GET /dashboard, GET /analytics, DELETE /profile,
# POST /profile/recover, GET /onet/search, GET /onet/careers/{soc_code},
# GET /calendar, POST /calendar, PUT /calendar/{dateEntryId},
# DELETE /calendar/{dateEntryId}, GET /calendar/heatmap
EXPECTED_METHOD_COUNT = 18

# Synthesize once, reuse across all Hypothesis examples
_CACHED_TEMPLATE = _synth_all_templates()["RegainApiStack"]


@given(
    method_index=st.integers(min_value=0, max_value=EXPECTED_METHOD_COUNT - 1),
)
@settings(deadline=None)
def test_all_endpoints_have_cognito_authorizer(method_index: int) -> None:
    """For all API Gateway endpoints (excluding OPTIONS), each endpoint must
    have a Cognito authorizer attached with COGNITO_USER_POOLS authorization type.
    """
    template = _CACHED_TEMPLATE

    methods = _get_non_options_methods(template)
    assert len(methods) == EXPECTED_METHOD_COUNT, (
        f"Expected {EXPECTED_METHOD_COUNT} non-OPTIONS API methods, "
        f"found {len(methods)}"
    )

    authorizer_ids = _get_authorizer_ids(template)
    assert len(authorizer_ids) > 0, "Expected at least one Cognito authorizer"

    logical_id, resource = methods[method_index % len(methods)]
    props = resource.get("Properties", {})

    auth_type = props.get("AuthorizationType")
    assert auth_type == "COGNITO_USER_POOLS", (
        f"Method {logical_id} ({props.get('HttpMethod')}) has "
        f"AuthorizationType={auth_type}, expected COGNITO_USER_POOLS"
    )

    authorizer_ref = props.get("AuthorizerId", {})
    ref_value = authorizer_ref.get("Ref", "") if isinstance(authorizer_ref, dict) else ""
    assert ref_value in authorizer_ids, (
        f"Method {logical_id} ({props.get('HttpMethod')}) references "
        f"authorizer '{ref_value}' which is not a Cognito authorizer. "
        f"Known authorizers: {authorizer_ids}"
    )
