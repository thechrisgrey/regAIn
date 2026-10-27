# Market Alignment on Analytics Page — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface alignment score and skill-gap-vs-demand breakdown on the Analytics page by extending the existing `/analytics` endpoint and adding a new card.

**Architecture:** Add a 4th parallel query to `AnalyticsService.get_analytics()` that fetches the user's `targetRole` from UserProfiles and calls `calculate_alignment()`. Frontend renders a new `MarketAlignmentCard` in the existing grid. No new endpoints, hooks, or service calls.

**Tech Stack:** Python 3.12 (Lambda), DynamoDB, React 19, Tailwind v4, Vitest

---

### Task 1: CDK — Grant Dashboard Lambda read access to MarketData

The Dashboard Lambda already has the `MARKET_DATA_TABLE` env var (`api_stack.py:85`) but lacks `grant_read_data` for the MarketData table. The IAM least-privilege test also needs updating.

**Files:**
- Modify: `infra/stacks/api_stack.py:198-202`
- Modify: `tests/unit/stacks/test_iam_least_privilege.py:32`

- [ ] **Step 1: Add MarketData grant in api_stack.py**

In `infra/stacks/api_stack.py`, find the Dashboard grants block (around line 198–202):

```python
        # Dashboard: read UserProfiles, Campaigns, MissionHistory, EvidenceVault
        self.tables["UserProfiles"].grant_read_data(lambdas["Dashboard"])
        self.tables["Campaigns"].grant_read_data(lambdas["Dashboard"])
        self.tables["MissionHistory"].grant_read_data(lambdas["Dashboard"])
        self.tables["EvidenceVault"].grant_read_data(lambdas["Dashboard"])
```

Add after the last line:

```python
        self.tables["MarketData"].grant_read_data(lambdas["Dashboard"])
```

Update the comment to:

```python
        # Dashboard: read UserProfiles, Campaigns, MissionHistory, EvidenceVault, MarketData
```

- [ ] **Step 2: Update IAM test allowed tables**

In `tests/unit/stacks/test_iam_least_privilege.py`, find line 32:

```python
    "Dashboard": {"UserProfiles", "Campaigns", "MissionHistory", "EvidenceVault"},
```

Change to:

```python
    "Dashboard": {"UserProfiles", "Campaigns", "MissionHistory", "EvidenceVault", "MarketData"},
```

- [ ] **Step 3: Run IAM tests**

Run: `.venv/bin/pytest tests/unit/stacks/test_iam_least_privilege.py -x -q -v`
Expected: All tests PASS (including the Dashboard Lambda now expecting MarketData access)

- [ ] **Step 4: Commit**

```bash
git add infra/stacks/api_stack.py tests/unit/stacks/test_iam_least_privilege.py
git commit -m "feat: grant Dashboard Lambda read access to MarketData table"
```

---

### Task 2: Backend — Add market alignment to AnalyticsService

Add a 4th parallel task to `get_analytics()` that fetches the user's profile, extracts `targetRole`, and calls `calculate_alignment()`.

**Files:**
- Modify: `backend/handlers/dashboard/analytics_service.py`

- [ ] **Step 1: Add alignment import and helper method**

At the top of `analytics_service.py`, add after the existing imports (after line 6):

```python
from backend.handlers.market_intel.alignment import calculate_alignment
```

- [ ] **Step 2: Add _compute_market_alignment method to AnalyticsService**

Add this method to the `AnalyticsService` class, after `_compute_unevidenced_skills` (after line 248):

