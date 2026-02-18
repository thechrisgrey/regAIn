# Implementation Plan: Market Intelligence System

## Overview

Build the market intelligence data pipeline and analysis engine as importable Python modules at `backend/lambda/market_intel/`. Implementation follows dependency order: data models → skill taxonomy → scoring → alignment → insights → ingestion pipeline → seed data → CDK infrastructure → integration wiring.

## Tasks

- [x] 1. Create market intelligence module structure and data models
  - [x] 1.1 Create `backend/lambda/market_intel/` package with `__init__.py`, `models.py`
    - Define dataclasses: `MarketDataRecord`, `CanonicalSkill`, `AlignmentResult`, `MarketInsight`
    - `MarketDataRecord`: sector, timestamp, role_title, category, demand_score, growth_rate, trend_direction, top_skills, salary_range, posting_volume, projection, source, insights
    - `AlignmentResult`: alignment_pct, skill_breakdown, top_gaps, top_strengths, target_role_id, user_id, calculated_at
    - `MarketInsight`: type, role_id, message_template, data_payload, generated_date, shown, user_id
    - Include `to_dynamodb_item()` and `from_dynamodb_item()` methods on `MarketDataRecord`
    - _Requirements: 5.1, 5.5, 6.4, 7.1_

- [x] 2. Implement skill taxonomy module
  - [x] 2.1 Create `backend/lambda/market_intel/taxonomy.py`
    - Define `TAXONOMY` dict of ~200 `CanonicalSkill` entries across 5 categories (Technical, Analytical, Communication, Leadership, Domain_Specific)
    - Build `ALIAS_INDEX` reverse-lookup dict at module load time (lowercase alias → canonical name)
    - Implement `normalize_skill(skill_string: str) -> str | None` — case-insensitive alias lookup, returns None for unmatched
    - Implement `serialize_taxonomy() -> str` and `deserialize_taxonomy(json_str: str) -> dict` for JSON round-trip
    - Implement `get_canonical_skill(name: str) -> CanonicalSkill | None`
    - Focus on skills relevant to the 5 seed transition paths; fill remaining categories with common career skills
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

  - [x] 2.2 Write property tests for skill taxonomy
    - **Property 4: Taxonomy alias completeness** — For any CanonicalSkill, onet_codes, job_posting_aliases, and user_aliases are non-empty
    - **Property 5: Taxonomy normalization and round-trip** — For any alias in the taxonomy, normalize returns correct canonical name; serialize then deserialize preserves all lookups
    - **Property 6: Taxonomy unmatched skills return None** — For any string not in ALIAS_INDEX, normalize_skill returns None
    - **Validates: Requirements 4.2, 4.3, 4.4, 4.6**

- [x] 3. Implement demand score calculation
  - [x] 3.1 Create `backend/lambda/market_intel/scoring.py`
    - Implement `calculate_demand_score(posting_volume, growth_rate, median_salary, projection, all_posting_volumes, all_median_salaries) -> dict`
    - Returns dict with demand_score (int 0-100), components breakdown, trend_direction, sorted top_skills, salary_range
    - Implement `_percentile_rank(value, all_values) -> float` helper
    - Implement `_growth_rate_score(growth_rate) -> int` — maps to 0/10/20/30
    - Implement `_projection_score(projection) -> int` — maps BLS categories to 0/5/15/20/25
    - Implement `get_trend_direction(growth_rate) -> str` — maps to surging/growing/stable/declining
    - Implement `recalculate_scores(role_ids: list[str]) -> dict` — reads from DynamoDB, recalculates, writes back
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [x] 3.2 Write property tests for demand scoring
    - **Property 7: Demand score invariants** — For any valid inputs: score in [0,100], components in their ranges, components sum to score, trend_direction matches growth_rate, top_skills sorted by frequency desc, salary min ≤ median ≤ max
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5**

