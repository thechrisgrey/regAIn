# Requirements Document

## Introduction

This specification upgrades the REGAIN Coaching Agent from direct Strands @tool invocation to a fully instrumented, policy-governed, production-grade agentic system using Amazon Bedrock AgentCore platform services. The integration wraps the existing 12 coaching tools in AgentCore Gateway for unified MCP-compatible access, adds Cedar-based policy enforcement for fine-grained access control, instruments the agent with AgentCore Observability for production monitoring, and optionally enables AgentCore Code Interpreter for dynamic visualization. All existing Lambda tool logic, DynamoDB tables, Cognito auth, and API Gateway routes remain unchanged — Gateway wraps existing functions, it does not replace them.

## Glossary

- **AgentCore_Gateway**: Amazon Bedrock AgentCore Gateway service that provides unified, MCP-compatible tool management with centralized auth, logging, and access control for agent tool invocations.
- **MCP_Tool_Schema**: A Model Context Protocol-compatible tool definition specifying name, description, typed input/output JSON Schema, and required auth claims for a single tool function.
- **Cedar_Policy**: A fine-grained access control policy written in the Cedar policy language, evaluated at the Gateway layer to permit or deny tool invocations based on request context, user identity, and resource attributes.
- **AgentCore_Observability**: Amazon Bedrock AgentCore Observability service providing OpenTelemetry-based distributed tracing, metrics, and dashboards for agent sessions and tool invocations.
- **AgentCore_Code_Interpreter**: Amazon Bedrock AgentCore Code Interpreter service providing sandboxed Python execution environments for dynamic data visualization and analysis.
- **Coaching_Agent**: The existing Strands-based AI agent that orchestrates coaching interactions, now routing tool calls through AgentCore Gateway instead of direct invocation.
- **Tool_Invocation**: A single call from the Coaching_Agent to one of the 12 registered tools, routed through AgentCore_Gateway with policy evaluation and trace capture.
- **Policy_Denial**: An event where a Cedar_Policy evaluation rejects a Tool_Invocation, logged for audit and returned as a structured error to the Coaching_Agent.
- **Coaching_Session**: A bounded interaction between a user and the Coaching_Agent, spanning from initial message through all tool calls to final response, captured as a single distributed trace.
- **CloudWatch_Dashboard**: An AWS CloudWatch dashboard aggregating operational metrics, traces, and alerts for the REGAIN coaching system.
- **Gateway_Authorization**: The process by which AgentCore_Gateway validates Cognito JWT tokens and injects authenticated user identity (userId from JWT claims) into Tool_Invocation context.
- **Trace_Span**: A single unit of work within a distributed trace, representing one operation such as a model inference call, a Tool_Invocation, or a Cedar_Policy evaluation.

## Requirements

### Requirement 1: AgentCore Gateway Instance and Tool Registration

**User Story:** As a platform operator, I want all coaching agent tool invocations routed through a centralized gateway, so that tool access is unified, logged, and controllable from a single management plane.

#### Acceptance Criteria

1. THE AgentCore_Gateway SHALL be provisioned as a single instance named "regain-coaching-gateway" in us-east-1.
2. WHEN the AgentCore_Gateway is provisioned, THE AgentCore_Gateway SHALL register all 13 Coaching_Agent tools (the 12 currently active tools plus the existing but unregistered get_alignment tool) as MCP-compatible tool endpoints backed by the existing Lambda function ARNs.
3. WHEN a tool is registered, THE AgentCore_Gateway SHALL store an MCP_Tool_Schema containing the tool name, natural language description, typed JSON Schema for inputs, typed JSON Schema for outputs, and required auth claims.
4. THE AgentCore_Gateway SHALL expose a semantic discovery endpoint so the Coaching_Agent can find tools via natural language query.
5. WHEN the AgentCore_Gateway receives a Tool_Invocation request, THE AgentCore_Gateway SHALL validate the accompanying Cognito JWT token using the existing User Pool configuration before routing the request.
6. WHEN the AgentCore_Gateway validates a JWT token, THE AgentCore_Gateway SHALL extract the userId from the token claims and inject it into the Tool_Invocation context so that tools receive the authenticated userId from Gateway_Authorization rather than from agent-supplied parameters.

