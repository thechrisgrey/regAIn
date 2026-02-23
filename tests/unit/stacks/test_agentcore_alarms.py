"""Unit tests for SNS topic and CloudWatch alarms (Task 7.3).

Verifies that AgentCoreStack creates the RegainCoachingAlerts SNS topic
and 3 CloudWatch alarms with correct thresholds and actions.

Requirements: 12.1, 12.2, 12.3
"""

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
    for name in ("coaching", "missions", "evidence", "dashboard", "market_intel", "profile"):
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
        profile_lambda=lambdas["profile"],
        user_pool=user_pool,
    )

    return app.synth().get_stack_by_name("TestAgentCoreStack").template


def _find_resources_by_type(template: dict, resource_type: str) -> list[dict]:
    """Return all resources of a given CloudFormation type."""
    return [
        res
        for res in template.get("Resources", {}).values()
        if res.get("Type") == resource_type
    ]


def _find_alarms(template: dict) -> list[dict]:
    """Return all CloudWatch Alarm resources."""
    return _find_resources_by_type(template, "AWS::CloudWatch::Alarm")


def _find_alarm_by_name(template: dict, alarm_name: str) -> dict | None:
    """Find a CloudWatch Alarm by its AlarmName property."""
    for res in template.get("Resources", {}).values():
        if res.get("Type") != "AWS::CloudWatch::Alarm":
            continue
        if res.get("Properties", {}).get("AlarmName") == alarm_name:
            return res
    return None


def _find_sns_topics(template: dict) -> list[dict]:
    """Return all SNS Topic resources."""
    return _find_resources_by_type(template, "AWS::SNS::Topic")


class TestSnsTopicCreation:
    """Tests for the RegainCoachingAlerts SNS topic."""

    def test_sns_topic_created(self) -> None:
        """Stack should create an SNS topic."""
        template = _get_template()
        topics = _find_sns_topics(template)
        assert len(topics) >= 1

    def test_sns_topic_name(self) -> None:
        """SNS topic should be named RegainCoachingAlerts."""
        template = _get_template()
        topics = _find_sns_topics(template)
        names = [t["Properties"].get("TopicName") for t in topics]
        assert "RegainCoachingAlerts" in names

    def test_sns_topic_arn_exported(self) -> None:
        """Stack should export the SNS topic ARN via CfnOutput."""
        template = _get_template()
        outputs = template.get("Outputs", {})
        export_names = [
            v.get("Export", {}).get("Name")
            for v in outputs.values()
        ]
        assert "RegainAlertSnsTopicArn" in export_names


class TestAlarmCount:
    """Tests for the overall alarm configuration."""

    def test_three_alarms_created(self) -> None:
        """Stack should create exactly 3 CloudWatch alarms."""
        template = _get_template()
        alarms = _find_alarms(template)
        assert len(alarms) == 3


class TestErrorRateAlarm:
    """Tests for the high error rate alarm (Requirement 12.1)."""

    def test_error_rate_alarm_exists(self) -> None:
        """Error rate alarm should exist."""
        template = _get_template()
        alarm = _find_alarm_by_name(template, "Regain-HighErrorRate")
        assert alarm is not None

    def test_error_rate_threshold(self) -> None:
        """Error rate alarm threshold should be 0.1 (10%)."""
        template = _get_template()
        alarm = _find_alarm_by_name(template, "Regain-HighErrorRate")
        assert alarm is not None
        assert alarm["Properties"]["Threshold"] == 0.1

    def test_error_rate_period(self) -> None:
        """Error rate alarm should evaluate over 5-minute periods."""
        template = _get_template()
        alarm = _find_alarm_by_name(template, "Regain-HighErrorRate")
        assert alarm is not None
        # Math expression alarms use Metrics array with Period on each metric
        metrics = alarm["Properties"].get("Metrics", [])
        periods = [m.get("MetricStat", {}).get("Period") for m in metrics if "MetricStat" in m]
        assert all(p == 300 for p in periods)

    def test_error_rate_uses_math_expression(self) -> None:
        """Error rate alarm should use a math expression for errors/total."""
        template = _get_template()
        alarm = _find_alarm_by_name(template, "Regain-HighErrorRate")
        assert alarm is not None
        metrics = alarm["Properties"].get("Metrics", [])
        expressions = [m for m in metrics if "Expression" in m]
        assert len(expressions) >= 1

    def test_error_rate_alarm_action_is_sns(self) -> None:
        """Error rate alarm should notify the SNS topic."""
        template = _get_template()
        alarm = _find_alarm_by_name(template, "Regain-HighErrorRate")
        assert alarm is not None
        actions = alarm["Properties"].get("AlarmActions", [])
        assert len(actions) >= 1