- [x] 4. Implement alignment calculation
  - [x] 4.1 Create `backend/lambda/market_intel/alignment.py`
    - Implement `compute_evidence_strength(has_skill: bool, evidence_count: int, has_recent_evidence: bool) -> float` — returns 0.0/0.3/0.6/0.9/1.0
    - Implement `calculate_alignment(user_id: str, target_role_id: str) -> AlignmentResult`
    - Reads user skills from UserProfiles, evidence from EvidenceVault, role requirements from MarketData via DynamoDBClient
    - Normalizes all skills through taxonomy before comparison
    - Computes weighted average alignment, per-skill breakdown, top 3 gaps, top 3 strengths
    - Returns AlignmentResult with 0.0% alignment and empty breakdown if role has no data
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 10.5_

  - [x] 4.2 Write property tests for alignment calculation
    - **Property 8: Evidence strength mapping** — For any (has_skill, evidence_count, has_recent_evidence) combination, score matches the specified mapping
    - **Property 9: Alignment calculation invariants** — For any user skills/evidence and target role skills: alignment_pct in [0,100], breakdown covers all target skills, gaps sorted by market_weight×(1-user_score) desc, strengths sorted by market_weight×user_score desc
    - **Property 12: Missing role returns error indicator** — For any role_id not in data, returns 0.0% alignment without exception
    - **Validates: Requirements 6.2, 6.3, 6.4, 6.5, 10.5**

- [x] 5. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement insight generation
  - [x] 6.1 Create `backend/lambda/market_intel/insights.py`
    - Define `INSIGHT_TEMPLATES` dict with message templates for all 5 insight types
    - Implement `generate_role_trend_insight(record: MarketDataRecord) -> MarketInsight`
    - Implement `generate_alignment_insight(alignment: AlignmentResult, role_title: str) -> MarketInsight`
    - Implement `generate_gap_opportunity_insight(skill_name: str, frequency: float, evidence_count: int, role_id: str, role_title: str) -> MarketInsight`
    - Implement `generate_emerging_role_insight(record: MarketDataRecord, alignment_pct: float) -> MarketInsight`
    - Implement `generate_milestone_insight(previous: AlignmentResult, current: AlignmentResult, role_title: str) -> MarketInsight`
    - Implement `get_insights(role_id: str | None, user_id: str | None, insight_type: str | None) -> list[dict]` — queries from DynamoDB
    - All template placeholders must have corresponding keys in data_payload
    - _Requirements: 7.1, 7.2, 7.4, 7.5, 7.6_

  - [x] 6.2 Write property tests for insight generation
    - **Property 10: Insight structure validity** — For any generated insight: all required fields present, type is one of 5 valid types, all template placeholders have matching data_payload keys
    - **Property 11: Milestone delta correctness** — For any two AlignmentResults, milestone insight correctly reports previous_pct, current_pct, and skills_improved
    - **Validates: Requirements 7.1, 7.5**

- [x] 7. Implement ingestion pipeline
  - [x] 7.1 Create `backend/lambda/market_intel/ingestion/retry.py`
    - Implement `retry_with_backoff(fn, max_retries=3, base_delay=1.0)` — exponential backoff at 1s/2s/4s
    - Catches exceptions, logs each retry attempt, re-raises after exhausting retries
    - _Requirements: 1.5, 2.4, 3.4_

  - [x] 7.2 Create `backend/lambda/market_intel/ingestion/onet.py`
    - Implement `ingest(role_ids: list[str]) -> dict` — fetches from O*NET API, transforms to MarketDataRecord, writes to DynamoDB
    - Uses `retry_with_backoff` for each API call
    - Catches per-role failures, continues processing remaining roles
    - Returns `{"succeeded": [...], "failed": [...]}`
    - API key from `ONET_API_KEY` environment variable
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

  - [x] 7.3 Create `backend/lambda/market_intel/ingestion/bls.py`
    - Implement `ingest(series_ids: list[str]) -> dict` — fetches from BLS Public Data API v1, transforms, merges into DynamoDB
    - Uses `retry_with_backoff` for each API call
    - Catches per-series failures, continues processing remaining series
    - Returns `{"succeeded": [...], "failed": [...]}`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [x] 7.4 Create `backend/lambda/market_intel/ingestion/usajobs.py`
    - Implement `ingest(keywords: list[str]) -> dict` — fetches from USAJobs API, transforms, merges into DynamoDB
    - Uses `retry_with_backoff` for each API call
    - Catches per-keyword failures, continues processing remaining keywords
    - Returns `{"succeeded": [...], "failed": [...]}`
    - API key from `USAJOBS_API_KEY` environment variable, User-Agent from `USAJOBS_USER_AGENT` env var
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 7.5 Write property tests for ingestion pipeline
    - **Property 1: Ingestion transformation produces valid records** — For any valid mock API response, transformer output contains all required MarketData fields with correct types
    - **Property 2: Ingestion idempotency** — For any record, writing same role+date twice results in exactly one DynamoDB item
    - **Property 3: Ingestion resilience** — For any role list with partial failures, succeeded count equals non-failing role count
    - **Validates: Requirements 1.3, 1.4, 1.6, 2.2, 2.3, 2.5, 3.2, 3.3, 3.5**

