# Page Context Snapshots Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the coaching agent a structured JSON snapshot of every page's rendered data so it never hallucinates facts the user can see.

**Architecture:** Each page calls `setPageSnapshot(data)` on the MutationBus context when its data loads. CoachModal reads the snapshot and attaches `[page_data: {json}]` to every outgoing message. The system prompt instructs the agent to treat page_data as authoritative.

**Tech Stack:** React 19, TypeScript, Vitest, Tailwind v4

---

### Task 1: Extend MutationBus with page snapshot support

**Files:**
- Modify: `frontend/src/hooks/MutationBusContext.tsx`
- Modify: `frontend/src/hooks/useMutationBus.ts`
- Test: `frontend/src/__tests__/hooks/usePageSnapshot.test.tsx` (new)

The existing MutationBus callbacks are `() => void` — they don't carry data. Rather than changing that interface, we add a dedicated `pageSnapshotRef` + `setPageSnapshot` + `getPageSnapshot` to the context. This keeps the event bus unchanged and adds a clean data channel.

- [ ] **Step 1: Write failing test**

Create `frontend/src/__tests__/hooks/usePageSnapshot.test.tsx`:

```tsx
import { renderHook, act } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { MutationBusProvider } from '../../hooks/MutationBusContext';
import { useMutationBus } from '../../hooks/useMutationBus';

function wrapper({ children }: { children: React.ReactNode }) {
  return <MutationBusProvider>{children}</MutationBusProvider>;
}

describe('page snapshot via MutationBus', () => {
  it('returns null when no snapshot has been set', () => {
    const { result } = renderHook(() => useMutationBus(), { wrapper });
    expect(result.current.getPageSnapshot()).toBeNull();
  });

  it('stores and retrieves a snapshot', () => {
    const { result } = renderHook(() => useMutationBus(), { wrapper });
    const snapshot = { page: 'dashboard', phase: 'foundation', missionsCompleted: 0 };

    act(() => {
      result.current.setPageSnapshot(snapshot);
    });

    expect(result.current.getPageSnapshot()).toEqual(snapshot);
  });

  it('overwrites previous snapshot', () => {
    const { result } = renderHook(() => useMutationBus(), { wrapper });

    act(() => {
      result.current.setPageSnapshot({ page: 'dashboard', phase: 'foundation' });
    });
    act(() => {
      result.current.setPageSnapshot({ page: 'missions', activeMissions: 2 });
    });

    expect(result.current.getPageSnapshot()).toEqual({ page: 'missions', activeMissions: 2 });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest --run src/__tests__/hooks/usePageSnapshot.test.tsx`
Expected: FAIL — `getPageSnapshot` and `setPageSnapshot` do not exist.

- [ ] **Step 3: Implement MutationBus extension**

In `frontend/src/hooks/MutationBusContext.tsx`, add the snapshot ref and functions:

```tsx
import { createContext, useRef, useCallback, type ReactNode } from 'react';

export type MutationEventType =
  | 'mission:completed'
  | 'mission:generated'
  | 'evidence:logged'
  | 'campaign:created'
  | 'resume:generated'
  | 'voice:session_completed'
  | 'scorecard:viewed'
  | 'profile:updated'
  | 'page:navigated';

export interface MutationEvent {
  type: MutationEventType;
  payload?: Record<string, unknown>;
}

export type PageSnapshot = Record<string, unknown>;

export interface MutationBusContextType {
  emit: (event: MutationEvent) => void;
  subscribe: (type: MutationEventType, callback: () => void) => () => void;
  setPageSnapshot: (snapshot: PageSnapshot) => void;
  getPageSnapshot: () => PageSnapshot | null;
}

const MutationBusContext = createContext<MutationBusContextType | undefined>(undefined);

export { MutationBusContext };

export function MutationBusProvider({ children }: { children: ReactNode }) {
  const listenersRef = useRef<Map<MutationEventType, Set<() => void>>>(new Map());
  const pageSnapshotRef = useRef<PageSnapshot | null>(null);

  const subscribe = useCallback((type: MutationEventType, callback: () => void) => {
    if (!listenersRef.current.has(type)) {
      listenersRef.current.set(type, new Set());
    }
    listenersRef.current.get(type)!.add(callback);
    return () => {
      listenersRef.current.get(type)?.delete(callback);
    };
  }, []);

  const emit = useCallback((event: MutationEvent) => {
    listenersRef.current.get(event.type)?.forEach((cb) => cb());
  }, []);

  const setPageSnapshot = useCallback((snapshot: PageSnapshot) => {
    pageSnapshotRef.current = snapshot;
  }, []);

  const getPageSnapshot = useCallback(() => {
    return pageSnapshotRef.current;
  }, []);

  return (
    <MutationBusContext.Provider value={{ emit, subscribe, setPageSnapshot, getPageSnapshot }}>
      {children}
    </MutationBusContext.Provider>
  );
}
```

