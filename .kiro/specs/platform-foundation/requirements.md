# Requirements Document

## Introduction

The REGAIN platform foundation establishes the core infrastructure, authentication, data layer, API endpoints, and frontend shell for an AI-powered reskilling platform. This foundation enables veterans, AI-displaced workers, and career pivoters to engage in structured, evidence-based career transitions through daily missions, adaptive coaching, and market intelligence.

## Glossary

- **CDK_App**: AWS Cloud Development Kit application that synthesizes CloudFormation templates
- **User_Pool**: Amazon Cognito User Pool for authentication and user management
- **DynamoDB_Table**: NoSQL database table with on-demand billing
- **Lambda_Handler**: AWS Lambda function entry point that processes API requests
- **API_Gateway**: Amazon API Gateway REST API with Cognito authorization
- **Frontend_Shell**: React application with routing, authentication, and API client layer
- **Evidence_Vault**: Collection of documented skills, artifacts, and reflections from completed missions
- **Campaign**: Structured reskilling journey with phases and missions
- **Mission**: Small, completable skill-building task
- **Service_Module**: Python module containing business logic separate from Lambda handlers
- **Data_Access_Layer**: Shared Python module for DynamoDB operations
- **Protected_Route**: React route that requires authentication

## Requirements

### Requirement 1: CDK Project Initialization

**User Story:** As a developer, I want a properly initialized AWS CDK project, so that I can define and deploy infrastructure as code.

#### Acceptance Criteria

1. THE CDK_App SHALL be created at `/infra/app.py` with Python as the implementation language
2. THE CDK_App SHALL include a requirements.txt file with aws-cdk-lib and constructs dependencies
3. WHEN the CDK app is synthesized, THEN it SHALL produce valid CloudFormation templates
4. THE CDK_App SHALL tag all resources with Project=REGAIN and Environment=dev

### Requirement 2: Project Directory Structure

**User Story:** As a developer, I want a complete directory structure, so that code is organized according to project conventions.

#### Acceptance Criteria

1. THE System SHALL create directories for infra/stacks/, backend/lambda/, backend/agents/, frontend/src/, and tests/
2. THE System SHALL create subdirectories under backend/lambda/ for onboarding, missions, evidence, coaching, and shared utilities
3. THE System SHALL create subdirectories under backend/agents/ for coaching and market_intel agents
4. THE System SHALL create subdirectories under frontend/src/ for components, pages, hooks, services, and types
5. THE System SHALL create subdirectories under tests/ for unit and integration tests

### Requirement 3: Shared Python Utilities

**User Story:** As a developer, I want shared utilities for Lambda functions, so that common functionality is not duplicated.

#### Acceptance Criteria

1. THE Data_Access_Layer SHALL provide functions for DynamoDB CRUD operations
2. THE Data_Access_Layer SHALL accept table names via environment variables
3. THE System SHALL provide response helper functions for consistent API responses
4. THE System SHALL provide environment configuration utilities for reading AWS resource identifiers
5. WHEN a Lambda function needs DynamoDB access, THEN it SHALL use the Data_Access_Layer

### Requirement 4: Authentication Stack

**User Story:** As a user, I want secure authentication, so that my profile and data are protected.

#### Acceptance Criteria

1. THE User_Pool SHALL support email-based sign-up and sign-in
2. THE User_Pool SHALL have a client configured for SRP authentication flow without client secret
3. THE Auth_Stack SHALL output the User Pool ID as a CloudFormation export
4. THE Auth_Stack SHALL output the User Pool Client ID as a CloudFormation export
5. WHEN a user signs up, THEN the User_Pool SHALL verify their email address

### Requirement 5: Data Stack

**User Story:** As a developer, I want DynamoDB tables for all application data, so that user profiles, campaigns, missions, evidence, and market data can be stored.

#### Acceptance Criteria

