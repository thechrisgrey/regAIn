# Requirements Document

## Introduction

The Market Intelligence System is the data pipeline and analysis engine that powers REGAIN's data-driven career guidance. It ingests job market data from free public sources (O*NET, BLS, USAJobs), normalizes skills through a unified taxonomy, calculates demand scores and user-to-market alignment percentages, and generates structured insights that the Coaching Agent delivers conversationally and the Mission Engine uses for skill gap prioritization. All market data is pre-fetched on schedule and stored in the existing MarketData DynamoDB table — external APIs are never called during user-facing requests.

## Glossary

- **Market_Intelligence_System**: The collection of Python modules at `backend/lambda/market_intel/` that implement data ingestion, skill normalization, demand scoring, alignment calculation, and insight generation.
- **Ingestion_Pipeline**: The set of scheduled Lambda functions that fetch data from external APIs (O*NET, BLS, USAJobs), transform responses into the MarketData table schema, and write records to DynamoDB.
- **Skill_Taxonomy**: A static Python data structure defining ~200 canonical skills organized into categories (Technical, Analytical, Communication, Leadership, Domain_Specific), each with aliases mapping from O*NET codes, job posting variants, and natural language descriptions.
- **Canonical_Skill**: A single entry in the Skill_Taxonomy representing a normalized skill name with associated aliases, O*NET code mappings, and category classification.
- **Demand_Score**: A composite score (0–100) for a tracked role calculated from posting volume, growth rate, salary signal, and BLS employment projections.
- **Trend_Direction**: A categorical label derived from year-over-year growth rate: "surging" (>20%), "growing" (5–20%), "stable" (-5% to 5%), or "declining" (<-5%).
- **Alignment_Percentage**: A weighted score (0–100%) representing how well a user's demonstrated skills match a target role's requirements, where weights are skill frequency in job postings and user scores reflect evidence strength.
- **Evidence_Strength**: A score (0.0–1.0) for a user's proficiency in a canonical skill, derived from the count and recency of evidence items in the EvidenceVault table.
- **Market_Insight**: A structured data object containing a type, role reference, message template, data payload, and metadata — used by the Coaching Agent to deliver personalized market-aware guidance.
- **Seed_Data**: Pre-loaded market data records for five representative transition paths, enabling immediate platform functionality without waiting for API refresh cycles.
- **MarketData_Table**: The existing DynamoDB table (RegainMarketData, PK: sector, SK: timestamp) used to store all ingested and computed market intelligence records.
- **DynamoDBClient**: The existing shared data access layer at `backend/lambda/shared/dynamodb.py` used for all database operations.
- **EventBridge_Schedule**: An Amazon EventBridge Scheduler rule that triggers a Lambda function on a defined cron or rate schedule.

## Requirements

### Requirement 1: O*NET Data Ingestion

**User Story:** As the REGAIN platform, I want to ingest occupation and skill requirement data from the O*NET Web Services API, so that the system has authoritative role-to-skill mappings for demand scoring and gap analysis.

#### Acceptance Criteria

