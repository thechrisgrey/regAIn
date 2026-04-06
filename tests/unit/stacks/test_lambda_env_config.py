"""Property test for Lambda environment configuration.

**Property 8: Lambda Environment Configuration**
**Validates: Requirements 6.10**

Verifies that all Lambda functions created by the API Stack receive
DynamoDB table names via environment variables.
"""

from hypothesis import given, settings, strategies as st

from tests.unit.stacks.conftest import _synth_all_templates


# The five required DynamoDB table environment variables.
REQUIRED_TABLE_ENV_VARS = [
    "USER_PROFILES_TABLE",
    "CAMPAIGNS_TABLE",
    "MISSION_HISTORY_TABLE",
    "EVIDENCE_VAULT_TABLE",
    "MARKET_DATA_TABLE",
]

EXPECTED_LAMBDA_COUNT = 8


_CACHED_TEMPLATE = _synth_all_templates()["RegainApiStack"]


def _get_lambda_functions(template: dict) -> list[tuple[str, dict]]:
    """Extract all AWS::Lambda::Function resources from the template (excluding LogRetention provider Lambdas)."""
    return [
        (logical_id, resource)
        for logical_id, resource in template.get("Resources", {}).items()
        if resource.get("Type") == "AWS::Lambda::Function"
        and "LogRetention" not in logical_id
    ]


@given(
    lambda_index=st.integers(min_value=0, max_value=EXPECTED_LAMBDA_COUNT - 1),
    env_var_index=st.integers(min_value=0, max_value=len(REQUIRED_TABLE_ENV_VARS) - 1),
)
@settings(deadline=None)
def test_all_lambdas_have_table_env_vars(
    lambda_index: int, env_var_index: int
) -> None:
    """For all Lambda functions that access DynamoDB, each function should
    receive table names via environment variables.

    **Validates: Requirements 6.10**

    The lambda_index selects which function to check and env_var_index
    selects which environment variable to verify, ensuring full coverage
    across many iterations.
    """
    template = _CACHED_TEMPLATE
    lambdas = _get_lambda_functions(template)

    assert len(lambdas) == EXPECTED_LAMBDA_COUNT, (
        f"Expected {EXPECTED_LAMBDA_COUNT} Lambda functions, found {len(lambdas)}"
    )

    logical_id, resource = lambdas[lambda_index % len(lambdas)]
    props = resource.get("Properties", {})
    env_vars = props.get("Environment", {}).get("Variables", {})

    required_var = REQUIRED_TABLE_ENV_VARS[env_var_index]
    assert required_var in env_vars, (
        f"Lambda {logical_id} is missing environment variable {required_var}. "
        f"Present vars: {list(env_vars.keys())}"
    )
