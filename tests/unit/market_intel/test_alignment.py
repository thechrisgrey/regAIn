"""Property-based tests for alignment calculation.

Tests Properties 8, 9, and 12 from the market intelligence design doc
using hypothesis for exhaustive input space coverage.
"""

import importlib
import os
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import boto3
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from moto import mock_aws

_alignment_mod = importlib.import_module("backend.lambda.market_intel.alignment")
compute_evidence_strength = _alignment_mod.compute_evidence_strength
calculate_alignment = _alignment_mod.calculate_alignment

_models_mod = importlib.import_module("backend.lambda.market_intel.models")
AlignmentResult = _models_mod.AlignmentResult


# ---------------------------------------------------------------------------
# Property 8: Evidence strength mapping
# Validates: Requirements 6.2
# ---------------------------------------------------------------------------


class TestEvidenceStrengthMapping:
    """Property 8 — For any (has_skill, evidence_count, has_recent_evidence)
    combination, score matches the specified mapping."""

    @given(
        evidence_count=st.integers(min_value=0, max_value=20),
        has_recent_evidence=st.booleans(),
    )
    @settings(max_examples=100)
    def test_no_skill_returns_zero(
        self, evidence_count: int, has_recent_evidence: bool
    ) -> None:
        """**Validates: Requirements 6.2**

        has_skill=False → 0.0 regardless of other inputs.
        """
        assert compute_evidence_strength(False, evidence_count, has_recent_evidence) == 0.0

    @given(has_recent_evidence=st.booleans())
    @settings(max_examples=100)
    def test_skill_no_evidence_returns_03(self, has_recent_evidence: bool) -> None:
        """**Validates: Requirements 6.2**

        has_skill=True, evidence_count=0 → 0.3.
        """
        assert compute_evidence_strength(True, 0, has_recent_evidence) == 0.3

    @given(
        evidence_count=st.integers(min_value=1, max_value=2),
        has_recent_evidence=st.booleans(),
    )
    @settings(max_examples=100)
    def test_skill_low_evidence_returns_06(
        self, evidence_count: int, has_recent_evidence: bool
    ) -> None:
        """**Validates: Requirements 6.2**

        has_skill=True, evidence_count in [1,2] → 0.6.
        """
        assert compute_evidence_strength(True, evidence_count, has_recent_evidence) == 0.6

    @given(evidence_count=st.integers(min_value=3, max_value=20))
    @settings(max_examples=100)
    def test_skill_high_evidence_no_recent_returns_09(
        self, evidence_count: int
    ) -> None:
        """**Validates: Requirements 6.2**

        has_skill=True, evidence_count >= 3, has_recent_evidence=False → 0.9.
        """
        assert compute_evidence_strength(True, evidence_count, False) == 0.9

    @given(evidence_count=st.integers(min_value=3, max_value=20))
    @settings(max_examples=100)
    def test_skill_high_evidence_recent_returns_10(
        self, evidence_count: int
    ) -> None:
        """**Validates: Requirements 6.2**

        has_skill=True, evidence_count >= 3, has_recent_evidence=True → 1.0.
        """
        assert compute_evidence_strength(True, evidence_count, True) == 1.0

    @given(
        has_skill=st.booleans(),
        evidence_count=st.integers(min_value=0, max_value=20),
        has_recent_evidence=st.booleans(),
    )
    @settings(max_examples=100)
    def test_score_always_in_valid_set(
        self, has_skill: bool, evidence_count: int, has_recent_evidence: bool
    ) -> None:
        """**Validates: Requirements 6.2**

        Output is always one of the five defined values.
        """
        score = compute_evidence_strength(has_skill, evidence_count, has_recent_evidence)
        assert score in {0.0, 0.3, 0.6, 0.9, 1.0}


# ---------------------------------------------------------------------------
# Helpers for Properties 9 and 12
# ---------------------------------------------------------------------------

# Canonical skills known to exist in the taxonomy (from taxonomy.py)
KNOWN_SKILLS = [
    "Python Programming",
    "Java Programming",
    "JavaScript",
    "TypeScript",
    "SQL",
    "Cloud Computing",
    "AWS",
]

TABLE_ENV_VARS = {
    "USER_PROFILES_TABLE": "RegainUserProfiles",
    "CAMPAIGNS_TABLE": "RegainCampaigns",
    "MISSION_HISTORY_TABLE": "RegainMissionHistory",
    "EVIDENCE_VAULT_TABLE": "RegainEvidenceVault",
    "MARKET_DATA_TABLE": "RegainMarketData",
}


