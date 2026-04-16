"""Verify the Tavily SSM policy factory produces the expected ARN pattern.

The `_search_ssm_policy` method on `AgentStack` grants `ssm:GetParameter`
scoped to `/regain/search/*` so the coaching agent's `web_search` tool
can retrieve the Tavily API key on all three agent Lambdas (ChatStream,
Voice, REST Coaching).

This is a pure unit test — we instantiate a tiny CDK app, call the
factory method, and inspect the resulting `PolicyStatement`. We do NOT
synthesize the full AgentStack (which requires AgentCore + Data + Api
to be built first and is covered by CDK synthesis integration tests).
"""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import aws_iam as iam


def _new_stack() -> cdk.Stack:
    """Create a throwaway stack to host the policy factory call."""
    app = cdk.App()
    return cdk.Stack(app, "TestStack", env=cdk.Environment(account="111111111111", region="us-east-1"))


def test_search_ssm_policy_grants_only_search_prefix() -> None:
    """The policy must scope `ssm:GetParameter` to `/regain/search/*`."""
    # Import here to avoid loading CDK at module collection time.
    from infra.stacks.agent_stack import AgentStack  # noqa: WPS433

    # Grab the unbound method so we don't have to fully instantiate AgentStack,
    # which requires half a dozen cross-stack references. The method only
    # closes over `cdk.Aws.REGION` / `cdk.Aws.ACCOUNT_ID`, not `self`.
    statement = AgentStack._search_ssm_policy(None)  # type: ignore[arg-type]

    assert isinstance(statement, iam.PolicyStatement)
    rendered = statement.to_json()

    assert rendered["Action"] == "ssm:GetParameter"
    resource = rendered["Resource"]
    assert "parameter/regain/search/*" in resource
    # Must NOT be broader than /regain/search/*.
    assert "parameter/regain/*" not in resource
    assert "parameter/*" not in resource
