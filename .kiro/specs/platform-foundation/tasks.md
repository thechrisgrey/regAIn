# Implementation Plan: Platform Foundation

## Overview

This implementation plan establishes the REGAIN platform foundation through incremental, testable steps. The approach follows this sequence:

1. Initialize CDK project and directory structure
2. Create shared utilities for Lambda functions
3. Implement infrastructure stacks (Auth, Data, API)
4. Build frontend shell with authentication
5. Wire everything together with integration points

Each task builds on previous work, with checkpoints to validate progress. Testing tasks are marked as optional (*) for faster MVP iteration.

## Tasks

- [x] 1. Initialize CDK project and directory structure
  - Create infra/app.py as CDK entry point
  - Create infra/requirements.txt with aws-cdk-lib and constructs
  - Create complete directory structure per project conventions
  - Set up Python virtual environment for CDK
  - _Requirements: 1.1, 1.2, 2.1, 2.2, 2.3, 2.4, 2.5_

- [x] 2. Create shared Python utilities for Lambda functions
  - [x] 2.1 Implement DynamoDB data access layer (backend/lambda/shared/dynamodb.py)
    - Create DynamoDBClient class with get_item, put_item, query, update_item methods
    - Read table names from environment variables
    - Add type hints and docstrings
    - _Requirements: 3.1, 3.2_
  
  - [x] 2.2 Implement response helpers (backend/lambda/shared/responses.py)
    - Create success_response and error_response functions
    - Include CORS headers
    - _Requirements: 3.3_
  
  - [x] 2.3 Implement environment configuration (backend/lambda/shared/config.py)
    - Create Config class with environment variable accessors
    - _Requirements: 3.4_
  
  - [x] 2.4 Implement data models (backend/lambda/shared/models.py)
    - Create UserProfile, Campaign, Mission, Evidence dataclasses
    - Add to_dynamodb_item and from_dynamodb_item methods
    - _Requirements: 3.1_
  
  - [x] 2.5 Write property test for environment-based table configuration
    - **Property 3: Environment-Based Table Configuration**
    - **Validates: Requirements 3.2**


- [x] 3. Implement Authentication Stack (infra/stacks/auth_stack.py)
  - [x] 3.1 Create AuthStack class with Cognito User Pool
    - Configure email sign-in and verification
    - Create User Pool Client with SRP auth flow (no client secret)
    - Add CloudFormation outputs for User Pool ID and Client ID
    - Apply resource tags (Project=REGAIN, Environment=dev)
    - Update infra/app.py to instantiate AuthStack
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 8.1, 8.4, 8.5, 8.6_
  
  - [x] 3.2 Write unit test for AuthStack configuration
    - Verify User Pool has email sign-in enabled
    - Verify User Pool Client has correct auth flow
    - Verify CloudFormation outputs exist
    - _Requirements: 4.1, 4.2, 4.3, 4.4_
  
  - [x] 3.3 Write property test for resource tagging
    - **Property 2: Resource Tagging Consistency**
    - **Validates: Requirements 1.4, 8.5, 8.6**

- [x] 4. Implement Data Stack (infra/stacks/data_stack.py)
  - [x] 4.1 Create DataStack class with all DynamoDB tables
    - Create UserProfiles table (PK: userId)
    - Create Campaigns table (PK: userId, SK: campaignId) with status GSI
    - Create MissionHistory table (PK: userId, SK: missionId) with status and date GSIs
    - Create EvidenceVault table (PK: userId, SK: evidenceId) with skill_tag GSI
    - Create MarketData table (PK: sector, SK: timestamp)
    - Use on-demand billing for all tables
    - Add CloudFormation outputs for all table names and ARNs
    - Apply resource tags
    - Update infra/app.py to instantiate DataStack
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 5.10, 5.11, 5.12, 8.2, 8.4, 8.5, 8.6, 9.1, 9.4_
  
  - [ ]* 4.2 Write property test for on-demand billing mode
    - **Property 4: On-Demand Billing Mode**
    - **Validates: Requirements 5.10, 9.1, 9.4**
  
  - [ ]* 4.3 Write property test for table output completeness
    - **Property 5: Table Output Completeness**
    - **Validates: Requirements 5.11, 5.12**

