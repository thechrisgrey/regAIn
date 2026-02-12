---
inclusion: always
name: coding-conventions
description: REGAIN coding standards, patterns, and anti-patterns
---

# Coding Conventions

## General

- Keep it simple. No over-engineering. No premature abstraction.
- Every module does one thing well.
- Explicit over implicit. Name things clearly.

## Python (Backend + Agents)

- Type hints on all function signatures.
- Docstrings on public functions (Google style).
- Lambda handlers are thin: validate input, call service, return response.
- Service modules contain business logic. Handlers never contain business logic.
- DynamoDB access through a dedicated data access layer in `backend/lambda/shared/`.
- Environment variables for all configuration (table names, region, model IDs).

## TypeScript / React (Frontend)

- Functional components only. No class components.
- Custom hooks for all API interactions (`useOnboarding`, `useMissions`, etc.).
- Cognito auth context wraps the app. Protected routes enforce auth.
- Tailwind CSS for styling. No CSS modules, no styled-components.
- No state management library. React Context + useReducer where needed.

## Strands Agents

- Tools are pure Python functions decorated with @tool.
- Tool docstrings are critical — they ARE the LLM's understanding of what the tool does. Write them with precision.
- System prompts live in dedicated `prompts.py` files. Never inline.
- Agent configuration (model, tools, memory) in `agent.py`.

## CDK / Infrastructure

- One stack per AWS service domain.
- Cross-stack references via CfnOutput and Fn.importValue.
- All resource names include "Regain" prefix for identification.
- Tags: Project=REGAIN, Environment=dev on all resources.

## Testing

- Focused unit tests. Test business logic, not AWS SDK calls.
- Mock AWS services with moto or pytest fixtures.
- No excessive test generation. Quality over quantity.
- Tests live in `/tests/unit/` mirroring the source structure.

## Anti-Patterns (Do NOT do these)

- Do not create README files for individual modules unless asked.
- Do not generate extensive documentation beyond docstrings.
- Do not create abstract base classes unless there are 3+ concrete implementations.
- Do not use ORMs. DynamoDB access is direct via boto3.
- Do not add logging frameworks. Use Python's built-in logging module.
- Do not install unnecessary dependencies. Every pip package must justify its existence.
