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
)
from constructs import Construct


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
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.user_pool = user_pool
        self.tables = tables
        self.coaching_lambda = coaching_lambda
        self.strands_layer = self._create_strands_layer()

        voice_lambda = self._create_voice_lambda()
        self._create_websocket_api(voice_lambda)
        self._grant_voice_lambda_permissions(voice_lambda)
        self._upgrade_coaching_lambda_permissions()

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
        }

    def _bedrock_env(self) -> dict[str, str]:
        """Return Bedrock, AgentCore, and Gateway environment variables."""
        return {
            "BEDROCK_MODEL_ID": "amazon.nova-lite-v1:0",
            "NOVA_SONIC_MODEL_ID": "amazon.nova-sonic-v1:0",
            "AGENTCORE_MEMORY_ID": "regain-coaching-memory",
            "AGENTCORE_MEMORY_NAMESPACE_PREFIX": "regain-coaching",
            "AWS_REGION_NAME": "us-east-1",
            "AGENTCORE_GATEWAY_ID": "pending-agentcore-deploy",
            "AGENTCORE_GATEWAY_ENDPOINT": "pending-agentcore-deploy",
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
        )

    def _create_websocket_api(self, voice_lambda: _lambda.Function) -> None:
        """Create WebSocket API Gateway for voice sessions."""
        integration = apigwv2_integrations.WebSocketLambdaIntegration(
            "RegainVoiceIntegration",
            handler=voice_lambda,
        )

        self.websocket_api = apigwv2.WebSocketApi(
            self,
            "RegainVoiceWebSocketApi",
            api_name="RegainVoiceWebSocketApi",
            connect_route_options=apigwv2.WebSocketRouteOptions(integration=integration),
            default_route_options=apigwv2.WebSocketRouteOptions(integration=integration),
            disconnect_route_options=apigwv2.WebSocketRouteOptions(integration=integration),
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
            resources=["arn:aws:bedrock:*:*:*"],
        )

    def _agentcore_memory_policy(self) -> iam.PolicyStatement:
        """Create IAM policy statement for AgentCore Memory operations."""
        return iam.PolicyStatement(
            actions=[
                "bedrock:RetrieveMemory",
                "bedrock:CreateMemory",
            ],
            resources=["*"],
        )

    def _grant_voice_lambda_permissions(self, voice_lambda: _lambda.Function) -> None:
        """Grant the Voice Lambda Bedrock and DynamoDB permissions."""
        voice_lambda.add_to_role_policy(self._bedrock_policy())
        voice_lambda.add_to_role_policy(self._agentcore_memory_policy())

        for table in self.tables.values():
            table.grant_read_write_data(voice_lambda)

    def _upgrade_coaching_lambda_permissions(self) -> None:
        """Add Bedrock permissions and full DynamoDB access to the existing Coaching Lambda."""
        self.coaching_lambda.add_to_role_policy(self._bedrock_policy())
        self.coaching_lambda.add_to_role_policy(self._agentcore_memory_policy())

        # Add Bedrock and AgentCore env vars to the coaching Lambda
        for key, value in self._bedrock_env().items():
            self.coaching_lambda.add_environment(key, value)

        # Grant read/write on all tables (upgrades from read-only on UserProfiles)
        for table in self.tables.values():
            table.grant_read_write_data(self.coaching_lambda)
