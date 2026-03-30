"""REGAIN API Stack — API Gateway, Lambda Functions, and IAM Roles."""
from pathlib import Path

import aws_cdk as cdk
from aws_cdk import (
    aws_apigateway as apigw,
    aws_cloudwatch as cloudwatch,
    aws_cloudwatch_actions as cw_actions,
    aws_cognito as cognito,
    aws_dynamodb as dynamodb,
    aws_events as events,
    aws_events_targets as targets,
    aws_iam as iam,
    aws_lambda as _lambda,
    aws_logs as logs,
    aws_sns as sns,
    aws_wafv2 as wafv2,
)
from constructs import Construct

from .monitoring import add_lambda_alarms


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
        self.strands_layer = self._create_strands_layer()

        authorizer = self._create_cognito_authorizer()
        lambdas = self._create_lambda_functions()
        self._grant_permissions(lambdas)
        self._create_api(authorizer, lambdas)
        self._attach_waf()
        self._create_cleanup_lambda()
        self._create_monitoring(lambdas)

        # Expose Lambda functions for cross-stack references
        self.coaching_lambda = lambdas["Coaching"]
        self.missions_lambda = lambdas["Missions"]
        self.evidence_lambda = lambdas["Evidence"]
        self.dashboard_lambda = lambdas["Dashboard"]
        self.profile_lambda = lambdas["Profile"]

    def _create_strands_layer(self) -> _lambda.LayerVersion:
        """Create the Strands Agents Lambda Layer from the local build directory."""
        layer_path = Path(__file__).resolve().parent.parent / "layer_build"
        return _lambda.LayerVersion(
            self,
            "RegainStrandsAgentsLayer",
            code=_lambda.Code.from_asset(str(layer_path)),
            compatible_runtimes=[_lambda.Runtime.PYTHON_3_12],
            description="Strands Agents SDK for REGAIN Coaching Lambda",
        )

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
        env = {
            "USER_PROFILES_TABLE": self.tables["UserProfiles"].table_name,
            "CAMPAIGNS_TABLE": self.tables["Campaigns"].table_name,
            "MISSION_HISTORY_TABLE": self.tables["MissionHistory"].table_name,
            "EVIDENCE_VAULT_TABLE": self.tables["EvidenceVault"].table_name,
            "MARKET_DATA_TABLE": self.tables["MarketData"].table_name,
            "USER_POOL_ID": self.user_pool.user_pool_id,
            "ALLOWED_ORIGIN": "https://regain.altivum.ai",
        }
        if "IdempotencyKeys" in self.tables:
            env["IDEMPOTENCY_TABLE"] = self.tables["IdempotencyKeys"].table_name
        return env

    def _create_lambda_function(
        self,
        name: str,
        handler_path: str,
        layers: list[_lambda.LayerVersion] | None = None,
        memory_size: int = 256,
    ) -> _lambda.Function:
        """Create a single Lambda function.

        Args:
            name: Logical name for the function (e.g. "Onboarding").
            handler_path: Dotted handler path (e.g. "backend.handlers.onboarding.handler.lambda_handler").
            layers: Optional Lambda Layers to attach.
            memory_size: Memory allocation in MB (default 256).

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
            layers=layers or [],
            environment=self._table_env(),
            timeout=cdk.Duration.seconds(30),
            memory_size=memory_size,
            tracing=_lambda.Tracing.ACTIVE,
            log_retention=logs.RetentionDays.ONE_MONTH,
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
            "Onet": "backend.handlers.onet.handler.lambda_handler",
        }
        # Missions Lambda gets 512MB for mission generation + scoring workload
        memory_overrides = {"Missions": 512}
        result = {
            name: self._create_lambda_function(
                name,
                path,
                layers=[self.strands_layer] if name == "Coaching" and self.strands_layer else None,
                memory_size=memory_overrides.get(name, 256),
            )
            for name, path in handlers.items()
        }

        # Onet Lambda reads O*NET credentials from SSM SecureString at runtime
        result["Onet"].add_to_role_policy(
            iam.PolicyStatement(
                actions=["ssm:GetParameter"],
                resources=[
                    f"arn:aws:ssm:{self.region}:{self.account}:parameter/regain/onet/*",
                ],
            )
        )

        return result

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

        # Missions: read/write MissionHistory, write EvidenceVault, read Campaigns,
        # read/write UserProfiles (rate limiting), read MarketData (engine)
        self.tables["MissionHistory"].grant_read_write_data(lambdas["Missions"])
        self.tables["EvidenceVault"].grant_read_write_data(lambdas["Missions"])
        self.tables["Campaigns"].grant_read_data(lambdas["Missions"])
        self.tables["UserProfiles"].grant_read_write_data(lambdas["Missions"])
        self.tables["MarketData"].grant_read_data(lambdas["Missions"])

        # Evidence: read EvidenceVault
        self.tables["EvidenceVault"].grant_read_data(lambdas["Evidence"])

        # Coaching: read UserProfiles
        self.tables["UserProfiles"].grant_read_data(lambdas["Coaching"])

        # Dashboard: read UserProfiles, Campaigns, MissionHistory, EvidenceVault
        self.tables["UserProfiles"].grant_read_data(lambdas["Dashboard"])
        self.tables["Campaigns"].grant_read_data(lambdas["Dashboard"])
        self.tables["MissionHistory"].grant_read_data(lambdas["Dashboard"])
        self.tables["EvidenceVault"].grant_read_data(lambdas["Dashboard"])

        # Onet: no DynamoDB access — proxies external O*NET API only

        # Profile: read/write all user tables (for cascade delete) + Cognito
        self.tables["UserProfiles"].grant_read_write_data(lambdas["Profile"])
        self.tables["Campaigns"].grant_read_write_data(lambdas["Profile"])
        self.tables["MissionHistory"].grant_read_write_data(lambdas["Profile"])
        self.tables["EvidenceVault"].grant_read_write_data(lambdas["Profile"])
        lambdas["Profile"].add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "cognito-idp:AdminDeleteUser",
                    "cognito-idp:AdminUserGlobalSignOut",
                ],
                resources=[self.user_pool.user_pool_arn],
            )
        )

        # Missions + Resume need IdempotencyKeys table for idempotent mutations
        if "IdempotencyKeys" in self.tables:
            self.tables["IdempotencyKeys"].grant_read_write_data(lambdas["Missions"])

        # CloudWatch PutMetricData for business metrics (all Lambdas)
        metrics_policy = iam.PolicyStatement(
            actions=["cloudwatch:PutMetricData"],
            resources=["*"],
            conditions={
                "StringEquals": {"cloudwatch:namespace": "REGAIN/Business"},
            },
        )
        for fn in lambdas.values():
            fn.add_to_role_policy(metrics_policy)

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
                allow_origins=["https://regain.altivum.ai"],
                allow_methods=apigw.Cors.ALL_METHODS,
                allow_headers=["Content-Type", "Authorization", "Idempotency-Key"],
            ),
            deploy_options=apigw.StageOptions(
                throttling_rate_limit=100,
                throttling_burst_limit=200,
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

        # POST /missions/generate
        generate = missions.add_resource("generate")
        generate.add_method(
            "POST",
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

        # GET /evidence/suggest-tags
        evidence_suggest = evidence.add_resource("suggest-tags")
        evidence_suggest.add_method(
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

        # GET /analytics
        analytics = self.api.root.add_resource("analytics")
        analytics.add_method(
            "GET",
            apigw.LambdaIntegration(lambdas["Dashboard"]),
            **auth_kwargs,
        )

        # DELETE /profile + POST /profile/recover
        profile = self.api.root.add_resource("profile")
        profile.add_method(
            "DELETE",
            apigw.LambdaIntegration(lambdas["Profile"]),
            **auth_kwargs,
        )
        profile_recover = profile.add_resource("recover")
        profile_recover.add_method(
            "POST",
            apigw.LambdaIntegration(lambdas["Profile"]),
            **auth_kwargs,
        )

        # GET /onet/search, GET /onet/careers/{soc_code}
        onet = self.api.root.add_resource("onet")
        onet_search = onet.add_resource("search")
        onet_search.add_method(
            "GET",
            apigw.LambdaIntegration(lambdas["Onet"]),
            **auth_kwargs,
        )
        onet_careers = onet.add_resource("careers")
        onet_soc_code = onet_careers.add_resource("{soc_code}")
        onet_soc_code.add_method(
            "GET",
            apigw.LambdaIntegration(lambdas["Onet"]),
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
                    "Access-Control-Allow-Origin": "'https://regain.altivum.ai'",
                    "Access-Control-Allow-Headers": "'Content-Type,Authorization,Idempotency-Key'",
                    "Access-Control-Allow-Methods": "'GET,POST,PUT,DELETE,OPTIONS'",
                },
            )

        cdk.CfnOutput(
            self,
            "ApiUrl",
            value=self.api.url,
            export_name="RegainApiUrl",
        )

    def _attach_waf(self) -> None:
        """Attach a WAF WebACL to the REST API with rate limiting and common rules."""
        web_acl = wafv2.CfnWebACL(
            self,
            "RegainApiWebAcl",
            name="RegainApiWebAcl",
            scope="REGIONAL",
            default_action=wafv2.CfnWebACL.DefaultActionProperty(allow={}),
            visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                cloud_watch_metrics_enabled=True,
                metric_name="RegainApiWebAcl",
                sampled_requests_enabled=True,
            ),
            rules=[
                wafv2.CfnWebACL.RuleProperty(
                    name="RateLimit",
                    priority=1,
                    action=wafv2.CfnWebACL.RuleActionProperty(block={}),
                    statement=wafv2.CfnWebACL.StatementProperty(
                        rate_based_statement=wafv2.CfnWebACL.RateBasedStatementProperty(
                            limit=2000,
                            aggregate_key_type="IP",
                        ),
                    ),
                    visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                        cloud_watch_metrics_enabled=True,
                        metric_name="RegainRateLimit",
                        sampled_requests_enabled=True,
                    ),
                ),
                wafv2.CfnWebACL.RuleProperty(
                    name="AWSCommonRules",
                    priority=2,
                    override_action=wafv2.CfnWebACL.OverrideActionProperty(none={}),
                    statement=wafv2.CfnWebACL.StatementProperty(
                        managed_rule_group_statement=wafv2.CfnWebACL.ManagedRuleGroupStatementProperty(
                            vendor_name="AWS",
                            name="AWSManagedRulesCommonRuleSet",
                        ),
                    ),
                    visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                        cloud_watch_metrics_enabled=True,
                        metric_name="RegainCommonRules",
                        sampled_requests_enabled=True,
                    ),
                ),
            ],
        )

        wafv2.CfnWebACLAssociation(
            self,
            "RegainApiWebAclAssociation",
            resource_arn=f"arn:aws:apigateway:{cdk.Aws.REGION}::/restapis/{self.api.rest_api_id}/stages/{self.api.deployment_stage.stage_name}",
            web_acl_arn=web_acl.attr_arn,
        )

    def _create_cleanup_lambda(self) -> None:
        """Create scheduled Lambda to hard-delete expired soft-deleted accounts."""
        cleanup_fn = _lambda.Function(
            self,
            "RegainCleanupFunction",
            function_name="RegainCleanup",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="backend.handlers.profile.cleanup.lambda_handler",
            code=_lambda.Code.from_asset(
                str(Path(__file__).resolve().parent.parent.parent),
                exclude=["frontend", "tests", "infra", ".venv", "node_modules", ".git", "_layer"],
            ),
            environment=self._table_env(),
            timeout=cdk.Duration.seconds(300),
            memory_size=256,
            tracing=_lambda.Tracing.ACTIVE,
            log_retention=logs.RetentionDays.ONE_MONTH,
        )

        # Grant same permissions as Profile Lambda (cascade delete across all tables)
        self.tables["UserProfiles"].grant_read_write_data(cleanup_fn)
        self.tables["Campaigns"].grant_read_write_data(cleanup_fn)
        self.tables["MissionHistory"].grant_read_write_data(cleanup_fn)
        self.tables["EvidenceVault"].grant_read_write_data(cleanup_fn)
        if "VoiceSessions" in self.tables:
            self.tables["VoiceSessions"].grant_read_write_data(cleanup_fn)
        cleanup_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "cognito-idp:AdminDeleteUser",
                    "cognito-idp:AdminUserGlobalSignOut",
                ],
                resources=[self.user_pool.user_pool_arn],
            )
        )

        # Run daily at 3 AM UTC
        events.Rule(
            self,
            "RegainCleanupSchedule",
            rule_name="RegainCleanupSchedule",
            schedule=events.Schedule.cron(hour="3", minute="0"),
            targets=[targets.LambdaFunction(cleanup_fn)],
        )

        self.cleanup_lambda = cleanup_fn

    def _create_monitoring(self, lambdas: dict[str, _lambda.Function]) -> None:
        """Add CloudWatch alarms for all Lambda functions and the API Gateway."""
        # On first deploy, AgentCoreStack (which exports RegainAlertSnsTopicArn)
        # doesn't exist yet because it depends on ApiStack's lambdas. Use a
        # context flag to skip the import on bootstrap deploys.
        skip_alert_import = self.node.try_get_context("skip_alert_import")
        if skip_alert_import:
            alert_topic = sns.Topic(self, "RegainApiAlertTopic",
                                    topic_name="RegainApiAlerts")
        else:
            alert_topic = sns.Topic.from_topic_arn(
                self, "ImportedAlertTopic",
                cdk.Fn.import_value("RegainAlertSnsTopicArn"),
            )

        for name, fn in lambdas.items():
            add_lambda_alarms(self, fn, alert_topic, name=name, timeout_seconds=30)

        # Cleanup Lambda alarms (separate because it's not in the main lambdas dict)
        add_lambda_alarms(
            self, self.cleanup_lambda, alert_topic,
            name="Cleanup", timeout_seconds=300,
        )

        # API Gateway 5xx alarm
        api_5xx_metric = cloudwatch.Metric(
            namespace="AWS/ApiGateway",
            metric_name="5XXError",
            dimensions_map={"ApiName": "RegainApi"},
            statistic="Sum",
            period=cdk.Duration.minutes(5),
        )
        api_5xx_alarm = api_5xx_metric.create_alarm(
            self, "RegainApi5xxAlarm",
            alarm_name="Regain-Api-5xxErrors",
            alarm_description="API Gateway 5xx error count > 0 over 5 minutes",
            threshold=0,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        api_5xx_alarm.add_alarm_action(cw_actions.SnsAction(alert_topic))

        # DynamoDB monitoring dashboard
        self._create_dynamodb_dashboard()
        self._create_business_dashboard()

    def _create_dynamodb_dashboard(self) -> None:
        """Create a CloudWatch dashboard with DynamoDB throttle and capacity widgets."""
        # Monitor the 6 data tables (skip ephemeral WebSocketConnections and IdempotencyKeys)
        monitored_tables = [
            "UserProfiles", "Campaigns", "MissionHistory",
            "EvidenceVault", "MarketData", "VoiceSessions",
        ]

        throttle_widgets: list[cloudwatch.IWidget] = []
        capacity_widgets: list[cloudwatch.IWidget] = []

        for table_name in monitored_tables:
            if table_name not in self.tables:
                continue
            table = self.tables[table_name]
            dimensions = {"TableName": table.table_name}

            throttle_widgets.append(
                cloudwatch.GraphWidget(
                    title=f"{table_name} Throttled Events",
                    left=[
                        cloudwatch.Metric(
                            namespace="AWS/DynamoDB",
                            metric_name="ReadThrottleEvents",
                            dimensions_map=dimensions,
                            statistic="Sum",
                            period=cdk.Duration.minutes(5),
                        ),
                        cloudwatch.Metric(
                            namespace="AWS/DynamoDB",
                            metric_name="WriteThrottleEvents",
                            dimensions_map=dimensions,
                            statistic="Sum",
                            period=cdk.Duration.minutes(5),
                        ),
                    ],
                    width=8,
                )
            )

            capacity_widgets.append(
                cloudwatch.GraphWidget(
                    title=f"{table_name} Consumed Capacity",
                    left=[
                        cloudwatch.Metric(
                            namespace="AWS/DynamoDB",
                            metric_name="ConsumedReadCapacityUnits",
                            dimensions_map=dimensions,
                            statistic="Sum",
                            period=cdk.Duration.minutes(5),
                        ),
                        cloudwatch.Metric(
                            namespace="AWS/DynamoDB",
                            metric_name="ConsumedWriteCapacityUnits",
                            dimensions_map=dimensions,
                            statistic="Sum",
                            period=cdk.Duration.minutes(5),
                        ),
                    ],
                    width=8,
                )
            )

        cloudwatch.Dashboard(
            self,
            "RegainDynamoDBDashboard",
            dashboard_name="Regain-DynamoDB",
            widgets=[
                [cloudwatch.TextWidget(
                    markdown="## DynamoDB Throttled Events",
                    width=24,
                )],
                throttle_widgets,
                [cloudwatch.TextWidget(
                    markdown="## DynamoDB Consumed Capacity",
                    width=24,
                )],
                capacity_widgets,
            ],
        )

    def _create_business_dashboard(self) -> None:
        """Create a CloudWatch dashboard with business KPI widgets."""
        ns = "REGAIN/Business"
        period = cdk.Duration.hours(1)

        def _metric(name: str, statistic: str = "Sum") -> cloudwatch.Metric:
            return cloudwatch.Metric(
                namespace=ns,
                metric_name=name,
                statistic=statistic,
                period=period,
            )

        cloudwatch.Dashboard(
            self,
            "RegainBusinessDashboard",
            dashboard_name="REGAIN-Business",
            widgets=[
                [
                    cloudwatch.GraphWidget(
                        title="Missions Completed",
                        left=[_metric("missions_completed")],
                        width=8,
                    ),
                    cloudwatch.GraphWidget(
                        title="Evidence Logged",
                        left=[_metric("evidence_logged")],
                        width=8,
                    ),
                    cloudwatch.GraphWidget(
                        title="Resumes Generated",
                        left=[_metric("resume_generated")],
                        width=8,
                    ),
                ],
                [
                    cloudwatch.GraphWidget(
                        title="Coaching Sessions Started",
                        left=[_metric("coaching_session_started")],
                        width=8,
                    ),
                    cloudwatch.GraphWidget(
                        title="Coaching Session Duration (avg)",
                        left=[_metric("coaching_session_duration", "Average")],
                        width=8,
                    ),
                    cloudwatch.GraphWidget(
                        title="Voice Sessions Completed",
                        left=[_metric("voice_session_completed")],
                        width=8,
                    ),
                ],
            ],
        )