class TestLatencyAlarm:
    """Tests for the high latency alarm (Requirement 12.2)."""

    def test_latency_alarm_exists(self) -> None:
        """Latency alarm should exist."""
        template = _get_template()
        alarm = _find_alarm_by_name(template, "Regain-HighLatency")
        assert alarm is not None

    def test_latency_threshold(self) -> None:
        """Latency alarm threshold should be 5000 ms (5 seconds)."""
        template = _get_template()
        alarm = _find_alarm_by_name(template, "Regain-HighLatency")
        assert alarm is not None
        assert alarm["Properties"]["Threshold"] == 5000

    def test_latency_uses_p95(self) -> None:
        """Latency alarm should use p95 statistic."""
        template = _get_template()
        alarm = _find_alarm_by_name(template, "Regain-HighLatency")
        assert alarm is not None
        # L2 alarm with extended statistic
        props = alarm["Properties"]
        stat = props.get("ExtendedStatistic") or props.get("Statistic")
        assert stat is not None
        assert "p95" in str(stat).lower()

    def test_latency_metric_namespace(self) -> None:
        """Latency alarm should use the REGAIN/Coaching namespace."""
        template = _get_template()
        alarm = _find_alarm_by_name(template, "Regain-HighLatency")
        assert alarm is not None
        assert alarm["Properties"]["Namespace"] == "REGAIN/Coaching"

    def test_latency_metric_name(self) -> None:
        """Latency alarm should monitor ToolInvocationLatency."""
        template = _get_template()
        alarm = _find_alarm_by_name(template, "Regain-HighLatency")
        assert alarm is not None
        assert alarm["Properties"]["MetricName"] == "ToolInvocationLatency"

    def test_latency_alarm_action_is_sns(self) -> None:
        """Latency alarm should notify the SNS topic."""
        template = _get_template()
        alarm = _find_alarm_by_name(template, "Regain-HighLatency")
        assert alarm is not None
        actions = alarm["Properties"].get("AlarmActions", [])
        assert len(actions) >= 1


class TestPolicyDenialAlarm:
    """Tests for the policy denial spike alarm (Requirement 12.3)."""

    def test_denial_alarm_exists(self) -> None:
        """Policy denial alarm should exist."""
        template = _get_template()
        alarm = _find_alarm_by_name(template, "Regain-PolicyDenialSpike")
        assert alarm is not None

    def test_denial_threshold(self) -> None:
        """Policy denial alarm threshold should be 20."""
        template = _get_template()
        alarm = _find_alarm_by_name(template, "Regain-PolicyDenialSpike")
        assert alarm is not None
        assert alarm["Properties"]["Threshold"] == 20

    def test_denial_period(self) -> None:
        """Policy denial alarm should evaluate over 1-minute periods."""
        template = _get_template()
        alarm = _find_alarm_by_name(template, "Regain-PolicyDenialSpike")
        assert alarm is not None
        assert alarm["Properties"]["Period"] == 60

    def test_denial_uses_sum_statistic(self) -> None:
        """Policy denial alarm should use Sum statistic."""
        template = _get_template()
        alarm = _find_alarm_by_name(template, "Regain-PolicyDenialSpike")
        assert alarm is not None
        assert alarm["Properties"]["Statistic"] == "Sum"

    def test_denial_metric_namespace(self) -> None:
        """Policy denial alarm should use the REGAIN/Coaching namespace."""
        template = _get_template()
        alarm = _find_alarm_by_name(template, "Regain-PolicyDenialSpike")
        assert alarm is not None
        assert alarm["Properties"]["Namespace"] == "REGAIN/Coaching"

    def test_denial_metric_name(self) -> None:
        """Policy denial alarm should monitor PolicyDenialCount."""
        template = _get_template()
        alarm = _find_alarm_by_name(template, "Regain-PolicyDenialSpike")
        assert alarm is not None
        assert alarm["Properties"]["MetricName"] == "PolicyDenialCount"

    def test_denial_alarm_action_is_sns(self) -> None:
        """Policy denial alarm should notify the SNS topic."""
        template = _get_template()
        alarm = _find_alarm_by_name(template, "Regain-PolicyDenialSpike")
        assert alarm is not None
        actions = alarm["Properties"].get("AlarmActions", [])
        assert len(actions) >= 1
