#!/usr/bin/env python3
"""REGAIN Platform — CDK Application Entry Point."""
import aws_cdk as cdk

app = cdk.App()

env = cdk.Environment(
    account="563170906428",
    region="us-east-1",
)

# Stacks will be instantiated here as they are implemented.
# See Task 8 for full wiring of AuthStack, DataStack, and ApiStack.

cdk.Tags.of(app).add("Project", "REGAIN")
cdk.Tags.of(app).add("Environment", "dev")

app.synth()
