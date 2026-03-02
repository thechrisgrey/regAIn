"""CDK assertion tests for WebSocket WAF and EventBridge DLQ.

Verifies that:
- AgentStack has WAF WebACLs and associations for both WebSocket APIs
- VoicePracticeStack has WAF WebACL and association for its WebSocket API
- MarketIntelStack has an SQS DLQ for EventBridge targets
"""

import aws_cdk as cdk

from infra.stacks.auth_stack import AuthStack
from infra.stacks.data_stack import DataStack
from infra.stacks.api_stack import ApiStack
from infra.stacks.agent_stack import AgentStack
from infra.stacks.voice_practice_stack import VoicePracticeStack
from infra.stacks.market_intel_stack import MarketIntelStack

_ACCOUNT = "563170906428"
_REGION = "us-east-1"


def _synth_all() -> dict[str, dict]:
    """Synthesize the relevant stacks and return their templates."""
    app = cdk.App()
    env = cdk.Environment(account=_ACCOUNT, region=_REGION)

    auth_stack = AuthStack(app, "RegainAuthStack", env=env)
    data_stack = DataStack(app, "RegainDataStack", env=env)
    api_stack = ApiStack(
        app, "RegainApiStack",
        user_pool=auth_stack.user_pool,
        tables=data_stack.tables,
        env=env,
    )

    agent_stack = AgentStack(
        app, "RegainAgentStack",
        user_pool=auth_stack.user_pool,
        tables=data_stack.tables,
        coaching_lambda=api_stack.coaching_lambda,
        resume_lambda_arn=f"arn:aws:lambda:{_REGION}:{_ACCOUNT}:function:RegainResume",
        resume_bucket_name=f"regain-resume-{_ACCOUNT}",
        env=env,
    )

    voice_practice_stack = VoicePracticeStack(
        app, "RegainVoicePracticeStack",
        user_pool=auth_stack.user_pool,
        tables=data_stack.tables,
        api=api_stack.api,
        profile_lambda=api_stack.profile_lambda,
        env=env,
    )

    market_intel_stack = MarketIntelStack(
        app, "RegainMarketIntelStack",
        tables=data_stack.tables,
        env=env,
    )

    assembly = app.synth()
    return {
        "AgentStack": assembly.get_stack_by_name("RegainAgentStack").template,
        "VoicePracticeStack": assembly.get_stack_by_name("RegainVoicePracticeStack").template,
        "MarketIntelStack": assembly.get_stack_by_name("RegainMarketIntelStack").template,
    }


def _count_resources(template: dict, resource_type: str) -> int:
    """Count resources of a given type in a CloudFormation template."""
    return sum(
        1 for res in template.get("Resources", {}).values()
        if res.get("Type") == resource_type
    )


class TestAgentStackWebACL:
    """Verify AgentStack has WAF WebACLs for both WebSocket APIs."""

    def test_agent_stack_has_webacl(self):
        templates = _synth_all()
        count = _count_resources(templates["AgentStack"], "AWS::WAFv2::WebACL")
        assert count >= 2, f"Expected >= 2 WAFv2 WebACLs in AgentStack, found {count}"

    def test_agent_stack_has_webacl_associations(self):
        templates = _synth_all()
        count = _count_resources(templates["AgentStack"], "AWS::WAFv2::WebACLAssociation")
        assert count >= 2, f"Expected >= 2 WAFv2 WebACLAssociations in AgentStack, found {count}"


class TestVoicePracticeStackWebACL:
    """Verify VoicePracticeStack has WAF WebACL for its WebSocket API."""

    def test_voice_practice_has_webacl(self):
        templates = _synth_all()
        count = _count_resources(templates["VoicePracticeStack"], "AWS::WAFv2::WebACL")
        assert count >= 1, f"Expected >= 1 WAFv2 WebACL in VoicePracticeStack, found {count}"

    def test_voice_practice_has_webacl_association(self):
        templates = _synth_all()
        count = _count_resources(templates["VoicePracticeStack"], "AWS::WAFv2::WebACLAssociation")
        assert count >= 1, f"Expected >= 1 WAFv2 WebACLAssociation in VoicePracticeStack, found {count}"


class TestMarketIntelStackDLQ:
    """Verify MarketIntelStack has SQS DLQ for EventBridge targets."""

    def test_market_intel_has_sqs_queue(self):
        templates = _synth_all()
        count = _count_resources(templates["MarketIntelStack"], "AWS::SQS::Queue")
        assert count >= 1, f"Expected >= 1 SQS Queue in MarketIntelStack, found {count}"
