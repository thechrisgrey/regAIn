# AgentCore Memory Session Fix + Agent Caching

**Date:** 2026-04-07
**Branch:** TBD (from main, post-merge of feat/always-on-coaching-agent)

## Problem

Two inefficiencies in the coaching agent's per-message lifecycle:

1. **Orphaned AgentCore Memory sessions.** `_create_session_manager()` in `agent.py:95` generates `session_id=f"session-{uuid.uuid4().hex[:12]}"` on every call. Since `create_coaching_agent()` is called per WebSocket message, each message creates a new AgentCore Memory session. Short-term memory turns can never accumulate within a session, and cross-turn strategies (summarization, preference extraction) are broken.

2. **Redundant agent reconstruction.** Every message triggers: tool discovery + circuit breaker check, `get_valid_skill_tags()` DynamoDB query, `get_system_prompt()` assembly, `BedrockModel()` initialization, and `AgentCoreMemorySessionManager` creation. Within a single WebSocket session (same `connection_id`), these are stable and don't need to be rebuilt.

## Solution

### 1. Stable Session ID

Pass `connection_id` from `stream_handler.py` through `create_coaching_agent()` to `_create_session_manager()` as the `session_id`. This anchors AgentCore Memory's short-term turns to the WebSocket session lifetime, matching the intended Strands SDK pattern (one session manager, multiple `agent()` calls).

The REST handler (`service.py`) continues using a UUID — each REST call is a standalone interaction with no session continuity.

**Changes:**
- `agent.py`: Add `session_id: str | None = None` parameter to `_create_session_manager()`. Use it when provided, fall back to UUID when `None`.
- `agent.py`: Add `session_id: str | None = None` parameter to `create_coaching_agent()`. Pass through to `_create_session_manager()`.
- `stream_handler.py`: Pass `connection_id` as `session_id` in all `create_coaching_agent()` call sites (regular chat, action event response, compact agent).

### 2. Module-Level Agent Cache

Add `_cached_agents: dict[str, Agent] = {}` at module level in `stream_handler.py`, keyed by `connection_id`.

**Cache lifecycle:**

| Event | Action |
|-------|--------|
| Regular chat message (cache miss) | Create agent via `create_coaching_agent(session_id=connection_id, conversation_history=thread["turns"])`, store in `_cached_agents[connection_id]` |
| Regular chat message (cache hit) | Reuse cached agent. Skip `create_coaching_agent()` entirely |
| `attention_mode` change | Evict `_cached_agents[connection_id]` — next message rebuilds with new mode |
| Auto-compaction triggers | Evict `_cached_agents[connection_id]` — agent's `messages` list is stale relative to compacted thread |
| `$disconnect` | Delete `_cached_agents.pop(connection_id, None)` |
| `action_event` / `compact` | No caching — these create purpose-specific throwaway agents |

**What runs on every message (even cache hit):**
- `load_active_thread()` — needed for token budget check + auto-compact decision
- Streaming callback + tool hooks creation (per-invocation)
- Turn persistence to ConversationThreads DynamoDB table

**What's skipped on cache hit:**
- Tool loading / gateway circuit breaker check
- `get_valid_skill_tags()` DynamoDB query
- `get_system_prompt()` assembly
- `BedrockModel()` initialization
- `AgentCoreMemorySessionManager` creation
- Conversation history injection (agent's `messages` list already has prior turns)

**Multi-container safety:** API Gateway WebSocket routes have no Lambda instance affinity. A different container won't have a cached agent and falls back to fresh creation with DynamoDB thread history. No correctness issue — caching is a performance optimization, not a correctness requirement.

## Files Changed

| File | Change |
|------|--------|
| `backend/agents/coaching/agent.py` | Add `session_id` param to `_create_session_manager()` and `create_coaching_agent()` |
| `backend/handlers/coaching/stream_handler.py` | Add `_cached_agents` dict, cache hit/miss logic, eviction on attention_mode/compact/disconnect, pass `session_id=connection_id` |
| `backend/handlers/coaching/service.py` | No change (REST handler, UUID session is correct) |

## Testing

- Unit test: verify `_create_session_manager()` uses provided `session_id` when given, falls back to UUID when `None`
- Unit test: verify agent cache hit returns same agent instance, cache miss creates new
- Unit test: verify eviction on attention_mode change, compaction, disconnect
- Integration: existing coaching flow tests continue to pass (thread history still loaded from DynamoDB on cache miss)

## Non-Goals

- Agent caching for `action_event` or `compact` handlers (throwaway agents with special prompts)
- Changing the REST handler's session ID strategy
- Changing the `actor_id` (already correctly set to `user_id`)
- Adding `batch_size` to the session manager config (default batch_size=1 is fine for our message-at-a-time pattern)
