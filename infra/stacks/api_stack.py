"""REGAIN API Stack — API Gateway, Lambda Functions, and IAM Roles."""
from pathlib import Path

import aws_cdk as cdk
from aws_cdk import (
    aws_apigateway as apigw,
    aws_cognito as cognito,
    aws_dynamodb as dynamodb,
    aws_iam as iam,
    aws_lambda as _lambda,
)
from constructs import Construct


class ApiStack(cdk.Stack):
    """REST API Gateway with Lambda integrations for REGAIN platform."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        user_pool: cognito.UserPool,
        tables: dict[str, dynamodb.Table],
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.user_pool = user_pool
        self.tables = tables

        authorizer = self._create_cognito_authorizer()
        lambdas = self._create_lambda_functions()
        self._grant_permissions(lambdas)
        self._create_api(authorizer, lambdas)

        # Expose Lambda functions for cross-stack references
        self.coaching_lambda = lambdas["Coaching"]
        self.missions_lambda = lambdas["Missions"]
        self.evidence_lambda = lambdas["Evidence"]
        self.dashboard_lambda = lambdas["Dashboard"]

    def _create_cognito_authorizer(self) -> apigw.CognitoUserPoolsAuthorizer:
        """Create Cognito authorizer for API Gateway."""
        return apigw.CognitoUserPoolsAuthorizer(
            self,
            "RegainCognitoAuthorizer",
            authorizer_name="RegainCognitoAuthorizer",
            cognito_user_pools=[self.user_pool],
        )

    def _table_env(self) -> dict[str, str]:
        """Return environment variables mapping for all DynamoDB table names."""
        return {
            "USER_PROFILES_TABLE": self.tables["UserProfiles"].table_name,
            "CAMPAIGNS_TABLE": self.tables["Campaigns"].table_name,
            "MISSION_HISTORY_TABLE": self.tables["MissionHistory"].table_name,
            "EVIDENCE_VAULT_TABLE": self.tables["EvidenceVault"].table_name,
            "MARKET_DATA_TABLE": self.tables["MarketData"].table_name,
            "USER_POOL_ID": self.user_pool.user_pool_id,
        }

    def _create_lambda_function(self, name: str, handler_path: str) -> _lambda.Function:
        """Create a single Lambda function.

        Args:
            name: Logical name for the function (e.g. "Onboarding").
            handler_path: Dotted handler path (e.g. "backend.handlers.onboarding.handler.lambda_handler").

        Returns:
            The Lambda function construct.
        """
        return _lambda.Function(
            self,
            f"Regain{name}Function",
            function_name=f"Regain{name}",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler=handler_path,
            code=_lambda.Code.from_asset(
                str(Path(__file__).resolve().parent.parent.parent),
                exclude=["frontend", "tests", "infra", ".venv", "node_modules", ".git", "_layer"],
            ),
            environment=self._table_env(),
            timeout=cdk.Duration.seconds(30),
            memory_size=256,
        )

    def _create_lambda_functions(self) -> dict[str, _lambda.Function]:
        """Create all Lambda functions."""
        handlers = {
            "Onboarding": "backend.handlers.onboarding.handler.lambda_handler",
            "Missions": "backend.handlers.missions.handler.lambda_handler",
            "Evidence": "backend.handlers.evidence.handler.lambda_handler",
            "Coaching": "backend.handlers.coaching.handler.lambda_handler",
            "Dashboard": "backend.handlers.dashboard.handler.lambda_handler",
            "Profile": "backend.handlers.profile.handler.lambda_handler",
        }
        return {
            name: self._create_lambda_function(name, path)
            for name, path in handlers.items()
        }

    def _grant_permissions(self, lambdas: dict[str, _lambda.Function]) -> None:
        """Grant least-privilege DynamoDB permissions to each Lambda.

        Each function only gets access to the tables it actually uses.
        """
        # Onboarding: read/write UserProfiles and Campaigns + mission seeding
        # needs read/write MissionHistory, read EvidenceVault and MarketData
        self.tables["UserProfiles"].grant_read_write_data(lambdas["Onboarding"])
        self.tables["Campaigns"].grant_read_write_data(lambdas["Onboarding"])
        self.tables["MissionHistory"].grant_read_write_data(lambdas["Onboarding"])
        self.tables["EvidenceVault"].grant_read_data(lambdas["Onboarding"])
        self.tables["MarketData"].grant_read_data(lambdas["Onboarding"])

        # Missions: read/write MissionHistory, write EvidenceVault, read Campaigns
        self.tables["MissionHistory"].grant_read_write_data(lambdas["Missions"])
        self.tables["EvidenceVault"].grant_write_data(lambdas["Missions"])
        self.tables["Campaigns"].grant_read_data(lambdas["Missions"])

        # Evidence: read EvidenceVault
        self.tables["EvidenceVault"].grant_read_data(lambdas["Evidence"])

        # Coaching: read UserProfiles
        self.tables["UserProfiles"].grant_read_data(lambdas["Coaching"])

        # Dashboard: read Campaigns, MissionHistory, EvidenceVault
        self.tables["Campaigns"].grant_read_data(lambdas["Dashboard"])
        self.tables["MissionHistory"].grant_read_data(lambdas["Dashboard"])
        self.tables["EvidenceVault"].grant_read_data(lambdas["Dashboard"])

        # Profile: read/write all user tables (for cascade delete) + Cognito
        self.tables["UserProfiles"].grant_read_write_data(lambdas["Profile"])
        self.tables["Campaigns"].grant_read_write_data(lambdas["Profile"])
        self.tables["MissionHistory"].grant_read_write_data(lambdas["Profile"])
        self.tables["EvidenceVault"].grant_read_write_data(lambdas["Profile"])
        lambdas["Profile"].add_to_role_policy(
            iam.PolicyStatement(
                actions=["cognito-idp:AdminDeleteUser"],
                resources=[self.user_pool.user_pool_arn],
            )
        )

    def _create_api(
        self,
        authorizer: apigw.CognitoUserPoolsAuthorizer,
        lambdas: dict[str, _lambda.Function],
    ) -> None:
        """Create REST API with resources, methods, and CORS."""
        self.api = apigw.RestApi(
            self,
            "RegainApi",
            rest_api_name="RegainApi",
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS,
                allow_methods=apigw.Cors.ALL_METHODS,
                allow_headers=["Content-Type", "Authorization"],
            ),
        )

        auth_kwargs = {
            "authorizer": authorizer,
            "authorization_type": apigw.AuthorizationType.COGNITO,
        }

        # POST /onboarding
        onboarding = self.api.root.add_resource("onboarding")
        onboarding.add_method(
            "POST",
            apigw.LambdaIntegration(lambdas["Onboarding"]),
            **auth_kwargs,
        )

        # GET /missions
        missions = self.api.root.add_resource("missions")
        missions.add_method(
            "GET",
            apigw.LambdaIntegration(lambdas["Missions"]),
            **auth_kwargs,
        )

        # POST /missions/{missionId}/complete
        mission_id = missions.add_resource("{missionId}")
        complete = mission_id.add_resource("complete")
        complete.add_method(
            "POST",
            apigw.LambdaIntegration(lambdas["Missions"]),
            **auth_kwargs,
        )

        # GET /evidence
        evidence = self.api.root.add_resource("evidence")
        evidence.add_method(
            "GET",
            apigw.LambdaIntegration(lambdas["Evidence"]),
            **auth_kwargs,
        )

        # POST /coaching/checkin
        coaching = self.api.root.add_resource("coaching")
        checkin = coaching.add_resource("checkin")
        checkin.add_method(
            "POST",
            apigw.LambdaIntegration(lambdas["Coaching"]),
            **auth_kwargs,
        )

        # GET /dashboard
        dashboard = self.api.root.add_resource("dashboard")
        dashboard.add_method(
            "GET",
            apigw.LambdaIntegration(lambdas["Dashboard"]),
            **auth_kwargs,
        )

        # DELETE /profile
        profile = self.api.root.add_resource("profile")
        profile.add_method(
            "DELETE",
            apigw.LambdaIntegration(lambdas["Profile"]),
            **auth_kwargs,
        )

        # Ensure 4xx/5xx gateway responses include CORS headers so the
        # browser doesn't block error responses (e.g. Cognito 401).
        for suffix, response_type in [
            ("4xx", apigw.ResponseType.DEFAULT_4_XX),
            ("5xx", apigw.ResponseType.DEFAULT_5_XX),
        ]:
            self.api.add_gateway_response(
                f"CorsGateway{suffix}",
                type=response_type,
                response_headers={
                    "Access-Control-Allow-Origin": "'*'",
                    "Access-Control-Allow-Headers": "'Content-Type,Authorization'",
                    "Access-Control-Allow-Methods": "'GET,POST,PUT,DELETE,OPTIONS'",
                },
            )

        cdk.CfnOutput(
            self,
            "ApiUrl",
            value=self.api.url,
            export_name="RegainApiUrl",
        )
