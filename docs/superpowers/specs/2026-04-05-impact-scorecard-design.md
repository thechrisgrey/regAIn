# Impact Scorecard — Design Spec

**Date:** 2026-04-05
**Deadline:** April 14 (code complete) / April 17 (article + video publish)
**Context:** AWS 10,000 AIdeas competition finalist — Social Impact category
**Purpose:** Address judge feedback ("crowded market with free alternatives") by shipping the feature no free tool can replicate: an evidence-backed, exportable career readiness score.

---

## 1. Strategic Summary

The Impact Scorecard computes a Composite Readiness Index (CRI) from timestamped, evidence-backed activity data — not self-reported surveys. It synthesizes five dimensions (Mission Velocity, Evidence Density, Market Alignment, Phase Progression, Adaptive Difficulty Trajectory) into a single 0-100 score with full drill-down transparency. The score is exportable as a branded PDF and shareable via a public link.

**The one-line differentiator:** "This score has receipts."

---

## 2. Schema Changes Required

### 2.1 Mission Model — Add `category`, `difficulty`, `skillTags`

**Current state** (`backend/handlers/shared/models.py:139-179`):
The `Mission` dataclass has: `user_id, mission_id, campaign_id, title, description, status, completed_date, evidence_id`.

The engine's `MissionCandidate` (`backend/engine/models.py:14-29`) has `category`, `difficulty`, `skill_tags`, `estimated_minutes`, `expected_evidence_type` — but these are dropped when `MissionsService.generate_mission()` creates the `Mission` object (`backend/handlers/missions/service.py:186-193`).

**Change:**
Add `category`, `difficulty`, and `skill_tags` to the `Mission` dataclass. Persist them when missions are generated from `MissionCandidate` results.

```python
# Mission dataclass additions
category: Optional[str] = None        # "reflection", "skill_building", etc.
difficulty: Optional[int] = None       # 1-5
skill_tags: Optional[List[str]] = None # normalized skill tag list
```

**Files to modify:**
- `backend/handlers/shared/models.py` — add fields to `Mission`, update `to_dynamodb_item()` and `from_dynamodb_item()`
- `backend/handlers/missions/service.py:186-193` — populate `category`, `difficulty`, `skill_tags` from `result.primary`
- `backend/handlers/onboarding/service.py` — if `_seed_first_missions()` creates missions, add fields there too

**Backward compatibility:** Fields are Optional with None defaults. Existing records without these fields continue to work. The scorecard computation handles missing values gracefully.

### 2.2 Evidence Model — Add `wordCount`

**Current state** (`backend/handlers/shared/models.py:182-219`):
The `Evidence` dataclass has: `user_id, evidence_id, mission_id, skill_tag, reflection, created_at, artifact_url`.

**Change:**
Add `word_count` computed from the `reflection` field length at write time.

```python
word_count: Optional[int] = None  # len(reflection.split())
```

**Files to modify:**
- `backend/handlers/shared/models.py` — add field to `Evidence`
- `backend/handlers/missions/service.py:244-255` — compute `word_count` before creating Evidence
- `backend/agents/coaching/tools.py` — in `log_evidence`, compute `word_count` from reflection

### 2.3 Backfill Script

A one-time script to enrich existing MissionHistory records with `category` and `difficulty` by matching against template definitions. Runs as a standalone Python script, not a Lambda.

**Logic:**
- Query all missions for all users
- For each mission, attempt to match `title` against template titles in `templates.py` to recover `category` and default `difficulty`
- For missions that can't be matched, set `category = "general"` and `difficulty = 1`
- Batch-write updates via `batch_writer()`

---

## 3. Scoring Model

### 3.1 Mission Velocity Score (MVS) — Weight: 20%

**Inputs:** MissionHistory (completed missions with timestamps and categories)

**Sub-signals:**
- **Weekly Completion Rate (WCR):** `missions_completed_last_7d / 7`, normalized to 0-1 against a target of 1.0/day
- **Category Distribution Score (CDS):** `1 - (stdev(category_counts) / mean(category_counts))`. Perfectly balanced = 1.0. Single-category focus = lower score.
- **Velocity Trend (VT):** `(WCR_last_7d - WCR_prior_7d) / max(WCR_prior_7d, 0.01)`. Sigmoid-capped to prevent extreme values from dominating.

