---
inclusion: always
name: technology-stack
description: REGAIN technology stack, AWS services, and infrastructure decisions
---

# Technology Stack

## Languages

- **Backend / Agents:** Python 3.12+
- **Frontend:** TypeScript + React
- **IaC:** AWS CDK (Python) → CloudFormation

## AWS Services

### Frontend & Auth

- AWS Amplify (React hosting, CI/CD)
- Amazon Cognito (User Pool, social sign-in, JWT tokens)

### API & Compute

- Amazon API Gateway (REST API)
- AWS Lambda (Python handlers — thin wrappers delegating to service modules)
- AWS Step Functions (campaign orchestration, mission sequencing, phase progression)

### Data

- Amazon DynamoDB (all application data — user profiles, campaigns, missions, evidence, market data)

### AI / Agent Layer

- **Strands Agents SDK** (Python) — agent framework for both agents
- **Amazon Bedrock AgentCore Runtime** — serverless deployment for agents
- **Amazon Bedrock AgentCore Memory** — episodic memory (short-term + long-term strategies)
- **Amazon Bedrock AgentCore Gateway** — secure access to external APIs for Market Intelligence agent
- **Amazon Bedrock AgentCore Policy** — behavioral guardrails via Cedar policies
- **Amazon Bedrock AgentCore Observability** — tracing, debugging, metrics via OpenTelemetry + CloudWatch
- **Amazon Bedrock AgentCore Evaluations** — quality scoring (correctness, helpfulness, safety)
- **Amazon Nova 2 Lite** — default model for cost-effective inference
- **Intelligent Prompt Routing** — auto-escalation to capable models for complex interactions

### Key Constraints

- Must operate within AWS Free Tier limits + $200 new customer credits
- AgentCore Runtime: consumption-based pricing (pay only for active compute, I/O wait is free)
- Nova 2 Lite: ~$0.000035/1K input tokens (extremely cost-efficient)
- DynamoDB: 25 GB storage + 25 RCU/WCU in free tier
- Lambda: 1M requests + 400,000 GB-seconds/month free
- Amplify: 1000 build minutes + 15 GB served/month free

## AWS Account

- Dedicated account: 563170906428
- Region: us-east-1 (primary — AgentCore availability)
