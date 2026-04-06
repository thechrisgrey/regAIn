"""Coaching Agent configuration for the REGAIN platform.

Creates and configures the Strands Coaching Agent with model, tools,
session manager (AgentCore Memory), and system prompt.

Agent configuration lives here; business logic lives in tools.py;
persona definition lives in prompts.py.
"""

import logging
import os
import uuid

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
    ]


def _create_session_manager(user_id: str):
    """Create an AgentCoreMemorySessionManager for automatic turn storage.

    Returns None if the memory ID is not configured or initialization fails.
    The agent will run without memory in that case (graceful degradation).
    """
    memory_id = os.environ.get("AGENTCORE_MEMORY_ID", "")
    if not memory_id or memory_id == _PENDING:
        logger.info("AGENTCORE_MEMORY_ID not set; running without memory")
        return None

    try:
        from bedrock_agentcore.memory.integrations.strands.config import (
            AgentCoreMemoryConfig,
            RetrievalConfig,
        )
        from bedrock_agentcore.memory.integrations.strands.session_manager import (
            AgentCoreMemorySessionManager,
        )

        config = AgentCoreMemoryConfig(
            memory_id=memory_id,
            actor_id=user_id,
            session_id=f"session-{uuid.uuid4().hex[:12]}",
            retrieval_config=RetrievalConfig(),
        )
        return AgentCoreMemorySessionManager(
            agentcore_memory_config=config,
            region_name=os.environ.get("AWS_REGION", "us-east-1"),
        )
    except Exception:
        logger.warning("Failed to create AgentCoreMemorySessionManager", exc_info=True)
        return None


def create_coaching_agent(
    user_id: str,
    jwt_token: str,
    callback_handler=None,
    hooks: list | None = None,
    conversation_history: list | None = None,
    attention_mode: str = "focus",
) -> Agent:
    """Create a Coaching Agent with tools, memory session manager, and system prompt.

    Args:
        user_id: The authenticated user's ID.
        jwt_token: The user's Cognito JWT for Gateway authorization.
        callback_handler: Optional callback for streaming text chunks.
        hooks: Optional list of HookProvider instances for lifecycle events.
        conversation_history: Optional list of prior conversation turns to load into agent context.
        attention_mode: The user's current attention mode ('dnd', 'focus', or 'explore'). Default 'focus'.

    Returns:
        A configured Strands Agent.
    """
    from backend.agents.coaching.circuit_breaker import gateway_circuit

    if _is_gateway_available() and not gateway_circuit.is_open:
        try:
            logger.info("Using AgentCore Gateway tools")
            tools = _get_gateway_tools(jwt_token)
            gateway_circuit.record_success()
        except Exception:
            logger.warning("Gateway tool discovery failed, falling back to direct tools")
            gateway_circuit.record_failure()
            tools = _get_direct_tools()
    else:
        if gateway_circuit.is_open:
            logger.info("Gateway circuit open, using direct tool invocation")
        else:
            logger.info("Gateway not provisioned, using direct tool invocation")
        tools = _get_direct_tools()

    from backend.agents.coaching.tools import get_valid_skill_tags

    valid_tags = get_valid_skill_tags(user_id)
    system_prompt = get_system_prompt(
        valid_skill_tags=valid_tags,
        attention_mode=attention_mode,
    )

    model = BedrockModel(
        model_id=os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0"),
        region_name=os.environ.get("AWS_REGION", "us-east-1"),
    )

    session_manager = _create_session_manager(user_id)

    kwargs: dict = {
        "model": model,
        "system_prompt": system_prompt,
        "tools": tools,
    }
    if session_manager is not None:
        kwargs["session_manager"] = session_manager
    if callback_handler is not None:
        kwargs["callback_handler"] = callback_handler
    if hooks:
        kwargs["hooks"] = hooks

    agent = Agent(**kwargs)

    if conversation_history:
        for turn in conversation_history:
            role = turn.get("role", "")
            content = turn.get("content", "")
            if role == "user":
                agent.messages.append({"role": "user", "content": [{"text": content}]})
            elif role == "assistant":
                agent.messages.append({"role": "assistant", "content": [{"text": content}]})

    return agent