**Formula:**
```
MVS = (0.5 * WCR_normalized + 0.3 * CDS + 0.2 * sigmoid(VT)) * 100
```

### 3.2 Evidence Density Score (EDS) — Weight: 30%

**Inputs:** EvidenceVault (entries with skillTag, reflection, createdAt, artifactUrl, wordCount)

**Sub-signals:**
- **Evidence Coverage Ratio (ECR):** `missions_with_evidence / total_completed_missions`
- **Evidence Richness Score (ERS):** Per entry: `min(1.0, word_count / 150) * has_artifact_bonus`. Average across entries. `has_artifact_bonus = 1.3 if artifactUrl else 1.0`.
- **Skill Tag Breadth (STB):** `unique_skill_tags / total_entries`. Rewards breadth over repetition.

**Formula:**
```
EDS = (0.4 * ECR + 0.4 * ERS + 0.2 * STB) * 100
```

**Recency weighting:** Evidence entries decay on a 30-day half-life:
```
recency_weight(entry) = 0.5 ^ (days_since_entry / 30)
```

### 3.3 Market Alignment Score (MAS) — Weight: 25%

**Inputs:** EvidenceVault skill tags + MarketData table (O*NET/USAJobs demand)

**Computation:**
1. Build **Target Role Skill Vector (TRSV):** From MarketData, extract `topSkills` for the user's `targetRole`. Each skill has a demand weight (frequency/importance score).
2. Build **User Skill Vector (USV):** From EvidenceVault, compute `{skill: evidence_count * recency_weight}`.
3. Compute **cosine similarity** between TRSV and USV.
4. Apply **demand multiplier** from USAJobs posting volume (capped at 1.2x boost).

**Formula:**
```
MAS_raw = cosine_similarity(TRSV, USV)
DM = sum(USV[skill] * posting_count[skill]) / sum(USV[skill])  # normalized
MAS = 100 * MAS_raw * min(1.2, DM_normalized)
```

**Hot Skills Gap:** The 3 skills where `TRSV[skill] - USV[skill]` is largest. Surfaced in the UI with links to relevant missions.

### 3.4 Phase Progression Score (PPS) — Weight: 15%

**Inputs:** Campaign phase + MissionHistory completion counts

**Formula:**
```
CPI = phase_index / 4   # Foundation=0.25, Expansion=0.50, Launch=0.75, Complete=1.0
PPS = CPI * 100
```

Phase gate criteria satisfied are stored for the drill-down view.

### 3.5 Adaptive Difficulty Score (ADS) — Weight: 10%

**Inputs:** MissionHistory (difficulty per completed mission, by category over time)

**Sub-signals:**
- **Adaptation Rate (AR):** Linear regression slope of difficulty over time, per category. Positive slope = system is increasing challenge.
- **Difficulty Ceiling (DC):** `max(difficulty_completed[category]) / 5`. Highest demonstrated difficulty per category.

**Formula:**
```
ADS = mean(AR_normalized * 50 + DC * 50) across categories
```

### 3.6 Composite Readiness Index (CRI)

```
CRI = (0.20 * MVS) + (0.30 * EDS) + (0.25 * MAS) + (0.15 * PPS) + (0.10 * ADS)
```

**Amplifiers:**
- Difficulty 4-5 evidence gets 1.05x multiplier on EDS contribution
- USAJobs demand surge (>90th percentile) gives temporary 1.10x on MAS for 7 days

**Score caching:** Computed result is stored in the `RegainImpactScores` table (SK=`LATEST`). Recomputed on page load if stale (>1 hour) and nightly via EventBridge. Daily snapshots (SK=`SNAPSHOT#YYYY-MM-DD`) retained for 90 days to power longitudinal charts.

---

## 4. Infrastructure — RegainScoreStack

A new CDK stack: `infra/stacks/score_stack.py`

### 4.1 DynamoDB Table: `RegainImpactScores`

| Key | Type | Purpose |
|-----|------|---------|
| PK: `userId` | String | User identifier |
| SK: `LATEST` or `SNAPSHOT#YYYY-MM-DD` | String | Current score or daily snapshot |