1. THE Data_Stack SHALL create a UserProfiles table with userId as partition key
2. THE Data_Stack SHALL create a Campaigns table with userId as partition key and campaignId as sort key
3. THE Data_Stack SHALL create a MissionHistory table with userId as partition key and missionId as sort key
4. THE Data_Stack SHALL create an EvidenceVault table with userId as partition key and evidenceId as sort key
5. THE Data_Stack SHALL create a MarketData table with sector as partition key and timestamp as sort key
6. THE Campaigns table SHALL have a Global Secondary Index on status attribute
7. THE MissionHistory table SHALL have a Global Secondary Index on status attribute
8. THE MissionHistory table SHALL have a Global Secondary Index on date attribute
9. THE EvidenceVault table SHALL have a Global Secondary Index on skill tag attribute
10. WHEN creating tables, THE Data_Stack SHALL use on-demand billing mode
11. THE Data_Stack SHALL output all table names as CloudFormation exports
12. THE Data_Stack SHALL output all table ARNs as CloudFormation exports

### Requirement 6: API Stack with Lambda Functions

**User Story:** As a frontend developer, I want REST API endpoints, so that the React application can interact with backend services.

#### Acceptance Criteria

1. THE API_Gateway SHALL use Cognito authorizer with the User_Pool from Auth_Stack
2. THE API_Gateway SHALL expose a POST /onboarding endpoint
3. THE API_Gateway SHALL expose a GET /missions endpoint
4. THE API_Gateway SHALL expose a POST /missions/{missionId}/complete endpoint
5. THE API_Gateway SHALL expose a GET /evidence endpoint
6. THE API_Gateway SHALL expose a POST /coaching/checkin endpoint
7. THE API_Gateway SHALL expose a GET /dashboard endpoint
8. WHEN an endpoint is invoked, THEN the API_Gateway SHALL validate the Cognito JWT token
9. THE Lambda_Handler for each endpoint SHALL use Python 3.12 runtime
10. THE Lambda_Handler SHALL receive DynamoDB table names via environment variables
11. THE Lambda_Handler SHALL have IAM permissions only for required DynamoDB tables
12. WHEN a Lambda_Handler receives a request, THEN it SHALL validate input, call a Service_Module, and return a response
13. THE Lambda_Handler SHALL NOT contain business logic

### Requirement 7: Frontend React Application

**User Story:** As a developer, I want a React frontend shell, so that I can build user interfaces on top of authentication and API integration.

#### Acceptance Criteria

1. THE Frontend_Shell SHALL be created using Vite with TypeScript
2. THE Frontend_Shell SHALL have Tailwind CSS configured for styling
3. THE Frontend_Shell SHALL use React Router with routes for /onboarding, /dashboard, /missions, /evidence, and /profile
4. THE Frontend_Shell SHALL integrate AWS Amplify Auth library for Cognito authentication
5. WHEN a user navigates to a Protected_Route without authentication, THEN they SHALL be redirected to login
6. THE Frontend_Shell SHALL have a layout component with navigation sidebar
7. THE Frontend_Shell SHALL have an API service layer with typed fetch functions for each backend endpoint
8. THE API service layer SHALL include authentication headers in all requests
9. THE Frontend_Shell SHALL NOT include UI implementation beyond routing and authentication

### Requirement 8: Infrastructure Naming and Tagging

**User Story:** As a cloud administrator, I want consistent resource naming and tagging, so that AWS resources are identifiable and organized.

#### Acceptance Criteria

1. THE Auth_Stack SHALL be named RegainAuthStack
2. THE Data_Stack SHALL be named RegainDataStack
3. THE API_Stack SHALL be named RegainApiStack
4. THE System SHALL prefix all resource names with "Regain"
5. THE System SHALL tag all resources with Project=REGAIN
6. THE System SHALL tag all resources with Environment=dev

### Requirement 9: Cost Optimization

**User Story:** As a project owner, I want infrastructure that operates within AWS Free Tier limits, so that costs are minimized during development.

#### Acceptance Criteria

1. WHEN creating DynamoDB tables, THE Data_Stack SHALL use on-demand capacity mode
2. THE Lambda_Handler SHALL use Python 3.12 runtime for efficiency
3. THE System SHALL NOT provision resources that exceed Free Tier limits
4. THE System SHALL NOT use provisioned throughput for DynamoDB tables

### Requirement 10: Testing Foundation

**User Story:** As a developer, I want a testing structure, so that Lambda handlers and business logic can be verified.

#### Acceptance Criteria

1. THE System SHALL create a tests/unit/ directory structure mirroring backend/lambda/
2. WHEN testing a Lambda_Handler, THE test SHALL verify the handler calls the Service_Module correctly
3. THE System SHALL NOT generate excessive test files
4. THE tests SHALL mock AWS SDK calls using pytest fixtures or moto
