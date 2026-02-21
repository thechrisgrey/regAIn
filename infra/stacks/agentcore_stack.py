"""REGAIN AgentCore Stack — Gateway, Observability, and Alerting.

Provisions AgentCore platform services that wrap existing Lambda-backed tools
with centralized auth and distributed tracing.
Gateway wraps existing functions — it does not replace them.

Requirements: 1.1, 1.2, 1.4, 1.5, 9.1, 9.2, 9.3, 14.1, 14.2, 14.3, 14.4

Cedar policies are managed via the AgentCore Policy Engine API (SDK/CLI),
not CloudFormation, since AWS::BedrockAgentCore::GatewayPolicy is not a
supported resource type.
"""

import json

import aws_cdk as cdk
from aws_cdk import (
    aws_cloudwatch as cloudwatch,
    aws_cloudwatch_actions as cw_actions,
    aws_cognito as cognito,
    aws_iam as iam,
    aws_lambda as _lambda,
    aws_logs as logs,
    aws_s3 as s3,
    aws_sns as sns,
)
from constructs import Construct
from typing import Any


class AgentCoreStack(cdk.Stack):
    """AgentCore platform services: Gateway, Observability, Alerting."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        coaching_lambda: _lambda.Function,
        missions_lambda: _lambda.Function,
        evidence_lambda: _lambda.Function,
        dashboard_lambda: _lambda.Function,
        market_intel_lambda: _lambda.Function | None = None,
        user_pool: cognito.UserPool,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self._lambda_targets = {
            "coaching": coaching_lambda,
            "missions": missions_lambda,
            "evidence": evidence_lambda,
            "dashboard": dashboard_lambda,
        }
        if market_intel_lambda:
            self._lambda_targets["market_intel"] = market_intel_lambda

        self._user_pool = user_pool

        # IAM roles must exist before Gateway (RoleArn is required).
        self._gateway_lambda_role = self._create_gateway_lambda_role()
        self._agent_gateway_role = self._create_agent_gateway_role()

        self.gateway = self._create_gateway()
        self._gateway_targets = self._register_tool_schemas()

        # Observability & alerting (CloudWatch-only, no Gateway config resources).
        self._policy_audit_log_group = self._create_audit_log_group()
        self._trace_log_group = self._create_trace_log_group()
        self.create_alarms()

        self._code_interpreter_bucket = self._create_code_interpreter_bucket()
        self._create_outputs()

    # -- Gateway ---------------------------------------------------------------

    def _create_gateway(self) -> cdk.CfnResource:
        """Create AgentCore Gateway with Cognito JWT authorization."""
        user_pool_client_id = cdk.Fn.import_value("RegainUserPoolClientId")
        discovery_url = (
            f"https://cognito-idp.{self.region}.amazonaws.com/"
            f"{self._user_pool.user_pool_id}/.well-known/openid-configuration"
        )

        return cdk.CfnResource(
            self,
            "RegainCoachingGateway",
            type="AWS::BedrockAgentCore::Gateway",
            properties={
                "Name": "regain-coaching-gateway",
                "Description": "REGAIN Coaching Agent tool gateway with MCP access",
                "AuthorizerType": "CUSTOM_JWT",
                "AuthorizerConfiguration": {
                    "CustomJWTAuthorizer": {
                        "DiscoveryUrl": discovery_url,
                        "AllowedAudience": [user_pool_client_id],
                        "AllowedClients": [user_pool_client_id],
                    },
                },
                "ProtocolType": "MCP",
                "RoleArn": self._gateway_lambda_role.role_arn,
            },
        )

    # -- IAM Roles -------------------------------------------------------------

    def _create_gateway_lambda_role(self) -> iam.Role:
        """Create IAM role for Gateway to invoke Lambda tool targets."""
        role = iam.Role(
            self,
            "RegainGatewayLambdaRole",
            role_name="RegainGatewayLambdaInvocationRole",
            assumed_by=iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
            description="Allows AgentCore Gateway to invoke REGAIN Lambda tool targets",
        )

        lambda_arns = [fn.function_arn for fn in self._lambda_targets.values()]
        role.add_to_policy(
            iam.PolicyStatement(
                actions=["lambda:InvokeFunction"],
                resources=lambda_arns,
            )
        )

        return role

    def _create_agent_gateway_role(self) -> iam.Role:
        """Create IAM role for the Coaching Agent to access Gateway."""
        role = iam.Role(
            self,
            "RegainAgentGatewayRole",
            role_name="RegainAgentGatewayAccessRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="Allows Coaching Agent Lambda to access AgentCore Gateway",
        )

        role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock:InvokeAgent",
                    "bedrock:InvokeAgentCore",
                ],
                resources=[
                    f"arn:aws:bedrock:{self.region}:{self.account}:gateway/*",
                ],
            )
        )

        return role

    # -- Observability (CloudWatch log groups) ---------------------------------

    def _create_audit_log_group(self) -> logs.LogGroup:
        """Create CloudWatch log group for policy evaluation audit logs."""
        log_group = logs.LogGroup(
            self,
            "RegainPolicyAuditLogs",
            log_group_name="/regain/agentcore/policy-audit",
            retention=logs.RetentionDays.THREE_MONTHS,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )
        log_group.grant_write(iam.ServicePrincipal("bedrock.amazonaws.com"))
        return log_group

    def _create_trace_log_group(self) -> logs.LogGroup:
        """Create CloudWatch log group for OpenTelemetry trace export."""
        log_group = logs.LogGroup(
            self,
            "RegainObservabilityTraces",
            log_group_name="/regain/agentcore/traces",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )
        log_group.grant_write(iam.ServicePrincipal("bedrock.amazonaws.com"))
        return log_group

    # -- Tool registration -----------------------------------------------------

    @staticmethod
    def _tool_registry() -> list[dict[str, Any]]:
        """Return all MCP tool schemas with their Lambda target keys.

        Each entry mirrors the schema in backend/agents/coaching/tool_schemas.py.
        SchemaDefinition uses PascalCase per CloudFormation spec.
        """
        user_id_prop: dict[str, Any] = {
            "Type": "string",
            "Description": "Authenticated user ID from Cognito JWT claims.",
        }

        return [
            {
                "name": "regain_read_user_profile",
                "description": "Read a user's complete profile including persona, target role, skills, and onboarding status.",
                "lambda_target": "coaching",
                "input_schema": {
                    "Type": "object",
                    "Properties": {"userId": user_id_prop},
                    "Required": ["userId"],
                },
                "output_schema": {
                    "Type": "object",
                    "Properties": {
                        "userId": {"Type": "string"},
                        "name": {"Type": "string"},
                        "email": {"Type": "string"},
                        "persona": {"Type": "string"},
                        "target_role": {"Type": "string"},
                        "skills": {"Type": "array", "Items": {"Type": "string"}},
                        "onboarding_completed": {"Type": "boolean"},
                        "created_at": {"Type": "string"},
                    },
                },
            },
            {
                "name": "regain_update_user_profile",
                "description": "Update fields on a user's profile. Pass only the fields that need to change.",
                "lambda_target": "coaching",
                "input_schema": {
                    "Type": "object",
                    "Properties": {
                        "userId": user_id_prop,
                        "updates": {"Type": "object", "Description": "Field-value pairs to update."},
                    },
                    "Required": ["userId", "updates"],
                },
                "output_schema": {"Type": "object"},
            },
            {
                "name": "regain_get_campaign_status",
                "description": "Get the active campaign for a user including phase, target role, and skills focus.",
                "lambda_target": "coaching",
                "input_schema": {
                    "Type": "object",
                    "Properties": {"userId": user_id_prop},
                    "Required": ["userId"],
                },
                "output_schema": {
                    "Type": "object",
                    "Properties": {
                        "userId": {"Type": "string"},
                        "campaignId": {"Type": "string"},
                        "title": {"Type": "string"},
                        "phase": {"Type": "string"},
                        "status": {"Type": "string"},
                        "startDate": {"Type": "string"},
                        "targetRole": {"Type": "string"},
                        "skillsFocus": {"Type": "array", "Items": {"Type": "string"}},
                    },
                },
            },
            {
                "name": "regain_create_campaign",
                "description": "Create a new reskilling campaign starting in the foundation phase.",
                "lambda_target": "coaching",
                "input_schema": {
                    "Type": "object",
                    "Properties": {
                        "userId": user_id_prop,
                        "title": {"Type": "string"},
                        "targetRole": {"Type": "string"},
                        "skillsFocus": {"Type": "array", "Items": {"Type": "string"}},
                    },
                    "Required": ["userId", "title", "targetRole", "skillsFocus"],
                },
                "output_schema": {
                    "Type": "object",
                    "Properties": {
                        "userId": {"Type": "string"},
                        "campaignId": {"Type": "string"},
                        "title": {"Type": "string"},
                        "phase": {"Type": "string"},
                        "status": {"Type": "string"},
                    },
                },
            },
            {
                "name": "regain_get_current_mission",
                "description": "Get the current pending or in-progress mission for a user.",
                "lambda_target": "missions",
                "input_schema": {
                    "Type": "object",
                    "Properties": {"userId": user_id_prop},
                    "Required": ["userId"],
                },
                "output_schema": {
                    "Type": "object",
                    "Properties": {
                        "userId": {"Type": "string"},
                        "missionId": {"Type": "string"},
                        "title": {"Type": "string"},
                        "description": {"Type": "string"},
                        "status": {"Type": "string"},
                    },
                },
            },
            {
                "name": "regain_generate_mission",
                "description": "Generate a personalized daily mission via the Mission Engine pipeline.",
                "lambda_target": "missions",
                "input_schema": {
                    "Type": "object",
                    "Properties": {
                        "userId": user_id_prop,
                        "campaignId": {"Type": "string"},
                    },
                    "Required": ["userId", "campaignId"],
                },
                "output_schema": {
                    "Type": "object",
                    "Properties": {
                        "primary": {"Type": "object"},
                        "alternates": {"Type": "array", "Items": {"Type": "object"}},
                        "skill_gap_report": {"Type": "object"},
                    },
                },
            },
            {
                "name": "regain_complete_mission",
                "description": "Mark a mission as completed, log evidence, and update campaign progress.",
                "lambda_target": "evidence",
                "input_schema": {
                    "Type": "object",
                    "Properties": {
                        "userId": user_id_prop,
                        "missionId": {"Type": "string"},
                        "reflection": {"Type": "string"},
                        "skillTag": {"Type": "string"},
                        "artifactUrl": {"Type": "string"},
                    },
                    "Required": ["userId", "missionId", "reflection", "skillTag"],
                },
                "output_schema": {
                    "Type": "object",
                    "Properties": {
                        "mission_id": {"Type": "string"},
                        "evidence_id": {"Type": "string"},
                    },
                },
            },
            {
                "name": "regain_log_evidence",
                "description": "Log evidence to the user's Evidence Vault.",
                "lambda_target": "evidence",
                "input_schema": {
                    "Type": "object",
                    "Properties": {
                        "userId": user_id_prop,
                        "missionId": {"Type": "string"},
                        "skillTag": {"Type": "string"},
                        "reflection": {"Type": "string"},
                        "artifactUrl": {"Type": "string"},
                    },
                    "Required": ["userId", "missionId", "skillTag", "reflection"],
                },
                "output_schema": {
                    "Type": "object",
                    "Properties": {
                        "evidence_id": {"Type": "string"},
                        "skill_evidence_count": {"Type": "integer"},
                    },
                },
            },
            {
                "name": "regain_get_evidence_summary",
                "description": "Get a summary of all evidence in a user's Evidence Vault by skill.",
                "lambda_target": "evidence",
                "input_schema": {
                    "Type": "object",
                    "Properties": {"userId": user_id_prop},
                    "Required": ["userId"],
                },
                "output_schema": {
                    "Type": "object",
                    "Properties": {
                        "total_count": {"Type": "integer"},
                    },
                },
            },
            {
                "name": "regain_get_market_insights",
                "description": "Get market intelligence for a target role.",
                "lambda_target": "market_intel",
                "input_schema": {
                    "Type": "object",
                    "Properties": {
                        "roleId": {"Type": "string"},
                    },
                    "Required": ["roleId"],
                },
                "output_schema": {
                    "Type": "object",
                    "Properties": {
                        "role_id": {"Type": "string"},
                        "demand_score": {"Type": "number"},
                        "trend_direction": {"Type": "string"},
                    },
                },
            },
            {
                "name": "regain_get_alignment",
                "description": "Calculate skill alignment between a user and a target role.",
                "lambda_target": "market_intel",
                "input_schema": {
                    "Type": "object",
                    "Properties": {
                        "userId": user_id_prop,
                        "targetRoleId": {"Type": "string"},
                    },
                    "Required": ["userId", "targetRoleId"],
                },
                "output_schema": {
                    "Type": "object",
                    "Properties": {
                        "alignment_pct": {"Type": "number"},
                        "user_id": {"Type": "string"},
                    },
                },
            },
            {
                "name": "regain_recall_memory",
                "description": "Retrieve relevant past conversation context for a user.",
                "lambda_target": "coaching",
                "input_schema": {
                    "Type": "object",
                    "Properties": {
                        "userId": user_id_prop,
                        "query": {"Type": "string"},
                    },
                    "Required": ["userId", "query"],
                },
                "output_schema": {
                    "Type": "array",
                    "Items": {"Type": "object"},
                },
            },
            {
                "name": "regain_store_memory",
                "description": "Store a coaching session summary for long-term memory.",
                "lambda_target": "coaching",
                "input_schema": {
                    "Type": "object",
                    "Properties": {
                        "userId": user_id_prop,
                        "content": {"Type": "string"},
                    },
                    "Required": ["userId", "content"],
                },
                "output_schema": {
                    "Type": "object",
                    "Properties": {
                        "status": {"Type": "string"},
                        "namespace": {"Type": "string"},
                    },
                },
            },
        ]

    def _register_tool_schemas(self) -> list[cdk.CfnResource]:
        """Register MCP tool schemas as Gateway targets.

        Creates AWS::BedrockAgentCore::GatewayTarget for each tool,
        using the correct Mcp.Lambda target configuration.
        """
        targets: list[cdk.CfnResource] = []

        for schema in self._tool_registry():
            tool_name: str = schema["name"]
            lambda_key: str = schema["lambda_target"]

            # Resolve the Lambda; fall back to coaching for market_intel if not provisioned.
            lambda_fn = self._lambda_targets.get(
                lambda_key,
                self._lambda_targets["coaching"],
            )

            # GatewayTarget Name must match pattern: ^([0-9a-zA-Z][-]?){1,100}$
            target_name = tool_name.replace("_", "-")

            # PascalCase logical ID for CDK construct.
            logical_id = "".join(part.capitalize() for part in tool_name.split("_"))

            target = cdk.CfnResource(
                self,
                f"GatewayTarget{logical_id}",
                type="AWS::BedrockAgentCore::GatewayTarget",
                properties={
                    "GatewayIdentifier": self.gateway.ref,
                    "Name": target_name,
                    "Description": schema["description"],
                    "TargetConfiguration": {
                        "Mcp": {
                            "Lambda": {
                                "LambdaArn": lambda_fn.function_arn,
                                "ToolSchema": {
                                    "InlinePayload": [
                                        {
                                            "Name": tool_name,
                                            "Description": schema["description"],
                                            "InputSchema": schema["input_schema"],
                                            "OutputSchema": schema["output_schema"],
                                        },
                                    ],
                                },
                            },
                        },
                    },
                    "CredentialProviderConfigurations": [
                        {
                            "CredentialProviderType": "GATEWAY_IAM_ROLE",
                        },
                    ],
                },
            )

            target.add_dependency(self.gateway)
            targets.append(target)

        return targets

    # -- S3 bucket for Code Interpreter ----------------------------------------

    def _create_code_interpreter_bucket(self) -> s3.Bucket:
        """Create S3 bucket for Code Interpreter output files."""
        return s3.Bucket(
            self,
            "RegainCodeInterpreterOutput",
            bucket_name=f"regain-code-interpreter-output-{self.account}",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=cdk.RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            lifecycle_rules=[
                s3.LifecycleRule(
                    expiration=cdk.Duration.days(1),
                    id="expire-after-24h",
                ),
            ],
        )

    # -- CloudWatch dashboard --------------------------------------------------

    def create_dashboard(self) -> None:
        """Create REGAIN-Coaching-Operations CloudWatch dashboard."""
        namespace = "REGAIN/Coaching"
        policy_log_group = self._policy_audit_log_group.log_group_name

        tool_names = [
            "regain_read_user_profile",
            "regain_update_user_profile",
            "regain_get_campaign_status",
            "regain_create_campaign",
            "regain_get_current_mission",
            "regain_generate_mission",
            "regain_complete_mission",
            "regain_log_evidence",
            "regain_get_evidence_summary",
            "regain_get_market_insights",
            "regain_get_alignment",
            "regain_recall_memory",
            "regain_store_memory",
        ]

        session_count_widget = {
            "type": "metric", "x": 0, "y": 0, "width": 8, "height": 6,
            "properties": {
                "title": "Session Count",
                "metrics": [
                    [namespace, "SessionCount", "Period", "Daily", {"stat": "Sum", "label": "Daily Sessions"}],
                    [namespace, "SessionCount", "Period", "Weekly", {"stat": "Sum", "label": "Weekly Sessions"}],
                ],
                "view": "timeSeries", "period": 86400,
            },
        }

        active_users_widget = {
            "type": "metric", "x": 8, "y": 0, "width": 8, "height": 6,
            "properties": {
                "title": "Active Users",
                "metrics": [[namespace, "ActiveUsers", {"stat": "Maximum", "label": "Active Users"}]],
                "view": "singleValue", "period": 300,
            },
        }

        error_rate_widget = {
            "type": "metric", "x": 16, "y": 0, "width": 8, "height": 6,
            "properties": {
                "title": "Error Rate",
                "metrics": [
                    [namespace, "ErrorCount", {"stat": "Sum", "id": "errors", "visible": False}],
                    [namespace, "InvocationCount", {"stat": "Sum", "id": "total", "visible": False}],
                    [{"expression": "100 * errors / total", "label": "Error Rate %", "id": "rate"}],
                ],
                "view": "gauge", "yAxis": {"left": {"min": 0, "max": 100}}, "period": 300,
            },
        }

        tool_invocation_metrics = [
            [namespace, "ToolInvocationCount", "ToolName", name, {"stat": "Sum", "label": name}]
            for name in tool_names
        ]
        tool_invocation_widget = {
            "type": "metric", "x": 0, "y": 6, "width": 8, "height": 6,
            "properties": {
                "title": "Tool Invocations by Tool",
                "metrics": tool_invocation_metrics,
                "view": "timeSeries", "stacked": True, "period": 3600,
            },
        }

        policy_denial_widget = {
            "type": "log", "x": 8, "y": 6, "width": 8, "height": 6,
            "properties": {
                "title": "Policy Denials",
                "query": (
                    f"SOURCE '{policy_log_group}' "
                    "| filter evaluation_result = 'DENY' "
                    "| fields @timestamp, tool_name, userId, policy_name, denial_reason "
                    "| sort @timestamp desc | limit 50"
                ),
                "view": "table",
            },
        }

        token_usage_widget = {
            "type": "metric", "x": 16, "y": 6, "width": 8, "height": 6,
            "properties": {
                "title": "Token Usage",
                "metrics": [
                    [namespace, "TokenUsage", "Direction", "Input", {"stat": "Sum", "label": "Input Tokens"}],
                    [namespace, "TokenUsage", "Direction", "Output", {"stat": "Sum", "label": "Output Tokens"}],
                ],
                "view": "timeSeries", "stacked": True, "period": 3600,
            },
        }

        latency_percentile_widget = {
            "type": "metric", "x": 0, "y": 12, "width": 12, "height": 6,
            "properties": {
                "title": "Tool Invocation Latency Percentiles",
                "metrics": [
                    [namespace, "ToolInvocationLatency", {"stat": "p50", "label": "p50"}],
                    [namespace, "ToolInvocationLatency", {"stat": "p95", "label": "p95"}],
                    [namespace, "ToolInvocationLatency", {"stat": "p99", "label": "p99"}],
                ],
                "view": "timeSeries", "period": 300,
            },
        }

        memory_ops_widget = {
            "type": "metric", "x": 12, "y": 12, "width": 12, "height": 6,
            "properties": {
                "title": "Memory Operations",
                "metrics": [
                    [namespace, "MemoryOperationCount", "Operation", "Read", {"stat": "Sum", "label": "Reads"}],
                    [namespace, "MemoryOperationCount", "Operation", "Write", {"stat": "Sum", "label": "Writes"}],
                    [namespace, "MemoryOperationLatency", "Operation", "Read", {"stat": "Average", "label": "Read Latency (ms)"}],
                    [namespace, "MemoryOperationLatency", "Operation", "Write", {"stat": "Average", "label": "Write Latency (ms)"}],
                ],
                "view": "bar", "period": 3600,
            },
        }

        dashboard_body = {
            "widgets": [
                session_count_widget, active_users_widget, error_rate_widget,
                tool_invocation_widget, policy_denial_widget, token_usage_widget,
                latency_percentile_widget, memory_ops_widget,
            ],
        }

        cdk.CfnResource(
            self,
            "RegainCoachingDashboard",
            type="AWS::CloudWatch::Dashboard",
            properties={
                "DashboardName": "REGAIN-Coaching-Operations",
                "DashboardBody": json.dumps(dashboard_body),
            },
        )

    # -- Alarms ----------------------------------------------------------------

    def create_alarms(self) -> None:
        """Create SNS topic and CloudWatch alarms for operational alerting."""
        namespace = "REGAIN/Coaching"

        self._alert_topic = sns.Topic(
            self,
            "RegainCoachingAlerts",
            topic_name="RegainCoachingAlerts",
            display_name="REGAIN Coaching Operational Alerts",
        )
        sns_action = cw_actions.SnsAction(self._alert_topic)

        # Alarm 1: Error rate > 10% over 5 minutes.
        error_count_metric = cloudwatch.Metric(
            namespace=namespace, metric_name="ErrorCount",
            statistic="Sum", period=cdk.Duration.minutes(5),
        )
        invocation_count_metric = cloudwatch.Metric(
            namespace=namespace, metric_name="InvocationCount",
            statistic="Sum", period=cdk.Duration.minutes(5),
        )
        error_rate_expr = cloudwatch.MathExpression(
            expression="IF(total > 0, errors / total, 0)",
            using_metrics={"errors": error_count_metric, "total": invocation_count_metric},
            label="Error Rate", period=cdk.Duration.minutes(5),
        )
        error_rate_alarm = error_rate_expr.create_alarm(
            self, "RegainHighErrorRateAlarm",
            alarm_name="Regain-HighErrorRate",
            alarm_description="Coaching system error rate exceeds 10% over 5 minutes",
            threshold=0.1, evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        error_rate_alarm.add_alarm_action(sns_action)

        # Alarm 2: p95 latency > 5 seconds.
        latency_metric = cloudwatch.Metric(
            namespace=namespace, metric_name="ToolInvocationLatency",
            statistic="p95", period=cdk.Duration.minutes(5),
        )
        latency_alarm = latency_metric.create_alarm(
            self, "RegainHighLatencyAlarm",
            alarm_name="Regain-HighLatency",
            alarm_description="p95 tool invocation latency exceeds 5 seconds",
            threshold=5000, evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        latency_alarm.add_alarm_action(sns_action)

        # Alarm 3: Policy denial spike > 20 in 1 minute.
        denial_metric = cloudwatch.Metric(
            namespace=namespace, metric_name="PolicyDenialCount",
            statistic="Sum", period=cdk.Duration.minutes(1),
        )
        denial_alarm = denial_metric.create_alarm(
            self, "RegainPolicyDenialSpikeAlarm",
            alarm_name="Regain-PolicyDenialSpike",
            alarm_description="Policy denial count exceeds 20 in 1 minute",
            threshold=20, evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        denial_alarm.add_alarm_action(sns_action)

    # -- Outputs ---------------------------------------------------------------

    def _create_outputs(self) -> None:
        """Create CfnOutputs for Gateway endpoint, IDs, and ARNs."""
        cdk.CfnOutput(
            self, "GatewayId",
            value=self.gateway.ref,
            export_name="RegainAgentCoreGatewayId",
        )
        cdk.CfnOutput(
            self, "GatewayEndpointUrl",
            value=cdk.Fn.get_att(self.gateway.logical_id, "GatewayUrl").to_string(),
            export_name="RegainAgentCoreGatewayEndpoint",
        )
        cdk.CfnOutput(
            self, "GatewayLambdaRoleArn",
            value=self._gateway_lambda_role.role_arn,
            export_name="RegainGatewayLambdaRoleArn",
        )
        cdk.CfnOutput(
            self, "AgentGatewayRoleArn",
            value=self._agent_gateway_role.role_arn,
            export_name="RegainAgentGatewayRoleArn",
        )
        cdk.CfnOutput(
            self, "AlertSnsTopicArn",
            value=self._alert_topic.topic_arn,
            export_name="RegainAlertSnsTopicArn",
        )
        cdk.CfnOutput(
            self, "CodeInterpreterBucketName",
            value=self._code_interpreter_bucket.bucket_name,
            export_name="RegainCodeInterpreterBucketName",
        )
