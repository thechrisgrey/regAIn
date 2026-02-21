"""Property-based test for evidence user isolation.

**Property: Evidence Query User Isolation**

Verifies that evidence queries never return data belonging to other
users, even when multiple users share the same skill tags.

Two complementary approaches:
1. Source-level verification that the service never queries the
   skill-index GSI (which lacks userId scoping).
2. Runtime verification that DynamoDBClient.query() with
   filter_expression correctly isolates user data.
"""

import importlib
import uuid
from pathlib import Path
from typing import Any, Dict

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# DynamoDBClient has no 'backend.handlers' imports so importlib works.
_dynamodb_mod = importlib.import_module("backend.handlers.shared.dynamodb")
DynamoDBClient = _dynamodb_mod.DynamoDBClient

_SERVICE_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent.parent.parent
    / "backend"
    / "handlers"
    / "evidence"
    / "service.py"
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

skill_tags = st.sampled_from(
    ["python", "leadership", "data-analysis", "cloud", "general"]
)


def _seed_evidence(
    tables: Dict[str, Any],
    user_id: str,
    skill_tag: str,
) -> str:
    """Insert one evidence item and return its evidenceId."""
    evidence_id = str(uuid.uuid4())
    tables["evidence_vault"].put_item(
        Item={
            "userId": user_id,
            "evidenceId": evidence_id,
            "skillTag": skill_tag,
            "createdAt": "2026-01-15T00:00:00Z",
            "reflection": "test reflection",
        }
    )
    return evidence_id


# ---------------------------------------------------------------------------
# Source-level verification
# ---------------------------------------------------------------------------


class TestEvidenceServiceSource:
    """Verify the evidence service source code enforces user isolation."""

    def _read_service_source(self) -> str:
        return _SERVICE_PATH.read_text()

    def test_no_skill_index_gsi_query(self) -> None:
        """Service must not query the skill-index GSI (it lacks userId)."""
        source = self._read_service_source()
        assert 'index_name="skill-index"' not in source, (
            "EvidenceService still queries skill-index GSI which leaks data across users"
        )

    def test_skill_tag_branch_queries_by_user_id(self) -> None:
        """Both code paths must query by userId on the main table."""
        source = self._read_service_source()
        # The service should use Key("userId") in both branches
        user_id_key_count = source.count('Key("userId")')
        assert user_id_key_count >= 2, (
            f"Expected at least 2 Key(\"userId\") expressions (filtered + unfiltered), "
            f"found {user_id_key_count}"
        )

    def test_uses_filter_expression_for_skill_tag(self) -> None:
        """Skill tag filtering must use FilterExpression, not a GSI key condition."""
        source = self._read_service_source()
        assert "filter_expression=" in source, (
            "EvidenceService should use filter_expression for skillTag filtering"
        )
        assert 'Attr("skillTag")' in source, (
            "EvidenceService should filter on Attr(\"skillTag\")"
        )


# ---------------------------------------------------------------------------
# Runtime verification via DynamoDBClient
# ---------------------------------------------------------------------------


class TestEvidenceQueryIsolation:
    """Runtime proof that userId-scoped queries with filter_expression
    never leak data across users."""

    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        requesting_tag=skill_tags,
        other_tag=skill_tags,
    )
    def test_filtered_query_scoped_to_user(
        self,
        dynamodb_tables: Dict[str, Any],
        requesting_tag: str,
        other_tag: str,
    ) -> None:
        """Query by userId + skillTag filter only returns the requesting user's items."""
        from boto3.dynamodb.conditions import Attr, Key

        user_a = f"user-a-{uuid.uuid4()}"
        user_b = f"user-b-{uuid.uuid4()}"

        # Both users have evidence with the requesting tag
        _seed_evidence(dynamodb_tables, user_a, requesting_tag)
        _seed_evidence(dynamodb_tables, user_b, requesting_tag)
        _seed_evidence(dynamodb_tables, user_b, other_tag)

        db = DynamoDBClient()
        results = db.query(
            "evidence_vault",
            Key("userId").eq(user_a),
            filter_expression=Attr("skillTag").eq(requesting_tag),
        )

        for item in results:
            assert item["userId"] == user_a, (
                f"Leaked evidence from {item['userId']} to {user_a}"
            )

    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(tag=skill_tags)
    def test_unfiltered_query_scoped_to_user(
        self,
        dynamodb_tables: Dict[str, Any],
        tag: str,
    ) -> None:
        """Query by userId without filter only returns the requesting user's items."""
        from boto3.dynamodb.conditions import Key

        user_a = f"user-a-{uuid.uuid4()}"
        user_b = f"user-b-{uuid.uuid4()}"

        _seed_evidence(dynamodb_tables, user_a, tag)
        _seed_evidence(dynamodb_tables, user_b, tag)

        db = DynamoDBClient()
        results = db.query(
            "evidence_vault",
            Key("userId").eq(user_a),
        )

        for item in results:
            assert item["userId"] == user_a, (
                f"Leaked evidence from {item['userId']} to {user_a}"
            )

    def test_filter_expression_returns_correct_tag(
        self,
        dynamodb_tables: Dict[str, Any],
    ) -> None:
        """FilterExpression correctly narrows results to the requested skill tag."""
        from boto3.dynamodb.conditions import Attr, Key

        user = f"user-{uuid.uuid4()}"

        _seed_evidence(dynamodb_tables, user, "python")
        _seed_evidence(dynamodb_tables, user, "cloud")
        _seed_evidence(dynamodb_tables, user, "python")

        db = DynamoDBClient()
        results = db.query(
            "evidence_vault",
            Key("userId").eq(user),
            filter_expression=Attr("skillTag").eq("python"),
        )

        assert len(results) == 2
        assert all(item["skillTag"] == "python" for item in results)