### Requirement 2: MCP Tool Schema Definitions

**User Story:** As a platform developer, I want each coaching tool to have a precise, typed schema definition, so that the gateway can validate inputs, document outputs, and enable semantic tool discovery.

#### Acceptance Criteria

1. WHEN defining an MCP_Tool_Schema for a tool, THE MCP_Tool_Schema SHALL specify all required and optional input parameters with JSON Schema types matching the existing Strands @tool function signatures.
2. WHEN defining an MCP_Tool_Schema for a tool, THE MCP_Tool_Schema SHALL specify the output structure with JSON Schema types matching the existing tool return dict shapes.
3. THE MCP_Tool_Schema for each tool SHALL include a natural language description suitable for semantic discovery by the Coaching_Agent.
4. WHEN the AgentCore_Gateway receives a Tool_Invocation, THE AgentCore_Gateway SHALL validate the input payload against the registered MCP_Tool_Schema before forwarding to the Lambda target.
5. IF a Tool_Invocation input fails schema validation, THEN THE AgentCore_Gateway SHALL return a structured error containing the validation failure details without invoking the Lambda target.

### Requirement 3: Agent Migration to Gateway-Routed Tool Invocation

**User Story:** As a platform developer, I want the coaching agent to invoke tools through the gateway instead of direct function imports, so that all tool calls pass through centralized auth, policy, and observability layers.

#### Acceptance Criteria

1. WHEN the Coaching_Agent is initialized, THE Coaching_Agent SHALL discover available tools from the AgentCore_Gateway endpoint instead of importing tool functions directly from the tools module.
2. WHEN the Coaching_Agent invokes a tool, THE Coaching_Agent SHALL send the Tool_Invocation request to the AgentCore_Gateway endpoint with the user's Cognito JWT token attached.
3. WHEN the AgentCore_Gateway routes a Tool_Invocation to a Lambda target, THE existing Lambda handler logic SHALL execute without modification.
4. WHEN the Coaching_Agent receives a tool response from the AgentCore_Gateway, THE Coaching_Agent SHALL process the response identically to how it processed direct tool return values.
5. IF the AgentCore_Gateway is unreachable, THEN THE Coaching_Agent SHALL return a structured error indicating gateway unavailability rather than falling back to direct tool invocation.

### Requirement 4: User Data Isolation Policy

**User Story:** As a platform operator, I want to enforce that the coaching agent can only access data belonging to the authenticated user, so that no cross-user data leakage is possible regardless of agent behavior.

#### Acceptance Criteria

1. THE Cedar_Policy for user data isolation SHALL permit a Tool_Invocation only when the userId parameter in the request matches the userId extracted from the JWT claims by Gateway_Authorization.
2. IF a Tool_Invocation contains a userId that does not match the authenticated user's JWT claims, THEN THE AgentCore_Gateway SHALL deny the request and return a Policy_Denial with reason "cross-user access denied".
3. WHEN a Policy_Denial occurs for user data isolation, THE AgentCore_Gateway SHALL log the denial event to CloudWatch including the requesting userId, the target userId, the tool name, and a timestamp.

### Requirement 5: Evidence Write Scope Policy

**User Story:** As a platform operator, I want to restrict evidence creation to active coaching sessions with valid timestamps, so that the agent cannot bulk-create, backdate, or fabricate evidence records.

#### Acceptance Criteria

1. THE Cedar_Policy for evidence write scope SHALL permit the log_evidence tool only when the Coaching_Session is active.
2. THE Cedar_Policy for evidence write scope SHALL permit the log_evidence tool only when the evidence timestamp is within the last 24 hours.
3. WHEN the associated campaign status is "completed", THE log_evidence Lambda tool logic SHALL reject the evidence write and return a structured error, enforced in the Lambda handler rather than in Cedar to avoid requiring Gateway DynamoDB access to the Campaigns table.
4. IF a log_evidence Tool_Invocation violates the evidence write scope Cedar_Policy, THEN THE AgentCore_Gateway SHALL deny the request and return a Policy_Denial with reason "evidence write scope violation".

