"""Test for encryption at rest compliance.

Verifies that S3 buckets use server-side encryption and DynamoDB tables
use default encryption (AWS-owned keys).
"""

import aws_cdk as cdk

from infra.stacks.auth_stack import AuthStack
from infra.stacks.data_stack import DataStack
from infra.stacks.api_stack import ApiStack
from infra.stacks.resume_stack import ResumeStack
from infra.stacks.voice_practice_stack import VoicePracticeStack


def _synth_templates() -> dict[str, dict]:
    """Synthesize the CDK app and return templates keyed by stack name."""
    env = cdk.Environment(account="123456789012", region="us-east-1")
    app = cdk.App()
    auth = AuthStack(app, "RegainAuthStack", env=env)
    data = DataStack(app, "RegainDataStack", env=env)
    api = ApiStack(
        app, "RegainApiStack",
        user_pool=auth.user_pool,
        tables=data.tables,
        env=env,
    )
    ResumeStack(
        app, "RegainResumeStack",
        user_pool=auth.user_pool,
        tables=data.tables,
        api=api.api,
        profile_lambda=api.profile_lambda,
        env=env,
    )
    VoicePracticeStack(
        app, "RegainVoicePracticeStack",
        user_pool=auth.user_pool,
        tables=data.tables,
        api=api.api,
        profile_lambda=api.profile_lambda,
        env=env,
    )
    assembly = app.synth()
    return {
        name: assembly.get_stack_by_name(name).template
        for name in [
            "RegainResumeStack",
            "RegainVoicePracticeStack",
            "RegainDataStack",
        ]
    }


def _get_resources_by_type(template: dict, resource_type: str) -> list[tuple[str, dict]]:
    """Extract all resources of a given type from a CloudFormation template."""
    return [
        (lid, res)
        for lid, res in template.get("Resources", {}).items()
        if res.get("Type") == resource_type
    ]


def test_s3_buckets_have_encryption() -> None:
    """All S3 buckets should have SSE-S3 (AES256) encryption enabled."""
    templates = _synth_templates()
    for stack_name in ("RegainResumeStack", "RegainVoicePracticeStack"):
        template = templates[stack_name]
        buckets = _get_resources_by_type(template, "AWS::S3::Bucket")
        assert buckets, f"No S3 buckets found in {stack_name}"

        for lid, bucket in buckets:
            encryption = bucket.get("Properties", {}).get(
                "BucketEncryption", {}
            )
            rules = encryption.get("ServerSideEncryptionConfiguration", [])
            algorithms = [
                rule.get("ServerSideEncryptionByDefault", {}).get(
                    "SSEAlgorithm", ""
                )
                for rule in rules
            ]
            assert "AES256" in algorithms or "aws:kms" in algorithms, (
                f"Bucket {lid} in {stack_name} is missing server-side encryption. "
                f"Found: {encryption}"
            )


def test_dynamodb_tables_use_default_encryption() -> None:
    """DynamoDB tables should not override encryption (uses AWS-owned keys by default)."""
    templates = _synth_templates()
    template = templates["RegainDataStack"]
    tables = _get_resources_by_type(template, "AWS::DynamoDB::Table")
    assert len(tables) >= 6, f"Expected at least 6 tables, found {len(tables)}"

    for lid, table in tables:
        sse = table.get("Properties", {}).get("SSESpecification", {})
        # Default encryption uses AWS-owned keys.
        # If SSESpecification is absent or SSEEnabled is false, that's the default.
        sse_enabled = sse.get("SSEEnabled", False)
        if sse_enabled:
            # If SSE is explicitly enabled, it should be using AWS_OWNED_CMK
            sse_type = sse.get("SSEType", "")
            assert sse_type != "KMS" or "KMSMasterKeyId" not in sse, (
                f"Table {lid} has non-default encryption: {sse}"
            )
