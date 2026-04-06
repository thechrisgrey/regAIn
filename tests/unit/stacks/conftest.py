"""Shared fixtures for CDK stack tests.

Caches CDK synthesis results so that multiple tests can reuse the same
synthesized templates without re-running the full synthesis (~3s per run).
"""

import os
from functools import lru_cache

import aws_cdk as cdk
import pytest


@lru_cache(maxsize=1)
def _synth_all_templates() -> dict[str, dict]:
    """Synthesize the full CDK app once and cache all stack templates.

    Returns a dict mapping stack name to its CloudFormation template dict.
    """
    # Ensure layer stubs exist for synthesis
    os.makedirs("infra/layer_build/python", exist_ok=True)
    os.makedirs("infra/weasyprint_layer/python", exist_ok=True)
    os.makedirs("infra/weasyprint_layer/lib", exist_ok=True)
    os.makedirs("_layer/python", exist_ok=True)

    from infra.stacks.auth_stack import AuthStack
    from infra.stacks.data_stack import DataStack
    from infra.stacks.api_stack import ApiStack

    app = cdk.App()
    auth = AuthStack(app, "RegainAuthStack")
    data = DataStack(app, "RegainDataStack")
    ApiStack(app, "RegainApiStack", user_pool=auth.user_pool, tables=data.tables)
    assembly = app.synth()

    return {
        stack.stack_name: stack.template
        for stack in [
            assembly.get_stack_by_name("RegainAuthStack"),
            assembly.get_stack_by_name("RegainDataStack"),
            assembly.get_stack_by_name("RegainApiStack"),
        ]
    }


@pytest.fixture(scope="session")
def all_templates() -> dict[str, dict]:
    """Session-scoped fixture providing all synthesized stack templates."""
    return _synth_all_templates()


@pytest.fixture(scope="session")
def api_template(all_templates: dict[str, dict]) -> dict:
    """Session-scoped fixture providing the ApiStack template."""
    return all_templates["RegainApiStack"]


@pytest.fixture(scope="session")
def auth_template(all_templates: dict[str, dict]) -> dict:
    """Session-scoped fixture providing the AuthStack template."""
    return all_templates["RegainAuthStack"]


@pytest.fixture(scope="session")
def data_template(all_templates: dict[str, dict]) -> dict:
    """Session-scoped fixture providing the DataStack template."""
    return all_templates["RegainDataStack"]
