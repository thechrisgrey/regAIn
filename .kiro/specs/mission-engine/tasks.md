# Implementation Plan: Mission Engine

## Overview

Build the Mission Engine as a standalone Python package at `backend/engine/`. Implementation proceeds bottom-up: data models first, then individual components (skill gap, difficulty, templates, scoring, lifecycle, phase gates), then the orchestrator that wires them together, and finally integration with the Coaching Agent's existing tools.

## Tasks

- [x] 1. Create engine package with data models
  - [x] 1.1 Create `backend/engine/__init__.py` and `backend/engine/models.py`
    - Define dataclasses: MissionCandidate, SkillGapReport, GateResult, GateCondition, DifficultyState, CompletionResult, GenerationResult
    - All fields with type hints, default values where appropriate
    - Add `to_dict()` and `from_dict()` serialization helpers on DifficultyState (for DynamoDB storage)
    - _Requirements: 1.3, 4.7, 5.6_

- [x] 2. Implement skill gap analysis
  - [x] 2.1 Create `backend/engine/skill_gap.py`
    - Implement `analyze_skill_gaps()` with recency-weighted evidence scoring (halves every 90 days, threshold of 3 items for full score)
    - Implement market alignment percentage as weighted average of skill scores by demand
    - Return SkillGapReport with per-skill scores, alignment %, priority skills sorted by gap × demand
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [x] 2.2 Write property tests for skill gap analysis
    - **Property 2: Skill gap scores bounded 0.0-1.0**
    - **Validates: Requirements 2.2**
    - **Property 3: Market alignment is correct weighted average**
    - **Validates: Requirements 2.3**

- [x] 3. Implement difficulty scaling model
  - [x] 3.1 Create `backend/engine/difficulty.py`
    - Implement `compute_difficulty_state()` from mission history
    - Implement `should_advance()` (3 consecutive completions + 7-day cooldown)
    - Implement `should_regress()` (3 consecutive skips)
    - Implement `update_difficulty()` returning new DifficultyState
    - Implement `filter_by_difficulty()` filtering candidates within ±1 of user level
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 3.2 Write property tests for difficulty model
    - **Property 4: Difficulty levels bounded 1-5**
    - **Validates: Requirements 3.1**
    - **Property 5: Difficulty advances after 3 consecutive completions**
    - **Validates: Requirements 3.3**
    - **Property 6: Difficulty regresses after 3 consecutive skips**
    - **Validates: Requirements 3.4**
    - **Property 7: Difficulty advancement capped at 1 per 7 days**
    - **Validates: Requirements 3.5**

- [x] 4. Implement mission templates
  - [x] 4.1 Create `backend/engine/templates.py`
    - Define MissionTemplate dataclass with parameterized fields
    - Define templates for all 5 categories (Reflection, Skill_Building, Portfolio, Networking, Market_Research) across difficulty levels 1-5 and phases
    - Implement `instantiate_template()` substituting user profile, skill gaps, and market data
    - Implement `instantiate_all_templates()` filtering by phase
    - Implement `get_all_templates()` returning the full registry
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

  - [x] 4.2 Write property test for template instantiation
    - **Property 1: Template instantiation produces valid candidates**
    - **Validates: Requirements 1.2, 1.3, 1.4**

- [x] 5. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement priority scoring
  - [x] 6.1 Create `backend/engine/scoring.py`
    - Implement `score_gap_priority()` — higher for wider gaps in high-demand skills
    - Implement `score_category_balance()` — penalize overindexed categories
    - Implement `score_difficulty_appropriateness()` — peak at matching level
    - Implement `score_phase_alignment()` — favor phase-preferred categories
    - Implement `score_streak_momentum()` — adapt to streak state
    - Implement `score_candidate()` applying weights: gap 40%, balance 20%, difficulty 15%, phase 15%, streak 10%
    - Implement `score_and_rank()` sorting candidates by score descending
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_

  - [x] 6.2 Write property tests for scoring
    - **Property 8: Priority score equals weighted sum of sub-scores**
    - **Validates: Requirements 4.1**
    - **Property 9: Gap priority monotonic with gap width and demand**
    - **Validates: Requirements 4.2**
    - **Property 10: Category balance penalizes overindexed categories**
    - **Validates: Requirements 4.3**
    - **Property 11: Difficulty appropriateness peaks at matching level**
    - **Validates: Requirements 4.4**
    - **Property 12: Phase alignment favors phase-appropriate categories**
    - **Validates: Requirements 4.5**
    - **Property 13: Streak momentum adapts to streak state**
    - **Validates: Requirements 4.6**

