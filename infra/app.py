#!/usr/bin/env python3
"""REGAIN Platform — CDK Application Entry Point."""
import aws_cdk as cdk
from stacks.auth_stack import AuthStack
from stacks.data_stack import DataStack

app = cdk.App()

env = cdk.Environment(
    account="563170906428",
    region="us-east-1",
)

auth_stack = AuthStack(app, "RegainAuthStack", env=env)
data_stack = DataStack(app, "RegainDataStack", env=env)

# Remaining stacks will be instantiated here as they are implemented.
# See Task 8 for full wiring of ApiStack.

cdk.Tags.of(app).add("Project", "REGAIN")
cdk.Tags.of(app).add("Environment", "dev")

app.synth()
