#!/usr/bin/env python3
"""REGAIN Platform — CDK Application Entry Point."""
import aws_cdk as cdk
from stacks.auth_stack import AuthStack
from stacks.data_stack import DataStack
from stacks.api_stack import ApiStack
from stacks.agent_stack import AgentStack

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

agent_stack = AgentStack(
    app,
    "RegainAgentStack",
    user_pool=auth_stack.user_pool,
    tables=data_stack.tables,
    coaching_lambda=api_stack.coaching_lambda,
    env=env,
)

cdk.Tags.of(app).add("Project", "REGAIN")
cdk.Tags.of(app).add("Environment", "dev")

app.synth()
