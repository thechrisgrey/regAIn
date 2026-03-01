"""REGAIN Voice Practice Stack — S3 Bucket, WebSocket + REST Lambdas, and API Gateway Routes."""
from pathlib import Path

import aws_cdk as cdk
from aws_cdk import (
    aws_apigateway as apigw,
    aws_apigatewayv2 as apigwv2,
    aws_apigatewayv2_integrations as apigwv2_integrations,
    aws_cognito as cognito,
    aws_dynamodb as dynamodb,
    aws_iam as iam,
    aws_lambda as _lambda,
    aws_s3 as s3,
    aws_sns as sns,
)
from constructs import Construct

from .monitoring import add_lambda_alarms


class VoicePracticeStack(cdk.Stack):
    """Voice practice infrastructure: S3 bucket, WebSocket + REST Lambdas, and API routes."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        user_pool: cognito.UserPool,
        tables: dict[str, dynamodb.Table],
        api: apigw.RestApi,
        profile_lambda: _lambda.Function,
        env: cdk.Environment,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, env=env, **kwargs)

        self.user_pool = user_pool
        self.tables = tables
        self.profile_lambda = profile_lambda

        self.bucket = self._create_bucket()
        self.strands_layer = self._create_strands_layer()
        self.ws_lambda = self._create_ws_lambda()
        self._create_ws_api()
        self.rest_lambda = self._create_rest_lambda()
        self._create_api_routes(api)
        self._grant_permissions()
        self._grant_profile_lambda_permissions()
        self._create_monitoring()
        self._create_outputs()

    def _table_env(self) -> dict[str, str]:
        """Return environment variables mapping for all DynamoDB table names."""
        return {
            "USER_PROFILES_TABLE": self.tables["UserProfiles"].table_name,
            "CAMPAIGNS_TABLE": self.tables["Campaigns"].table_name,
            "MISSION_HISTORY_TABLE": self.tables["MissionHistory"].table_name,
            "EVIDENCE_VAULT_TABLE": self.tables["EvidenceVault"].table_name,
            "MARKET_DATA_TABLE": self.tables["MarketData"].table_name,
            "VOICE_SESSIONS_TABLE": self.tables["VoiceSessions"].table_name,
            "WS_CONNECTIONS_TABLE": self.tables["WebSocketConnections"].table_name,
        }

    def _create_bucket(self) -> s3.Bucket:
        """Create the Voice Practice S3 bucket with versioning and public access blocked."""
        return s3.Bucket(
            self,
            "RegainVoicePracticeBucket",
            bucket_name=f"regain-voice-practice-{cdk.Aws.ACCOUNT_ID}",
            versioned=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=cdk.RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

    def _create_strands_layer(self) -> _lambda.LayerVersion:
        """Create the Strands Agents Lambda Layer from the local build directory."""
        layer_path = Path(__file__).resolve().parent.parent / "layer_build"
        return _lambda.LayerVersion(
            self,
            "RegainStrandsAgentsLayer",
            code=_lambda.Code.from_asset(str(layer_path)),
            compatible_runtimes=[_lambda.Runtime.PYTHON_3_12],
            description="Strands Agents SDK for REGAIN Voice Practice Lambda",
        )

    def _create_ws_lambda(self) -> _lambda.Function:
        """Create the WebSocket Lambda for voice practice sessions."""
        env = {
            **self._table_env(),
            "VOICE_PRACTICE_BUCKET_NAME": self.bucket.bucket_name,
            "BEDROCK_MODEL_ID": "amazon.nova-lite-v1:0",
            "NOVA_SONIC_MODEL_ID": "amazon.nova-2-sonic-v1:0",
            "AGENTCORE_MEMORY_ID": "regain-coaching-memory",
            "AGENTCORE_MEMORY_NAMESPACE_PREFIX": "regain-coaching",
            "AWS_REGION_NAME": "us-east-1",
        }

        return _lambda.Function(
            self,
            "RegainVoicePracticeFunction",
            function_name="RegainVoicePractice",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="backend.handlers.voice_practice.ws_handler.lambda_handler",
            code=_lambda.Code.from_asset(
                str(Path(__file__).resolve().parent.parent.parent),
                exclude=["frontend", "tests", "infra", ".venv", "node_modules", ".git", "_layer"],
            ),
            layers=[self.strands_layer],
            environment=env,
            timeout=cdk.Duration.seconds(120),
            memory_size=512,
            reserved_concurrent_executions=30,
        )

    def _create_ws_api(self) -> None:
        """Create WebSocket API Gateway for voice practice sessions."""
        # Each route needs its own integration instance so CDK grants
        # API Gateway lambda:InvokeFunction permission for every route.
        connect_integration = apigwv2_integrations.WebSocketLambdaIntegration(
            "RegainVPConnectIntegration", handler=self.ws_lambda,
        )
        default_integration = apigwv2_integrations.WebSocketLambdaIntegration(
            "RegainVPDefaultIntegration", handler=self.ws_lambda,
        )
        disconnect_integration = apigwv2_integrations.WebSocketLambdaIntegration(
            "RegainVPDisconnectIntegration", handler=self.ws_lambda,
        )

        self.websocket_api = apigwv2.WebSocketApi(
            self,
            "RegainVoicePracticeWebSocketApi",
            api_name="RegainVoicePracticeWebSocketApi",
            connect_route_options=apigwv2.WebSocketRouteOptions(integration=connect_integration),
            default_route_options=apigwv2.WebSocketRouteOptions(integration=default_integration),
            disconnect_route_options=apigwv2.WebSocketRouteOptions(integration=disconnect_integration),
        )

        self.websocket_stage = apigwv2.WebSocketStage(
            self,
            "RegainVoicePracticeProdStage",
            web_socket_api=self.websocket_api,
            stage_name="prod",
            auto_deploy=True,
        )

    def _create_rest_lambda(self) -> _lambda.Function:
        """Create the REST API Lambda for voice practice session queries."""
        env = {
            **self._table_env(),
            "VOICE_PRACTICE_BUCKET_NAME": self.bucket.bucket_name,
        }

        return _lambda.Function(
            self,
            "RegainVoicePracticeApiFunction",
            function_name="RegainVoicePracticeApi",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="backend.handlers.voice_practice.api_handler.lambda_handler",
            code=_lambda.Code.from_asset(
                str(Path(__file__).resolve().parent.parent.parent),
                exclude=["frontend", "tests", "infra", ".venv", "node_modules", ".git", "_layer"],
            ),
            environment=env,
            timeout=cdk.Duration.seconds(30),
            memory_size=256,
        )

    def _create_api_routes(self, api: apigw.RestApi) -> None:
        """Add GET /voice-sessions and GET /voice-sessions/{sessionId} routes.

        Uses L1 (Cfn) constructs to avoid a cyclic cross-stack dependency.
        """
        rest_api_id = api.rest_api_id
        root_resource_id = api.rest_api_root_resource_id

        # Authorizer
        authorizer = apigw.CfnAuthorizer(
            self,
            "RegainVoicePracticeAuthorizer",
            name="RegainVoicePracticeAuthorizer",
            rest_api_id=rest_api_id,
            type="COGNITO_USER_POOLS",
            identity_source="method.request.header.Authorization",
            provider_arns=[self.user_pool.user_pool_arn],
        )

        # /voice-sessions resource
        sessions_resource = apigw.CfnResource(
            self,
            "VoiceSessionsApiResource",
            rest_api_id=rest_api_id,
            parent_id=root_resource_id,
            path_part="voice-sessions",
        )

        # /voice-sessions/{sessionId} resource
        session_id_resource = apigw.CfnResource(
            self,
            "VoiceSessionIdApiResource",
            rest_api_id=rest_api_id,
            parent_id=sessions_resource.ref,
            path_part="{sessionId}",
        )

        # Lambda invoke permission for API Gateway
        self.rest_lambda.add_permission(
            "ApiGatewayInvoke",
            principal=iam.ServicePrincipal("apigateway.amazonaws.com"),
            source_arn=f"arn:aws:execute-api:{cdk.Aws.REGION}:{cdk.Aws.ACCOUNT_ID}:{rest_api_id}/*",
        )

        integration_uri = (
            f"arn:aws:apigateway:{cdk.Aws.REGION}:lambda:path"
            f"/2015-03-31/functions/{self.rest_lambda.function_arn}/invocations"
        )

        for method_id, resource_id, http_method in [
            ("VoiceSessionsGetMethod", sessions_resource.ref, "GET"),
            ("VoiceSessionIdGetMethod", session_id_resource.ref, "GET"),
        ]:
            apigw.CfnMethod(
                self,
                method_id,
                rest_api_id=rest_api_id,
                resource_id=resource_id,
                http_method=http_method,
                authorization_type="COGNITO_USER_POOLS",
                authorizer_id=authorizer.ref,
                integration=apigw.CfnMethod.IntegrationProperty(
                    type="AWS_PROXY",
                    integration_http_method="POST",
                    uri=integration_uri,
                ),
            )

        # CORS OPTIONS methods for L1 resources (not covered by default_cors_preflight_options)
        cors_response_params = {
            "method.response.header.Access-Control-Allow-Headers": "'Content-Type,Authorization'",
            "method.response.header.Access-Control-Allow-Methods": "'GET,POST,PUT,DELETE,OPTIONS'",
            "method.response.header.Access-Control-Allow-Origin": "'https://regain.altivum.ai'",
        }
        cors_method_response_params = {
            "method.response.header.Access-Control-Allow-Headers": True,
            "method.response.header.Access-Control-Allow-Methods": True,
            "method.response.header.Access-Control-Allow-Origin": True,
        }
        for options_id, resource_id in [
            ("VoiceSessionsOptionsMethod", sessions_resource.ref),
            ("VoiceSessionIdOptionsMethod", session_id_resource.ref),
        ]:
            apigw.CfnMethod(
                self,
                options_id,
                rest_api_id=rest_api_id,
                resource_id=resource_id,
                http_method="OPTIONS",
                authorization_type="NONE",
                integration=apigw.CfnMethod.IntegrationProperty(
                    type="MOCK",
                    request_templates={"application/json": '{"statusCode": 200}'},
                    integration_responses=[
                        apigw.CfnMethod.IntegrationResponseProperty(
                            status_code="200",
                            response_parameters=cors_response_params,
                        )
                    ],
                ),
                method_responses=[
                    apigw.CfnMethod.MethodResponseProperty(
                        status_code="200",
                        response_parameters=cors_method_response_params,
                    )
                ],
            )

    def _grant_permissions(self) -> None:
        """Grant least-privilege IAM permissions to the WS and REST Lambdas."""
        # WS Lambda: Bedrock
        self.ws_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                    "bedrock:InvokeModelWithBidirectionalStream",
                ],
                resources=[
                    f"arn:aws:bedrock:{cdk.Aws.REGION}::foundation-model/amazon.nova-lite-v1:0",
                    f"arn:aws:bedrock:{cdk.Aws.REGION}::foundation-model/amazon.nova-2-sonic-v1:0",
                ],
            )
        )

        # WS Lambda: AgentCore Memory
        self.ws_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock:RetrieveMemory",
                    "bedrock:CreateMemory",
                ],
                resources=["*"],
            )
        )

        # WS Lambda: S3 read/write on bucket
        self.bucket.grant_read_write(self.ws_lambda)

        # WS Lambda: DynamoDB permissions
        self.tables["WebSocketConnections"].grant_read_write_data(self.ws_lambda)
        self.tables["VoiceSessions"].grant_read_write_data(self.ws_lambda)
        self.tables["UserProfiles"].grant_read_data(self.ws_lambda)
        self.tables["Campaigns"].grant_read_data(self.ws_lambda)
        self.tables["MissionHistory"].grant_read_data(self.ws_lambda)

        # WS Lambda: WebSocket management (post_to_connection)
        self.ws_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["execute-api:ManageConnections"],
                resources=[
                    f"arn:aws:execute-api:{cdk.Aws.REGION}:{cdk.Aws.ACCOUNT_ID}:"
                    f"{self.websocket_api.api_id}/prod/POST/@connections/*"
                ],
            )
        )

        # REST Lambda: S3 read on bucket
        self.bucket.grant_read(self.rest_lambda)

        # REST Lambda: VoiceSessions read
        self.tables["VoiceSessions"].grant_read_data(self.rest_lambda)

    def _grant_profile_lambda_permissions(self) -> None:
        """Grant the Profile Lambda permissions for voice practice cascade delete.

        Uses a constructed ARN from the known bucket name to avoid
        cyclic cross-stack references (VoicePracticeStack ↔ ApiStack).
        """
        self.tables["VoiceSessions"].grant_read_write_data(self.profile_lambda)

        # Construct the bucket ARN from the known name to break the
        # VoicePracticeStack ↔ ApiStack cyclic dependency.
        bucket_name = f"regain-voice-practice-{cdk.Aws.ACCOUNT_ID}"
        bucket_arn = f"arn:aws:s3:::{bucket_name}"
        self.profile_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["s3:GetObject", "s3:ListBucket", "s3:DeleteObject"],
                resources=[bucket_arn, f"{bucket_arn}/*"],
            )
        )

        # Add env vars to the profile lambda
        self.profile_lambda.add_environment(
            "VOICE_SESSIONS_TABLE", self.tables["VoiceSessions"].table_name,
        )
        self.profile_lambda.add_environment(
            "VOICE_PRACTICE_BUCKET_NAME", bucket_name,
        )

    def _create_monitoring(self) -> None:
        """Add CloudWatch alarms for voice practice Lambda functions."""
        alert_topic = sns.Topic.from_topic_arn(
            self, "ImportedAlertTopic",
            cdk.Fn.import_value("RegainAlertSnsTopicArn"),
        )
        add_lambda_alarms(self, self.ws_lambda, alert_topic, name="VoicePractice", timeout_seconds=120)
        add_lambda_alarms(self, self.rest_lambda, alert_topic, name="VoicePracticeApi", timeout_seconds=30)

    def _create_outputs(self) -> None:
        """Create CloudFormation outputs for voice practice infrastructure."""
        cdk.CfnOutput(
            self,
            "VoicePracticeBucketName",
            value=self.bucket.bucket_name,
            export_name="RegainVoicePracticeBucketName",
        )
        cdk.CfnOutput(
            self,
            "VoicePracticeBucketArn",
            value=self.bucket.bucket_arn,
            export_name="RegainVoicePracticeBucketArn",
        )
        cdk.CfnOutput(
            self,
            "VoicePracticeWsLambdaArn",
            value=self.ws_lambda.function_arn,
            export_name="RegainVoicePracticeWsLambdaArn",
        )
        cdk.CfnOutput(
            self,
            "VoicePracticeWebSocketApiUrl",
            value=self.websocket_stage.url,
            export_name="RegainVoicePracticeWebSocketApiUrl",
        )
        cdk.CfnOutput(
            self,
            "VoicePracticeRestLambdaArn",
            value=self.rest_lambda.function_arn,
            export_name="RegainVoicePracticeRestLambdaArn",
        )
