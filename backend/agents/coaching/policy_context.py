"""Gateway policy context builders for Cedar policy evaluation.

Provides helper functions that pre-compute context values used by Cedar
policies. These run in the Gateway context-building step before Cedar
evaluation, translating complex field-level checks into simple booleans
that Cedar can evaluate efficiently.
"""


ALLOWED_PROFILE_FIELDS: frozenset[str] = frozenset({
    "skills",
    "experience",
    "targetRoles",
    "preferences",
    "transferable_skills",
    "technical_skills",
    "domain_knowledge",
    "experience_years",
    "industry",
    "role_history",
    "persona",
    "onboarding_completed",
    "target_role",
    "first_name",
    "last_name",
    "current_role",
    "company",
    "years_in_role",
    "highest_position",
    "story",
    "coach_notes",
})

RESTRICTED_PROFILE_FIELDS: frozenset[str] = frozenset({
    "email",
    "cognitoId",
    "role",
    "tier",
    "userId",
})


def check_profile_fields_allowed(update_fields: set[str]) -> bool:
    """Check whether all update field keys are in the allowed set.

    Used by the Gateway context builder to set ``context.all_fields_allowed``
    before Cedar policy evaluation for ``update_user_profile`` invocations.

    Args:
        update_fields: The set of field keys from the updates parameter.

    Returns:
        True if every field is in the allowed set and none are restricted.
        False if any field is restricted or not in the allowed set.
    """
    if not update_fields:
        return False
    return update_fields.issubset(ALLOWED_PROFILE_FIELDS)


def get_restricted_fields(update_fields: set[str]) -> list[str]:
    """Return the list of restricted fields present in the update request.

    Used to populate the denial reason with the specific disallowed fields
    per Requirement 7.3.

    Args:
        update_fields: The set of field keys from the updates parameter.

    Returns:
        Sorted list of restricted field names found in the update request.
    """
    return sorted(update_fields & RESTRICTED_PROFILE_FIELDS)
