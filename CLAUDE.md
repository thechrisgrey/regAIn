# REGAIN — Project Guide

## Architecture

- **Backend**: Python CDK stacks (`infra/`), Lambda handlers, DynamoDB
- **Frontend**: React 19 + Tailwind v4 + Vite 8 (`frontend/`)
- **Auth**: AWS Cognito via Amplify SDK (env vars: `VITE_USER_POOL_ID`, `VITE_USER_POOL_CLIENT_ID`)

## Frontend Design System

### Tokens & Theming
- All design tokens live in `frontend/src/index.css` via Tailwind v4 `@theme` block
- `tailwind.config.js` is minimal — do NOT add theme extensions there; use `@theme` in CSS
- Fonts: General Sans (sans) + JetBrains Mono (mono) — self-hosted in `public/fonts/`

### Color Palette
- **Primary**: `primary-50` through `primary-900` (slate-blue, #5B61D5 at 500)
- **Surfaces**: `surface-1` (white) through `surface-4` (light gray) — use for bg hierarchy
- **Neutrals**: `neutral-50` through `neutral-900` — use instead of `gray-*` or `slate-*`
- **Semantic**: `success-*`, `warning-*`, `error-*`, `info-*`
- **Never use** raw Tailwind `indigo-*`, `blue-*`, `gray-*`, `slate-*` in UI code

### Shared Components (`frontend/src/components/ui/`)
- `Button` — 4 variants (primary, secondary, ghost, destructive) × 3 sizes (sm, md, lg)
- `Card` — 3 variants (default, elevated, accent) + `hoverable` prop
- `Badge` — 6 variants (primary, success, warning, error, info, default); pill-shaped
- `Input`, `Textarea`, `Select` — with `label` and `error` props
- `SectionLabel` — replaces `text-[11px] uppercase tracking-widest` pattern
- `ProgressBar` — animated fill on mount, accepts `barClassName` for custom color
- `SkeletonBlock` — shimmer gradient animation
- `NavIcon` — SVG icon map for sidebar nav items
- Barrel export from `components/ui/index.ts`

### Shared Utilities
- `utils/campaign.ts` — `phaseIndex`, `phaseLabel`, `phaseProgress`, `daysActive`, `formatDate`
- `utils/evidence.ts` — `computeSkillStats()` (used by Evidence.tsx and Profile.tsx)

### Animation System (CSS-only, no Framer Motion)
- `animate-fade-in` — page root transitions
- `animate-fade-in-up` — staggered card/list items (use `style={{ animationDelay }}`)
- `animate-scale-in` — chat messages, modals
- `animate-shimmer` — skeleton loading states
- `animate-voice-pulse`, `animate-voice-breathe`, `animate-voice-ripple` — voice session visual indicators
- All keyframes defined in `index.css`; animations use `backwards` fill mode

## Commands

```bash
# Frontend
cd frontend && npm run dev      # Dev server
cd frontend && npm run build    # tsc + vite build
cd frontend && npx vitest --run # Run tests (36 tests)
cd frontend && npm run lint     # ESLint

# Backend
.venv/bin/pytest tests/ -x -q   # Run tests (~551 tests, ~8 min)

# Build Strands Lambda Layer (requires Docker)
bash infra/build_layer.sh  # outputs to infra/layer_build/ (~212MB)

# CDK Deploy (all stacks in us-east-1, account 563170906428)
cd infra && AWS_PROFILE=regain npx cdk deploy <StackName> --require-approval never
# Stacks: RegainAuthStack, RegainDataStack, RegainApiStack, RegainAgentStack, RegainAgentCoreStack, RegainMarketIntelStack
```

## Key Decisions & Patterns

- **No emojis** anywhere in UI text or labels (project requirement)
- Layout sidebar: `w-60 bg-neutral-900`, active nav uses left indicator bar
- Login: split layout (60% dark brand / 40% form), collapses on mobile
- Stat numbers use `font-mono tabular-nums` for alignment
- Card hover: `transition-all duration-200 hover:shadow-card-hover hover:-translate-y-px`
- Custom CSS vars for radii: `--radius-card` (8px), `--radius-button` (6px), `--radius-badge` (pill)

## Backend Architecture

- **Handlers**: `backend/handlers/` (NOT `backend/lambda/` — `lambda` is a Python reserved keyword and causes `SyntaxError` on Lambda runtime)
- **DynamoDB attribute names**: All tables use **camelCase** keys (`targetRole`, `campaignId`, `skillsFocus`) — match this in any code that reads from DynamoDB
- **Mission seeding**: `OnboardingService._seed_first_missions()` calls `generate_daily_mission()` during onboarding so users have missions from day 1
- **MarketData GSI**: `role-title-index` on `roleTitle` allows lookup by human-readable role name
- **Thin handler pattern**: Each Lambda handler validates input, delegates to a service class, returns via `success_response`/`error_response` — no business logic in handlers
- **Profile (delete account)**: `backend/handlers/profile/` — cascading hard delete across 4 DynamoDB tables + Cognito `AdminDeleteUser`. DynamoDB deletions first, Cognito last for recoverability
- **Cascade deletion**: Uses `delete_all_by_partition_key()` with `batch_writer()` (25-item batches) for tables with composite keys (Campaigns, MissionHistory, EvidenceVault)
- **Strands Lambda Layer**: Each stack that needs it (ApiStack, AgentStack) creates its own inline `LayerVersion` from `infra/layer_build/`. No cross-stack layer reference — avoids CloudFormation export update failures when layer code changes
- **Agent Gateway fallback**: `backend/agents/coaching/agent.py` checks `AGENTCORE_GATEWAY_ENDPOINT` — if `"pending-agentcore-deploy"` or empty, uses direct `@tool` functions from `tools.py` instead of `GatewayToolClient`. All imports are lazy to avoid circular dependencies
- **Coaching chat streaming**: `useStreamingCoaching` hook connects via WebSocket (`VITE_CHAT_WS_URL`) for progressive text responses. `MarkdownMessage` component renders assistant markdown via `react-markdown` + `remark-gfm`
- **Voice onboarding**: `useVoiceOnboarding` hook handles Nova Sonic bidirectional audio via WebSocket (`VITE_VOICE_WS_URL`). Uses ScriptProcessorNode for capture (intentional — better browser support than AudioWorklet), continuous-buffer ScriptProcessorNode for playback, auto-mutes mic during AI speaking to prevent feedback loop
- **Voice audio protocol**: Backend expects raw base64-encoded PCM 16-bit mono 16kHz in `event.body` (NOT JSON-wrapped). Backend sends JSON: `{"type": "audio", "data": "<base64>"}`, `{"type": "fallback", ...}`, `{"type": "clear_audio", ...}`
- **Skill tag normalization**: `log_evidence` in `tools.py` normalizes skill tags via `taxonomy.normalize_skill()` before storage (e.g. "python" -> "Python Programming"). Unknown tags pass through as-is. `complete_mission` inherits this via its internal `log_evidence` call
- **Prescribed skill tags**: `get_system_prompt()` in `prompts.py` accepts `valid_skill_tags` from the user's campaign `skillsFocus`. When present, the agent is instructed to use only those tags. `get_valid_skill_tags()` in `tools.py` queries the active campaign

## DynamoDB Table Keys

| Table | Partition Key | Sort Key | GSIs |
|-------|-------------|----------|------|
| UserProfiles | `userId` | — | — |
| Campaigns | `userId` | `campaignId` | `status-index` (PK: status, SK: userId) |
| MissionHistory | `userId` | `missionId` | `status-index`, `date-index` |
| EvidenceVault | `userId` | `evidenceId` | `skill-index` (PK: skillTag, SK: createdAt) |
| MarketData | `sector` | `timestamp` | `role-title-index` (PK: roleTitle) |

## Gotchas

- Tailwind v4 uses `@theme` in CSS, not `theme.extend` in config — tokens must go in `index.css`
- React 19: `JSX.Element` namespace requires explicit import (`ReactNode` from 'react' instead)
- SkeletonBlock needs explicit `style` prop in interface if passing inline styles
- Font files must be in `public/fonts/` for Vite to serve them correctly with preload
- **Cognito authorizer** expects **idToken** (not accessToken) when no OAuth scopes are configured
- **API Gateway CORS**: `default_cors_preflight_options` only handles OPTIONS — add `GatewayResponse` for `DEFAULT_4_XX`/`DEFAULT_5_XX` with CORS headers to cover error responses
- **DynamoDB composite keys**: `get_item`/`update_item` on Campaigns requires `{userId, campaignId}`, on MissionHistory requires `{userId, missionId}` — moto mocks dispatch by table name only, so key bugs are invisible in tests
- **Hosting**: AWS Amplify in **us-east-2** (app ID: `d2z52fw5cbbzo`, domain: regain.altivum.ai) — auto-deploys from git push to main
- **Hardcoded Lambda/method counts in tests**: When adding a new Lambda or API route, update `EXPECTED_LAMBDA_COUNT` in `test_iam_least_privilege.py`, `test_lambda_env_config.py`, `test_lambda_runtime_consistency.py`, and `EXPECTED_METHOD_COUNT` in `test_api_authorization.py`
- **Profile Lambda IAM**: Needs `cognito-idp:AdminDeleteUser` on user pool ARN + read/write on 4 DynamoDB tables. `USER_POOL_ID` env var is set via `_table_env()`
- **Docker Desktop on macOS**: The `/usr/local/bin/docker` symlink may point to `/Volumes/Docker/` (stale) while the actual binary is at `/Applications/Docker.app/Contents/Resources/bin/docker`. The build script auto-detects this
- **`infra/layer_build/`** is gitignored — must be rebuilt locally via `bash infra/build_layer.sh` before `cdk deploy`
- **Lambda Layer build must preserve `.dist-info`**: OpenTelemetry uses `importlib.metadata.entry_points()` which requires `.dist-info` directories. Only remove `__pycache__` in the build script, never `*.dist-info`
- **Cross-stack Lambda Layer references break on update**: CloudFormation can't update an export when other stacks import it, and LayerVersion always creates a new physical resource. Solution: create the layer inline in each stack that needs it
- **Voice audio: use ScriptProcessorNode, not AudioWorklet** — AudioWorklet fails silently in production (module loading issues) and falls back to ScriptProcessor anyway. Use ScriptProcessorNode directly; the deprecation warning is harmless. Reference implementation: `~/Desktop/altivum/elo/src/hooks/useAudioCapture.ts`
- **Voice playback: continuous buffer, not scheduled AudioBufferSource** — Scheduling individual `AudioBufferSourceNode.start(time)` causes audible gaps between chunks. Use a single ScriptProcessorNode with a growing Float32Array buffer (read/write indices) for gapless playback. Reference: `~/Desktop/altivum/elo/src/hooks/useAudioPlayback.ts`
- **Voice feedback prevention**: Auto-mute the mic track when AI is speaking (set `track.enabled = false`). Send silence frames instead of nothing to keep the Nova Sonic stream alive. Unmute when `isAgentSpeaking` goes false
- **Amplify env var timing**: Env vars are resolved at build **start** time. If you update env vars after a build triggers, the current build won't have them — trigger a fresh rebuild with `aws amplify start-job --job-type RETRY --job-id <latest>`
- **Coaching tools test import order**: When mocking `backend.engine.generator.complete_mission` in tests, the `patch()` must be active **before** `_load_tools()` re-imports the tools module, because `from ... import ... as engine_complete_mission` captures a binding at import time. Use `with patch(...): tools = _load_tools(...)` not `tools = _load_tools(...); with patch(...):`
- **Mission lifecycle transitions**: Missions must follow `pending -> in_progress -> completed`. Tests for `complete_mission` must seed missions with `status: "in_progress"`, not `"pending"`, or the engine rejects the transition
