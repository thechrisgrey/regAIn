"""REGAIN Score Stack — Impact Scorecard infrastructure.

Creates DynamoDB tables for computed scores and public share links,
Lambda functions for score computation and PDF export,
EventBridge nightly recomputation rule, S3 bucket for PDF exports,
and API Gateway routes for the scorecard endpoints.
"""

from pathlib import Path

import aws_cdk as cdk
from aws_cdk import (
    aws_apigateway as apigw,
    aws_cognito as cognito,
    aws_dynamodb as dynamodb,
    aws_events as events,
    aws_events_targets as targets,
    aws_iam as iam,
    aws_lambda as _lambda,
    aws_logs as logs,
    aws_s3 as s3,
    aws_sns as sns,
    aws_sqs as sqs,
)
from constructs import Construct

from .monitoring import add_lambda_alarms


class ScoreStack(cdk.Stack):
    """Impact Scorecard infrastructure: tables, Lambdas, EventBridge, S3, API routes."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        tables: dict[str, dynamodb.Table],
        api: apigw.RestApi,
        user_pool: cognito.UserPool,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.tables = tables
        self._score_tables = self._create_tables()
        self.exports_bucket = self._create_exports_bucket()
        self._weasyprint_layer = self._create_weasyprint_layer()
        self.score_lambda = self._create_score_lambda()
        self.public_lambda = self._create_public_lambda()
        self._grant_permissions()
        self._create_nightly_schedule()
        self._create_api_routes(api, user_pool)
        self._create_monitoring()
        self._create_outputs()

    # ------------------------------------------------------------------
    # DynamoDB Tables
    # ------------------------------------------------------------------

    def _create_tables(self) -> dict[str, dynamodb.Table]:
        """Create ImpactScores and PublicScoreLinks tables."""
        retain = self.node.try_get_context("retain_data")
        removal = cdk.RemovalPolicy.RETAIN if retain else cdk.RemovalPolicy.DESTROY

        impact_scores = dynamodb.Table(
            self,
            "RegainImpactScores",
            table_name="RegainImpactScores",
            partition_key=dynamodb.Attribute(
                name="userId", type=dynamodb.AttributeType.STRING,
            ),
            sort_key=dynamodb.Attribute(
                name="sk", type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=removal,
            point_in_time_recovery=True,
            time_to_live_attribute="ttl",
        )

        public_links = dynamodb.Table(
            self,
            "RegainPublicScoreLinks",
            table_name="RegainPublicScoreLinks",
            partition_key=dynamodb.Attribute(
                name="shortCode", type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=cdk.RemovalPolicy.DESTROY,
            time_to_live_attribute="expiresAt",
        )

        return {"ImpactScores": impact_scores, "PublicScoreLinks": public_links}

    # ------------------------------------------------------------------
    # S3 Bucket
    # ------------------------------------------------------------------

    def _create_exports_bucket(self) -> s3.Bucket:
        """Create S3 bucket for PDF score exports."""
        retain = self.node.try_get_context("retain_data")
        removal = cdk.RemovalPolicy.RETAIN if retain else cdk.RemovalPolicy.DESTROY
        auto_del = not bool(retain)

        return s3.Bucket(
            self,
            "RegainScoreExportsBucket",
            bucket_name=f"regain-score-exports-{cdk.Aws.ACCOUNT_ID}",
            versioned=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=removal,
            auto_delete_objects=auto_del,
            lifecycle_rules=[
                s3.LifecycleRule(
                    expiration=cdk.Duration.days(30),
                    noncurrent_version_expiration=cdk.Duration.days(7),
                ),
            ],
        )

    # ------------------------------------------------------------------
    # Lambda Layer
    # ------------------------------------------------------------------

    def _create_weasyprint_layer(self) -> _lambda.LayerVersion:
        """Create a Lambda Layer with WeasyPrint + system dependencies (Cairo, Pango)."""
        return _lambda.LayerVersion(
            self,
            "RegainWeasyPrintLayer",
            layer_version_name="RegainWeasyPrint",
            code=_lambda.Code.from_asset(
                str(Path(__file__).resolve().parent.parent / "weasyprint_layer"),
            ),
            compatible_runtimes=[_lambda.Runtime.PYTHON_3_12],
            description="WeasyPrint + Cairo/Pango for PDF generation",
        )

    # ------------------------------------------------------------------
    # Lambda Functions
    # ------------------------------------------------------------------

    def _table_env(self) -> dict[str, str]:
        """Environment variables for all DynamoDB table names."""
        return {
            "USER_PROFILES_TABLE": self.tables["UserProfiles"].table_name,
            "CAMPAIGNS_TABLE": self.tables["Campaigns"].table_name,
            "MISSION_HISTORY_TABLE": self.tables["MissionHistory"].table_name,
            "EVIDENCE_VAULT_TABLE": self.tables["EvidenceVault"].table_name,
            "MARKET_DATA_TABLE": self.tables["MarketData"].table_name,
            "IMPACT_SCORES_TABLE": self._score_tables["ImpactScores"].table_name,
            "PUBLIC_SCORE_LINKS_TABLE": self._score_tables["PublicScoreLinks"].table_name,
            "SCORE_EXPORTS_BUCKET": self.exports_bucket.bucket_name,
        }

    def _create_score_lambda(self) -> _lambda.Function:
        """Create the score computation Lambda (API + EventBridge trigger).

        Includes the WeasyPrint layer for PDF generation. LD_LIBRARY_PATH
        is set so the Lambda runtime can find Cairo/Pango shared libraries
        in the layer's /opt/lib directory.
        """
        env = self._table_env()
        env["LD_LIBRARY_PATH"] = "/opt/lib:/var/lang/lib:/lib64:/usr/lib64"

        return _lambda.Function(
            self,
            "RegainScoreComputeFunction",
            function_name="RegainScoreCompute",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="backend.handlers.score.handler.lambda_handler",
            code=_lambda.Code.from_asset(
                str(Path(__file__).resolve().parent.parent.parent),
                exclude=["frontend", "tests", "infra", ".venv", "node_modules", ".git", "_layer"],
            ),
            layers=[self._weasyprint_layer],
            environment=env,
            timeout=cdk.Duration.seconds(60),
            memory_size=1024,  # WeasyPrint needs more memory for PDF rendering
            tracing=_lambda.Tracing.ACTIVE,
            log_retention=logs.RetentionDays.ONE_MONTH,
        )

    def _create_public_lambda(self) -> _lambda.Function:
        """Create the public scorecard Lambda (unauthenticated read-only)."""
        return _lambda.Function(
            self,
            "RegainScorePublicFunction",
            function_name="RegainScorePublic",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="backend.handlers.score.public_handler.lambda_handler",
            code=_lambda.Code.from_asset(
                str(Path(__file__).resolve().parent.parent.parent),
                exclude=["frontend", "tests", "infra", ".venv", "node_modules", ".git", "_layer"],
            ),
            environment={
                "IMPACT_SCORES_TABLE": self._score_tables["ImpactScores"].table_name,
                "PUBLIC_SCORE_LINKS_TABLE": self._score_tables["PublicScoreLinks"].table_name,
            },
            timeout=cdk.Duration.seconds(10),
            memory_size=256,
            tracing=_lambda.Tracing.ACTIVE,
            log_retention=logs.RetentionDays.ONE_MONTH,
        )

    # ------------------------------------------------------------------
    # IAM Permissions
    # ------------------------------------------------------------------

    def _grant_permissions(self) -> None:
        """Grant least-privilege IAM permissions."""
        # Score compute Lambda: read 5 data tables, read/write score tables
        self.tables["UserProfiles"].grant_read_data(self.score_lambda)
        self.tables["Campaigns"].grant_read_data(self.score_lambda)
        self.tables["MissionHistory"].grant_read_data(self.score_lambda)
        self.tables["EvidenceVault"].grant_read_data(self.score_lambda)
        self.tables["MarketData"].grant_read_data(self.score_lambda)
        self._score_tables["ImpactScores"].grant_read_write_data(self.score_lambda)
        self._score_tables["PublicScoreLinks"].grant_read_write_data(self.score_lambda)
        self.exports_bucket.grant_put(self.score_lambda)
        self.exports_bucket.grant_read(self.score_lambda)

        # Public Lambda: read-only on score tables
        self._score_tables["ImpactScores"].grant_read_data(self.public_lambda)
        self._score_tables["PublicScoreLinks"].grant_read_data(self.public_lambda)

    # ------------------------------------------------------------------
    # EventBridge Nightly Recomputation
    # ------------------------------------------------------------------

    def _create_nightly_schedule(self) -> None:
        """Create EventBridge rule for nightly score recomputation at 02:00 UTC."""
        dlq = sqs.Queue(
            self,
            "RegainScoreRecomputeDlq",
            queue_name="RegainScoreRecomputeDlq",
            retention_period=cdk.Duration.days(14),
            enforce_ssl=True,
        )

        events.Rule(
            self,
            "RegainNightlyScoreRecompute",
            rule_name="RegainNightlyScoreRecompute",
            schedule=events.Schedule.cron(
                minute="0", hour="2", month="*", year="*",
            ),
            targets=[
                targets.LambdaFunction(
                    self.score_lambda,
                    event=events.RuleTargetInput.from_object({"mode": "batch"}),
                    dead_letter_queue=dlq,
                ),
            ],
        )

    # ------------------------------------------------------------------
    # API Routes (L1 to avoid cyclic dependency with ApiStack)
    # ------------------------------------------------------------------

    def _create_api_routes(
        self,
        api: apigw.RestApi,
        user_pool: cognito.UserPool,
    ) -> None:
        """Add score API routes to the existing REST API.

        Uses L1 (Cfn) constructs to avoid cyclic cross-stack dependency.
        """
        rest_api_id = api.rest_api_id
        root_resource_id = api.rest_api_root_resource_id

        # Authorizer
        authorizer = apigw.CfnAuthorizer(
            self,
            "RegainScoreAuthorizer",
            name="RegainScoreAuthorizer",
            rest_api_id=rest_api_id,
            type="COGNITO_USER_POOLS",
            identity_source="method.request.header.Authorization",
            provider_arns=[user_pool.user_pool_arn],
        )

        # Lambda invoke permissions
        self.score_lambda.add_permission(
            "ApiGatewayInvokeScore",
            principal=iam.ServicePrincipal("apigateway.amazonaws.com"),
            source_arn=f"arn:aws:execute-api:{cdk.Aws.REGION}:{cdk.Aws.ACCOUNT_ID}:{rest_api_id}/*",
        )
        self.public_lambda.add_permission(
            "ApiGatewayInvokePublic",
            principal=iam.ServicePrincipal("apigateway.amazonaws.com"),
            source_arn=f"arn:aws:execute-api:{cdk.Aws.REGION}:{cdk.Aws.ACCOUNT_ID}:{rest_api_id}/*",
        )

        score_integration_uri = (
            f"arn:aws:apigateway:{cdk.Aws.REGION}:lambda:path"
            f"/2015-03-31/functions/{self.score_lambda.function_arn}/invocations"
        )
        public_integration_uri = (
            f"arn:aws:apigateway:{cdk.Aws.REGION}:lambda:path"
            f"/2015-03-31/functions/{self.public_lambda.function_arn}/invocations"
        )

        cors_headers = {
            "method.response.header.Access-Control-Allow-Headers": "'Content-Type,Authorization'",
            "method.response.header.Access-Control-Allow-Methods": "'GET,POST,OPTIONS'",
            "method.response.header.Access-Control-Allow-Origin": "'https://regain.altivum.ai'",
        }
        cors_params = {k: True for k in cors_headers}

        def _add_options(resource_ref: str, construct_id: str) -> None:
            """Add CORS OPTIONS method to a resource."""
            apigw.CfnMethod(
                self,
                construct_id,
                rest_api_id=rest_api_id,
                resource_id=resource_ref,
                http_method="OPTIONS",
                authorization_type="NONE",
                integration=apigw.CfnMethod.IntegrationProperty(
                    type="MOCK",
                    request_templates={"application/json": '{"statusCode": 200}'},
                    integration_responses=[
                        apigw.CfnMethod.IntegrationResponseProperty(
                            status_code="200",
                            response_parameters=cors_headers,
                        ),
                    ],
                ),
                method_responses=[
                    apigw.CfnMethod.MethodResponseProperty(
                        status_code="200",
                        response_parameters=cors_params,
                    ),
                ],
            )

        # /score resource
        score_resource = apigw.CfnResource(
            self, "ScoreApiResource",
            rest_api_id=rest_api_id,
            parent_id=root_resource_id,
            path_part="score",
        )

        # GET /score (authenticated)
        apigw.CfnMethod(
            self, "ScoreGetMethod",
            rest_api_id=rest_api_id,
            resource_id=score_resource.ref,
            http_method="GET",
            authorization_type="COGNITO_USER_POOLS",
            authorizer_id=authorizer.ref,
            integration=apigw.CfnMethod.IntegrationProperty(
                type="AWS_PROXY",
                integration_http_method="POST",
                uri=score_integration_uri,
            ),
        )
        _add_options(score_resource.ref, "ScoreOptionsMethod")

        # /score/history resource
        history_resource = apigw.CfnResource(
            self, "ScoreHistoryApiResource",
            rest_api_id=rest_api_id,
            parent_id=score_resource.ref,
            path_part="history",
        )

        # GET /score/history (authenticated)
        apigw.CfnMethod(
            self, "ScoreHistoryGetMethod",
            rest_api_id=rest_api_id,
            resource_id=history_resource.ref,
            http_method="GET",
            authorization_type="COGNITO_USER_POOLS",
            authorizer_id=authorizer.ref,
            integration=apigw.CfnMethod.IntegrationProperty(
                type="AWS_PROXY",
                integration_http_method="POST",
                uri=score_integration_uri,
            ),
        )
        _add_options(history_resource.ref, "ScoreHistoryOptionsMethod")

        # /score/share resource
        share_resource = apigw.CfnResource(
            self, "ScoreShareApiResource",
            rest_api_id=rest_api_id,
            parent_id=score_resource.ref,
            path_part="share",
        )

        # POST /score/share (authenticated)
        apigw.CfnMethod(
            self, "ScoreSharePostMethod",
            rest_api_id=rest_api_id,
            resource_id=share_resource.ref,
            http_method="POST",
            authorization_type="COGNITO_USER_POOLS",
            authorizer_id=authorizer.ref,
            integration=apigw.CfnMethod.IntegrationProperty(
                type="AWS_PROXY",
                integration_http_method="POST",
                uri=score_integration_uri,
            ),
        )
        _add_options(share_resource.ref, "ScoreShareOptionsMethod")

        # /score/export resource
        export_resource = apigw.CfnResource(
            self, "ScoreExportApiResource",
            rest_api_id=rest_api_id,
            parent_id=score_resource.ref,
            path_part="export",
        )

        # POST /score/export (authenticated)
        apigw.CfnMethod(
            self, "ScoreExportPostMethod",
            rest_api_id=rest_api_id,
            resource_id=export_resource.ref,
            http_method="POST",
            authorization_type="COGNITO_USER_POOLS",
            authorizer_id=authorizer.ref,
            integration=apigw.CfnMethod.IntegrationProperty(
                type="AWS_PROXY",
                integration_http_method="POST",
                uri=score_integration_uri,
            ),
        )
        _add_options(export_resource.ref, "ScoreExportOptionsMethod")

        # /score/public/{shortCode} resource
        public_resource = apigw.CfnResource(
            self, "ScorePublicApiResource",
            rest_api_id=rest_api_id,
            parent_id=score_resource.ref,
            path_part="public",
        )
        shortcode_resource = apigw.CfnResource(
            self, "ScoreShortCodeApiResource",
            rest_api_id=rest_api_id,
            parent_id=public_resource.ref,
            path_part="{shortCode}",
        )

        # GET /score/public/{shortCode} (unauthenticated)
        apigw.CfnMethod(
            self, "ScorePublicGetMethod",
            rest_api_id=rest_api_id,
            resource_id=shortcode_resource.ref,
            http_method="GET",
            authorization_type="NONE",
            integration=apigw.CfnMethod.IntegrationProperty(
                type="AWS_PROXY",
                integration_http_method="POST",
                uri=public_integration_uri,
            ),
        )
        _add_options(shortcode_resource.ref, "ScorePublicOptionsMethod")

    # ------------------------------------------------------------------
    # Monitoring
    # ------------------------------------------------------------------

    def _create_monitoring(self) -> None:
        """Add CloudWatch alarms for score Lambda functions."""
        _skip = self.node.try_get_context("skip_alert_import")
        if _skip:
            return

        alert_topic = sns.Topic.from_topic_arn(
            self, "ImportedAlertTopic",
            cdk.Fn.import_value("RegainAlertSnsTopicArn"),
        )
        add_lambda_alarms(
            self, self.score_lambda, alert_topic,
            name="ScoreCompute", timeout_seconds=60, prefix="Score-",
        )
        add_lambda_alarms(
            self, self.public_lambda, alert_topic,
            name="ScorePublic", timeout_seconds=10, prefix="Score-",
        )

    # ------------------------------------------------------------------
    # Outputs
    # ------------------------------------------------------------------

    def _create_outputs(self) -> None:
        """Create CloudFormation outputs for cross-stack references."""
        cdk.CfnOutput(
            self, "ImpactScoresTableName",
            value=self._score_tables["ImpactScores"].table_name,
            export_name="RegainImpactScoresTableName",
        )
        cdk.CfnOutput(
            self, "ScoreExportsBucketName",
            value=self.exports_bucket.bucket_name,
            export_name="RegainScoreExportsBucketName",
        )