Attributes: `cri`, `missionVelocityScore`, `evidenceDensityScore`, `marketAlignmentScore`, `phaseProgressionScore`, `adaptiveDifficultyScore`, `dimensionDetail` (Map), `computedAt`, `evidenceCount`, `missionsCompleted`.

Daily snapshots have TTL of 90 days for longitudinal chart data.

Billing: PAY_PER_REQUEST. PITR: enabled. Removal policy: follows `retain_data` context pattern.

### 4.2 DynamoDB Table: `RegainPublicScoreLinks`

| Key | Type | Purpose |
|-----|------|---------|
| PK: `shortCode` | String | 8-character URL-safe token |

Attributes: `userId`, `createdAt`, `expiresAt` (TTL), `visibleDimensions` (list of dimension names the user chose to share).

### 4.3 Lambda Functions

**score-compute** (triggered by API Gateway + EventBridge nightly)
- Runtime: Python 3.12, 512 MB, 30s timeout
- Reads: UserProfiles, Campaigns, MissionHistory, EvidenceVault, MarketData (cross-stack grants)
- Writes: RegainImpactScores
- On API trigger: compute for requesting user, return result
- On EventBridge trigger: batch-compute for all active users (scan UserProfiles where `onboardingCompleted = true`)

**score-export-pdf** (triggered by API Gateway)
- Runtime: Python 3.12, 1024 MB, 60s timeout (WeasyPrint is memory-hungry)
- Reads: RegainImpactScores, EvidenceVault, MissionHistory, MarketData
- Writes: S3 exports bucket
- Returns: signed S3 URL (15-minute expiry)
- Lambda layer: WeasyPrint + dependencies

**score-public** (triggered by API Gateway)
- Runtime: Python 3.12, 256 MB, 10s timeout
- Reads: RegainPublicScoreLinks, RegainImpactScores
- Returns: JSON for client-side rendering (no SSR)

### 4.4 S3 Bucket

`regain-score-exports-{account}` — stores generated PDFs. Versioned, encrypted (S3_MANAGED), auto-delete after 30 days via lifecycle rule. Cross-stack grant to profile Lambda for cascade deletion.

### 4.5 EventBridge Rule

Nightly at 02:00 UTC, triggers score-compute Lambda with `{"mode": "batch"}` payload.

### 4.6 API Routes

| Method | Path | Auth | Lambda | Purpose |
|--------|------|------|--------|---------|
| GET | /score | Cognito | score-compute | Get current CRI + dimensions |
| GET | /score/history | Cognito | score-compute | 30/90-day snapshots |
| POST | /score/share | Cognito | score-public | Generate public link |
| POST | /score/export | Cognito | score-export-pdf | Generate PDF, return URL |
| GET | /score/public/{shortCode} | None (public) | score-public | Public scorecard data |

Public route `/score/public/{shortCode}` is behind WAF (existing) but without Cognito authorizer. Rate limited to 100 req/min per IP via WAF rule. Frontend route `/s/:shortCode` renders the `<PublicScorecard />` component and fetches data from this API endpoint.

### 4.7 CI Update

`.github/workflows/ci.yml` — change stack count validation from 8 to 9.

---

## 5. Frontend Components

All components follow existing REGAIN patterns: Tailwind v4 design tokens, CSS animations with `animate-fade-in` / `animate-fade-in-up`, warm cocoa/mauve palette, General Sans + JetBrains Mono fonts. No emojis.

### 5.1 Data Layer

**`useImpactScore()` hook** — wraps `GET /score`, 60s cache TTL via `cachedGet()`. Returns `{ score, dimensions, loading, error, refresh }`.

**`useScoreHistory()` hook** — wraps `GET /score/history`. Returns `{ snapshots, loading, error }`.

**API additions to `frontend/src/services/api.ts`:**
```typescript
score: {
  get: (token: string) => cachedGet<ScoreResponse>('/score', token, 60_000),
  history: (token: string) => cachedGet<ScoreHistoryResponse>('/score/history', token, 60_000),
  share: (token: string) => apiRequest<ShareResponse>('/score/share', { method: 'POST' }, token),
  exportPdf: (token: string) => apiRequest<ExportResponse>('/score/export', { method: 'POST' }, token),
},
```