```python
    def _compute_market_alignment(self, user_id: str) -> dict | None:
        """Compute market alignment for the user's target role.

        Fetches the user's targetRole from UserProfiles, then calls
        calculate_alignment() to produce alignment %, top gaps, and
        top strengths.

        Returns None if targetRole is not set or alignment fails.
        """
        try:
            profile = self.db.get_item("user_profiles", {"userId": user_id})
        except Exception:
            logger.warning("Failed to fetch profile for alignment", exc_info=True)
            return None

        if not profile:
            return None

        target_role = profile.get("targetRole")
        if not target_role or not isinstance(target_role, str) or not target_role.strip():
            return None

        target_role = target_role.strip()

        try:
            result = calculate_alignment(user_id, target_role)
        except Exception:
            logger.warning("Alignment calculation failed for %s", user_id, exc_info=True)
            return None

        return {
            "alignmentPct": round(result.alignment_pct, 1),
            "targetRole": target_role,
            "topGaps": [
                {"skill": g["skill"], "gap": round(g["gap"], 2), "demand": round(g["market_weight"] * 100)}
                for g in result.top_gaps
            ],
            "topStrengths": [
                {"skill": s["skill"], "userScore": round(s["user_score"], 2)}
                for s in result.top_strengths
            ],
            "calculatedAt": result.calculated_at,
        }
```

- [ ] **Step 3: Wire the 4th parallel task into get_analytics()**

Replace the `get_analytics` method body. Change `max_workers=3` to `max_workers=4` and add the alignment future:

```python
    def get_analytics(self, user_id: str) -> Dict[str, Any]:
        """Aggregate analytics data for a user.

        Runs 4 parallel DynamoDB queries (missions, evidence, campaigns,
        market alignment) and computes derived analytics from the results.
        """
        key_condition = Key("userId").eq(user_id)

        with ThreadPoolExecutor(max_workers=4) as executor:
            missions_future = executor.submit(
                self.db.query_all, "mission_history", key_condition
            )
            evidence_future = executor.submit(
                self.db.query_all, "evidence_vault", key_condition
            )
            campaigns_future = executor.submit(
                self.db.query_all, "campaigns", key_condition
            )
            alignment_future = executor.submit(
                self._compute_market_alignment, user_id
            )

            try:
                missions = missions_future.result(timeout=_QUERY_TIMEOUT_SECONDS)
                evidence = evidence_future.result(timeout=_QUERY_TIMEOUT_SECONDS)
                campaigns = campaigns_future.result(timeout=_QUERY_TIMEOUT_SECONDS)
            except FuturesTimeoutError:
                logger.error("Analytics query timed out after %ds", _QUERY_TIMEOUT_SECONDS)
                raise

            # Alignment failure is non-fatal — returns None on error
            try:
                market_alignment = alignment_future.result(timeout=_QUERY_TIMEOUT_SECONDS)
            except Exception:
                logger.warning("Market alignment timed out or failed", exc_info=True)
                market_alignment = None

        active_campaign = next(
            (c for c in campaigns if c.get("status") == "active"), None
        )
        completed_missions = [m for m in missions if m.get("status") == "completed"]

        return {
            "skillBreakdown": self._compute_skill_breakdown(evidence),
            "activityHeatmap": self._compute_activity_heatmap(completed_missions, evidence),
            "velocityTrend": self._compute_velocity_trend(completed_missions),
            "campaignEta": self._compute_campaign_eta(completed_missions, active_campaign),
            "skillSuggestions": self._compute_unevidenced_skills(evidence, active_campaign),
            "marketAlignment": market_alignment,
        }
```

- [ ] **Step 4: Run backend tests**

Run: `.venv/bin/pytest tests/unit/handlers/ -x -q -k "dashboard"` 
Expected: Existing dashboard tests still PASS

- [ ] **Step 5: Commit**

```bash
git add backend/handlers/dashboard/analytics_service.py
git commit -m "feat: add market alignment to analytics endpoint"
```

---

### Task 3: Backend test — AnalyticsService market alignment

Create a test file for the new alignment integration in AnalyticsService.

**Files:**
- Create: `tests/unit/handlers/dashboard/test_analytics_alignment.py`

- [ ] **Step 1: Write tests**

Create `tests/unit/handlers/dashboard/test_analytics_alignment.py`:

