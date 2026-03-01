"""REGAIN Resume Stack — S3 Bucket, Resume Lambda, and API Gateway Routes."""
from pathlib import Path

import aws_cdk as cdk
from aws_cdk import (
    aws_apigateway as apigw,
    aws_cognito as cognito,
    aws_dynamodb as dynamodb,
    aws_iam as iam,
    aws_lambda as _lambda,
    aws_s3 as s3,
    aws_sns as sns,
)
from constructs import Construct

from .monitoring import add_lambda_alarms


class ResumeStack(cdk.Stack):
    """Resume generation infrastructure: S3 bucket, Lambda, and API routes."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        user_pool: cognito.UserPool,
        tables: dict[str, dynamodb.Table],
        api: apigw.RestApi,
        profile_lambda: _lambda.Function,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.profile_lambda = profile_lambda
        self.bucket = self._create_bucket()
        self.resume_lambda = self._create_lambda(tables)
        self._grant_permissions(tables)
        self._grant_profile_lambda_permissions()
        self._create_api_routes(api, user_pool)
        self._create_monitoring()
        self._create_outputs()

    def _create_bucket(self) -> s3.Bucket:
        """Create the Resume S3 bucket with versioning, lifecycle rules, and public access blocked."""
        return s3.Bucket(
            self,
            "RegainResumeBucket",
            bucket_name=f"regain-resume-{cdk.Aws.ACCOUNT_ID}",
            versioned=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=cdk.RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            lifecycle_rules=[
                s3.LifecycleRule(
                    noncurrent_versions_to_retain=2,
                    noncurrent_version_expiration=cdk.Duration.days(30),
                ),
            ],
        )

    def _create_lambda(self, tables: dict[str, dynamodb.Table]) -> _lambda.Function:
        """Create the Resume Generation Lambda function."""
        return _lambda.Function(
            self,
            "RegainResumeFunction",
            function_name="RegainResume",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="backend.handlers.resume.handler.lambda_handler",
            code=_lambda.Code.from_asset(
                str(Path(__file__).resolve().parent.parent.parent),
                exclude=["frontend", "tests", "infra", ".venv", "node_modules", ".git", "_layer"],
            ),
            environment={
                "USER_PROFILES_TABLE": tables["UserProfiles"].table_name,
                "CAMPAIGNS_TABLE": tables["Campaigns"].table_name,
                "MISSION_HISTORY_TABLE": tables["MissionHistory"].table_name,
                "EVIDENCE_VAULT_TABLE": tables["EvidenceVault"].table_name,
                "MARKET_DATA_TABLE": tables["MarketData"].table_name,
                "RESUME_BUCKET_NAME": self.bucket.bucket_name,
                "BEDROCK_MODEL_ID": "amazon.nova-lite-v1:0",
                **({"IDEMPOTENCY_TABLE": tables["IdempotencyKeys"].table_name} if "IdempotencyKeys" in tables else {}),
            },
            timeout=cdk.Duration.seconds(60),
            memory_size=512,
            tracing=_lambda.Tracing.ACTIVE,
        )

    def _grant_permissions(self, tables: dict[str, dynamodb.Table]) -> None:
        """Grant least-privilege IAM permissions to the Resume Lambda."""
        # UserProfiles needs read/write for metadata updates and rate limiting
        tables["UserProfiles"].grant_read_write_data(self.resume_lambda)

        # Read-only access on the other 4 tables
        for name in ("Campaigns", "MissionHistory", "EvidenceVault", "MarketData"):
            tables[name].grant_read_data(self.resume_lambda)

        # IdempotencyKeys table for idempotent resume generation
        if "IdempotencyKeys" in tables:
            tables["IdempotencyKeys"].grant_read_write_data(self.resume_lambda)

        # Read/write on Resume bucket
        self.bucket.grant_read_write(self.resume_lambda)

        # Bedrock InvokeModel for Nova Lite
        self.resume_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel"],
                resources=[
                    f"arn:aws:bedrock:{cdk.Aws.REGION}::foundation-model/amazon.nova-lite-v1:0",
                ],
            )
        )

    def _grant_profile_lambda_permissions(self) -> None:
        """Grant the Profile Lambda permissions for resume cascade delete.

        Uses a constructed ARN from the known bucket name to avoid
        cyclic cross-stack references (ResumeStack <-> ApiStack).
        """
        bucket_name = f"regain-resume-{cdk.Aws.ACCOUNT_ID}"
        bucket_arn = f"arn:aws:s3:::{bucket_name}"
        self.profile_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["s3:GetObject", "s3:ListBucket", "s3:DeleteObject"],
                resources=[bucket_arn, f"{bucket_arn}/*"],
            )
        )
        self.profile_lambda.add_environment("RESUME_BUCKET_NAME", bucket_name)

    def _create_api_routes(
        self,
        api: apigw.RestApi,
        user_pool: cognito.UserPool,
    ) -> None:
        """Add GET /resume and POST /resume/generate routes to the existing API.

        Uses L1 (Cfn) constructs to avoid a cyclic cross-stack dependency.
        The L2 ``api.root.add_resource()`` approach creates a bidirectional
        reference between ApiStack and ResumeStack which CDK rejects.
        """
        rest_api_id = api.rest_api_id
        root_resource_id = api.rest_api_root_resource_id

        # Authorizer
        authorizer = apigw.CfnAuthorizer(
            self,
            "RegainResumeAuthorizer",
            name="RegainResumeAuthorizer",
            rest_api_id=rest_api_id,
            type="COGNITO_USER_POOLS",
            identity_source="method.request.header.Authorization",
            provider_arns=[user_pool.user_pool_arn],
        )

        # /resume resource
        resume_resource = apigw.CfnResource(
            self,
            "ResumeApiResource",
            rest_api_id=rest_api_id,
            parent_id=root_resource_id,
            path_part="resume",
        )

        # /resume/generate resource
        generate_resource = apigw.CfnResource(
            self,
            "ResumeGenerateApiResource",
            rest_api_id=rest_api_id,
            parent_id=resume_resource.ref,
            path_part="generate",
        )

        # Lambda invoke permission for API Gateway
        self.resume_lambda.add_permission(
            "ApiGatewayInvoke",
            principal=iam.ServicePrincipal("apigateway.amazonaws.com"),
            source_arn=f"arn:aws:execute-api:{cdk.Aws.REGION}:{cdk.Aws.ACCOUNT_ID}:{rest_api_id}/*",
        )

        integration_uri = (
            f"arn:aws:apigateway:{cdk.Aws.REGION}:lambda:path"
            f"/2015-03-31/functions/{self.resume_lambda.function_arn}/invocations"
        )

        for method_id, resource_id, http_method in [
            ("ResumeGetMethod", resume_resource.ref, "GET"),
            ("ResumeGeneratePostMethod", generate_resource.ref, "POST"),
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
            ("ResumeOptionsMethod", resume_resource.ref),
            ("ResumeGenerateOptionsMethod", generate_resource.ref),
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

    def _create_monitoring(self) -> None:
        """Add CloudWatch alarms for the Resume Lambda."""
        alert_topic = sns.Topic.from_topic_arn(
            self, "ImportedAlertTopic",
            cdk.Fn.import_value("RegainAlertSnsTopicArn"),
        )
        add_lambda_alarms(self, self.resume_lambda, alert_topic, name="Resume", timeout_seconds=60)

    def _create_outputs(self) -> None:
        """Create CloudFormation outputs for resume infrastructure."""
        cdk.CfnOutput(
            self,
            "ResumeBucketName",
            value=self.bucket.bucket_name,
            export_name="RegainResumeBucketName",
        )
        cdk.CfnOutput(
            self,
            "ResumeBucketArn",
            value=self.bucket.bucket_arn,
            export_name="RegainResumeBucketArn",
        )
        cdk.CfnOutput(
            self,
            "ResumeLambdaArn",
            value=self.resume_lambda.function_arn,
            export_name="RegainResumeLambdaArn",
        )
