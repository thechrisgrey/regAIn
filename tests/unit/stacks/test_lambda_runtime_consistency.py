"""Property test for Lambda runtime consistency.

**Property 7: Lambda Runtime Consistency**
**Validates: Requirements 6.9, 9.2**

Verifies that all Lambda functions created by the API Stack use Python 3.12 runtime.
"""

from hypothesis import given, settings, strategies as st

from tests.unit.stacks.conftest import _synth_all_templates

_CACHED_TEMPLATE = _synth_all_templates()["RegainApiStack"]


def _get_lambda_functions(template: dict) -> list[tuple[str, dict]]:
    """Extract all Lambda Function resources from the template (excluding LogRetention provider Lambdas)."""
    return [
        (logical_id, resource)
        for logical_id, resource in template.get("Resources", {}).items()
        if resource.get("Type") == "AWS::Lambda::Function"
        and "LogRetention" not in logical_id
    ]


# The API stack creates exactly 8 Lambda functions:
# Onboarding, Missions, Evidence, Coaching, Dashboard, Profile, Onet, Cleanup
EXPECTED_LAMBDA_COUNT = 8


@given(
    lambda_index=st.integers(min_value=0, max_value=EXPECTED_LAMBDA_COUNT - 1),
)
@settings(deadline=None)
def test_all_lambdas_use_python_312_runtime(lambda_index: int) -> None:
    """For all Lambda functions in the API Stack, each function must use
    Python 3.12 runtime for consistency and efficiency.

    The lambda_index parameter selects which function to verify on each
    iteration, ensuring every function is checked across many runs.
    """
    template = _CACHED_TEMPLATE
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