No changes needed to `useMutationBus.ts` — it already returns the full context type.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest --run src/__tests__/hooks/usePageSnapshot.test.tsx`
Expected: PASS (3 tests)

- [ ] **Step 5: Run full frontend suite**

Run: `cd frontend && npx vitest --run 2>&1 | tail -5`
Expected: All 240+ tests pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/hooks/MutationBusContext.tsx frontend/src/__tests__/hooks/usePageSnapshot.test.tsx
git commit -m "feat: add page snapshot support to MutationBus context"
```

---

### Task 2: CoachModal — attach page_data to all messages

**Files:**
- Modify: `frontend/src/components/CoachModal.tsx`
- Test: `frontend/src/__tests__/components/CoachModalSnapshot.test.tsx` (new)

The CoachModal reads `getPageSnapshot()` and serializes it into every outgoing message as `[page_data: {...}]`.

- [ ] **Step 1: Write failing test**

Create `frontend/src/__tests__/components/CoachModalSnapshot.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { MutationBusProvider } from '../../hooks/MutationBusContext';
import { useMutationBus } from '../../hooks/useMutationBus';

// We test the message formatting logic in isolation rather than the full CoachModal
// because CoachModal depends on CoachingContext (WebSocket), Auth, etc.

describe('page_data message formatting', () => {
  it('builds message with page_data when snapshot exists', () => {
    // Simulate the formatting logic that CoachModal uses
    const snapshot = { page: 'dashboard', phase: 'foundation', missionsCompleted: 0 };
    const pageContext = 'dashboard';
    const userText = 'How am I doing?';

    const message = snapshot
      ? `[page_context: ${pageContext}] [page_data: ${JSON.stringify(snapshot)}] ${userText}`
      : `[page_context: ${pageContext}] ${userText}`;

    expect(message).toContain('[page_data: {"page":"dashboard"');
    expect(message).toContain('"phase":"foundation"');
    expect(message).toContain('How am I doing?');
  });

  it('builds message without page_data when no snapshot', () => {
    const snapshot = null;
    const pageContext = 'dashboard';
    const userText = 'Hello';

    const message = snapshot
      ? `[page_context: ${pageContext}] [page_data: ${JSON.stringify(snapshot)}] ${userText}`
      : `[page_context: ${pageContext}] ${userText}`;

    expect(message).not.toContain('[page_data:');
    expect(message).toContain('[page_context: dashboard]');
    expect(message).toContain('Hello');
  });

  it('builds proactive check with page_data', () => {
    const snapshot = { page: 'missions', activeMissions: 2 };
    const pageContext = 'missions';

    const message = snapshot
      ? `[page_context: ${pageContext}] [page_data: ${JSON.stringify(snapshot)}] [proactive_check]`
      : `[page_context: ${pageContext}] [proactive_check]`;

    expect(message).toContain('[page_data: {"page":"missions"');
    expect(message).toContain('[proactive_check]');
  });

  it('strips page_data from visible user messages', () => {
    const content = '[page_context: dashboard] [page_data: {"page":"dashboard"}] How am I doing?';
    const cleaned = content
      .replace(/\[page_context:\s*\w+\]\s*/g, '')
      .replace(/\[page_data:\s*\{[^}]*(?:\{[^}]*\}[^}]*)*\}]\s*/g, '')
      .replace(/\[proactive_check\]\s*/g, '')
      .trim();

    expect(cleaned).toBe('How am I doing?');
  });
});
```

- [ ] **Step 2: Run test to verify it fails (or passes — these are pure logic tests)**

Run: `cd frontend && npx vitest --run src/__tests__/components/CoachModalSnapshot.test.tsx`

- [ ] **Step 3: Implement CoachModal changes**

In `frontend/src/components/CoachModal.tsx`:

**3a. Import `getPageSnapshot` from the hook.** Near the top where hooks are called, add:

```tsx
const { emit, getPageSnapshot } = useMutationBus();
```

(If `useMutationBus` is not already imported, add the import.)

**3b. Create a helper function** inside the component (before `useEffect`s):

```tsx
  // Build message prefix with page context and snapshot data.
  function buildPrefix(): string {
    const snapshot = getPageSnapshot();
    if (snapshot) {
      return `[page_context: ${pageContext}] [page_data: ${JSON.stringify(snapshot)}]`;
    }
    return `[page_context: ${pageContext}]`;
  }
```

