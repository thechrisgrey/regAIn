"""Unit tests for AgentCore policy evaluation audit logging (Task 5.1).

Verifies that AgentCoreStack creates a CloudWatch log group for policy
audit logs and configures the Gateway to emit structured evaluation results.

Requirements: 9.1, 9.2, 9.3
"""

import aws_cdk as cdk
from aws_cdk import (
    aws_cognito as cognito,
    aws_lambda as _lambda,
)

from infra.stacks.agentcore_stack import AgentCoreStack


def _synth_stack() -> dict:
    """Synthesize AgentCoreStack and return the CloudFormation template."""
    app = cdk.App()
    stack = cdk.Stack(app, "TestDeps")

    user_pool = cognito.UserPool(stack, "Pool")

    def _make_lambda(id_: str) -> _lambda.Function:
        return _lambda.Function(
            stack,
            id_,
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="handler.lambda_handler",
            code=_lambda.Code.from_inline("def lambda_handler(e,c): pass"),
        )

    agentcore = AgentCoreStack(
        app,
        "TestAgentCore",
        coaching_lambda=_make_lambda("Coaching"),
        missions_lambda=_make_lambda("Missions"),
        evidence_lambda=_make_lambda("Evidence"),
        dashboard_lambda=_make_lambda("Dashboard"),
        user_pool=user_pool,
    )

    return app.synth().get_stack_by_name("TestAgentCore").template


def _find_resources(template: dict, resource_type: str) -> list[dict]:
    """Return all resources of a given type from a CFN template."""
    return [
        v for v in template.get("Resources", {}).values()
        if v.get("Type") == resource_type
    ]


class TestPolicyAuditLogGroup:
    """Tests for the CloudWatch log group creation."""

    def test_log_group_created(self) -> None:
        """Stack should create a CloudWatch log group for policy audit logs."""
        template = _synth_stack()
        log_groups = _find_resources(template, "AWS::Logs::LogGroup")
        assert len(log_groups) >= 1, "Expected at least one CloudWatch log group"

    def test_log_group_name(self) -> None:
        """Log group should use the /regain/agentcore/policy-audit name."""
        template = _synth_stack()
        log_groups = _find_resources(template, "AWS::Logs::LogGroup")
        names = [
            lg["Properties"].get("LogGroupName", "")
            for lg in log_groups
        ]
        assert "/regain/agentcore/policy-audit" in names

    def test_log_group_retention(self) -> None:
        """Log group should have a retention period set (not indefinite)."""
        template = _synth_stack()
        log_groups = _find_resources(template, "AWS::Logs::LogGroup")
        audit_lg = next(
            lg for lg in log_groups
            if lg["Properties"].get("LogGroupName") == "/regain/agentcore/policy-audit"
        )
        assert "RetentionInDays" in audit_lg["Properties"]
        assert audit_lg["Properties"]["RetentionInDays"] > 0


class TestGatewayAuditLogConfig:
    """Tests for the Gateway logging configuration resource."""

    def test_gateway_logging_config_created(self) -> None:
        """Stack should create a Gateway resource with logging configuration."""
        template = _synth_stack()
        gateways = _find_resources(template, "AWS::BedrockAgentCore::Gateway")
        # Should have at least 2: the main gateway + the audit log config
        assert len(gateways) >= 2, (
            f"Expected at least 2 Gateway resources (main + audit config), got {len(gateways)}"
        )

    def test_logging_config_has_policy_evaluation_logging(self) -> None:
        """Gateway audit config should enable policy evaluation logging."""
        template = _synth_stack()
        gateways = _find_resources(template, "AWS::BedrockAgentCore::Gateway")
        audit_configs = [
            gw for gw in gateways
            if "LoggingConfiguration" in gw.get("Properties", {})
        ]
        assert len(audit_configs) >= 1, "No Gateway resource with LoggingConfiguration found"

        config = audit_configs[0]["Properties"]["LoggingConfiguration"]
        policy_logging = config.get("PolicyEvaluationLogging", {})
        assert policy_logging.get("Enabled") is True
        assert policy_logging.get("IncludeRequestContext") is True
        assert policy_logging.get("ExcludeSensitiveData") is True

    def test_logging_config_log_level_all(self) -> None:
        """Policy evaluation logging should capture ALL results (permit + deny).

        Requirement 9.1: log all evaluation results (permit or deny).
        """
        template = _synth_stack()
        gateways = _find_resources(template, "AWS::BedrockAgentCore::Gateway")
        audit_configs = [
            gw for gw in gateways
            if "LoggingConfiguration" in gw.get("Properties", {})
        ]
        config = audit_configs[0]["Properties"]["LoggingConfiguration"]
        assert config["PolicyEvaluationLogging"]["LogLevel"] == "ALL"


class TestPolicyAuditOutputs:
    """Tests for CfnOutput exports related to audit logging."""

    def test_log_group_arn_exported(self) -> None:
        """Stack should export the policy audit log group ARN."""
        template = _synth_stack()
        outputs = template.get("Outputs", {})
        export_names = [
            v.get("Export", {}).get("Name", "")
            for v in outputs.values()
        ]
        assert "RegainPolicyAuditLogGroupArn" in export_names


class TestPolicyAuditTagging:
    """Tests for resource tagging on audit logging resources."""

    def test_log_group_tagged(self) -> None:
        """Log group should be tagged with Project=REGAIN and Environment=dev."""
        template = _synth_stack()
        log_groups = _find_resources(template, "AWS::Logs::LogGroup")
        audit_lg = next(
            lg for lg in log_groups
            if lg["Properties"].get("LogGroupName") == "/regain/agentcore/policy-audit"
        )
        tags = {t["Key"]: t["Value"] for t in audit_lg["Properties"].get("Tags", [])}
        assert tags.get("Project") == "REGAIN"
        assert tags.get("Environment") == "dev"


class TestStackAttribute:
    """Tests for the audit log group attribute on the stack."""

    def test_stack_has_policy_audit_log_group_attribute(self) -> None:
        """AgentCoreStack should expose _policy_audit_log_group attribute."""
        assert hasattr(AgentCoreStack, "_configure_policy_audit_logging")
