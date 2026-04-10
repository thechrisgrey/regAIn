"""REGAIN Data Stack — DynamoDB Tables."""
import aws_cdk as cdk
from aws_cdk import (
    aws_cloudwatch as cloudwatch,
    aws_cloudwatch_actions as cw_actions,
    aws_dynamodb as dynamodb,
    aws_s3 as s3,
    aws_sns as sns,
    aws_sns_subscriptions as sns_subscriptions,
)
from constructs import Construct


class DataStack(cdk.Stack):
    """DynamoDB tables for REGAIN platform data layer."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.tables: dict[str, dynamodb.Table] = {}

        retain = self.node.try_get_context("retain_data")
        self._removal_policy = cdk.RemovalPolicy.RETAIN if retain else cdk.RemovalPolicy.DESTROY

        self._create_user_profiles_table()
        self._create_campaigns_table()
        self._create_mission_history_table()
        self._create_evidence_vault_table()
        self._create_market_data_table()
        self._create_voice_sessions_table()
        self._create_ws_connections_table()
        self._create_idempotency_keys_table()
        self._create_conversation_threads_table()
        self._create_thread_archives_bucket()

        self._create_monitoring()
        self._create_outputs()

    def _create_user_profiles_table(self) -> None:
        """Create UserProfiles table (PK: userId)."""
        self.tables["UserProfiles"] = dynamodb.Table(
            self,
            "RegainUserProfiles",
            table_name="RegainUserProfiles",
            partition_key=dynamodb.Attribute(
                name="userId", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=self._removal_policy,
            point_in_time_recovery=True,
        )

    def _create_campaigns_table(self) -> None:
        """Create Campaigns table (PK: userId, SK: campaignId) with status GSI."""
        table = dynamodb.Table(
            self,
            "RegainCampaigns",
            table_name="RegainCampaigns",
            partition_key=dynamodb.Attribute(
                name="userId", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="campaignId", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=self._removal_policy,
            point_in_time_recovery=True,
        )
        table.add_global_secondary_index(
            index_name="status-index",
            partition_key=dynamodb.Attribute(
                name="status", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="userId", type=dynamodb.AttributeType.STRING
            ),
        )
        self.tables["Campaigns"] = table

    def _create_mission_history_table(self) -> None:
        """Create MissionHistory table (PK: userId, SK: missionId) with status and date GSIs."""
        table = dynamodb.Table(
            self,
            "RegainMissionHistory",
            table_name="RegainMissionHistory",
            partition_key=dynamodb.Attribute(
                name="userId", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="missionId", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=self._removal_policy,
            point_in_time_recovery=True,
        )
        table.add_global_secondary_index(
            index_name="status-index",
            partition_key=dynamodb.Attribute(
                name="status", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="userId", type=dynamodb.AttributeType.STRING
            ),
        )
        table.add_global_secondary_index(
            index_name="date-index",
            partition_key=dynamodb.Attribute(
                name="userId", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="completedDate", type=dynamodb.AttributeType.STRING
            ),
        )
        self.tables["MissionHistory"] = table

    def _create_evidence_vault_table(self) -> None:
        """Create EvidenceVault table (PK: userId, SK: evidenceId) with skill_tag GSI."""
        table = dynamodb.Table(
            self,
            "RegainEvidenceVault",
            table_name="RegainEvidenceVault",
            partition_key=dynamodb.Attribute(
                name="userId", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="evidenceId", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=self._removal_policy,
            point_in_time_recovery=True,
        )
        table.add_global_secondary_index(
            index_name="skill-index",
            partition_key=dynamodb.Attribute(
                name="skillTag", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="createdAt", type=dynamodb.AttributeType.STRING
            ),
        )
        self.tables["EvidenceVault"] = table

    def _create_market_data_table(self) -> None:
        """Create MarketData table (PK: sector, SK: timestamp) with role-title GSI."""
        table = dynamodb.Table(
            self,
            "RegainMarketData",
            table_name="RegainMarketData",
            partition_key=dynamodb.Attribute(
                name="sector", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="timestamp", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=self._removal_policy,
            point_in_time_recovery=True,
        )
        table.add_global_secondary_index(
            index_name="role-title-index",
            partition_key=dynamodb.Attribute(
                name="roleTitle", type=dynamodb.AttributeType.STRING
            ),
        )
        self.tables["MarketData"] = table

    def _create_voice_sessions_table(self) -> None:
        """Create VoiceSessions table (PK: userId, SK: sessionId) with type-date GSI."""
        table = dynamodb.Table(
            self,
            "RegainVoiceSessions",
            table_name="RegainVoiceSessions",
            partition_key=dynamodb.Attribute(
                name="userId", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="sessionId", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=self._removal_policy,
            point_in_time_recovery=True,
        )
        table.add_global_secondary_index(
            index_name="type-date-index",
            partition_key=dynamodb.Attribute(
                name="sessionType", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="createdAt", type=dynamodb.AttributeType.STRING
            ),
        )
        self.tables["VoiceSessions"] = table

    def _create_ws_connections_table(self) -> None:
        """Create WebSocketConnections table (PK: connectionId) with TTL.

        Stores transient WebSocket connection metadata so that Lambda
        containers handling $default/$disconnect can look up the user
        authenticated during $connect.
        """
        self.tables["WebSocketConnections"] = dynamodb.Table(
            self,
            "RegainWebSocketConnections",
            table_name="RegainWebSocketConnections",
            partition_key=dynamodb.Attribute(
                name="connectionId", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=cdk.RemovalPolicy.DESTROY,
            time_to_live_attribute="ttl",
        )

    def _create_idempotency_keys_table(self) -> None:
        """Create IdempotencyKeys table (PK: idempotencyKey) with TTL.

        Stores cached mutation responses for 24 hours to prevent
        duplicate operations on retry.
        """
        self.tables["IdempotencyKeys"] = dynamodb.Table(
            self,
            "RegainIdempotencyKeys",
            table_name="RegainIdempotencyKeys",
            partition_key=dynamodb.Attribute(
                name="idempotencyKey", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=cdk.RemovalPolicy.DESTROY,
            time_to_live_attribute="expiresAt",
        )

    def _create_conversation_threads_table(self) -> None:
        """Create ConversationThreads table (PK: userId, SK: threadId)."""
        self.tables["ConversationThreads"] = dynamodb.Table(
            self,
            "RegainConversationThreads",
            table_name="RegainConversationThreads",
            partition_key=dynamodb.Attribute(
                name="userId", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="threadId", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=self._removal_policy,
            point_in_time_recovery=True,
            time_to_live_attribute="expiresAt",
        )

    def _create_thread_archives_bucket(self) -> None:
        """Create S3 bucket for compacted thread archives."""
        self.thread_archives_bucket = s3.Bucket(
            self,
            "RegainThreadArchives",
            bucket_name=f"regain-thread-archives-{self.account}-{self.region}",
            versioned=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            removal_policy=self._removal_policy,
            lifecycle_rules=[
                s3.LifecycleRule(
                    transitions=[
                        s3.Transition(
                            storage_class=s3.StorageClass.GLACIER,
                            transition_after=cdk.Duration.days(30),
                        )
                    ],
                )
            ],
        )

    def _create_monitoring(self) -> None:
        """Add CloudWatch throttle alarms for the 7 data tables.

        Creates its own SNS topic for DynamoDB alerts to avoid a cyclic
        dependency with AgentCoreStack (which owns the main alert topic
        but depends on ApiStack which depends on DataStack).

        Skips ephemeral tables (WebSocketConnections, IdempotencyKeys)
        since they use TTL-based cleanup and don't hold durable data.
        """
        alert_topic = sns.Topic(
            self,
            "RegainDynamoDBAlerts",
            topic_name="RegainDynamoDBAlerts",
        )
        alert_topic.add_subscription(
            sns_subscriptions.EmailSubscription("team@altivum.ai"),
        )
        cdk.CfnOutput(
            self,
            "DynamoDBAlertTopicArn",
            value=alert_topic.topic_arn,
            export_name="RegainDynamoDBAlertTopicArn",
        )
        sns_action = cw_actions.SnsAction(alert_topic)

        monitored_tables = [
            "UserProfiles", "Campaigns", "MissionHistory",
            "EvidenceVault", "MarketData", "VoiceSessions",
            "ConversationThreads",
        ]

        for table_name in monitored_tables:
            table = self.tables[table_name]
            dimensions = {"TableName": table.table_name}

            for metric_name, label in [
                ("ReadThrottleEvents", "ReadThrottle"),
                ("WriteThrottleEvents", "WriteThrottle"),
            ]:
                alarm = cloudwatch.Metric(
                    namespace="AWS/DynamoDB",
                    metric_name=metric_name,
                    dimensions_map=dimensions,
                    statistic="Sum",
                    period=cdk.Duration.minutes(5),
                ).create_alarm(
                    self,
                    f"{table_name}{label}Alarm",
                    alarm_name=f"Regain-{table_name}-{label}",
                    alarm_description=(
                        f"{table_name} DynamoDB {label} events > 0 "
                        "in a single 5-minute period"
                    ),
                    threshold=0,
                    evaluation_periods=1,
                    comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
                    treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
                )
                alarm.add_alarm_action(sns_action)

    def _create_outputs(self) -> None:
        """Create CloudFormation outputs for all table names and ARNs."""
        for table_name, table in self.tables.items():
            cdk.CfnOutput(
                self,
                f"{table_name}Name",
                value=table.table_name,
                export_name=f"Regain{table_name}Name",
            )
            cdk.CfnOutput(
                self,
                f"{table_name}Arn",
                value=table.table_arn,
                export_name=f"Regain{table_name}Arn",
            )
        cdk.CfnOutput(
            self,
            "ThreadArchivesBucketName",
            value=self.thread_archives_bucket.bucket_name,
            export_name="RegainThreadArchivesBucketName",
        )
