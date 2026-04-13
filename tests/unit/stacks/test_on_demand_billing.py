"""Property test for on-demand billing mode.

**Property 4: On-Demand Billing Mode**
**Validates: Requirements 5.10, 9.1, 9.4**

Verifies that all DynamoDB tables created by the Data Stack use on-demand
(PAY_PER_REQUEST) billing mode and do not specify provisioned throughput.
"""

from hypothesis import given, settings, strategies as st

from tests.unit.stacks.conftest import _synth_all_templates

EXPECTED_TABLE_COUNT = 10

_CACHED_TEMPLATE = _synth_all_templates()["RegainDataStack"]


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
@settings(deadline=None)
def test_all_tables_use_on_demand_billing(table_index: int) -> None:
    """For all DynamoDB tables in the Data Stack, each table must use
    PAY_PER_REQUEST billing mode and must not specify provisioned throughput.

    The table_index parameter selects which table to verify on each iteration,
    ensuring every table is checked across many runs.
    """
    template = _CACHED_TEMPLATE
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
