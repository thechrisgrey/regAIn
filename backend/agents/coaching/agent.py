"""Coaching Agent configuration for the REGAIN platform.

Creates and configures the Strands Coaching Agent with model, tools,
session manager (AgentCore Memory), and system prompt.

Agent configuration lives here; business logic lives in tools.py;
persona definition lives in prompts.py.
"""

import logging
import os
import uuid
from collections import OrderedDict
from typing import Any, Dict

from strands import Agent
from strands.models.bedrock import BedrockModel

from backend.agents.coaching.prompts import get_system_prompt

logger = logging.getLogger(__name__)

_PENDING = "pending-agentcore-deploy"

# Beyond ~30 text-only turns, Nova Pro pattern-matches prior assistant
# narrative and skips tool invocation. Only applies to the fallback
# path — AgentCoreMemorySessionManager replays full tool_use/tool_result.
MAX_REPLAYED_TURNS = 15

_MAX_CACHE_SIZE = 50
_component_cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()


def evict_cached_components(cache_key: str) -> None:
    """Remove a cached component set, e.g. on WebSocket disconnect."""
    _component_cache.pop(cache_key, None)


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
        generate_resume,
        get_resume,
        read_calendar,
        write_calendar_entry,
        onet_search_careers,
        onet_career_detail,
        web_search,
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
        generate_resume,
        get_resume,
        read_calendar,
        write_calendar_entry,
        onet_search_careers,
        onet_career_detail,
        web_search,
    ]


def _create_session_manager(user_id: str, session_id: str | None = None):
    """Create an AgentCoreMemorySessionManager for automatic turn storage.

    Args:
        user_id: The authenticated user's ID.
        session_id: Optional explicit session ID (e.g. WebSocket connection_id).
            Falls back to a random ``session-<hex>`` value when not provided.

    Returns None if the memory ID is not configured or initialization fails.
    The agent will run without memory in that case (graceful degradation).
    """
    memory_id = os.environ.get("AGENTCORE_MEMORY_ID", "")
    if not memory_id or memory_id == _PENDING:
        logger.info("AGENTCORE_MEMORY_ID not set; running without memory")
        return None

    resolved_session_id = session_id or f"session-{uuid.uuid4().hex[:12]}"

    try:
        from bedrock_agentcore.memory.integrations.strands.config import (
            AgentCoreMemoryConfig,
        )
        from bedrock_agentcore.memory.integrations.strands.session_manager import (
            AgentCoreMemorySessionManager,
        )

        config = AgentCoreMemoryConfig(
            memory_id=memory_id,
            actor_id=user_id,
            session_id=resolved_session_id,
            retrieval_config=None,
        )
        return AgentCoreMemorySessionManager(
            agentcore_memory_config=config,
            region_name=os.environ.get("AWS_REGION", "us-east-1"),
        )
    except Exception:
        logger.warning("Failed to create AgentCoreMemorySessionManager", exc_info=True)
        return None


import re

_NOISE_TOKEN_RE = re.compile(
    r"\[page_context:\s*\w+\]\s*"
    r"|\[page_data:\s*\{[^}]*\}\]\s*"
    r"|\[proactive_check\]\s*"
)


def _is_noise_turn(turn: dict) -> bool:
    """Return True if this conversation turn is background noise that
    should not be replayed."""
    role = turn.get("role", "")
    content = turn.get("content", "") or ""
    stripped = content.strip()

    if role == "user" and "[proactive_check]" in stripped:
        return True
    if role == "assistant" and stripped == "[no_suggestion]":
        return True
    if role == "user" and stripped.startswith("[page_context:"):
        remainder = _NOISE_TOKEN_RE.sub("", stripped).strip()
        if not remainder:
            return True
    return False


