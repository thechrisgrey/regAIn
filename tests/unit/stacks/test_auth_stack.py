"""Unit tests for AuthStack configuration.

Validates: Requirements 4.1, 4.2, 4.3, 4.4
"""

import aws_cdk as cdk
from aws_cdk.assertions import Template, Match
from infra.stacks.auth_stack import AuthStack


def _synth_auth_template() -> Template:
    """Synthesize AuthStack and return the CloudFormation template."""
    app = cdk.App()
    stack = AuthStack(app, "TestAuthStack")
    return Template.from_stack(stack)


def test_user_pool_has_email_sign_in() -> None:
    """Verify User Pool has email sign-in enabled (Req 4.1)."""
    template = _synth_auth_template()
    template.has_resource_properties(
        "AWS::Cognito::UserPool",
        {
            "UsernameAttributes": ["email"],
            "AutoVerifiedAttributes": ["email"],
        },
    )


def test_user_pool_client_has_srp_auth_flow() -> None:
    """Verify User Pool Client uses SRP auth without client secret (Req 4.2)."""
    template = _synth_auth_template()
    template.has_resource_properties(
        "AWS::Cognito::UserPoolClient",
        {
            "ExplicitAuthFlows": Match.array_with(
                ["ALLOW_USER_SRP_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]
            ),
            "GenerateSecret": False,
        },
    )


def test_user_pool_id_output_exists() -> None:
    """Verify CloudFormation output for User Pool ID exists (Req 4.3)."""
    template = _synth_auth_template()
    template.has_output(
        "UserPoolId",
        {
            "Export": {"Name": "RegainUserPoolId"},
        },
    )


def test_user_pool_client_id_output_exists() -> None:
    """Verify CloudFormation output for User Pool Client ID exists (Req 4.4)."""
    template = _synth_auth_template()
    template.has_output(
        "UserPoolClientId",
        {
            "Export": {"Name": "RegainUserPoolClientId"},
        },
    )
