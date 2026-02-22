"""CDK assertion tests for ResumeStack.

Validates that the synthesized CloudFormation template contains:
- S3 bucket with versioning and public access blocked
- Lambda function with Python 3.12 runtime and Bedrock permissions
- API Gateway GET and POST routes with Cognito authorization
- CloudFormation outputs for bucket and Lambda ARNs

References: .kiro/specs/agent-friendly-resume/requirements.md
"""

import aws_cdk as cdk
import pytest

from infra.stacks.auth_stack import AuthStack
from infra.stacks.data_stack import DataStack
from infra.stacks.api_stack import ApiStack
from infra.stacks.resume_stack import ResumeStack


def _synth_resume_template() -> dict:
    """Synthesize the full CDK app and return the ResumeStack CloudFormation template."""
    app = cdk.App()
    auth_stack = AuthStack(app, "RegainAuthStack")
    data_stack = DataStack(app, "RegainDataStack")
    api_stack = ApiStack(
        app, "RegainApiStack",
        user_pool=auth_stack.user_pool,
        tables=data_stack.tables,
    )
    ResumeStack(
        app, "RegainResumeStack",
        user_pool=auth_stack.user_pool,
        tables=data_stack.tables,
        api=api_stack.api,
    )
    assembly = app.synth()
    return assembly.get_stack_by_name("RegainResumeStack").template


@pytest.fixture(scope="module")
def template() -> dict:
    """Module-scoped fixture — synthesize once for all tests."""
    return _synth_resume_template()


def _resources_by_type(tmpl: dict, resource_type: str) -> list[tuple[str, dict]]:
    """Return all (logical_id, resource) pairs matching a CloudFormation type."""
    return [
        (lid, res)
        for lid, res in tmpl.get("Resources", {}).items()
        if res.get("Type") == resource_type
    ]


def test_s3_bucket_versioning_enabled(template: dict) -> None:
    """S3 Resume bucket must have versioning enabled."""
    buckets = _resources_by_type(template, "AWS::S3::Bucket")
    assert len(buckets) >= 1, "Expected at least one S3 bucket"
    versioning = buckets[0][1]["Properties"].get("VersioningConfiguration", {})
    assert versioning.get("Status") == "Enabled", (
        f"Bucket versioning is '{versioning.get('Status')}', expected 'Enabled'"
    )


def test_s3_bucket_blocks_public_access(template: dict) -> None:
    """S3 Resume bucket must block all public access."""
    buckets = _resources_by_type(template, "AWS::S3::Bucket")
    assert len(buckets) >= 1
    pab = buckets[0][1]["Properties"].get("PublicAccessBlockConfiguration", {})
    for flag in ("BlockPublicAcls", "BlockPublicPolicy", "IgnorePublicAcls", "RestrictPublicBuckets"):
        assert pab.get(flag) is True, (
            f"PublicAccessBlockConfiguration.{flag} is {pab.get(flag)}, expected True"
        )


def test_lambda_has_bedrock_invoke_permission(template: dict) -> None:
    """IAM policies must grant bedrock:InvokeModel to the Resume Lambda."""
    policies = _resources_by_type(template, "AWS::IAM::Policy")
    bedrock_found = False
    for _lid, res in policies:
        for stmt in res.get("Properties", {}).get("PolicyDocument", {}).get("Statement", []):
            actions = stmt.get("Action", [])
            if isinstance(actions, str):
                actions = [actions]
            if "bedrock:InvokeModel" in actions:
                bedrock_found = True
                break
        if bedrock_found:
            break
    assert bedrock_found, "No IAM policy contains 'bedrock:InvokeModel' action"


def test_api_gateway_resume_routes_exist(template: dict) -> None:
    """API Gateway must have GET and POST methods (excluding OPTIONS)."""
    methods = _resources_by_type(template, "AWS::ApiGateway::Method")
    http_methods = {
        res["Properties"]["HttpMethod"]
        for _lid, res in methods
        if res["Properties"].get("HttpMethod") != "OPTIONS"
    }
    assert "GET" in http_methods, f"Expected GET method, found: {http_methods}"
    assert "POST" in http_methods, f"Expected POST method, found: {http_methods}"


def test_api_gateway_routes_have_cognito_auth(template: dict) -> None:
    """All non-OPTIONS API Gateway methods must use COGNITO_USER_POOLS auth."""
    methods = _resources_by_type(template, "AWS::ApiGateway::Method")
    non_options = [
        (lid, res) for lid, res in methods
        if res["Properties"].get("HttpMethod") != "OPTIONS"
    ]
    assert len(non_options) > 0, "Expected at least one non-OPTIONS method"
    for lid, res in non_options:
        auth_type = res["Properties"].get("AuthorizationType")
        assert auth_type == "COGNITO_USER_POOLS", (
            f"Method {lid} ({res['Properties'].get('HttpMethod')}) has "
            f"AuthorizationType='{auth_type}', expected 'COGNITO_USER_POOLS'"
        )


def test_lambda_function_exists_with_correct_runtime(template: dict) -> None:
    """At least one Lambda function must exist with Python 3.12 runtime."""
    functions = _resources_by_type(template, "AWS::Lambda::Function")
    assert len(functions) >= 1, "Expected at least one Lambda function"
    runtimes = [f[1]["Properties"].get("Runtime") for f in functions]
    assert "python3.12" in runtimes, (
        f"Expected runtime 'python3.12', found: {runtimes}"
    )


def test_cfn_outputs_exist(template: dict) -> None:
    """Stack must export ResumeBucketName, ResumeBucketArn, and ResumeLambdaArn."""
    outputs = template.get("Outputs", {})
    export_names = {
        out.get("Export", {}).get("Name")
        for out in outputs.values()
        if "Export" in out
    }
    for expected in ("RegainResumeBucketName", "RegainResumeBucketArn", "RegainResumeLambdaArn"):
        assert expected in export_names, (
            f"Missing export '{expected}'. Found: {export_names}"
        )