**3c. Update the proactive check** (around line 247-250). Change:

```tsx
      void sendMessage(
        `[page_context: ${pageContext}] [proactive_check]`,
        'general',
      );
```

To:

```tsx
      void sendMessage(
        `${buildPrefix()} [proactive_check]`,
        'general',
      );
```

**3d. Update handleSend** (around line 292-294). Change:

```tsx
      await sendMessage(
        `[page_context: ${pageContext}] ${text}`,
        sessionType,
      );
```

To:

```tsx
      await sendMessage(
        `${buildPrefix()} ${text}`,
        sessionType,
      );
```

**3e. Update the user message filter** (around line 261-267) to also strip `[page_data: ...]`. Change:

```tsx
        const cleaned = m.content
          .replace(/\[page_context:\s*\w+\]\s*/g, '')
          .replace(/\[proactive_check\]\s*/g, '')
          .trim();
```

To:

```tsx
        const cleaned = m.content
          .replace(/\[page_context:\s*\w+\]\s*/g, '')
          .replace(/\[page_data:\s*\{[^}]*(?:\{[^}]*\}[^}]*)*\}]\s*/g, '')
          .replace(/\[proactive_check\]\s*/g, '')
          .trim();
```

- [ ] **Step 4: Run tests**

Run: `cd frontend && npx vitest --run 2>&1 | tail -5`
Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/CoachModal.tsx frontend/src/__tests__/components/CoachModalSnapshot.test.tsx
git commit -m "feat: attach page_data snapshot to all coaching messages"
```

---

### Task 3: Dashboard snapshot

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx`
- Test: `frontend/src/__tests__/pages/DashboardSnapshot.test.tsx` (new)

- [ ] **Step 1: Write failing test**

Create `frontend/src/__tests__/pages/DashboardSnapshot.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest';
import { phaseLabel, phaseProgress, daysActive } from '../../utils/campaign';
import type { Campaign } from '../../types';

// Test the snapshot builder function in isolation
function buildDashboardSnapshot(
  campaign: Campaign,
  stats: { missionsCompleted: number; evidenceCount: number },
) {
  return {
    page: 'dashboard' as const,
    phase: phaseLabel(campaign.phase),
    phaseProgress: phaseProgress(campaign.phase),
    targetRole: campaign.targetRole,
    missionsCompleted: stats.missionsCompleted,
    evidenceCount: stats.evidenceCount,
    daysActive: daysActive(campaign.startDate),
    startDate: campaign.startDate,
    skillsFocus: campaign.skillsFocus,
  };
}

describe('buildDashboardSnapshot', () => {
  const campaign: Campaign = {
    userId: 'u1',
    campaignId: 'c1',
    title: 'AI Career',
    phase: 'foundation',
    status: 'active',
    startDate: '2026-04-05',
    targetRole: 'AI Implementation Lead',
    skillsFocus: ['Leadership', 'Data Analysis'],
  };

  it('includes correct phase label', () => {
    const snap = buildDashboardSnapshot(campaign, { missionsCompleted: 0, evidenceCount: 0 });
    expect(snap.phase).toBe('Foundation');
  });

  it('includes all required fields', () => {
    const snap = buildDashboardSnapshot(campaign, { missionsCompleted: 3, evidenceCount: 7 });
    expect(snap.page).toBe('dashboard');
    expect(snap.targetRole).toBe('AI Implementation Lead');
    expect(snap.missionsCompleted).toBe(3);
    expect(snap.evidenceCount).toBe(7);
    expect(snap.skillsFocus).toEqual(['Leadership', 'Data Analysis']);
    expect(snap.phaseProgress).toBe(33);
    expect(snap.daysActive).toBeGreaterThanOrEqual(1);
  });

  it('maps momentum phase to Expansion display label', () => {
    const snap = buildDashboardSnapshot(
      { ...campaign, phase: 'momentum' },
      { missionsCompleted: 5, evidenceCount: 10 },
    );
    expect(snap.phase).toBe('Expansion');
  });
});
```

- [ ] **Step 2: Run test to verify it passes** (this tests the pure function, which uses existing utils)

Run: `cd frontend && npx vitest --run src/__tests__/pages/DashboardSnapshot.test.tsx`

- [ ] **Step 3: Implement Dashboard snapshot emission**

In `frontend/src/pages/Dashboard.tsx`:

**3a. Add import** at the top:

```tsx
import { useMutationBus } from '../hooks/useMutationBus';
import { phaseLabel } from '../utils/campaign';
```

(`phaseLabel` may already be imported — check. `phaseProgress`, `daysActive` are already imported.)

