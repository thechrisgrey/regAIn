"""MCP-compatible tool schema definitions for the REGAIN Coaching Agent.

Each schema maps a tool name (regain_ prefix) to its typed input/output
JSON Schema, natural language description, Lambda target, and required
auth claims. Schemas match the existing @tool function signatures in
tools.py exactly.

The userId parameter is marked with ``"x-jwt-injected": true`` on every
tool that requires it — Gateway extracts userId from the validated
Cognito JWT and injects it into the invocation context so the agent
never supplies it directly.
"""

from typing import Any, Optional


# -- Shared sub-schemas used across multiple tools --------------------------

_ERROR_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "error": {"type": "string"},
        "message": {"type": "string"},
    },
    "required": ["error", "message"],
}

_USER_ID_PROPERTY: dict[str, Any] = {
    "type": "string",
    "description": "Authenticated user ID, injected from Cognito JWT claims.",
    "x-jwt-injected": True,
}


# -- Individual tool schemas ------------------------------------------------

_READ_USER_PROFILE: dict[str, Any] = {
    "name": "regain_read_user_profile",
    "description": (
        "Read a user's complete profile from the REGAIN platform. "
        "Returns the user's name, persona type (veteran, ai_displaced, "
        "career_pivoter), target role, skills inventory, and onboarding "
        "status. Call at the start of a session to personalize coaching."
    ),
    "lambda_target": "coaching",
    "input_schema": {
        "type": "object",
        "properties": {
            "userId": _USER_ID_PROPERTY,
        },
        "required": ["userId"],
    },
    "output_schema": {
        "type": "object",
        "properties": {
            "userId": {"type": "string"},
            "name": {"type": "string"},
            "email": {"type": "string"},
            "persona": {"type": "string"},
            "target_role": {"type": "string"},
            "skills": {"type": "array", "items": {"type": "string"}},
            "onboarding_completed": {"type": "boolean"},
            "created_at": {"type": "string"},
        },
    },
    "required_auth_claims": ["sub"],
}

_UPDATE_USER_PROFILE: dict[str, Any] = {
    "name": "regain_update_user_profile",
    "description": (
        "Update fields on a user's profile. Pass only the fields that "
        "need to change; existing fields are preserved. Valid fields "
        "include skills, target_role, persona, onboarding_completed, "
        "first_name, last_name, current_role, company, years_in_role, "
        "highest_position, story, coach_notes, experience, and "
        "Transition Profile fields (transferable_skills, "
        "technical_skills, domain_knowledge, experience_years, "
        "industry, role_history)."
    ),
    "lambda_target": "coaching",
    "input_schema": {
        "type": "object",
        "properties": {
            "userId": _USER_ID_PROPERTY,
            "updates": {
                "type": "object",
                "description": "Dict of field names to new values.",
            },
        },
        "required": ["userId", "updates"],
    },
    "output_schema": {
        "type": "object",
        "description": "Full updated profile with all attributes after the update.",
        "additionalProperties": True,
    },
    "required_auth_claims": ["sub"],
}

_GET_CAMPAIGN_STATUS: dict[str, Any] = {
    "name": "regain_get_campaign_status",
    "description": (
        "Get the active campaign for a user. Returns the campaign "
        "record including current phase (foundation, expansion, or "
        "launch), title, target role, and skills focus. Call before "
        "creating a new campaign or when reviewing progress."
    ),
    "lambda_target": "coaching",
    "input_schema": {
        "type": "object",
        "properties": {
            "userId": _USER_ID_PROPERTY,
        },
        "required": ["userId"],
    },
    "output_schema": {
        "type": "object",
        "properties": {
            "userId": {"type": "string"},
            "campaignId": {"type": "string"},
            "title": {"type": "string"},
            "phase": {"type": "string", "enum": ["foundation", "expansion", "launch"]},
            "status": {"type": "string"},
            "startDate": {"type": "string"},
            "targetRole": {"type": "string"},
            "skillsFocus": {"type": "array", "items": {"type": "string"}},
        },
    },
    "required_auth_claims": ["sub"],
}

