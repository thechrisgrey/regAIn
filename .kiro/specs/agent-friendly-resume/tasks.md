# Implementation Plan: Agent-Friendly Resume

## Overview

Implement the Agent-Friendly Resume feature in dependency order: CDK infrastructure first, then backend service logic, async triggers, API endpoints, coaching agent tools, and finally the frontend. Each task builds on the previous, ensuring no orphaned code.

## Tasks

- [x] 1. Set up Resume Stack CDK infrastructure
  - [x] 1.1 Create `infra/stacks/resume_stack.py` with ResumeStack class
    - S3 bucket with versioning enabled and all public access blocked
    - Resume Generation Lambda (Python 3.12 runtime) with environment variables for all 5 DynamoDB table names, bucket name, and Bedrock model ID
    - IAM policy: read on UserProfiles, Campaigns, MissionHistory, EvidenceVault, MarketData tables; read/write on Resume bucket; bedrock:InvokeModel for Nova Lite
    - Add GET /resume and POST /resume/generate routes to existing API Gateway with Cognito authorizer (cross-stack reference via Fn.importValue)
    - CfnOutputs for bucket name, bucket ARN, and Lambda ARN
    - Tag all resources with Project=REGAIN, Environment=dev
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6_

  - [x] 1.2 Register ResumeStack in `infra/app.py`
    - Import and instantiate ResumeStack with dependencies on DataStack, ApiStack, AuthStack
    - _Requirements: 10.4_

  - [x] 1.3 Write CDK assertion tests for ResumeStack
    - Create `tests/unit/test_resume_stack.py`
    - Assert S3 bucket has versioning enabled (Req 4.4)
    - Assert S3 bucket blocks public access (Req 4.5)
    - Assert Lambda has read permissions on all 5 DynamoDB tables (Req 10.2, 10.6)
    - Assert Lambda has write permissions on Resume bucket (Req 10.2)
    - Assert Lambda has bedrock:InvokeModel permission (Req 10.2)
    - Assert API Gateway routes exist with Cognito authorization (Req 10.3, 8.6)
    - Assert all resources tagged with Project=REGAIN, Environment=dev (Req 10.5)
    - _Requirements: 4.4, 4.5, 10.2, 10.3, 10.5, 10.6, 8.6_

