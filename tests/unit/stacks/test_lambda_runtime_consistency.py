"""Property test for Lambda runtime consistency.

**Property 7: Lambda Runtime Consistency**
**Validates: Requirements 6.9, 9.2**

Verifies that all Lambda functions created by the API Stack use Python 3.12 runtime.
"""

import aws_cdk as cdk
from hypothesis import given, settings, strategies as st

from infra.stacks.auth_stack import AuthStack
from infra.stacks.data_stack import DataStack
from infra.stacks.api_stack import ApiStack


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
    """Extract all Lambda Function resources from the template."""
    return [
        (logical_id, resource)
        for logical_id, resource in template.get("Resources", {}).items()
        if resource.get("Type") == "AWS::Lambda::Function"
    ]


# The API stack creates exactly 5 Lambda functions:
# Onboarding, Missions, Evidence, Coaching, Dashboard
EXPECTED_LAMBDA_COUNT = 5


@given(
    lambda_index=st.integers(min_value=0, max_value=EXPECTED_LAMBDA_COUNT - 1),
)
@settings(max_examples=100, deadline=None)
def test_all_lambdas_use_python_312_runtime(lambda_index: int) -> None:
    """For all Lambda functions in the API Stack, each function must use
    Python 3.12 runtime for consistency and efficiency.

    The lambda_index parameter selects which function to verify on each
    iteration, ensuring every function is checked across many runs.
    """
    template = _synth_api_template()
    lambdas = _get_lambda_functions(template)

    assert len(lambdas) == EXPECTED_LAMBDA_COUNT, (
        f"Expected {EXPECTED_LAMBDA_COUNT} Lambda functions, found {len(lambdas)}"
    )

    logical_id, resource = lambdas[lambda_index % len(lambdas)]
    props = resource.get("Properties", {})

    runtime = props.get("Runtime")
    assert runtime == "python3.12", (
        f"Lambda {logical_id} has Runtime={runtime}, expected python3.12"
    )