_CREATE_CAMPAIGN: dict[str, Any] = {
    "name": "regain_create_campaign",
    "description": (
        "Create a new reskilling campaign for a user. Creates a "
        "campaign starting in the foundation phase with active status. "
        "Each campaign is a structured three-phase plan "
        "(Foundation → Expansion → Launch) tailored to the user's "
        "target role and skill gaps."
    ),
    "lambda_target": "coaching",
    "input_schema": {
        "type": "object",
        "properties": {
            "userId": _USER_ID_PROPERTY,
            "title": {
                "type": "string",
                "description": "Descriptive title for the campaign.",
            },
            "targetRole": {
                "type": "string",
                "description": "The job role the user is working toward.",
            },
            "skillsFocus": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of skill names the campaign will develop.",
            },
        },
        "required": ["userId", "title", "targetRole", "skillsFocus"],
    },
    "output_schema": {
        "type": "object",
        "properties": {
            "userId": {"type": "string"},
            "campaignId": {"type": "string"},
            "title": {"type": "string"},
            "phase": {"type": "string"},
            "status": {"type": "string"},
            "startDate": {"type": "string"},
            "targetRole": {"type": "string"},
            "skillsFocus": {"type": "array", "items": {"type": "string"}},
        },
    },
    "required_auth_claims": ["sub"],
}

_GET_CURRENT_MISSION: dict[str, Any] = {
    "name": "regain_get_current_mission",
    "description": (
        "Get the current pending or in-progress mission for a user. "
        "Also returns behavioral pattern analysis from the user's full "
        "mission history to detect avoidance, identify strengths, and "
        "adapt coaching."
    ),
    "lambda_target": "missions",
    "input_schema": {
        "type": "object",
        "properties": {
            "userId": _USER_ID_PROPERTY,
        },
        "required": ["userId"],
    },
    "output_schema": {
        "type": "object",
        "properties": {
            "userId": {"type": "string"},
            "missionId": {"type": "string"},
            "campaignId": {"type": "string"},
            "title": {"type": "string"},
            "description": {"type": "string"},
            "status": {"type": "string"},
            "skillTag": {"type": "string"},
            "patterns": {
                "type": "object",
                "description": "Behavioral pattern analysis from mission history.",
            },
        },
    },
    "required_auth_claims": ["sub"],
}

_GENERATE_MISSION: dict[str, Any] = {
    "name": "regain_generate_mission",
    "description": (
        "Generate a personalized daily mission for a user's reskilling "
        "campaign. Runs the full Mission Engine pipeline: skill gap "
        "analysis, template instantiation, difficulty filtering, "
        "priority scoring, and ranking. Returns the top-scored mission "
        "plus two alternates."
    ),
    "lambda_target": "missions",
    "input_schema": {
        "type": "object",
        "properties": {
            "userId": _USER_ID_PROPERTY,
            "campaignId": {
                "type": "string",
                "description": "The active campaign this mission belongs to.",
            },
        },
        "required": ["userId", "campaignId"],
    },
    "output_schema": {
        "type": "object",
        "properties": {
            "primary": {
                "type": "object",
                "description": "The recommended mission with all fields.",
            },
            "alternates": {
                "type": "array",
                "items": {"type": "object"},
                "description": "List of backup missions.",
            },
            "skill_gap_report": {
                "type": "object",
                "description": "Current skill gap analysis.",
            },
        },
    },
    "required_auth_claims": ["sub"],
}

