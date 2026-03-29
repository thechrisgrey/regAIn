# AgentCore Memory Subsystem Fix

Rewire the coaching agent's memory from broken hand-rolled boto3 calls to the official Strands `AgentCoreMemorySessionManager` integration, fix the profile deletion cleanup, and provision the memory resource properly via CDK.

## Problem

The coaching agent's `store_memory` and `recall_memory` tools call `boto3.client("bedrock-agent-runtime")` with methods (`create_memory()`, `retrieve_memory()`) that don't exist on that client. Every call silently fails. Memory has never worked — the agent hallucinated user names because `recall_memory` returned `source: "unavailable"` and the agent confabulated instead of falling back to `read_user_profile`.

The profile deletion code uses `boto3.client("bedrock-agentcore")` with `list_memory_records()` / `delete_memory_record()` — the correct client — but the memory ID (`regain-coaching-memory`) is a human-readable name, not a real resource ID. The ID fails the API's validation pattern (`[a-zA-Z][a-zA-Z0-9-_]{0,99}-[a-zA-Z0-9]{10}`), so deletion also silently fails.

## Decisions

| Question | Decision |
|----------|----------|
| Memory integration approach | Strands `AgentCoreMemorySessionManager` — automatic turn storage, framework-managed |
| Memory resource provisioning | CDK `CfnCustomResource` in AgentCoreStack — creates memory via `bedrock-agentcore-control` |
| Conversation storage | Automatic via session manager — no explicit `store_memory` tool |
| Memory recall | Automatic retrieval at session start via `RetrievalConfig` + lightweight `recall_memory` tool for targeted mid-conversation queries |

## 1. Memory Resource Provisioning (CDK)

`AgentCoreStack` gets a `CfnCustomResource` backed by an inline Lambda that calls `bedrock-agentcore-control`:

- **Create**: `control_client.create_memory(name="regain-coaching", description="Coaching session memory for REGAIN platform", eventExpiryDuration=90, memoryStrategies=[...])` with three strategies:
  - `summaryMemoryStrategy` (name: `SessionSummarizer`, namespaceTemplates: `["/summaries/{actorId}/"]`)
  - `userPreferenceMemoryStrategy` (name: `PreferenceLearner`, namespaceTemplates: `["/preferences/{actorId}/"]`)
  - `semanticMemoryStrategy` (name: `FactExtractor`, namespaceTemplates: `["/facts/{actorId}/"]`)
- **Delete**: `control_client.delete_memory(memoryId=physical_resource_id)` on stack teardown.
- **Output**: The returned `memory['id']` (real ID with 10-char suffix) is exported as `RegainAgentCoreMemoryId` and set as `AGENTCORE_MEMORY_ID` on all coaching and profile Lambdas.

The custom resource Lambda needs IAM permissions: `bedrock:CreateMemory`, `bedrock:DeleteMemory`, `bedrock:GetMemory` scoped to `*` (memory IDs are generated at creation time).

## 2. Lambda Layer Changes

Add `bedrock-agentcore` to `build_layer.sh`:

```bash
pip install strands-agents strands-agents-tools aws-sdk-bedrock-runtime 'PyJWT[crypto]' bedrock-agentcore --target /out
```

This brings in `AgentCoreMemorySessionManager`, `AgentCoreMemoryConfig`, and `RetrievalConfig` from `bedrock_agentcore.memory.integrations.strands`.

## 3. Coaching Agent Integration

### agent.py

`create_coaching_agent()` constructs an `AgentCoreMemorySessionManager` and passes it to `Agent(session_manager=...)`:

```python
from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig, RetrievalConfig
from bedrock_agentcore.memory.integrations.strands.session_manager import AgentCoreMemorySessionManager

config = AgentCoreMemoryConfig(
    memory_id=os.environ.get("AGENTCORE_MEMORY_ID", ""),
    actor_id=user_id,                    # per-user namespace scoping
    session_id=f"session-{uuid.uuid4().hex[:12]}",
    retrieval_config=RetrievalConfig(),   # auto-retrieval at session start
)
session_manager = AgentCoreMemorySessionManager(
    agentcore_memory_config=config,
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
)
```

