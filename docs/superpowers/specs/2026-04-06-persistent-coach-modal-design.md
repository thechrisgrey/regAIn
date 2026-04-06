# Persistent Coach Modal — Design Spec

**Date:** 2026-04-06
**Purpose:** Replace the dedicated coaching page with an always-available, page-aware floating chat panel powered by Nova Pro. The coach is proactive, contextual, and available on every authenticated page.

---

## 1. Summary

A bottom-right floating chat panel that replaces `/coaching` as a dedicated page. The coach lives in `Layout.tsx`, persists across navigation, connects via the existing WebSocket infrastructure, and uses the full Strands agent toolset. The model is upgraded from Nova Lite to Nova Pro (`amazon.nova-pro-v1:0`) for better reasoning and accuracy.

The coach is page-aware: it knows which route the user is on and proactively offers contextual suggestions based on real user data.

---

## 2. Architecture

The existing `CoachingContext` already lives at the app root and manages WebSocket state, messages, streaming, reconnection, and sessionStorage persistence. No changes to WebSocket logic, message state, or streaming infrastructure.

**Changes:**
- Remove `/coaching` route and `CoachingPage.tsx`
- Remove "Coaching" from sidebar nav
- Add `<CoachModal />` to `Layout.tsx` — renders on every authenticated page
- Lazy-connect WebSocket on first modal open (not on page load)
- Upgrade model to Nova Pro
- Add page context awareness to agent prompt

---

## 3. Frontend: CoachModal Component

### 3.1 States

**Collapsed:** Floating button, bottom-right corner, 56px circle with chat icon. Subtle pulse animation when a proactive suggestion is pending. Small dot badge for unread messages.

**Expanded:** 400px wide, ~500px tall panel anchored to bottom-right. Contains:
- Header: "Coach" label, minimize button, close button
- Message list: scrollable, MarkdownMessage for assistant, plain text bubbles for user
- Tool activity: AgentActivityFeed inline above streaming text
- Input: text field + send button

**Minimized with notification:** Collapsed button with dot badge indicating unread proactive message.

### 3.2 Behavior

- **Open/close:** Click the floating button to toggle. Escape key closes. Click outside does NOT close (prevents accidental dismissal during conversation).
- **Persist across pages:** Messages survive navigation (sessionStorage via existing CoachingContext).
- **Lazy WebSocket:** Don't connect until the user first opens the modal. After first open, stay connected for the session.
- **Scroll:** Auto-scroll to bottom on new messages. Manual scroll up pauses auto-scroll.
- **Resize:** Drag top edge to make panel taller (max 80vh). Persisted to localStorage.

### 3.3 Session Type Auto-Detection

No user-facing dropdown. Automatic:
- No profile exists → `session_type: "onboarding"`
- Has profile + first message of the day → `session_type: "checkin"` with `[greeting_request]`
- Has profile + mid-conversation → `session_type: "general"`

### 3.4 Reused Components (no changes)

- `CoachingContext` / `useCoaching` hook — all WebSocket and state logic
- `MarkdownMessage` — assistant message rendering
- `AgentActivityFeed` — tool execution step display

---

## 4. Page-Aware Proactive Prompts

The modal reads `useLocation().pathname` and sends page context to the agent. Proactive messages are real agent responses — not frontend-generated text.

### 4.1 Trigger Rules

| Route | Context Tag | Proactive Trigger |
|-------|-------------|-------------------|
| `/dashboard` | `[page_context: dashboard]` | First visit of the day: "Welcome back. Here's what changed." |
| `/missions` | `[page_context: missions]` | No pending missions: "Ready for a new mission?" |
| `/evidence` | `[page_context: evidence]` | Low skill breadth: "Your vault could use more breadth in {X}." |
| `/scorecard` | `[page_context: scorecard]` | Hot skills gap: "Your top gap is {X} — want a mission for it?" |
| `/analytics` | `[page_context: analytics]` | Velocity declining: "Your completion rate dipped. Want to talk about what's blocking you?" |
| `/resume` | `[page_context: resume]` | Resume stale: "You've logged 5 new evidence entries since your last resume. Want to regenerate?" |
| `/onet` | `[page_context: careers]` | First visit: "Exploring careers? Tell me your target role and I'll pull market data." |
| `/profile` | `[page_context: profile]` | Phase gate near: "You're 3 missions from advancing to the next phase." |

### 4.2 Proactive Behavior