def create_coaching_agent(
    user_id: str,
    jwt_token: str,
    callback_handler=None,
    hooks: list | None = None,
    conversation_history: list | None = None,
    attention_mode: str = "explore",
    session_id: str | None = None,
    cache_key: str | None = None,
) -> Agent:
    """Create a Coaching Agent with tools, memory session manager, and system prompt.

    Args:
        user_id: The authenticated user's ID.
        jwt_token: The user's Cognito JWT for Gateway authorization.
        callback_handler: Optional callback for streaming text chunks.
        hooks: Optional list of HookProvider instances for lifecycle events.
        conversation_history: Optional list of prior conversation turns to load into agent context.
        attention_mode: The user's current attention mode ('dnd' or 'explore'). Default 'explore'.
        session_id: Optional explicit session ID for AgentCore Memory (e.g. WebSocket connection_id).
            Falls back to a random UUID when not provided.
        cache_key: Optional key (e.g. WebSocket connection_id) for reusing expensive
            components (tools, model, session_manager, system_prompt) across calls.
            When set, the first call computes and stores; subsequent calls reuse.

    Returns:
        A configured Strands Agent.
    """
    cache_hit = cache_key and cache_key in _component_cache
    if cache_hit:
        _component_cache.move_to_end(cache_key)
        cached = _component_cache[cache_key]
        tools = cached["tools"]
        model = cached["model"]
        session_manager = cached["session_manager"]
        system_prompt = cached["system_prompt"]
        tool_names = [getattr(t, "__name__", getattr(t, "TOOL_SPEC", {}).get("name", str(t))) for t in tools] if isinstance(tools, list) else []
        logger.info("Agent cache HIT for %s — tools: %s", cache_key, tool_names)
    else:
        # Gateway tool discovery is disabled — the Strands version in the
        # Lambda layer rejects the ModuleType tool format produced by
        # GatewayToolClient, resulting in zero usable tools.  Use direct
        # @tool functions which Strands recognises natively.
        tools = _get_direct_tools()
        tool_names = [getattr(t, "__name__", "?") for t in tools]
        logger.info("Loaded %d direct tools: %s", len(tools), tool_names)

        from backend.agents.coaching.tools import (
            get_valid_skill_tags,
            db as _tools_db,
        )

        valid_tags = get_valid_skill_tags(user_id)

        # Fetch target_role for prompt grounding. Failure is non-fatal —
        # the prompt falls back to "(not yet set)".
        target_role: str | None = None
        try:
            profile = _tools_db.get_item("user_profiles", {"userId": user_id})
            if profile:
                raw = profile.get("targetRole")
                if isinstance(raw, str) and raw.strip():
                    target_role = raw.strip()
        except Exception:
            logger.warning("Could not read targetRole for %s", user_id, exc_info=True)

        system_prompt = get_system_prompt(
            valid_skill_tags=valid_tags,
            attention_mode=attention_mode,
            target_role=target_role,
        )

        model = BedrockModel(
            model_id=os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0"),
            region_name=os.environ.get("AWS_REGION", "us-east-1"),
        )

        session_manager = _create_session_manager(user_id, session_id=session_id)

        if cache_key:
            _component_cache[cache_key] = {
                "tools": tools,
                "model": model,
                "session_manager": session_manager,
                "system_prompt": system_prompt,
            }
            if len(_component_cache) > _MAX_CACHE_SIZE:
                _component_cache.popitem(last=False)

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

    # Dual-storage contract:
    #   DynamoDB ConversationThreads = source of truth for ordered thread history.
    #   AgentCore Memory (SessionManager) = long-term semantic recall across sessions.
    #
    # Only replay DynamoDB thread turns when the SessionManager did NOT already
    # restore messages (i.e. new session or no session_manager). If the
    # SessionManager restored an existing session, agent.messages is already
    # populated and appending thread turns would duplicate context.
    session_restored = session_manager is not None and agent.messages
    if conversation_history and not session_restored:
        filtered = [t for t in conversation_history if not _is_noise_turn(t)]
        recent_turns = filtered[-MAX_REPLAYED_TURNS:]

        # Bedrock requires the first message to be role=user.  Skip any
        # assistant turns that appear before the first user turn (can happen
        # when action_event proactive responses are saved without a
        # corresponding user turn).
        first_user_seen = False
        for turn in recent_turns:
            role = turn.get("role", "")
            content = turn.get("content", "")
            if role == "user":
                first_user_seen = True
                agent.messages.append({"role": "user", "content": [{"text": content}]})
            elif role == "assistant" and first_user_seen:
                agent.messages.append({"role": "assistant", "content": [{"text": content}]})

    return agent
