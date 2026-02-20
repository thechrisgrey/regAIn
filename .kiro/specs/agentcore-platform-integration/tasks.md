# Implementation Plan: AgentCore Platform Integration

## Overview

Migrate the REGAIN Coaching Agent from direct tool invocation to AgentCore Gateway-routed, policy-governed, observable tool access. Implementation follows dependency order: Gateway first (enables everything else), then Policy (depends on Gateway), then Observability (benefits from Gateway traces), then Code Interpreter (stretch, depends on Gateway).

## Tasks

- [x] 1. AgentCore Gateway setup and tool registration
  - [x] 1.1 Create AgentCoreStack CDK stack with Gateway instance
    - Create `infra/stacks/agentcore_stack.py` with `AgentCoreStack` class
    - Provision AgentCore Gateway instance named "regain-coaching-gateway"
    - Configure Gateway inbound authorization with existing Cognito User Pool JWT validation
    - Create IAM roles: Gateway → Lambda invocation, Agent → Gateway access
    - Add CfnOutput for Gateway endpoint URL and Gateway ID
    - Tag all resources with Project=REGAIN, Environment=dev
    - Wire AgentCoreStack into `infra/app.py` with cross-stack references from AuthStack and ApiStack
    - _Requirements: 1.1, 1.5, 14.1, 14.2, 14.3, 14.4_

  - [x] 1.2 Define MCP tool schemas for all 13 tools
    - Create `backend/agents/coaching/tool_schemas.py` containing MCP-compatible schema definitions for all 13 tools
    - Each schema: tool name (regain_ prefix), natural language description, JSON Schema for inputs (with userId marked as JWT-injected), JSON Schema for outputs, required auth claims
    - Schema input types must match existing @tool function signatures exactly
    - Schema output types must match existing tool return dict shapes
    - Include get_alignment (currently unregistered, adding to agent tool set)
    - _Requirements: 1.3, 2.1, 2.2, 2.3_

  - [x] 1.3 Register tool schemas in Gateway via CDK
    - In AgentCoreStack, register all 13 tool schemas with their Lambda function ARN targets
    - Map tools to correct Lambda targets: coaching tools → Coaching Lambda, mission tools → Missions Lambda, evidence tools → Evidence Lambda, market tools → Market Intel Lambda, dashboard tools → Dashboard Lambda
    - Enable semantic tool discovery on the Gateway instance
    - _Requirements: 1.2, 1.4_

  - [x] 1.4 Write property test for MCP schema correctness
    - **Property 1: MCP schema correctness**
    - For each registered tool, verify schema input params match @tool function signature via inspect.signature, output schema matches return dict shape, and description is non-empty
    - **Validates: Requirements 1.3, 2.1, 2.2, 2.3**

- [x] 2. Gateway client and agent migration
  - [x] 2.1 Create Gateway client module
    - Create `backend/agents/coaching/gateway_client.py` with `GatewayToolClient` class
    - Implement `discover_tools()` — calls Gateway MCP endpoint, returns tool list compatible with Strands Agent tool format
    - Implement `invoke_tool(tool_name, params)` — sends tool invocation to Gateway with JWT token, handles response and error parsing
    - Handle Gateway errors: return structured error dicts matching existing tool error contract
    - Configure Gateway endpoint URL and ID from environment variables
    - _Requirements: 3.1, 3.2, 3.5_

  - [x] 2.2 Migrate agent.py to use Gateway-routed tools
    - Update `create_coaching_agent()` to accept `jwt_token` parameter
    - Replace direct tool imports with Gateway tool discovery via `GatewayToolClient`
    - Add `get_alignment` to the agent's tool set (previously defined but unregistered)
    - Add environment variables: AGENTCORE_GATEWAY_ID, AGENTCORE_GATEWAY_ENDPOINT
    - _Requirements: 3.1, 3.2_

  - [x] 2.3 Update Coaching Lambda handler to pass JWT to agent
    - Update `backend/lambda/coaching/handler.py` to extract full JWT token from request and pass to `create_coaching_agent()`
    - Update Voice Lambda handler similarly
    - Add Gateway environment variables to Lambda configuration in AgentStack CDK
    - _Requirements: 3.2, 1.6_

  - [x] 2.4 Write property test for Gateway routing equivalence
    - **Property 3: Gateway routing equivalence**
    - For random valid tool parameters, verify Gateway-routed invocation produces same result as direct invocation
    - Mock Gateway to forward to actual tool functions
    - **Validates: Requirements 3.3, 3.4**

  - [x] 2.5 Write property test for JWT validation and userId injection
    - **Property 2: JWT validation and userId injection**
    - For random valid JWTs, verify userId injected into tool context matches JWT claims; for invalid JWTs, verify rejection
    - **Validates: Requirements 1.5, 1.6**

