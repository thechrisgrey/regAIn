# Implementation Plan: Coaching Agent

## Overview

Implements the REGAIN Coaching Agent as a Strands Agents SDK-based conversational AI system. Tasks are ordered by dependency: shared utilities first, then Strands tools, then agent configuration, then Lambda integration, then voice support, then frontend wiring. Each task builds on the previous and ends with wiring into the existing platform.

## Tasks

- [x] 1. Implement Strands tools for DynamoDB operations
  - [x] 1.1 Create `backend/agents/coaching/tools.py` with `read_user_profile` and `update_user_profile` tools
    - Use @tool decorator from strands
    - Import and use `DynamoDBClient` from `backend/lambda/shared/dynamodb.py`
    - `read_user_profile(user_id: str) -> dict`: get item from user_profiles table, return profile dict or error dict
    - `update_user_profile(user_id: str, updates: dict) -> dict`: update item in user_profiles table, return updated profile
    - Tool docstrings must precisely describe what each tool does for the LLM
    - Return structured dicts, never free text
    - _Requirements: 1.4, 9.4_

  - [x] 1.2 Add `get_campaign_status` and `create_campaign` tools to `tools.py`
    - `get_campaign_status(user_id: str) -> dict`: query campaigns table for active campaign, return campaign dict
    - `create_campaign(user_id: str, title: str, target_role: str, skills_focus: list) -> dict`: create campaign with phase="foundation", status="active", return dict with campaign_id
    - Generate campaign_id with uuid4
    - _Requirements: 2.1, 2.2_

  - [x] 1.3 Add `get_current_mission` and `generate_mission` tools to `tools.py`
    - `get_current_mission(user_id: str) -> dict`: query mission_history for pending/in_progress missions, include pattern analysis via `_analyze_patterns` helper
    - `generate_mission(user_id: str, campaign_id: str, title: str, description: str, skill_tag: str) -> dict`: write mission with status="pending", return dict with mission_id
    - Generate mission_id with uuid4
    - _Requirements: 2.3, 7.2, 7.3_

  - [x] 1.4 Add `complete_mission` and `log_evidence` tools to `tools.py`
    - `complete_mission(user_id: str, mission_id: str, reflection: str, skill_tag: str, artifact_url: str = "") -> dict`: update mission status to "completed", create evidence record, return dict with evidence_id
    - `log_evidence(user_id: str, mission_id: str, skill_tag: str, reflection: str, artifact_url: str = "") -> dict`: write evidence to evidence_vault, count existing evidence for skill_tag, return dict with evidence_id and skill_evidence_count
    - _Requirements: 5.2, 5.3, 5.4_

  - [x] 1.5 Add `get_evidence_summary` and `get_market_insights` tools to `tools.py`
    - `get_evidence_summary(user_id: str) -> dict`: query evidence_vault, aggregate by skill_tag, return dict with skill counts and recent evidence list
    - `get_market_insights(sector: str) -> dict`: query market_data table by sector, return latest entry with job_trends, skill_demand, salary_ranges
    - _Requirements: 6.1_

  - [x] 1.6 Implement `_analyze_patterns` helper function in `tools.py`
    - Pure function: takes list of mission dicts, returns PatternAnalysis dict
    - Count completions/skips by skill_tag category
    - Flag categories with >50% skip rate as avoidance_signals
    - Flag categories with 0% skip rate and >=1 completion as strength_signals
    - _Requirements: 4.1_

- [x] 2. Checkpoint — Verify all Strands tools
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Implement AgentCore Memory tools
  - [x] 3.1 Add `recall_memory` and `store_memory` tools to `tools.py`
    - `recall_memory(user_id: str, query: str) -> list[dict]`: call AgentCore Memory API with namespace `regain-coaching-{user_id}`, semantic + recency search, return list of memory entries
    - `store_memory(user_id: str, content: str) -> dict`: store content in AgentCore Memory with user namespace, return confirmation dict
    - Use boto3 bedrock-agent-runtime client for AgentCore Memory API calls
    - Handle service unavailability gracefully — return empty results on failure
    - _Requirements: 3.5, 9.5, 10.2, 10.3_

  - [x] 3.2 Write property tests for memory namespace isolation
    - **Property 8: Memory namespace isolation**
    - **Validates: Requirements 9.5, 10.3**

- [x] 4. Implement agent configuration and system prompt
  - [x] 4.1 Create `backend/agents/coaching/prompts.py` with `get_system_prompt()` function
    - Define agent persona: experienced career transition coach
    - Define coaching philosophy: evidence over affirmation, structure that adapts
    - Define session type handling: onboarding, checkin, general
    - Define behavioral rules: always read profile first, detect avoidance, reference evidence, never give generic advice
    - Define tool usage guidelines: when to call each tool
    - Return prompt as string
    - _Requirements: 9.3_

  - [x] 4.2 Create `backend/agents/coaching/agent.py` with `create_coaching_agent()` function
    - Import Agent from strands, BedrockModel from strands.models.bedrock
    - Configure model_id from `BEDROCK_MODEL_ID` env var, default to `amazon.nova-lite-v1:0`
    - Configure region from `AWS_REGION` env var, default to `us-east-1`
    - Register all 12 tools from tools.py
    - Load system prompt from prompts.py
    - Return configured Agent instance
    - _Requirements: 9.1, 9.2_

  - [x] 4.3 Create `backend/agents/coaching/requirements.txt`
    - Add `strands-agents` and `strands-agents-tools` dependencies
    - Add `boto3` dependency
    - _Requirements: 9.1_

