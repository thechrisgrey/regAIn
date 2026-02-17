# Requirements Document

## Introduction

The Mission Engine is the core intelligence layer of the REGAIN platform that generates, scores, assigns, adapts, and manages personalized career reskilling missions. It operates as a standalone Python package (`backend/engine/`) that the Coaching Agent's Strands `@tool` functions call into. The engine takes user profile data, campaign state, skill gaps, market signals, and behavioral patterns as inputs and produces ranked, evidence-producing missions tailored to each user's career transition.

## Glossary

- **Mission_Engine**: The Python module at `backend/engine/` that contains all mission generation, scoring, difficulty scaling, skill gap analysis, phase gate evaluation, and lifecycle management logic.
- **Mission_Candidate**: A scored mission object produced by the generation algorithm, containing title, description, skill tags, difficulty level, estimated duration, expected evidence type, phase alignment, and market relevance score.
- **Mission_Template**: A parameterized structure defining a mission category (Reflection, Skill_Building, Portfolio, Networking, Market_Research) with placeholder fields that accept user profile data, skill gaps, and market data to produce personalized mission instances.
- **Skill_Gap_Analyzer**: The component that compares a user's demonstrated skills (from EvidenceVault) against target role requirements (from MarketIntel) to produce per-skill gap scores.
- **Priority_Scorer**: The component that ranks Mission_Candidates using a weighted scoring formula (gap priority 40%, category balance 20%, difficulty appropriateness 15%, phase alignment 15%, streak momentum 10%).
- **Phase_Gate_Evaluator**: The component that checks whether a user's campaign meets the milestone conditions required to advance from one phase to the next (Foundation → Expansion → Launch).
- **Difficulty_Model**: The system that tracks per-category difficulty levels (1–5) for each user and determines when to advance or regress based on completion and skip patterns.
- **Mission_Lifecycle**: The state machine governing mission transitions: generated → assigned → in_progress → completed → skipped → expired.
- **Transition_Profile**: The user's profile data including extracted skills, experience map, target roles, and skill taxonomy stored in the UserProfiles DynamoDB table.
- **Evidence_Density**: The count and recency-weighted quality of evidence records per skill in the EvidenceVault table.
- **Market_Alignment_Percentage**: An aggregate score (0–100%) representing how well a user's demonstrated skills match target role requirements weighted by market demand.
- **Campaign_Phase**: One of three sequential phases — Foundation, Expansion, or Launch — each with distinct mission characteristics and milestone gates.
- **DynamoDBClient**: The existing shared data access layer at `backend/lambda/shared/dynamodb.py` used for all database operations.

## Requirements

### Requirement 1: Mission Template System

**User Story:** As a career reskilling user, I want missions generated from structured templates personalized to my background, so that each mission is relevant to my specific transition and produces demonstrable evidence.

#### Acceptance Criteria

1. THE Mission_Engine SHALL define Mission_Templates in five categories: Reflection, Skill_Building, Portfolio, Networking, and Market_Research.
2. WHEN a Mission_Template is instantiated, THE Mission_Engine SHALL substitute user-specific data (skills, target role, experience, skill gaps, market data) into the template's parameterized fields to produce a personalized mission instance.
3. THE Mission_Engine SHALL ensure every instantiated mission includes a title, description, skill tags, difficulty level, estimated duration, expected evidence type, and a rationale explaining relevance to the user's transition.
4. WHEN a Mission_Template is instantiated, THE Mission_Engine SHALL produce a mission with an estimated duration between 15 and 45 minutes.
5. THE Mission_Engine SHALL ensure every mission description specifies a concrete, evidence-producing action rather than a generic career advice statement.

### Requirement 2: Skill Gap Analysis

**User Story:** As a career reskilling user, I want the platform to identify gaps between my demonstrated skills and target role requirements, so that missions focus on the areas with the highest impact for my career transition.

#### Acceptance Criteria