### Requirement 6: Mission Generation Rate Limit Policy

**User Story:** As a platform operator, I want to limit how many missions the agent can generate per user per day, so that runaway generation loops are prevented.

#### Acceptance Criteria

1. THE Cedar_Policy for mission generation rate limiting SHALL permit the generate_mission tool only when the daily generation count for the authenticated user is fewer than 3, serving as a defense-in-depth backstop.
2. IF a generate_mission Tool_Invocation exceeds the daily rate limit, THEN THE AgentCore_Gateway SHALL deny the request and return a Policy_Denial with reason "daily mission generation limit reached".
3. WHEN a generate_mission Tool_Invocation is permitted, THE generate_mission Lambda tool logic SHALL atomically increment the dailyMissionGenCount attribute on the UserProfiles DynamoDB table using a conditional update (condition: dailyMissionGenCount < 3) to prevent concurrent over-generation.

### Requirement 7: Profile Update Restrictions Policy

**User Story:** As a platform operator, I want to restrict which user profile fields the coaching agent can modify, so that auth-related and administrative fields are protected from agent writes.

#### Acceptance Criteria

1. THE Cedar_Policy for profile update restrictions SHALL permit the update_user_profile tool only when the modified fields are within the allowed set: skills, experience, targetRoles, preferences, transferable_skills, technical_skills, domain_knowledge, experience_years, industry, role_history, persona, onboarding_completed, and target_role.
2. THE Cedar_Policy for profile update restrictions SHALL deny the update_user_profile tool when the modified fields include any of: email, cognitoId, role, tier, userId.
3. IF an update_user_profile Tool_Invocation attempts to modify a restricted field, THEN THE AgentCore_Gateway SHALL deny the request and return a Policy_Denial with reason "restricted field modification denied" including the list of disallowed fields.

### Requirement 8: Market Data Read-Only Policy

**User Story:** As a platform operator, I want to enforce that the coaching agent can only read market intelligence data, so that market data integrity is maintained exclusively by the scheduled pipeline.

#### Acceptance Criteria

1. THE Cedar_Policy for market data access SHALL permit the get_market_insights and get_alignment tools for read operations on MarketData.
2. THE Cedar_Policy for market data access SHALL deny any Tool_Invocation that would write, update, or delete MarketData records when initiated by the Coaching_Agent.
3. IF a write operation on MarketData is attempted by the Coaching_Agent, THEN THE AgentCore_Gateway SHALL deny the request and return a Policy_Denial with reason "market data is read-only for coaching agent".

### Requirement 9: Policy Audit Logging

**User Story:** As a platform operator, I want all policy evaluation results logged for audit, so that I can review access patterns and investigate security incidents.

#### Acceptance Criteria

1. WHEN a Cedar_Policy evaluation occurs, THE AgentCore_Gateway SHALL log the evaluation result (permit or deny) to CloudWatch with the tool name, userId, policy name, and timestamp.
2. WHEN a Policy_Denial occurs, THE AgentCore_Gateway SHALL log the denial with the full request context including tool name, input parameters (excluding sensitive data), policy name, denial reason, userId, and timestamp.
3. THE policy evaluation step SHALL add less than 50 milliseconds of latency to each Tool_Invocation.

### Requirement 10: Distributed Tracing

**User Story:** As a platform operator, I want end-to-end distributed traces for every coaching session, so that I can diagnose latency issues and understand the full request flow.

#### Acceptance Criteria

1. WHEN a Coaching_Session begins, THE AgentCore_Observability SHALL create a root Trace_Span that encompasses the entire session from user message to final response.
2. WHEN the Coaching_Agent invokes a model for inference, THE AgentCore_Observability SHALL create a child Trace_Span capturing model ID, input token count, output token count, and inference latency.
3. WHEN a Tool_Invocation is routed through the AgentCore_Gateway, THE AgentCore_Observability SHALL create a child Trace_Span capturing tool name, Gateway routing latency, policy evaluation result, Lambda execution latency, and DynamoDB read/write latency.
4. THE AgentCore_Observability SHALL export all traces via OpenTelemetry protocol to CloudWatch.