def _setup_moto_tables():
    """Create all DynamoDB tables inside an active mock_aws context.

    Returns a dict of boto3 Table resources keyed by logical name.
    """
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
    for env_var, table_name in TABLE_ENV_VARS.items():
        os.environ[env_var] = table_name

    dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
    tables = {}

    tables["user_profiles"] = dynamodb.create_table(
        TableName="RegainUserProfiles",
        KeySchema=[{"AttributeName": "userId", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "userId", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    tables["evidence_vault"] = dynamodb.create_table(
        TableName="RegainEvidenceVault",
        KeySchema=[
            {"AttributeName": "userId", "KeyType": "HASH"},
            {"AttributeName": "evidenceId", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "userId", "AttributeType": "S"},
            {"AttributeName": "evidenceId", "AttributeType": "S"},
            {"AttributeName": "skillTag", "AttributeType": "S"},
            {"AttributeName": "createdAt", "AttributeType": "S"},
        ],
        GlobalSecondaryIndexes=[{
            "IndexName": "skill-index",
            "KeySchema": [
                {"AttributeName": "skillTag", "KeyType": "HASH"},
                {"AttributeName": "createdAt", "KeyType": "RANGE"},
            ],
            "Projection": {"ProjectionType": "ALL"},
        }],
        BillingMode="PAY_PER_REQUEST",
    )
    tables["market_data"] = dynamodb.create_table(
        TableName="RegainMarketData",
        KeySchema=[
            {"AttributeName": "sector", "KeyType": "HASH"},
            {"AttributeName": "timestamp", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "sector", "AttributeType": "S"},
            {"AttributeName": "timestamp", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    return tables


def _insert_market_data(tables, role_id: str, skills_with_freq: list[dict]) -> None:
    """Insert a market data record with given skills into the moto table."""
    # DynamoDB requires Decimal, not float
    dynamo_skills = [
        {"skill": s["skill"], "frequency": Decimal(str(s["frequency"]))}
        for s in skills_with_freq
    ]
    tables["market_data"].put_item(Item={
        "sector": f"role:{role_id}",
        "timestamp": "2025-01-15",
        "roleTitle": f"Test Role {role_id}",
        "category": "technology",
        "demandScore": 75,
        "growthRate": "12.0",
        "trendDirection": "growing",
        "topSkills": dynamo_skills,
        "salaryRange": {"min": 60000, "median": 90000, "max": 120000, "region": "national"},
        "postingVolume": 500,
        "projection": "Faster",
        "source": "synthetic",
        "insights": [],
    })


def _insert_user_profile(tables, user_id: str, skills: list[str]) -> None:
    """Insert a user profile with given skills."""
    tables["user_profiles"].put_item(Item={
        "userId": user_id,
        "skills": skills,
    })


def _insert_evidence(
    tables, user_id: str, skill_tag: str, count: int, recent: bool,
    reference_date: datetime | None = None,
) -> None:
    """Insert evidence items for a user/skill combination."""
    if reference_date is None:
        reference_date = datetime.now(timezone.utc)
    for i in range(count):
        if recent and i == 0:
            created = (reference_date - timedelta(days=5)).isoformat()
        else:
            created = (reference_date - timedelta(days=60 + i)).isoformat()
        tables["evidence_vault"].put_item(Item={
            "userId": user_id,
            "evidenceId": str(uuid.uuid4()),
            "skillTag": skill_tag,
            "createdAt": created,
        })


# ---------------------------------------------------------------------------
# Property 9: Alignment calculation invariants
# Validates: Requirements 6.3, 6.4, 6.5
# ---------------------------------------------------------------------------

# Strategy: generate a list of 1-5 target skills with frequencies
skill_entry_strategy = st.fixed_dictionaries({
    "skill": st.sampled_from(KNOWN_SKILLS),
    "frequency": st.floats(min_value=5.0, max_value=95.0, allow_nan=False, allow_infinity=False),
})

target_skills_strategy = st.lists(
    skill_entry_strategy,
    min_size=1,
    max_size=5,
).filter(lambda lst: len({e["skill"] for e in lst}) == len(lst))  # unique skills


class TestAlignmentCalculationInvariants:
    """Property 9 — For any user skills/evidence and target role skills:
    alignment_pct in [0,100], breakdown covers all target skills,
    gaps sorted by market_weight×(1-user_score) desc,
    strengths sorted by market_weight×user_score desc."""

    @given(
        target_skills=target_skills_strategy,
        user_skill_indices=st.lists(st.integers(min_value=0, max_value=6), max_size=5),
        evidence_counts=st.lists(
            st.integers(min_value=0, max_value=5), min_size=7, max_size=7,
        ),
    )
    @settings(max_examples=100)
    def test_alignment_invariants(
        self,
        target_skills: list[dict],
        user_skill_indices: list[int],
        evidence_counts: list[int],
    ) -> None:
        """**Validates: Requirements 6.3, 6.4, 6.5**

        Verifies alignment_pct range, breakdown completeness,
        and gap/strength sort order.
        """
        with mock_aws():
            tables = _setup_moto_tables()

            role_id = f"test_role_{uuid.uuid4().hex[:8]}"
            user_id = f"test_user_{uuid.uuid4().hex[:8]}"
            reference_date = datetime(2025, 6, 15, tzinfo=timezone.utc)

            # Build the set of user skills from indices
            user_skills = list({KNOWN_SKILLS[i % len(KNOWN_SKILLS)] for i in user_skill_indices})

            # Insert market data
            _insert_market_data(tables, role_id, target_skills)

            # Insert user profile
            _insert_user_profile(tables, user_id, user_skills)

            # Insert evidence for each known skill
            for idx, skill_name in enumerate(KNOWN_SKILLS):
                ec = evidence_counts[idx]
                if ec > 0:
                    has_recent = ec >= 3  # make some recent for variety
                    _insert_evidence(
                        tables, user_id, skill_name, ec,
                        recent=has_recent, reference_date=reference_date,
                    )

            result = calculate_alignment(user_id, role_id, reference_date=reference_date)

            # Invariant 1: alignment_pct in [0, 100]
            assert 0.0 <= result.alignment_pct <= 100.0

            # Invariant 2: breakdown has one entry per target skill
            assert len(result.skill_breakdown) == len(target_skills)

            # Invariant 3: each entry has valid user_score and market_weight
            for entry in result.skill_breakdown:
                assert 0.0 <= entry["user_score"] <= 1.0
                assert entry["market_weight"] > 0.0

            # Invariant 4: top_gaps sorted by market_weight × (1 - user_score) desc
            if len(result.top_gaps) > 1:
                gap_scores = [
                    g["market_weight"] * (1.0 - g["user_score"]) for g in result.top_gaps
                ]
                for i in range(len(gap_scores) - 1):
                    assert gap_scores[i] >= gap_scores[i + 1] - 1e-9

            # Invariant 5: top_strengths sorted by market_weight × user_score desc
            if len(result.top_strengths) > 1:
                strength_scores = [
                    s["market_weight"] * s["user_score"] for s in result.top_strengths
                ]
                for i in range(len(strength_scores) - 1):
                    assert strength_scores[i] >= strength_scores[i + 1] - 1e-9

            # Invariant 6: alignment_pct matches weighted average formula
            total_ws = sum(e["user_score"] * e["market_weight"] for e in result.skill_breakdown)
            total_w = sum(e["market_weight"] for e in result.skill_breakdown)
            if total_w > 0:
                expected_pct = (total_ws / total_w) * 100.0
                assert abs(result.alignment_pct - expected_pct) < 1e-6


# ---------------------------------------------------------------------------
# Property 12: Missing role returns error indicator
# Validates: Requirements 10.5
# ---------------------------------------------------------------------------


class TestMissingRoleReturnsErrorIndicator:
    """Property 12 — For any role_id not in data, returns 0.0% alignment
    without exception."""

    @given(role_id=st.text(min_size=5, max_size=30, alphabet=st.characters(
        whitelist_categories=("Ll", "Lu", "Nd"), whitelist_characters="_-",
    )))
    @settings(max_examples=100)
    def test_missing_role_returns_zero_alignment(
        self, role_id: str
    ) -> None:
        """**Validates: Requirements 10.5**

        Any role_id not in MarketData returns AlignmentResult with
        alignment_pct=0.0 and empty skill_breakdown.
        """
        with mock_aws():
            tables = _setup_moto_tables()

            user_id = f"user_{uuid.uuid4().hex[:8]}"
            _insert_user_profile(tables, user_id, ["Python Programming"])

            result = calculate_alignment(user_id, role_id)

            assert isinstance(result, AlignmentResult)
            assert result.alignment_pct == 0.0
            assert result.skill_breakdown == []
            assert result.top_gaps == []
            assert result.top_strengths == []
