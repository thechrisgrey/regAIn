"""Shared Lambda monitoring utilities for REGAIN CDK stacks."""
import aws_cdk as cdk
from aws_cdk import (
    aws_cloudwatch as cloudwatch,
    aws_cloudwatch_actions as cw_actions,
    aws_lambda as _lambda,
    aws_sns as sns,
)
from constructs import Construct


def add_lambda_alarms(
    scope: Construct,
    function: _lambda.Function,
    alert_topic: sns.ITopic,
    name: str,
    timeout_seconds: int = 30,
    prefix: str = "",
) -> None:
    """Add standard CloudWatch alarms to a Lambda function.

    Creates 3 alarms:
    1. Error count > 0 over 5 minutes
    2. p95 duration > 80% of timeout over 5 minutes
    3. Throttle count > 0 over 5 minutes

    Args:
        scope: CDK construct scope.
        function: Lambda function to monitor.
        alert_topic: SNS topic for alarm notifications.
        name: Plain string name for construct IDs (e.g. "Onboarding").
        timeout_seconds: Function timeout for duration threshold calculation.
        prefix: Optional prefix for alarm names to avoid cross-stack conflicts.
    """
    alarm_prefix = f"Regain-{prefix}{name}" if prefix else f"Regain-{name}"
    sns_action = cw_actions.SnsAction(alert_topic)

    # Alarm 1: Error count > 0 over 5 min
    error_alarm = function.metric_errors(period=cdk.Duration.minutes(5)).create_alarm(
        scope,
        f"{name}ErrorAlarm",
        alarm_name=f"{alarm_prefix}-Errors",
        alarm_description=f"{alarm_prefix} Lambda error count > 0 over 5 minutes",
        threshold=0,
        evaluation_periods=1,
        comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
        treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
    )
    error_alarm.add_alarm_action(sns_action)

    # Alarm 2: p95 duration > 80% of timeout
    duration_threshold = timeout_seconds * 1000 * 0.8  # ms
    duration_alarm = function.metric_duration(
        statistic="p95",
        period=cdk.Duration.minutes(5),
    ).create_alarm(
        scope,
        f"{name}DurationAlarm",
        alarm_name=f"{alarm_prefix}-HighDuration",
        alarm_description=f"{alarm_prefix} p95 duration > 80% of {timeout_seconds}s timeout",
        threshold=duration_threshold,
        evaluation_periods=1,
        comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
        treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
    )
    duration_alarm.add_alarm_action(sns_action)

    # Alarm 3: Throttles > 0
    throttle_alarm = function.metric_throttles(
        period=cdk.Duration.minutes(5),
    ).create_alarm(
        scope,
        f"{name}ThrottleAlarm",
        alarm_name=f"{alarm_prefix}-Throttles",
        alarm_description=f"{alarm_prefix} Lambda throttled in last 5 minutes",
        threshold=0,
        evaluation_periods=1,
        comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
        treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
    )
    throttle_alarm.add_alarm_action(sns_action)
