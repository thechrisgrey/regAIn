# Coaching Agent Tool-Call Hallucination Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop Nova Pro from claiming tool successes it never invoked when coaching chat history grows long.

**Architecture:** Four independent, incrementally deployable fixes. (1) Repair the `AgentCoreMemoryConfig` initialization so `AgentCoreMemorySessionManager` actually attaches, restoring native `tool_use`/`tool_result` replay from AgentCore Memory. (2) Cap DynamoDB thread replay to the last 15 turns on the fallback path so long text-only histories don't contaminate the model. (3) Filter `[proactive_check]` and bare `[page_context]` noise turns out of replay. (4) Add a behavioral rule making tool invocation mandatory for any state-changing claim.

**Tech Stack:** Python 3.12, Strands Agents SDK, Amazon Bedrock AgentCore Memory, Bedrock Nova Pro (`amazon.nova-pro-v1:0`), AWS Lambda, DynamoDB, pytest, moto.

**Context — why this plan exists:**

A local repro (`scripts/nova_tool_repro.py --replay-history`) confirmed the bug: with 54 DynamoDB thread turns replayed as text-only messages, Nova Pro responds "I've updated your target role to Senior Software Engineer" but never calls `update_user_profile`. The same 3-tool configuration works fine with an empty history. The agent code has a latent bug: `_create_session_manager` in `backend/agents/coaching/agent.py:121` passes `retrieval_config=RetrievalConfig()`, but pydantic schema requires `Optional[Dict[str, RetrievalConfig]]`. This raises silently in the `except Exception` block, `session_manager` becomes `None`, and the code falls into the text-only replay path at `agent.py:248-261`. In production the fallback replays all turns unbounded.

Each phase is independently valuable and mergeable. Phase 1 is the most impactful — it restores the correct Strands/AgentCore integration and the other phases become defensive.

---

## File Structure

**Files modified (total):**

- `backend/agents/coaching/agent.py` — Phases 1, 2, 3
- `backend/agents/coaching/prompts.py` — Phase 4
- `tests/unit/agents/coaching/test_agent.py` — Phases 1, 2, 3 (tests)
- `tests/unit/agents/coaching/test_prompts.py` — Phase 4 (tests)

**Files created:** None. All changes are surgical edits to existing files.

**Verification scripts used (existing):**

- `scripts/nova_tool_repro.py` — already writes a full local repro harness, used to manually validate each phase.

---

## Phase 1 — Fix AgentCoreMemorySessionManager Initialization

**Why first:** This is the root cause. When this is fixed, Strands automatically replays prior `tool_use`/`tool_result` blocks from AgentCore Memory, which is exactly what Nova Pro needs to see to keep calling tools. Phases 2–4 become defensive layers.

### Task 1.1: Failing test — config gets a dict, not a RetrievalConfig

**Files:**
- Modify: `tests/unit/agents/coaching/test_agent.py` (add to `TestSessionIdPassthrough` class or create new `TestSessionManagerConfig` class)

- [ ] **Step 1: Write the failing test**

Add this test to `tests/unit/agents/coaching/test_agent.py` as a new class at the end of the file:

