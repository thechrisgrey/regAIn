"""Property test for least-privilege IAM permissions.

**Property 9: Least-Privilege IAM Permissions**
**Validates: Requirements 6.11**

Verifies that each Lambda function's IAM role only grants permissions to
the specific DynamoDB tables it needs to access, not all tables.
"""

import aws_cdk as cdk
from hypothesis import given, settings, strategies as st

from infra.stacks.auth_stack import AuthStack
from infra.stacks.data_stack import DataStack
from infra.stacks.api_stack import ApiStack


# Expected Lambda count in the API stack.
EXPECTED_LAMBDA_COUNT = 7

# Map each Lambda logical-name fragment to the tables it MAY access.
# Derived from ApiStack._grant_permissions.
ALLOWED_TABLES: dict[str, set[str]] = {
    "Onboarding": {"UserProfiles", "Campaigns", "MissionHistory", "EvidenceVault", "MarketData"},
    "Missions": {"MissionHistory", "EvidenceVault", "Campaigns", "UserProfiles", "MarketData"},
    "Evidence": {"EvidenceVault"},
    "Coaching": {"UserProfiles"},
    "Dashboard": {"Campaigns", "MissionHistory", "EvidenceVault"},
    "Profile": {"UserProfiles", "Campaigns", "MissionHistory", "EvidenceVault", "VoiceSessions"},
    "Onet": set(),
}

ALL_TABLE_NAMES = {"UserProfiles", "Campaigns", "MissionHistory", "EvidenceVault", "MarketData", "VoiceSessions", "WebSocketConnections"}


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
    """Extract all AWS::Lambda::Function resources."""
    return [
        (lid, res)
        for lid, res in template.get("Resources", {}).items()
        if res.get("Type") == "AWS::Lambda::Function"
    ]


def _identify_lambda_name(logical_id: str) -> str | None:
    """Map a CloudFormation logical ID back to a known Lambda name fragment."""
    for name in ALLOWED_TABLES:
        if name.lower() in logical_id.lower():
            return name
    return None


def _get_iam_policies_for_role(
    template: dict, role_logical_id: str
) -> list[dict]:
    """Return all IAM policy documents attached to a role."""
    policies: list[dict] = []

    # Inline policies on the role itself
    role_res = template.get("Resources", {}).get(role_logical_id, {})
    for inline in role_res.get("Properties", {}).get("Policies", []):
        policies.append(inline.get("PolicyDocument", {}))

    # AWS::IAM::Policy resources that reference this role
    for lid, res in template.get("Resources", {}).items():
        if res.get("Type") != "AWS::IAM::Policy":
            continue
        props = res.get("Properties", {})
        roles = props.get("Roles", [])
        for role_ref in roles:
            ref_val = role_ref.get("Ref", "") if isinstance(role_ref, dict) else ""
            if ref_val == role_logical_id:
                policies.append(props.get("PolicyDocument", {}))
    return policies


def _resolve_resource_to_table(resource: object, template: dict) -> str | None:
    """Resolve a resource ARN reference to a known table name."""
    if isinstance(resource, str):
        for table_name in ALL_TABLE_NAMES:
            if table_name.lower() in resource.lower():
                return table_name
        return None

    if isinstance(resource, dict):
        import_val = resource.get("Fn::ImportValue")
        if import_val and isinstance(import_val, str):
            for table_name in ALL_TABLE_NAMES:
                if table_name in import_val:
                    return table_name

        get_att = resource.get("Fn::GetAtt")
        if get_att and isinstance(get_att, list):
            logical_id = get_att[0]
            for table_name in ALL_TABLE_NAMES:
                if table_name.lower() in logical_id.lower():
                    return table_name

        ref = resource.get("Ref")
        if ref and isinstance(ref, str):
            for table_name in ALL_TABLE_NAMES:
                if table_name.lower() in ref.lower():
                    return table_name

        join_val = resource.get("Fn::Join")
        if join_val and isinstance(join_val, list) and len(join_val) == 2:
            parts = join_val[1]
            for part in parts:
                resolved = _resolve_resource_to_table(part, template)
                if resolved:
                    return resolved

    return None


def _get_tables_accessed_by_lambda(
    template: dict, lambda_logical_id: str
) -> set[str]:
    """Determine which DynamoDB tables a Lambda function can access via its IAM role."""
    lambda_res = template["Resources"][lambda_logical_id]
    role_ref = lambda_res.get("Properties", {}).get("Role", {})

    role_logical_id = None
    if isinstance(role_ref, dict):
        get_att = role_ref.get("Fn::GetAtt")
        if get_att and isinstance(get_att, list):
            role_logical_id = get_att[0]
        ref = role_ref.get("Ref")
        if ref:
            role_logical_id = ref

    if not role_logical_id:
        return set()

    policies = _get_iam_policies_for_role(template, role_logical_id)

    accessed_tables: set[str] = set()
    for policy_doc in policies:
        for statement in policy_doc.get("Statement", []):
            actions = statement.get("Action", [])
            if isinstance(actions, str):
                actions = [actions]
            if not any("dynamodb" in a.lower() for a in actions):
                continue
            resources = statement.get("Resource", [])
            if not isinstance(resources, list):
                resources = [resources]
            for res in resources:
                table_name = _resolve_resource_to_table(res, template)
                if table_name:
                    accessed_tables.add(table_name)
    return accessed_tables


@given(
    lambda_index=st.integers(min_value=0, max_value=EXPECTED_LAMBDA_COUNT - 1),
)
@settings(max_examples=100, deadline=None)
def test_lambda_has_least_privilege_table_access(lambda_index: int) -> None:
    """For all Lambda functions, each function's IAM role should only grant
    permissions to the specific DynamoDB tables it needs, not all tables.

    **Validates: Requirements 6.11**
    """
    template = _synth_api_template()
    lambdas = _get_lambda_functions(template)

    assert len(lambdas) == EXPECTED_LAMBDA_COUNT, (
        f"Expected {EXPECTED_LAMBDA_COUNT} Lambda functions, found {len(lambdas)}"
    )

    logical_id, _ = lambdas[lambda_index % len(lambdas)]
    lambda_name = _identify_lambda_name(logical_id)
    assert lambda_name is not None, (
        f"Could not identify Lambda name from logical ID: {logical_id}"
    )

    accessed_tables = _get_tables_accessed_by_lambda(template, logical_id)
    allowed = ALLOWED_TABLES[lambda_name]
    forbidden = ALL_TABLE_NAMES - allowed

    # The Lambda must NOT have access to tables outside its allowed set
    unauthorized = accessed_tables & forbidden
    assert not unauthorized, (
        f"Lambda {lambda_name} ({logical_id}) has access to tables it should "
        f"not: {unauthorized}. Allowed: {allowed}, Found: {accessed_tables}"
    )

    # The Lambda MUST have access to at least one of its allowed tables
    # (skip for Lambdas that need no DynamoDB access, e.g. Onet)
    if allowed:
        assert accessed_tables, (
            f"Lambda {lambda_name} ({logical_id}) has no DynamoDB table access at all. "
            f"Expected access to: {allowed}"
        )
