# Requirements Document

## Introduction

The Coaching Agent is the intelligence layer of the REGAIN platform — an AI-powered conversational coaching system that guides veterans, AI-displaced workers, and career pivoters through personalized reskilling campaigns. Built on the AWS Strands Agents SDK with Amazon Nova 2 Sonic for voice interaction and AgentCore Memory for session continuity, the agent conducts conversational onboarding, delivers daily coaching check-ins, generates adaptive missions, extracts evidence from conversations, and integrates market intelligence into coaching guidance. The agent operates against the existing DynamoDB tables and API Gateway endpoints established in the platform-foundation spec.

## Glossary

- **Coaching_Agent**: The Strands-based AI agent that orchestrates all coaching interactions, tool calls, and conversational flows.
- **Transition_Profile**: A structured representation of a user's career background including extracted skills, experience duration, industry, role history, and persona classification, stored in the UserProfiles DynamoDB table.
- **Campaign_Roadmap**: A three-phase reskilling plan (Foundation → Expansion → Launch) generated from the Transition Profile and stored in the Campaigns DynamoDB table.
- **Mission**: A concrete, evidence-producing skill-building task assigned to a user within a campaign phase, stored in the MissionHistory DynamoDB table.
- **Evidence**: A structured record of a completed action, skill demonstration, or reflection extracted from conversation, stored in the EvidenceVault DynamoDB table.
- **Skill_Taxonomy**: A structured classification of user skills into three categories: transferable skills, technical skills, and domain knowledge.
- **AgentCore_Memory**: Amazon Bedrock AgentCore Memory service providing per-user episodic memory with semantic and recency search for conversational continuity.
- **Nova_Sonic_Session**: A bidirectional streaming voice session using Amazon Bedrock Nova 2 Sonic (amazon.nova-sonic-v1:0) for speech-to-speech interaction.
- **Strands_Tool**: A Python function decorated with the Strands @tool decorator that the Coaching Agent can invoke during conversation to read or write platform data.
- **Behavioral_Pattern**: A detected trend in a user's mission completion history, such as consistently skipping a category of missions or favoring certain skill types.
- **Campaign_Phase**: One of three sequential stages in a Campaign Roadmap — Foundation (quick wins, confidence building), Expansion (skill deepening, stretch goals), or Launch (job-ready activities, portfolio completion).

## Requirements

### Requirement 1: Conversational Skill Extraction

**User Story:** As a user beginning my reskilling journey, I want to describe my career background in natural language, so that the system can understand my skills and experience without requiring me to fill out forms.

#### Acceptance Criteria

1. WHEN a user provides a natural language career description, THE Coaching_Agent SHALL extract skills, experience duration, industry, and role history from the conversation.
2. WHEN the Coaching_Agent extracts skills, THE Coaching_Agent SHALL classify each skill into the Skill_Taxonomy categories: transferable skills, technical skills, and domain knowledge.
3. IF the Coaching_Agent cannot extract sufficient information from the user's input, THEN THE Coaching_Agent SHALL ask targeted follow-up questions to fill gaps in the Transition_Profile.
4. WHEN skill extraction is complete, THE Coaching_Agent SHALL write the structured Transition_Profile to the UserProfiles DynamoDB table using the update_user_profile Strands_Tool.

### Requirement 2: Campaign Roadmap Generation

**User Story:** As a user who has completed onboarding, I want a personalized reskilling plan generated from my background, so that I have a structured path toward my target role.

#### Acceptance Criteria

1. WHEN a Transition_Profile is complete, THE Coaching_Agent SHALL generate a Campaign_Roadmap with three sequential phases: Foundation, Expansion, and Launch.
2. WHEN generating a Campaign_Roadmap, THE Coaching_Agent SHALL write the campaign record to the Campaigns DynamoDB table using the create_campaign Strands_Tool.
3. WHEN a Campaign_Roadmap is created, THE Coaching_Agent SHALL generate an initial set of Mission records for the Foundation phase and write them to the MissionHistory DynamoDB table using the generate_mission Strands_Tool.
4. WHEN generating missions, THE Coaching_Agent SHALL produce concrete, evidence-producing tasks that reference specific skills from the user's Transition_Profile.

### Requirement 3: Daily Check-In Coaching

**User Story:** As an active user, I want a daily coaching interaction that reviews my progress and delivers my next mission, so that I stay on track and motivated.

#### Acceptance Criteria

1. WHEN a user initiates a check-in, THE Coaching_Agent SHALL read the user's mission history, campaign status, and evidence records using the appropriate Strands_Tools.
2. WHEN delivering a mission, THE Coaching_Agent SHALL provide context explaining why the mission matters for the user's transition.
3. WHEN a previous mission was completed, THE Coaching_Agent SHALL review the completion and acknowledge the user's progress with evidence-based encouragement.
4. WHEN a previous mission was not completed, THE Coaching_Agent SHALL adapt its coaching tone to provide redirection without judgment.
5. WHEN conducting a check-in, THE Coaching_Agent SHALL use AgentCore_Memory to maintain conversational continuity across sessions.

### Requirement 4: Behavioral Pattern Detection

**User Story:** As a user who may have blind spots in my reskilling approach, I want the coaching agent to detect patterns in my behavior, so that it can guide me toward a balanced skill development.

#### Acceptance Criteria

