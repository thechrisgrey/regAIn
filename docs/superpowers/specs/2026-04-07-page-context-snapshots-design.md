# Page Context Snapshots for Agent

**Date:** 2026-04-07

## Problem

The coaching agent receives `[page_context: dashboard]` but has no data about what the user actually sees. It must independently call tools to reconstruct page state, which it sometimes skips (hallucinating "Expansion phase" when the user is in Foundation, or "actively engaging" with 0 completions). The agent and the frontend make separate calls to the same data, creating divergence.

## Solution

Each page emits a structured JSON snapshot of its rendered data via the MutationBus. The coach modal caches the latest snapshot and attaches it as `[page_data: {...}]` to every message sent to the agent. The system prompt instructs the agent to treat `page_data` as authoritative for page-level facts.

## Architecture

### Data Flow

```
Page renders -> hook data available -> page emits {type: 'page:snapshot', payload: {...}}
                                                        |
CoachModal subscribes -> caches latest snapshot in ref
                                                        |
User sends message or proactive check fires
                                                        |
Message: "[page_context: dashboard] [page_data: {json}] user message"
                                                        |
Agent reads [page_data], trusts it, only calls tools for actions/deeper queries
```

### Delivery Mechanism

1. Each page emits `page:snapshot` via MutationBus when data loads or changes.
2. CoachModal subscribes and caches the latest snapshot in a `useRef`.
3. Every outgoing message (chat, proactive check, action event) includes `[page_data: {json}]` after `[page_context: X]`.
4. Missions page also re-emits on form input changes (debounced) to capture in-progress reflections.

### Agent Trust Model

The `page_data` snapshot is the source of truth for page-level facts. The agent:
- States facts (phase, counts, scores, mission titles, reflections) directly from `page_data` without calling tools.
- References `formInput` to help the user refine reflections or suggest skill tags.
- Only calls tools for actions (complete mission, log evidence, generate mission) or deeper data not in the snapshot (behavioral patterns, market insights, memory recall).
- Never contradicts `page_data`.

## Page Snapshot Schemas

### Dashboard

```json
{
  "page": "dashboard",
  "phase": "foundation",
  "phaseProgress": 33,
  "targetRole": "AI Implementation Lead",
  "missionsCompleted": 0,
  "evidenceCount": 0,
  "daysActive": 1,
  "startDate": "2026-04-05",
  "skillsFocus": ["Leadership", "Data Analysis"]
}
```

**Source:** `useDashboard()` -> `data.campaign` + `data.stats`

### Missions

```json
{
  "page": "missions",
  "activeMissions": 2,
  "primaryMission": {
    "title": "Lead a Small Team Project",
    "description": "Organize and lead a small team...",
    "skillTag": "Leadership",
    "status": "in_progress"
  },
  "alternateMissions": [{"title": "...", "skillTag": "..."}],
  "historyCount": 3,
  "completedCount": 2,
  "skippedCount": 1,
  "dailyRemaining": 5,
  "dailyLimit": 6,
  "formInput": {
    "reflection": "I led the sprint planning meeting today...",
    "artifactUrl": "https://docs.google.com/...",
    "skillTags": ["Leadership", "Team Management"]
  }
}
```

**Source:** `useMissions()` -> derived `activeMissions`, `historyMissions`, `primaryMission`, `alternateMissions`. Form state from `CompletionForm` component (reflection, artifactUrl, skillTags).

`formInput` is `null` when the completion form has no user input. Present only when the user has typed something. Emitted on input changes with debounce to avoid flooding.

### Evidence

```json
{
  "page": "evidence",
  "totalItems": 12,
  "skillsCovered": 4,
  "topSkills": [
    {"skill": "Leadership", "count": 5},
    {"skill": "Data Analysis", "count": 3},
    {"skill": "Python Programming", "count": 2},
    {"skill": "Communication", "count": 2}
  ],
  "recentItems": [
    {"skillTag": "Leadership", "reflection": "Led cross-functional sync...", "createdAt": "2026-04-06T14:30:00Z"},
    {"skillTag": "Data Analysis", "reflection": "Built dashboard tracking...", "createdAt": "2026-04-05T10:15:00Z"}
  ]
}
```

**Source:** `useEvidence()` -> `evidence` array + `computeSkillStats()`. `recentItems` is the 5 most recent entries with skillTag, reflection text, and timestamp.

### Profile

```json
{
  "page": "profile",
  "username": "cperez",
  "targetRole": "AI Implementation Lead",
  "phase": "foundation",
  "daysActive": 1,
  "missionsCompleted": 0,
  "evidenceCount": 0,
  "skillsFocus": ["Leadership", "Data Analysis"],
  "skillDevelopment": [
    {"skill": "Leadership", "count": 5, "intensity": "high"},
    {"skill": "Data Analysis", "count": 3, "intensity": "medium"}
  ]
}
```

**Source:** `useDashboard()` + `useEvidence()` + `useAuth()`.

### Resume (no resume)

```json
{
  "page": "resume",
  "hasResume": false
}
```

### Resume (with resume)

```json
{
  "page": "resume",
  "hasResume": true,
  "version": 1,
  "generatedAt": "2026-04-06T09:00:00Z",
  "missionsCompleted": 5,
  "evidenceItems": 12,
  "marketAlignment": 68,
  "targetRole": "AI Implementation Lead",
  "phase": "expansion",
  "skills": [
    {"name": "Leadership", "proficiency": "developing", "evidenceCount": 4, "strongestEvidence": "Led cross-functional team of 6..."}
  ],
  "topAccomplishments": ["Led sprint planning across 3 teams", "Built analytics dashboard"]
}
```

**Source:** `useResume()` -> `resume.frontmatter` + `resume.content`.

