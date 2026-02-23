#!/usr/bin/env python3
"""REGAIN Platform — CDK Application Entry Point."""
import aws_cdk as cdk
from stacks.auth_stack import AuthStack
from stacks.data_stack import DataStack
from stacks.api_stack import ApiStack
from stacks.agent_stack import AgentStack
from stacks.agentcore_stack import AgentCoreStack
from stacks.market_intel_stack import MarketIntelStack
from stacks.resume_stack import ResumeStack
from stacks.voice_practice_stack import VoicePracticeStack

app = cdk.App()

env = cdk.Environment(
    account="563170906428",
    region="us-east-1",
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

agent_stack = AgentStack(
    app,
    "RegainAgentStack",
    user_pool=auth_stack.user_pool,
    tables=data_stack.tables,
    coaching_lambda=api_stack.coaching_lambda,
    # Use plain strings (not construct references) to avoid cyclic dependency:
    # ResumeStack → ApiStack (for api) would cycle with ApiStack → ResumeStack.
    resume_lambda_arn=f"arn:aws:lambda:us-east-1:563170906428:function:RegainResume",
    resume_bucket_name=f"regain-resume-563170906428",
    env=env,
)

market_intel_stack = MarketIntelStack(
    app,
    "RegainMarketIntelStack",
    tables=data_stack.tables,
    env=env,
)

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

cdk.Tags.of(app).add("Project", "REGAIN")
cdk.Tags.of(app).add("Environment", "dev")

app.synth()
