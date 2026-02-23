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
cd frontend && npx vitest --run # Run tests (47 tests)
cd frontend && npm run lint     # ESLint

# Backend
.venv/bin/pytest tests/ -x -q   # Run tests (~606 tests, ~8 min)

# Build Strands Lambda Layer (requires Docker)
bash infra/build_layer.sh  # outputs to infra/layer_build/ (~212MB)

# CDK Deploy (all stacks in us-east-1, account 563170906428)
cd infra && AWS_PROFILE=regain npx cdk deploy <StackName> --require-approval never
# Stacks: RegainAuthStack, RegainDataStack, RegainApiStack, RegainAgentStack, RegainAgentCoreStack, RegainMarketIntelStack, RegainVoicePracticeStack, RegainResumeStack
```

## Key Decisions & Patterns

- **No emojis** anywhere in UI text or labels (project requirement)
- Layout sidebar: `w-60` with deep indigo gradient (`#1E2140` to `#12141F`), active nav uses left 3px indicator bar with `animate-glow-pulse`
- Login: split layout (60% dark brand / 40% form), collapses on mobile
- Stat numbers use `font-mono tabular-nums` for alignment + `.stat-value` CSS class for gradient text (neutral-900 to primary-700). Wrap stats in `bg-surface-2 rounded-[var(--radius-button)] px-4 py-3` cells
- Card hover: `transition-all duration-200 hover:shadow-card-hover hover:-translate-y-0.5`
- Custom CSS vars for radii: `--radius-card` (12px), `--radius-button` (8px), `--radius-badge` (pill)
- **Accent palette**: `accent-50` through `accent-600` (warm amber) — for motivational/achievement moments
- **Shadows**: Primary-tinted hover shadows (`--shadow-card-hover` uses `rgba(91,97,213,0.08)`), `--shadow-glow` for UI emphasis
- **Body texture**: Subtle dot grid via `radial-gradient` in `body` styles
- **Page headers**: All main pages use consistent pattern: `h1 text-2xl font-semibold tracking-tight` + subtitle `text-sm text-neutral-500`
- **CSS utility classes**: `.stat-value` (gradient text), `.chat-input-glow` (focus ring), `.section-divider` (gradient line) — defined in `index.css` after base layer
- **Card accent variant**: 3px left primary border for emphasis cards (current focus, primary mission)

## Backend Architecture