```python
class TestSessionManagerRetrievalConfig:
    """Pydantic schema for AgentCoreMemoryConfig requires
    retrieval_config to be Optional[Dict[str, RetrievalConfig]], not
    a bare RetrievalConfig. See layer_build/.../strands/config.py.
    """

    def test_retrieval_config_is_dict_or_none(self, monkeypatch):
        """AgentCoreMemoryConfig must receive retrieval_config as
        dict or None, never a bare RetrievalConfig instance."""
        monkeypatch.setenv("AGENTCORE_MEMORY_ID", "mem-123")
        monkeypatch.setenv("AWS_REGION", "us-east-1")

        mock_config_cls = MagicMock(name="AgentCoreMemoryConfig")
        mock_retrieval_cls = MagicMock(name="RetrievalConfig")
        mock_session_mgr_cls = MagicMock(name="AgentCoreMemorySessionManager")

        config_mod = types.ModuleType(
            "bedrock_agentcore.memory.integrations.strands.config"
        )
        config_mod.AgentCoreMemoryConfig = mock_config_cls  # type: ignore[attr-defined]
        config_mod.RetrievalConfig = mock_retrieval_cls  # type: ignore[attr-defined]

        mgr_mod = types.ModuleType(
            "bedrock_agentcore.memory.integrations.strands.session_manager"
        )
        mgr_mod.AgentCoreMemorySessionManager = mock_session_mgr_cls  # type: ignore[attr-defined]

        with patch.dict(sys.modules, {
            "bedrock_agentcore": types.ModuleType("bedrock_agentcore"),
            "bedrock_agentcore.memory": types.ModuleType("bedrock_agentcore.memory"),
            "bedrock_agentcore.memory.integrations": types.ModuleType("bedrock_agentcore.memory.integrations"),
            "bedrock_agentcore.memory.integrations.strands": types.ModuleType("bedrock_agentcore.memory.integrations.strands"),
            "bedrock_agentcore.memory.integrations.strands.config": config_mod,
            "bedrock_agentcore.memory.integrations.strands.session_manager": mgr_mod,
        }):
            from backend.agents.coaching.agent import _create_session_manager

            _create_session_manager("user-42", session_id="ws-conn-abc")

        mock_config_cls.assert_called_once()
        call_kwargs = mock_config_cls.call_args.kwargs
        retrieval = call_kwargs.get("retrieval_config")
        assert retrieval is None or isinstance(retrieval, dict), (
            f"retrieval_config must be None or dict, got {type(retrieval).__name__}: {retrieval}"
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/agents/coaching/test_agent.py::TestSessionManagerRetrievalConfig::test_retrieval_config_is_dict_or_none -v`

Expected: FAIL with assertion error — `retrieval_config` is currently a MagicMock instance (because `RetrievalConfig()` is called and that mock call is passed), not `None` or `dict`.

- [ ] **Step 3: Apply the fix**

Edit `backend/agents/coaching/agent.py` lines 112-126. Change the `try` block body to:

```python
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
```

Notes:
- Drop the `RetrievalConfig` import — we no longer use it.
- `retrieval_config=None` disables namespace-scoped retrieval. The session manager still writes and restores the ordered turn stream, which is what we need for tool-call replay. Namespaced retrieval can be re-added later as `retrieval_config={"/actor/{user_id}": RetrievalConfig()}` if we want long-term semantic recall of memories across sessions.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/agents/coaching/test_agent.py::TestSessionManagerRetrievalConfig -v`

Expected: PASS.

- [ ] **Step 5: Run the broader agent test module to confirm no regressions**

Run: `.venv/bin/pytest tests/unit/agents/coaching/test_agent.py -v`

Expected: All tests pass (including `test_session_id_passed_to_session_manager` and `test_session_id_defaults_to_uuid_when_none` in `TestSessionIdPassthrough` — they still mock `RetrievalConfig` but don't assert it's called, so they should continue to work).

- [ ] **Step 6: Commit**

```bash
git add backend/agents/coaching/agent.py tests/unit/agents/coaching/test_agent.py
git commit -m "fix(coaching-agent): pass retrieval_config=None to AgentCoreMemoryConfig

AgentCoreMemoryConfig pydantic schema requires retrieval_config to be
Optional[Dict[str, RetrievalConfig]], but we were passing a bare
RetrievalConfig() instance. Validation failed silently inside the
except-Exception block, session_manager was None in production, and
the coaching Lambda fell back to text-only DynamoDB thread replay —
which primes Nova Pro to skip tool calls after ~30 turns.

With retrieval_config=None, Strands' AgentCoreMemorySessionManager
attaches cleanly and replays prior tool_use/tool_result blocks on
each invocation."
```

### Task 1.2: Local verification against live Bedrock

**Files:**
- Use: `scripts/nova_tool_repro.py` (already exists)

- [ ] **Step 1: Reproduce the hallucination with history replay BEFORE the fix baseline**

_(Skip if already run during investigation.)_

Run:
```bash
AWS_PROFILE=regain AWS_DEFAULT_REGION=us-east-1 \
    .venv/bin/python scripts/nova_tool_repro.py \
    --tools 3 --user-id <sub> --replay-history --prod-prompt