1. WHEN the Skill_Gap_Analyzer runs, THE Mission_Engine SHALL compare the user's demonstrated skills from EvidenceVault (weighted by evidence recency and count) against target role requirements from MarketIntel.
2. WHEN the Skill_Gap_Analyzer computes a per-skill gap score, THE Mission_Engine SHALL produce a value between 0.0 (no evidence) and 1.0 (strong evidence, market-aligned) for each skill.
3. WHEN the Skill_Gap_Analyzer computes the Market_Alignment_Percentage, THE Mission_Engine SHALL calculate it as the weighted average of individual skill scores where weights are the market demand values for each skill.
4. WHEN a mission is completed and new evidence is logged, THE Mission_Engine SHALL recompute the affected skill gap scores to reflect the updated evidence.

### Requirement 3: Difficulty Scaling

**User Story:** As a career reskilling user, I want mission difficulty to adapt to my performance in each category, so that I am consistently challenged without being overwhelmed.

#### Acceptance Criteria

1. THE Difficulty_Model SHALL track difficulty levels independently per mission category per user, with levels ranging from 1 to 5.
2. WHEN a new user begins a campaign, THE Difficulty_Model SHALL initialize all category difficulty levels to 1.
3. WHEN a user completes 3 consecutive missions at the current difficulty level in a given category, THE Difficulty_Model SHALL advance that category's difficulty level by 1, up to a maximum of 5.
4. WHEN a user skips 3 consecutive missions in a given category, THE Difficulty_Model SHALL reduce that category's difficulty level by 1, down to a minimum of 1.
5. THE Difficulty_Model SHALL restrict difficulty advancement to a maximum of 1 level increase per category per 7-day period.

### Requirement 4: Mission Scoring and Priority Queue

**User Story:** As a career reskilling user, I want the platform to select the most impactful mission for me each day, so that my limited time produces maximum career progress.

#### Acceptance Criteria

1. WHEN the Priority_Scorer ranks Mission_Candidates, THE Mission_Engine SHALL apply the following weights: gap priority at 40%, category balance at 20%, difficulty appropriateness at 15%, phase alignment at 15%, and streak momentum at 10%.
2. WHEN computing the gap priority score for a Mission_Candidate, THE Priority_Scorer SHALL assign higher scores to missions targeting wider skill gaps in skills with higher market demand.
3. WHEN computing the category balance score, THE Priority_Scorer SHALL penalize categories the user has overindexed on and reward underrepresented categories relative to the user's mission history.
4. WHEN computing the difficulty appropriateness score, THE Priority_Scorer SHALL assign the highest score to missions matching the user's current difficulty level in that category, with decreasing scores for missions further from the current level.
5. WHEN computing the phase alignment score, THE Priority_Scorer SHALL assign higher scores to mission types that fit the current Campaign_Phase (Reflection and Skill_Building in Foundation, Portfolio and Market_Research in Expansion, Networking in Launch).
6. WHEN computing the streak momentum score, THE Priority_Scorer SHALL favor missions similar to recent completions when the user is on a completion streak, and favor easier or more engaging missions when the streak is broken.
7. WHEN the Priority_Scorer completes ranking, THE Mission_Engine SHALL select the top-scored Mission_Candidate as the primary daily mission and provide 2 alternate missions.

### Requirement 5: Campaign Phase Progression

**User Story:** As a career reskilling user, I want to advance through campaign phases as I build skills and evidence, so that I have clear milestones marking my progress toward career readiness.

#### Acceptance Criteria

