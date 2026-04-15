# O*NET Agent Tool Integration

**Date:** 2026-04-14
**Status:** Design approved, pending implementation plan

## Context

REGAIN is a top-50 finalist in the AWS 10,000 AIdeas competition. Judge
feedback flagged that the product sits in a crowded market space with free
alternatives. One of REGAIN's differentiators is grounding career advice in
authoritative public data — specifically the U.S. Department of Labor's
O*NET career database.

The backend already exposes `/onet/search` and `/onet/careers/{soc_code}`
REST endpoints backed by `backend/handlers/onet/service.py`, which proxies
the O*NET Web Services API v2. The frontend uses this via the Careers
page. The **coaching agent** cannot currently query O*NET — all career
guidance is ungrounded LLM output.

This spec enables the agent to programmatically pull O*NET data during
coaching conversations, both on-demand (user asks) and proactively (agent
decides grounding adds value). The demo-day goal is to let judges see the
agent autonomously invoke O*NET tools and ground advice in real
government-sourced data.

## Goals

- Coaching agent can search O*NET careers and fetch full career detail via
  tool calls during conversation
- Agent autonomously decides when to pull O*NET data — no scripted triggers
- Agent has enough information in-prompt to know O*NET exists and when to
  use it (target role pre-populated)
- Tool calls are visible in the existing tool-execution UI (`ToolStep`s) so
  judges can see the reasoning on demo day

## Non-Goals

- No caching (per design discussion — always fetch fresh from O*NET)
- No voice agent integration (fast-follow; tools will be available but
  voice agent prompt/`_prefetch_context()` not updated in this scope)
- No trimming or summarization of returned data — tools return raw O*NET
  JSON for the requested sections (section-level filtering is not trimming)
- No new DynamoDB tables, Lambda Layers, or env vars

## Architecture

```
Coaching Agent (LLM)
   ↓ invokes @tool
backend/agents/coaching/tools.py
  - onet_search_careers(keyword)
  - onet_career_detail(soc_code, sections)
   ↓ delegates
backend/handlers/onet/service.py   (existing)
   ↓ HTTPS GET with X-API-Key
api-v2.onetcenter.org/mnm/*
   ↓ key fetched from
SSM /regain/onet/api-key (SecureString, cached in Lambda container)
```

## Tool Specifications

### `onet_search_careers(keyword: str) -> dict`

Thin wrapper over `service.search_careers()`.

**Docstring** (visible to the LLM):
> Search O*NET for careers matching a keyword. Use when you need the SOC
> code for a role the user mentions (e.g. "software engineer", "nurse").
> Returns candidate careers with SOC codes and titles. Follow up with
> `onet_career_detail` for full data.

**Validation:**
- `keyword` must be non-empty after `strip()` → `ERR_VALIDATION` otherwise

**Returns:** Raw O*NET response dict `{"career": [{"code", "title", "tags", ...}]}`

### `onet_career_detail(soc_code: str, sections: list[str]) -> dict`

Wrapper over `service.get_career_detail()` with section filtering.

**Docstring:**
> Fetch authoritative O*NET data for a specific career. `sections` is
> REQUIRED — pick only what you need to avoid bloating context. Valid:
> "knowledge", "skills", "abilities", "personality", "technology",
> "education", "job_outlook", "check_out_my_state", "explore_more".
> Overview (code, title, what_they_do, on_the_job) is always included.

**Validation:**
- `soc_code` must match `/^\d{2}-\d{4}\.\d{2}$/` → `ERR_VALIDATION`
- `sections` must be non-empty list → `ERR_VALIDATION`
- Every section name must be in the allowlist above → `ERR_VALIDATION` with
  the offending name in the message

**Implementation note:** The existing `service.get_career_detail()` fetches
all 9 sections unconditionally. The tool will either (a) reuse it and
strip unrequested sections before returning, or (b) call `service._onet_request()`
directly for the overview + requested sections. Option (b) is preferred —
avoids wasted network calls. The implementation plan will decide.

**Returns:** Dict with overview fields plus one key per requested section.

### Error Mapping

Both tools use the standard typed error kinds from `tools.py`:

| Condition | `error_kind` |
|-----------|-------------|
| Empty keyword / invalid SOC format / empty or unknown section name | `ERR_VALIDATION` |
| O*NET returns 404 | `ERR_NOT_FOUND` |
| O*NET returns other 4xx | `ERR_PERMANENT` |
| Network timeout / 5xx | `ERR_TRANSIENT` |
| SSM can't fetch API key | `ERR_PERMANENT` |