- Fires once per page per session (tracked in a `Set<string>` ref, resets on reload)
- Only fires if the modal is collapsed (doesn't interrupt active conversations)
- Delivered as a real agent message via WebSocket
- Agent receives `[page_context: X] [proactive_check]` and decides based on user data
- If nothing useful to say, agent responds with exactly `[no_suggestion]` — frontend detects this string and discards the message (never shown to user)
- Proactive message causes the floating button to pulse and show a dot badge
- User opens modal, sees the suggestion, can respond or dismiss

### 4.3 System Prompt Addition

New section in `prompts.py`:

```
## Page Context Awareness

When you receive a [page_context: X] tag, the user is currently viewing that page.
Use this context to make your response relevant to what they're looking at.

When you also receive [proactive_check], briefly offer one actionable suggestion
relevant to that page based on the user's actual data — or respond with exactly
"[no_suggestion]" if there's nothing useful to suggest. Keep proactive messages
to 1-2 sentences. Be specific — reference real numbers, skill names, or mission
titles. Don't repeat a suggestion you've already made in this session.

Page context guide:
- dashboard: user is viewing their campaign overview and stats
- missions: user is viewing their mission list
- evidence: user is browsing their evidence vault
- scorecard: user is viewing their Impact Scorecard and CRI
- analytics: user is viewing activity analytics and velocity
- resume: user is viewing or generating their resume
- careers: user is exploring O*NET career data
- profile: user is viewing their profile settings
```

---

## 5. Backend Changes

### 5.1 Model Upgrade

Change `BEDROCK_MODEL_ID` environment variable from `amazon.nova-lite-v1:0` to `amazon.nova-pro-v1:0`.

**Files:**
- `infra/stacks/agent_stack.py` — update model ID in `_bedrock_env()` or Lambda environment
- `infra/stacks/api_stack.py` — if coaching Lambda model ID is set here

### 5.2 IAM Policy

Update Bedrock `InvokeModel` resource ARN to include `amazon.nova-pro-v1:0`.

**Files:**
- `infra/stacks/agent_stack.py` — Bedrock IAM policy statement
- `infra/stacks/api_stack.py` — if coaching Lambda has its own Bedrock policy

### 5.3 System Prompt

Add page context awareness section to `backend/agents/coaching/prompts.py` (~15 lines).

### 5.4 No Other Backend Changes

- No new Lambda functions
- No new API routes
- No new DynamoDB tables
- WebSocket handler unchanged
- Strands agent tools unchanged
- Streaming protocol unchanged

---

## 6. Removals

| Removed | Reason |
|---------|--------|
| `frontend/src/pages/CoachingPage.tsx` | Replaced by CoachModal |
| `CoachingPage` lazy import in `App.tsx` | Route deleted |
| `/coaching` route in router | No longer a page |
| "Coaching" nav item in sidebar | No destination page |
| Voice/text toggle in chat UI | Voice Practice is its own page |
| Session type dropdown | Auto-detected |
| "Clear" as primary action | Moved to subtle menu option in modal header |

---

## 7. Implementation Plan

### Phase 1: Backend (1 task)
- Upgrade model ID to Nova Pro in CDK
- Update IAM policy for Nova Pro
- Add page context section to system prompt
- Deploy

### Phase 2: Frontend — CoachModal (2-3 tasks)
- Build `<CoachModal />` component (collapsed/expanded states, floating button, panel layout)
- Wire to existing `useCoaching` hook (message list, input, streaming, tool steps)
- Add lazy WebSocket connection (connect on first open)
- Add page context detection (`useLocation` → context tag injection)
- Add proactive message logic (per-page triggers, once-per-session tracking, pulse animation)

### Phase 3: Cleanup (1 task)
- Remove CoachingPage, route, and sidebar nav item
- Update tests
- Remove session type dropdown logic from CoachingContext (replace with auto-detection)

---

## 8. Risks

| Risk | Mitigation |
|------|-----------|
| Nova Pro costs more than Nova Lite | Monitor Bedrock costs post-deploy. Nova Pro is ~3x Lite pricing but significantly better quality. |
| Proactive messages feel spammy | Once per page per session. Agent decides based on real data. `[no_suggestion]` escape hatch. |
| Modal blocks important page content | 400px panel in bottom-right. Main content is still fully visible and interactive. |
| Removing /coaching breaks bookmarks | Add a redirect: `/coaching` → `/dashboard` (with modal auto-open). |
