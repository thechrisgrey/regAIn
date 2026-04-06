"""Property test for table output completeness.

**Property 5: Table Output Completeness**
**Validates: Requirements 5.11, 5.12**

Verifies that for all DynamoDB tables created by the Data Stack, the
CloudFormation template exports both the table name and table ARN.
"""

from hypothesis import given, settings, strategies as st

from tests.unit.stacks.conftest import _synth_all_templates

EXPECTED_TABLE_COUNT = 9

_CACHED_TEMPLATE = _synth_all_templates()["RegainDataStack"]


def _get_dynamodb_table_names(template: dict) -> list[str]:
    """Extract logical IDs of all DynamoDB table resources."""
    return [
        logical_id
        for logical_id, resource in template.get("Resources", {}).items()
        if resource.get("Type") == "AWS::DynamoDB::Table"
    ]


def _get_outputs(template: dict) -> dict[str, dict]:
    """Extract all CloudFormation outputs from the template."""
    return template.get("Outputs", {})


@given(
    table_index=st.integers(min_value=0, max_value=EXPECTED_TABLE_COUNT - 1),
)
@settings(deadline=None)
def test_every_table_has_name_and_arn_outputs(table_index: int) -> None:
    """For all DynamoDB tables in the Data Stack, the template must export
    both the table name and the table ARN as CloudFormation outputs.

    The table_index parameter selects which table to verify on each iteration,
    ensuring every table is checked across many runs.
    """
    template = _CACHED_TEMPLATE
    table_logical_ids = _get_dynamodb_table_names(template)

    assert len(table_logical_ids) == EXPECTED_TABLE_COUNT, (
        f"Expected {EXPECTED_TABLE_COUNT} DynamoDB tables, found {len(table_logical_ids)}"
    )

    outputs = _get_outputs(template)
    export_names = {
        out.get("Export", {}).get("Name")
        for out in outputs.values()
        if "Export" in out
    }

    logical_id = table_logical_ids[table_index % len(table_logical_ids)]

    # Derive the domain table name from the logical ID by stripping the CDK hash suffix.
    # CDK logical IDs look like "RegainUserProfilesABC123" — the resource construct ID
    # is "Regain<TableName>", so we match against known table names.
    known_tables = ["UserProfiles", "Campaigns", "MissionHistory", "EvidenceVault", "MarketData", "VoiceSessions", "WebSocketConnections", "IdempotencyKeys", "ConversationThreads"]
    matched_table = None
    for name in known_tables:
        if logical_id.startswith(f"Regain{name}"):
            matched_table = name
            break

    assert matched_table is not None, (
        f"Could not match logical ID {logical_id} to a known table name"
    )

    expected_name_export = f"Regain{matched_table}Name"
    expected_arn_export = f"Regain{matched_table}Arn"

    assert expected_name_export in export_names, (
        f"Table {matched_table} (logical: {logical_id}) is missing "
        f"Name export '{expected_name_export}'. Found exports: {sorted(export_names)}"
    )

    assert expected_arn_export in export_names, (
        f"Table {matched_table} (logical: {logical_id}) is missing "
        f"ARN export '{expected_arn_export}'. Found exports: {sorted(export_names)}"
    )
