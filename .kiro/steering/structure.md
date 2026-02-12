---
inclusion: always
name: project-structure
description: REGAIN repository structure and file organization
---

# Project Structure

```
regAIn/
├── README.md
├── .kiro/
│   ├── steering/              # Kiro steering files
│   ├── specs/                 # Generated spec documents
│   └── settings/
│       └── mcp.json           # MCP server configuration
├── infra/                     # AWS CDK infrastructure
│   ├── app.py                 # CDK app entry point
│   ├── requirements.txt
│   └── stacks/
│       ├── auth_stack.py      # Cognito
│       ├── api_stack.py       # API Gateway + Lambda
│       ├── data_stack.py      # DynamoDB tables
│       ├── orchestration_stack.py  # Step Functions
│       ├── frontend_stack.py  # Amplify
│       └── agent_stack.py     # AgentCore configs
├── backend/
│   ├── lambda/                # Lambda function handlers
│   │   ├── onboarding/
│   │   ├── missions/
│   │   ├── evidence/
│   │   ├── coaching/
│   │   └── shared/            # Shared utilities, models, DynamoDB access
│   └── agents/                # Strands agent code
│       ├── coaching/
│       │   ├── agent.py
│       │   ├── tools.py
│       │   ├── prompts.py
│       │   └── requirements.txt
│       └── market_intel/
│           ├── agent.py
│           ├── tools.py
│           ├── prompts.py
│           └── requirements.txt
├── frontend/                  # React application
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── hooks/
│   │   ├── services/          # API client layer
│   │   └── types/
│   ├── package.json
│   └── tsconfig.json
└── tests/
    ├── unit/
    └── integration/
```

## Naming Conventions

- Python: snake_case for files, functions, variables. PascalCase for classes.
- TypeScript/React: PascalCase for components. camelCase for functions and variables.
- DynamoDB tables: PascalCase (UserProfiles, Campaigns, MissionHistory, EvidenceVault, MarketData)
- Lambda handlers: `handler.py` in each function directory with a `lambda_handler` function.
- CDK stacks: PascalCase class names ending in Stack (AuthStack, ApiStack, etc.)