**Types** added to `frontend/src/types/index.ts` or a new `types/score.ts`.

### 5.2 Page: `<ImpactScorecard />`

Route: `/analytics` (replaces or enhances existing AnalyticsPage)
Lazy-loaded in `App.tsx`.

**Layout (desktop):**
```
[Page Header: "Impact Scorecard" + subtitle]
[CRI Gauge — centered hero, large arc]
[Phase Track — horizontal below gauge]
[5 Dimension Tiles — row of cards]
[Evidence Density Chart — skill constellation or bar chart]
[Market Alignment Radar + Hot Skills]
[Difficulty Trajectory Chart]
[Export Bar — sticky bottom]
```

**States:**
- Loading: Skeleton matching the layout structure
- Error: Retry card (existing DashboardError pattern)
- Empty (day 1): "Your scorecard starts here" card with CTA to first mission
- Partial (day 7): CRI gauge with real score, coaching prompt
- Full (day 30+): All components populated, export CTA prominent

### 5.3 `<CRIGauge />`

SVG arc gauge. Props: `score: number`, `evidenceCount: number`.
- Arc draws from 0 to score over 1.2s on mount (CSS animation on `stroke-dashoffset`)
- Score number in center: General Sans 72px, neutral-900
- Below arc: "Backed by {N} pieces of documented evidence" in JetBrains Mono
- Click opens `<CRIBreakdown />` modal — drill-down tree showing dimension → sub-signal → evidence trace

### 5.4 `<DimensionTile />`

Compact card component used 5x. Props: `name`, `score`, `trend`, `sparklineData`.
- Score in JetBrains Mono (signals "computed, not felt")
- 7-day sparkline: lightweight SVG polyline, no library needed
- Trend arrow: up (green), down (amber), flat (neutral)
- Click expands to full chart view for that dimension

### 5.5 `<SkillConstellation />`

D3-force node graph. Props: `skills: { name, count, lastDate, connections }[]`.
- Each node: `<circle>` sized by evidence count
- Edges: `<line>` connecting skills that co-appear on the same mission
- Color intensity: recency (bright = last 7 days, faded = 30+ days)
- Animates on mount: nodes appear sequentially, edges draw
- Mobile fallback: `<SkillBarChart />` horizontal bars grouped by skill

**Dependencies:** `d3-force` and `d3-scale` only (not the full D3 bundle). Tree-shakeable.

**Isolation:** Lazy-loaded via `React.lazy()` to avoid loading D3 on other pages. Follows the same pattern as AudioVisualizer (heavy dependency isolated to its own component).

### 5.6 `<MarketAlignmentRadar />`

Spider/radar chart. Props: `targetSkills`, `userSkills`, `hotSkillsGap`.
- Two datasets: O*NET target boundary (outer, neutral-300 stroke) + user evidence fill (inner, primary-500 fill with 0.3 opacity)
- 8-10 spokes for top skills of target role
- Hot Skills panel below: 3 cards showing highest-demand gaps with "Start Mission" link

**Implementation:** Custom SVG (radar charts are straightforward geometry — no library needed). 8-10 spokes with polar coordinate math.

### 5.7 `<PhaseTrack />`

Horizontal four-node timeline. Props: `currentPhase`, `gateCriteria`.
- Nodes: Foundation, Expansion, Launch, Complete
- Completed nodes: filled primary-500, clickable to show gate criteria met
- Current node: ring glow animation (reuse `animate-glow-pulse` from nav)
- Future nodes: neutral-200

### 5.8 `<DifficultyTrajectory />`

Multi-line chart. Props: `historyByCategory: Record<string, {date, difficulty}[]>`.
- One line per mission category, using 5 distinct colors from the palette
- Y-axis: difficulty 1-5
- X-axis: time (last 30/90 days)
- Milestone annotations auto-generated: "Reached Difficulty 4 in Skill Building"

**Implementation:** Custom SVG with the same lightweight approach as sparklines. No charting library.

### 5.9 `<ScoreExportBar />`

Floating bottom bar. Props: `onExportPdf`, `onShare`.
- Appears after scrolling past the CRI gauge
- Two buttons: "Download Report" (triggers PDF generation) and "Share Scorecard" (generates public link, copies URL)
- Loading states for both actions
- Uses existing Button component