```

Expected (on `main` before the fix): exit code 1. Log shows "Tool invocations captured: 0" and the agent narrates "I've updated your target role" without calling `update_user_profile`.

- [ ] **Step 2: Re-run with the fix applied**

On the phase-1 branch, run the same command. Note that the repro script is a local Strands `Agent(...)` with no session manager — this local script won't see the benefit of Phase 1 directly. So the acceptance criterion here is: no regression vs. baseline. If the repro still fails the same way with the 54-turn replay, that's fine — Phase 1 fix is for the Lambda path where `AGENTCORE_MEMORY_ID` is set, and Phases 2-3 address the fallback path the repro exercises.

- [ ] **Step 3: Manual Lambda verification (after deploy)**

_(Deferred until after all four phases are merged and deployed.)_

Send a real message through the coaching WebSocket asking to update the target role. Check CloudWatch Logs for the coaching Lambda:
- Expected: `BEFORE tool call: update_user_profile` appears in `/aws/lambda/RegainChatStreamFn` log stream.
- Check: no "Failed to create AgentCoreMemorySessionManager" warning appears in recent logs.

---

## Phase 2 — Cap Fallback Replay at 15 Turns

**Why:** Even with Phase 1 fixed, the fallback path at `agent.py:248-261` exists for users whose session manager fails to attach (rare, but possible during AgentCore outages or if `AGENTCORE_MEMORY_ID` is unset in a region). Unbounded text-only replay of long histories is the toxic pattern that causes the hallucination. Cap it.

### Task 2.1: Failing test — fallback replay truncates to last N turns

**Files:**
- Modify: `tests/unit/agents/coaching/test_agent.py` (add new test class at end of file)

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/agents/coaching/test_agent.py`:

```python
class TestConversationHistoryCap:
    """When session_manager is None, conversation_history must be
    truncated to the last N turns before appending to agent.messages.
    Long text-only replays contaminate Nova Pro's tool-calling."""

    @pytest.mark.usefixtures("_pending_env")
    def test_long_history_is_truncated_to_last_15(
        self, mock_direct_tools, mock_bedrock_model
    ):
        """54-turn conversation should be truncated to last 15 turns."""
        from backend.agents.coaching.agent import (
            MAX_REPLAYED_TURNS,
            create_coaching_agent,
        )

        assert MAX_REPLAYED_TURNS == 15, (
            "Cap constant must be 15 (empirically safe for Nova Pro)"
        )

        # Build 54 turns, user/assistant alternating starting with user.
        turns = []
        for i in range(27):
            turns.append({"role": "user", "content": f"user msg {i}"})
            turns.append({"role": "assistant", "content": f"assistant msg {i}"})

        # Use a plain list for agent.messages so append() works.
        with patch("backend.agents.coaching.agent.Agent") as mock_agent_cls:
            agent_instance = MagicMock()
            agent_instance.messages = []
            mock_agent_cls.return_value = agent_instance

            create_coaching_agent(
                user_id="user-1",
                jwt_token="jwt",
                conversation_history=turns,
            )

        replayed = agent_instance.messages
        assert len(replayed) == MAX_REPLAYED_TURNS, (
            f"Expected {MAX_REPLAYED_TURNS} messages replayed, got {len(replayed)}"
        )
        # Content of first replayed message should be one of the LAST
        # 15 turns from the input.
        first_replayed_text = replayed[0]["content"][0]["text"]
        assert first_replayed_text in [
            t["content"] for t in turns[-MAX_REPLAYED_TURNS:]
        ]

    @pytest.mark.usefixtures("_pending_env")
    def test_short_history_is_unchanged(
        self, mock_direct_tools, mock_bedrock_model
    ):
        """Histories at or below the cap should replay fully."""
        from backend.agents.coaching.agent import create_coaching_agent

        turns = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
            {"role": "user", "content": "update target to SWE"},
        ]

        with patch("backend.agents.coaching.agent.Agent") as mock_agent_cls:
            agent_instance = MagicMock()
            agent_instance.messages = []
            mock_agent_cls.return_value = agent_instance

            create_coaching_agent(
                user_id="user-1",
                jwt_token="jwt",
                conversation_history=turns,
            )

        assert len(agent_instance.messages) == 3

    @pytest.mark.usefixtures("_pending_env")
    def test_cap_preserves_first_user_turn_rule(
        self, mock_direct_tools, mock_bedrock_model
    ):
        """Bedrock requires the first message to be role=user. After
        truncation, if the first kept turn is assistant, drop it."""
        from backend.agents.coaching.agent import create_coaching_agent

        # Build 20 turns; turn[-15] happens to be assistant (even index).
        turns = []
        for i in range(10):
            turns.append({"role": "user", "content": f"u{i}"})
            turns.append({"role": "assistant", "content": f"a{i}"})

        with patch("backend.agents.coaching.agent.Agent") as mock_agent_cls:
            agent_instance = MagicMock()
            agent_instance.messages = []
            mock_agent_cls.return_value = agent_instance

            create_coaching_agent(
                user_id="user-1",
                jwt_token="jwt",
                conversation_history=turns,
            )

        # Drop assistant turns that appear before the first user turn.
        assert len(agent_instance.messages) > 0
        assert agent_instance.messages[0]["role"] == "user", (
            "First replayed message must be role=user"
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/agents/coaching/test_agent.py::TestConversationHistoryCap -v`

