"""REGAIN Agent Stack — Coaching Agent infrastructure (WebSocket API, Voice Lambda, Bedrock permissions)."""
from pathlib import Path

import aws_cdk as cdk
from aws_cdk import (
    aws_apigatewayv2 as apigwv2,
    aws_apigatewayv2_integrations as apigwv2_integrations,
    aws_cognito as cognito,
    aws_dynamodb as dynamodb,
    aws_iam as iam,
    aws_lambda as _lambda,
    aws_logs as logs,
    aws_sns as sns,
)
from constructs import Construct

from .monitoring import add_lambda_alarms


class AgentStack(cdk.Stack):
    """Infrastructure for the REGAIN Coaching Agent: voice Lambda, WebSocket API, and Bedrock permissions."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        user_pool: cognito.UserPool,
        tables: dict[str, dynamodb.Table],
        coaching_lambda: _lambda.Function,
        resume_lambda_arn: str | None = None,
        resume_bucket_name: str | None = None,
        gateway_id: str | None = None,
        gateway_endpoint: str | None = None,
        memory_id: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.user_pool = user_pool
        self.tables = tables
        self.coaching_lambda = coaching_lambda
        self.resume_lambda_arn = resume_lambda_arn
        self.resume_bucket_name = resume_bucket_name
        self.gateway_id = gateway_id
        self.gateway_endpoint = gateway_endpoint
        self.memory_id = memory_id
        self.strands_layer = self._create_strands_layer()

        voice_lambda = self._create_voice_lambda()
        self._create_websocket_api(voice_lambda)
        self._grant_voice_lambda_permissions(voice_lambda)
        self._upgrade_coaching_lambda_permissions()

        chat_stream_lambda = self._create_chat_stream_lambda()
        self._create_chat_websocket_api(chat_stream_lambda)
        self._grant_chat_stream_lambda_permissions(chat_stream_lambda)

        self._create_monitoring(voice_lambda, chat_stream_lambda)

    def _create_strands_layer(self) -> _lambda.LayerVersion:
        """Create the Strands Agents Lambda Layer from the local build directory."""
        layer_path = Path(__file__).resolve().parent.parent / "layer_build"
        return _lambda.LayerVersion(
            self,
            "RegainStrandsAgentsLayer",
            code=_lambda.Code.from_asset(str(layer_path)),
            compatible_runtimes=[_lambda.Runtime.PYTHON_3_12],
            description="Strands Agents SDK for REGAIN Voice Lambda",
        )

    def _table_env(self) -> dict[str, str]:
        """Return environment variables mapping for all DynamoDB table names."""
        return {
            "USER_PROFILES_TABLE": self.tables["UserProfiles"].table_name,
            "CAMPAIGNS_TABLE": self.tables["Campaigns"].table_name,
            "MISSION_HISTORY_TABLE": self.tables["MissionHistory"].table_name,
            "EVIDENCE_VAULT_TABLE": self.tables["EvidenceVault"].table_name,
            "MARKET_DATA_TABLE": self.tables["MarketData"].table_name,
            "WS_CONNECTIONS_TABLE": self.tables["WebSocketConnections"].table_name,
        }

    def _bedrock_env(self) -> dict[str, str]:
        """Return Bedrock, AgentCore, and Gateway environment variables."""
        return {
            "BEDROCK_MODEL_ID": "amazon.nova-pro-v1:0",
            "NOVA_SONIC_MODEL_ID": "amazon.nova-2-sonic-v1:0",
            "AGENTCORE_MEMORY_ID": self.memory_id or "pending-memory-deploy",
            "AGENTCORE_MEMORY_NAMESPACE_PREFIX": "regain-coaching",
            "AWS_REGION_NAME": "us-east-1",
            "AGENTCORE_GATEWAY_ID": self.gateway_id or "pending-agentcore-deploy",
            "AGENTCORE_GATEWAY_ENDPOINT": self.gateway_endpoint or "pending-agentcore-deploy",
            "REGAIN_TRACING_ENABLED": "true",
            "USER_POOL_ID": self.user_pool.user_pool_id,
        }

    def _create_voice_lambda(self) -> _lambda.Function:
        """Create the Voice Session Lambda for WebSocket audio streaming."""
        env = {**self._table_env(), **self._bedrock_env()}

        return _lambda.Function(
            self,
            "RegainVoiceSessionFunction",
            function_name="RegainVoiceSession",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="backend.handlers.coaching.voice_handler.lambda_handler",
            code=_lambda.Code.from_asset(
                str(Path(__file__).resolve().parent.parent.parent),
                exclude=["frontend", "tests", "infra", ".venv", "node_modules", ".git", "_layer"],
            ),
            layers=[self.strands_layer],
            environment=env,
            timeout=cdk.Duration.seconds(120),
            memory_size=512,
            tracing=_lambda.Tracing.ACTIVE,
            log_retention=logs.RetentionDays.ONE_MONTH,
        )

    def _create_websocket_api(self, voice_lambda: _lambda.Function) -> None:
        """Create WebSocket API Gateway for voice sessions."""
        # Each route needs its own integration instance so CDK grants
        # API Gateway lambda:InvokeFunction permission for every route.
        connect_int = apigwv2_integrations.WebSocketLambdaIntegration(
            "RegainVoiceConnectInt", handler=voice_lambda,
        )
        default_int = apigwv2_integrations.WebSocketLambdaIntegration(
            "RegainVoiceDefaultInt", handler=voice_lambda,
        )
        disconnect_int = apigwv2_integrations.WebSocketLambdaIntegration(
            "RegainVoiceDisconnectInt", handler=voice_lambda,
        )

        self.websocket_api = apigwv2.WebSocketApi(
            self,
            "RegainVoiceWebSocketApi",
            api_name="RegainVoiceWebSocketApi",
            connect_route_options=apigwv2.WebSocketRouteOptions(integration=connect_int),
            default_route_options=apigwv2.WebSocketRouteOptions(integration=default_int),
            disconnect_route_options=apigwv2.WebSocketRouteOptions(integration=disconnect_int),
        )

        self.websocket_stage = apigwv2.WebSocketStage(
            self,
            "RegainVoiceProdStage",
            web_socket_api=self.websocket_api,
            stage_name="prod",
            auto_deploy=True,
        )

        cdk.CfnOutput(
            self,
            "WebSocketApiUrl",
            value=self.websocket_stage.url,
            export_name="RegainWebSocketApiUrl",
        )

        cdk.CfnOutput(
            self,
            "VoiceLambdaFunctionName",
            value=voice_lambda.function_name,
            export_name="RegainVoiceLambdaFunctionName",
        )

    def _bedrock_policy(self) -> iam.PolicyStatement:
        """Create IAM policy statement for Bedrock model invocation."""
        return iam.PolicyStatement(
            actions=[
                "bedrock:InvokeModel",
                "bedrock:InvokeModelWithResponseStream",
                "bedrock:InvokeModelWithBidirectionalStream",
            ],
            resources=[
                f"arn:aws:bedrock:{cdk.Aws.REGION}::foundation-model/amazon.nova-pro-v1:0",
                f"arn:aws:bedrock:{cdk.Aws.REGION}::foundation-model/amazon.nova-2-sonic-v1:0",
            ],
        )

    def _agentcore_memory_policy(self) -> iam.PolicyStatement:
        """Create IAM policy statement for AgentCore Memory operations."""
        return iam.PolicyStatement(
            actions=[
                "bedrock:CreateEvent",
                "bedrock:RetrieveMemoryRecords",
                "bedrock:ListMemoryRecords",
            ],
            resources=["*"],
        )

    def _agentcore_gateway_policy(self) -> iam.PolicyStatement:
        """Create IAM policy statement for AgentCore Gateway access."""
        return iam.PolicyStatement(
            actions=["bedrock:InvokeAgent", "bedrock:InvokeAgentCore"],
            resources=[f"arn:aws:bedrock:{cdk.Aws.REGION}:{cdk.Aws.ACCOUNT_ID}:gateway/*"],
        )

    def _grant_voice_lambda_permissions(self, voice_lambda: _lambda.Function) -> None:
        """Grant the Voice Lambda Bedrock, DynamoDB, and WebSocket management permissions."""
        voice_lambda.add_to_role_policy(self._bedrock_policy())
        voice_lambda.add_to_role_policy(self._agentcore_memory_policy())
        voice_lambda.add_to_role_policy(self._agentcore_gateway_policy())

        # Grant execute-api:ManageConnections so Lambda can call post_to_connection.
        voice_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["execute-api:ManageConnections"],
                resources=[
                    f"arn:aws:execute-api:{cdk.Aws.REGION}:{cdk.Aws.ACCOUNT_ID}:"
                    f"{self.websocket_api.api_id}/prod/POST/@connections/*"
                ],
            )
        )

        self.tables["UserProfiles"].grant_read_write_data(voice_lambda)
        self.tables["Campaigns"].grant_read_write_data(voice_lambda)
        self.tables["MissionHistory"].grant_read_write_data(voice_lambda)
        self.tables["EvidenceVault"].grant_read_write_data(voice_lambda)
        self.tables["MarketData"].grant_read_data(voice_lambda)
        self.tables["WebSocketConnections"].grant_read_write_data(voice_lambda)

        voice_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["cloudwatch:PutMetricData"],
                resources=["*"],
                conditions={"StringEquals": {"cloudwatch:namespace": "REGAIN/Business"}},
            )
        )

    def _upgrade_coaching_lambda_permissions(self) -> None:
        """Add Bedrock permissions and scoped DynamoDB access to the existing Coaching Lambda."""
        self.coaching_lambda.add_to_role_policy(self._bedrock_policy())
        self.coaching_lambda.add_to_role_policy(self._agentcore_memory_policy())
        self.coaching_lambda.add_to_role_policy(self._agentcore_gateway_policy())

        # Add Bedrock and AgentCore env vars to the coaching Lambda.
        # Gateway values use Fn.import_value() instead of CDK token references
        # to avoid cyclic dependency: coaching_lambda is owned by ApiStack, and
        # AgentCoreStack already depends on ApiStack for Lambda ARNs.
        cross_stack_keys = {"AGENTCORE_GATEWAY_ID", "AGENTCORE_GATEWAY_ENDPOINT", "AGENTCORE_MEMORY_ID"}
        for key, value in self._bedrock_env().items():
            if key not in cross_stack_keys:
                self.coaching_lambda.add_environment(key, value)

        # On bootstrap deploys (skip_alert_import=true), AgentCoreStack doesn't
        # exist yet so Fn::ImportValue would fail. Use sentinel values and
        # redeploy after AgentCoreStack is up.
        skip_bootstrap = self.node.try_get_context("skip_alert_import")
        if self.gateway_id and not skip_bootstrap:
            self.coaching_lambda.add_environment(
                "AGENTCORE_GATEWAY_ID",
                cdk.Fn.import_value("RegainAgentCoreGatewayId"),
            )
            self.coaching_lambda.add_environment(
                "AGENTCORE_GATEWAY_ENDPOINT",
                cdk.Fn.import_value("RegainAgentCoreGatewayEndpoint"),
            )
        else:
            self.coaching_lambda.add_environment(
                "AGENTCORE_GATEWAY_ID", "pending-agentcore-deploy",
            )
            self.coaching_lambda.add_environment(
                "AGENTCORE_GATEWAY_ENDPOINT", "pending-agentcore-deploy",
            )

        if self.memory_id and not skip_bootstrap:
            self.coaching_lambda.add_environment(
                "AGENTCORE_MEMORY_ID",
                cdk.Fn.import_value("RegainAgentCoreMemoryId"),
            )
        else:
            self.coaching_lambda.add_environment(
                "AGENTCORE_MEMORY_ID", "pending-memory-deploy",
            )

        # Grant scoped DynamoDB access (upgrades from read-only on UserProfiles)
        self.tables["UserProfiles"].grant_read_write_data(self.coaching_lambda)
        self.tables["Campaigns"].grant_read_write_data(self.coaching_lambda)
        self.tables["MissionHistory"].grant_read_write_data(self.coaching_lambda)
        self.tables["EvidenceVault"].grant_read_write_data(self.coaching_lambda)
        self.tables["MarketData"].grant_read_data(self.coaching_lambda)

        # Wire Resume Lambda + S3 bucket so coaching tools can invoke resume generation.
        # Uses string ARNs and inline IAM policies (not construct references) to avoid
        # a cyclic dependency: ResumeStack → ApiStack (for api) and ApiStack → ResumeStack.
        if self.resume_lambda_arn:
            self.coaching_lambda.add_environment(
                "RESUME_LAMBDA_ARN", self.resume_lambda_arn
            )
            self.coaching_lambda.add_to_role_policy(
                iam.PolicyStatement(
                    actions=["lambda:InvokeFunction"],
                    resources=[self.resume_lambda_arn],
                )
            )
        if self.resume_bucket_name:
            self.coaching_lambda.add_environment(
                "RESUME_BUCKET_NAME", self.resume_bucket_name
            )
            bucket_arn = f"arn:aws:s3:::{self.resume_bucket_name}"
            self.coaching_lambda.add_to_role_policy(
                iam.PolicyStatement(
                    actions=["s3:GetObject", "s3:GetBucketLocation", "s3:ListBucket"],
                    resources=[bucket_arn, f"{bucket_arn}/*"],
                )
            )

    # ------------------------------------------------------------------
    # Chat Streaming (WebSocket text-based coaching)
    # ------------------------------------------------------------------

    def _create_chat_stream_lambda(self) -> _lambda.Function:
        """Create the Chat Streaming Lambda for WebSocket text coaching."""
        env = {**self._table_env(), **self._bedrock_env()}

        return _lambda.Function(
            self,
            "RegainChatStreamFunction",
            function_name="RegainChatStream",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="backend.handlers.coaching.stream_handler.lambda_handler",
            code=_lambda.Code.from_asset(
                str(Path(__file__).resolve().parent.parent.parent),
                exclude=["frontend", "tests", "infra", ".venv", "node_modules", ".git", "_layer"],
            ),
            layers=[self.strands_layer],
            environment=env,
            timeout=cdk.Duration.seconds(120),
            memory_size=512,
            tracing=_lambda.Tracing.ACTIVE,
            log_retention=logs.RetentionDays.ONE_MONTH,
        )

    def _create_chat_websocket_api(self, chat_stream_lambda: _lambda.Function) -> None:
        """Create WebSocket API Gateway for chat streaming sessions."""
        chat_connect_int = apigwv2_integrations.WebSocketLambdaIntegration(
            "RegainChatConnectInt", handler=chat_stream_lambda,
        )
        chat_default_int = apigwv2_integrations.WebSocketLambdaIntegration(
            "RegainChatDefaultInt", handler=chat_stream_lambda,
        )
        chat_disconnect_int = apigwv2_integrations.WebSocketLambdaIntegration(
            "RegainChatDisconnectInt", handler=chat_stream_lambda,
        )

        self.chat_websocket_api = apigwv2.WebSocketApi(
            self,
            "RegainChatWebSocketApi",
            api_name="RegainChatWebSocketApi",
            connect_route_options=apigwv2.WebSocketRouteOptions(integration=chat_connect_int),
            default_route_options=apigwv2.WebSocketRouteOptions(integration=chat_default_int),
            disconnect_route_options=apigwv2.WebSocketRouteOptions(integration=chat_disconnect_int),
        )

        self.chat_websocket_stage = apigwv2.WebSocketStage(
            self,
            "RegainChatProdStage",
            web_socket_api=self.chat_websocket_api,
            stage_name="prod",
            auto_deploy=True,
        )

        cdk.CfnOutput(
            self,
            "ChatWebSocketApiUrl",
            value=self.chat_websocket_stage.url,
            export_name="RegainChatWebSocketApiUrl",
        )

    def _grant_chat_stream_lambda_permissions(self, chat_stream_lambda: _lambda.Function) -> None:
        """Grant the Chat Stream Lambda Bedrock, DynamoDB, and WebSocket management permissions."""
        chat_stream_lambda.add_to_role_policy(self._bedrock_policy())
        chat_stream_lambda.add_to_role_policy(self._agentcore_memory_policy())
        chat_stream_lambda.add_to_role_policy(self._agentcore_gateway_policy())

        # Grant execute-api:ManageConnections so Lambda can call post_to_connection.
        chat_stream_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["execute-api:ManageConnections"],
                resources=[
                    f"arn:aws:execute-api:{cdk.Aws.REGION}:{cdk.Aws.ACCOUNT_ID}:"
                    f"{self.chat_websocket_api.api_id}/prod/POST/@connections/*"
                ],
            )
        )

        self.tables["UserProfiles"].grant_read_write_data(chat_stream_lambda)
        self.tables["Campaigns"].grant_read_write_data(chat_stream_lambda)
        self.tables["MissionHistory"].grant_read_write_data(chat_stream_lambda)
        self.tables["EvidenceVault"].grant_read_write_data(chat_stream_lambda)
        self.tables["MarketData"].grant_read_data(chat_stream_lambda)
        self.tables["WebSocketConnections"].grant_read_write_data(chat_stream_lambda)

        # CloudWatch PutMetricData for business metrics
        chat_stream_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["cloudwatch:PutMetricData"],
                resources=["*"],
                conditions={
                    "StringEquals": {"cloudwatch:namespace": "REGAIN/Business"},
                },
            )
        )

        # CloudWatch PutMetricData for coaching operational metrics
        chat_stream_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["cloudwatch:PutMetricData"],
                resources=["*"],
                conditions={
                    "StringEquals": {"cloudwatch:namespace": "REGAIN/Coaching"},
                },
            )
        )

    def _create_monitoring(
        self,
        voice_lambda: _lambda.Function,
        chat_stream_lambda: _lambda.Function,
    ) -> None:
        """Add CloudWatch alarms for agent Lambda functions."""
        alert_topic = sns.Topic.from_topic_arn(
            self, "ImportedAlertTopic",
            cdk.Fn.import_value("RegainAlertSnsTopicArn"),
        )
        add_lambda_alarms(self, voice_lambda, alert_topic, name="VoiceSession", timeout_seconds=120)
        add_lambda_alarms(self, chat_stream_lambda, alert_topic, name="ChatStream", timeout_seconds=120)