**3b. Inside the `Dashboard` component**, after `const { data, loading, error, fetchDashboard } = useDashboard();`, add:

```tsx
  const { setPageSnapshot } = useMutationBus();
```

**3c. Add a `useEffect`** after the existing `fetchDashboard` effect (around line 343):

```tsx
  useEffect(() => {
    if (!data?.campaign) return;
    const { campaign, stats } = data;
    setPageSnapshot({
      page: 'dashboard',
      phase: phaseLabel(campaign.phase),
      phaseProgress: phaseProgress(campaign.phase),
      targetRole: campaign.targetRole,
      missionsCompleted: stats.missionsCompleted,
      evidenceCount: stats.evidenceCount,
      daysActive: daysActive(campaign.startDate),
      startDate: campaign.startDate,
      skillsFocus: campaign.skillsFocus,
    });
  }, [data, setPageSnapshot]);
```

- [ ] **Step 4: Run full suite**

Run: `cd frontend && npx vitest --run 2>&1 | tail -5`
Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Dashboard.tsx frontend/src/__tests__/pages/DashboardSnapshot.test.tsx
git commit -m "feat: emit page snapshot from Dashboard"
```

---

### Task 4: Missions snapshot with form input

**Files:**
- Modify: `frontend/src/pages/Missions.tsx`
- Test: `frontend/src/__tests__/pages/MissionsSnapshot.test.tsx` (new)

This is the most complex page because CompletionForm holds local state (reflection, artifactUrl, skillTags) that must flow into the snapshot. We add an `onFormChange` callback prop to CompletionForm so Missions can include it in the snapshot.

- [ ] **Step 1: Write failing test**

Create `frontend/src/__tests__/pages/MissionsSnapshot.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest';
import type { Mission } from '../../types';

interface FormInput {
  reflection: string;
  artifactUrl: string;
  skillTags: string[];
}

function buildMissionsSnapshot(
  activeMissions: Mission[],
  primaryMission: Mission | null,
  alternateMissions: Mission[],
  historyMissions: Mission[],
  dailyRemaining: number | null,
  dailyLimit: number | null,
  formInput: FormInput | null,
) {
  return {
    page: 'missions' as const,
    activeMissions: activeMissions.length,
    primaryMission: primaryMission
      ? { title: primaryMission.title, description: primaryMission.description, status: primaryMission.status }
      : null,
    alternateMissions: alternateMissions.map(m => ({ title: m.title, description: m.description })),
    historyCount: historyMissions.length,
    completedCount: historyMissions.filter(m => m.status === 'completed').length,
    skippedCount: historyMissions.filter(m => m.status === 'skipped').length,
    dailyRemaining,
    dailyLimit,
    formInput: formInput && (formInput.reflection || formInput.artifactUrl || formInput.skillTags.length > 0)
      ? formInput
      : null,
  };
}

describe('buildMissionsSnapshot', () => {
  const mission: Mission = {
    userId: 'u1',
    missionId: 'm1',
    campaignId: 'c1',
    title: 'Lead a Team',
    description: 'Organize and lead...',
    status: 'pending',
  };

  it('includes primary mission details', () => {
    const snap = buildMissionsSnapshot([mission], mission, [], [], 5, 6, null);
    expect(snap.primaryMission).toEqual({
      title: 'Lead a Team',
      description: 'Organize and lead...',
      status: 'pending',
    });
  });

  it('includes form input when user has typed', () => {
    const form = { reflection: 'I did the thing', artifactUrl: '', skillTags: ['Leadership'] };
    const snap = buildMissionsSnapshot([mission], mission, [], [], 5, 6, form);
    expect(snap.formInput).toEqual(form);
  });

  it('excludes form input when empty', () => {
    const form = { reflection: '', artifactUrl: '', skillTags: [] };
    const snap = buildMissionsSnapshot([mission], mission, [], [], 5, 6, form);
    expect(snap.formInput).toBeNull();
  });

  it('counts completed and skipped in history', () => {
    const history: Mission[] = [
      { ...mission, missionId: 'm2', status: 'completed', completedDate: '2026-04-06' },
      { ...mission, missionId: 'm3', status: 'skipped', completedDate: '2026-04-05' },
      { ...mission, missionId: 'm4', status: 'completed', completedDate: '2026-04-04' },
    ];
    const snap = buildMissionsSnapshot([], null, [], history, 5, 6, null);
    expect(snap.completedCount).toBe(2);
    expect(snap.skippedCount).toBe(1);
    expect(snap.historyCount).toBe(3);
  });
});
```

- [ ] **Step 2: Run test**

Run: `cd frontend && npx vitest --run src/__tests__/pages/MissionsSnapshot.test.tsx`

- [ ] **Step 3: Implement Missions snapshot**

In `frontend/src/pages/Missions.tsx`:

**3a. Add import:**

```tsx
import { useMutationBus } from '../hooks/useMutationBus';
```

**3b. Add hook** inside `Missions()` component after existing hooks:

```tsx
  const { setPageSnapshot } = useMutationBus();