```python
"""Tests for market alignment integration in AnalyticsService."""

from unittest.mock import MagicMock, patch

import pytest

from backend.handlers.dashboard.analytics_service import AnalyticsService


@pytest.fixture()
def mock_db():
    """Return a mock DynamoDB client."""
    db = MagicMock()
    db.query_all.return_value = []
    db.get_item.return_value = None
    return db


class TestMarketAlignmentInAnalytics:
    """Tests for marketAlignment field in get_analytics response."""

    def test_returns_null_when_no_target_role(self, mock_db):
        """marketAlignment is None when user has no targetRole."""
        mock_db.get_item.return_value = {"userId": "u1", "skills": []}
        service = AnalyticsService(db_client=mock_db)

        with patch(
            "backend.handlers.dashboard.analytics_service.calculate_alignment"
        ) as mock_align:
            result = service.get_analytics("u1")

        assert result["marketAlignment"] is None
        mock_align.assert_not_called()

    def test_returns_null_when_no_profile(self, mock_db):
        """marketAlignment is None when profile doesn't exist."""
        mock_db.get_item.return_value = None
        service = AnalyticsService(db_client=mock_db)

        result = service.get_analytics("u1")

        assert result["marketAlignment"] is None

    def test_returns_alignment_when_target_role_set(self, mock_db):
        """marketAlignment populated when targetRole exists."""
        mock_db.get_item.return_value = {
            "userId": "u1",
            "targetRole": "ai_qa_engineer",
        }
        service = AnalyticsService(db_client=mock_db)

        mock_result = MagicMock()
        mock_result.alignment_pct = 62.5
        mock_result.top_gaps = [
            {"skill": "Python Testing", "gap": 0.78, "market_weight": 0.78, "user_score": 0.0},
        ]
        mock_result.top_strengths = [
            {"skill": "Manual QA", "user_score": 1.0, "market_weight": 0.65},
        ]
        mock_result.calculated_at = "2026-04-18T00:00:00+00:00"

        with patch(
            "backend.handlers.dashboard.analytics_service.calculate_alignment",
            return_value=mock_result,
        ) as mock_align:
            result = service.get_analytics("u1")

        mock_align.assert_called_once_with("u1", "ai_qa_engineer")
        ma = result["marketAlignment"]
        assert ma is not None
        assert ma["alignmentPct"] == 62.5
        assert ma["targetRole"] == "ai_qa_engineer"
        assert len(ma["topGaps"]) == 1
        assert ma["topGaps"][0]["skill"] == "Python Testing"
        assert ma["topGaps"][0]["demand"] == 78
        assert len(ma["topStrengths"]) == 1
        assert ma["topStrengths"][0]["skill"] == "Manual QA"
        assert ma["calculatedAt"] == "2026-04-18T00:00:00+00:00"

    def test_alignment_failure_returns_null(self, mock_db):
        """marketAlignment is None when calculate_alignment raises."""
        mock_db.get_item.return_value = {
            "userId": "u1",
            "targetRole": "ai_qa_engineer",
        }
        service = AnalyticsService(db_client=mock_db)

        with patch(
            "backend.handlers.dashboard.analytics_service.calculate_alignment",
            side_effect=RuntimeError("boom"),
        ):
            result = service.get_analytics("u1")

        assert result["marketAlignment"] is None

    def test_other_fields_unaffected_by_alignment(self, mock_db):
        """Existing analytics fields are present regardless of alignment."""
        mock_db.get_item.return_value = None
        service = AnalyticsService(db_client=mock_db)

        result = service.get_analytics("u1")

        assert "skillBreakdown" in result
        assert "activityHeatmap" in result
        assert "velocityTrend" in result
        assert "campaignEta" in result
        assert "skillSuggestions" in result
        assert "marketAlignment" in result

    def test_empty_target_role_string_returns_null(self, mock_db):
        """marketAlignment is None when targetRole is empty string."""
        mock_db.get_item.return_value = {"userId": "u1", "targetRole": "  "}
        service = AnalyticsService(db_client=mock_db)

        result = service.get_analytics("u1")

        assert result["marketAlignment"] is None
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/handlers/dashboard/test_analytics_alignment.py -x -v`
Expected: All 6 tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/unit/handlers/dashboard/test_analytics_alignment.py
git commit -m "test: add AnalyticsService market alignment tests"
```

---

### Task 4: Frontend types — Add MarketAlignment to AnalyticsResponse

**Files:**
- Modify: `frontend/src/types/index.ts:334-340`

- [ ] **Step 1: Add MarketAlignment types**

In `frontend/src/types/index.ts`, find the Analytics types section (line 309). Add the new interfaces before `AnalyticsResponse` (before line 334):

```typescript
export interface MarketAlignmentGap {
  skill: string;
  gap: number;
  demand: number;
}

