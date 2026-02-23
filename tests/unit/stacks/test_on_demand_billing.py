"""Property test for on-demand billing mode.

**Property 4: On-Demand Billing Mode**
**Validates: Requirements 5.10, 9.1, 9.4**

Verifies that all DynamoDB tables created by the Data Stack use on-demand
(PAY_PER_REQUEST) billing mode and do not specify provisioned throughput.
"""

import aws_cdk as cdk
from hypothesis import given, settings, strategies as st

from infra.stacks.data_stack import DataStack

EXPECTED_TABLE_COUNT = 7


def _synth_data_stack_template() -> dict:
    """Synthesize the DataStack and return the raw CloudFormation template."""
    app = cdk.App()
    DataStack(app, "RegainDataStack")
    assembly = app.synth()
    return assembly.get_stack_by_name("RegainDataStack").template


def _get_dynamodb_tables(template: dict) -> list[tuple[str, dict]]:
    """Extract all DynamoDB table resources from a CloudFormation template."""
    return [
        (logical_id, resource)
        for logical_id, resource in template.get("Resources", {}).items()
        if resource.get("Type") == "AWS::DynamoDB::Table"
    ]


@given(
    table_index=st.integers(min_value=0, max_value=EXPECTED_TABLE_COUNT - 1),
)
@settings(max_examples=100)
def test_all_tables_use_on_demand_billing(table_index: int) -> None:
    """For all DynamoDB tables in the Data Stack, each table must use
    PAY_PER_REQUEST billing mode and must not specify provisioned throughput.

    The table_index parameter selects which table to verify on each iteration,
    ensuring every table is checked across many runs.
    """
    template = _synth_data_stack_template()
    tables = _get_dynamodb_tables(template)

    assert len(tables) == EXPECTED_TABLE_COUNT, (
        f"Expected {EXPECTED_TABLE_COUNT} DynamoDB tables, found {len(tables)}"
    )

    logical_id, resource = tables[table_index % len(tables)]
    props = resource.get("Properties", {})

    # Must use PAY_PER_REQUEST billing mode
    billing_mode = props.get("BillingMode")
    assert billing_mode == "PAY_PER_REQUEST", (
        f"Table {logical_id} has BillingMode={billing_mode}, "
        f"expected PAY_PER_REQUEST"
    )

    # Must not have provisioned throughput configured
    provisioned = props.get("ProvisionedThroughput")
    assert provisioned is None, (
        f"Table {logical_id} has ProvisionedThroughput={provisioned}, "
        f"expected None for on-demand billing"
    )
