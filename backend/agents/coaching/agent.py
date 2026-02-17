"""Coaching Agent configuration for the REGAIN platform.

Creates and configures the Strands Coaching Agent with model, tools,
and system prompt. Agent configuration lives here; business logic
lives in tools.py; persona definition lives in prompts.py.
"""

import importlib
import os

from strands import Agent
from strands.models.bedrock import BedrockModel

from backend.agents.coaching.prompts import get_system_prompt

# 'lambda' is a Python keyword in the module path, so tools.py already
# handles its own imports via importlib.  We import the decorated tool
# functions directly from the sibling module.
_tools_mod = importlib.import_module("backend.agents.coaching.tools")

_ALL_TOOLS = [
    _tools_mod.read_user_profile,
    _tools_mod.update_user_profile,
    _tools_mod.get_campaign_status,
    _tools_mod.create_campaign,
    _tools_mod.get_current_mission,
    _tools_mod.generate_mission,
    _tools_mod.complete_mission,
    _tools_mod.log_evidence,
    _tools_mod.get_evidence_summary,
    _tools_mod.get_market_insights,
    _tools_mod.recall_memory,
    _tools_mod.store_memory,
]


def create_coaching_agent(user_id: str) -> Agent:
    """Create a configured Coaching Agent instance for a specific user.

    Builds a Strands Agent wired to Amazon Nova Lite (or the model
    specified by BEDROCK_MODEL_ID) with all 12 coaching tools and the
    system prompt from prompts.py.

    Args:
        user_id: The authenticated user's ID. Accepted for future
            memory-namespace scoping but not used in the current
            implementation.

    Returns:
        A configured Strands Agent ready to process messages.
    """
    model = BedrockModel(
        model_id=os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0"),
        region_name=os.environ.get("AWS_REGION", "us-east-1"),
    )

    agent = Agent(
        model=model,
        system_prompt=get_system_prompt(),
        tools=_ALL_TOOLS,
    )
    return agent
