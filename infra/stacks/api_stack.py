"""REGAIN API Stack — API Gateway, Lambda Functions, and IAM Roles."""
import aws_cdk as cdk
from aws_cdk import (
    aws_apigateway as apigw,
    aws_cognito as cognito,
    aws_dynamodb as dynamodb,
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
        }

    def _create_lambda_function(self, name: str, handler_path: str) -> _lambda.Function:
        """Create a single Lambda function.

        Args:
            name: Logical name for the function (e.g. "Onboarding").
            handler_path: Dotted handler path (e.g. "backend.lambda.onboarding.handler.lambda_handler").

        Returns:
            The Lambda function construct.
        """
        return _lambda.Function(
            self,
            f"Regain{name}Function",
            function_name=f"Regain{name}",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler=handler_path,
            code=_lambda.Code.from_asset("../backend"),
            environment=self._table_env(),
            timeout=cdk.Duration.seconds(30),
            memory_size=256,
        )

    def _create_lambda_functions(self) -> dict[str, _lambda.Function]:
        """Create all Lambda functions."""
        handlers = {
            "Onboarding": "lambda.onboarding.handler.lambda_handler",
            "Missions": "lambda.missions.handler.lambda_handler",
            "Evidence": "lambda.evidence.handler.lambda_handler",
            "Coaching": "lambda.coaching.handler.lambda_handler",
            "Dashboard": "lambda.dashboard.handler.lambda_handler",
        }
        return {
            name: self._create_lambda_function(name, path)
            for name, path in handlers.items()
        }

    def _grant_permissions(self, lambdas: dict[str, _lambda.Function]) -> None:
        """Grant least-privilege DynamoDB permissions to each Lambda.

        Each function only gets access to the tables it actually uses.
        """
        # Onboarding: writes to UserProfiles and Campaigns
        self.tables["UserProfiles"].grant_write_data(lambdas["Onboarding"])
        self.tables["Campaigns"].grant_write_data(lambdas["Onboarding"])

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

        cdk.CfnOutput(
            self,
            "ApiUrl",
            value=self.api.url,
            export_name="RegainApiUrl",
        )