1. WHEN the Phase_Gate_Evaluator checks the Foundation-to-Expansion gate, THE Mission_Engine SHALL require: at least 10 completed missions, at least 3 mission categories represented, at least 8 unique skills with evidence, and Market_Alignment_Percentage of at least 40%.
2. WHEN the Phase_Gate_Evaluator checks the Expansion-to-Launch gate, THE Mission_Engine SHALL require: at least 25 total completed missions, all 5 mission categories represented, at least 15 unique skills with evidence, at least 3 portfolio artifacts created, and Market_Alignment_Percentage of at least 65%.
3. WHEN the Phase_Gate_Evaluator checks Launch phase completion, THE Mission_Engine SHALL require: at least 40 total completed missions, at least 20 unique skills with evidence, and Market_Alignment_Percentage of at least 80%.
4. WHEN a mission is completed, THE Phase_Gate_Evaluator SHALL automatically evaluate whether the current phase's gate conditions are met.
5. WHEN all gate conditions for the current phase are met, THE Phase_Gate_Evaluator SHALL return a phase transition result indicating the new phase.
6. IF a gate evaluation finds conditions are not met, THEN THE Phase_Gate_Evaluator SHALL return a progress summary showing completion percentage for each gate condition.

### Requirement 6: Mission Lifecycle Management

**User Story:** As a career reskilling user, I want clear mission states and timely transitions, so that my mission queue stays current and my behavioral data is accurate.

#### Acceptance Criteria

1. THE Mission_Lifecycle SHALL enforce the following valid state transitions: generated → assigned, assigned → in_progress, assigned → skipped, in_progress → completed, in_progress → skipped, and assigned → expired.
2. IF a mission state transition is requested that is not in the set of valid transitions, THEN THE Mission_Lifecycle SHALL reject the transition and return an error indicating the current state and the invalid target state.
3. WHEN a mission transitions to completed, THE Mission_Lifecycle SHALL record the completedAt timestamp and link the associated evidence identifiers.
4. WHEN a mission transitions to assigned, THE Mission_Lifecycle SHALL record the assignedAt timestamp.
5. WHEN a mission has been in assigned status for more than 48 hours without transitioning to in_progress, THE Mission_Lifecycle SHALL transition the mission to expired status.
6. WHEN a mission transitions to completed or skipped, THE Mission_Lifecycle SHALL update the user's behavioral pattern data (completion streaks, skip streaks, time-to-complete) used by the Difficulty_Model and Priority_Scorer.

### Requirement 7: Mission Generation Orchestration

**User Story:** As a career reskilling user, I want the engine to generate a daily mission that accounts for all my data, so that each mission is the best possible use of my time.

#### Acceptance Criteria

1. WHEN the Mission_Engine generates missions, THE Mission_Engine SHALL retrieve the user's Transition_Profile, active Campaign, mission history, evidence summary, and relevant market data from DynamoDB using the existing DynamoDBClient.
2. WHEN the Mission_Engine generates missions, THE Mission_Engine SHALL produce a ranked list of at least 3 Mission_Candidates by instantiating templates, scoring them with the Priority_Scorer, and sorting by score descending.
3. THE Mission_Engine SHALL complete the full mission generation pipeline (data retrieval, gap analysis, template instantiation, scoring, ranking) within 3 seconds.
4. THE Mission_Engine SHALL assign no more than 1 primary mission per user per day.
5. WHEN the Mission_Engine generates missions, THE Mission_Engine SHALL exclude mission templates that duplicate a mission the user completed within the previous 14 days based on matching template identifier and primary skill tag.

### Requirement 8: Integration with Coaching Agent

**User Story:** As the Coaching Agent, I want to call into the Mission Engine as a Python module, so that I can deliver intelligent missions conversationally without duplicating generation logic.

#### Acceptance Criteria

1. THE Mission_Engine SHALL expose a public Python API that the Coaching Agent's `generate_mission` and `complete_mission` Strands @tool functions can import and call directly.
2. THE Mission_Engine SHALL operate as a standalone Python package at `backend/engine/` with no dependency on the Coaching Agent module.
3. WHEN the Coaching Agent calls the Mission_Engine's generation function, THE Mission_Engine SHALL return structured data (Mission_Candidates with all fields) rather than free-text responses.
4. WHEN the Coaching Agent calls the Mission_Engine's completion function, THE Mission_Engine SHALL handle evidence linking, difficulty updates, phase gate evaluation, and behavioral pattern updates, returning a structured result including any phase transition.
