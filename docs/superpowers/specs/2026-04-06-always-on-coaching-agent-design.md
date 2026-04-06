# Always-On Coaching Agent

**Date**: 2026-04-06
**Status**: Approved
**Approach**: Event Bus + Persistent WebSocket (Approach A)

## Problem

The coaching agent is stateless between messages. Each WebSocket message creates a fresh `Agent()` instance with a random `session_id` — the agent has zero knowledge of what it said or did in the previous exchange unless AgentCore Memory surfaces it via semantic search. The frontend `sessionStorage` makes the conversation look continuous, but the backend sees each message in isolation.

The agent also has no awareness of user actions across the site. It doesn't know when the user completes a mission, logs evidence, generates a resume, or finishes a voice session unless the user explicitly tells it.

## Goals

1. **Conversation thread continuity** -- The agent loads full ordered conversation history (including tool calls and results) on every invocation, maintaining context across messages.
2. **Real-time action awareness** -- User actions (mission completed, evidence logged, page navigated) flow to the agent as events, giving it continuous situational awareness.
3. **User-controlled attention modes** -- The user chooses how proactive the agent is: Do Not Disturb, Focus, or Explore.
4. **Bounded memory with compaction** -- Token budget tracking with automatic and manual summarization to keep the thread within model context limits.
5. **No new Lambda functions** -- All new behavior runs through the existing WebSocket `$default` handler.

## Architecture

### Conversation Thread Table

New DynamoDB table: `ConversationThreads`

| Attribute | Type | Purpose |
|-----------|------|---------|
| `userId` (PK) | String | Partition key |
| `threadId` (SK) | String | `active` for current thread, ISO timestamp for archived compactions |
| `turns` | List | Ordered turn objects |
| `tokenEstimate` | Number | Running approximate token count |
| `maxTokenBudget` | Number | Per-user ceiling (default ~27k tokens for Nova Lite 32k context) |
| `attentionMode` | String | `explore` / `focus` / `dnd` |
| `lastActivityAt` | String | ISO timestamp, updated on every turn |
| `pendingMessages` | List | Proactive messages queued while WebSocket was disconnected |
| `compactedFrom` | String | For archived threads: the threadId that was compacted |

**Turn object shape:**

```json
{
  "role": "user | assistant | system | tool_call | tool_result",
  "content": "...",
  "toolName": "read_user_profile",
  "timestamp": "2026-04-06T19:30:00Z",
  "source": "chat | action_event | compaction"
}
```

**Billing**: On-demand (PAY_PER_REQUEST). PITR enabled. No GSIs. No TTL on active threads.

**Relationship to AgentCore Memory**: The thread table is working memory (ordered, structured, full tool-call history). AgentCore Memory is long-term recall (semantic search across sessions). They are complementary -- compaction summaries flow into both.

### WebSocket Lifecycle

The WebSocket connection lives at the API Gateway layer, independent of Lambda invocations. Each message type triggers a Lambda invocation that does real work -- no dedicated heartbeats.

**Natural keep-alive**: Action events from user activity (page navigation, mutations) keep the connection alive. The API Gateway 10-minute idle timeout only fires during true inactivity, at which point a silent reconnect on the next action is acceptable.

**Message types (extended from current):**

| Direction | Type | Purpose |
|-----------|------|---------|
| Client -> Server | `auth` | JWT authentication (exists) |
| Client -> Server | `message` | User chat message (exists) |
| Client -> Server | `action_event` | User action: `{action: "mission:completed", payload: {...}}` |
| Client -> Server | `attention_mode` | Mode change: `{mode: "focus"}` |
| Client -> Server | `compact` | User requests compaction |
| Client -> Server | `sync` | Reconnect rehydration request |
| Server -> Client | `delta` | Streaming text chunk (exists) |
| Server -> Client | `done` | Stream complete (exists) |
| Server -> Client | `thinking` / `thinking_complete` | Tool execution visibility (exists) |
| Server -> Client | `error` | Error (exists) |
| Server -> Client | `proactive` | Agent-initiated message |
| Server -> Client | `thread_meta` | Token count + compaction status update |