_COMPLETE_MISSION: dict[str, Any] = {
    "name": "regain_complete_mission",
    "description": (
        "Mark a mission as completed, log evidence, and update campaign "
        "progress. Logs the user's evidence first, then delegates to "
        "the Mission Engine for state transition, difficulty adjustment, "
        "and phase gate evaluation."
    ),
    "lambda_target": "evidence",
    "input_schema": {
        "type": "object",
        "properties": {
            "userId": _USER_ID_PROPERTY,
            "missionId": {
                "type": "string",
                "description": "The mission being completed.",
            },
            "reflection": {
                "type": "string",
                "description": "The user's reflection on what they did or learned.",
            },
            "skillTag": {
                "type": "string",
                "description": "The skill demonstrated by completing this mission.",
            },
            "artifactUrl": {
                "type": "string",
                "description": "Optional URL to a supporting artifact.",
                "default": "",
            },
        },
        "required": ["userId", "missionId", "reflection", "skillTag"],
    },
    "output_schema": {
        "type": "object",
        "properties": {
            "mission_id": {"type": "string"},
            "difficulty_change": {"type": "object"},
            "gate_result": {"type": "object"},
            "evidence_id": {"type": "string"},
            "skill_evidence_count": {"type": "integer"},
        },
    },
    "required_auth_claims": ["sub"],
}

_LOG_EVIDENCE: dict[str, Any] = {
    "name": "regain_log_evidence",
    "description": (
        "Log a piece of evidence to the user's Evidence Vault. Creates "
        "a timestamped evidence record tagged with the relevant skill. "
        "Returns the cumulative count of evidence for that skill."
    ),
    "lambda_target": "evidence",
    "input_schema": {
        "type": "object",
        "properties": {
            "userId": _USER_ID_PROPERTY,
            "missionId": {
                "type": "string",
                "description": "The mission this evidence relates to.",
            },
            "skillTag": {
                "type": "string",
                "description": "The skill this evidence demonstrates.",
            },
            "reflection": {
                "type": "string",
                "description": "The user's description of what they did or learned.",
            },
            "artifactUrl": {
                "type": "string",
                "description": "Optional URL to a supporting artifact.",
                "default": "",
            },
        },
        "required": ["userId", "missionId", "skillTag", "reflection"],
    },
    "output_schema": {
        "type": "object",
        "properties": {
            "evidence_id": {"type": "string"},
            "skill_evidence_count": {"type": "integer"},
        },
    },
    "required_auth_claims": ["sub"],
}

_GET_EVIDENCE_SUMMARY: dict[str, Any] = {
    "name": "regain_get_evidence_summary",
    "description": (
        "Get a summary of all evidence in a user's Evidence Vault. "
        "Returns a breakdown of evidence counts by skill tag and the "
        "most recent evidence entries. Use during check-ins to "
        "reference accumulated proof or to identify skill gaps."
    ),
    "lambda_target": "evidence",
    "input_schema": {
        "type": "object",
        "properties": {
            "userId": _USER_ID_PROPERTY,
        },
        "required": ["userId"],
    },
    "output_schema": {
        "type": "object",
        "properties": {
            "by_skill": {
                "type": "object",
                "description": "Dict mapping skill tags to evidence counts.",
                "additionalProperties": {"type": "integer"},
            },
            "recent": {
                "type": "array",
                "items": {"type": "object"},
                "description": "The 5 most recent evidence entries.",
            },
            "total_count": {"type": "integer"},
        },
    },
    "required_auth_claims": ["sub"],
}

_GET_MARKET_INSIGHTS: dict[str, Any] = {
    "name": "regain_get_market_insights",
    "description": (
        "Get the latest market intelligence data for a target role. "
        "Returns demand scores, growth trends, in-demand skills, and "
        "salary ranges. Use when coaching users on skill prioritization "
        "or discussing career trajectory."
    ),
    "lambda_target": "market_intel",
    "input_schema": {
        "type": "object",
        "properties": {
            "roleId": {
                "type": "string",
                "description": (
                    "The role identifier to query "
                    "(e.g. 'ai_qa_engineer', 'data_analyst')."
                ),
            },
        },
        "required": ["roleId"],
    },
    "output_schema": {
        "type": "object",
        "properties": {
            "role_id": {"type": "string"},
            "demand_score": {"type": "number"},
            "trend_direction": {"type": "string"},
            "growth_rate": {"type": "number"},
            "top_skills": {"type": "array", "items": {"type": "string"}},
            "salary_range": {"type": "object"},
            "insights": {"type": "object"},
        },
    },
    "required_auth_claims": ["sub"],
}