- [x] 2. Checkpoint — Ensure CDK stack synthesizes and tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Implement Resume Generation Lambda backend
  - [x] 3.1 Create shared data models in `backend/lambda/shared/resume_models.py`
    - Define `ResumeData` dataclass (profile, campaign, completed_missions, evidence_entries, market_alignment)
    - Define `ResumeResult` dataclass (content, s3_key, version, generated_at, presigned_url)
    - Define frontmatter field types and skill object structure
    - _Requirements: 1.2, 1.3_

  - [x] 3.2 Implement `backend/lambda/resume/service.py` — ResumeService class
    - `_gather_data(user_id)`: parallel DynamoDB reads from all 5 tables using ThreadPoolExecutor; return error naming specific table on failure; return error if zero completed missions
    - `_synthesize(data)`: construct Nova Lite prompt from ResumeData, invoke Bedrock, validate output has correct YAML frontmatter and 5 markdown sections, retry once on validation failure
    - `_store(user_id, content)`: write timestamped copy to `{userId}/resume/resume-{timestamp}.md`, overwrite `{userId}/resume/latest.md`, update UserProfiles with lastResumeGeneratedAt, resumeS3Key, incremented resumeVersion
    - `generate_resume(user_id)`: orchestrate gather → synthesize → store, return ResumeResult with presigned URL (1-hour expiry)
    - `get_resume(user_id)`: read pointer from UserProfiles, fetch content from S3, generate presigned URL, return metadata; return "no resume" message if no existing resume
    - `_check_rate_limit(user_id)`: query dailyResumeGenCount and dailyResumeGenDate from UserProfiles, enforce 3-per-day limit, reset count on new day
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 3.1, 3.2, 3.3, 3.4, 3.5, 4.1, 4.2, 4.3, 8.4, 11.1, 11.4, 11.5_

  - [x] 3.3 Implement `backend/lambda/resume/handler.py` — thin Lambda handler
    - Route by event shape: API Gateway GET → get_resume, API Gateway POST → check rate limit then generate_resume, async event → generate_resume
    - Validate input, delegate to ResumeService, return formatted response
    - Return appropriate HTTP status codes (200, 400, 404, 429, 500, 502)
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [x] 3.4 Write property tests for resume generation
    - Create `tests/unit/test_resume_properties.py` using Hypothesis
    - **Property 1: Resume document structure validity** — Generate random valid ResumeData, call _synthesize with mocked Bedrock, validate YAML frontmatter has all required fields with correct types, validate 5 markdown sections in order
    - **Validates: Requirements 1.1, 1.2, 1.3, 1.5, 11.2, 11.3**

  - [x] 3.5 Write property test for YAML round-trip
    - **Property 2: YAML frontmatter round-trip** — Generate random YAML-safe dicts matching frontmatter schema, round-trip through yaml.safe_load/yaml.safe_dump/yaml.safe_load, assert equivalence
    - **Validates: Requirements 1.6**

  - [x] 3.6 Write property test for sensitive data exclusion
    - **Property 3: Output excludes sensitive data** — Generate random profiles with PII fields (email, phone, address, UUIDs), verify none leak into resume output
    - **Validates: Requirements 1.4, 11.4**

  - [x] 3.7 Write property test for professional summary sentence count
    - **Property 4: Professional summary sentence count** — Validate Professional Summary section contains 2-3 sentences
    - **Validates: Requirements 2.1**

  - [x] 3.8 Write property test for mission highlights count
    - **Property 5: Mission highlights count invariant** — Generate varying numbers of missions, verify 5-8 highlights for 8+ missions, all missions for fewer
    - **Validates: Requirements 2.3**

  - [x] 3.9 Write property test for top accomplishments count
    - **Property 6: Top accomplishments count invariant** — Generate varying evidence, verify 3-5 accomplishments in frontmatter
    - **Validates: Requirements 2.4**

  - [x] 3.10 Write property test for proficiency indicator determinism
    - **Property 7: Proficiency indicator derived from evidence depth** — Generate random evidence counts, verify same input always produces same proficiency indicator
    - **Validates: Requirements 2.5**

  - [x] 3.11 Write property test for table failure error specificity
    - **Property 8: Table failure produces specific error** — Simulate each of 5 table failures, verify error names the specific table and no partial resume is produced
    - **Validates: Requirements 3.4**

  - [x] 3.12 Write property test for storage completeness
    - **Property 9: Storage produces both files with metadata update** — Mock S3 and DynamoDB, verify timestamped copy stored, latest.md overwritten, and UserProfiles metadata updated
    - **Validates: Requirements 4.1, 4.2, 4.3**

  - [x] 3.13 Write property test for rate limit enforcement
    - **Property 11: Rate limit enforced at 3 per day** — Simulate sequential generation requests, verify 4th returns 429
    - **Validates: Requirements 8.4, 8.5**

  - [x] 3.14 Write unit tests for ResumeService
    - Create `tests/unit/test_resume_service.py` using pytest + moto
    - Test data gathering reads all 5 tables (mocked with moto)
    - Test parallel execution of DynamoDB queries (verify ThreadPoolExecutor usage)
    - Test zero missions returns appropriate error (Req 3.5)
    - Test get_resume for user with no resume returns "no resume" message (Req 7.4)
    - Test presigned URL generated with 1-hour expiry (Req 11.5)
    - _Requirements: 3.1, 3.2, 3.4, 3.5, 7.4, 11.5_

- [x] 4. Checkpoint — Ensure backend service tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement async triggers for mission completion and phase advancement
  - [x] 5.1 Add async resume trigger to `complete_mission` in `backend/agents/coaching/tools.py`
    - After successful mission completion, invoke Resume Lambda with `InvocationType='Event'` and payload `{"user_id": user_id, "trigger": "mission_completion"}`
    - Wrap in try/except — log failure, never block mission completion
    - Use `RESUME_LAMBDA_ARN` environment variable
    - _Requirements: 5.1, 5.2, 5.3_

  - [x] 5.2 Add async resume trigger to phase advancement path
    - In the phase advancement code path, invoke Resume Lambda with `InvocationType='Event'` and payload `{"user_id": user_id, "trigger": "phase_advancement"}`
    - Wrap in try/except — log failure, never block phase advancement
    - Only trigger on Foundation→Expansion and Expansion→Launch transitions, not on other events
    - _Requirements: 6.1, 6.3_

  - [x] 5.3 Write property test for phase advancement trigger
    - **Property 10: Phase advancement updates campaign phase** — Generate phase transitions, verify frontmatter campaign_phase matches new post-transition phase
    - **Validates: Requirements 6.2**

  - [x] 5.4 Write unit test for async trigger non-blocking behavior
    - Test that Lambda.invoke failure in complete_mission does not raise an exception
    - Test that mission completion succeeds even when resume generation invocation fails
    - _Requirements: 5.3_