## Agent Prompt Changes

Add to the coaching agent system prompt (`backend/agents/coaching/prompts.py`
or wherever `get_system_prompt()` lives):

```
## O*NET Career Data

You have access to authoritative U.S. Department of Labor career data via
two tools:

- `onet_search_careers(keyword)` — find SOC codes for a role
- `onet_career_detail(soc_code, sections)` — fetch rich career data

Use these when:
- The user asks about a specific career, role, or job title
- You're advising on skills, tasks, outlook, or education for their target role
- You're grounding mission suggestions in what the role actually requires

The user's target role is: {target_role}

Prefer to ground career advice in O*NET data rather than general knowledge.
Pull only the sections you need (e.g. "skills" + "job_outlook" for a
progress check-in, "education" + "technology" for a learning path).
```

`{target_role}` is interpolated from the user profile at prompt-build
time. When the profile's `targetRole` is empty/missing, the prompt builder
substitutes the string `"(not yet set)"` so the section reads "The user's
target role is: (not yet set)". In that state the agent is expected to
call `onet_search_careers` after asking the user what role they're
targeting, rather than calling `onet_career_detail` blindly.

## Infrastructure / IAM

In `infra/stacks/agent_stack.py`, add a helper method:

```python
def _onet_ssm_policy(self) -> iam.PolicyStatement:
    return iam.PolicyStatement(
        actions=["ssm:GetParameter"],
        resources=[
            f"arn:aws:ssm:{self.region}:{self.account}:parameter/regain/onet/*"
        ],
    )
```

Attach to all three agent Lambdas:
- `self.coaching_lambda` (REST endpoint)
- `chat_stream_lambda` (WebSocket streaming — primary path for tool calls)
- `voice_lambda` (pre-emptively; enables future voice integration without
  a second infra change)

No other infrastructure changes. The O*NET service module is already part
of the `backend/` tree bundled with each Lambda. No new env vars, no
DynamoDB, no Layer updates.

## Testing

### Unit — `tests/unit/agents/coaching/test_onet_tools.py` (new)

- `onet_search_careers` happy path — mock `service.search_careers`,
  assert pass-through of raw payload
- `onet_search_careers` rejects empty/whitespace keyword with `ERR_VALIDATION`
- `onet_career_detail` happy path — mock, assert requested sections
  included and unrequested ones absent
- `onet_career_detail` rejects invalid SOC format, empty sections list,
  unknown section name
- Error mapping — `urllib.error.HTTPError(404)` → `ERR_NOT_FOUND`,
  `HTTPError(4xx)` → `ERR_PERMANENT`, `URLError`/timeout → `ERR_TRANSIENT`
- Tools registered with Strands `@tool` decorator (verify via whatever
  attribute the existing `tools.py` tests use — `TOOL_SPEC`, `tool_spec`,
  or `__strands_tool__` depending on Strands version)

### Integration — existing `test_coaching_agent_tools.py`

- If the file enumerates expected tool names, add the two new tools
- Verify `agent.tool_names` includes both after agent build

### Infra — existing `test_iam_least_privilege.py`

- If the SSM parameter allowlist for agent Lambdas is strict (not wildcard),
  extend to include `/regain/onet/*`
- No Lambda count changes — no new Lambdas
- No DynamoDB table count changes

### Live O*NET calls

None. All tests mock at the `service.py` boundary. The existing O*NET
handler tests already cover the HTTP client.

## Rollout

1. Implement tools + prompt changes on a feature branch
2. Run full pytest suite + lint
3. `cdk diff RegainAgentStack` — review IAM changes
4. `cdk deploy RegainAgentStack` to dev account
5. Smoke-test via chat UI: ask "what skills do I need for my target role?"
   — verify tool calls appear in `AgentActivityFeed`
6. Merge to `main` (squash) → Amplify auto-deploys frontend (no frontend
   changes here, so this is a no-op)

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| O*NET rate limit (20 req/s) hit during demo | Unlikely at single-user demo scale; if hit, `ERR_TRANSIENT` surfaces cleanly |
| Raw JSON blows token budget | `sections` required forces agent to pick; existing auto-compact catches overflow |
| LLM narrates tool success on error | Existing pattern — tools return `{"error": ..., "error_kind": ...}` structurally; agent system prompt already covers this |
| SSM GetParameter IAM drift | Covered by `test_iam_least_privilege.py` |

## Open Questions

None as of 2026-04-14. Implementation plan can proceed.