- [ ] 5. Checkpoint - Verify CDK synthesis
  - Run `cdk synth` to generate CloudFormation templates
  - Verify all stacks synthesize without errors
  - Review generated templates for correctness
  - Ensure all tests pass, ask the user if questions arise.


- [ ] 6. Implement Lambda handlers and service modules
  - [ ] 6.1 Create onboarding Lambda (backend/lambda/onboarding/)
    - Create handler.py with lambda_handler function (thin handler pattern)
    - Create service.py with OnboardingService class containing business logic
    - Implement create_profile method to write to UserProfiles and Campaigns tables
    - Add input validation for required fields
    - Create requirements.txt with boto3
    - _Requirements: 6.2, 6.12, 6.13_
  
  - [ ] 6.2 Create missions Lambda (backend/lambda/missions/)
    - Create handler.py with lambda_handler for GET /missions and POST /missions/{missionId}/complete
    - Create service.py with MissionsService class
    - Implement list_missions and complete_mission methods
    - Add input validation
    - _Requirements: 6.3, 6.4, 6.12, 6.13_
  
  - [ ] 6.3 Create evidence Lambda (backend/lambda/evidence/)
    - Create handler.py with lambda_handler for GET /evidence
    - Create service.py with EvidenceService class
    - Implement list_evidence method with optional skill_tag filtering
    - _Requirements: 6.5, 6.12, 6.13_
  
  - [ ] 6.4 Create coaching Lambda (backend/lambda/coaching/)
    - Create handler.py with lambda_handler for POST /coaching/checkin
    - Create service.py with CoachingService class (placeholder for future agent integration)
    - Implement basic checkin method
    - _Requirements: 6.6, 6.12, 6.13_
  
  - [ ] 6.5 Create dashboard Lambda (backend/lambda/dashboard/)
    - Create handler.py with lambda_handler for GET /dashboard
    - Create service.py with DashboardService class
    - Implement get_dashboard method to aggregate campaign stats
    - _Requirements: 6.7, 6.12, 6.13_
  
  - [ ]* 6.6 Write unit tests for Lambda handlers
    - Test that each handler validates input
    - Test that each handler calls service module correctly
    - Test error handling for invalid input
    - **Property 14: Handler Test Verification**
    - **Validates: Requirements 10.2**
  
  - [ ]* 6.7 Write property test for thin handler pattern
    - **Property 10: Thin Handler Pattern**
    - **Validates: Requirements 6.12**


- [ ] 7. Implement API Stack (infra/stacks/api_stack.py)
  - [ ] 7.1 Create ApiStack class with API Gateway and Lambda integrations
    - Create REST API with Cognito authorizer using User Pool from AuthStack
    - Create Lambda functions for all handlers (onboarding, missions, evidence, coaching, dashboard)
    - Configure Lambda environment variables with table names from DataStack
    - Grant IAM permissions to Lambda functions for required DynamoDB tables only
    - Create API Gateway resources and methods for all endpoints
    - Enable CORS on all endpoints
    - Apply resource tags
    - Update infra/app.py to instantiate ApiStack with cross-stack references (AuthStack, DataStack)
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9, 6.10, 6.11, 8.3, 8.4, 8.5, 8.6, 9.2_
  
  - [ ]* 7.2 Write property test for API authorization enforcement
    - **Property 6: API Authorization Enforcement**
    - **Validates: Requirements 6.8**
  
  - [ ]* 7.3 Write property test for Lambda runtime consistency
    - **Property 7: Lambda Runtime Consistency**
    - **Validates: Requirements 6.9, 9.2**
  
  - [ ]* 7.4 Write property test for Lambda environment configuration
    - **Property 8: Lambda Environment Configuration**
    - **Validates: Requirements 6.10**
  
  - [ ]* 7.5 Write property test for least-privilege IAM permissions
    - **Property 9: Least-Privilege IAM Permissions**
    - **Validates: Requirements 6.11**