- **Handlers**: `backend/handlers/` (NOT `backend/lambda/` — `lambda` is a Python reserved keyword and causes `SyntaxError` on Lambda runtime)
- **DynamoDB attribute names**: All tables use **camelCase** keys (`targetRole`, `campaignId`, `skillsFocus`) — match this in any code that reads from DynamoDB
- **Mission seeding**: `OnboardingService._seed_first_missions()` calls `generate_daily_mission()` during onboarding so users have missions from day 1
- **MarketData GSI**: `role-title-index` on `roleTitle` allows lookup by human-readable role name
- **Thin handler pattern**: Each Lambda handler validates input, delegates to a service class, returns via `success_response`/`error_response` — no business logic in handlers
- **Profile (delete account)**: `backend/handlers/profile/` — cascading hard delete across 5 DynamoDB tables + 3 S3 buckets + Cognito `AdminDeleteUser`. DynamoDB first, S3 second, Cognito last for recoverability
- **Cascade deletion**: Uses `delete_all_by_partition_key()` with `batch_writer()` (25-item batches) for tables with composite keys (Campaigns, MissionHistory, EvidenceVault, VoiceSessions)
- **Shared `get_user_id()`**: `backend/handlers/shared/auth.py` — extracted from 8 handler files. Import: `from backend.handlers.shared.auth import get_user_id`
- **DynamoDB `query_all()`**: `DynamoDBClient.query_all()` follows `LastEvaluatedKey` pagination for complete results. Use for listings (dashboard, evidence, missions, cascade deletion). `query()` returns only the first 1MB page
- **Atomic rate limiting pattern**: Resume rate limit (`_enforce_rate_limit()`) uses conditional DynamoDB updates — same pattern as mission rate limiting in `tools.py:337-382`. Two-step: reset date counter, then atomically increment with `< limit` condition
- **Resume Lambda wiring**: Coaching Lambda has `RESUME_LAMBDA_ARN` and `RESUME_BUCKET_NAME` env vars + IAM permissions, set by AgentStack using plain string ARNs (not construct references) to avoid cyclic CDK dependency
- **Strands Lambda Layer**: Each stack that needs it (ApiStack, AgentStack) creates its own inline `LayerVersion` from `infra/layer_build/`. No cross-stack layer reference — avoids CloudFormation export update failures when layer code changes
- **Agent Gateway fallback**: `backend/agents/coaching/agent.py` checks `AGENTCORE_GATEWAY_ENDPOINT` — if `"pending-agentcore-deploy"` or empty, uses direct `@tool` functions from `tools.py` instead of `GatewayToolClient`. All imports are lazy to avoid circular dependencies
- **Coaching chat streaming**: `useStreamingCoaching` hook connects via WebSocket (`VITE_CHAT_WS_URL`) for progressive text responses. `MarkdownMessage` component renders assistant markdown via `react-markdown` + `remark-gfm`
- **Voice onboarding**: `useVoiceOnboarding` hook handles Nova Sonic bidirectional audio via WebSocket (`VITE_VOICE_WS_URL`). Uses ScriptProcessorNode for capture (intentional — better browser support than AudioWorklet), continuous-buffer ScriptProcessorNode for playback, auto-mutes mic during AI speaking to prevent feedback loop
- **Voice audio protocol**: Backend expects raw base64-encoded PCM 16-bit mono 16kHz in `event.body` (NOT JSON-wrapped). Backend sends JSON: `{"type": "audio", "data": "<base64>"}`, `{"type": "fallback", ...}`, `{"type": "clear_audio", ...}`
- **Skill tag normalization**: `log_evidence` in `tools.py` normalizes skill tags via `taxonomy.normalize_skill()` before storage (e.g. "python" -> "Python Programming"). Unknown tags pass through as-is. `complete_mission` inherits this via its internal `log_evidence` call
- **Prescribed skill tags**: `get_system_prompt()` in `prompts.py` accepts `valid_skill_tags` from the user's campaign `skillsFocus`. When present, the agent is instructed to use only those tags. `get_valid_skill_tags()` in `tools.py` queries the active campaign
- **Mission generation endpoint**: `POST /missions/generate` in the Missions Lambda generates and persists a new mission via the engine pipeline. Uses independent rate limiting (`webMissionGenCount` / `lastWebMissionGenDate` on UserProfiles) with a 6/day limit, separate from the coaching agent's 3/day limit (`dailyMissionGenCount`)
- **Day-change detection**: `Missions.tsx` uses `visibilitychange` listener + 60-second interval to detect UTC date rollover and auto-re-fetch missions. Avoids stale "all caught up" state
- **Voice practice**: `backend/handlers/voice_practice/` — standalone voice-to-voice practice feature with two modes: mock interview and mission discussion. WebSocket handler (`ws_handler.py`) streams Nova Sonic audio, accumulates transcript, generates AI assessment on disconnect. REST handler (`api_handler.py`) serves session list + detail. Assessment generated by Bedrock Nova Lite with structured JSON output
- **Voice practice stack**: `infra/stacks/voice_practice_stack.py` — S3 bucket for transcripts/assessments, WebSocket API + Lambda (120s timeout), REST Lambda, L1 API routes on shared API Gateway. Grants Profile Lambda cross-stack S3 + VoiceSessions table access for cascade deletion
- **Voice practice frontend**: `useVoicePractice` hook handles WebSocket + audio (same pattern as `useVoiceOnboarding`), `useVoiceSessions` hook fetches session list/detail. `VoicePracticePage` has 3 views: mode selection + history, active session, assessing spinner with polling. `VoiceSessionDetailPage` renders assessment sections with ProgressBar scores + expandable transcript
- **Profile cascade deletion**: Deletes across 5 DynamoDB tables + 3 S3 buckets (voice practice, resume, code interpreter) before Cognito deletion. Each S3 bucket cleanup uses `_delete_s3_prefix()` with user-scoped prefix. Env vars: `VOICE_PRACTICE_BUCKET_NAME`, `RESUME_BUCKET_NAME`, `CODE_INTERPRETER_BUCKET_NAME`
- **Resume LLM output cleaning**: `ResumeService._clean_llm_output()` strips markdown code fences (`` ```markdown ... ``` ``) and preamble text that Nova Lite sometimes adds before the `---` frontmatter delimiter. Validation uses case-insensitive section header matching
- **Shared Nova Sonic client**: `backend/handlers/shared/nova_sonic.py` — async bidirectional streaming client using `aws_sdk_bedrock_runtime` SDK (NOT boto3). Used by both coaching voice handler and voice practice handler. Event protocol: sessionStart → promptStart → contentStart/textInput → contentEnd → contentStart(AUDIO) → audioInput chunks. Response loop reads `stream.await_output()` and dispatches to callbacks
- **Nova Sonic model ID**: `amazon.nova-2-sonic-v1:0` (Nova 2 Sonic, NOT `amazon.nova-sonic-v1:0`). Input audio: 16kHz PCM mono. Output audio: 24kHz PCM mono. Lambda layer includes `aws-sdk-bedrock-runtime` package
- **Nova Sonic Lambda async bridge**: Lambda handlers are sync but `aws_sdk_bedrock_runtime` is async. A module-level daemon thread runs `asyncio.run_forever()`, and handlers use `run_coroutine_threadsafe()` to schedule async work. See `ensure_event_loop()` and `run_async()` in `nova_sonic.py`
- **AudioVisualizer**: WebGL 3D orb at `frontend/src/components/voice/AudioVisualizer.tsx` — uses R3F + `three-custom-shader-material` with per-state configs and lerped transitions in `useFrame`