**Reconnection**: On reconnect, after auth succeeds, the frontend sends `{type: "sync"}`. The backend responds with `{type: "thread_meta", tokenEstimate, tokenBudget, attentionMode, pendingMessages: [...]}` to rehydrate the frontend with any proactive messages generated while disconnected.

### Memory Compaction

**Token budget**: ~27k tokens (Nova Lite 32k context minus ~4k system prompt/tools, ~1k safety margin).

**Estimation**: `len(content) // 4` on every turn append. Approximate, not exact.

**Thresholds:**

| Range | Color | Behavior |
|-------|-------|----------|
| 0-74% | Green | Normal operation |
| 75-89% | Yellow | User can manually compact |
| 90-99% | Red | User strongly encouraged to compact |
| 100% | Auto-trigger | Agent summarizes before processing next message |

**Compaction flow:**

1. Agent receives system instruction: "Summarize the conversation into the most important context needed to continue coaching. Preserve: active mission state, recent evidence, behavioral patterns, commitments, unresolved topics. Target ~15% of current thread length."
2. Summary becomes the new first turn (`source: "compaction"`).
3. Full pre-compaction thread archived to S3: `s3://regain-thread-archives/{userId}/{threadId}-{timestamp}.jsonl`
4. Summary also stored in AgentCore Memory `/summaries/{user_id}/` namespace.
5. `tokenEstimate` resets to summary token count (~4k tokens).

**Manual compaction**: User clicks "Compact" in the coach modal. Same flow, user-initiated.

**Thread reset**: "Clear conversation" wipes the thread entirely, archives to S3, resets `tokenEstimate` to 0. AgentCore Memory retains long-term recall.

### Attention Modes

Three modes controlling agent proactivity on action events. Stored on the thread row as `attentionMode`. Default: `focus`.

**Do Not Disturb**: Action events are appended to the thread (context preserved) but the agent is never invoked for them. Explicit chat messages always work regardless of mode.

**Focus**: Agent is invoked on action events with a constrained system instruction: "Respond only if this action represents a significant milestone, a pattern break, or requires attention. Otherwise append to context silently." Agent returns a response or an empty signal.

**Explore**: Agent is invoked on every action event with latitude to surface insights, connections, suggestions, and encouragement.

**Frontend control**: Three-state segmented toggle in the coach modal header (DnD / Focus / Explore).

### Action Event Catalog

Events forwarded from the frontend MutationBus and router to the backend via WebSocket:

| Event | Source | Payload |
|-------|--------|---------|
| `mission:completed` | MutationBus | `{missionId, title, skillTags}` |
| `mission:generated` | MutationBus | `{missionId, title}` |
| `evidence:logged` | MutationBus | `{evidenceId, skillTag, reflection}` |
| `page:navigated` | Router | `{route, pageContext}` |
| `campaign:created` | MutationBus | `{campaignId, targetRole}` |
| `resume:generated` | MutationBus | `{format}` |
| `voice:session_completed` | MutationBus | `{sessionType, duration}` |
| `scorecard:viewed` | Route | `{}` |
| `profile:updated` | MutationBus | `{fields}` |

**Deduplication**: Same `action` + `payload` within 5 seconds is dropped.

**Batching**: 3+ action events within a 2-second window are batched into a single system turn. Agent invoked once.

### End-to-End Flow (Explore Mode Example)

```
User completes mission on Missions page
  -> MutationBus emits "mission:completed"
  -> DataContext refreshes dashboard/missions/evidence (existing)
  -> AgentEventBridge sends action_event over WebSocket
  -> $default Lambda:
      1. Load thread from ConversationThreads
      2. Append system turn: "User completed mission: [title], skills: [tags]"
      3. Check attentionMode: "explore"
      4. Create agent with thread as conversation history
      5. Agent reasons, decides to respond
      6. Stream response as {type: "proactive"}
      7. Append assistant turn to thread, update tokenEstimate
      8. Send {type: "thread_meta"} to frontend
  -> Frontend: notification dot if modal closed, inline message if open
```