Expected: FAIL. `MAX_REPLAYED_TURNS` is not yet defined (ImportError) and the cap behavior isn't implemented.

- [ ] **Step 3: Apply the fix**

Edit `backend/agents/coaching/agent.py`.

a) Add a module-level constant near the top (after `_PENDING = "pending-agentcore-deploy"`):

```python
# Empirically-determined safe cap for text-only conversation replay.
# Beyond ~30 turns, long text-only histories prime Nova Pro to pattern-
# match prior assistant narrative and skip tool invocation. Applied
# only on the fallback path — the AgentCoreMemorySessionManager path
# replays full tool_use/tool_result blocks and does not need the cap.
MAX_REPLAYED_TURNS = 15
```

b) Replace lines 247-261 (the `session_restored` / `conversation_history` block) with:

```python
    session_restored = session_manager is not None and agent.messages
    if conversation_history and not session_restored:
        # Cap replay length. Long text-only histories contaminate
        # Nova Pro's tool-calling.
        recent_turns = conversation_history[-MAX_REPLAYED_TURNS:]

        # Bedrock requires the first message to be role=user. Skip any
        # assistant turns that appear before the first user turn (can
        # happen after truncation or when action_event proactive
        # responses are saved without a corresponding user turn).
        first_user_seen = False
        for turn in recent_turns:
            role = turn.get("role", "")
            content = turn.get("content", "")
            if role == "user":
                first_user_seen = True
                agent.messages.append({"role": "user", "content": [{"text": content}]})
            elif role == "assistant" and first_user_seen:
                agent.messages.append({"role": "assistant", "content": [{"text": content}]})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/agents/coaching/test_agent.py::TestConversationHistoryCap -v`

Expected: All 3 tests pass.

- [ ] **Step 5: Run full agent test module**

Run: `.venv/bin/pytest tests/unit/agents/coaching/test_agent.py -v`

Expected: All existing tests still pass.

- [ ] **Step 6: Local repro verification**

Run:
```bash
AWS_PROFILE=regain AWS_DEFAULT_REGION=us-east-1 \
    .venv/bin/python scripts/nova_tool_repro.py \
    --tools 3 --user-id <sub> --replay-history --prod-prompt
```

Expected: exit code 0. "Tool invocations captured: 1" and `update_user_profile` fires.

If the repro still fails, the cap alone is insufficient and we need Phase 3 (noise filter). Commit Phase 2 anyway and move to Phase 3.

- [ ] **Step 7: Commit**