## DynamoDB Table Keys

| Table | Partition Key | Sort Key | GSIs |
|-------|-------------|----------|------|
| UserProfiles | `userId` | — | — |
| Campaigns | `userId` | `campaignId` | `status-index` (PK: status, SK: userId) |
| MissionHistory | `userId` | `missionId` | `status-index`, `date-index` |
| EvidenceVault | `userId` | `evidenceId` | `skill-index` (PK: skillTag, SK: createdAt) |
| MarketData | `sector` | `timestamp` | `role-title-index` (PK: roleTitle) |
| VoiceSessions | `userId` | `sessionId` | `type-date-index` (PK: sessionType, SK: createdAt) |
| WebSocketConnections | `connectionId` | — | — (TTL on `ttl` attribute) |

## Gotchas

- Tailwind v4 uses `@theme` in CSS, not `theme.extend` in config — tokens must go in `index.css`
- React 19: `JSX.Element` namespace requires explicit import (`ReactNode` from 'react' instead)
- SkeletonBlock needs explicit `style` prop in interface if passing inline styles
- Font files must be in `public/fonts/` for Vite to serve them correctly with preload
- **Cognito authorizer** expects **idToken** (not accessToken) when no OAuth scopes are configured
- **API Gateway CORS**: `default_cors_preflight_options` only handles OPTIONS — add `GatewayResponse` for `DEFAULT_4_XX`/`DEFAULT_5_XX` with CORS headers to cover error responses
- **DynamoDB composite keys**: `get_item`/`update_item` on Campaigns requires `{userId, campaignId}`, on MissionHistory requires `{userId, missionId}` — moto mocks dispatch by table name only, so key bugs are invisible in tests
- **Hosting**: AWS Amplify in **us-east-2** (app ID: `d2z52fw5cbbzo`, domain: regain.altivum.ai) — auto-deploys from git push to main
- **Hardcoded counts in tests**: When adding Lambdas/routes to **ApiStack**, update `EXPECTED_LAMBDA_COUNT` in `test_iam_least_privilege.py`, `test_lambda_env_config.py`, `test_lambda_runtime_consistency.py`, and `EXPECTED_METHOD_COUNT` in `test_api_authorization.py`. When adding tables to **DataStack**, update `EXPECTED_TABLE_COUNT` in `test_on_demand_billing.py` and `test_table_output_completeness.py` (+ `known_tables` list). Update `ALLOWED_TABLES` in `test_iam_least_privilege.py` if permissions change
- **Profile Lambda IAM**: Needs `cognito-idp:AdminDeleteUser` on user pool ARN + read/write on 5 DynamoDB tables + S3 delete on 3 buckets (voice practice, resume, code interpreter). `USER_POOL_ID` env var is set via `_table_env()`. Bucket env vars set by VoicePracticeStack, ResumeStack, and AgentCoreStack respectively
- **Nova Lite model ID**: Use `amazon.nova-lite-v1:0` (NOT `us.amazon.nova-lite-v2:0` which doesn't exist). PyYAML is NOT available in Lambda Python 3.12 runtime — use inline string parsing instead
- **L1 API Gateway CORS**: `default_cors_preflight_options` only covers L2 resources. L1 `CfnResource` routes (used in ResumeStack, VoicePracticeStack to avoid cyclic deps) need manual MOCK OPTIONS methods with CORS headers
- **Cross-stack profile Lambda permissions**: ResumeStack and AgentCoreStack both accept `profile_lambda` and call `add_to_role_policy()`/`add_environment()`. Changes flow to ApiStack (the Lambda's owning stack). Use constructed bucket ARNs (not construct references) to avoid cycles
- **Docker Desktop on macOS**: The `/usr/local/bin/docker` symlink may point to `/Volumes/Docker/` (stale) while the actual binary is at `/Applications/Docker.app/Contents/Resources/bin/docker`. The build script auto-detects this
- **`infra/layer_build/`** is gitignored — must be rebuilt locally via `bash infra/build_layer.sh` before `cdk deploy`
- **Lambda Layer build must preserve `.dist-info`**: OpenTelemetry uses `importlib.metadata.entry_points()` which requires `.dist-info` directories. Only remove `__pycache__` in the build script, never `*.dist-info`
- **Cross-stack Lambda Layer references break on update**: CloudFormation can't update an export when other stacks import it, and LayerVersion always creates a new physical resource. Solution: create the layer inline in each stack that needs it
- **CDK cyclic dependency with cross-stack construct references**: When StackA owns a Lambda and StackB owns a resource, passing StackB's construct reference to modify StackA's Lambda env vars creates StackA → StackB dependency. If StackB already depends on StackA, this cycles. Solution: pass plain string ARNs/names (not construct references) and use inline `iam.PolicyStatement` instead of `grant_invoke()`/`grant_read()`. See `agent_stack.py` resume wiring for the pattern
- **Voice audio: use ScriptProcessorNode, not AudioWorklet** — AudioWorklet fails silently in production (module loading issues) and falls back to ScriptProcessor anyway. Use ScriptProcessorNode directly; the deprecation warning is harmless. Reference implementation: `~/Desktop/altivum/elo/src/hooks/useAudioCapture.ts`
- **Voice playback: continuous buffer, not scheduled AudioBufferSource** — Scheduling individual `AudioBufferSourceNode.start(time)` causes audible gaps between chunks. Use a single ScriptProcessorNode with a growing Float32Array buffer (read/write indices) for gapless playback. Reference: `~/Desktop/altivum/elo/src/hooks/useAudioPlayback.ts`
- **Voice feedback prevention**: Auto-mute the mic track when AI is speaking (set `track.enabled = false`). Send silence frames instead of nothing to keep the Nova Sonic stream alive. Unmute when `isAgentSpeaking` goes false
- **Voice practice env var**: `VITE_VOICE_PRACTICE_WS_URL` must be set in Amplify env vars after deploying `RegainVoicePracticeStack` (WebSocket API URL from stack outputs)
- **Amplify env var timing**: Env vars are resolved at build **start** time. If you update env vars after a build triggers, the current build won't have them — trigger a fresh rebuild with `aws amplify start-job --job-type RETRY --job-id <latest>`
- **Coaching tools test import order**: When mocking `backend.engine.generator.complete_mission` in tests, the `patch()` must be active **before** `_load_tools()` re-imports the tools module, because `from ... import ... as engine_complete_mission` captures a binding at import time. Use `with patch(...): tools = _load_tools(...)` not `tools = _load_tools(...); with patch(...):`
- **Mission lifecycle transitions**: Missions must follow `pending -> in_progress -> completed`. Tests for `complete_mission` must seed missions with `status: "in_progress"`, not `"pending"`, or the engine rejects the transition
- **ESLint hook naming**: Don't prefix plain utility functions with `use` (e.g. `useUtcDate`) — ESLint's `react-hooks/rules-of-hooks` rule will flag calls to them inside non-hook functions. Use `get`/`compute`/plain names instead
- **fast-check `fc.date()` generates invalid dates**: `fc.date().map(d => d.toISOString())` can produce `Invalid Date` instances that throw `RangeError`. Fix: use `fc.integer({ min: 946684800000, max: 4102444800000 }).map(ts => new Date(ts).toISOString())` for safe ISO strings
- **`three-custom-shader-material` v6 + R3F**: Do NOT use the `vanilla` import with `extend()` — R3F calls `new CustomShaderMaterial()` with no args, but v6's constructor destructures its first arg, causing `Cannot destructure property 'baseMaterial' of 'undefined'`. Use the default React import (`from 'three-custom-shader-material'`) which is a proper React component that handles construction internally
- **CSM fragment shader `normal` redefinition**: Three.js MeshStandardMaterial declares `vec3 normal` in its built-in fragment shader. CSM injects custom code into the existing shader, so using `normal` as a variable name in the custom fragment causes `'normal' : redefinition`. Use a different name (e.g. `nW`)
- **CDK WebSocketLambdaIntegration shared instance = missing permissions**: When a single `WebSocketLambdaIntegration` instance is shared across `connect_route_options`, `default_route_options`, and `disconnect_route_options`, CDK only adds `lambda:InvokeFunction` permission for the first route (`$connect`). API Gateway silently drops messages for `$default` and `$disconnect`. Fix: create separate integration instances per route
- **WebSocket Lambda has no instance affinity**: API Gateway WebSocket routes (`$connect`, `$default`, `$disconnect`) can each hit different Lambda containers. Module-level Python dicts (`_connections`, `_sessions`) are NOT shared across containers. Fix: persist connection metadata (userId, sessionType, jwtToken) in the `WebSocketConnections` DynamoDB table on `$connect`, load it on `$default`/`$disconnect`. Shared module: `backend/handlers/shared/ws_connections.py`. In-memory `_sessions` (live Nova Sonic streams) are still module-level — they're created on first `$default` after loading connection info from DynamoDB
