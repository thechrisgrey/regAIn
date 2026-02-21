"""Coaching Agent configuration for the REGAIN platform.

Creates and configures the Strands Coaching Agent with model, tools,
and system prompt. Detects whether AgentCore Gateway is provisioned:

- If Gateway is available → discover tools via GatewayToolClient
  (centralized auth, policy, and observability).
- If Gateway is pending → use direct @tool functions from tools.py
  (local invocation, no Gateway dependency).

Agent configuration lives here; business logic lives in tools.py;
persona definition lives in prompts.py.
"""

import logging
import os

from strands import Agent
from strands.models.bedrock import BedrockModel

from backend.agents.coaching.prompts import get_system_prompt

logger = logging.getLogger(__name__)

_PENDING = "pending-agentcore-deploy"


def _is_gateway_available() -> bool:
    """Check if AgentCore Gateway is provisioned and ready."""
    endpoint = os.environ.get("AGENTCORE_GATEWAY_ENDPOINT", "")
    return bool(endpoint) and endpoint != _PENDING


def _get_gateway_tools(jwt_token: str):
    """Discover tools from AgentCore Gateway (lazy import)."""
    from backend.agents.coaching.gateway_client import GatewayToolClient

    gateway_id = os.environ.get("AGENTCORE_GATEWAY_ID", "regain-coaching-gateway")
    client = GatewayToolClient(gateway_id, jwt_token)
    return client.discover_tools()


def _get_direct_tools() -> list:
    """Return direct @tool functions for local invocation (lazy import)."""
    from backend.agents.coaching.tools import (
        read_user_profile,
        update_user_profile,
        get_campaign_status,
        create_campaign,
        get_current_mission,
        generate_mission,
        complete_mission,
        log_evidence,
        get_evidence_summary,
        get_market_insights,
        get_alignment,
        recall_memory,
        store_memory,
    )

    return [
        read_user_profile,
        update_user_profile,
        get_campaign_status,
        create_campaign,
        get_current_mission,
        generate_mission,
        complete_mission,
        log_evidence,
        get_evidence_summary,
        get_market_insights,
        get_alignment,
        recall_memory,
        store_memory,
    ]


def create_coaching_agent(user_id: str, jwt_token: str) -> Agent:
    """Create a Coaching Agent with tools routed through Gateway or invoked directly.

    Detects Gateway availability via the AGENTCORE_GATEWAY_ENDPOINT env var.
    If the endpoint is "pending-agentcore-deploy" or empty, falls back to
    direct @tool function invocation from tools.py.

    Args:
        user_id: The authenticated user's ID. Kept for future
            memory-namespace scoping.
        jwt_token: The user's Cognito JWT for Gateway authorization.

    Returns:
        A configured Strands Agent.
    """
    if _is_gateway_available():
        logger.info("Using AgentCore Gateway tools")
        tools = _get_gateway_tools(jwt_token)
    else:
        logger.info("Gateway not provisioned, using direct tool invocation")
        tools = _get_direct_tools()

    model = BedrockModel(
        model_id=os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0"),
        region_name=os.environ.get("AWS_REGION", "us-east-1"),
    )

    return Agent(
        model=model,
        system_prompt=get_system_prompt(),
        tools=tools,
    )