export interface MarketAlignmentStrength {
  skill: string;
  userScore: number;
}

export interface MarketAlignment {
  alignmentPct: number;
  targetRole: string;
  topGaps: MarketAlignmentGap[];
  topStrengths: MarketAlignmentStrength[];
  calculatedAt: string;
}
```

- [ ] **Step 2: Add marketAlignment field to AnalyticsResponse**

Find the `AnalyticsResponse` interface (line 334):

```typescript
export interface AnalyticsResponse {
  skillBreakdown: SkillBreakdownItem[];
  activityHeatmap: ActivityHeatmapDay[];
  velocityTrend: { weeks: VelocityWeek[] };
  campaignEta: CampaignEta | null;
  skillSuggestions: string[];
}
```

Change to:

```typescript
export interface AnalyticsResponse {
  skillBreakdown: SkillBreakdownItem[];
  activityHeatmap: ActivityHeatmapDay[];
  velocityTrend: { weeks: VelocityWeek[] };
  campaignEta: CampaignEta | null;
  skillSuggestions: string[];
  marketAlignment: MarketAlignment | null;
}
```

- [ ] **Step 3: Run type check**

Run: `cd frontend && npx tsc --noEmit`
Expected: PASS (no type errors — `useAnalytics` returns `AnalyticsResponse` and the new field is nullable, so existing consumers are unaffected)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/index.ts
git commit -m "feat: add MarketAlignment types to AnalyticsResponse"
```

---

### Task 5: Frontend — MarketAlignmentCard on AnalyticsPage

Add a new card component to the Analytics page that renders the alignment score, top gaps, and top strengths.

**Files:**
- Modify: `frontend/src/pages/AnalyticsPage.tsx`

- [ ] **Step 1: Add MarketAlignment import**

In `AnalyticsPage.tsx`, add `MarketAlignment` to the type imports (line 4):

```typescript
import type {
  SkillBreakdownItem,
  ActivityHeatmapDay,
  VelocityWeek,
  CampaignEta,
  MarketAlignment,
} from '../types';
```

- [ ] **Step 2: Add the MarketAlignmentCard component**

Add this component after the `SkillBarChart` component (after line 412, before the `SkillGapsList` component):