- [x] 3. Checkpoint — Gateway integration
  - Ensure all tests pass, ask the user if questions arise.
  - Verify: AgentCoreStack synthesizes, Gateway client connects, agent discovers tools, tool invocations route through Gateway

- [x] 4. Cedar policy definitions and enforcement
  - [x] 4.1 Implement user data isolation policy
    - Define Cedar policy document in AgentCoreStack: permit tool invocation only when request userId matches JWT userId
    - Attach policy to Gateway instance
    - _Requirements: 4.1, 4.2, 4.3_

  - [x] 4.2 Implement evidence write scope policy
    - Define Cedar policy: permit log_evidence only when session is active AND timestamp within 24h
    - Campaign-completed check stays in Lambda tool logic (not Cedar) — add campaign status validation to `log_evidence` in tools.py if not already present
    - Attach policy to Gateway instance
    - _Requirements: 5.1, 5.2, 5.3_

  - [x] 4.3 Implement mission generation rate limit
    - Add `dailyMissionGenCount` (Number) and `lastMissionGenDate` (String) attributes to UserProfiles table schema (no new table — just new attributes)
    - Update `generate_mission` in tools.py to use DynamoDB conditional update: `ADD dailyMissionGenCount 1` with condition `dailyMissionGenCount < 3`, reset counter when `lastMissionGenDate != today`
    - Define Cedar policy as defense-in-depth backstop: permit generate_mission when context.daily_generation_count < 3
    - Attach policy to Gateway instance
    - _Requirements: 6.1, 6.2, 6.3_

  - [x] 4.4 Implement profile update restrictions policy
    - Build Gateway context builder logic: check if all update field keys are in allowed set, set `context.all_fields_allowed` boolean
    - Define Cedar policy: permit update_user_profile when context.all_fields_allowed == true
    - Attach policy to Gateway instance
    - _Requirements: 7.1, 7.2, 7.3_

  - [x] 4.5 Implement market data read-only policy
    - Define Cedar policy: permit regain_get_market_insights and regain_get_alignment; deny write/update/delete on MarketData
    - Attach policy to Gateway instance
    - _Requirements: 8.1, 8.2, 8.3_

  - [x] 4.6 Write property test for user data isolation
    - **Property 4: User data isolation**
    - For random (request userId, JWT userId) pairs, verify permit iff match, deny iff mismatch
    - **Validates: Requirements 4.1, 4.2**

  - [x] 4.7 Write property test for evidence write scope
    - **Property 5: Evidence write scope enforcement**
    - For random (session_active, timestamp_age) tuples, verify permit iff both conditions met
    - **Validates: Requirements 5.1, 5.2**

  - [x] 4.8 Write property test for mission generation rate limit and counter atomicity
    - **Property 6: Mission generation rate limit**
    - For random (user_id, daily_count 0-10), verify permit iff count < 3
    - **Property 7: Mission generation counter atomicity**
    - Verify DynamoDB conditional update increments by 1 and rejects at count >= 3
    - **Validates: Requirements 6.1, 6.2, 6.3**

  - [x] 4.9 Write property test for profile update field restrictions
    - **Property 8: Profile update field restrictions**
    - For random subsets of allowed + restricted field names, verify permit iff all fields in allowed set
    - **Validates: Requirements 7.1, 7.2**

  - [x] 4.10 Write property test for market data read-only enforcement
    - **Property 9: Market data read-only enforcement**
    - For random (tool_name, operation_type) pairs, verify reads permitted and writes denied
    - **Validates: Requirements 8.1, 8.2**