```bash
git add backend/agents/coaching/agent.py tests/unit/agents/coaching/test_agent.py
git commit -m "fix(coaching-agent): cap fallback conversation replay at 15 turns

When the AgentCoreMemorySessionManager is unavailable, we fall back to
replaying DynamoDB thread turns as text-only user/assistant messages.
Beyond ~30 turns this primes Nova Pro to pattern-match prior assistant
narrative and skip tool invocation (confirmed locally with
scripts/nova_tool_repro.py at 54 turns).

Cap replay to the last 15 turns. The AgentCoreMemorySessionManager
path is unaffected — it replays full tool_use/tool_result blocks."
```

---

## Phase 3 — Filter Noise Turns From Replay

**Why:** Even short histories can be dominated by `[proactive_check]` action-event turns and bare `[page_context: X]` prefixes with no user text after `▎`. These contribute no useful signal and add to pattern drift. Filtering them out gives the 15-turn cap 15 real conversation turns instead of a mix of background chatter.

### Task 3.1: Failing test — noise turns are excluded from replay

**Files:**
- Modify: `tests/unit/agents/coaching/test_agent.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/agents/coaching/test_agent.py`:

```python
class TestReplayNoiseFilter:
    """[proactive_check] and bare [page_context:X] turns are noise and
    must be filtered out before replay."""

    @pytest.mark.usefixtures("_pending_env")
    def test_proactive_check_turns_are_filtered(
        self, mock_direct_tools, mock_bedrock_model
    ):
        from backend.agents.coaching.agent import create_coaching_agent

        turns = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
            {"role": "user", "content": "[proactive_check] [page_data: {}]"},
            {"role": "assistant", "content": "[no_suggestion]"},
            {"role": "user", "content": "Update my target"},
        ]

        with patch("backend.agents.coaching.agent.Agent") as mock_agent_cls:
            agent_instance = MagicMock()
            agent_instance.messages = []
            mock_agent_cls.return_value = agent_instance

            create_coaching_agent(
                user_id="user-1",
                jwt_token="jwt",
                conversation_history=turns,
            )

        texts = [m["content"][0]["text"] for m in agent_instance.messages]
        assert "Hello" in texts
        assert "Hi there" in texts
        assert "Update my target" in texts
        assert not any("[proactive_check]" in t for t in texts), (
            "proactive_check turns must be filtered"
        )
        assert "[no_suggestion]" not in texts, (
            "no_suggestion assistant responses must be filtered"
        )

    @pytest.mark.usefixtures("_pending_env")
    def test_bare_page_context_turns_are_filtered(
        self, mock_direct_tools, mock_bedrock_model
    ):
        """A turn that's ONLY a [page_context:X] prefix with no user
        text after it adds no signal. The ▎ char delimits page
        context prefix from user message. When nothing follows, it's
        noise."""
        from backend.agents.coaching.agent import create_coaching_agent

        turns = [
            {"role": "user", "content": "Hello"},
            {"role": "user", "content": "[page_context: dashboard] ▎"},
            {"role": "user", "content": "[page_context: missions] ▎What mission next?"},
        ]

        with patch("backend.agents.coaching.agent.Agent") as mock_agent_cls:
            agent_instance = MagicMock()
            agent_instance.messages = []
            mock_agent_cls.return_value = agent_instance

            create_coaching_agent(
                user_id="user-1",
                jwt_token="jwt",
                conversation_history=turns,
            )

        texts = [m["content"][0]["text"] for m in agent_instance.messages]
        assert "Hello" in texts
        assert any("What mission next?" in t for t in texts), (
            "page_context turns with real user text must be kept"
        )
        assert not any(
            t.endswith("▎") or t.endswith("▎ ") for t in texts
        ), "bare page_context turns must be filtered"

    @pytest.mark.usefixtures("_pending_env")
    def test_filter_applied_before_cap(
        self, mock_direct_tools, mock_bedrock_model
    ):
        """Filter happens first, THEN cap to last 15. So noisy
        histories don't waste cap budget on filtered turns."""
        from backend.agents.coaching.agent import (
            MAX_REPLAYED_TURNS,
            create_coaching_agent,
        )

        # 20 noise turns followed by 5 real turns. After filtering,
        # only 5 turns remain and all should be replayed.
        turns = []
        for i in range(20):
            turns.append({
                "role": "user",
                "content": "[proactive_check] [page_data: {}]",
            })
            turns.append({"role": "assistant", "content": "[no_suggestion]"})
        for i in range(5):
            turns.append({"role": "user", "content": f"real user turn {i}"})
            turns.append({"role": "assistant", "content": f"real asst turn {i}"})

        with patch("backend.agents.coaching.agent.Agent") as mock_agent_cls:
            agent_instance = MagicMock()
            agent_instance.messages = []
            mock_agent_cls.return_value = agent_instance

            create_coaching_agent(
                user_id="user-1",
                jwt_token="jwt",
                conversation_history=turns,
            )

        # 10 real turns ≤ 15 cap, so all 10 should be replayed.
        assert len(agent_instance.messages) == 10
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/agents/coaching/test_agent.py::TestReplayNoiseFilter -v`

