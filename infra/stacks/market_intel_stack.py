"""REGAIN Market Intelligence Stack — Scheduled ingestion pipeline infrastructure.

Creates Lambda functions for O*NET, BLS, USAJobs ingestion and seed data loading,
EventBridge Scheduler rules for automated refresh, DynamoDB permissions, and a
CDK custom resource to trigger seed data on first deployment.

Requirements: 1.7, 2.6, 3.6, 8.1, 8.2, 8.3, 8.6, 9.3
"""

from pathlib import Path

import aws_cdk as cdk
from aws_cdk import (
    aws_dynamodb as dynamodb,
    aws_events as events,
    aws_events_targets as targets,
    aws_lambda as _lambda,
    custom_resources as cr,
)
from constructs import Construct


class MarketIntelStack(cdk.Stack):
    """Scheduled market data ingestion pipeline and seed loader."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        tables: dict[str, dynamodb.Table],
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.tables = tables

        self._deps_layer = self._create_deps_layer()
        lambdas = self._create_lambda_functions()
        self._grant_permissions(lambdas)
        self._create_schedules(lambdas)
        self._create_seed_trigger(lambdas["Seed"])

    def _create_deps_layer(self) -> _lambda.LayerVersion:
        """Create a Lambda Layer with third-party Python dependencies (requests)."""
        return _lambda.LayerVersion(
            self,
            "RegainPythonDepsLayer",
            layer_version_name="RegainPythonDeps",
            code=_lambda.Code.from_asset(
                str(Path(__file__).resolve().parent.parent.parent / "_layer"),
            ),
            compatible_runtimes=[_lambda.Runtime.PYTHON_3_12],
            description="Third-party Python dependencies for REGAIN market intel Lambdas",
        )

    def _table_env(self) -> dict[str, str]:
        """Environment variables for DynamoDB table names and API keys."""
        return {
            "MARKET_DATA_TABLE": self.tables["MarketData"].table_name,
            "USER_PROFILES_TABLE": self.tables["UserProfiles"].table_name,
            "EVIDENCE_VAULT_TABLE": self.tables["EvidenceVault"].table_name,
        }

    def _create_lambda_function(
        self, name: str, handler_path: str, extra_env: dict[str, str] | None = None,
    ) -> _lambda.Function:
        """Create a single Lambda function for the ingestion pipeline.

        Args:
            name: Logical name (e.g. "OnetIngestion").
            handler_path: Dotted handler path.
            extra_env: Additional environment variables beyond table names.

        Returns:
            The Lambda function construct.
        """
        env = self._table_env()
        if extra_env:
            env.update(extra_env)

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
            layers=[self._deps_layer],
            environment=env,
            timeout=cdk.Duration.seconds(30),
            memory_size=256,
        )

    def _create_lambda_functions(self) -> dict[str, _lambda.Function]:
        """Create all market intelligence Lambda functions."""
        api_key_env = {
            "ONET_API_KEY": "",
            "USAJOBS_API_KEY": "",
            "USAJOBS_USER_AGENT": "",
        }

        return {
            "Onet": self._create_lambda_function(
                "OnetIngestion",
                "backend.handlers.market_intel.handler.onet_handler",
                extra_env={"ONET_API_KEY": api_key_env["ONET_API_KEY"]},
            ),
            "Bls": self._create_lambda_function(
                "BlsIngestion",
                "backend.handlers.market_intel.handler.bls_handler",
            ),
            "Usajobs": self._create_lambda_function(
                "UsajobsIngestion",
                "backend.handlers.market_intel.handler.usajobs_handler",
                extra_env={
                    "USAJOBS_API_KEY": api_key_env["USAJOBS_API_KEY"],
                    "USAJOBS_USER_AGENT": api_key_env["USAJOBS_USER_AGENT"],
                },
            ),
            "Seed": self._create_lambda_function(
                "SeedLoader",
                "backend.handlers.market_intel.handler.seed_handler",
            ),
        }

    def _grant_permissions(self, lambdas: dict[str, _lambda.Function]) -> None:
        """Grant DynamoDB permissions to pipeline Lambdas.

        All Lambdas get read/write on MarketData and read on UserProfiles
        and EvidenceVault (needed for alignment calculation during scoring).
        """
        for fn in lambdas.values():
            self.tables["MarketData"].grant_read_write_data(fn)
            self.tables["UserProfiles"].grant_read_data(fn)
            self.tables["EvidenceVault"].grant_read_data(fn)

    def _create_schedules(self, lambdas: dict[str, _lambda.Function]) -> None:
        """Create EventBridge Scheduler rules for automated ingestion.

        - O*NET: 1st of each month at 6 AM UTC
        - BLS: 15th of each month at 6 AM UTC
        - USAJobs: Every Monday at 6 AM UTC
        """
        events.Rule(
            self,
            "RegainOnetSchedule",
            rule_name="RegainOnetMonthlyIngestion",
            schedule=events.Schedule.cron(
                minute="0", hour="6", day="1", month="*", year="*",
            ),
            targets=[targets.LambdaFunction(lambdas["Onet"])],
        )

        events.Rule(
            self,
            "RegainBlsSchedule",
            rule_name="RegainBlsMonthlyIngestion",
            schedule=events.Schedule.cron(
                minute="0", hour="6", day="15", month="*", year="*",
            ),
            targets=[targets.LambdaFunction(lambdas["Bls"])],
        )

        events.Rule(
            self,
            "RegainUsajobsSchedule",
            rule_name="RegainUsajobsWeeklyIngestion",
            schedule=events.Schedule.cron(
                minute="0", hour="6", week_day="MON", month="*", year="*",
            ),
            targets=[targets.LambdaFunction(lambdas["Usajobs"])],
        )

    def _create_seed_trigger(self, seed_fn: _lambda.Function) -> None:
        """Create a CDK custom resource that invokes the seed handler on deployment.

        This triggers seed data loading on first deploy. Subsequent deploys
        re-invoke the handler, but seed loading is idempotent (overwrites).
        """
        provider = cr.Provider(
            self,
            "RegainSeedProvider",
            on_event_handler=seed_fn,
        )

        cdk.CustomResource(
            self,
            "RegainSeedTrigger",
            service_token=provider.service_token,
            properties={
                "trigger": "initial-seed-load",
            },
        )