- [x] 5. Policy audit logging
  - [x] 5.1 Configure policy evaluation audit logging
    - Configure Gateway to log all policy evaluation results to CloudWatch
    - Log fields: tool name, userId, policy name, evaluation result (permit/deny), timestamp
    - For denials: additionally log denial reason and request context (excluding sensitive data)
    - _Requirements: 9.1, 9.2, 9.3_

  - [x] 5.2 Write property test for audit log completeness
    - **Property 10: Policy audit log completeness**
    - Trigger policy evaluations, verify log entries contain all required fields
    - **Validates: Requirements 4.3, 9.1, 9.2**

- [x] 6. Checkpoint — Policy enforcement
  - Ensure all tests pass, ask the user if questions arise.
  - Verify: all 5 Cedar policies attached, denials logged, rate limiting atomic

- [x] 7. AgentCore Observability and monitoring
  - [x] 7.1 Configure AgentCore Observability tracing
    - Enable AgentCore Observability on the Gateway instance
    - Configure OpenTelemetry trace export to CloudWatch
    - Trace spans auto-captured: Gateway routing, policy evaluation, Lambda execution
    - Add agent-level instrumentation for session root span, model inference spans, and memory operation spans
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

  - [x] 7.2 Create CloudWatch dashboard
    - Define "REGAIN-Coaching-Operations" dashboard in AgentCoreStack CDK
    - Top row: session count time series, active users counter, error rate gauge
    - Middle row: tool invocation heatmap, policy denial log table, token usage stacked area
    - Bottom row: latency percentile line charts, memory operation bar charts
    - _Requirements: 11.1, 11.2, 11.3, 11.4_

  - [x] 7.3 Create SNS topic and CloudWatch alarms
    - Create SNS topic "RegainCoachingAlerts" in AgentCoreStack
    - Alarm 1: error rate > 10% over 5 minutes
    - Alarm 2: p95 latency > 5 seconds
    - Alarm 3: policy denial count > 20 in 1 minute
    - _Requirements: 12.1, 12.2, 12.3_

  - [x] 7.4 Write property test for trace span completeness
    - **Property 12: Trace span completeness**
    - For random operations, verify trace spans contain required fields per operation type
    - **Validates: Requirements 10.2, 10.3**

  - [x] 7.5 Write property test for input schema validation
    - **Property 11: Input schema validation**
    - For random valid and invalid payloads per tool schema, verify accept/reject behavior
    - **Validates: Requirements 2.4, 2.5**

- [x] 8. Checkpoint — Observability
  - Ensure all tests pass, ask the user if questions arise.
  - Verify: traces appear in CloudWatch, dashboard renders, alarms configured

- [x] 9. Code Interpreter integration (Stretch Goal)
  - [x] 9.1 Register Code Interpreter as Gateway tool
    - Add Code Interpreter tool schema to tool_schemas.py
    - Register in Gateway with sandbox constraints: matplotlib, pandas, numpy only; no network; 30s timeout; 512MB memory
    - Create S3 bucket for output files with 24h lifecycle in AgentCoreStack
    - _Requirements: 13.2, 13.4, 13.5_

  - [x] 9.2 Implement Code Interpreter invocation in Gateway client
    - Add code execution method to GatewayToolClient
    - Handle output file upload to S3 and presigned URL generation (1hr expiry)
    - Ensure only agent-generated code is accepted (no user-submitted code passthrough)
    - _Requirements: 13.1, 13.3, 13.6_

  - [x] 9.3 Write property test for Code Interpreter output URL
    - **Property 13: Code interpreter output URL**
    - For random matplotlib code that produces files, verify presigned S3 URL in response
    - **Validates: Requirements 13.3**

- [x] 10. Final checkpoint
  - Ensure all tests pass, ask the user if questions arise.
  - Verify end-to-end: agent discovers tools via Gateway, invokes with JWT, policies enforce, traces captured, dashboard shows data

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Gateway tasks (1-3) must complete before Policy (4-6) and Observability (7-8)
- Code Interpreter (9) is a stretch goal — implement only after 1-8 are complete
- Property tests validate universal correctness properties from the design document
- All infrastructure is CDK-managed in the new AgentCoreStack
- No new DynamoDB tables — only new attributes on UserProfiles for rate limiting