Expected: FAIL — noise filter not yet implemented.

- [ ] **Step 3: Apply the fix**

Edit `backend/agents/coaching/agent.py`.

a) Add a module-level helper function above `create_coaching_agent`:

```python
def _is_noise_turn(turn: dict) -> bool:
    """Return True if this conversation turn is background noise that
    should not be replayed.

    Filtered patterns:
    - User turns that start with [proactive_check] (action-event
      proactive checks emitted by the frontend MutationBus).
    - Assistant turns that are exactly [no_suggestion] (the agent's
      "nothing to say" response to a proactive_check).
    - User turns that are ONLY a [page_context:X] prefix with no
      real user text after the ▎ separator.
    """
    role = turn.get("role", "")
    content = turn.get("content", "") or ""
    stripped = content.strip()

    if role == "user" and stripped.startswith("[proactive_check]"):
        return True
    if role == "assistant" and stripped == "[no_suggestion]":
        return True
    if role == "user" and stripped.startswith("[page_context:"):
        # Split on the ▎ delimiter. If nothing (or just whitespace)
        # comes after it, this is a bare page-context ping with no
        # user message.
        if "▎" in stripped:
            _, _, after = stripped.partition("▎")
            if not after.strip():
                return True
    return False
```

b) Update the replay block added in Phase 2 to filter BEFORE capping:

```python
    session_restored = session_manager is not None and agent.messages
    if conversation_history and not session_restored:
        # Drop background-noise turns (proactive_check, bare
        # page_context) before capping so we don't waste cap budget.
        filtered = [t for t in conversation_history if not _is_noise_turn(t)]

        # Cap replay length. Long text-only histories contaminate
        # Nova Pro's tool-calling.
        recent_turns = filtered[-MAX_REPLAYED_TURNS:]

        # Bedrock requires the first message to be role=user.
        first_user_seen = False
        for turn in recent_turns:
            role = turn.get("role", "")
            content = turn.get("content", "")
            if role == "user":
                first_user_seen = True
                agent.messages.append({"role": "user", "content": [{"text": content}]})
            elif role == "assistant" and first_user_seen:
                agent.messages.append({"role": "assistant", "content": [{"text": content}]})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/agents/coaching/test_agent.py::TestReplayNoiseFilter -v`

Expected: All 3 tests pass.

- [ ] **Step 5: Run full agent test module**

Run: `.venv/bin/pytest tests/unit/agents/coaching/test_agent.py -v`

