"""Coaching Agent configuration for the REGAIN platform.

Creates and configures the Strands Coaching Agent with model, tools,
and system prompt. Tools are discovered from AgentCore Gateway instead
of direct imports, routing all invocations through centralized auth,
policy, and observability layers.

Agent configuration lives here; business logic lives in tools.py;
persona definition lives in prompts.py.
"""

import os

from strands import Agent
from strands.models.bedrock import BedrockModel

from backend.agents.coaching.gateway_client import GatewayToolClient
from backend.agents.coaching.prompts import get_system_prompt


def create_coaching_agent(user_id: str, jwt_token: str) -> Agent:
    """Create a Coaching Agent that routes tools through AgentCore Gateway.

    Discovers available tools from the AgentCore Gateway MCP endpoint
    instead of importing tool functions directly. All 13 tools
    (including get_alignment) are discovered automatically from the
    Gateway registry.

    Args:
        user_id: The authenticated user's ID. Kept for future
            memory-namespace scoping.
        jwt_token: The user's Cognito JWT for Gateway authorization.

    Returns:
        A configured Strands Agent with Gateway-routed tools.
    """
    gateway_id = os.environ.get("AGENTCORE_GATEWAY_ID", "regain-coaching-gateway")
    gateway_client = GatewayToolClient(gateway_id, jwt_token)
    gateway_tools = gateway_client.discover_tools()

    model = BedrockModel(
        model_id=os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0"),
        region_name=os.environ.get("AWS_REGION", "us-east-1"),
    )

    return Agent(
        model=model,
        system_prompt=get_system_prompt(),
        tools=gateway_tools,
    )