- [ ] 8. Verify and finalize CDK app wiring
  - [ ] 8.1 Verify all stacks are correctly wired in infra/app.py
    - Confirm AuthStack, DataStack, and ApiStack are instantiated
    - Confirm cross-stack references are correct (User Pool to ApiStack, tables to ApiStack)
    - Confirm environment is configured (region: us-east-1, account: 563170906428)
    - Clean up any inconsistencies from incremental additions
    - _Requirements: 1.1, 1.4_
  
  - [ ]* 8.2 Write property test for CDK synthesis validity
    - **Property 1: CDK Synthesis Validity**
    - **Validates: Requirements 1.3**
  
  - [ ]* 8.3 Write property test for resource naming convention
    - **Property 13: Resource Naming Convention**
    - **Validates: Requirements 8.4**

- [ ] 9. Checkpoint - Verify complete infrastructure
  - Run `cdk synth` to generate all CloudFormation templates
  - Review Lambda function configurations
  - Verify IAM permissions are least-privilege
  - Verify all cross-stack references are correct
  - Ensure all tests pass, ask the user if questions arise.


- [ ] 10. Initialize frontend React application
  - [ ] 10.1 Create React + TypeScript project with Vite
    - Scaffold Vite into a temp directory, then move contents into existing frontend/ to avoid nesting
    - Configure Tailwind CSS (install dependencies, create tailwind.config.js)
    - Set up project structure (components, pages, hooks, services, types directories)
    - _Requirements: 7.1, 7.2, 2.4_
  
  - [ ] 10.2 Install and configure dependencies
    - Install React Router v6
    - Install AWS Amplify Auth library
    - Configure Amplify with Cognito User Pool ID and Client ID
    - Create .env file for API URL and Cognito configuration
    - _Requirements: 7.3, 7.4_

- [ ] 11. Implement authentication layer
  - [ ] 11.1 Create authentication context (src/hooks/useAuth.tsx)
    - Implement AuthProvider with Amplify Auth integration
    - Implement useAuth hook with signIn, signOut, getToken methods
    - Handle authentication state management
    - _Requirements: 7.4_
  
  - [ ] 11.2 Create Login component (src/components/Login.tsx)
    - Implement email/password login form
    - Handle authentication errors
    - Redirect to dashboard on successful login
    - _Requirements: 7.4_
  
  - [ ] 11.3 Create ProtectedRoute component (src/components/ProtectedRoute.tsx)
    - Check authentication status
    - Redirect to login if not authenticated
    - Show loading state while checking auth
    - _Requirements: 7.5_
  
  - [ ]* 11.4 Write property test for protected route authentication
    - **Property 11: Protected Route Authentication**
    - **Validates: Requirements 7.5**

- [ ] 12. Implement API client layer
  - [ ] 12.1 Create API service (src/services/api.ts)
    - Implement apiRequest helper function with authentication headers
    - Create typed API functions for all endpoints (onboarding, missions, evidence, dashboard)
    - Handle API errors with custom ApiError class
    - _Requirements: 7.7, 7.8_
  
  - [ ] 12.2 Create TypeScript types (src/types/index.ts)
    - Define UserProfile, Campaign, Mission, Evidence interfaces
    - Define API request/response types
    - _Requirements: 7.7_
  
  - [ ]* 12.3 Write property test for API request authentication
    - **Property 12: API Request Authentication**
    - **Validates: Requirements 7.8**


- [ ] 13. Implement custom hooks for API interactions
  - [ ] 13.1 Create useOnboarding hook (src/hooks/useOnboarding.ts)
    - Implement hook for calling POST /onboarding endpoint
    - Handle loading and error states
    - _Requirements: 7.3_
  
  - [ ] 13.2 Create useMissions hook (src/hooks/useMissions.ts)
    - Implement hook for GET /missions and POST /missions/{missionId}/complete
    - Handle loading and error states
    - _Requirements: 7.3_
  
  - [ ] 13.3 Create useEvidence hook (src/hooks/useEvidence.ts)
    - Implement hook for GET /evidence with optional filtering
    - Handle loading and error states
    - _Requirements: 7.3_
  
  - [ ] 13.4 Create useDashboard hook (src/hooks/useDashboard.ts)
    - Implement hook for GET /dashboard
    - Handle loading and error states
    - _Requirements: 7.3_

