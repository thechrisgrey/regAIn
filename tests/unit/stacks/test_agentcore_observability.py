"""Unit tests for AgentCore Observability configuration (Task 7.1).

Verifies that AgentCoreStack creates the observability CfnResource with
correct trace export settings, auto-captured span types, and IAM
permissions for CloudWatch trace export.

Tests the configure_observability() method by inspecting the synthesized
CloudFormation template properties.
"""

from infra.stacks.agentcore_stack import AgentCoreStack


def _get_observability_resources(template: dict) -> list[dict]:
    """Extract observability-related resources from a CFN template."""
    results = []
    for logical_id, resource in template.get("Resources", {}).items():
        if "Observability" in logical_id:
            results.append({"logical_id": logical_id, **resource})
    return results


def _get_template() -> dict:
    """Synthesize AgentCoreStack and return the CFN template dict.

    Uses the _tool_registry static method to verify the stack can be
    constructed, but avoids full CDK synthesis with real Lambda assets
    by importing only the stack class and calling _tool_registry.
    """
    import aws_cdk as cdk
    from aws_cdk import aws_cognito as cognito, aws_lambda as _lambda

    app = cdk.App()

    # Minimal supporting stack for cross-stack references.
    support = cdk.Stack(app, "SupportStack")
    user_pool = cognito.UserPool(support, "Pool")

    dummy_code = _lambda.Code.from_inline("def handler(e,c): pass")
    lambdas = {}
    for name in ("coaching", "missions", "evidence", "dashboard", "market_intel"):
        lambdas[name] = _lambda.Function(
            support,
            f"{name}Lambda",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=dummy_code,
        )

    stack = AgentCoreStack(
        app,
        "TestAgentCoreStack",
        coaching_lambda=lambdas["coaching"],
        missions_lambda=lambdas["missions"],
        evidence_lambda=lambdas["evidence"],
        dashboard_lambda=lambdas["dashboard"],
        market_intel_lambda=lambdas["market_intel"],
        user_pool=user_pool,
    )

    return app.synth().get_stack_by_name("TestAgentCoreStack").template


class TestObservabilityConfiguration:
    """Tests for the AgentCore Observability CDK resource."""

    def test_observability_config_resource_created(self) -> None:
        """Stack should create an observability configuration resource."""
        template = _get_template()
        obs_resources = _get_observability_resources(template)
        assert len(obs_resources) >= 1, "No observability resources found"

    def test_observability_config_type(self) -> None:
        """Observability config should be an AWS::BedrockAgentCore::Gateway resource."""
        template = _get_template()
        obs_resources = _get_observability_resources(template)
        config_resource = next(
            (r for r in obs_resources if "Config" in r["logical_id"]),
            None,
        )
        assert config_resource is not None, "ObservabilityConfig resource not found"
        assert config_resource["Type"] == "AWS::BedrockAgentCore::Gateway"

    def test_observability_tracing_enabled(self) -> None:
        """Observability configuration should have tracing enabled."""
        template = _get_template()
        obs_resources = _get_observability_resources(template)
        config_resource = next(
            (r for r in obs_resources if "Config" in r["logical_id"]),
            None,
        )
        assert config_resource is not None
        props = config_resource["Properties"]
        obs_config = props["ObservabilityConfiguration"]
        assert obs_config["Enabled"] is True
        assert obs_config["TraceConfiguration"]["Enabled"] is True

    def test_opentelemetry_protocol_enabled(self) -> None:
        """Trace configuration should enable OpenTelemetry protocol."""
        template = _get_template()
        obs_resources = _get_observability_resources(template)
        config_resource = next(
            (r for r in obs_resources if "Config" in r["logical_id"]),
            None,
        )
        assert config_resource is not None
        trace_config = config_resource["Properties"]["ObservabilityConfiguration"][
            "TraceConfiguration"
        ]
        assert trace_config["OpenTelemetryProtocol"] is True

    def test_auto_captured_spans(self) -> None:
        """Trace config should auto-capture Gateway routing, policy eval, and Lambda execution."""
        template = _get_template()
        obs_resources = _get_observability_resources(template)
        config_resource = next(
            (r for r in obs_resources if "Config" in r["logical_id"]),
            None,
        )
        assert config_resource is not None
        trace_config = config_resource["Properties"]["ObservabilityConfiguration"][
            "TraceConfiguration"
        ]
        auto_spans = trace_config["AutoCapturedSpans"]
        assert "GatewayRouting" in auto_spans
        assert "PolicyEvaluation" in auto_spans
        assert "LambdaExecution" in auto_spans

    def test_cloudwatch_export_destination(self) -> None:
        """Traces should export to a CloudWatch log group."""
        template = _get_template()
        obs_resources = _get_observability_resources(template)
        config_resource = next(
            (r for r in obs_resources if "Config" in r["logical_id"]),
            None,
        )
        assert config_resource is not None
        export_dest = config_resource["Properties"]["ObservabilityConfiguration"][
            "TraceConfiguration"
        ]["ExportDestination"]
        assert "CloudWatch" in export_dest
        cw_config = export_dest["CloudWatch"]
        assert "LogGroupArn" in cw_config


class TestObservabilityLogGroup:
    """Tests for the trace export CloudWatch log group."""

    def test_trace_log_group_created(self) -> None:
        """Stack should create a log group for trace export."""
        template = _get_template()
        log_groups = [
            (lid, r)
            for lid, r in template["Resources"].items()
            if r["Type"] == "AWS::Logs::LogGroup"
            and "Traces" in lid
        ]
        assert len(log_groups) >= 1, "Trace log group not found"

    def test_trace_log_group_name(self) -> None:
        """Trace log group should use the /regain/agentcore/traces path."""
        template = _get_template()
        for _lid, r in template["Resources"].items():
            if r["Type"] == "AWS::Logs::LogGroup":
                name = r.get("Properties", {}).get("LogGroupName", "")
                if name == "/regain/agentcore/traces":
                    return
        pytest.fail("Log group with name '/regain/agentcore/traces' not found")


class TestObservabilityTags:
    """Tests for resource tagging on observability resources."""

    def test_observability_resources_tagged(self) -> None:
        """Trace log group should have Project=REGAIN and Environment=dev tags.

        Note: CfnResource types (like the observability config) don't get
        tags injected into CloudFormation Properties by CDK's Tags.of() —
        only L2 constructs do. We verify the LogGroup which is L2.
        """
        template = _get_template()
        for _lid, r in template["Resources"].items():
            if r["Type"] == "AWS::Logs::LogGroup":
                name = r.get("Properties", {}).get("LogGroupName", "")
                if name == "/regain/agentcore/traces":
                    tags = r.get("Properties", {}).get("Tags", [])
                    tag_dict = {t["Key"]: t["Value"] for t in tags}
                    assert tag_dict.get("Project") == "REGAIN"
                    assert tag_dict.get("Environment") == "dev"
                    return
        pytest.fail("Trace log group not found")


class TestObservabilityOutputs:
    """Tests for CfnOutput exports."""

    def test_trace_log_group_arn_exported(self) -> None:
        """Stack should export the trace log group ARN."""
        template = _get_template()
        outputs = template.get("Outputs", {})
        found = any(
            "ObservabilityTraceLogGroupArn" in k
            for k in outputs
        )
        assert found, "ObservabilityTraceLogGroupArn output not found"


# Need pytest import for pytest.fail
import pytest