- [x] 5. Checkpoint — Verify agent configuration
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Update coaching Lambda to use Strands Agent
  - [x] 6.1 Update `backend/lambda/coaching/service.py` to invoke the Strands Agent
    - Replace placeholder response with Strands Agent invocation
    - Accept session_type parameter (onboarding, checkin, general)
    - Instantiate agent via `create_coaching_agent(user_id)`
    - Pass formatted message to agent with session_type and user_id context
    - Return agent response as structured dict
    - _Requirements: 1.1, 3.1_

  - [x] 6.2 Update `backend/lambda/coaching/handler.py` to pass session_type
    - Extract session_type from request body (default: "checkin")
    - Pass session_type to service.checkin()
    - _Requirements: 3.1_

  - [x] 6.3 Write property tests for Strands tools
    - [x] 6.3.1 Write property test for profile update round trip
      - **Property 1: Profile update round trip**
      - **Validates: Requirements 1.4**
    - [x] 6.3.2 Write property test for skill taxonomy partitioning
      - **Property 2: Skill taxonomy partitioning**
      - **Validates: Requirements 1.2**
    - [x] 6.3.3 Write property test for campaign creation round trip
      - **Property 3: Campaign creation round trip**
      - **Validates: Requirements 2.1, 2.2**
    - [x] 6.3.4 Write property test for mission generation round trip and structure
      - **Property 4: Mission generation round trip and structure**
      - **Validates: Requirements 2.3, 7.2, 7.3**
    - [x] 6.3.5 Write property test for mission skill alignment
      - **Property 5: Mission skill alignment**
      - **Validates: Requirements 2.4**
    - [x] 6.3.6 Write property test for evidence logging round trip with count accuracy
      - **Property 6: Evidence logging round trip with count accuracy**
      - **Validates: Requirements 5.2, 5.3, 5.4**
    - [x] 6.3.7 Write property test for behavioral pattern detection accuracy
      - **Property 9: Behavioral pattern detection accuracy**
      - **Validates: Requirements 4.1**

- [x] 7. Checkpoint — Verify coaching Lambda integration
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Implement voice session support
  - [x] 8.1 Create `backend/lambda/coaching/voice_handler.py` for WebSocket API Gateway
    - Implement `$connect` handler: extract Cognito token from query string, validate, store connection_id → user_id mapping in DynamoDB or in-memory
    - Implement `$default` handler: receive audio frames, forward to Nova Sonic session
    - Implement `$disconnect` handler: close Nova Sonic session, store session summary via `store_memory` tool
    - Use boto3 bedrock-runtime client for `InvokeModelWithBidirectionalStream` with model `amazon.nova-sonic-v1:0`
    - Configure audio format: PCM 16-bit, 16kHz
    - Register Strands tools for async invocation during voice session
    - Handle Nova Sonic session creation failure with text fallback response
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [x] 8.2 Write unit tests for voice handler
    - Test $connect authentication success and failure
    - Test $disconnect cleanup
    - Test Nova Sonic fallback on session creation failure
    - _Requirements: 8.1, 8.5_

- [x] 9. Add CDK infrastructure for coaching agent
  - [x] 9.1 Create `infra/stacks/agent_stack.py` with AgentStack
    - Define WebSocket API Gateway for voice sessions
    - Create voice session Lambda function with Bedrock permissions
    - Update existing Coaching Lambda with Bedrock invoke permissions and all DynamoDB table read/write grants
    - Add environment variables: BEDROCK_MODEL_ID, NOVA_SONIC_MODEL_ID, AGENTCORE_MEMORY_NAMESPACE_PREFIX
    - Add all DynamoDB table name env vars (already done for some in ApiStack, extend for full access)
    - Tag all resources with Project=REGAIN, Environment=dev
    - _Requirements: 8.1, 9.1, 9.2_

  - [x] 9.2 Update `infra/app.py` to include AgentStack
    - Import and instantiate AgentStack
    - Pass required cross-stack references (tables, user_pool)
    - _Requirements: 9.1_

- [x] 10. Checkpoint — Verify infrastructure and voice support
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. Wire frontend coaching interface
  - [x] 11.1 Create `frontend/src/hooks/useCoaching.ts` custom hook
    - Implement `sendMessage(message: string, sessionType: string)` function that calls POST /coaching/checkin
    - Manage loading, error, and response state
    - Use existing API service layer for authenticated requests
    - _Requirements: 3.1_

  - [x] 11.2 Create `frontend/src/hooks/useVoiceSession.ts` custom hook
    - Manage WebSocket connection lifecycle to voice API Gateway endpoint
    - Handle audio capture via Web Audio API (PCM 16-bit, 16kHz)
    - Stream audio to/from WebSocket
    - Handle connection errors with fallback to text mode
    - Expose `startSession()`, `stopSession()`, `isActive` state
    - _Requirements: 8.1, 8.2, 8.5_

  - [x] 11.3 Create `frontend/src/pages/CoachingPage.tsx`
    - Text input with send button for text-mode coaching
    - Voice button that toggles voice session via useVoiceSession hook
    - Message history display showing agent responses
    - Session type selector (onboarding, check-in, general)
    - Use Tailwind CSS for styling
    - Use useCoaching hook for text interactions
    - _Requirements: 3.1, 8.1_

  - [x] 11.4 Add coaching route to React Router in `frontend/src/App.tsx`
    - Add `/coaching` route pointing to CoachingPage
    - Protect route with auth context
    - _Requirements: 3.1_

- [x] 12. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties using Hypothesis
- Unit tests validate specific examples and edge cases using pytest + moto
- All Strands tools use the existing DynamoDBClient — no new data access patterns
- No new DynamoDB tables are created — all operations use existing tables from platform-foundation spec