```

**3c. Add form input state tracking.** After the existing `const [generating, ...]` state declarations (around line 639), add:

```tsx
  const [formInput, setFormInput] = useState<{
    reflection: string;
    artifactUrl: string;
    skillTags: string[];
  } | null>(null);
```

**3d. Add `onFormChange` prop to CompletionForm.** In the `CompletionForm` function component (around line 220), add the prop:

```tsx
function CompletionForm({
  missionId,
  onComplete,
  onSkip,
  completing,
  completionError,
  onFormChange,
}: {
  missionId: string;
  onComplete: (missionId: string, data: CompleteData) => void;
  onSkip: (missionId: string) => void;
  completing: boolean;
  completionError: string | null;
  onFormChange?: (data: { reflection: string; artifactUrl: string; skillTags: string[] }) => void;
}) {
```

**3e. Add a useEffect inside CompletionForm** to notify parent on input changes (after the existing state declarations, around line 240):

```tsx
  useEffect(() => {
    onFormChange?.({ reflection, artifactUrl, skillTags });
  }, [reflection, artifactUrl, skillTags, onFormChange]);
```

**3f. Pass `onFormChange` from PrimaryMissionCard** (around line 436):

```tsx
      <CompletionForm
        key={mission.missionId}
        missionId={mission.missionId}
        onComplete={onComplete}
        onSkip={onSkip}
        completing={completing}
        completionError={completionError}
        onFormChange={onFormChange}
      />
```

And add the prop to `PrimaryMissionCard`:

```tsx
function PrimaryMissionCard({
  mission,
  onComplete,
  onSkip,
  completing,
  completionError,
  onFormChange,
}: {
  mission: Mission;
  onComplete: (missionId: string, data: CompleteData) => void;
  onSkip: (missionId: string) => void;
  completing: boolean;
  completionError: string | null;
  onFormChange?: (data: { reflection: string; artifactUrl: string; skillTags: string[] }) => void;
}) {
```

**3g. Pass `onFormChange` when rendering PrimaryMissionCard** (around line 840):

```tsx
        <PrimaryMissionCard
          mission={primaryMission}
          onComplete={handleComplete}
          onSkip={handleSkip}
          completing={completing}
          completionError={completionError}
          onFormChange={setFormInput}
        />
```

**3h. Add snapshot emission useEffect** in `Missions()`:

```tsx
  useEffect(() => {
    if (loading && missions.length === 0) return;
    const hasInput = formInput && (formInput.reflection || formInput.artifactUrl || formInput.skillTags.length > 0);
    setPageSnapshot({
      page: 'missions',
      activeMissions: activeMissions.length,
      primaryMission: primaryMission
        ? { title: primaryMission.title, description: primaryMission.description, status: primaryMission.status }
        : null,
      alternateMissions: alternateMissions.map(m => ({ title: m.title, description: m.description })),
      historyCount: historyMissions.length,
      completedCount: historyMissions.filter(m => m.status === 'completed').length,
      skippedCount: historyMissions.filter(m => m.status === 'skipped').length,
      dailyRemaining,
      dailyLimit,
      formInput: hasInput ? formInput : null,
    });
  }, [activeMissions, primaryMission, alternateMissions, historyMissions, dailyRemaining, dailyLimit, formInput, loading, missions.length, setPageSnapshot]);
```

- [ ] **Step 4: Run full suite**

Run: `cd frontend && npx vitest --run 2>&1 | tail -5`
Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Missions.tsx frontend/src/__tests__/pages/MissionsSnapshot.test.tsx
git commit -m "feat: emit page snapshot from Missions with form input"
```

---

### Task 5: Evidence + Profile snapshots

**Files:**
- Modify: `frontend/src/pages/Evidence.tsx`
- Modify: `frontend/src/pages/Profile.tsx`

- [ ] **Step 1: Implement Evidence snapshot**

In `frontend/src/pages/Evidence.tsx`:

**1a. Add import:**

```tsx
import { useMutationBus } from '../hooks/useMutationBus';
```

**1b. Add hook** inside `Evidence()` after existing hooks:

```tsx
  const { setPageSnapshot } = useMutationBus();
```

**1c. Add useEffect** after the `skillStats` memo:

```tsx
  useEffect(() => {
    if (loading && evidence.length === 0) return;
    setPageSnapshot({
      page: 'evidence',
      totalItems: evidence.length,
      skillsCovered: skillStats.length,
      topSkills: skillStats.slice(0, 8).map(s => ({ skill: s.skill, count: s.count })),
      recentItems: [...evidence]
        .sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime())
        .slice(0, 5)
        .map(e => ({ skillTag: e.skillTag, reflection: e.reflection, createdAt: e.createdAt })),
    });
  }, [evidence, skillStats, loading, setPageSnapshot]);
```

- [ ] **Step 2: Implement Profile snapshot**

In `frontend/src/pages/Profile.tsx`:

**2a. Add import:**

```tsx
import { useMutationBus } from '../hooks/useMutationBus';
import { phaseLabel } from '../utils/campaign';
```

(`phaseLabel` may not be imported yet — `phaseIndex`, `phaseProgress`, `daysActive`, `formatDate` are.)

**2b. Add hook** inside `Profile()` after existing hooks:

```tsx
  const { setPageSnapshot } = useMutationBus();
```

**2c. Add useEffect** after the `fetchDashboard` effect:

```tsx
  useEffect(() => {
    if (!data?.campaign) return;
    const { campaign, stats } = data;
    setPageSnapshot({
      page: 'profile',
      username: user?.username ?? '',
      targetRole: campaign.targetRole,
      phase: phaseLabel(campaign.phase),
      daysActive: daysActive(campaign.startDate),
      missionsCompleted: stats.missionsCompleted,
      evidenceCount: stats.evidenceCount,
      skillsFocus: campaign.skillsFocus,
    });
  }, [data, user, setPageSnapshot]);
```

- [ ] **Step 3: Run full suite**

Run: `cd frontend && npx vitest --run 2>&1 | tail -5`
Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Evidence.tsx frontend/src/pages/Profile.tsx
git commit -m "feat: emit page snapshots from Evidence and Profile"
```

---

### Task 6: Resume + Impact Scorecard snapshots

**Files:**
- Modify: `frontend/src/pages/ResumePage.tsx`
- Modify: `frontend/src/pages/ImpactScorecardPage.tsx`

- [ ] **Step 1: Implement Resume snapshot**

In `frontend/src/pages/ResumePage.tsx`:

**1a. Add import:**

```tsx
import { useMutationBus } from '../hooks/useMutationBus';
```

**1b. Add hook** inside `ResumePage()`:

```tsx
  const { setPageSnapshot } = useMutationBus();
```

**1c. Add useEffect:**

```tsx
  useEffect(() => {
    if (loading && !resume) return;
    if (!resume) {
      setPageSnapshot({ page: 'resume', hasResume: false });
      return;
    }
    const fm = resume.frontmatter;
    setPageSnapshot({
      page: 'resume',
      hasResume: true,
      version: resume.version,
      generatedAt: resume.generatedAt,
      missionsCompleted: fm.missions_completed,
      evidenceItems: fm.evidence_items,
      marketAlignment: fm.market_alignment_score,
      targetRole: fm.target_role,
      phase: fm.campaign_phase,
      skills: fm.skills.map(s => ({
        name: s.skill_name,
        proficiency: s.proficiency_indicator,
        evidenceCount: s.evidence_count,
        strongestEvidence: s.strongest_evidence_summary,
      })),
      topAccomplishments: fm.top_accomplishments,
    });
  }, [resume, loading, setPageSnapshot]);
```

- [ ] **Step 2: Implement Scorecard snapshot**

In `frontend/src/pages/ImpactScorecardPage.tsx`:

**2a. Add import:**

```tsx
import { useMutationBus } from '../hooks/useMutationBus';
```

**2b. Add hook** inside `ImpactScorecardPage()`:

```tsx
  const { setPageSnapshot } = useMutationBus();
```

**2c. Add useEffect:**

```tsx
  useEffect(() => {
    if (loading || !data) return;
    if (data.missionsCompleted < 3) {
      setPageSnapshot({
        page: 'scorecard',
        unlocked: false,
        missionsCompleted: data.missionsCompleted,
        missionsNeeded: 3,
      });
      return;
    }
    setPageSnapshot({
      page: 'scorecard',
      unlocked: true,
      cri: data.cri,
      missionsCompleted: data.missionsCompleted,
      evidenceCount: data.evidenceCount,
      targetRole: data.targetRole,
      phase: data.dimensionDetail.phaseProgression.phase,
      computedAt: data.computedAt,
      dimensions: {
        velocity: data.missionVelocityScore,
        evidence: data.evidenceDensityScore,
        marketFit: data.marketAlignmentScore,
        phase: data.phaseProgressionScore,
        difficulty: data.adaptiveDifficultyScore,
      },
    });
  }, [data, loading, setPageSnapshot]);
```

- [ ] **Step 3: Run full suite**

Run: `cd frontend && npx vitest --run 2>&1 | tail -5`
Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/ResumePage.tsx frontend/src/pages/ImpactScorecardPage.tsx
git commit -m "feat: emit page snapshots from Resume and Impact Scorecard"
```

---

### Task 7: Analytics + Voice Practice + O*NET snapshots

**Files:**
- Modify: `frontend/src/pages/AnalyticsPage.tsx`
- Modify: `frontend/src/pages/VoicePracticePage.tsx`
- Modify: `frontend/src/pages/OnetPage.tsx`

- [ ] **Step 1: Implement Analytics snapshot**

In `frontend/src/pages/AnalyticsPage.tsx`, add the import, hook, and useEffect following the same pattern. The snapshot needs the analytics data — read from `useAnalytics()`. Add after the data loads:

```tsx
import { useMutationBus } from '../hooks/useMutationBus';
```

```tsx
  const { setPageSnapshot } = useMutationBus();
```

```tsx
  useEffect(() => {
    if (loading || !data) return;
    setPageSnapshot({
      page: 'analytics',
      currentStreak: data.currentStreak,
      longestStreak: data.longestStreak,
      missionsCompleted: data.missionsCompleted,
      missionsSkipped: data.missionsSkipped,
      avgPerWeek: data.avgPerWeek,
      topSkills: data.skillBreakdown.slice(0, 5).map(s => ({ skill: s.skill, count: s.count })),
      activeDaysThisWeek: data.activeDaysThisWeek,
    });
  }, [data, loading, setPageSnapshot]);
```

Note: Check the actual field names from `useAnalytics()` data object. The names above match the spec — adjust if the hook returns different property names.

- [ ] **Step 2: Implement Voice Practice snapshot**

In `frontend/src/pages/VoicePracticePage.tsx`, add:

```tsx
import { useMutationBus } from '../hooks/useMutationBus';
```

```tsx
  const { setPageSnapshot } = useMutationBus();
```

```tsx
  useEffect(() => {
    setPageSnapshot({
      page: 'voice-practice',
      status,
      totalSessions: sessions.length,
      recentSessions: sessions.slice(0, 3).map(s => ({
        type: s.sessionType,
        date: s.createdAt,
        overallScore: s.overallScore ?? null,
      })),
    });
  }, [status, sessions, setPageSnapshot]);
```

Note: Check the actual field names on session objects from `useVoiceSessions()`.

- [ ] **Step 3: Implement O*NET snapshot**

In `frontend/src/pages/OnetPage.tsx`, add:

```tsx
import { useMutationBus } from '../hooks/useMutationBus';
```

```tsx
  const { setPageSnapshot } = useMutationBus();
```

Two snapshot emissions — one for search results, one for career detail:

```tsx
  // Snapshot: search results view
  useEffect(() => {
    if (careerDetail) return; // detail view handles its own snapshot
    setPageSnapshot({
      page: 'careers',
      searchKeyword: keyword,
      resultCount: results.length,
      results: results.map(r => ({
        title: r.title,
        code: r.code,
        brightOutlook: r.tags?.bright_outlook ?? false,
      })),
    });
  }, [results, keyword, careerDetail, setPageSnapshot]);

  // Snapshot: career detail view
  useEffect(() => {
    if (!careerDetail) return;
    const c = careerDetail;
    setPageSnapshot({
      page: 'careers-detail',
      title: c.title,
      code: c.code,
      tags: {
        brightOutlook: c.tags?.bright_outlook ?? false,
        green: c.tags?.green ?? false,
        apprenticeship: c.tags?.apprenticeship ?? false,
      },
      whatTheyDo: c.what_they_do ?? '',
      topTasks: (c.on_the_job?.task ?? []).slice(0, 5).map(t => t.statement),
      education: c.education ? {
        jobZone: c.education.job_zone?.code ?? 0,
        title: c.education.job_zone?.title ?? '',
        usuallyNeeded: c.education.education_usually_needed ?? [],
      } : null,
      outlook: c.job_outlook?.outlook ? {
        category: c.job_outlook.outlook.category ?? '',
        description: c.job_outlook.outlook.description ?? '',
      } : null,
      salary: c.job_outlook?.salary ? {
        median: c.job_outlook.salary.annual_median ?? 0,
        low: c.job_outlook.salary.annual_10th_percentile ?? 0,
        high: c.job_outlook.salary.annual_90th_percentile ?? 0,
      } : null,
      topKnowledge: (c.knowledge ?? []).flatMap(g => g.items ?? []).slice(0, 5).map(i => ({ name: i.name, score: i.score })),
      topSkills: (c.skills ?? []).flatMap(g => g.items ?? []).slice(0, 5).map(i => ({ name: i.name, score: i.score })),
      topAbilities: (c.abilities ?? []).flatMap(g => g.items ?? []).slice(0, 5).map(i => ({ name: i.name, score: i.score })),
      personality: {
        topInterest: c.personality?.top_interest?.name ?? '',
        workStyles: (c.personality?.work_styles ?? []).map(ws => ws.name),
      },
      hotTechnologies: (c.technology ?? []).flatMap(t => (t.example ?? []).filter(e => e.hot_technology).map(e => e.title)),
      relatedCareers: (c.explore_more?.careers ?? []).map(rc => ({ title: rc.title, code: rc.code })),
    });
  }, [careerDetail, setPageSnapshot]);
```

Note: Check the actual `OnetCareerReport` type for exact field paths. The paths above are derived from `OnetCareerDetail.tsx` rendering logic — adjust if types differ.

- [ ] **Step 4: Run full suite**

Run: `cd frontend && npx vitest --run 2>&1 | tail -5`
Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/AnalyticsPage.tsx frontend/src/pages/VoicePracticePage.tsx frontend/src/pages/OnetPage.tsx
git commit -m "feat: emit page snapshots from Analytics, Voice Practice, and O*NET"
```

---

### Task 8: System prompt changes

**Files:**
- Modify: `backend/agents/coaching/prompts.py`

- [ ] **Step 1: Update page_data trust instructions**

In `backend/agents/coaching/prompts.py`, replace the current Page Context Awareness section (around line 146-161) with:

```python
## Page Context Awareness

When you receive a [page_context: X] tag, the user is currently viewing that page.

When a message includes [page_data: {...}], this JSON contains the exact data currently displayed on the user's screen. Treat it as authoritative:
- State facts (phase, counts, scores, mission titles, reflections) directly from page_data without calling tools first.
- The "formInput" field contains what the user has typed but not yet submitted — you can reference this to help them refine their reflection or suggest skill tags.
- Only call tools when you need to take an action (complete mission, log evidence, generate mission) or need deeper data not in the snapshot (behavioral patterns, market insights, memory recall).
- Never contradict page_data — if it says phase is "Foundation", the phase is Foundation.

When you receive [proactive_check] with [page_data]:
1. Read page_data for the current state (phase, counts, mission status, etc.).
2. Only call tools if you need deeper context not in the snapshot (patterns, memory, market data).
3. Offer one actionable suggestion in 1-2 sentences based on the data.
4. If nothing useful to suggest, respond with exactly "[no_suggestion]".
Never state a phase, completion count, or activity level you did not read from page_data or a tool response. Do not repeat a suggestion you've already made in this session.

Page context guide:
- dashboard: campaign overview — phase, missions completed, evidence count, days active, target role, skills
- missions: mission list — active/primary/alternate missions, history counts, daily limits, user's form input (reflection, artifact, skill tags)
- evidence: evidence vault — total items, skills covered, top skills with counts, recent items with reflections
- scorecard: Impact Scorecard — CRI score, 5 dimension scores, phase, target role
- analytics: activity analytics — streaks, velocity, skill breakdown, weekly activity
- resume: generated resume — version, frontmatter stats, skills with proficiency, accomplishments
- voice-practice: voice session history — total sessions, recent scores
- careers: O*NET career search results — keyword, result list with outlook tags
- careers-detail: full O*NET career report — tasks, education, salary, knowledge/skills/abilities scores, personality, technology, related careers
- profile: user profile — identity, campaign journey, skill development chart
```

- [ ] **Step 2: Run backend coaching tests**

Run: `.venv/bin/pytest tests/unit/agents/ tests/unit/handlers/coaching/ -x -q`
Expected: All pass.

- [ ] **Step 3: Commit**

```bash
git add backend/agents/coaching/prompts.py
git commit -m "feat: update system prompt to use page_data snapshots as authoritative context"
```

---

### Task 9: Full verification and push

- [ ] **Step 1: Run full frontend tests**

Run: `cd frontend && npx vitest --run 2>&1 | tail -5`
Expected: All tests pass.

- [ ] **Step 2: Run full backend tests**

Run: `.venv/bin/pytest tests/ -x -q 2>&1 | tail -5`
Expected: All tests pass.

- [ ] **Step 3: Push branch**

```bash
git push -u origin feat/page-context-snapshots
```
