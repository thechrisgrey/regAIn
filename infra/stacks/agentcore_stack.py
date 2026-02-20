"""REGAIN AgentCore Stack — Gateway, Policy, Observability, and Alerting.

Provisions AgentCore platform services that wrap existing Lambda-backed tools
with centralized auth, Cedar policy enforcement, and distributed tracing.
Gateway wraps existing functions — it does not replace them.

Requirements: 1.1, 1.2, 1.4, 1.5, 9.1, 9.2, 9.3, 14.1, 14.2, 14.3, 14.4
"""

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
    """AgentCore platform services: Gateway, Policy, Observability, Alerting."""

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
        """Initialize AgentCoreStack with cross-stack references.

        Args:
            scope: CDK app or stage.
            construct_id: Stack logical ID.
            coaching_lambda: Coaching Lambda from ApiStack.
            missions_lambda: Missions Lambda from ApiStack.
            evidence_lambda: Evidence Lambda from ApiStack.
            dashboard_lambda: Dashboard Lambda from ApiStack.
            market_intel_lambda: Market Intel Lambda (optional, added when available).
            user_pool: Cognito User Pool from AuthStack.
            **kwargs: Additional CDK Stack kwargs.
        """
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

        self.gateway = self._create_gateway()
        self._gateway_lambda_role = self._create_gateway_lambda_role()
        self._agent_gateway_role = self._create_agent_gateway_role()
        self._gateway_targets = self._register_tool_schemas()
        self._cedar_policies = self.attach_cedar_policies()
        self._policy_audit_log_group = self._configure_policy_audit_logging()
        self._observability_config = self.configure_observability()
        self.create_dashboard()
        self.create_alarms()
        self._code_interpreter_bucket = self._create_code_interpreter_bucket()
        self._code_interpreter_target = self._register_code_interpreter_target()
        self._create_outputs()

    def _create_gateway(self) -> cdk.CfnResource:
        """Create AgentCore Gateway instance with Cognito JWT authorization.

        Returns:
            CfnResource representing the Gateway instance.
        """
        return cdk.CfnResource(
            self,
            "RegainCoachingGateway",
            type="AWS::BedrockAgentCore::Gateway",
            properties={
                "Name": "regain-coaching-gateway",
                "Description": "REGAIN Coaching Agent tool gateway with MCP-compatible access",
                "AuthorizationConfiguration": {
                    "AuthorizationType": "JWT",
                    "JwtAuthorizationConfiguration": {
                        "Issuer": f"https://cognito-idp.{self.region}.amazonaws.com/{self._user_pool.user_pool_id}",
                        "AllowedAudiences": [self._user_pool.user_pool_id],
                    },
                },
                "ProtocolConfiguration": {
                    "Mcp": {
                        "SupportedVersions": ["2025-03-26"],
                        "SemanticToolDiscovery": {
                            "Enabled": True,
                        },
                    },
                },
            },
        )

    def _create_gateway_lambda_role(self) -> iam.Role:
        """Create IAM role for Gateway to invoke Lambda tool targets.

        Returns:
            IAM Role with Lambda invoke permissions on all tool targets.
        """
        role = iam.Role(
            self,
            "RegainGatewayLambdaRole",
            role_name="RegainGatewayLambdaInvocationRole",
            assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"),
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
        """Create IAM role for the Coaching Agent to access Gateway.

        Returns:
            IAM Role with permissions to invoke Gateway endpoints.
        """
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

    def _configure_policy_audit_logging(self) -> logs.LogGroup:
        """Create CloudWatch log group and configure Gateway policy audit logging.

        Creates a dedicated log group for Cedar policy evaluation results.
        Configures the Gateway to emit structured audit logs containing:
        - All evaluations: tool name, userId, policy name, result (permit/deny), timestamp
        - Denials only: additionally log denial reason and request context (excluding sensitive data)

        Requirement 9.3 note: policy evaluation latency (<50ms) is managed by
        the Gateway service itself — no application-level optimization needed.

        Returns:
            The CloudWatch LogGroup for policy audit logs.

        Requirements: 9.1, 9.2, 9.3
        """
        log_group = logs.LogGroup(
            self,
            "RegainPolicyAuditLogs",
            log_group_name="/regain/agentcore/policy-audit",
            retention=logs.RetentionDays.THREE_MONTHS,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        cdk.Tags.of(log_group).add("Project", "REGAIN")
        cdk.Tags.of(log_group).add("Environment", "dev")

        # Configure Gateway to emit policy evaluation logs to CloudWatch.
        # The Gateway natively logs all Cedar policy evaluation results
        # including permit/deny decisions, tool name, userId, policy name,
        # and timestamp. For denials, it additionally logs the denial reason
        # and sanitized request context (sensitive data excluded).
        audit_log_config = cdk.CfnResource(
            self,
            "RegainGatewayAuditLogConfig",
            type="AWS::BedrockAgentCore::Gateway",
            properties={
                "GatewayIdentifier": self.gateway.ref,
                "LoggingConfiguration": {
                    "LogDestination": {
                        "CloudWatchLogGroup": {
                            "LogGroupArn": log_group.log_group_arn,
                        },
                    },
                    "PolicyEvaluationLogging": {
                        "Enabled": True,
                        "LogLevel": "ALL",
                        "IncludeRequestContext": True,
                        "ExcludeSensitiveData": True,
                    },
                },
            },
        )

        audit_log_config.add_dependency(self.gateway)

        cdk.Tags.of(audit_log_config).add("Project", "REGAIN")
        cdk.Tags.of(audit_log_config).add("Environment", "dev")

        # Grant Gateway permission to write to the audit log group.
        log_group.grant_write(iam.ServicePrincipal("bedrock.amazonaws.com"))

        # Export log group ARN for cross-stack reference.
        cdk.CfnOutput(
            self,
            "PolicyAuditLogGroupArn",
            value=log_group.log_group_arn,
            export_name="RegainPolicyAuditLogGroupArn",
            description="CloudWatch Log Group ARN for policy evaluation audit logs",
        )

        return log_group

    def _create_outputs(self) -> None:
        """Create CfnOutputs for Gateway endpoint URL and Gateway ID."""
        cdk.CfnOutput(
            self,
            "GatewayId",
            value=self.gateway.ref,
            export_name="RegainAgentCoreGatewayId",
            description="AgentCore Gateway instance ID",
        )

        cdk.CfnOutput(
            self,
            "GatewayEndpointUrl",
            value=cdk.Fn.get_att(self.gateway.logical_id, "Endpoint").to_string(),
            export_name="RegainAgentCoreGatewayEndpoint",
            description="AgentCore Gateway MCP endpoint URL",
        )

        cdk.CfnOutput(
            self,
            "GatewayLambdaRoleArn",
            value=self._gateway_lambda_role.role_arn,
            export_name="RegainGatewayLambdaRoleArn",
            description="IAM Role ARN for Gateway to invoke Lambda targets",
        )

        cdk.CfnOutput(
            self,
            "AgentGatewayRoleArn",
            value=self._agent_gateway_role.role_arn,
            export_name="RegainAgentGatewayRoleArn",
            description="IAM Role ARN for Agent to access Gateway",
        )

        cdk.CfnOutput(
            self,
            "AlertSnsTopicArn",
            value=self._alert_topic.topic_arn,
            export_name="RegainAlertSnsTopicArn",
            description="SNS topic ARN for coaching operational alerts",
        )

        cdk.CfnOutput(
            self,
            "CodeInterpreterBucketName",
            value=self._code_interpreter_bucket.bucket_name,
            export_name="RegainCodeInterpreterBucketName",
            description="S3 bucket for Code Interpreter output files",
        )

    # -- Code Interpreter resources (Stretch Goal) ----------------------------

    def _create_code_interpreter_bucket(self) -> s3.Bucket:
        """Create S3 bucket for Code Interpreter output files.

        Bucket stores chart images and CSV exports generated by the
        sandboxed Code Interpreter. Objects expire after 24 hours.
        Access is via presigned URLs with 1-hour expiry (handled at
        application level, not in CDK).

        Returns:
            The S3 Bucket for Code Interpreter output.

        Requirements: 13.3, 13.5
        """
        bucket = s3.Bucket(
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

        cdk.Tags.of(bucket).add("Project", "REGAIN")
        cdk.Tags.of(bucket).add("Environment", "dev")

        return bucket

    def _register_code_interpreter_target(self) -> cdk.CfnResource:
        """Register Code Interpreter as a Gateway tool target.

        Configures the Code Interpreter with sandbox constraints:
        - Pre-installed packages: matplotlib, pandas, numpy only
        - No network access
        - 30-second execution timeout
        - 512MB memory limit
        - Auto-terminate after 5 minutes of inactivity

        Returns:
            CfnResource representing the Code Interpreter Gateway target.

        Requirements: 13.2, 13.4, 13.5
        """
        target = cdk.CfnResource(
            self,
            "GatewayTargetRegainCodeInterpreter",
            type="AWS::BedrockAgentCore::GatewayTarget",
            properties={
                "GatewayIdentifier": self.gateway.ref,
                "Name": "regain_code_interpreter",
                "Description": (
                    "Sandboxed Python Code Interpreter for generating "
                    "visualizations and data exports from user progress data."
                ),
                "ToolSchema": {
                    "InputSchema": {
                        "type": "object",
                        "properties": {
                            "code": {"type": "string"},
                            "session_id": {"type": "string"},
                        },
                        "required": ["code", "session_id"],
                    },
                    "OutputSchema": {
                        "type": "object",
                        "properties": {
                            "url": {"type": "string"},
                            "execution_status": {"type": "string"},
                            "stdout": {"type": "string"},
                            "stderr": {"type": "string"},
                        },
                    },
                },
                "TargetConfiguration": {
                    "CodeInterpreterTargetConfiguration": {
                        "SandboxConfiguration": {
                            "AllowedPackages": ["matplotlib", "pandas", "numpy"],
                            "NetworkAccess": False,
                            "MaxExecutionTimeSeconds": 30,
                            "MaxMemoryMb": 512,
                            "IdleTimeoutSeconds": 300,
                        },
                        "OutputBucket": self._code_interpreter_bucket.bucket_name,
                    },
                },
                "CredentialProviderConfigurations": [
                    {
                        "CredentialProviderType": "GATEWAY_IAM_ROLE",
                        "CredentialProvider": {
                            "RoleArn": self._gateway_lambda_role.role_arn,
                        },
                    },
                ],
            },
        )

        target.add_dependency(self.gateway)

        cdk.Tags.of(target).add("Project", "REGAIN")
        cdk.Tags.of(target).add("Environment", "dev")

        return target

    # -- Tool schema definitions for Gateway registration ----------------------
    # Defined inline rather than imported from backend/agents/coaching/tool_schemas.py
    # because CDK runs in a separate Python context from the Lambda runtime.

    @staticmethod
    def _tool_registry() -> list[dict[str, Any]]:
        """Return all 13 MCP tool schemas with their Lambda target keys.

        Each entry mirrors the schema in backend/agents/coaching/tool_schemas.py
        but is kept self-contained for CDK synthesis.

        Returns:
            List of dicts with name, description, lambda_target,
            input_schema, and output_schema.
        """
        user_id_prop: dict[str, Any] = {
            "type": "string",
            "description": "Authenticated user ID, injected from Cognito JWT claims.",
        }

        return [
            {
                "name": "regain_read_user_profile",
                "description": (
                    "Read a user's complete profile including persona, "
                    "target role, skills, and onboarding status."
                ),
                "lambda_target": "coaching",
                "input_schema": {
                    "type": "object",
                    "properties": {"userId": user_id_prop},
                    "required": ["userId"],
                },
                "output_schema": {
                    "type": "object",
                    "properties": {
                        "userId": {"type": "string"},
                        "name": {"type": "string"},
                        "email": {"type": "string"},
                        "persona": {"type": "string"},
                        "target_role": {"type": "string"},
                        "skills": {"type": "array", "items": {"type": "string"}},
                        "onboarding_completed": {"type": "boolean"},
                        "created_at": {"type": "string"},
                    },
                },
            },
            {
                "name": "regain_update_user_profile",
                "description": (
                    "Update fields on a user's profile. Pass only the "
                    "fields that need to change."
                ),
                "lambda_target": "coaching",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "userId": user_id_prop,
                        "updates": {"type": "object", "description": "Field-value pairs to update."},
                    },
                    "required": ["userId", "updates"],
                },
                "output_schema": {
                    "type": "object",
                    "additionalProperties": True,
                },
            },
            {
                "name": "regain_get_campaign_status",
                "description": (
                    "Get the active campaign for a user including phase, "
                    "target role, and skills focus."
                ),
                "lambda_target": "coaching",
                "input_schema": {
                    "type": "object",
                    "properties": {"userId": user_id_prop},
                    "required": ["userId"],
                },
                "output_schema": {
                    "type": "object",
                    "properties": {
                        "userId": {"type": "string"},
                        "campaignId": {"type": "string"},
                        "title": {"type": "string"},
                        "phase": {"type": "string"},
                        "status": {"type": "string"},
                        "startDate": {"type": "string"},
                        "targetRole": {"type": "string"},
                        "skillsFocus": {"type": "array", "items": {"type": "string"}},
                    },
                },
            },
            {
                "name": "regain_create_campaign",
                "description": (
                    "Create a new reskilling campaign starting in the "
                    "foundation phase."
                ),
                "lambda_target": "coaching",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "userId": user_id_prop,
                        "title": {"type": "string"},
                        "targetRole": {"type": "string"},
                        "skillsFocus": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["userId", "title", "targetRole", "skillsFocus"],
                },
                "output_schema": {
                    "type": "object",
                    "properties": {
                        "userId": {"type": "string"},
                        "campaignId": {"type": "string"},
                        "title": {"type": "string"},
                        "phase": {"type": "string"},
                        "status": {"type": "string"},
                        "startDate": {"type": "string"},
                        "targetRole": {"type": "string"},
                        "skillsFocus": {"type": "array", "items": {"type": "string"}},
                    },
                },
            },
            {
                "name": "regain_get_current_mission",
                "description": (
                    "Get the current pending or in-progress mission for "
                    "a user with behavioral pattern analysis."
                ),
                "lambda_target": "missions",
                "input_schema": {
                    "type": "object",
                    "properties": {"userId": user_id_prop},
                    "required": ["userId"],
                },
                "output_schema": {
                    "type": "object",
                    "properties": {
                        "userId": {"type": "string"},
                        "missionId": {"type": "string"},
                        "campaignId": {"type": "string"},
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                        "status": {"type": "string"},
                        "skillTag": {"type": "string"},
                        "patterns": {"type": "object"},
                    },
                },
            },
            {
                "name": "regain_generate_mission",
                "description": (
                    "Generate a personalized daily mission via the Mission "
                    "Engine pipeline. Returns top mission plus alternates."
                ),
                "lambda_target": "missions",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "userId": user_id_prop,
                        "campaignId": {"type": "string"},
                    },
                    "required": ["userId", "campaignId"],
                },
                "output_schema": {
                    "type": "object",
                    "properties": {
                        "primary": {"type": "object"},
                        "alternates": {"type": "array", "items": {"type": "object"}},
                        "skill_gap_report": {"type": "object"},
                    },
                },
            },
            {
                "name": "regain_complete_mission",
                "description": (
                    "Mark a mission as completed, log evidence, and update "
                    "campaign progress."
                ),
                "lambda_target": "evidence",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "userId": user_id_prop,
                        "missionId": {"type": "string"},
                        "reflection": {"type": "string"},
                        "skillTag": {"type": "string"},
                        "artifactUrl": {"type": "string"},
                    },
                    "required": ["userId", "missionId", "reflection", "skillTag"],
                },
                "output_schema": {
                    "type": "object",
                    "properties": {
                        "mission_id": {"type": "string"},
                        "difficulty_change": {"type": "object"},
                        "gate_result": {"type": "object"},
                        "evidence_id": {"type": "string"},
                        "skill_evidence_count": {"type": "integer"},
                    },
                },
            },
            {
                "name": "regain_log_evidence",
                "description": (
                    "Log evidence to the user's Evidence Vault with a "
                    "timestamped, skill-tagged record."
                ),
                "lambda_target": "evidence",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "userId": user_id_prop,
                        "missionId": {"type": "string"},
                        "skillTag": {"type": "string"},
                        "reflection": {"type": "string"},
                        "artifactUrl": {"type": "string"},
                    },
                    "required": ["userId", "missionId", "skillTag", "reflection"],
                },
                "output_schema": {
                    "type": "object",
                    "properties": {
                        "evidence_id": {"type": "string"},
                        "skill_evidence_count": {"type": "integer"},
                    },
                },
            },
            {
                "name": "regain_get_evidence_summary",
                "description": (
                    "Get a summary of all evidence in a user's Evidence "
                    "Vault broken down by skill."
                ),
                "lambda_target": "evidence",
                "input_schema": {
                    "type": "object",
                    "properties": {"userId": user_id_prop},
                    "required": ["userId"],
                },
                "output_schema": {
                    "type": "object",
                    "properties": {
                        "by_skill": {"type": "object", "additionalProperties": {"type": "integer"}},
                        "recent": {"type": "array", "items": {"type": "object"}},
                        "total_count": {"type": "integer"},
                    },
                },
            },
            {
                "name": "regain_get_market_insights",
                "description": (
                    "Get market intelligence for a target role including "
                    "demand scores, trends, and salary ranges."
                ),
                "lambda_target": "market_intel",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "roleId": {"type": "string"},
                    },
                    "required": ["roleId"],
                },
                "output_schema": {
                    "type": "object",
                    "properties": {
                        "role_id": {"type": "string"},
                        "demand_score": {"type": "number"},
                        "trend_direction": {"type": "string"},
                        "growth_rate": {"type": "number"},
                        "top_skills": {"type": "array", "items": {"type": "string"}},
                        "salary_range": {"type": "object"},
                        "insights": {"type": "object"},
                    },
                },
            },
            {
                "name": "regain_get_alignment",
                "description": (
                    "Calculate skill alignment between a user and a target "
                    "role with gap and strength analysis."
                ),
                "lambda_target": "market_intel",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "userId": user_id_prop,
                        "targetRoleId": {"type": "string"},
                    },
                    "required": ["userId", "targetRoleId"],
                },
                "output_schema": {
                    "type": "object",
                    "properties": {
                        "alignment_pct": {"type": "number"},
                        "skill_breakdown": {"type": "array", "items": {"type": "object"}},
                        "top_gaps": {"type": "array", "items": {"type": "object"}},
                        "top_strengths": {"type": "array", "items": {"type": "object"}},
                        "target_role_id": {"type": "string"},
                        "user_id": {"type": "string"},
                        "calculated_at": {"type": "string"},
                    },
                },
            },
            {
                "name": "regain_recall_memory",
                "description": (
                    "Retrieve relevant past conversation context for a "
                    "user ranked by semantic relevance and recency."
                ),
                "lambda_target": "coaching",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "userId": user_id_prop,
                        "query": {"type": "string"},
                    },
                    "required": ["userId", "query"],
                },
                "output_schema": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "content": {"type": "string"},
                            "metadata": {"type": "object"},
                        },
                    },
                },
            },
            {
                "name": "regain_store_memory",
                "description": (
                    "Store a coaching session summary or key observation "
                    "for long-term memory."
                ),
                "lambda_target": "coaching",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "userId": user_id_prop,
                        "content": {"type": "string"},
                    },
                    "required": ["userId", "content"],
                },
                "output_schema": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string"},
                        "namespace": {"type": "string"},
                    },
                },
            },
            {
                "name": "regain_code_interpreter",
                "description": (
                    "Execute Python code in a sandboxed Code Interpreter "
                    "to generate visualizations or data exports. Only "
                    "matplotlib, pandas, and numpy available. No network, "
                    "30s timeout, 512MB memory."
                ),
                "lambda_target": "code_interpreter",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string"},
                        "session_id": {"type": "string"},
                    },
                    "required": ["code", "session_id"],
                },
                "output_schema": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string"},
                        "execution_status": {"type": "string"},
                        "stdout": {"type": "string"},
                        "stderr": {"type": "string"},
                    },
                },
            },
        ]

    def _register_tool_schemas(self) -> list[cdk.CfnResource]:
        """Register all 13 MCP tool schemas as Gateway targets.

        Creates a ``AWS::BedrockAgentCore::GatewayTarget`` CfnResource for
        each tool, mapping it to the correct Lambda function ARN and
        attaching it to the Gateway instance.

        Returns:
            List of CfnResource objects representing the registered targets.
        """
        targets: list[cdk.CfnResource] = []

        for schema in self._tool_registry():
            tool_name: str = schema["name"]
            lambda_key: str = schema["lambda_target"]

            # Code Interpreter has its own dedicated registration method
            # (_register_code_interpreter_target) with a different target
            # configuration, so skip it here to avoid duplicate constructs.
            if lambda_key == "code_interpreter":
                continue

            # Resolve the Lambda function for this tool's target key.
            # Market intel tools fall back to coaching Lambda when the
            # dedicated market_intel Lambda is not yet provisioned.
            lambda_fn = self._lambda_targets.get(
                lambda_key,
                self._lambda_targets["coaching"],
            )

            # Convert snake_case tool name to PascalCase for the logical ID.
            logical_id = "".join(
                part.capitalize() for part in tool_name.split("_")
            )

            target = cdk.CfnResource(
                self,
                f"GatewayTarget{logical_id}",
                type="AWS::BedrockAgentCore::GatewayTarget",
                properties={
                    "GatewayIdentifier": self.gateway.ref,
                    "Name": tool_name,
                    "Description": schema["description"],
                    "ToolSchema": {
                        "InputSchema": schema["input_schema"],
                        "OutputSchema": schema["output_schema"],
                    },
                    "TargetConfiguration": {
                        "LambdaTargetConfiguration": {
                            "LambdaArn": lambda_fn.function_arn,
                        },
                    },
                    "CredentialProviderConfigurations": [
                        {
                            "CredentialProviderType": "GATEWAY_IAM_ROLE",
                            "CredentialProvider": {
                                "RoleArn": self._gateway_lambda_role.role_arn,
                            },
                        },
                    ],
                },
            )

            # Ensure targets are created after the Gateway exists.
            target.add_dependency(self.gateway)

            cdk.Tags.of(target).add("Project", "REGAIN")
            cdk.Tags.of(target).add("Environment", "dev")

            targets.append(target)

        return targets

    def attach_cedar_policies(self) -> list[cdk.CfnResource]:
        """Define and attach Cedar policies to the Gateway instance.

        Creates CfnResource entries for each Cedar policy document and
        attaches them to the Gateway. Designed so each policy is added
        via the reusable ``_attach_policy`` helper.

        Returns:
            List of CfnResource objects representing attached policies.
        """
        policies: list[cdk.CfnResource] = []

        policies.append(self._attach_policy(
            policy_id="UserDataIsolation",
            policy_name="regain-user-data-isolation",
            description=(
                "Permits tool invocations only when the request userId "
                "matches the authenticated JWT userId. Denies cross-user "
                "data access regardless of agent behavior."
            ),
            cedar_document=self._cedar_user_data_isolation(),
        ))

        policies.append(self._attach_policy(
            policy_id="EvidenceWriteScope",
            policy_name="regain-evidence-write-scope",
            description=(
                "Permits log_evidence only when the coaching session is "
                "active and the evidence timestamp is within the last 24 "
                "hours. Campaign-completed check is enforced in Lambda."
            ),
            cedar_document=self._cedar_evidence_write_scope(),
        ))

        policies.append(self._attach_policy(
            policy_id="MissionGenerationRateLimit",
            policy_name="regain-mission-generation-rate-limit",
            description=(
                "Defense-in-depth backstop: permits generate_mission only "
                "when the daily generation count is fewer than 3. Primary "
                "enforcement is the DynamoDB atomic conditional update."
            ),
            cedar_document=self._cedar_mission_generation_rate_limit(),
        ))

        policies.append(self._attach_policy(
            policy_id="ProfileUpdateRestrictions",
            policy_name="regain-profile-update-restrictions",
            description=(
                "Permits update_user_profile only when all modified fields "
                "are within the allowed set. Denies when restricted fields "
                "(email, cognitoId, role, tier, userId) are present."
            ),
            cedar_document=self._cedar_profile_update_restrictions(),
        ))

        policies.append(self._attach_policy(
            policy_id="MarketDataReadOnly",
            policy_name="regain-market-data-read-only",
            description=(
                "Permits get_market_insights and get_alignment for read "
                "operations on MarketData. Denies write, update, or delete "
                "operations to maintain market data integrity."
            ),
            cedar_document=self._cedar_market_data_read_only(),
        ))

        return policies

    @staticmethod
    def _cedar_user_data_isolation() -> str:
        """Return the Cedar policy document for user data isolation.

        Permits tool invocation only when the userId in tool_params matches
        the userId extracted from the JWT claims by Gateway authorization.
        Forbids any cross-user access.

        Returns:
            Cedar policy document string.
        """
        return (
            '// Policy: User Data Isolation\n'
            '// Requirement 4.1 — permit only when request userId matches JWT userId\n'
            '// Requirement 4.2 — deny cross-user access with reason\n'
            '// Requirement 4.3 — denial events logged to CloudWatch\n'
            'permit(\n'
            '    principal,\n'
            '    action in [Action::"invoke_tool"],\n'
            '    resource\n'
            ') when {\n'
            '    resource.tool_params.userId == context.auth.userId\n'
            '};\n'
            '\n'
            'forbid(\n'
            '    principal,\n'
            '    action in [Action::"invoke_tool"],\n'
            '    resource\n'
            ') when {\n'
            '    resource.tool_params.userId != context.auth.userId\n'
            '};'
        )

    @staticmethod
    def _cedar_evidence_write_scope() -> str:
        """Return the Cedar policy document for evidence write scope.

        Permits the log_evidence tool only when the coaching session is
        active AND the evidence timestamp is within the last 24 hours.
        The campaign-completed check is enforced in Lambda tool logic,
        not in Cedar, to avoid giving Gateway DynamoDB access.

        Returns:
            Cedar policy document string.
        """
        return (
            '// Policy: Evidence Write Scope\n'
            '// Requirement 5.1 — permit log_evidence only when session is active\n'
            '// Requirement 5.2 — permit log_evidence only when timestamp within 24h\n'
            '// Requirement 5.3 — campaign-completed check enforced in Lambda, not Cedar\n'
            'permit(\n'
            '    principal,\n'
            '    action in [Action::"invoke_tool"],\n'
            '    resource\n'
            ') when {\n'
            '    resource.tool_name == "regain_log_evidence" &&\n'
            '    context.session.is_active == true &&\n'
            '    context.evidence_timestamp.within_last_24h == true\n'
            '};\n'
            '\n'
            'forbid(\n'
            '    principal,\n'
            '    action in [Action::"invoke_tool"],\n'
            '    resource\n'
            ') when {\n'
            '    resource.tool_name == "regain_log_evidence" &&\n'
            '    (context.session.is_active == false ||\n'
            '     context.evidence_timestamp.within_last_24h == false)\n'
            '};'
        )

    @staticmethod
    def _cedar_mission_generation_rate_limit() -> str:
        """Return the Cedar policy document for mission generation rate limiting.

        Defense-in-depth backstop that permits generate_mission only when
        the daily generation count is fewer than 3. Primary enforcement is
        the DynamoDB atomic conditional update in the generate_mission tool.

        Returns:
            Cedar policy document string.
        """
        return (
            '// Policy: Mission Generation Rate Limit\n'
            '// Requirement 6.1 — permit generate_mission when daily count < 3\n'
            '// Requirement 6.2 — deny with reason when daily count >= 3\n'
            '// Requirement 6.3 — primary enforcement is DynamoDB conditional update\n'
            'permit(\n'
            '    principal,\n'
            '    action in [Action::"invoke_tool"],\n'
            '    resource\n'
            ') when {\n'
            '    resource.tool_name == "regain_generate_mission" &&\n'
            '    context.daily_generation_count < 3\n'
            '};\n'
            '\n'
            'forbid(\n'
            '    principal,\n'
            '    action in [Action::"invoke_tool"],\n'
            '    resource\n'
            ') when {\n'
            '    resource.tool_name == "regain_generate_mission" &&\n'
            '    context.daily_generation_count >= 3\n'
            '};'
        )

    @staticmethod
    def _cedar_profile_update_restrictions() -> str:
        """Return the Cedar policy document for profile update restrictions.

        Permits update_user_profile only when all field keys in the updates
        are within the allowed set. The Gateway context builder pre-computes
        ``context.all_fields_allowed`` by checking field keys against the
        allowed/restricted sets before Cedar evaluation.

        Returns:
            Cedar policy document string.
        """
        return (
            '// Policy: Profile Update Restrictions\n'
            '// Requirement 7.1 — permit update_user_profile only when all fields are in allowed set\n'
            '// Requirement 7.2 — deny when modified fields include restricted fields\n'
            '// Requirement 7.3 — deny with reason "restricted field modification denied"\n'
            'permit(\n'
            '    principal,\n'
            '    action in [Action::"invoke_tool"],\n'
            '    resource\n'
            ') when {\n'
            '    resource.tool_name == "regain_update_user_profile" &&\n'
            '    context.all_fields_allowed == true\n'
            '};\n'
            '\n'
            'forbid(\n'
            '    principal,\n'
            '    action in [Action::"invoke_tool"],\n'
            '    resource\n'
            ') when {\n'
            '    resource.tool_name == "regain_update_user_profile" &&\n'
            '    context.all_fields_allowed == false\n'
            '};'
        )
    @staticmethod
    def _cedar_market_data_read_only() -> str:
        """Return the Cedar policy document for market data read-only access.

        Permits the get_market_insights and get_alignment tools for read
        operations on MarketData. Forbids any write, update, or delete
        operations on MarketData by the Coaching Agent.

        Returns:
            Cedar policy document string.
        """
        return (
            '// Policy: Market Data Read-Only\n'
            '// Requirement 8.1 — permit get_market_insights and get_alignment for read operations\n'
            '// Requirement 8.2 — deny write/update/delete on MarketData by Coaching Agent\n'
            '// Requirement 8.3 — deny with reason "market data is read-only for coaching agent"\n'
            'permit(\n'
            '    principal,\n'
            '    action in [Action::"invoke_tool"],\n'
            '    resource\n'
            ') when {\n'
            '    resource.tool_name in ["regain_get_market_insights", "regain_get_alignment"]\n'
            '};\n'
            '\n'
            'forbid(\n'
            '    principal,\n'
            '    action in [Action::"invoke_tool"],\n'
            '    resource\n'
            ') when {\n'
            '    resource.target_table == "MarketData" &&\n'
            '    context.operation_type in ["write", "update", "delete"]\n'
            '};'
        )




    def _attach_policy(
        self,
        *,
        policy_id: str,
        policy_name: str,
        description: str,
        cedar_document: str,
    ) -> cdk.CfnResource:
        """Attach a single Cedar policy document to the Gateway.

        Reusable helper so all 5 Cedar policies follow the same pattern.

        Args:
            policy_id: PascalCase logical ID suffix (e.g. "UserDataIsolation").
            policy_name: Kebab-case policy name for the resource.
            description: Human-readable policy description.
            cedar_document: The Cedar policy document string.

        Returns:
            CfnResource representing the attached policy.
        """
        policy = cdk.CfnResource(
            self,
            f"CedarPolicy{policy_id}",
            type="AWS::BedrockAgentCore::GatewayPolicy",
            properties={
                "GatewayIdentifier": self.gateway.ref,
                "Name": policy_name,
                "Description": description,
                "PolicyDocument": cedar_document,
            },
        )

        policy.add_dependency(self.gateway)

        cdk.Tags.of(policy).add("Project", "REGAIN")
        cdk.Tags.of(policy).add("Environment", "dev")

        return policy

    def configure_observability(self) -> cdk.CfnResource:
        """Configure AgentCore Observability with OpenTelemetry trace export.

        Enables distributed tracing on the Gateway instance. Traces are
        auto-captured for Gateway routing, Cedar policy evaluation, and
        Lambda execution spans. All traces export to CloudWatch via
        OpenTelemetry protocol.

        Agent-level spans (session root, model inference, memory ops) are
        instrumented in backend/agents/coaching/instrumentation.py and
        attach to the Gateway-generated trace context.

        Returns:
            The CfnResource for the observability configuration.

        Requirements: 10.1, 10.2, 10.3, 10.4
        """
        # Log group for trace data exported via OpenTelemetry.
        trace_log_group = logs.LogGroup(
            self,
            "RegainObservabilityTraces",
            log_group_name="/regain/agentcore/traces",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        cdk.Tags.of(trace_log_group).add("Project", "REGAIN")
        cdk.Tags.of(trace_log_group).add("Environment", "dev")

        # Grant the Bedrock service principal write access to the trace log group.
        trace_log_group.grant_write(iam.ServicePrincipal("bedrock.amazonaws.com"))

        # Configure AgentCore Observability on the Gateway instance.
        observability_config = cdk.CfnResource(
            self,
            "RegainObservabilityConfig",
            type="AWS::BedrockAgentCore::Gateway",
            properties={
                "GatewayIdentifier": self.gateway.ref,
                "ObservabilityConfiguration": {
                    "Enabled": True,
                    "TraceConfiguration": {
                        "Enabled": True,
                        "ExportDestination": {
                            "CloudWatch": {
                                "LogGroupArn": trace_log_group.log_group_arn,
                            },
                        },
                        "OpenTelemetryProtocol": True,
                        "AutoCapturedSpans": [
                            "GatewayRouting",
                            "PolicyEvaluation",
                            "LambdaExecution",
                        ],
                    },
                },
            },
        )

        observability_config.add_dependency(self.gateway)

        cdk.Tags.of(observability_config).add("Project", "REGAIN")
        cdk.Tags.of(observability_config).add("Environment", "dev")

        # Export trace log group ARN for cross-stack reference.
        cdk.CfnOutput(
            self,
            "ObservabilityTraceLogGroupArn",
            value=trace_log_group.log_group_arn,
            export_name="RegainObservabilityTraceLogGroupArn",
            description="CloudWatch Log Group ARN for OpenTelemetry trace export",
        )

        self._trace_log_group = trace_log_group
        self._observability_config = observability_config

        return observability_config

    def create_dashboard(self) -> None:
        """Create REGAIN-Coaching-Operations CloudWatch dashboard.

        Defines a 3-row dashboard layout:
        - Top row: session count time series, active users counter, error rate gauge
        - Middle row: tool invocation heatmap, policy denial log table, token usage stacked area
        - Bottom row: latency percentile line charts, memory operation bar charts

        Widget region is omitted — CloudWatch defaults to the stack's deployment region.

        Requirements: 11.1, 11.2, 11.3, 11.4
        """
        import json

        namespace = "REGAIN/Coaching"
        policy_log_group = self._policy_audit_log_group.log_group_name

        # All 13 tool names for metric dimensions.
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

        # --- Top row: session count, active users, error rate ---

        session_count_widget = {
            "type": "metric",
            "x": 0,
            "y": 0,
            "width": 8,
            "height": 6,
            "properties": {
                "title": "Session Count",
                "metrics": [
                    [namespace, "SessionCount", "Period", "Daily", {"stat": "Sum", "label": "Daily Sessions"}],
                    [namespace, "SessionCount", "Period", "Weekly", {"stat": "Sum", "label": "Weekly Sessions"}],
                ],
                "view": "timeSeries",
                "period": 86400,
            },
        }

        active_users_widget = {
            "type": "metric",
            "x": 8,
            "y": 0,
            "width": 8,
            "height": 6,
            "properties": {
                "title": "Active Users",
                "metrics": [
                    [namespace, "ActiveUsers", {"stat": "Maximum", "label": "Active Users"}],
                ],
                "view": "singleValue",
                "period": 300,
            },
        }

        error_rate_widget = {
            "type": "metric",
            "x": 16,
            "y": 0,
            "width": 8,
            "height": 6,
            "properties": {
                "title": "Error Rate",
                "metrics": [
                    [namespace, "ErrorCount", {"stat": "Sum", "id": "errors", "visible": False}],
                    [namespace, "InvocationCount", {"stat": "Sum", "id": "total", "visible": False}],
                    [{"expression": "100 * errors / total", "label": "Error Rate %", "id": "rate"}],
                ],
                "view": "gauge",
                "yAxis": {"left": {"min": 0, "max": 100}},
                "period": 300,
            },
        }

        # --- Middle row: tool invocation heatmap, policy denial log, token usage ---

        tool_invocation_metrics = [
            [namespace, "ToolInvocationCount", "ToolName", name, {"stat": "Sum", "label": name}]
            for name in tool_names
        ]
        tool_invocation_widget = {
            "type": "metric",
            "x": 0,
            "y": 6,
            "width": 8,
            "height": 6,
            "properties": {
                "title": "Tool Invocations by Tool",
                "metrics": tool_invocation_metrics,
                "view": "timeSeries",
                "stacked": True,
                "period": 3600,
            },
        }

        policy_denial_widget = {
            "type": "log",
            "x": 8,
            "y": 6,
            "width": 8,
            "height": 6,
            "properties": {
                "title": "Policy Denials",
                "query": (
                    f"SOURCE '{policy_log_group}' "
                    "| filter evaluation_result = 'DENY' "
                    "| fields @timestamp, tool_name, userId, policy_name, denial_reason "
                    "| sort @timestamp desc "
                    "| limit 50"
                ),
                "view": "table",
            },
        }

        token_usage_widget = {
            "type": "metric",
            "x": 16,
            "y": 6,
            "width": 8,
            "height": 6,
            "properties": {
                "title": "Token Usage",
                "metrics": [
                    [namespace, "TokenUsage", "Direction", "Input", {"stat": "Sum", "label": "Input Tokens"}],
                    [namespace, "TokenUsage", "Direction", "Output", {"stat": "Sum", "label": "Output Tokens"}],
                ],
                "view": "timeSeries",
                "stacked": True,
                "period": 3600,
            },
        }

        # --- Bottom row: latency percentiles, memory operations ---

        latency_percentile_widget = {
            "type": "metric",
            "x": 0,
            "y": 12,
            "width": 12,
            "height": 6,
            "properties": {
                "title": "Tool Invocation Latency Percentiles",
                "metrics": [
                    [namespace, "ToolInvocationLatency", {"stat": "p50", "label": "p50"}],
                    [namespace, "ToolInvocationLatency", {"stat": "p95", "label": "p95"}],
                    [namespace, "ToolInvocationLatency", {"stat": "p99", "label": "p99"}],
                ],
                "view": "timeSeries",
                "period": 300,
            },
        }

        memory_ops_widget = {
            "type": "metric",
            "x": 12,
            "y": 12,
            "width": 12,
            "height": 6,
            "properties": {
                "title": "Memory Operations",
                "metrics": [
                    [namespace, "MemoryOperationCount", "Operation", "Read", {"stat": "Sum", "label": "Reads"}],
                    [namespace, "MemoryOperationCount", "Operation", "Write", {"stat": "Sum", "label": "Writes"}],
                    [namespace, "MemoryOperationLatency", "Operation", "Read", {"stat": "Average", "label": "Read Latency (ms)"}],
                    [namespace, "MemoryOperationLatency", "Operation", "Write", {"stat": "Average", "label": "Write Latency (ms)"}],
                ],
                "view": "bar",
                "period": 3600,
            },
        }

        dashboard_body = {
            "widgets": [
                # Top row
                session_count_widget,
                active_users_widget,
                error_rate_widget,
                # Middle row
                tool_invocation_widget,
                policy_denial_widget,
                token_usage_widget,
                # Bottom row
                latency_percentile_widget,
                memory_ops_widget,
            ],
        }

        dashboard = cdk.CfnResource(
            self,
            "RegainCoachingDashboard",
            type="AWS::CloudWatch::Dashboard",
            properties={
                "DashboardName": "REGAIN-Coaching-Operations",
                "DashboardBody": json.dumps(dashboard_body),
            },
        )

        cdk.Tags.of(dashboard).add("Project", "REGAIN")
        cdk.Tags.of(dashboard).add("Environment", "dev")

        self._dashboard = dashboard

    def create_alarms(self) -> None:
        """Create SNS topic and CloudWatch alarms for operational alerting.

        Creates:
        - SNS topic "RegainCoachingAlerts" for alarm notifications
        - Alarm 1: Error rate > 10% over 5-minute window
        - Alarm 2: p95 tool invocation latency > 5 seconds
        - Alarm 3: Policy denial count > 20 in 1-minute window

        Requirements: 12.1, 12.2, 12.3
        """
        namespace = "REGAIN/Coaching"

        # SNS topic for alarm notifications.
        self._alert_topic = sns.Topic(
            self,
            "RegainCoachingAlerts",
            topic_name="RegainCoachingAlerts",
            display_name="REGAIN Coaching Operational Alerts",
        )
        cdk.Tags.of(self._alert_topic).add("Project", "REGAIN")
        cdk.Tags.of(self._alert_topic).add("Environment", "dev")

        sns_action = cw_actions.SnsAction(self._alert_topic)

        # Alarm 1: Error rate > 10% over 5 minutes.
        # Uses a math expression: errors / total > 0.1
        error_count_metric = cloudwatch.Metric(
            namespace=namespace,
            metric_name="ErrorCount",
            statistic="Sum",
            period=cdk.Duration.minutes(5),
        )
        invocation_count_metric = cloudwatch.Metric(
            namespace=namespace,
            metric_name="InvocationCount",
            statistic="Sum",
            period=cdk.Duration.minutes(5),
        )
        error_rate_expr = cloudwatch.MathExpression(
            expression="IF(total > 0, errors / total, 0)",
            using_metrics={
                "errors": error_count_metric,
                "total": invocation_count_metric,
            },
            label="Error Rate",
            period=cdk.Duration.minutes(5),
        )
        error_rate_alarm = error_rate_expr.create_alarm(
            self,
            "RegainHighErrorRateAlarm",
            alarm_name="Regain-HighErrorRate",
            alarm_description="Coaching system error rate exceeds 10% over 5 minutes",
            threshold=0.1,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        error_rate_alarm.add_alarm_action(sns_action)
        cdk.Tags.of(error_rate_alarm).add("Project", "REGAIN")
        cdk.Tags.of(error_rate_alarm).add("Environment", "dev")

        # Alarm 2: p95 latency > 5 seconds (5000 ms).
        latency_metric = cloudwatch.Metric(
            namespace=namespace,
            metric_name="ToolInvocationLatency",
            statistic="p95",
            period=cdk.Duration.minutes(5),
        )
        latency_alarm = latency_metric.create_alarm(
            self,
            "RegainHighLatencyAlarm",
            alarm_name="Regain-HighLatency",
            alarm_description="p95 tool invocation latency exceeds 5 seconds",
            threshold=5000,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        latency_alarm.add_alarm_action(sns_action)
        cdk.Tags.of(latency_alarm).add("Project", "REGAIN")
        cdk.Tags.of(latency_alarm).add("Environment", "dev")

        # Alarm 3: Policy denial count > 20 in 1 minute.
        denial_metric = cloudwatch.Metric(
            namespace=namespace,
            metric_name="PolicyDenialCount",
            statistic="Sum",
            period=cdk.Duration.minutes(1),
        )
        denial_alarm = denial_metric.create_alarm(
            self,
            "RegainPolicyDenialSpikeAlarm",
            alarm_name="Regain-PolicyDenialSpike",
            alarm_description="Policy denial count exceeds 20 in 1 minute",
            threshold=20,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        denial_alarm.add_alarm_action(sns_action)
        cdk.Tags.of(denial_alarm).add("Project", "REGAIN")
        cdk.Tags.of(denial_alarm).add("Environment", "dev")
