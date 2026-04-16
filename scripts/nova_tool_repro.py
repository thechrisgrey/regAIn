#!/usr/bin/env python3
"""Minimal repro for Nova Pro tool-routing reliability.

Hits live Bedrock + live DynamoDB (via the regain AWS profile) but runs
entirely locally — no Lambda involved. Builds a Strands Agent with a
configurable subset of the coaching tools, sends one user message, and
reports whether each tool was actually invoked.

Usage:
    AWS_PROFILE=regain AWS_DEFAULT_REGION=us-east-1 \\
        .venv/bin/python scripts/nova_tool_repro.py --tools 3 --user-id <sub>
    AWS_PROFILE=regain AWS_DEFAULT_REGION=us-east-1 \\
        .venv/bin/python scripts/nova_tool_repro.py --tools 18 --user-id <sub>

The --tools flag selects the tool subset size:
    3  = read_user_profile, update_user_profile, onet_search_careers
    18 = full production tool set
"""

import argparse
import logging
import os
import sys
from pathlib import Path

# Make the backend package importable
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("nova_repro")

# Silence noisy AWS/botocore logs
logging.getLogger("botocore").setLevel(logging.WARNING)
logging.getLogger("boto3").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

# Required env vars (point at production tables via the AWS profile)
os.environ.setdefault("USER_PROFILES_TABLE", "RegainUserProfiles")
os.environ.setdefault("CAMPAIGNS_TABLE", "RegainCampaigns")
os.environ.setdefault("MISSION_HISTORY_TABLE", "RegainMissionHistory")
os.environ.setdefault("EVIDENCE_VAULT_TABLE", "RegainEvidenceVault")
os.environ.setdefault("MARKET_DATA_TABLE", "RegainMarketData")
os.environ.setdefault("CALENDAR_TABLE", "RegainCalendar")
os.environ.setdefault("BEDROCK_MODEL_ID", "amazon.nova-pro-v1:0")
os.environ.setdefault("AWS_REGION", "us-east-1")


def build_tools(count: int):
    """Return a tool list of the requested size."""
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
    )

    all_tools = [
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
    ]

    if count == 3:
        return [read_user_profile, update_user_profile, onet_search_careers]
    if count == 18:
        return all_tools
    raise ValueError(f"Unsupported --tools value: {count} (use 3 or 18)")


def run_repro(
    tool_count: int,
    user_id: str,
    message: str,
    use_prod_prompt: bool,
    replay_history: bool,
    history_limit: int,
) -> int:
    from strands import Agent
    from strands.hooks import HookProvider, HookRegistry
    from strands.experimental.hooks import BeforeToolCallEvent, AfterToolCallEvent
    from strands.models.bedrock import BedrockModel

    tools = build_tools(tool_count)
    logger.info("Using %d tools: %s", len(tools), [t.__name__ for t in tools])

    invocations: list[dict] = []

    class TraceHook(HookProvider):
        def register_hooks(self, registry: HookRegistry) -> None:
            registry.add_callback(BeforeToolCallEvent, self.on_before)
            registry.add_callback(AfterToolCallEvent, self.on_after)

        def on_before(self, event: BeforeToolCallEvent) -> None:
            name = event.selected_tool.tool_name if event.selected_tool else "<unknown>"
            logger.info("BEFORE tool call: %s", name)
            invocations.append({"name": name, "status": "started"})

        def on_after(self, event: AfterToolCallEvent) -> None:
            name = event.selected_tool.tool_name if event.selected_tool else "<unknown>"
            logger.info("AFTER tool call: %s", name)
            for inv in invocations:
                if inv["name"] == name and inv["status"] == "started":
                    inv["status"] = "completed"
                    break

    if use_prod_prompt:
        from backend.agents.coaching.prompts import get_system_prompt
        system_prompt = get_system_prompt(
            valid_skill_tags=["Python Programming", "Leadership"],
            target_role="Senior Cloud Solutions Architect",
        )
    else:
        system_prompt = (
            "You are a career coaching assistant with tools available. "
            "When the user asks you to update their profile or set a target role, "
            "you MUST call the update_user_profile tool. Do not narrate without calling it."
        )

    logger.info("System prompt length: %d chars", len(system_prompt))

    model = BedrockModel(
        model_id=os.environ["BEDROCK_MODEL_ID"],
        region_name=os.environ["AWS_REGION"],
    )

    agent = Agent(
        model=model,
        system_prompt=system_prompt,
        tools=tools,
        hooks=[TraceHook()],
    )

    # Optionally replay the user's live DynamoDB thread history. Matches the
    # production code path in backend/agents/coaching/agent.py:248-261.
    if replay_history:
        import boto3
        ddb = boto3.resource("dynamodb", region_name=os.environ["AWS_REGION"])
        table = ddb.Table("RegainConversationThreads")
        row = table.get_item(Key={"userId": user_id, "threadId": "active"}).get("Item")
        turns = (row or {}).get("turns", [])
        if history_limit > 0:
            turns = turns[-history_limit:]
        logger.info("Replaying %d conversation turns into agent.messages", len(turns))
        first_user_seen = False
        for turn in turns:
            role = turn.get("role", "")
            content = turn.get("content", "")
            if role == "user":
                first_user_seen = True
                agent.messages.append({"role": "user", "content": [{"text": content}]})
            elif role == "assistant" and first_user_seen:
                agent.messages.append({"role": "assistant", "content": [{"text": content}]})

    # Inject the user_id context the way the production stream handler does —
    # by prepending it to the user message.
    user_message = f"[session_type=chat] [user_id={user_id}] {message}"

    logger.info("Sending user message: %s", message)
    logger.info("=" * 70)

    result = agent(user_message)

    logger.info("=" * 70)
    logger.info("Agent final text: %s", str(result)[:500])
    logger.info("=" * 70)
    logger.info("Tool invocations captured: %d", len(invocations))
    for inv in invocations:
        logger.info("  - %s (%s)", inv["name"], inv["status"])

    # Exit code: 0 if update_user_profile fired, 1 otherwise
    fired_update = any(inv["name"] == "update_user_profile" for inv in invocations)
    return 0 if fired_update else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tools", type=int, default=3, choices=[3, 18])
    parser.add_argument("--user-id", required=True, help="Cognito sub for the test user")
    parser.add_argument(
        "--message",
        default='Please set my target role to "Senior Software Engineer" using update_user_profile.',
    )
    parser.add_argument(
        "--prod-prompt",
        action="store_true",
        help="Use the production get_system_prompt instead of a minimal prompt",
    )
    parser.add_argument(
        "--replay-history",
        action="store_true",
        help="Replay the user's live DynamoDB thread turns before sending the message",
    )
    parser.add_argument(
        "--history-limit",
        type=int,
        default=0,
        help="When replaying, keep only the last N turns (0 = all)",
    )
    args = parser.parse_args()
    return run_repro(
        args.tools,
        args.user_id,
        args.message,
        args.prod_prompt,
        args.replay_history,
        args.history_limit,
    )


if __name__ == "__main__":
    sys.exit(main())