### 5.10 `<PublicScorecard />`

Route: `/s/:shortCode` (outside the authenticated layout)
- Fetches public score data from `GET /s/{shortCode}`
- Simplified layout: CRI gauge, dimension tiles, privacy-filtered evidence
- Verification badge: "Score computed from timestamped activity data. Not self-reported."
- No sidebar, no navigation — standalone page with REGAIN branding

### 5.11 Login Page Hero

Add a section above the sign-in form in `Login.tsx`:
- On the brand panel (desktop left 60%): replace the current single-line copy with 3-4 sentences explaining what REGAIN does
- On mobile: enhance the header copy similarly
- No mock data, no screenshots — just clear positioning copy

---

## 6. PDF Report Structure

**5-page Career Evidence Report:**

| Page | Content |
|------|---------|
| Cover | User name, target role, CRI score (gauge graphic), export date, REGAIN branding |
| Executive Summary | Auto-generated narrative paragraph + 5 dimension scores as horizontal bars |
| Evidence Highlights | Top 5 evidence entries (selected by richness score), each with mission title, date, skill tags, reflection excerpt |
| Market Alignment | Radar chart (rendered as static SVG), hot skills gaps, target role description |
| Mission History | Chronological completion list, category distribution chart, difficulty trajectory |

**Footer on every page:**
"This report was generated from verified, timestamped activity data. REGAIN does not issue scores based on self-reported surveys."

**Tech:** WeasyPrint Lambda layer renders HTML/CSS template to PDF. Jinja2 for templating. HTML template uses inline styles (WeasyPrint supports a subset of CSS).

---

## 7. Phased Build Plan

### Phase 1: Backend Foundation (Days 1-3)

**Day 1 — Schema changes + backfill**
- [ ] Add `category`, `difficulty`, `skill_tags` to `Mission` model
- [ ] Add `word_count` to `Evidence` model
- [ ] Update `MissionsService.generate_mission()` to populate new fields from `MissionCandidate`
- [ ] Update `MissionsService.complete_mission()` to compute `word_count`
- [ ] Update `log_evidence` in coaching tools to compute `word_count`
- [ ] Update onboarding `_seed_first_missions()` if it creates missions
- [ ] Write backfill script for existing mission records
- [ ] Update affected tests

**Day 2 — Score computation service**
- [ ] Create `backend/handlers/score/service.py` with `ScoreService`
- [ ] Implement `compute_mission_velocity()` (WCR, CDS, velocity trend, sigmoid)
- [ ] Implement `compute_evidence_density()` (ECR, ERS, STB, recency half-life)
- [ ] Implement `compute_market_alignment()` (cosine similarity, demand multiplier)
- [ ] Implement `compute_phase_progression()`
- [ ] Implement `compute_adaptive_difficulty()` (regression slope, difficulty ceiling)
- [ ] Implement `compute_cri()` (weighted composite with amplifiers)
- [ ] Implement `get_hot_skills_gap()`
- [ ] Implement `get_drill_down_tree()` (CRI → dimensions → evidence trace)
- [ ] Unit tests for each computation function

**Day 3 — Score Lambda handler + CDK stack**
- [ ] Create `backend/handlers/score/handler.py` (thin handler pattern)
- [ ] Create `infra/stacks/score_stack.py` (RegainScoreStack)
  - ImpactScores table + PublicScoreLinks table
  - score-compute Lambda + IAM grants for 5 data tables
  - EventBridge nightly rule
  - API routes via L1 CfnResource (avoid cyclic deps with ApiStack)
- [ ] Wire ScoreStack in `infra/app.py`
- [ ] Update CI stack count: 8 → 9
- [ ] Update `EXPECTED_LAMBDA_COUNT` in affected infra tests
- [ ] CDK synth validation

### Phase 2: Frontend Core (Days 4-6)

**Day 4 — Data layer + page scaffold + CRI gauge**
- [ ] Add score types to `frontend/src/types/`
- [ ] Add score API methods to `frontend/src/services/api.ts`
- [ ] Create `useImpactScore()` and `useScoreHistory()` hooks
- [ ] Create `<ImpactScorecard />` page with skeleton loading
- [ ] Update `App.tsx` routing (enhance or replace AnalyticsPage)
- [ ] Build `<CRIGauge />` SVG arc with mount animation
- [ ] Build `<CRIBreakdown />` drill-down modal