### Impact Scorecard (locked)

```json
{
  "page": "scorecard",
  "unlocked": false,
  "missionsCompleted": 1,
  "missionsNeeded": 3
}
```

### Impact Scorecard (unlocked)

```json
{
  "page": "scorecard",
  "unlocked": true,
  "cri": 42,
  "missionsCompleted": 5,
  "evidenceCount": 12,
  "targetRole": "AI Implementation Lead",
  "phase": "foundation",
  "computedAt": "2026-04-07T08:00:00Z",
  "dimensions": {
    "velocity": 55,
    "evidence": 38,
    "marketFit": 45,
    "phase": 33,
    "difficulty": 40
  }
}
```

**Source:** `useImpactScore()` -> `data.cri`, dimension scores, detail.

### Analytics

```json
{
  "page": "analytics",
  "currentStreak": 3,
  "longestStreak": 5,
  "missionsCompleted": 8,
  "missionsSkipped": 1,
  "avgPerWeek": 2.5,
  "topSkills": [{"skill": "Leadership", "count": 4}],
  "activeDaysThisWeek": 3
}
```

**Source:** `useAnalytics()`.

### Voice Practice

```json
{
  "page": "voice-practice",
  "status": "idle",
  "totalSessions": 3,
  "recentSessions": [
    {"type": "interview", "date": "2026-04-06", "overallScore": 72}
  ]
}
```

**Source:** `useVoicePractice()` + `useVoiceSessions()`.

### Careers (search results)

```json
{
  "page": "careers",
  "searchKeyword": "software engineer",
  "resultCount": 8,
  "results": [
    {"title": "Software Developers", "code": "15-1252.00", "brightOutlook": true}
  ]
}
```

**Source:** `useOnet()` -> `results`.

### Careers (detail view)

```json
{
  "page": "careers-detail",
  "title": "Software Developers",
  "code": "15-1252.00",
  "tags": {"brightOutlook": true, "green": false, "apprenticeship": false},
  "whatTheyDo": "Design, develop...",
  "topTasks": ["Design software...", "Modify existing..."],
  "education": {"jobZone": 4, "title": "...", "usuallyNeeded": ["Bachelor's degree"]},
  "outlook": {"category": "Bright", "description": "..."},
  "salary": {"median": 127260, "low": 74600, "high": 197000},
  "topKnowledge": [{"name": "Computers and Electronics", "score": 92}],
  "topSkills": [{"name": "Programming", "score": 88}],
  "topAbilities": [{"name": "Deductive Reasoning", "score": 78}],
  "personality": {"topInterest": "Investigative", "workStyles": ["Analytical Thinking", "Attention to Detail"]},
  "hotTechnologies": ["Python", "SQL", "JavaScript"],
  "relatedCareers": [{"title": "Web Developers", "code": "15-1254.00"}]
}
```

**Source:** `useOnet()` -> `careerDetail` (full `OnetCareerReport` object).

## System Prompt Changes

Add to the Page Context Awareness section in `prompts.py`:

```
When a message includes [page_data: {...}], this JSON contains the exact data
currently displayed on the user's screen. Treat it as authoritative:
- State facts (phase, counts, scores, mission titles, reflections) directly
  from page_data without calling tools first
- The "formInput" field contains what the user has typed but not yet submitted --
  you can reference this to help them refine their reflection or suggest skill tags
- Only call tools when you need to take an action (complete mission, log evidence,
  generate mission) or need deeper data not in the snapshot (behavioral patterns,
  market insights, memory recall)
- Never contradict page_data -- if it says phase is "foundation", the phase is foundation
```

Update the proactive check instructions to use `page_data` instead of requiring tool calls for basic context:

```
When you receive [proactive_check] with [page_data]:
1. Read page_data for the current state (phase, counts, mission status, etc.)
2. Only call tools if you need deeper context not in the snapshot (patterns, memory, market data)
3. Offer one actionable suggestion in 1-2 sentences based on the data
4. If nothing useful to suggest, respond with "[no_suggestion]"
```

## Files Changed

| File | Change |
|------|--------|
| `hooks/MutationBusContext.tsx` | Add `page:snapshot` event type |
| `pages/Dashboard.tsx` | Emit snapshot on data load |
| `pages/Missions.tsx` | Emit snapshot on data load + form input changes (debounced) |
| `pages/Evidence.tsx` | Emit snapshot on data load |
| `pages/Profile.tsx` | Emit snapshot on data load |
| `pages/ResumePage.tsx` | Emit snapshot on data load |
| `pages/ImpactScorecardPage.tsx` | Emit snapshot on data load |
| `pages/AnalyticsPage.tsx` | Emit snapshot on data load |
| `pages/VoicePracticePage.tsx` | Emit snapshot on data load |
| `pages/OnetPage.tsx` | Emit snapshot on search results + detail load |
| `components/CoachModal.tsx` | Subscribe to `page:snapshot`, cache in ref, attach `[page_data]` to all messages |
| `backend/agents/coaching/prompts.py` | Add `page_data` trust instructions, update proactive check instructions |

## Testing

- Unit test per page: verify snapshot emitted with correct shape when data loads.
- Unit test for CoachModal: verify `[page_data: {...}]` attached to outgoing messages.
- Unit test for Missions: verify `formInput` included when user has typed, `null` when empty.
- Integration: verify agent receives and uses `page_data` correctly (manual test against live agent).

## Non-Goals

- Sending snapshots to the backend as a separate API endpoint (frontend-only delivery via WebSocket message).
- Caching snapshots server-side (the agent sees what was sent in the message).
- Snapshot for the Coaching full-page chat (it IS the chat) or Onboarding (one-time flow).
