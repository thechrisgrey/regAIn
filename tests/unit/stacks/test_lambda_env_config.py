"""Property test for Lambda environment configuration.

**Property 8: Lambda Environment Configuration**
**Validates: Requirements 6.10**

Verifies that all Lambda functions created by the API Stack receive
DynamoDB table names via environment variables.
"""

import aws_cdk as cdk
from hypothesis import given, settings, strategies as st

from infra.stacks.auth_stack import AuthStack
from infra.stacks.data_stack import DataStack
from infra.stacks.api_stack import ApiStack


# The five required DynamoDB table environment variables.
REQUIRED_TABLE_ENV_VARS = [
    "USER_PROFILES_TABLE",
    "CAMPAIGNS_TABLE",
    "MISSION_HISTORY_TABLE",
    "EVIDENCE_VAULT_TABLE",
    "MARKET_DATA_TABLE",
]

EXPECTED_LAMBDA_COUNT = 6


def _synth_api_template() -> dict:
    """Synthesize the full CDK app in-process and return the ApiStack template."""
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


def _get_lambda_functions(template: dict) -> list[tuple[str, dict]]:
    """Extract all AWS::Lambda::Function resources from the template."""
    return [
        (logical_id, resource)
        for logical_id, resource in template.get("Resources", {}).items()
        if resource.get("Type") == "AWS::Lambda::Function"
    ]


@given(
    lambda_index=st.integers(min_value=0, max_value=EXPECTED_LAMBDA_COUNT - 1),
    env_var_index=st.integers(min_value=0, max_value=len(REQUIRED_TABLE_ENV_VARS) - 1),
)
@settings(max_examples=100, deadline=None)
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
    template = _synth_api_template()
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
