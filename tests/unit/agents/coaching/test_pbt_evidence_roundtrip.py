"""Property-based tests for evidence logging round trip with count accuracy.

# Feature: coaching-agent, Property 6: Evidence logging round trip with count accuracy

**Validates: Requirements 5.2, 5.3, 5.4**

For any valid evidence parameters (user_id, mission_id, skill_tag, reflection),
calling log_evidence should return a dict with evidence_id and skill_evidence_count,
and the returned skill_evidence_count should equal the total number of evidence
records in the EvidenceVault for that user_id and skill_tag combination.

Uses moto-mocked DynamoDB via the shared dynamodb_tables fixture.
The @tool decorator from strands is stubbed since strands-agents is not
yet installed.
"""

import importlib
import sys
import types
from typing import Any, Dict

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Stub the strands module so tools.py can be imported without strands-agents
# ---------------------------------------------------------------------------
_strands_stub = types.ModuleType("strands")
_strands_stub.tool = lambda fn: fn  # @tool is a no-op passthrough
sys.modules.setdefault("strands", _strands_stub)


def _load_tools():
    """Import tools module with a fresh DynamoDBClient bound to moto tables."""
    mod_name = "backend.agents.coaching.tools"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    return importlib.import_module(mod_name)


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# User IDs: non-empty alphanumeric strings with dashes
_user_id_strategy = st.text(
    min_size=1,
    max_size=30,
    alphabet=st.characters(whitelist_categories=("L", "N", "Pd")),
)

# Skill tags: non-empty lowercase alpha strings
_skill_tag_strategy = st.text(
    min_size=1,
    max_size=20,
    alphabet=st.characters(whitelist_categories=("Ll",)),
)

# Reflections: non-empty text strings
_reflection_strategy = st.text(
    min_size=1,
    max_size=100,
    alphabet=st.characters(whitelist_categories=("L", "N", "Zs")),
).filter(lambda s: s.strip())

# Number of evidence records to log per example
_n_evidence_strategy = st.integers(min_value=1, max_value=5)


class TestEvidenceLoggingRoundTrip:
    """Property 6: Evidence logging round trip with count accuracy.

    For any valid evidence parameters, calling log_evidence N times for
    the same user_id and skill_tag should return incrementing
    skill_evidence_count values, ending at N.
    """

    @given(
        user_id=_user_id_strategy,
        skill_tag=_skill_tag_strategy,
        reflection=_reflection_strategy,
        n_evidence=_n_evidence_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_evidence_count_matches_logged_count(
        self,
        dynamodb_tables: Dict[str, Any],
        user_id: str,
        skill_tag: str,
        reflection: str,
        n_evidence: int,
    ) -> None:
        """log_evidence N times returns skill_evidence_count == N after the last call.

        # Feature: coaching-agent, Property 6: Evidence logging round trip with count accuracy
        **Validates: Requirements 5.2, 5.3, 5.4**
        """
        tools = _load_tools()

        # Clean up existing evidence for this user to avoid stale data
        ev_table = dynamodb_tables["evidence_vault"]
        existing = ev_table.query(
            KeyConditionExpression="userId = :uid",
            ExpressionAttributeValues={":uid": user_id},
        ).get("Items", [])
        for item in existing:
            ev_table.delete_item(
                Key={"userId": item["userId"], "evidenceId": item["evidenceId"]}
            )

        evidence_ids: list[str] = []

        for i in range(1, n_evidence + 1):
            result = tools.log_evidence(
                user_id=user_id,
                mission_id=f"mission-{i}",
                skill_tag=skill_tag,
                reflection=reflection,
            )

            # Each call returns no error
            assert "error" not in result, f"log_evidence call {i} failed: {result}"

            # Each evidence_id starts with "evidence-"
            assert result["evidence_id"].startswith("evidence-"), (
                f"Call {i}: evidence_id {result['evidence_id']!r} missing prefix"
            )

            # After the i-th call, skill_evidence_count == i
            assert result["skill_evidence_count"] == i, (
                f"Call {i}: expected count {i}, got {result['skill_evidence_count']}"
            )

            evidence_ids.append(result["evidence_id"])

        # All evidence_ids are unique
        assert len(set(evidence_ids)) == n_evidence, (
            f"Expected {n_evidence} unique IDs, got {len(set(evidence_ids))}"
        )