- [ ] 14. Create page components (placeholder implementations)
  - [ ] 14.1 Create Layout component (src/components/Layout.tsx)
    - Implement navigation sidebar with links to all routes
    - Use React Router Outlet for nested routes
    - _Requirements: 7.6_
  
  - [ ] 14.2 Create page components (src/pages/)
    - Create Onboarding.tsx (placeholder with "Onboarding" heading)
    - Create Dashboard.tsx (placeholder with "Dashboard" heading)
    - Create Missions.tsx (placeholder with "Missions" heading)
    - Create Evidence.tsx (placeholder with "Evidence" heading)
    - Create Profile.tsx (placeholder with "Profile" heading)
    - _Requirements: 7.3, 7.9_
  
  - [ ] 14.3 Configure router in App.tsx
    - Set up React Router with all routes
    - Wrap protected routes with ProtectedRoute component
    - Wrap app with AuthProvider
    - _Requirements: 7.3, 7.5_

- [ ] 15. Checkpoint - Verify frontend shell
  - Run `npm run dev` to start development server
  - Test authentication flow (login/logout)
  - Verify protected routes redirect when not authenticated
  - Verify all routes are accessible when authenticated
  - Ensure all tests pass, ask the user if questions arise.


- [ ] 16. Set up testing infrastructure
  - [ ] 16.1 Configure pytest for backend tests
    - Create tests/unit/ directory structure mirroring backend/lambda/
    - Create conftest.py with shared fixtures for mocking AWS services
    - Install pytest, moto, hypothesis in test requirements
    - _Requirements: 10.1, 10.4_
  
  - [ ] 16.2 Create test fixtures (tests/unit/conftest.py)
    - Create fixture for mocking DynamoDB tables
    - Create fixture for mocking Cognito
    - Create fixture for Lambda event/context objects
    - _Requirements: 10.4_
  
  - [ ]* 16.3 Write property test for AWS SDK mocking
    - **Property 15: AWS SDK Mocking**
    - **Validates: Requirements 10.4**

- [ ] 17. Create integration wiring and final validation
  - [ ] 17.1 Verify deployment readiness
    - Skip README creation per anti-pattern convention (no per-module docs unless explicitly requested)
    - Verify environment variables needed for frontend are documented in .env.example
    - _Requirements: 1.1_
  
  - [ ] 17.2 Verify all cross-stack references
    - Ensure ApiStack correctly imports User Pool from AuthStack
    - Ensure ApiStack correctly imports table names/ARNs from DataStack
    - Verify Lambda environment variables are set correctly
    - _Requirements: 6.10, 6.11_
  
  - [ ] 17.3 Verify frontend configuration
    - Ensure .env file has correct API Gateway URL placeholder
    - Ensure Amplify configuration has correct Cognito User Pool ID and Client ID placeholders
    - Document how to populate these values after deployment
    - _Requirements: 7.4_

- [ ] 18. Final checkpoint - Complete foundation validation
  - Run `cdk synth` and verify all templates are valid
  - Run all unit tests: `pytest tests/unit/`
  - Run all property tests with statistics: `pytest tests/unit/ --hypothesis-show-statistics`
  - Verify directory structure matches project conventions
  - Verify all Lambda handlers follow thin-handler pattern
  - Verify all resources have correct naming (Regain prefix) and tags
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP iteration
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation at key milestones
- Property tests validate universal correctness properties across all inputs (minimum 100 iterations)
- Unit tests validate specific examples, edge cases, and error conditions
- The foundation is deployment-ready but does not include actual deployment steps (future phase)
- Frontend pages are placeholder implementations - actual UI will be built in future specs
- Agent code (coaching, market intelligence) is not included - that comes in future specs
- Step Functions orchestration is not included - that comes in future specs