If `AGENTCORE_MEMORY_ID` is empty or the session manager fails to initialize, the agent runs without memory (graceful degradation, same as today's silent failure but explicit).

### tools.py

- **Remove**: `store_memory` function entirely. Remove from `_get_direct_tools()` in `agent.py`.
- **Replace**: `recall_memory` with a lightweight version using `boto3.client("bedrock-agentcore")`:

```python
@tool
def recall_memory(user_id: str, query: str) -> dict:
    client = boto3.client("bedrock-agentcore", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    memory_id = os.environ.get("AGENTCORE_MEMORY_ID", "")
    if not memory_id:
        return {"entries": [], "source": "unavailable"}
    # Search across all strategy namespaces for relevant memories.
    all_records = []
    for ns in [f"/summaries/{user_id}/", f"/preferences/{user_id}/", f"/facts/{user_id}/"]:
        response = client.retrieve_memory_records(
            memoryId=memory_id,
            namespace=ns,
            searchCriteria={"query": {"text": query}},
        )
        all_records.extend(response.get("memoryRecordSummaries", []))
    records = all_records
    return {
        "entries": [{"content": r.get("content", ""), "metadata": r.get("metadata", {})} for r in records],
        "source": "memory",
    }
```

- **Remove**: `_memory_client` module-level global and `_get_memory_client()` helper.

### Gateway tool targets (AgentCoreStack)

Remove the `GatewayTargetRegainStoreMemory` target from the AgentCore Gateway configuration. Keep `GatewayTargetRegainRecallMemory` but update it to point to the new `recall_memory` implementation.

## 4. Profile Deletion Cleanup

`ProfileService._delete_agentcore_memory()` already uses the correct client (`bedrock-agentcore`) and methods. Two fixes:

1. **Memory ID**: Now receives the real ID (with suffix) via `AGENTCORE_MEMORY_ID` env var. The validation pattern will pass.

2. **Multi-namespace iteration**: Memory strategies create records under multiple namespaces. The deletion iterates over all known patterns:

```python
namespaces = [
    f"regain-coaching-{user_id}",      # legacy flat namespace (if any)
    f"/summaries/{user_id}/",           # summaryMemoryStrategy
    f"/preferences/{user_id}/",         # userPreferenceMemoryStrategy
    f"/facts/{user_id}/",               # semanticMemoryStrategy
]
for namespace in namespaces:
    # paginate list_memory_records + delete each record
```

## 5. System Prompt Changes

In `prompts.py`:
- Remove the instruction to call `store_memory` at end of each session.
- Keep the instruction to call `recall_memory` for targeted mid-conversation queries.
- Keep instruction on line 62 to call `read_user_profile` for the user's name (authoritative source).

## 6. IAM Permissions

### Coaching Lambdas (ChatStream, VoiceSession)

Add to existing policy:
- `bedrock:CreateEvent` — session manager stores conversation turns
- `bedrock:RetrieveMemoryRecords` — auto-retrieval + `recall_memory` tool
- `bedrock:ListMemoryRecords` — `recall_memory` fallback

### Custom Resource Lambda (AgentCoreStack)

New inline Lambda with:
- `bedrock:CreateMemory`, `bedrock:DeleteMemory`, `bedrock:GetMemory` on `bedrock-agentcore-control`

### Profile Lambda

Already has `bedrock:ListMemoryRecords` and `bedrock:DeleteMemoryRecord`. No changes needed — the correct memory ID fixes the validation failure.

## 7. Testing

- **`recall_memory` unit test**: Mock `boto3.client("bedrock-agentcore").retrieve_memory_records()`, verify correct params (`memoryId`, `namespace`, `searchCriteria`).
- **`_delete_agentcore_memory` unit test**: Verify iteration over 4 namespace patterns, calls `delete_memory_record` for each found record.
- **Agent tool list tests**: Update to remove `store_memory` from expected tools, verify `session_manager` is passed to `Agent()`.
- **Custom resource Lambda**: Unit test for create/delete handler logic with mocked `bedrock-agentcore-control` client.

## Files Changed

| File | Change |
|------|--------|
| `infra/build_layer.sh` | Add `bedrock-agentcore` to pip install |
| `infra/stacks/agentcore_stack.py` | Add CfnCustomResource for memory provisioning, export real memory ID |
| `backend/agents/coaching/agent.py` | Add `AgentCoreMemorySessionManager`, remove `store_memory` from tool list |
| `backend/agents/coaching/tools.py` | Remove `store_memory`, rewrite `recall_memory` to use `bedrock-agentcore` client, remove `_memory_client` / `_get_memory_client()` |
| `backend/agents/coaching/prompts.py` | Remove `store_memory` instruction |
| `backend/handlers/profile/service.py` | Update `_delete_agentcore_memory` to iterate strategy namespaces |
| `infra/stacks/agent_stack.py` | Add `bedrock:CreateEvent`, `bedrock:RetrieveMemoryRecords`, `bedrock:ListMemoryRecords` to coaching Lambda IAM |
| Tests | Update tool list tests, add recall_memory unit test, add deletion namespace test, add custom resource test |

## Out of Scope

- Migrating old memory data (none exists — memory never worked)
- Voice practice memory (uses the same coaching namespace pattern, benefits from this fix automatically)
- Changing the coaching agent's model or prompt persona
