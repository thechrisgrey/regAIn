"""CDK assertion tests for EventBridge DLQ.

Verifies that MarketIntelStack has an SQS DLQ for EventBridge targets.

Note: WAFv2 does not support API Gateway v2 WebSocket APIs, so WAF
protection is not applied to WebSocket stages.
"""

import aws_cdk as cdk

from infra.stacks.auth_stack import AuthStack
from infra.stacks.data_stack import DataStack
from infra.stacks.api_stack import ApiStack
from infra.stacks.market_intel_stack import MarketIntelStack

_ACCOUNT = "563170906428"
_REGION = "us-east-1"


def _synth_market_intel() -> dict:
    """Synthesize the MarketIntelStack and return its template."""
    app = cdk.App()
    env = cdk.Environment(account=_ACCOUNT, region=_REGION)

    auth_stack = AuthStack(app, "RegainAuthStack", env=env)
    data_stack = DataStack(app, "RegainDataStack", env=env)
    ApiStack(
        app, "RegainApiStack",
        user_pool=auth_stack.user_pool,
        tables=data_stack.tables,
        env=env,
    )

    MarketIntelStack(
        app, "RegainMarketIntelStack",
        tables=data_stack.tables,
        env=env,
    )

    assembly = app.synth()
    return assembly.get_stack_by_name("RegainMarketIntelStack").template


def _count_resources(template: dict, resource_type: str) -> int:
    """Count resources of a given type in a CloudFormation template."""
    return sum(
        1 for res in template.get("Resources", {}).values()
        if res.get("Type") == resource_type
    )


class TestMarketIntelStackDLQ:
    """Verify MarketIntelStack has SQS DLQ for EventBridge targets."""

    def test_market_intel_has_sqs_queue(self):
        template = _synth_market_intel()
        count = _count_resources(template, "AWS::SQS::Queue")
        assert count >= 1, f"Expected >= 1 SQS Queue in MarketIntelStack, found {count}"