## Infrastructure Changes

### New Resources

| Resource | Stack | Details |
|----------|-------|---------|
| `ConversationThreads` DynamoDB table | DataStack | PK: userId, SK: threadId, on-demand, PITR |
| `regain-thread-archives` S3 bucket | DataStack | Versioned, SSE-S3, Glacier lifecycle at 30 days |

### Permission Changes

| Stack | Lambda | Grant |
|-------|--------|-------|
| ApiStack | Coaching Lambda | Read/write ConversationThreads, write thread-archives bucket |
| AgentStack | Chat Stream Lambda | Read/write ConversationThreads, write thread-archives bucket |

### Environment Variables Added

| Variable | Set on | Source |
|----------|--------|--------|
| `CONVERSATION_THREADS_TABLE` | Coaching Lambda, Chat Stream Lambda | DataStack export |
| `THREAD_ARCHIVE_BUCKET` | Coaching Lambda, Chat Stream Lambda | DataStack export |

### Test Count Updates

- `test_iam_least_privilege.py`: Update Coaching/Chat Stream Lambda permission expectations
- `test_on_demand_billing.py`: Increment `EXPECTED_TABLE_COUNT`
- `test_table_output_completeness.py`: Add to `known_tables` list
- `test_lambda_env_config.py`: Add new env vars to expected config

### Profile Cascade Deletion

Add `ConversationThreads` table to cascade delete in `profile/service.py`. Add `regain-thread-archives` S3 prefix cleanup to `_delete_s3_prefix()` calls.

## Backend Code Changes

| File | Change |
|------|--------|
| `backend/handlers/shared/dynamodb.py` | Add `conversation_threads` to `TABLE_ENV_VARS` |
| `backend/handlers/coaching/stream_handler.py` | Add `action_event`, `compact`, `attention_mode`, `sync` handlers; load/save thread on every invocation |
| `backend/agents/coaching/agent.py` | Accept `conversation_history` param, pass to `Agent()` for full context |
| `backend/agents/coaching/prompts.py` | Add attention mode instructions to system prompt |
| `backend/handlers/profile/service.py` | Add ConversationThreads + thread-archives to cascade deletion |

### New Module

`backend/handlers/shared/thread.py` -- Thread management utilities:

- `load_active_thread(user_id)` -- returns turns list + metadata
- `append_turns(user_id, turns)` -- appends + updates tokenEstimate
- `compact_thread(user_id, summary, archive_bucket)` -- archive to S3, replace with summary
- `update_attention_mode(user_id, mode)` -- attribute update
- `get_pending_messages(user_id)` -- for sync on reconnect
- `flush_pending_messages(user_id)` -- clear after sync delivery
- `estimate_tokens(content)` -- `len(content) // 4`

## Frontend Code Changes

| File | Change |
|------|--------|
| `hooks/CoachingContext.tsx` | Handle `action_event`, `compact`, `attention_mode`, `sync` outgoing; handle `proactive`, `thread_meta` incoming; thread table is source of truth |
| `hooks/MutationBusContext.tsx` | Add event types: `campaign:created`, `resume:generated`, `voice:session_completed`, `profile:updated` |
| `components/CoachModal.tsx` | Attention mode toggle (segmented control); token budget indicator (% + color); compact button |

### New Module

`frontend/src/hooks/useAgentEventBridge.ts` -- Subscribes to MutationBus, forwards action events over WebSocket. Mounts inside CoachingProvider. Handles 5-second deduplication and 2-second batching debounce.

## Migration

Purely additive. No existing data changes shape.

- Existing users get an empty `ConversationThreads` row on first coaching interaction (created if not found).
- AgentCore Memory continues working alongside -- nothing removed.
- `sessionStorage` stays as frontend display cache; thread table is source of truth.

## Deploy Order

1. DataStack (new table + bucket)
2. ApiStack + AgentStack (permissions + env vars)
3. Backend code (thread module + stream_handler changes)
4. Frontend (CoachModal UI + event bridge)

Steps 1-3: single `cdk deploy --all`. Step 4: git push to main (Amplify auto-deploy).
