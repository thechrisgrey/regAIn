"""Property-based tests for Cedar policy: profile update field restrictions.

# Feature: agentcore-platform-integration, Property 8: Profile update field restrictions

**Validates: Requirements 7.1, 7.2**

For any update_user_profile tool invocation, the Cedar policy SHALL permit the
invocation if and only if every field key in the updates parameter is a member
of the allowed set. The presence of any field from the restricted set (email,
cognitoId, role, tier, userId) or any unknown field SHALL result in a Policy
Denial.

Strategy:
- Use the real ``check_profile_fields_allowed`` function from policy_context.
- Generate random subsets from the union of allowed + restricted fields.
- Generate random unknown field names to verify they are also rejected.
- Verify: permit iff all fields are in the allowed set.
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from backend.agents.coaching.policy_context import (
    ALLOWED_PROFILE_FIELDS,
    RESTRICTED_PROFILE_FIELDS,
    check_profile_fields_allowed,
)

# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

_all_known_fields = sorted(ALLOWED_PROFILE_FIELDS | RESTRICTED_PROFILE_FIELDS)

_allowed_subsets = st.frozensets(
    st.sampled_from(sorted(ALLOWED_PROFILE_FIELDS)),
    min_size=1,
)

_mixed_subsets = st.frozensets(
    st.sampled_from(_all_known_fields),
    min_size=1,
)

_random_field_names = st.text(
    min_size=1,
    max_size=20,
    alphabet=st.characters(whitelist_categories=("L",)),
)

_random_field_sets = st.frozensets(_random_field_names, min_size=1, max_size=5)


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------

class TestProfileUpdateFieldRestrictions:
    """Property 8: Profile update field restrictions.

    For random subsets of allowed + restricted field names, verify permit iff
    all fields in allowed set.
    """

    @given(fields=_allowed_subsets)
    @settings(max_examples=100)
    def test_pure_allowed_subsets_always_permit(self, fields: frozenset[str]) -> None:
        """Any non-empty subset of allowed fields must be permitted."""
        assert check_profile_fields_allowed(set(fields)) is True

    @given(fields=_mixed_subsets)
    @settings(max_examples=100)
    def test_permit_iff_all_fields_allowed(self, fields: frozenset[str]) -> None:
        """Permit iff every field in the subset belongs to the allowed set."""
        expected = fields.issubset(ALLOWED_PROFILE_FIELDS)
        assert check_profile_fields_allowed(set(fields)) is expected

    @given(fields=_random_field_sets)
    @settings(max_examples=100)
    def test_unknown_fields_rejected_unless_in_allowed(
        self, fields: frozenset[str]
    ) -> None:
        """Random field names are rejected unless they happen to be allowed."""
        expected = fields.issubset(ALLOWED_PROFILE_FIELDS)
        assert check_profile_fields_allowed(set(fields)) is expected

    @given(
        allowed=_allowed_subsets,
        restricted=st.frozensets(
            st.sampled_from(sorted(RESTRICTED_PROFILE_FIELDS)),
            min_size=1,
        ),
    )
    @settings(max_examples=100)
    def test_any_restricted_field_causes_denial(
        self, allowed: frozenset[str], restricted: frozenset[str]
    ) -> None:
        """Adding any restricted field to an allowed set must cause denial."""
        combined = set(allowed | restricted)
        assert check_profile_fields_allowed(combined) is False