1. WHEN the O*NET ingestion Lambda executes, THE Ingestion_Pipeline SHALL fetch occupation data, skill requirements, knowledge taxonomies, and job zone classifications from the O*NET Web Services API (https://services.onetcenter.org/ws/).
2. WHEN the O*NET ingestion Lambda executes, THE Ingestion_Pipeline SHALL authenticate using an API key stored in an environment variable.
3. WHEN the Ingestion_Pipeline receives a valid O*NET API response, THE Ingestion_Pipeline SHALL transform the response into the MarketData_Table schema and write records to DynamoDB.
4. WHEN the Ingestion_Pipeline writes O*NET data for a role and date that already exists, THE Ingestion_Pipeline SHALL overwrite the existing record rather than creating a duplicate.
5. IF an O*NET API call fails, THEN THE Ingestion_Pipeline SHALL retry with exponential backoff (3 retries at 1-second, 2-second, and 4-second intervals) before logging the error and continuing.
6. IF all retries for an O*NET API call are exhausted, THEN THE Ingestion_Pipeline SHALL log the failure and continue processing remaining roles without raising an exception.
7. THE Ingestion_Pipeline SHALL schedule O*NET data ingestion to run on the 1st of each month via an EventBridge_Schedule.

### Requirement 2: BLS Data Ingestion

**User Story:** As the REGAIN platform, I want to ingest employment projections, occupational outlook, and wage data from the Bureau of Labor Statistics API, so that demand scores reflect official labor market projections.

#### Acceptance Criteria

1. WHEN the BLS ingestion Lambda executes, THE Ingestion_Pipeline SHALL fetch employment projections, occupational outlook, and wage data by region and role from the BLS Public Data API (v1, no API key required).
2. WHEN the Ingestion_Pipeline receives a valid BLS API response, THE Ingestion_Pipeline SHALL transform the response into the MarketData_Table schema and merge the data with existing role records in DynamoDB.
3. WHEN the Ingestion_Pipeline writes BLS data for a role and date that already exists, THE Ingestion_Pipeline SHALL overwrite the existing record rather than creating a duplicate.
4. IF a BLS API call fails, THEN THE Ingestion_Pipeline SHALL retry with exponential backoff (3 retries at 1-second, 2-second, and 4-second intervals) before logging the error and continuing.
5. IF all retries for a BLS API call are exhausted, THEN THE Ingestion_Pipeline SHALL log the failure and continue processing remaining series without raising an exception.
6. THE Ingestion_Pipeline SHALL schedule BLS data ingestion to run on the 15th of each month via an EventBridge_Schedule.

### Requirement 3: USAJobs Data Ingestion

**User Story:** As the REGAIN platform, I want to ingest federal job posting volumes and skill requirements from the USAJobs API, so that the system has real-time posting data to supplement private sector projections.

#### Acceptance Criteria

1. WHEN the USAJobs ingestion Lambda executes, THE Ingestion_Pipeline SHALL fetch current job posting volumes and skill requirements for tracked roles from the USAJobs API.
2. WHEN the Ingestion_Pipeline receives a valid USAJobs API response, THE Ingestion_Pipeline SHALL transform the response into the MarketData_Table schema and merge the data with existing role records in DynamoDB.
3. WHEN the Ingestion_Pipeline writes USAJobs data for a role and date that already exists, THE Ingestion_Pipeline SHALL overwrite the existing record rather than creating a duplicate.
4. IF a USAJobs API call fails, THEN THE Ingestion_Pipeline SHALL retry with exponential backoff (3 retries at 1-second, 2-second, and 4-second intervals) before logging the error and continuing.
5. IF all retries for a USAJobs API call are exhausted, THEN THE Ingestion_Pipeline SHALL log the failure and continue processing remaining queries without raising an exception.
6. THE Ingestion_Pipeline SHALL schedule USAJobs data ingestion to run every Monday via an EventBridge_Schedule.

### Requirement 4: Skill Taxonomy and Normalization

**User Story:** As a user whose skills are described in varied language, I want the platform to normalize all skill references to a unified taxonomy, so that my skills are accurately compared against job market requirements regardless of how they were originally described.

#### Acceptance Criteria

1. THE Skill_Taxonomy SHALL define approximately 200 Canonical_Skills organized into five categories: Technical, Analytical, Communication, Leadership, and Domain_Specific.
2. THE Skill_Taxonomy SHALL map each Canonical_Skill to aliases from three sources: O*NET skill codes, common job posting variants, and natural language user descriptions.
3. WHEN the Market_Intelligence_System receives a skill string from any source (user input, O*NET response, job posting), THE Skill_Taxonomy SHALL normalize the string to a Canonical_Skill using case-insensitive alias matching.
4. IF the Skill_Taxonomy cannot match a skill string to any Canonical_Skill alias, THEN THE Skill_Taxonomy SHALL return a null match indicator rather than silently dropping the skill.
5. THE Skill_Taxonomy SHALL be implemented as a static Python data structure (dict or dataclass) that deploys with the Lambda code, not as a DynamoDB table.
6. THE Skill_Taxonomy SHALL serialize to and deserialize from a JSON representation for inspection and testing purposes.

### Requirement 5: Market Demand Scoring

**User Story:** As the REGAIN platform, I want to calculate a composite demand score for each tracked role, so that the Coaching Agent and Mission Engine can prioritize skills aligned with high-demand opportunities.

#### Acceptance Criteria

1. WHEN the Market_Intelligence_System calculates a Demand_Score for a role, THE Market_Intelligence_System SHALL produce a composite integer score between 0 and 100.
2. WHEN calculating the Demand_Score, THE Market_Intelligence_System SHALL combine four normalized components: posting volume (0–25, percentile rank against all tracked roles), growth rate (0–30, where >20% YoY scores 30, 10–20% scores 20, 0–10% scores 10, and negative scores 0), salary signal (0–20, percentile rank of median salary against all tracked roles), and projection (0–25, where "Much faster than average" scores 25, "Faster" scores 20, "Average" scores 15, "Slower" scores 5, and "Decline" scores 0).
3. WHEN the Market_Intelligence_System calculates a Demand_Score, THE Market_Intelligence_System SHALL also compute the Trend_Direction label: "surging" for >20% YoY growth, "growing" for 5–20%, "stable" for -5% to 5%, and "declining" for less than -5%.
4. WHEN the Market_Intelligence_System calculates a Demand_Score, THE Market_Intelligence_System SHALL produce a ranked list of top skills required for the role with frequency percentages derived from ingested data.
5. WHEN the Market_Intelligence_System calculates a Demand_Score, THE Market_Intelligence_System SHALL produce a salary range object containing min, median, max, and region fields.
6. THE Market_Intelligence_System SHALL recalculate Demand_Scores after each market data refresh and write updated scores to the MarketData_Table.

### Requirement 6: User-to-Market Alignment Calculation

**User Story:** As a user tracking my reskilling progress, I want to see a percentage representing how well my demonstrated skills match my target role's market requirements, so that I can measure my progress toward career readiness.

#### Acceptance Criteria

1. WHEN the Market_Intelligence_System calculates the Alignment_Percentage for a user and target role, THE Market_Intelligence_System SHALL compare the user's Canonical_Skills from the UserProfiles table against the target role's required skills from the MarketData_Table.
2. WHEN computing a per-skill score, THE Market_Intelligence_System SHALL assign Evidence_Strength values: 0.0 for skills the user does not have, 0.3 for claimed skills with zero evidence items, 0.6 for skills with 1–2 evidence items, 0.9 for skills with 3 or more evidence items, and 1.0 for skills with 3 or more evidence items where at least one was created within the last 30 days.
3. WHEN computing the Alignment_Percentage, THE Market_Intelligence_System SHALL calculate it as the weighted average of per-skill scores where weights are the frequency percentages of each skill in job postings for the target role.
4. WHEN the Market_Intelligence_System computes the Alignment_Percentage, THE Market_Intelligence_System SHALL also produce a per-skill breakdown containing skill name, user score, market weight, and gap value.
5. WHEN the Market_Intelligence_System computes the Alignment_Percentage, THE Market_Intelligence_System SHALL identify the top 3 gaps (skills with highest market_weight multiplied by one minus user_score) and top 3 strengths (skills with highest market_weight multiplied by user_score).
6. THE Market_Intelligence_System SHALL recalculate the Alignment_Percentage on demand when requested by the Coaching Agent or Mission Engine, reading current evidence from the EvidenceVault table.

### Requirement 7: Insight Generation

**User Story:** As the Coaching Agent, I want structured market insight objects with templates and data payloads, so that I can deliver personalized, data-driven guidance to users without generating market analysis from scratch.

#### Acceptance Criteria

1. THE Market_Intelligence_System SHALL generate Market_Insights as structured data objects containing: type, role_id, message_template, data_payload, generated_date, and shown (boolean, defaulting to false).
2. THE Market_Intelligence_System SHALL support five insight types: Role_Trend (role demand and growth data), Alignment (user skill overlap with a role), Gap_Opportunity (high-impact skill gap targeting), Emerging_Role (new high-demand role matching user skills), and Milestone (alignment improvement over time).
3. WHEN a market data refresh completes, THE Market_Intelligence_System SHALL regenerate Role_Trend and Emerging_Role insights for all tracked roles.
4. WHEN an Alignment_Percentage is recalculated, THE Market_Intelligence_System SHALL regenerate Alignment, Gap_Opportunity, and Milestone insights for the affected user and role.
5. WHEN generating a Milestone insight, THE Market_Intelligence_System SHALL compare the current Alignment_Percentage against the previous value and identify which skills improved.
6. THE Market_Intelligence_System SHALL store generated Market_Insights as attributes on the MarketData_Table records or as user-scoped records, enabling the Coaching Agent to query relevant insights by role or user.

### Requirement 8: Scheduled Refresh Pipeline

**User Story:** As the REGAIN platform, I want market data refreshed on an efficient schedule matching each source's update frequency, so that data stays current without wasting API calls or Lambda invocations.

#### Acceptance Criteria

1. THE Market_Intelligence_System SHALL schedule O*NET data ingestion to execute on the 1st of each month via an EventBridge_Schedule.
2. THE Market_Intelligence_System SHALL schedule BLS data ingestion to execute on the 15th of each month via an EventBridge_Schedule.
3. THE Market_Intelligence_System SHALL schedule USAJobs data ingestion to execute every Monday via an EventBridge_Schedule.
4. WHEN a scheduled ingestion completes, THE Ingestion_Pipeline SHALL trigger Demand_Score recalculation for all roles affected by the new data.
5. WHEN a Demand_Score recalculation completes, THE Market_Intelligence_System SHALL trigger insight regeneration for affected roles.
6. THE Market_Intelligence_System SHALL use Amazon EventBridge Scheduler for all cron triggers, not CloudWatch Events.

### Requirement 9: Seed Data Loading

**User Story:** As a competition demo user, I want the platform to have pre-loaded market data for representative transition paths, so that the application works immediately without waiting for API refresh cycles.

#### Acceptance Criteria

1. THE Market_Intelligence_System SHALL provide seed data for five transition paths: Software QA Engineer to AI Quality Assurance Engineer, Infantry/Combat Arms to Project Manager/Operations Manager, Retail Manager to Customer Success Manager, Truck Driver to Fleet Operations/Logistics Analyst, and Accountant to Data Analyst/Financial Systems Analyst.
2. WHEN seed data is loaded, THE Market_Intelligence_System SHALL populate each role with a Demand_Score, growth rate, top 10 required skills with frequency percentages, salary range, and Trend_Direction.
3. THE Market_Intelligence_System SHALL load seed data via a one-time Lambda function or CDK custom resource during deployment.
4. WHEN seed data is loaded for a role that already has data, THE Market_Intelligence_System SHALL overwrite the existing record to ensure idempotent loading.
5. THE Market_Intelligence_System SHALL clearly mark any synthetic data values in the seed data with a source field value of "synthetic" to distinguish from live API data.

### Requirement 10: Module Integration Interface

**User Story:** As the Coaching Agent and Mission Engine, I want to import market intelligence functions as a Python module, so that I can access demand scores, alignment calculations, and insights without making HTTP calls or duplicating logic.

#### Acceptance Criteria

1. THE Market_Intelligence_System SHALL expose public Python functions for: retrieving demand scores by role, calculating Alignment_Percentage for a user and target role, querying Market_Insights by role or user, and normalizing skill strings to Canonical_Skills.
2. THE Market_Intelligence_System SHALL operate as importable Python modules at `backend/lambda/market_intel/` with no dependency on the Coaching Agent or Mission Engine modules.
3. WHEN the Coaching Agent or Mission Engine calls a Market_Intelligence_System function, THE Market_Intelligence_System SHALL return structured dict or dataclass outputs rather than free-text responses.
4. THE Market_Intelligence_System SHALL read all market data from the MarketData_Table via the existing DynamoDBClient, never calling external APIs during user-facing function calls.
5. IF the MarketData_Table contains no data for a requested role, THEN THE Market_Intelligence_System SHALL return a structured error indicator rather than raising an exception.