1. WHEN the Coaching_Agent reads a user's mission history, THE Coaching_Agent SHALL analyze completion patterns to detect Behavioral_Patterns such as skill category avoidance or over-focus.
2. WHEN a Behavioral_Pattern is detected, THE Coaching_Agent SHALL adjust mission selection to address identified gaps.
3. WHEN a Behavioral_Pattern is detected, THE Coaching_Agent SHALL communicate the observation to the user with specific evidence from their mission history.

### Requirement 5: Evidence Extraction from Conversation

**User Story:** As a user describing my accomplishments in conversation, I want the agent to automatically capture evidence of my skills, so that my Evidence Vault grows without manual data entry.

#### Acceptance Criteria

1. WHEN a user describes a completed action, skill demonstration, or reflection during any conversation, THE Coaching_Agent SHALL recognize the statement as evidence.
2. WHEN evidence is recognized, THE Coaching_Agent SHALL extract structured data including skill tags, a description, and artifact references.
3. WHEN evidence is extracted, THE Coaching_Agent SHALL write the Evidence record to the EvidenceVault DynamoDB table using the log_evidence Strands_Tool.
4. WHEN evidence is logged, THE Coaching_Agent SHALL confirm to the user what was captured, including the skill tag and the cumulative evidence count for that skill.

### Requirement 6: Market Intelligence Integration

**User Story:** As a user making career decisions, I want coaching that references real market data, so that my reskilling efforts align with actual job market demand.

#### Acceptance Criteria

1. WHEN delivering coaching or generating missions, THE Coaching_Agent SHALL query the MarketData DynamoDB table using the get_market_insights Strands_Tool for relevant sector trends.
2. WHEN market data is available for the user's target role sector, THE Coaching_Agent SHALL reference specific market trends (job demand, skill gaps, salary ranges) in coaching responses.
3. WHEN generating missions, THE Coaching_Agent SHALL prioritize skills that have high market demand based on MarketData records.

### Requirement 7: Adaptive Mission Generation

**User Story:** As a user progressing through my campaign, I want missions that adapt to my demonstrated strengths, weaknesses, and market conditions, so that my reskilling stays relevant and challenging.

#### Acceptance Criteria

1. WHEN generating a new mission, THE Coaching_Agent SHALL consider the user's Campaign_Phase, Transition_Profile skill gaps, Behavioral_Patterns, and MarketData demand signals.
2. WHEN generating a mission, THE Coaching_Agent SHALL produce a mission with a title, description, target skill tag, and expected evidence type.
3. WHEN a mission is generated, THE Coaching_Agent SHALL write the Mission record to the MissionHistory DynamoDB table using the generate_mission Strands_Tool.
4. WHILE a user is in the Foundation Campaign_Phase, THE Coaching_Agent SHALL generate missions focused on quick wins and confidence building.
5. WHILE a user is in the Expansion Campaign_Phase, THE Coaching_Agent SHALL generate missions focused on skill deepening and stretch goals.
6. WHILE a user is in the Launch Campaign_Phase, THE Coaching_Agent SHALL generate missions focused on job-ready activities and portfolio completion.

### Requirement 8: Voice Interaction via Nova 2 Sonic

**User Story:** As a user who prefers speaking over typing, I want to interact with the coaching agent through voice, so that I can have natural coaching conversations.

#### Acceptance Criteria

1. WHEN a user initiates a voice session, THE system SHALL establish a Nova_Sonic_Session using the Bedrock bidirectional streaming API (InvokeModelWithBidirectionalStream).
2. WHILE a Nova_Sonic_Session is active, THE system SHALL stream audio input and output in PCM 16-bit, 16kHz format between the frontend and the Bedrock endpoint.
3. WHILE a Nova_Sonic_Session is active, THE Coaching_Agent Strands_Tools SHALL be callable asynchronously during the voice conversation.
4. WHEN a voice interaction triggers a Strands_Tool call, THE system SHALL execute the tool and return results to the Nova_Sonic_Session without interrupting the conversation flow.
5. IF a Nova_Sonic_Session cannot be established, THEN THE system SHALL fall back to text-based interaction through the existing API Gateway coaching endpoint.

### Requirement 9: Strands Agent Architecture

**User Story:** As a developer maintaining the platform, I want the coaching agent built on the Strands Agents SDK with clean tool boundaries, so that the agent is extensible and each capability is independently testable.

#### Acceptance Criteria

1. THE Coaching_Agent SHALL be implemented using the Strands Agents SDK Agent class with a configured tool list and model specification.
2. THE Coaching_Agent SHALL use Amazon Nova 2 Lite (model ID configurable via environment variable) as the default inference model.
3. THE Coaching_Agent system prompt SHALL be defined in a dedicated prompts.py file and SHALL define the agent's persona, coaching philosophy, and behavioral rules.
4. WHEN a Strands_Tool is invoked, THE Strands_Tool SHALL return structured dict outputs rather than free-text responses.
5. THE Coaching_Agent SHALL use AgentCore_Memory with per-user namespace isolation for episodic memory storage and retrieval.

### Requirement 10: Session and State Management

**User Story:** As a user returning to the platform, I want the coaching agent to remember our previous conversations, so that coaching feels continuous rather than starting fresh each time.

#### Acceptance Criteria

1. WHEN a coaching session begins, THE Coaching_Agent SHALL retrieve relevant prior conversation context from AgentCore_Memory using semantic and recency search.
2. WHEN a coaching session ends, THE Coaching_Agent SHALL store a summary of the session in AgentCore_Memory for future retrieval.
3. WHEN retrieving memory, THE Coaching_Agent SHALL scope all memory operations to the authenticated user's namespace to prevent cross-user data leakage.