**Day 5 — Dimension tiles + phase track + difficulty chart**
- [ ] Build `<DimensionTile />` component (shared, 5 configurations)
- [ ] Build sparkline SVG helper (reusable lightweight component)
- [ ] Build `<PhaseTrack />` with gate criteria expansion
- [ ] Build `<DifficultyTrajectory />` multi-line SVG chart
- [ ] Wire empty state (day 1 / day 7 / day 30 variants)

**Day 6 — Constellation + radar + export bar**
- [ ] Build `<SkillConstellation />` with D3-force
- [ ] Build `<SkillBarChart />` mobile fallback
- [ ] Build `<MarketAlignmentRadar />` custom SVG spider chart
- [ ] Build hot skills gap panel with mission links
- [ ] Build `<ScoreExportBar />` floating action bar

### Phase 3: Export + Public + Polish (Days 7-9)

**Day 7 — PDF export**
- [ ] Create WeasyPrint Lambda layer (Docker build)
- [ ] Create `backend/handlers/score/pdf_service.py`
- [ ] Design HTML/CSS template (Jinja2) for 5-page report
- [ ] Create `score-export-pdf` Lambda handler
- [ ] Add S3 bucket to ScoreStack
- [ ] Wire `POST /score/export` route
- [ ] Test PDF generation end-to-end

**Day 8 — Public scorecard + share flow**
- [ ] Create `score-public` Lambda handler
- [ ] Create public link generation (short code + DynamoDB write)
- [ ] Wire `POST /score/share` and `GET /s/{shortCode}` routes
- [ ] Build `<PublicScorecard />` page (standalone, no auth)
- [ ] Add privacy controls to share flow (select visible dimensions)
- [ ] Add WAF rule for public route rate limiting

**Day 9 — Polish + Login hero + testing**
- [ ] Update Login.tsx brand panel copy
- [ ] Mobile responsiveness pass on all scorecard components
- [ ] Constellation → bar chart breakpoint handling
- [ ] Integration testing (generate missions → complete → verify score computes)
- [ ] Seed demo account with realistic 30-day journey for video
- [ ] Run full test suites (frontend + backend + infra)

### Phase 4: Article + Video (Days 10-12)

**Days 10-11 — Article + demo video**
- [ ] Write finalist article (1,500-2,000 words) using paragraphs from expansion doc
- [ ] Record demo video (<3 minutes) with Impact Scorecard as centerpiece
- [ ] Upload video to YouTube, embed in article

**Day 12 — Buffer + publish**
- [ ] Final review of article
- [ ] Publish to AWS Builder Center with required tags
- [ ] Verify all links work

---

## 8. Dependencies and Risks

| Risk | Mitigation |
|------|-----------|
| WeasyPrint Lambda layer size (~40MB) | Build early (Day 7), test in isolation. Fallback: CSS print stylesheet if layer build fails |
| D3-force bundle size | Import only `d3-force` and `d3-scale` (~15KB gzipped). Lazy-load the constellation component |
| MarketData table may have sparse data for some roles | Graceful degradation: if no market data for target role, MAS shows "Insufficient market data" instead of 0 |
| Backfill may not perfectly match categories | Acceptable: backfill uses best-effort template matching. New missions will have accurate data |
| 9-stack CI change could conflict with in-flight PRs | Merge schema + CDK changes as first PR before frontend work begins |
| WeasyPrint CSS support is limited | Use simple layouts, inline styles, no flexbox/grid in PDF template. Test early |

---

## 9. What's Deferred (Post-Competition)

- NACE competency overlay (additive, no schema changes needed)
- QR code generation (trivial, ~2 hours)
- Structured JSON API for AI recruiting agents (endpoint + OpenAPI spec)
- Gamification (streaks, badges, phase celebration animations)
- Cohort percentile comparisons (requires aggregate user data)
- DynamoDB Streams for real-time score recomputation
- Skill constellation → force-directed improvements (physics tuning, zoom, filter)