_GET_ALIGNMENT: dict[str, Any] = {
    "name": "regain_get_alignment",
    "description": (
        "Calculate how well a user's demonstrated skills match a target "
        "role. Returns a concrete alignment percentage, per-skill "
        "breakdown, top gaps to close, and top strengths to leverage."
    ),
    "lambda_target": "market_intel",
    "input_schema": {
        "type": "object",
        "properties": {
            "userId": _USER_ID_PROPERTY,
            "targetRoleId": {
                "type": "string",
                "description": (
                    "The role identifier to align against "
                    "(e.g. 'ai_qa_engineer', 'project_manager')."
                ),
            },
        },
        "required": ["userId", "targetRoleId"],
    },
    "output_schema": {
        "type": "object",
        "properties": {
            "alignment_pct": {"type": "number"},
            "skill_breakdown": {"type": "array", "items": {"type": "object"}},
            "top_gaps": {"type": "array", "items": {"type": "object"}},
            "top_strengths": {"type": "array", "items": {"type": "object"}},
            "target_role_id": {"type": "string"},
            "user_id": {"type": "string"},
            "calculated_at": {"type": "string"},
        },
    },
    "required_auth_claims": ["sub"],
}

_RECALL_MEMORY: dict[str, Any] = {
    "name": "regain_recall_memory",
    "description": (
        "Retrieve relevant past conversation context for a user. "
        "Call at the start of every coaching session to recall prior "
        "session summaries, key decisions, and detected patterns. "
        "Results are ranked by semantic relevance and recency."
    ),
    "lambda_target": "coaching",
    "input_schema": {
        "type": "object",
        "properties": {
            "userId": _USER_ID_PROPERTY,
            "query": {
                "type": "string",
                "description": (
                    "Natural-language description of what context to "
                    "retrieve (e.g. 'previous coaching session summary')."
                ),
            },
        },
        "required": ["userId", "query"],
    },
    "output_schema": {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "content": {"type": "string"},
                "metadata": {"type": "object"},
            },
        },
    },
    "required_auth_claims": ["sub"],
}

_STORE_MEMORY: dict[str, Any] = {
    "name": "regain_store_memory",
    "description": (
        "Store a coaching session summary or key observation for a "
        "user. Call at the end of every coaching session to persist "
        "what was discussed, decisions made, evidence logged, missions "
        "delivered, and detected behavioral patterns."
    ),
    "lambda_target": "coaching",
    "input_schema": {
        "type": "object",
        "properties": {
            "userId": _USER_ID_PROPERTY,
            "content": {
                "type": "string",
                "description": "Text content to store (e.g. session summary).",
            },
        },
        "required": ["userId", "content"],
    },
    "output_schema": {
        "type": "object",
        "properties": {
            "status": {"type": "string"},
            "namespace": {"type": "string"},
        },
    },
    "required_auth_claims": ["sub"],
}

_READ_CALENDAR: dict[str, Any] = {
    "name": "regain_read_calendar",
    "description": (
        "Read calendar entries for a user within a date range. "
        "Use to check what tasks and notes the user has scheduled "
        "before suggesting new activities or responding to "
        "calendar-related questions."
    ),
    "lambda_target": "calendar",
    "input_schema": {
        "type": "object",
        "properties": {
            "userId": _USER_ID_PROPERTY,
            "start_date": {
                "type": "string",
                "description": "Start of range (YYYY-MM-DD).",
            },
            "end_date": {
                "type": "string",
                "description": "End of range (YYYY-MM-DD), inclusive.",
            },
        },
        "required": ["userId", "start_date", "end_date"],
    },
    "output_schema": {
        "type": "object",
        "properties": {
            "entries": {
                "type": "array",
                "items": {"type": "object"},
            },
        },
    },
    "required_auth_claims": ["sub"],
}