```typescript
// ---------------------------------------------------------------------------
// Market Alignment
// ---------------------------------------------------------------------------

function MarketAlignmentCard({
  alignment,
}: {
  alignment: MarketAlignment | null;
}) {
  if (!alignment) {
    return (
      <Card className="p-6 animate-fade-in-up" style={{ animationDelay: '180ms' }}>
        <SectionLabel>Market Alignment</SectionLabel>
        <p className="mt-5 text-sm leading-relaxed text-neutral-500">
          Set a target role in your{' '}
          <a href="/profile" className="text-primary-600 underline underline-offset-2">
            profile
          </a>{' '}
          to see market alignment.
        </p>
      </Card>
    );
  }

  const pct = Math.round(alignment.alignmentPct);

  return (
    <Card className="p-6 animate-fade-in-up" style={{ animationDelay: '180ms' }}>
      <div className="flex items-start justify-between">
        <div>
          <SectionLabel>Market Alignment</SectionLabel>
          <p className="mt-0.5 text-xs text-neutral-400">{alignment.targetRole}</p>
        </div>
      </div>

      <div className="mt-5 rounded-[var(--radius-button)] bg-surface-2 px-4 py-3">
        <p className="stat-value text-3xl font-medium font-mono tabular-nums">
          {pct}%
        </p>
      </div>
      <ProgressBar value={pct} className="mt-2" />

      {alignment.topGaps.length > 0 && (
        <div className="mt-5">
          <p className="text-[11px] font-medium uppercase tracking-widest text-neutral-500">
            Top Gaps
          </p>
          <div className="mt-2 space-y-2">
            {alignment.topGaps.map((gap) => (
              <div key={gap.skill}>
                <div className="flex items-center justify-between text-xs">
                  <span className="font-medium text-neutral-700 truncate max-w-[180px]">
                    {gap.skill}
                  </span>
                  <span className="font-mono tabular-nums text-neutral-400 ml-2 shrink-0">
                    {gap.demand}% of postings
                  </span>
                </div>
                <div className="mt-1 h-1.5 w-full overflow-hidden rounded-[var(--radius-badge)] bg-neutral-100">
                  <div
                    className="h-full rounded-[var(--radius-badge)] bg-accent-400 transition-all duration-700 ease-out"
                    style={{ width: `${gap.demand}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {alignment.topStrengths.length > 0 && (
        <div className="mt-5">
          <p className="text-[11px] font-medium uppercase tracking-widest text-neutral-500">
            Strengths
          </p>
          <div className="mt-2 space-y-2">
            {alignment.topStrengths.map((s) => (
              <div key={s.skill}>
                <div className="flex items-center justify-between text-xs">
                  <span className="font-medium text-neutral-700 truncate max-w-[180px]">
                    {s.skill}
                  </span>
                  <span className="font-mono tabular-nums text-neutral-400 ml-2 shrink-0">
                    {Math.round(s.userScore * 100)}%
                  </span>
                </div>
                <div className="mt-1 h-1.5 w-full overflow-hidden rounded-[var(--radius-badge)] bg-neutral-100">
                  <div
                    className="h-full rounded-[var(--radius-badge)] bg-success-400 transition-all duration-700 ease-out"
                    style={{ width: `${Math.round(s.userScore * 100)}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <p className="mt-4 text-[10px] text-neutral-400">
        Calculated {new Date(alignment.calculatedAt).toLocaleDateString()}
      </p>
    </Card>
  );
}
```

- [ ] **Step 3: Update the SkillBarChart animation delay**

The existing `SkillBarChart` has `animationDelay: '180ms'` (line 378). Since the new Market Alignment card uses `180ms`, bump `SkillBarChart` to `240ms`:

```typescript
    <Card className="p-6 animate-fade-in-up" style={{ animationDelay: '240ms' }}>
```

And bump `SkillGapsList` from `240ms` to `300ms` (line 421):

```typescript
    <Card className="p-6 animate-fade-in-up" style={{ animationDelay: '300ms' }}>
```

(Both occurrences in each component — including the empty-state card and the populated card use the same delay.)

- [ ] **Step 4: Wire MarketAlignmentCard into the page layout**

In the `AnalyticsPage` component's return JSX, add the Market Alignment card in a new row between the Activity Heatmap and the Skill Breakdown + Gaps row. Find (around line 547):

```tsx
      {/* Row 2: Activity Heatmap (full width) */}
      <ActivityHeatmap days={data.activityHeatmap} />

      {/* Row 3: Skill Breakdown + Gaps */}
      <div className="grid gap-6 md:grid-cols-2">
        <SkillBarChart skills={data.skillBreakdown} />
        <SkillGapsList gaps={data.skillSuggestions} />
      </div>
```

Replace with:

```tsx
      {/* Row 2: Activity Heatmap (full width) */}
      <ActivityHeatmap days={data.activityHeatmap} />

      {/* Row 3: Market Alignment + Skill Breakdown */}
      <div className="grid gap-6 md:grid-cols-2">
        <MarketAlignmentCard alignment={data.marketAlignment} />
        <SkillBarChart skills={data.skillBreakdown} />
      </div>

      {/* Row 4: Skill Gaps (full width) */}
      <SkillGapsList gaps={data.skillSuggestions} />
```

- [ ] **Step 5: Run type check and lint**

Run: `cd frontend && npx tsc --noEmit && npm run lint`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/AnalyticsPage.tsx
git commit -m "feat: add MarketAlignmentCard to Analytics page"
```

---

### Task 6: Frontend test — MarketAlignmentCard rendering

**Files:**
- Create: `frontend/src/pages/__tests__/AnalyticsPage.test.tsx`

- [ ] **Step 1: Write tests**

Create `frontend/src/pages/__tests__/AnalyticsPage.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import AnalyticsPage from '../AnalyticsPage';
import type { AnalyticsResponse } from '../../types';

// Mock hooks
const mockFetchAnalytics = vi.fn();
const mockSetPageSnapshot = vi.fn();

vi.mock('../../hooks/useAnalytics', () => ({
  useAnalytics: () => mockAnalyticsReturn,
}));

vi.mock('../../hooks/useMutationBus', () => ({
  useMutationBus: () => ({ setPageSnapshot: mockSetPageSnapshot }),
  useOnMutation: vi.fn(),
}));

const BASE_DATA: AnalyticsResponse = {
  skillBreakdown: [],
  activityHeatmap: [],
  velocityTrend: { weeks: [] },
  campaignEta: null,
  skillSuggestions: [],
  marketAlignment: null,
};

let mockAnalyticsReturn: {
  data: AnalyticsResponse | null;
  loading: boolean;
  error: string | null;
  fetchAnalytics: () => Promise<void>;
};

function renderPage() {
  return render(
    <MemoryRouter>
      <AnalyticsPage />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockAnalyticsReturn = {
    data: null,
    loading: false,
    error: null,
    fetchAnalytics: mockFetchAnalytics,
  };
});

describe('MarketAlignmentCard', () => {
  it('shows empty state when marketAlignment is null', () => {
    mockAnalyticsReturn.data = { ...BASE_DATA, marketAlignment: null };
    renderPage();

    expect(screen.getByText('Market Alignment')).toBeInTheDocument();
    expect(screen.getByText(/Set a target role/)).toBeInTheDocument();
  });

  it('renders alignment score and target role', () => {
    mockAnalyticsReturn.data = {
      ...BASE_DATA,
      marketAlignment: {
        alignmentPct: 62.5,
        targetRole: 'AI QA Engineer',
        topGaps: [],
        topStrengths: [],
        calculatedAt: '2026-04-18T00:00:00Z',
      },
    };
    renderPage();

    expect(screen.getByText('63%')).toBeInTheDocument();
    expect(screen.getByText('AI QA Engineer')).toBeInTheDocument();
  });

  it('renders top gaps with demand percentages', () => {
    mockAnalyticsReturn.data = {
      ...BASE_DATA,
      marketAlignment: {
        alignmentPct: 40,
        targetRole: 'Data Scientist',
        topGaps: [
          { skill: 'Python Testing', gap: 0.78, demand: 78 },
          { skill: 'CI/CD', gap: 0.65, demand: 65 },
        ],
        topStrengths: [],
        calculatedAt: '2026-04-18T00:00:00Z',
      },
    };
    renderPage();

    expect(screen.getByText('Python Testing')).toBeInTheDocument();
    expect(screen.getByText('78% of postings')).toBeInTheDocument();
    expect(screen.getByText('CI/CD')).toBeInTheDocument();
    expect(screen.getByText('65% of postings')).toBeInTheDocument();
  });

  it('renders top strengths with scores', () => {
    mockAnalyticsReturn.data = {
      ...BASE_DATA,
      marketAlignment: {
        alignmentPct: 75,
        targetRole: 'QA Lead',
        topGaps: [],
        topStrengths: [
          { skill: 'Manual QA', userScore: 1.0 },
          { skill: 'Test Planning', userScore: 0.9 },
        ],
        calculatedAt: '2026-04-18T00:00:00Z',
      },
    };
    renderPage();

    expect(screen.getByText('Manual QA')).toBeInTheDocument();
    expect(screen.getByText('100%')).toBeInTheDocument();
    expect(screen.getByText('Test Planning')).toBeInTheDocument();
    expect(screen.getByText('90%')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run tests**

Run: `cd frontend && npx vitest --run src/pages/__tests__/AnalyticsPage.test.tsx`
Expected: All 4 tests PASS

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/__tests__/AnalyticsPage.test.tsx
git commit -m "test: add MarketAlignmentCard rendering tests"
```
