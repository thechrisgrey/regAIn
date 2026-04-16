"""Canonical profile field allowlists for update_user_profile.

Single source of truth consumed by both the direct-tool path (tools.py)
and the Gateway/Cedar policy path (policy_context.py).
"""

# Fields the LLM is allowed to update on a user profile.
# Anything outside this set (e.g. rate-limit counters, S3 keys) is rejected.
ALLOWED_PROFILE_FIELDS: frozenset[str] = frozenset({
    # camelCase (DynamoDB convention)
    "skills", "targetRole", "persona", "onboardingCompleted",
    "firstName", "lastName", "currentRole", "company", "industry",
    "yearsExperience", "yearsInRole", "highestPosition",
    "story", "coachNotes", "experience",
    "transferableSkills", "technicalSkills", "domainKnowledge",
    "experienceYears", "roleHistory", "name",
    "skillsFocus",
    # snake_case (tool docstring convention, also accepted by DynamoDB)
    "target_role", "onboarding_completed",
    "first_name", "last_name", "current_role",
    "years_experience", "years_in_role", "highest_position",
    "coach_notes", "experience_years", "role_history",
    "transferable_skills", "technical_skills", "domain_knowledge",
    "skills_focus",
})

# Fields that must never be written by the agent under any circumstances.
RESTRICTED_PROFILE_FIELDS: frozenset[str] = frozenset({
    "email",
    "cognitoId",
    "role",
    "tier",
    "userId",
})

# Map snake_case docstring names -> canonical camelCase DynamoDB attributes.
# The LLM often passes snake_case from the tool docstring; DynamoDB attributes
# are camelCase by project convention. update_user_profile normalizes through
# this map before writing so consumers that read camelCase get the value.
SNAKE_TO_CAMEL_PROFILE_FIELDS: dict[str, str] = {
    "target_role": "targetRole",
    "onboarding_completed": "onboardingCompleted",
    "first_name": "firstName",
    "last_name": "lastName",
    "current_role": "currentRole",
    "years_experience": "yearsExperience",
    "years_in_role": "yearsInRole",
    "highest_position": "highestPosition",
    "coach_notes": "coachNotes",
    "experience_years": "experienceYears",
    "role_history": "roleHistory",
    "transferable_skills": "transferableSkills",
    "technical_skills": "technicalSkills",
    "domain_knowledge": "domainKnowledge",
    "skills_focus": "skillsFocus",
}