- [x] 7. Implement mission lifecycle
  - [x] 7.1 Create `backend/engine/lifecycle.py`
    - Define VALID_TRANSITIONS map
    - Implement `validate_transition()` checking against the map
    - Implement `transition_mission()` applying state change with timestamps and evidence linking
    - Implement `check_expired_missions()` identifying assigned missions past 48 hours
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [x] 7.2 Write property tests for lifecycle
    - **Property 16: State transitions match valid transition map**
    - **Validates: Requirements 6.1, 6.2**
    - **Property 17: Transitions produce correct timestamps and linked data**
    - **Validates: Requirements 6.3, 6.4**
    - **Property 18: Expiry detection for 48-hour assigned missions**
    - **Validates: Requirements 6.5**

- [x] 8. Implement phase gate evaluation
  - [x] 8.1 Create `backend/engine/phase_gates.py`
    - Define GATE_CONDITIONS for all three gates (Foundation→Expansion, Expansion→Launch, Launch completion)
    - Implement `evaluate_gate()` checking all conditions for the current phase
    - Return GateResult with passed status, next phase, and per-condition progress
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [x] 8.2 Write property test for phase gates
    - **Property 15: Gate evaluation correct for all phases**
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.6**

- [x] 9. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Implement generation orchestrator
  - [x] 10.1 Create `backend/engine/generator.py`
    - Implement `generate_daily_mission()` orchestrating the full pipeline: fetch data → analyze gaps → compute difficulty → instantiate templates → filter by difficulty → exclude 14-day duplicates → score and rank → return top 3
    - Implement `complete_mission()` orchestrating: transition state → update difficulty → evaluate gate → return CompletionResult
    - Handle error cases: missing profile, missing campaign, insufficient candidates (relax difficulty filter)
    - Use existing DynamoDBClient for all data access
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 8.1, 8.3, 8.4_

  - [x] 10.2 Write property test for duplicate exclusion
    - **Property 19: Recent duplicate exclusion within 14 days**
    - **Validates: Requirements 7.5**

  - [x] 10.3 Write unit tests for generator orchestration
    - Test with mocked DynamoDB data to verify pipeline wiring
    - Test error paths: missing profile, missing campaign, insufficient candidates
    - Test primary + 2 alternates selection
    - **Property 14: Top candidate selected as primary**
    - **Validates: Requirements 4.7**
    - _Requirements: 7.1, 7.2, 7.4_

- [x] 11. Integrate with Coaching Agent tools
  - [x] 11.1 Update `backend/agents/coaching/tools.py`
    - Modify `generate_mission` tool to import and call `backend.engine.generator.generate_daily_mission()` instead of doing a simple DynamoDB put
    - Modify `complete_mission` tool to import and call `backend.engine.generator.complete_mission()` instead of doing a simple status update
    - Ensure tool return dicts include all MissionCandidate fields and any phase transition info
    - Handle phase mapping: engine uses Foundation/Expansion/Launch, existing campaign data may use foundation/momentum/acceleration/transition
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

- [x] 12. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties using Hypothesis
- Unit tests validate specific examples and edge cases
- The engine package has no dependency on the Coaching Agent — integration is one-directional (agent imports engine)
- All DynamoDB access uses the existing DynamoDBClient — no new tables or infrastructure changes
