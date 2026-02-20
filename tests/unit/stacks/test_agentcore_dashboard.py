"""Unit tests for CloudWatch dashboard creation (Task 7.2).

Verifies that AgentCoreStack creates the REGAIN-Coaching-Operations
dashboard with the correct 3-row widget layout matching the design spec.

Requirements: 11.1, 11.2, 11.3, 11.4
"""

import json
import pytest
import aws_cdk as cdk
from aws_cdk import aws_cognito as cognito, aws_lambda as _lambda

from infra.stacks.agentcore_stack import AgentCoreStack


def _get_template() -> dict:
    """Synthesize AgentCoreStack and return the CFN template dict."""
    app = cdk.App()

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

    AgentCoreStack(
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


def _get_dashboard_resource(template: dict) -> dict | None:
    """Extract the CloudWatch Dashboard resource from the template."""
    for _lid, resource in template.get("Resources", {}).items():
        if resource.get("Type") == "AWS::CloudWatch::Dashboard":
            return resource
    return None


def _resolve_cfn_join(value: object) -> str:
    """Resolve a CloudFormation Fn::Join intrinsic to a plain string.

    Handles the case where CDK token references (like log group names)
    produce Fn::Join structures in the synthesized template.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, dict) and "Fn::Join" in value:
        separator, parts = value["Fn::Join"]
        resolved = []
        for part in parts:
            if isinstance(part, str):
                resolved.append(part)
            else:
                # Unresolvable ref — use placeholder
                resolved.append("<REF>")
        return separator.join(resolved)
    return str(value)


def _get_dashboard_body(template: dict) -> dict:
    """Parse the DashboardBody JSON from the template."""
    resource = _get_dashboard_resource(template)
    assert resource is not None, "Dashboard resource not found"
    body_raw = resource["Properties"]["DashboardBody"]
    body_str = _resolve_cfn_join(body_raw)
    return json.loads(body_str)


class TestDashboardResource:
    """Tests for the dashboard CloudFormation resource."""

    def test_dashboard_resource_created(self) -> None:
        """Stack should create an AWS::CloudWatch::Dashboard resource."""
        template = _get_template()
        resource = _get_dashboard_resource(template)
        assert resource is not None

    def test_dashboard_name(self) -> None:
        """Dashboard should be named REGAIN-Coaching-Operations."""
        template = _get_template()
        resource = _get_dashboard_resource(template)
        assert resource is not None
        assert resource["Properties"]["DashboardName"] == "REGAIN-Coaching-Operations"


class TestDashboardTopRow:
    """Tests for top row widgets: session count, active users, error rate.

    Requirement 11.2: top row with session count time series, active users
    counter, and error rate gauge.
    """

    def test_session_count_widget(self) -> None:
        """Top row should include a session count time series widget."""
        body = _get_dashboard_body(_get_template())
        widgets = body["widgets"]
        session_widget = next(
            (w for w in widgets if w["properties"].get("title") == "Session Count"),
            None,
        )
        assert session_widget is not None
        assert session_widget["properties"]["view"] == "timeSeries"
        assert session_widget["y"] == 0  # Top row

    def test_active_users_widget(self) -> None:
        """Top row should include an active users counter widget."""
        body = _get_dashboard_body(_get_template())
        widgets = body["widgets"]
        users_widget = next(
            (w for w in widgets if w["properties"].get("title") == "Active Users"),
            None,
        )
        assert users_widget is not None
        assert users_widget["properties"]["view"] == "singleValue"
        assert users_widget["y"] == 0

    def test_error_rate_widget(self) -> None:
        """Top row should include an error rate gauge widget."""
        body = _get_dashboard_body(_get_template())
        widgets = body["widgets"]
        error_widget = next(
            (w for w in widgets if w["properties"].get("title") == "Error Rate"),
            None,
        )
        assert error_widget is not None
        assert error_widget["properties"]["view"] == "gauge"
        assert error_widget["y"] == 0


class TestDashboardMiddleRow:
    """Tests for middle row: tool invocation heatmap, policy denial log, token usage.

    Requirement 11.3: middle row with tool invocation heatmap, policy denial
    log table, and token usage stacked area chart.
    """

    def test_tool_invocation_widget(self) -> None:
        """Middle row should include a stacked tool invocation widget."""
        body = _get_dashboard_body(_get_template())
        widgets = body["widgets"]
        tool_widget = next(
            (w for w in widgets if w["properties"].get("title") == "Tool Invocations by Tool"),
            None,
        )
        assert tool_widget is not None
        assert tool_widget["properties"]["stacked"] is True
        assert tool_widget["y"] == 6  # Middle row

    def test_policy_denial_log_widget(self) -> None:
        """Middle row should include a policy denial log table widget."""
        body = _get_dashboard_body(_get_template())
        widgets = body["widgets"]
        denial_widget = next(
            (w for w in widgets if w["properties"].get("title") == "Policy Denials"),
            None,
        )
        assert denial_widget is not None
        assert denial_widget["type"] == "log"
        assert denial_widget["properties"]["view"] == "table"
        assert denial_widget["y"] == 6

    def test_token_usage_widget(self) -> None:
        """Middle row should include a stacked token usage area chart."""
        body = _get_dashboard_body(_get_template())
        widgets = body["widgets"]
        token_widget = next(
            (w for w in widgets if w["properties"].get("title") == "Token Usage"),
            None,
        )
        assert token_widget is not None
        assert token_widget["properties"]["stacked"] is True
        assert token_widget["y"] == 6


class TestDashboardBottomRow:
    """Tests for bottom row: latency percentiles, memory operations.

    Requirement 11.4: bottom row with latency percentile line charts and
    memory operation bar charts.
    """

    def test_latency_percentile_widget(self) -> None:
        """Bottom row should include latency percentile line charts."""
        body = _get_dashboard_body(_get_template())
        widgets = body["widgets"]
        latency_widget = next(
            (w for w in widgets if w["properties"].get("title") == "Tool Invocation Latency Percentiles"),
            None,
        )
        assert latency_widget is not None
        assert latency_widget["properties"]["view"] == "timeSeries"
        assert latency_widget["y"] == 12  # Bottom row
        # Verify p50, p95, p99 metrics present.
        metrics = latency_widget["properties"]["metrics"]
        stats = [m[-1]["stat"] for m in metrics if isinstance(m[-1], dict)]
        assert "p50" in stats
        assert "p95" in stats
        assert "p99" in stats

    def test_memory_ops_widget(self) -> None:
        """Bottom row should include a memory operations bar chart."""
        body = _get_dashboard_body(_get_template())
        widgets = body["widgets"]
        memory_widget = next(
            (w for w in widgets if w["properties"].get("title") == "Memory Operations"),
            None,
        )
        assert memory_widget is not None
        assert memory_widget["properties"]["view"] == "bar"
        assert memory_widget["y"] == 12


class TestDashboardWidgetCount:
    """Tests for overall dashboard structure."""

    def test_total_widget_count(self) -> None:
        """Dashboard should contain exactly 8 widgets across 3 rows."""
        body = _get_dashboard_body(_get_template())
        assert len(body["widgets"]) == 8

    def test_three_row_layout(self) -> None:
        """Widgets should span exactly 3 rows (y=0, y=6, y=12)."""
        body = _get_dashboard_body(_get_template())
        y_values = {w["y"] for w in body["widgets"]}
        assert y_values == {0, 6, 12}

    def test_uses_regain_namespace(self) -> None:
        """Metric widgets should reference the REGAIN/Coaching namespace."""
        body = _get_dashboard_body(_get_template())
        metric_widgets = [w for w in body["widgets"] if w["type"] == "metric"]
        for widget in metric_widgets:
            metrics = widget["properties"]["metrics"]
            # At least one metric in each widget should use our namespace
            # (math expressions don't have a namespace entry).
            namespaces = [m[0] for m in metrics if isinstance(m[0], str) and "/" in m[0]]
            if namespaces:
                assert all(ns == "REGAIN/Coaching" for ns in namespaces)
