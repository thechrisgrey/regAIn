"""Unit tests for Gateway policy context builders (Task 4.4).

Tests the profile field validation logic used by the Gateway context
builder to set context.all_fields_allowed before Cedar evaluation.
"""

from backend.agents.coaching.policy_context import (
    ALLOWED_PROFILE_FIELDS,
    RESTRICTED_PROFILE_FIELDS,
    check_profile_fields_allowed,
    get_restricted_fields,
)


# -- check_profile_fields_allowed --------------------------------------------


def test_allowed_fields_only_returns_true() -> None:
    """All fields from the allowed set should be permitted."""
    assert check_profile_fields_allowed({"skills", "experience"}) is True


def test_single_allowed_field_returns_true() -> None:
    """A single allowed field should be permitted."""
    assert check_profile_fields_allowed({"target_role"}) is True


def test_all_allowed_fields_returns_true() -> None:
    """Every allowed field at once should be permitted."""
    assert check_profile_fields_allowed(set(ALLOWED_PROFILE_FIELDS)) is True


def test_restricted_field_returns_false() -> None:
    """Any restricted field should cause denial."""
    assert check_profile_fields_allowed({"email"}) is False


def test_mixed_allowed_and_restricted_returns_false() -> None:
    """Mix of allowed and restricted fields should cause denial."""
    assert check_profile_fields_allowed({"skills", "email"}) is False


def test_unknown_field_returns_false() -> None:
    """Fields not in the allowed set should cause denial."""
    assert check_profile_fields_allowed({"unknown_field"}) is False


def test_empty_fields_returns_false() -> None:
    """Empty update set should be denied (no-op update)."""
    assert check_profile_fields_allowed(set()) is False


def test_all_restricted_fields_return_false() -> None:
    """Every restricted field individually should be denied."""
    for field in RESTRICTED_PROFILE_FIELDS:
        assert check_profile_fields_allowed({field}) is False, f"{field} should be denied"


def test_all_allowed_fields_individually_return_true() -> None:
    """Every allowed field individually should be permitted."""
    for field in ALLOWED_PROFILE_FIELDS:
        assert check_profile_fields_allowed({field}) is True, f"{field} should be allowed"


# -- get_restricted_fields ----------------------------------------------------


def test_get_restricted_fields_returns_matching() -> None:
    """Should return only the restricted fields present in the update."""
    result = get_restricted_fields({"skills", "email", "cognitoId"})
    assert result == ["cognitoId", "email"]


def test_get_restricted_fields_returns_empty_for_allowed() -> None:
    """Should return empty list when no restricted fields present."""
    result = get_restricted_fields({"skills", "experience"})
    assert result == []


def test_get_restricted_fields_returns_sorted() -> None:
    """Returned list should be sorted alphabetically."""
    result = get_restricted_fields({"userId", "email", "role", "tier"})
    assert result == ["email", "role", "tier", "userId"]


# -- Set definitions ----------------------------------------------------------


def test_allowed_and_restricted_sets_are_disjoint() -> None:
    """Allowed and restricted sets must not overlap."""
    assert ALLOWED_PROFILE_FIELDS.isdisjoint(RESTRICTED_PROFILE_FIELDS)
