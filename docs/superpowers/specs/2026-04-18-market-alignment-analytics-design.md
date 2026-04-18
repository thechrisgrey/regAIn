# Market Alignment on Analytics Page — Design Spec

## Goal

Surface the user's market alignment score and skill-gap-vs-demand breakdown directly on the Analytics page, so users see at a glance how their evidenced skills map to their target role's market requirements.

## Context

The market intelligence pipeline (EventBridge scheduled Lambdas) already ingests O*NET, USAJobs, and BLS data into the `MarketData` DynamoDB table. The `calculate_alignment()` function in `backend/handlers/market_intel/alignment.py` computes alignment percentage and skill breakdowns. Today this data is only accessible through the coaching agent's `get_alignment` tool — not visible in any UI.

## Architecture

Extend the existing `/analytics` endpoint. Add alignment as a 4th parallel query in `AnalyticsService` (bump `ThreadPoolExecutor` to `max_workers=4`). Frontend renders a new "Market Alignment" card in the Analytics page grid. No new endpoints, no new hooks, no new service calls.

## Backend Changes

### AnalyticsService (`backend/handlers/dashboard/analytics_service.py`)

Add a 4th parallel task to `get_analytics()`:

1. Fetch the user's `targetRole` from UserProfiles (the existing 3 tasks query missions, evidence, and campaigns — not UserProfiles, so this is a new DynamoDB read within the 4th task).
2. If `targetRole` is set, call `calculate_alignment(user_id, target_role_id)` from `backend/handlers/market_intel/alignment.py`.
3. If `targetRole` is not set, return `null` for the alignment field.
4. Bump `ThreadPoolExecutor(max_workers=4)`.

### Response Shape

Add `marketAlignment` to `AnalyticsResponse`:

```python
"marketAlignment": {
    "alignmentPct": 62.0,
    "targetRole": "AI QA Engineer",
    "topGaps": [
        {"skill": "Python Testing", "gap": 0.78, "demand": 78},
        {"skill": "CI/CD", "gap": 0.65, "demand": 65}
    ],
    "topStrengths": [
        {"skill": "Manual QA", "userScore": 1.0},
        {"skill": "Test Planning", "userScore": 0.9}
    ],
    "calculatedAt": "2026-04-18T14:30:00Z"
}
```

`marketAlignment` is `null` when `targetRole` is not set or when the alignment calculation fails.

### IAM

The analytics Lambda needs a new DynamoDB read grant for the `MarketData` table. Add to the analytics Lambda's IAM policy in the CDK stack that owns it.

## Frontend Changes

### Types (`frontend/src/types/index.ts`)

```typescript
interface MarketAlignmentGap {
  skill: string;
  gap: number;
  demand: number;
}

interface MarketAlignmentStrength {
  skill: string;
  userScore: number;
}

interface MarketAlignment {
  alignmentPct: number;
  targetRole: string;
  topGaps: MarketAlignmentGap[];
  topStrengths: MarketAlignmentStrength[];
  calculatedAt: string;
}
```

Extend `AnalyticsResponse`:

```typescript
interface AnalyticsResponse {
  // ... existing fields unchanged ...
  marketAlignment: MarketAlignment | null;
}
```

### Analytics Page (`frontend/src/pages/AnalyticsPage.tsx`)

Add a "Market Alignment" card in the grid, positioned above the existing Skill Gaps section.

**Card contents:**

- **Header:** "Market Alignment" with target role name as subtitle text
- **Alignment score:** Large percentage using `.stat-value` gradient text + `font-mono tabular-nums`. `ProgressBar` beneath it with `barClassName` for primary color fill
- **Top Gaps (up to 3):** Skill name + "in X% of postings" + small horizontal bar representing demand weight. These are the actionable items
- **Top Strengths (up to 3):** Skill name + evidence strength as a filled bar or label

**No new hook or service call.** `useAnalytics()` already fetches `/analytics` and returns the full response. The new `marketAlignment` field arrives with the existing data.

### Empty States

| Condition | Card Display |
|-----------|-------------|
| `targetRole` not set (`marketAlignment` is `null`) | "Set a target role in your profile to see market alignment" with link to `/profile` |
| Alignment calculation failed (`marketAlignment` is `null`) | Same as above — subtle, not an error banner |
| No market data for role (0% alignment, empty breakdown) | Card renders 0% with "No market data available for this role yet" |
| Target role set but no evidence | 0% alignment, all skills shown as gaps — correct and useful |

### Error Handling

- The 4th parallel task is independent. If it fails, `marketAlignment` returns `null` and the other 5 sections render normally.
- No new error boundaries needed.

## Styling

Follow existing Analytics page patterns:

- Card uses `Card` component from `components/ui/`
- Alignment percentage uses `.stat-value` CSS class (gradient text, neutral-900 to primary-600) with `bg-surface-2 rounded-[var(--radius-button)] px-4 py-3`
- Gap bars use design token colors (primary palette)
- Strength indicators use success palette
- `calculatedAt` shown as small `text-[10px] text-neutral-400` timestamp
- Staggered `animate-fade-in-up` on card entrance, matching other cards

## Testing

- **Backend unit test:** Verify `get_analytics()` returns `marketAlignment` when `targetRole` is set, and `null` when not set. Mock `calculate_alignment()`.
- **Frontend unit test:** Verify the Market Alignment card renders with mock data and handles `null` gracefully.

## Out of Scope

- Salary intelligence display (chose alignment only)
- Demand trend charts (role_trend data)
- Historical alignment tracking over time
- Caching or pre-computing alignment scores
- Changes to the existing Skill Gaps section (kept as-is)