- [x] 6. Implement coaching agent resume tools
  - [x] 6.1 Add `generate_resume` and `get_resume` tools to `backend/agents/coaching/tools.py`
    - `generate_resume`: invoke Resume Lambda synchronously (RequestResponse), return presigned URL, version, and generated_at timestamp
    - `get_resume`: read UserProfiles pointer, fetch content from S3, return markdown content + metadata (version, generated_at, presigned URL); return "no resume" message if none exists
    - Follow existing @tool decorator pattern with precise docstrings
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [x] 6.2 Write property test for API and tool response shape
    - **Property 12: API and tool responses contain required fields** — Verify responses from generate_resume and get_resume contain content, generatedAt, version, and downloadUrl
    - **Validates: Requirements 7.3, 8.1, 8.3**

- [-] 7. Checkpoint — Ensure backend integration tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. Implement frontend Resume feature
  - [ ] 8.1 Add Resume types to `frontend/src/types/`
    - Define `ResumeResponse` interface (content, generatedAt, version, downloadUrl, frontmatter)
    - Define `ResumeFrontmatter` interface (schema_version, name, target_role, skills array, campaign_phase, etc.)
    - Define `ResumeSkill` interface (skill_name, evidence_count, strongest_evidence_summary, proficiency_indicator)
    - _Requirements: 1.2, 1.3, 8.1_

  - [ ] 8.2 Extend API client in `frontend/src/services/api.ts`
    - Add `resume.get(token)` → GET /resume
    - Add `resume.generate(token)` → POST /resume/generate
    - _Requirements: 8.1, 8.3_

  - [ ] 8.3 Create `frontend/src/hooks/useResume.ts` custom hook
    - State: resume data, loading, regenerating, error
    - `fetchResume()`: call GET /resume, handle 404 as empty state
    - `regenerateResume()`: call POST /resume/generate, handle 429 with rate limit message, update state on success
    - Follow the existing `useEvidence` hook pattern
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 9.8, 9.9_

  - [ ] 8.4 Create `frontend/src/pages/ResumePage.tsx`
    - Render frontmatter fields as structured metadata above the markdown body (not raw YAML)
    - Render markdown body using existing `MarkdownMessage` component
    - "Download .md" button using presigned URL
    - "Regenerate" button calling POST /resume/generate, disabled during regeneration with progress indicator
    - Version indicator: "Version N — Generated X hours ago"
    - Empty state: message indicating first mission completion required
    - Loading indicator while fetching resume data
    - _Requirements: 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 9.9_

  - [ ] 8.5 Update navigation in `frontend/src/components/Layout.tsx`
    - Add Resume nav item between Evidence and Profile
    - Add route for /resume pointing to ResumePage
    - _Requirements: 9.1_

  - [ ] 8.6 Write frontend unit tests
    - Test navigation includes Resume between Evidence and Profile (Req 9.1)
    - Test Resume page renders frontmatter as structured metadata (Req 9.3)
    - Test Download button present (Req 9.4)
    - Test Regenerate button present and calls POST endpoint (Req 9.5)
    - Test version indicator displays correctly (Req 9.6)
    - Test empty state message shown when no resume (Req 9.7)
    - Test loading indicator shown during fetch (Req 9.8)
    - Test Regenerate button disabled during regeneration (Req 9.9)
    - _Requirements: 9.1, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 9.9_

  - [ ] 8.7 Write frontend property test for response shape
    - Create `frontend/src/hooks/useResume.pbt.test.ts` using fast-check
    - **Property 12 (frontend): API response contains required fields** — Generate random API response shapes, verify hook exposes content, generatedAt, version, downloadUrl
    - **Validates: Requirements 8.1, 8.3**

- [ ] 9. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- The implementation follows dependency order: infrastructure → backend service → triggers → tools → frontend