Expected: All tests pass (including Phase 2's `TestConversationHistoryCap`).

- [ ] **Step 6: Local repro verification**

Run the Nova repro against a real DynamoDB history that's known to contain proactive_check noise. Expected: tool fires consistently.

- [ ] **Step 7: Commit**

```bash
git add backend/agents/coaching/agent.py tests/unit/agents/coaching/test_agent.py
git commit -m "fix(coaching-agent): filter proactive_check and bare page_context noise from replay

Background action events (proactive_check/no_suggestion pairs and
bare [page_context:X] ▎ prefixes) contribute no useful signal and
crowd out real conversation turns in the 15-turn replay cap.

Filter applied before the cap so noisy histories don't waste cap
budget."
```

---

## Phase 4 — Harden System Prompt Against Tool Narration

**Why:** Prompt is the last defensive layer. Even with Phases 1-3, we want an explicit rule that the model MUST call a tool for any state-changing claim. This also helps the older Nova Lite model (still used for resume generation) and any future model we swap in.

### Task 4.1: Failing test — system prompt contains mandatory-tool-call rule

**Files:**
- Modify: `tests/unit/agents/coaching/test_prompts.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/agents/coaching/test_prompts.py` inside `TestGetSystemPrompt`:

```python
    def test_mandatory_tool_call_rule_present(self) -> None:
        """The prompt must contain an explicit rule that the agent
        MUST call a tool to perform any action (never claim a state
        change in narrative alone)."""
        prompt = get_system_prompt()

        # Check for the key directive phrases.
        assert "MUST call a tool" in prompt, (
            "Prompt must contain explicit 'MUST call a tool' directive"
        )
        assert "narrative alone" in prompt or "narrative only" in prompt, (
            "Prompt must forbid narrating actions without tool calls"
        )

    def test_mandatory_tool_call_rule_survives_skill_tags(self) -> None:
        """Rule is present whether or not valid_skill_tags is set."""
        with_tags = get_system_prompt(valid_skill_tags=["Python"])
        without_tags = get_system_prompt()

        for p in (with_tags, without_tags):
            assert "MUST call a tool" in p
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/agents/coaching/test_prompts.py::TestGetSystemPrompt::test_mandatory_tool_call_rule_present tests/unit/agents/coaching/test_prompts.py::TestGetSystemPrompt::test_mandatory_tool_call_rule_survives_skill_tags -v`

Expected: FAIL — the phrase "MUST call a tool" is not yet in the prompt.

- [ ] **Step 3: Apply the fix**

Edit `backend/agents/coaching/prompts.py` behavioral rules section. Locate the `## Behavioral Rules` numbered list (lines 86-96 in the current file) and add a new rule immediately before rule 1 (making it the new rule 1, shifting the rest):

```markdown
## Behavioral Rules

1. You MUST call a tool to perform any action. Never claim you updated, created, logged, retrieved, completed, or generated anything in narrative alone. If a user asks you to change state (update their profile, create a campaign, log evidence, complete a mission, generate a mission, write a calendar entry, generate a resume), you must invoke the corresponding tool in the same turn. If you cannot invoke the tool for any reason, say so explicitly — do not pretend the action succeeded.
2. Follow the Session Opening procedure when receiving a `[greeting_request]` message. For all other messages, call `read_user_profile` before your first response if you haven't already this session.
3. Memory from prior sessions is automatically recalled at session start. Use recall_memory for targeted follow-up queries if you need specific context (e.g. "what was the avoidance pattern we discussed?"). If no prior context is available, acknowledge the limited context briefly.
4. During check-ins, call `get_current_mission` and `get_campaign_status` to understand where the user stands.
5. When the user describes completing something or demonstrating a skill, call log_evidence or complete_mission immediately. Don't wait for them to ask.
6. Detect avoidance patterns: if get_current_mission returns avoidance_signals, address them directly but compassionately. Name the pattern, explain why it matters, and suggest a lower-barrier mission in that category.
7. Never give generic advice. Every recommendation must reference the user's specific profile, evidence history, or market data.
8. Never state facts about the user's phase, mission count, evidence count, or activity level without first reading them from a tool response. If you haven't called a tool, you don't know the answer — call the tool first.
9. Adapt tone to momentum: high completion rates get stretch challenges; low completion rates get smaller wins and encouragement grounded in past evidence.
10. Session memory is stored automatically — do not attempt to store session summaries manually.
```

(Concretely: the new rule 1 is `You MUST call a tool to perform any action. Never claim you updated...`; the previous rules 1-9 get renumbered to 2-10.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/agents/coaching/test_prompts.py -v`

Expected: All tests pass.

- [ ] **Step 5: Local repro verification with the prod prompt**

Run:
```bash
AWS_PROFILE=regain AWS_DEFAULT_REGION=us-east-1 \
    .venv/bin/python scripts/nova_tool_repro.py \
    --tools 18 --user-id <sub> --replay-history --prod-prompt
```

Expected: exit code 0. Tool fires.

- [ ] **Step 6: Commit**

```bash
git add backend/agents/coaching/prompts.py tests/unit/agents/coaching/test_prompts.py
git commit -m "fix(coaching-prompt): add explicit 'MUST call a tool' behavioral rule

Nova Pro can narrate successful actions (profile updates, mission
generation, etc.) without actually invoking the corresponding tool,
particularly after long text-only conversation replay. Phases 1-3
address the replay root cause; this phase adds an explicit prompt-
level rule as the final defensive layer.

New rule 1 in the Behavioral Rules section:

  You MUST call a tool to perform any action. Never claim you
  updated, created, logged, retrieved, completed, or generated
  anything in narrative alone. [...]"
```

---

## Post-Deployment Verification (All Phases)

After Phase 4 is merged and the coaching Lambda is redeployed, run these manual checks:

- [ ] **Step 1: Chat with the production bot as the affected user**

1. Open the REGAIN app signed in as the user whose history triggered the original bug (54-turn thread).
2. Ask: "Please set my target role to Staff Engineer."
3. Wait for the response.

Expected:
- Agent confirms the update.
- `update_user_profile` appears in the tool-execution feed (the `ToolStep` chips in the UI).
- In CloudWatch Logs (`/aws/lambda/RegainChatStreamFn`), `BEFORE tool call: update_user_profile` is visible in the same session.
- In DynamoDB `RegainUserProfiles`, the user's `targetRole` attribute reflects the new value.

- [ ] **Step 2: Verify the session manager attached cleanly**

In CloudWatch Logs:
```
filter @message like /AgentCoreMemorySessionManager/
| fields @timestamp, @message
| limit 20
```

Expected: no "Failed to create AgentCoreMemorySessionManager" warnings after the deploy.

- [ ] **Step 3: Stress-test with a stale session**

For the same user, wait at least 10 minutes, reconnect to the WebSocket, and ask again to update the target role.

Expected: still fires the tool. Session manager restores history from AgentCore Memory; no fallback replay needed.

- [ ] **Step 4: Clean up**

Once Phase 1 is proven stable in production for ≥ 48 hours, consider removing the `MAX_REPLAYED_TURNS` cap and noise filter if we're confident the fallback path is never used. Until then, keep the defense in depth.

---

## Self-Review

**Spec coverage:**

| Fix (from user directive) | Covered by |
| ---------------------------------- | ---------------- |
| 1. Session manager pydantic bug    | Phase 1, Task 1.1 |
| 2. Cap replayed turns              | Phase 2, Task 2.1 |
| 3. Filter noise turns              | Phase 3, Task 3.1 |
| 4. Strengthen system prompt        | Phase 4, Task 4.1 |

All four user-requested fixes are present. No other fixes added.

**Placeholder scan:** No "TBD" / "TODO" / "similar to above" in task bodies. All code blocks are complete.

**Type consistency:** `MAX_REPLAYED_TURNS` (int, 15) is introduced in Phase 2 and referenced unchanged in Phase 3. `_is_noise_turn(turn: dict) -> bool` signature is consistent with how it's called. `_create_session_manager` signature is unchanged (only its body changes).

**Naming consistency:** `conversation_history` / `recent_turns` / `filtered` terminology is consistent between phases. The `first_user_seen` flag persists across Phases 2 and 3 (it was already in the codebase).

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-15-tool-hallucination-fix.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task (Task 1.1 → Task 2.1 → Task 3.1 → Task 4.1), review between tasks, fast iteration. Each task is self-contained TDD so subagents don't need session context.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints for review.

Which approach?
