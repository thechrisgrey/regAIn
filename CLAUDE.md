# REGAIN — Project Guide

## AWS AIdeas Competition Context

REGAIN is a **top-50 finalist** (out of 10,000 submissions) in the AWS 10,000 AIdeas competition.

### Semi-Finalist Rules
- **Kiro requirement**: Must use Kiro for at least part of development
- **AWS Free Tier**: App must stay within AWS Free Tier limits
- **Originality**: App must be completely original and not yet published
- **Builder Center article**: Semi-finalists publish an article showcasing the app, AWS services used, team name, and a demo

### Judge Feedback
> "The idea is great with forward-thinking AI integration and sophisticated technical execution but would sit in a crowded market space that offers free alternatives."

### Implications for Development
- **Differentiation is critical**: Lean into what free tools can't do: persistent memory across sessions, personalized mission-based skill development, voice practice with real-time assessment, market-aligned career intelligence
- **Free Tier awareness**: DynamoDB 25 RCU/WCU, Lambda 1M requests/mo, S3 5GB, Cognito 50K MAU, API Gateway 1M calls/mo
- **Kiro integration**: Track which parts of development use Kiro for the article writeup

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
- **Primary**: `primary-50` through `primary-900` (warm cocoa, #916D65 at 500)
- **Surfaces**: `surface-1` (white) through `surface-4` (#E5DBD8 warm blush)
- **Neutrals**: `neutral-50` through `neutral-900` (warm spectrum) — use instead of `gray-*` or `slate-*`
- **Semantic**: `success-*`, `warning-*`, `error-*`, `info-*`
- **Accent**: `accent-50` through `accent-600` (dusty mauve, #BFA8C5 at 400)
- **Steel**: `steel-50` through `steel-500` (cool blue, #B6C8E2 at 300)
- **Peach**: `peach-50` through `peach-300` (warm cream, #FCE5C7 at 100)
- **Never use** raw Tailwind `indigo-*`, `blue-*`, `gray-*`, `slate-*` in UI code
- **Brand hex codes**: `#B6C8E2`, `#FCE5C7`, `#BFA8C5`, `#E5DBD8`, `#916D65`

### Shared Components (`frontend/src/components/ui/`)
- `Button` — 4 variants (primary, secondary, ghost, destructive) × 3 sizes. Supports `forwardRef`
- `Card` — 3 variants (default, elevated, accent) + `hoverable` prop
- `Badge` — 6 variants (primary, success, warning, error, info, default); pill-shaped
- `Input`, `Textarea`, `Select` — with `label` and `error` props
- `SectionLabel` — replaces `text-[11px] uppercase tracking-widest` pattern
- `ProgressBar` — animated fill on mount, accepts `barClassName` for custom color
- `SkeletonBlock` — shimmer gradient animation
- `AgentActivityFeed` — step-by-step tool execution feed; takes `steps: ToolStep[]` + `visible: boolean`
- `ConfirmDialog` — accessible modal (focus trap, focus restore). Props: `open`, `title`, `description?`, `confirmLabel`, `cancelLabel`, `variant`, `onConfirm`, `onCancel`
- `NavIcon` — SVG icon map for sidebar nav items
- Barrel export from `components/ui/index.ts`

### Route-Level Components
- `ErrorBoundary` — wraps `<Outlet>`, catches render errors. Order: `ErrorBoundary > Suspense > Outlet` in `Layout.tsx`
- `RouteLoader` — centered spinner for Suspense fallback

### Code Splitting
- Lazy-loaded in `App.tsx`: `CoachingPage`, `VoicePracticePage`, `VoiceSessionDetailPage`, `ResumePage`, `OnetPage`
- Eagerly loaded: `Dashboard`, `Missions`, `Evidence`, `Profile`, `Onboarding`, `Login`
- Three.js isolated to `three` manual chunk via `vite.config.ts` `rolldownOptions`

### Shared Hooks
- `hooks/MutationBusContext.tsx` + `useMutationBus.ts` — ref-based event bus for cross-page data freshness. `emit({ type: 'mission:completed' })` triggers auto-refresh via `useOnMutation`
- `hooks/CoachingContext.tsx` — `connectionStatus`, `streamHint` (45s warning), `sendMessage` returns `Promise<boolean>`

### Shared Services (`frontend/src/services/`)
- `cache.ts` — `RequestCache` with SWR (stale-while-revalidate). `get(key, fetcher, ttlMs)` deduplicates in-flight requests. Singleton: `requestCache`
- `api.ts` — `cachedGet()` for reads (30s TTL). Mutations call `invalidateCache()`. AbortController timeout (30s) + retry on 5xx for GETs (2 retries, 100ms/200ms delays)

### Auth Token Caching
- `AuthContext.tsx` caches Cognito idToken in `useRef` for 55 minutes (1-min buffer before 1-hour expiry). Cleared on sign-out

### Shared Utilities
- `utils/campaign.ts` — `phaseIndex`, `phaseLabel`, `phaseProgress`, `daysActive`, `formatDate`
- `utils/evidence.ts` — `computeSkillStats()` (used by Evidence.tsx and Profile.tsx)

### Animation System (CSS-only)
- `animate-fade-in`, `animate-fade-in-up` (staggered), `animate-scale-in`, `animate-shimmer`
- `animate-voice-pulse`, `animate-voice-breathe`, `animate-voice-ripple` — voice session indicators
- Keyframes in `index.css`; use `backwards` fill mode

## Commands

```bash
# Frontend
cd frontend && npm run dev      # Dev server
cd frontend && npm run build    # tsc + vite build
cd frontend && npx vitest --run # Run tests (112 tests)
cd frontend && npm run lint     # ESLint

# Backend
.venv/bin/pytest tests/ -x -q   # Run tests (~665 tests, ~8 min)
.venv/bin/pytest tests/integration/ -x -q -v  # Integration tests only

# Build Strands Lambda Layer (requires Docker)
bash infra/build_layer.sh  # outputs to infra/layer_build/ (~212MB)

# CDK Deploy — ALWAYS use the safe wrapper (all stacks: account 563170906428, us-east-1)
# The wrapper validates caller identity before deploy, preventing silent cross-account drift
# when SSO expires and CDK falls back to long-lived IAM user creds in ~/.aws/credentials.
bash scripts/deploy.sh <StackName>
bash scripts/deploy.sh <StackName> --exclusively   # skip dependency stacks
# Stacks: RegainAuthStack, RegainDataStack, RegainApiStack, RegainAgentStack, RegainAgentCoreStack, RegainMarketIntelStack, RegainVoicePracticeStack, RegainResumeStack, RegainScoreStack

# DO NOT run `npx cdk deploy` directly — credential chain silently routes to account 205930636302
# via the default IAM user when SSO expires. The wrapper strips leaked AWS_* env vars, refreshes
# SSO if needed, and asserts account=563170906428 before calling cdk. See scripts/deploy.sh.
```

## Key Decisions & Patterns

- **No emojis** anywhere in UI text or labels
- **Logo**: Cursive "Regain." script at `public/regain-type.png` — use `<img>` with `brightness-0 invert` filter on dark backgrounds. Never hard-type "REGAIN" in UI
- **Layout sidebar**: `w-60`, warm chocolate gradient (`#3B2D27` → `#261C18`). Active nav uses left 3px indicator in `accent-400` with `animate-glow-pulse`
- **Login**: split layout (60% dark brand / 40% form), collapses on mobile. Gradient (`#3B2D27` → `#261C18` → `#1a1412`)
- **Intro video**: `IntroVideo.tsx` plays `regain-prod.mp4` from S3 (`regain-media` bucket, us-east-2) on first visit per session. `sessionStorage` gating
- **Stat numbers**: `font-mono tabular-nums` + `.stat-value` CSS class (gradient text, neutral-900 to primary-600). Wrap in `bg-surface-2 rounded-[var(--radius-button)] px-4 py-3`
- **Card hover**: `transition-all duration-200 hover:shadow-card-hover hover:-translate-y-0.5`
- **CSS vars**: `--radius-card` (12px), `--radius-button` (8px), `--radius-badge` (pill)
- **Shadows**: `--shadow-card-hover` uses `rgba(145,109,101,0.08)`, `--shadow-glow` uses mauve
- **Body texture**: Subtle dot grid via `radial-gradient` in `body` styles
- **Page headers**: `h1 text-2xl font-semibold tracking-tight` + subtitle `text-sm text-neutral-500`
- **CSS utility classes**: `.stat-value`, `.chat-input-glow`, `.section-divider`
- **Card accent variant**: 3px left primary border for emphasis cards

## Backend Architecture

- **Handlers**: `backend/handlers/` (NOT `backend/lambda/` — `lambda` is a Python reserved keyword)
- **DynamoDB attribute names**: All tables use **camelCase** keys (`targetRole`, `campaignId`, `skillsFocus`)
- **Thin handler pattern**: Handlers validate input, delegate to service class, return via `success_response`/`error_response` — no business logic in handlers
- **Shared `get_user_id()`**: `from backend.handlers.shared.auth import get_user_id`
- **DynamoDB `query_all()`**: Follows `LastEvaluatedKey` pagination. Use for listings and cascade deletion. `query()` returns only first 1MB page
- **Parallelized queries**: `DashboardService.get_dashboard()` and `resume/service.py` use `ThreadPoolExecutor(max_workers=3)`
- **Mission seeding**: `OnboardingService._seed_first_missions()` calls `generate_daily_mission()` during onboarding
- **Onboarding enriched fields**: Frontend sends `firstName`, `lastName`, `currentRole`, etc. Service builds `name` and `experience` list for backward compat
- **Atomic rate limiting**: Conditional DynamoDB updates — reset date counter, then atomically increment with `< limit` condition. Pattern in `tools.py:337-382` and resume service
- **Mission rate limits**: Coaching agent 3/day (`dailyMissionGenCount`), web endpoint 6/day (`webMissionGenCount`) — separate counters
- **Profile cascade deletion**: 5 DynamoDB tables + 3 S3 buckets + AgentCore Memory + Cognito `AdminDeleteUser`. Order: DynamoDB → S3 → AgentCore → Cognito. Uses `batch_writer()` (25-item batches). S3 uses `list_object_versions` paginator. Env vars: `VOICE_PRACTICE_BUCKET_NAME`, `RESUME_BUCKET_NAME`, `CODE_INTERPRETER_BUCKET_NAME`, `AGENTCORE_MEMORY_ID`, `USER_POOL_ID`
- **Strands Lambda Layer**: Each consuming stack (ApiStack, AgentStack) creates its own inline `LayerVersion` from `infra/layer_build/`. No cross-stack layer reference
- **DynamoDB PITR**: Enabled on 7 data tables. NOT on WebSocketConnections (ephemeral, TTL-based)
- **ConversationThreads**: Full ordered conversation turns per user. `threadId = "active"` for current, ISO timestamp for archived. Working memory complementing AgentCore Memory
- **Thread module**: `backend/handlers/shared/thread.py` — load, append, compact, attention mode. Lazy-initialized module-level table
- **Action events**: Frontend MutationBus events flow via coaching WebSocket as `action_event`. `useAgentEventBridge` handles 5s dedup + 2s batching
- **Attention modes**: `dnd` (silent), `focus` (significant events), `explore` (proactive insights). Stored on thread row
- **Token budget compaction**: ~27k budget. Auto-compacts at 100%. Archives to S3, summary replaces thread + goes to AgentCore Memory
- **Lambda concurrency**: Account limit is 10 (not default 1000). Reserved concurrency NOT set — all Lambdas share unreserved pool
- **Bedrock IAM scoped to models**: `bedrock:InvokeModel*` scoped to `amazon.nova-lite-v1:0` and `amazon.nova-2-sonic-v1:0` ARNs. Resume stack scoped to `nova-lite-v1:0` only
- **Agent tools always use direct @tool functions**: `_get_direct_tools()` from `tools.py`. Gateway tool discovery disabled — Strands layer rejects `ModuleType` tool objects
- **Strands tool introspection**: Use `agent.tool_names` (property). Tools live in `agent.tool_registry` — `agent.tools`/`agent._tools` don't exist
- **AgentCore Gateway wiring**: `agentcore_stack.py` exposes `gateway_id` + `gateway_endpoint`. All three agent Lambdas get `bedrock:InvokeAgent` + `bedrock:InvokeAgentCore` on `gateway/*`. CDK stack order: AgentCoreStack → AgentStack → ApiStack
- **Session tracing**: `SessionTracer` from `instrumentation.py`. `stream_handler.py` uses `connection_id` as session ID. `_flush_spans()` emits JSON `TRACE` logs. Enabled via `REGAIN_TRACING_ENABLED=true`
- **Coaching streaming**: `useStreamingCoaching` hook (WebSocket `VITE_CHAT_WS_URL`). `MarkdownMessage` renders via `react-markdown` + `remark-gfm`. `toolSteps: ToolStep[]` exposed for tool execution visibility. `TOOL_LABELS` map translates tool names
- **Tool execution hooks**: `stream_handler.py` uses Strands `HookProvider`. `BeforeToolCallEvent` sends `{"type": "thinking", "tool": <name>}`, `AfterToolCallEvent` sends `{"type": "thinking_complete", ...}`. Frontend accumulates as `ToolStep` (active → done). First `delta` marks remaining active done. Safety `threading.Timer` fires 10s before Lambda timeout
- **Strands `callback_handler` is text-only**: Only fires for LLM text tokens, NOT tool execution. Use `hooks` parameter with `BeforeToolCallEvent`/`AfterToolCallEvent` for tool lifecycle
- **Voice audio protocol**: Backend expects raw base64 PCM 16-bit mono 16kHz in `event.body` (NOT JSON-wrapped). Backend sends JSON: `{"type": "audio", ...}`, `{"type": "fallback", ...}`, `{"type": "clear_audio", ...}`
- **Shared Nova Sonic client**: `backend/handlers/shared/nova_sonic.py` — async bidirectional via `aws_sdk_bedrock_runtime` SDK (NOT boto3). Module-level daemon thread runs `asyncio.run_forever()`, handlers use `run_coroutine_threadsafe()`. Event protocol: sessionStart → promptStart → contentStart/textInput → contentEnd → contentStart(AUDIO) → audioInput. `tool_specs`/`on_tool_use` default `None`
- **Skill tag normalization**: `log_evidence` normalizes via `taxonomy.normalize_skill()` (e.g. "python" → "Python Programming"). Unknown tags pass through
- **Prescribed skill tags**: `get_system_prompt()` accepts `valid_skill_tags` from user's campaign `skillsFocus`. When present, agent restricted to those tags
- **Day-change detection**: `Missions.tsx` uses `visibilitychange` listener + 60s interval for UTC date rollover
- **Voice practice**: No live tools during sessions — all context pre-fetched into prompt via `_prefetch_context()`. `store_memory()` runs only on disconnect. Eliminates 500ms-2s audio gaps. Assessment generated via Bedrock Nova Lite with structured JSON output
- **AudioVisualizer**: WebGL 3D orb at `components/voice/AudioVisualizer.tsx` — R3F + `three-custom-shader-material` with per-state configs and lerped transitions in `useFrame`
- **Web search (`web_search` @tool)**: Coaching agent calls Tavily AI-search via `backend/handlers/search/service.py` (stdlib `urllib.request`, 8s timeout). SSM SecureString key at `/regain/search/tavily-api-key`. Per-user rate limit 20/day via atomic conditional update on `UserProfiles.dailySearchCount` + `lastSearchDate` (mirrors mission-gen pattern). IAM grant on all three agent Lambdas via `AgentStack._search_ssm_policy()`. Prompt instructs agent to cite results as inline markdown hyperlinks and treat snippets as untrusted

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
| ConversationThreads | `userId` | `threadId` | — |

## Gotchas

### Infrastructure / CDK

- **Agent tool DynamoDB wiring**: When adding a DynamoDB table that coaching agent tools need, update THREE places in `agent_stack.py`: (1) `_table_env()` for env var, (2) `_grant_chat_stream_lambda_permissions()`, (3) `_grant_voice_lambda_permissions()`. The REST API coaching Lambda in ApiStack is separate. Also update `AGENT_ALLOWED_TABLES` in `test_iam_least_privilege.py`
- **Hardcoded test counts**: When adding Lambdas/routes to **ApiStack**, update `EXPECTED_LAMBDA_COUNT` in `test_iam_least_privilege.py`, `test_lambda_env_config.py`, `test_lambda_runtime_consistency.py`, and `EXPECTED_METHOD_COUNT` in `test_api_authorization.py`. When adding tables to **DataStack**, update `EXPECTED_TABLE_COUNT` in `test_on_demand_billing.py` and `test_table_output_completeness.py` (+ `known_tables`). Update `ALLOWED_TABLES` in `test_iam_least_privilege.py` if permissions change
- **CDK cross-stack patterns**: Passing a construct reference from StackB to modify StackA's Lambda creates StackA → StackB dependency and often cycles. Fix: pass plain string ARNs/names (not construct references), use inline `iam.PolicyStatement` instead of `grant_invoke()`/`grant_read()`. For CfnResource cross-stack attrs, use `cfn_resource.get_att("Attr")` (construct method), NOT `cdk.Fn.get_att(logical_id, "Attr")`. For Lambda Layers: create inline `LayerVersion` in each consuming stack — don't share via export (CloudFormation can't update exports that other stacks import). For coaching_lambda (ApiStack) consuming AgentStack resources, use `cdk.Fn.import_value()` to break cycles
- **CDK cross-account deploy guard**: Use `bash scripts/deploy.sh <StackName>` — NOT `npx cdk deploy` directly. The CDK CLI auto-populates `CDK_DEFAULT_ACCOUNT` from whatever credentials it resolves; when the `regain` SSO session expires, CDK silently falls back to the long-lived IAM user in `~/.aws/credentials` (account 205930636302) and deploys there instead. The wrapper strips leaked `AWS_*` env vars, re-runs `aws sso login --profile regain` if needed, and asserts `sts get-caller-identity` returns 563170906428 before invoking CDK. `infra/app.py` now hardcodes `_ACCOUNT = "563170906428"` (no env override) and `tests/unit/infra/test_app_account_pinned.py` enforces that via AST check
- **`infra/layer_build/`** is gitignored — rebuild via `bash infra/build_layer.sh` before `cdk deploy`
- **API Gateway CORS**: `default_cors_preflight_options` only handles OPTIONS and only covers L2 resources. Add `GatewayResponse` for `DEFAULT_4_XX`/`DEFAULT_5_XX` with CORS headers. L1 `CfnResource` routes (ResumeStack, VoicePracticeStack — used to avoid cyclic deps) need manual MOCK OPTIONS methods
- **S3 versioned bucket deletion**: `delete_objects` without `VersionId` only creates delete markers — actual object versions persist indefinitely. Use `list_object_versions` paginator (returns `Versions` + `DeleteMarkers` with `VersionId`). Works on non-versioned buckets too (`VersionId` is `"null"`)

### WebSocket Lambdas

- **Separate `WebSocketLambdaIntegration` instances per route**: When shared across `connect`/`default`/`disconnect` route options, CDK only adds `lambda:InvokeFunction` permission for the first (`$connect`). API Gateway silently drops messages for others
- **No instance affinity**: `$connect`, `$default`, `$disconnect` can each hit different Lambda containers. Module-level Python dicts NOT shared. Persist connection metadata in `WebSocketConnections` table on `$connect`, load on `$default`/`$disconnect`. Shared module: `backend/handlers/shared/ws_connections.py`. In-memory `_sessions` (live Nova Sonic streams) are module-level — created on first `$default`
- **`execute-api:ManageConnections` IAM**: Lambdas calling `post_to_connection()` require explicit policy for `execute-api:ManageConnections` on `arn:aws:execute-api:{region}:{account}:{apiId}/prod/POST/@connections/*`. CDK does NOT grant this automatically

### Voice / Nova Sonic

- **Model**: `amazon.nova-2-sonic-v1:0`. Input: 16kHz PCM mono. Output: 24kHz PCM mono
- **Use ScriptProcessorNode, not AudioWorklet** — AudioWorklet fails silently in production. Deprecation warning is harmless. Reference: `~/Desktop/altivum/elo/src/hooks/useAudioCapture.ts`
- **Continuous buffer playback, not scheduled AudioBufferSource** — individual `.start(time)` causes audible gaps. Use single ScriptProcessorNode with growing Float32Array (read/write indices). Reference: `~/Desktop/altivum/elo/src/hooks/useAudioPlayback.ts`
- **Feedback prevention**: Auto-mute mic (`track.enabled = false`) when AI speaking. Send silence frames to keep stream alive. Unmute when `isAgentSpeaking` false
- **Mic unmute**: Use server-side `END_TURN` state signal (triggers `on_state("listening")`), NOT frontend speaking timer
- **Endpointing**: Leave `turnDetectionConfiguration` unset. `endpointingSensitivity: "HIGH"` causes aggressive user cut-offs
- **`inputSchema.json` must be a JSON string**: `toolSpec.inputSchema.json = json.dumps({...})`, NOT nested dict
- **`toolConfiguration` does NOT support `toolChoice`** — only `tools` is valid
- **SPECULATIVE text IS the assistant transcript**: `contentStart` with `generationStage == "SPECULATIVE"` for ASSISTANT role is the spoken text preview — don't filter it out
- **Transcript streaming — accumulate, don't append**: Nova Sonic sends text chunks incrementally. Accumulate consecutive same-role chunks into single `TranscriptEntry` (check `last.role === role`, append text)
- **`aws_sdk_bedrock_runtime` auth config**: Must include `auth_scheme_resolver=HTTPAuthSchemeResolver()`, `auth_schemes={"aws.auth#sigv4": SigV4AuthScheme(service="bedrock")}`, `aws_credentials_identity_resolver=EnvironmentCredentialsResolver()`
- **Pre-fetch context, don't use live tools during sessions**: Synchronous tool execution causes 500ms-2s audio gaps. Voice prompts enforce "2-3 sentences maximum"

### React / Frontend

- Tailwind v4 uses `@theme` in CSS, not `theme.extend` in config — tokens must go in `index.css`
- React 19: `JSX.Element` namespace requires explicit import (`ReactNode` from 'react' instead)
- **Vite 8 uses `build.rolldownOptions` not `build.rollupOptions`** (deprecated). `manualChunks` must be a function, match by `id.includes('node_modules/<pkg>/')`
- **`react-refresh/only-export-components`**: When `.tsx` exports both a `createContext()` value and a Provider, use `export { X }` (re-export) NOT `export const X = createContext(...)` (inline)
- **React 19 `react-hooks/refs`**: Don't use `useRef` to cache a value read during render. Use `useState(() => loadDraft())` lazy initializer instead
- **`useBlocker` (React Router v7.13)**: Only blocks React Router navigation, NOT in-component state changes. `isDirty` predicate must cover all form steps
- **`three-custom-shader-material` v6 + R3F**: Don't use the `vanilla` import with `extend()`. Use default React import — v6 constructor destructures first arg, R3F calls with no args
- **CSM fragment shader `normal`**: Three.js declares `vec3 normal` in built-in fragment. Use different name (e.g. `nW`) to avoid redefinition error
- **Font files**: Must be in `public/fonts/` for Vite to serve with preload

### Auth / API / Model

- **Cognito authorizer** expects **idToken** (not accessToken) when no OAuth scopes configured
- **DynamoDB composite keys**: `get_item`/`update_item` on Campaigns requires `{userId, campaignId}`, MissionHistory requires `{userId, missionId}` — moto mocks dispatch by table name only, so key bugs invisible in tests
- **Nova Lite model ID**: `amazon.nova-lite-v1:0` (NOT `us.amazon.nova-lite-v2:0` which doesn't exist)
- **PyYAML NOT available in Lambda Python 3.12** — use inline string parsing
- **LLM hallucinating tool success on error**: Tools returning `{"error": ...}` can still be narrated as success by Nova Lite/Pro. Silent failures (missing env var → ValueError → caught → error dict) are especially dangerous
- **Tavily SSM key provisioning**: Before first deploy of the web-search feature, stash the Tavily key once: `aws ssm put-parameter --profile regain --region us-east-1 --name /regain/search/tavily-api-key --type SecureString --value "tvly-..." --description "Tavily web search API key"`. CDK only grants read access — the parameter itself must exist or the coaching agent's `web_search` tool will raise on first invocation

### Deployment / Hosting

- **Hosting**: AWS Amplify in **us-east-2** (app ID: `d2z52fw5cbbzo`, domain: regain.altivum.ai) — auto-deploys from `git push` to main
- **Amplify env vars** resolve at build **start**. After updating, trigger fresh rebuild: `aws amplify start-job --job-type RELEASE --branch-name main --app-id d2z52fw5cbbzo`
- **Amplify `update-app --environment-variables` REPLACES all vars** (not merge). Read current via `aws amplify get-app --query 'app.environmentVariables'`, then include all in update
- **`VITE_VOICE_PRACTICE_WS_URL`** must be set in Amplify after deploying `RegainVoicePracticeStack`
- **`main` branch protected**: 3 required status checks (backend + frontend + infra CI). Must use feature branch + PR. Squash merge creates divergent local history — use `git pull --rebase` after merge
