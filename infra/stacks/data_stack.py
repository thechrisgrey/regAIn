"""REGAIN Data Stack — DynamoDB Tables."""
import aws_cdk as cdk
from aws_cdk import aws_dynamodb as dynamodb
from constructs import Construct


class DataStack(cdk.Stack):
    """DynamoDB tables for REGAIN platform data layer."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.tables: dict[str, dynamodb.Table] = {}

        self._create_user_profiles_table()
        self._create_campaigns_table()
        self._create_mission_history_table()
        self._create_evidence_vault_table()
        self._create_market_data_table()

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
            removal_policy=cdk.RemovalPolicy.DESTROY,
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
            removal_policy=cdk.RemovalPolicy.DESTROY,
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
            removal_policy=cdk.RemovalPolicy.DESTROY,
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
            removal_policy=cdk.RemovalPolicy.DESTROY,
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
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )
        table.add_global_secondary_index(
            index_name="role-title-index",
            partition_key=dynamodb.Attribute(
                name="roleTitle", type=dynamodb.AttributeType.STRING
            ),
        )
        self.tables["MarketData"] = table

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
