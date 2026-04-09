#!/usr/bin/env python3
"""REGAIN Platform — CDK Application Entry Point."""
import os

import aws_cdk as cdk
from stacks.auth_stack import AuthStack
from stacks.data_stack import DataStack
from stacks.api_stack import ApiStack
from stacks.agent_stack import AgentStack
from stacks.agentcore_stack import AgentCoreStack
from stacks.market_intel_stack import MarketIntelStack
from stacks.resume_stack import ResumeStack
from stacks.voice_practice_stack import VoicePracticeStack
from stacks.score_stack import ScoreStack

_ACCOUNT = os.environ.get("CDK_DEFAULT_ACCOUNT", "563170906428")
_REGION = os.environ.get("CDK_DEFAULT_REGION", "us-east-1")

app = cdk.App()

env = cdk.Environment(
    account=_ACCOUNT,
    region=_REGION,
)

auth_stack = AuthStack(app, "RegainAuthStack", env=env)
data_stack = DataStack(app, "RegainDataStack", env=env)
api_stack = ApiStack(
    app,
    "RegainApiStack",
    user_pool=auth_stack.user_pool,
    tables=data_stack.tables,
    env=env,
)

resume_stack = ResumeStack(
    app,
    "RegainResumeStack",
    user_pool=auth_stack.user_pool,
    tables=data_stack.tables,
    api=api_stack.api,
    profile_lambda=api_stack.profile_lambda,
    env=env,
)

voice_practice_stack = VoicePracticeStack(
    app,
    "RegainVoicePracticeStack",
    user_pool=auth_stack.user_pool,
    tables=data_stack.tables,
    api=api_stack.api,
    profile_lambda=api_stack.profile_lambda,
    env=env,
)

market_intel_stack = MarketIntelStack(
    app,
    "RegainMarketIntelStack",
    tables=data_stack.tables,
    env=env,
)

score_stack = ScoreStack(
    app,
    "RegainScoreStack",
    tables=data_stack.tables,
    api=api_stack.api,
    user_pool=auth_stack.user_pool,
    env=env,
)

# AgentCoreStack must be created before AgentStack so Gateway ID/endpoint
# are available as cross-stack references for Lambda env vars.
agentcore_stack = AgentCoreStack(
    app,
    "RegainAgentCoreStack",
    coaching_lambda=api_stack.coaching_lambda,
    missions_lambda=api_stack.missions_lambda,
    evidence_lambda=api_stack.evidence_lambda,
    dashboard_lambda=api_stack.dashboard_lambda,
    profile_lambda=api_stack.profile_lambda,
    user_pool=auth_stack.user_pool,
    env=env,
)

# Set AGENTCORE_MEMORY_ID on profile Lambda via Fn.import_value to avoid
# cyclic cross-stack reference (profile Lambda is owned by ApiStack).
# On bootstrap deploys (skip_alert_import=true), AgentCoreStack doesn't
# exist yet so Fn::ImportValue would fail.
_skip_bootstrap = app.node.try_get_context("skip_alert_import")
if not _skip_bootstrap:
    api_stack.profile_lambda.add_environment(
        "AGENTCORE_MEMORY_ID",
        cdk.Fn.import_value("RegainAgentCoreMemoryId"),
    )
    voice_practice_stack.ws_lambda.add_environment(
        "AGENTCORE_MEMORY_ID",
        cdk.Fn.import_value("RegainAgentCoreMemoryId"),
    )
else:
    api_stack.profile_lambda.add_environment(
        "AGENTCORE_MEMORY_ID", "pending-memory-deploy",
    )

agent_stack = AgentStack(
    app,
    "RegainAgentStack",
    user_pool=auth_stack.user_pool,
    tables=data_stack.tables,
    coaching_lambda=api_stack.coaching_lambda,
    # Use plain strings (not construct references) to avoid cyclic dependency:
    # ResumeStack → ApiStack (for api) would cycle with ApiStack → ResumeStack.
    resume_lambda_arn=f"arn:aws:lambda:{_REGION}:{_ACCOUNT}:function:RegainResume",
    resume_bucket_name=f"regain-resume-{_ACCOUNT}",
    gateway_id=agentcore_stack.gateway_id,
    gateway_endpoint=agentcore_stack.gateway_endpoint,
    memory_id=agentcore_stack.memory_id,
    env=env,
)

cdk.Tags.of(app).add("Project", "REGAIN")
cdk.Tags.of(app).add("Environment", "dev")

# Cost allocation tags per stack
for stack, service in [
    (auth_stack, "Auth"),
    (data_stack, "Data"),
    (api_stack, "Api"),
    (resume_stack, "Resume"),
    (voice_practice_stack, "VoicePractice"),
    (market_intel_stack, "MarketIntel"),
    (agentcore_stack, "AgentCore"),
    (agent_stack, "Agent"),
    (score_stack, "Score"),
]:
    cdk.Tags.of(stack).add("Service", service)

app.synth()