- [x] 8. Implement seed data loader
  - [x] 8.1 Create `backend/lambda/market_intel/seed.py`
    - Define seed data for 5 transition paths: QA→AI QA, Infantry→PM/Ops Manager, Retail Manager→Customer Success, Truck Driver→Fleet Ops/Logistics, Accountant→Data Analyst/Financial Systems
    - Each role: demand_score, growth_rate, trend_direction, 10 top_skills with frequencies, salary_range, source="synthetic"
    - Implement `load_seed_data() -> dict` — writes all seed records to MarketData table, idempotent
    - Use real O*NET/BLS data where possible, mark synthetic values
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [x] 8.2 Write property tests for seed data
    - **Property 13: Seed data structure validity** — For any seed record: all required fields present, top_skills has 10 entries with frequencies, salary min ≤ median ≤ max, source is "synthetic"
    - **Validates: Requirements 9.2, 9.5**

- [x] 9. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Create Lambda handlers and public API
  - [x] 10.1 Create `backend/lambda/market_intel/handler.py`
    - Implement `onet_handler(event, context)` — calls `onet.ingest()` then `scoring.recalculate_scores()`
    - Implement `bls_handler(event, context)` — calls `bls.ingest()` then `scoring.recalculate_scores()`
    - Implement `usajobs_handler(event, context)` — calls `usajobs.ingest()` then `scoring.recalculate_scores()`
    - Implement `seed_handler(event, context)` — calls `seed.load_seed_data()`
    - All handlers are thin wrappers: validate, delegate, return response
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 9.3_

  - [x] 10.2 Wire public API in `backend/lambda/market_intel/__init__.py`
    - Export: `get_demand_score`, `calculate_alignment`, `get_insights`, `normalize_skill`, `get_role_skills`
    - Each function reads from DynamoDB only, never calls external APIs
    - Returns structured dicts/dataclasses, returns error indicators for missing data
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

- [x] 11. Add CDK infrastructure for scheduled pipeline
  - [x] 11.1 Create `infra/stacks/market_intel_stack.py`
    - Define `MarketIntelStack` with Lambda functions for O*NET, BLS, USAJobs, and seed handlers
    - Create EventBridge Scheduler rules: O*NET on 1st of month, BLS on 15th, USAJobs every Monday
    - Grant DynamoDB read/write permissions on MarketData table to all pipeline Lambdas
    - Grant DynamoDB read permissions on UserProfiles and EvidenceVault tables for alignment calculation
    - Set environment variables: table names, API keys, region
    - Add CDK custom resource to trigger seed_handler on first deployment
    - Tags: Project=REGAIN, Environment=dev
    - _Requirements: 1.7, 2.6, 3.6, 8.1, 8.2, 8.3, 8.6, 9.3_

- [x] 12. Wire integration with Coaching Agent and Mission Engine
  - [x] 12.1 Update `backend/agents/coaching/tools.py` `get_market_insights` tool
    - Replace current sector-based query with import from `backend.lambda.market_intel`
    - Call `get_demand_score(role_id)` for role trend data
    - Call `get_insights(role_id=role_id)` for structured insights
    - Return structured dict with demand_score, trend_direction, growth_rate, top_skills, salary_range, and relevant insights
    - _Requirements: 10.1, 10.3_

  - [x] 12.2 Add `get_alignment` Strands @tool to `backend/agents/coaching/tools.py`
    - Import `calculate_alignment` from `backend.lambda.market_intel`
    - Call `calculate_alignment(user_id, target_role_id)` and return the AlignmentResult as dict
    - Write precise docstring so the Coaching Agent knows when to call it (alignment checks, progress reviews, gap discussions)
    - _Requirements: 6.1, 6.6, 10.1_

  - [x] 12.3 Update Mission Engine `backend/engine/skill_gap.py` to use taxonomy normalization
    - Import `normalize_skill` from `backend.lambda.market_intel`
    - Normalize user skills and target requirements through the canonical taxonomy before comparison
    - This ensures the Mission Engine's gap analysis uses the same skill identifiers as market data
    - _Requirements: 4.3, 10.1_

- [x] 13. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints at tasks 5, 9, and 13 ensure incremental validation
- Property tests use Hypothesis library with minimum 100 iterations per property
- The skill taxonomy starts focused on the 5 seed transition paths and expands to ~200 skills
- All ingestion modules share the same retry logic from `ingestion/retry.py`