### Requirement 11: Operational Metrics and Dashboard

**User Story:** As a platform operator, I want a centralized dashboard showing coaching system health, usage patterns, and performance metrics, so that I can monitor operations and detect issues proactively.

#### Acceptance Criteria

1. THE AgentCore_Observability SHALL emit CloudWatch metrics for: session count (daily and weekly), average session duration, Tool_Invocation count by tool name, Tool_Invocation latency percentiles (p50, p95, p99) by tool name, Policy_Denial count by policy name, token usage per session (input and output), error rate by tool and error type, model inference latency, and memory read/write latency.
2. THE CloudWatch_Dashboard named "REGAIN-Coaching-Operations" SHALL display a top row with session count time series, active users counter, and error rate gauge.
3. THE CloudWatch_Dashboard SHALL display a middle row with Tool_Invocation heatmap by tool and time, Policy_Denial log table, and token usage stacked area chart.
4. THE CloudWatch_Dashboard SHALL display a bottom row with latency percentile line charts and memory operation bar charts.

### Requirement 12: Operational Alerting

**User Story:** As a platform operator, I want automated alerts for anomalous conditions, so that I am notified of issues before they impact users.

#### Acceptance Criteria

1. WHEN the coaching system error rate exceeds 10% over a 5-minute window, THE alerting system SHALL send a notification to the configured SNS topic.
2. WHEN the p95 Tool_Invocation latency exceeds 5 seconds, THE alerting system SHALL send a notification to the configured SNS topic.
3. WHEN Policy_Denial count exceeds 20 within a 1-minute window, THE alerting system SHALL send a notification to the configured SNS topic.

### Requirement 13: Code Interpreter for Dynamic Visualization (Stretch Goal)

**User Story:** As a user reviewing my reskilling progress, I want the coaching agent to generate visual charts and data exports on demand, so that I can see my growth in graphical form.

#### Acceptance Criteria

1. WHEN a user requests a visual representation of their progress data, THE Coaching_Agent SHALL generate Python code using matplotlib or pandas and execute it via the AgentCore_Code_Interpreter.
2. WHEN the AgentCore_Code_Interpreter executes generated code, THE AgentCore_Code_Interpreter SHALL run in a sandboxed environment with access to matplotlib, pandas, and numpy, and without access to network, external filesystem, or AWS credentials.
3. WHEN the AgentCore_Code_Interpreter produces an output file (chart image or CSV), THE system SHALL upload the file to S3 and return a presigned URL to the user.
4. THE AgentCore_Code_Interpreter session SHALL auto-terminate after 5 minutes of inactivity.
5. THE AgentCore_Code_Interpreter SHALL enforce a maximum execution time of 30 seconds per code run and a maximum memory allocation of 512MB per session.
6. THE Coaching_Agent SHALL be the sole generator of code for the AgentCore_Code_Interpreter — users SHALL NOT submit arbitrary code for execution.

### Requirement 14: Infrastructure as Code

**User Story:** As a platform developer, I want all AgentCore resources defined in CDK, so that infrastructure is version-controlled, repeatable, and consistent with the existing stack pattern.

#### Acceptance Criteria

1. THE CDK infrastructure SHALL define all AgentCore_Gateway, Cedar_Policy, AgentCore_Observability, and alerting resources in a dedicated AgentCoreStack or as an extension of the existing AgentStack.
2. WHEN the CDK stack is deployed, THE stack SHALL create IAM roles for Gateway-to-Lambda invocation, Gateway-to-Policy evaluation, and Agent-to-Gateway access.
3. THE CDK stack SHALL use CfnOutput and cross-stack references to share the AgentCore_Gateway endpoint URL and other resource identifiers with dependent stacks.
4. THE CDK stack SHALL tag all created resources with Project=REGAIN and Environment=dev.
