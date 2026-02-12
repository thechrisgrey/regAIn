---
inclusion: fileMatch
fileMatchPattern: "backend/agents/**"
name: agent-development-patterns
description: Patterns for building REGAIN agents with Strands SDK and AgentCore
---

# Agent Development Patterns

## Agent Architecture

REGAIN has two agents. They do NOT communicate directly with each other. The application layer (Lambda + Step Functions) orchestrates interactions between them.

### Adaptive Coaching Agent

- Purpose: Guide users through campaigns via missions, evidence tracking, and personalized coaching
- Model: Amazon Nova 2 Lite (default) with Intelligent Prompt Routing for complex moments
- Memory: AgentCore Memory with episodic, semantic, and user preference strategies
- Tools: mission generation, evidence logging, pattern analysis, check-in conductor
- Guardrails via AgentCore Policy:
  - Never suggest missions outside user's assessed capability
  - Escalate to human support resources if user shows signs of crisis
  - Always tie encouragement to documented evidence
  - Never generate missions that require financial investment from the user

### Market Intelligence Agent

- Purpose: Scan job market, map skills to demand, identify aligned roles, forecast trends
- Model: Amazon Nova 2 Lite
- External access: AgentCore Gateway → job market APIs
- Tools: trend scanner, skills-demand mapper, role identifier, trend forecaster
- No memory needed — stateless market queries. Results feed into campaign data.

## Strands SDK Patterns

### Tool Definition

```python
from strands import Agent, tool

@tool
def my_tool(param1: str, param2: int) -> dict:
    """Clear, precise description of what this tool does.
    
    The LLM reads this docstring to decide when and how to use the tool.
    
    Args:
        param1: What this parameter represents
        param2: What this parameter represents
    
    Returns:
        Dictionary containing the result with keys: result_key, status
    """
    # Implementation
    return {"result_key": value, "status": "success"}
```

### Agent Creation

```python
from strands import Agent
from strands.models import BedrockModel

model = BedrockModel(
    model_id="us.amazon.nova-lite-v2:0",
    streaming=True
)

agent = Agent(
    model=model,
    tools=[tool1, tool2, tool3],
    system_prompt=SYSTEM_PROMPT  # imported from prompts.py
)
```

### AgentCore Runtime Deployment

```python
from bedrock_agentcore.runtime import BedrockAgentCoreApp

app = BedrockAgentCoreApp()

@app.entrypoint
def invoke(request):
    response = agent(request.get("message"))
    return {"response": response.message}
```

### AgentCore Memory Integration

```python
from bedrock_agentcore.memory import MemoryClient
from bedrock_agentcore.memory.integrations.strands.session_manager import (
    AgentCoreMemorySessionManager
)

client = MemoryClient(region_name="us-east-1")

session_manager = AgentCoreMemorySessionManager(
    memory_id=MEMORY_ID,
    actor_id=user_id,
    session_id=session_id
)

with session_manager:
    response = agent(user_message)
```