_WRITE_CALENDAR_ENTRY: dict[str, Any] = {
    "name": "regain_write_calendar_entry",
    "description": (
        "Write a new task or note to the user's calendar. Use after "
        "generating a mission (schedule it), after a coaching insight "
        "(write a note), or when the user asks for a reminder. "
        "Entries are authored as 'agent'."
    ),
    "lambda_target": "calendar",
    "input_schema": {
        "type": "object",
        "properties": {
            "userId": _USER_ID_PROPERTY,
            "date": {
                "type": "string",
                "description": "Target date (YYYY-MM-DD).",
            },
            "category": {
                "type": "string",
                "description": "Entry type: 'task' or 'note'.",
                "enum": ["task", "note"],
            },
            "content": {
                "type": "string",
                "description": "Plain text body of the entry.",
            },
        },
        "required": ["userId", "date", "category", "content"],
    },
    "output_schema": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "entryId": {"type": "string"},
        },
    },
    "required_auth_claims": ["sub"],
}

_CODE_INTERPRETER: dict[str, Any] = {
    "name": "regain_code_interpreter",
    "description": (
        "Execute Python code in a sandboxed Code Interpreter to generate "
        "visualizations (charts, graphs) or data exports (CSV) from user "
        "progress data. Only matplotlib, pandas, and numpy are available. "
        "No network access, no filesystem outside sandbox, no AWS "
        "credentials. Max 30s execution, 512MB memory. Output files are "
        "uploaded to S3 and returned as presigned URLs. Only "
        "agent-generated code is accepted — users cannot submit arbitrary "
        "code for execution."
    ),
    "lambda_target": "code_interpreter",
    "input_schema": {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": (
                    "Python code to execute. Must use only matplotlib, "
                    "pandas, or numpy. Agent-generated only."
                ),
            },
            "session_id": {
                "type": "string",
                "description": (
                    "Coaching session ID. One Code Interpreter session "
                    "per coaching session, reused within session."
                ),
            },
        },
        "required": ["code", "session_id"],
    },
    "output_schema": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Presigned S3 URL to the output file (1-hour expiry).",
            },
            "execution_status": {
                "type": "string",
                "description": "Status of code execution: success, error, timeout.",
            },
            "stdout": {
                "type": "string",
                "description": "Standard output from code execution.",
            },
            "stderr": {
                "type": "string",
                "description": "Standard error from code execution.",
            },
        },
    },
    "required_auth_claims": ["sub"],
}


# -- Public API -------------------------------------------------------------

TOOL_SCHEMAS: list[dict[str, Any]] = [
    _READ_USER_PROFILE,
    _UPDATE_USER_PROFILE,
    _GET_CAMPAIGN_STATUS,
    _CREATE_CAMPAIGN,
    _GET_CURRENT_MISSION,
    _GENERATE_MISSION,
    _COMPLETE_MISSION,
    _LOG_EVIDENCE,
    _GET_EVIDENCE_SUMMARY,
    _GET_MARKET_INSIGHTS,
    _GET_ALIGNMENT,
    _RECALL_MEMORY,
    _STORE_MEMORY,
    _READ_CALENDAR,
    _WRITE_CALENDAR_ENTRY,
    _CODE_INTERPRETER,
]


def get_tool_schemas() -> list[dict[str, Any]]:
    """Return all MCP-compatible tool schema definitions including Code Interpreter.

    Returns:
        A list of schema dicts, each containing name, description,
        lambda_target, input_schema, output_schema, and
        required_auth_claims.
    """
    return list(TOOL_SCHEMAS)


def get_schema_by_name(name: str) -> Optional[dict[str, Any]]:
    """Look up a single tool schema by its MCP tool name.

    Args:
        name: The tool name with regain_ prefix
            (e.g. "regain_read_user_profile").

    Returns:
        The matching schema dict, or None if no tool matches.
    """
    for schema in TOOL_SCHEMAS:
        if schema["name"] == name:
            return schema
    return None
