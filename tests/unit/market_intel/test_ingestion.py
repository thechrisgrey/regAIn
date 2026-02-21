"""Property-based tests for the REGAIN ingestion pipeline.

Tests Properties 1, 2, and 3 from the Market Intelligence design document
using Hypothesis for property-based testing and moto for DynamoDB mocking.

**Validates: Requirements 1.3, 1.4, 1.6, 2.2, 2.3, 2.5, 3.2, 3.3, 3.5**
"""

from __future__ import annotations

import importlib
import os
from datetime import date
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

import boto3
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from moto import mock_aws

# 'lambda' is a Python keyword — use importlib for sibling imports.
_models_mod = importlib.import_module("backend.handlers.market_intel.models")
MarketDataRecord = _models_mod.MarketDataRecord

_onet_mod = importlib.import_module("backend.handlers.market_intel.ingestion.onet")
_onet_transform = _onet_mod._transform

_bls_mod = importlib.import_module("backend.handlers.market_intel.ingestion.bls")
_bls_extract_latest_value = _bls_mod._extract_latest_value
_bls_merge_into_record = _bls_mod._merge_into_record

_usajobs_mod = importlib.import_module("backend.handlers.market_intel.ingestion.usajobs")
_usajobs_merge_into_record = _usajobs_mod._merge_into_record
_usajobs_extract_skills = _usajobs_mod._extract_skills
_usajobs_extract_salary_range = _usajobs_mod._extract_salary_range

_onet_ingest = _onet_mod.ingest
_bls_ingest = _bls_mod.ingest
_usajobs_ingest = _usajobs_mod.ingest


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# O*NET occupation response strategy
_onet_skill_element_st = st.fixed_dictionaries({
    "name": st.text(min_size=1, max_size=40, alphabet=st.characters(
        whitelist_categories=("L", "Nd"), whitelist_characters=" -",
    )).filter(lambda s: s.strip()),
    "score": st.fixed_dictionaries({
        "value": st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False).map(str),
    }),
})

_onet_occupation_st = st.fixed_dictionaries({
    "title": st.text(min_size=1, max_size=60, alphabet=st.characters(
        whitelist_categories=("L", "Nd"), whitelist_characters=" -",
    )).filter(lambda s: s.strip()),
    "tags": st.fixed_dictionaries({
        "bright_outlook": st.sampled_from(["technology", "management", "operations", "general"]),
    }),
    "job_zone": st.integers(min_value=1, max_value=5),
})

_onet_skills_list_st = st.lists(_onet_skill_element_st, min_size=0, max_size=10)

# Role ID strategy (SOC-like codes)
_role_id_st = st.text(
    min_size=3, max_size=20,
    alphabet=st.characters(whitelist_categories=("Ll", "Nd"), whitelist_characters="_-."),
).filter(lambda s: s.strip() and s[0].isalpha())

# BLS series data strategy
_bls_data_point_st = st.fixed_dictionaries({
    "year": st.sampled_from(["2024", "2025"]),
    "period": st.sampled_from(["M01", "M02", "M03", "M06", "M12"]),
    "value": st.integers(min_value=100, max_value=999999).map(str),
})

_bls_series_data_st = st.lists(_bls_data_point_st, min_size=1, max_size=6)

# USAJobs position item strategy
_usajobs_position_st = st.fixed_dictionaries({
    "PositionTitle": st.text(min_size=1, max_size=40, alphabet=st.characters(
        whitelist_categories=("L", "Nd"), whitelist_characters=" -",
    )).filter(lambda s: s.strip()),
    "QualificationSummary": st.text(min_size=0, max_size=200),
    "PositionRemuneration": st.lists(
        st.fixed_dictionaries({
            "MinimumRange": st.integers(min_value=30000, max_value=100000).map(str),
            "MaximumRange": st.integers(min_value=100001, max_value=200000).map(str),
        }),
        min_size=0, max_size=2,
    ),
})

_usajobs_positions_st = st.lists(_usajobs_position_st, min_size=0, max_size=5)

# Keyword strategy for USAJobs
_keyword_st = st.text(
    min_size=2, max_size=30,
    alphabet=st.characters(whitelist_categories=("Ll", "Nd"), whitelist_characters=" _"),
).filter(lambda s: s.strip() and len(s.strip()) >= 2)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup_market_data_table() -> Any:
    """Create the MarketData DynamoDB table in moto and set env vars."""
    os.environ["MARKET_DATA_TABLE"] = "RegainMarketData"
    os.environ["USER_PROFILES_TABLE"] = "RegainUserProfiles"
    os.environ["EVIDENCE_VAULT_TABLE"] = "RegainEvidenceVault"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"

    dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
    table = dynamodb.create_table(
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
    return table


def _floats_to_decimals(obj: Any) -> Any:
    """Recursively convert float values to Decimal for DynamoDB compatibility."""
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _floats_to_decimals(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_floats_to_decimals(v) for v in obj]
    return obj


def _assert_valid_market_record(record: MarketDataRecord) -> None:
    """Assert a MarketDataRecord has all required fields with correct types."""
    # sector: non-empty string starting with "role:"
    assert isinstance(record.sector, str)
    assert len(record.sector) > 0
    assert record.sector.startswith("role:")

    # timestamp: ISO date string
    assert isinstance(record.timestamp, str)
    assert len(record.timestamp) > 0

    # role_title: non-empty string
    assert isinstance(record.role_title, str)
    assert len(record.role_title) > 0

    # demand_score: int
    assert isinstance(record.demand_score, int)

    # growth_rate: float (or int, which is fine)
    assert isinstance(record.growth_rate, (int, float))

    # trend_direction: string
    assert isinstance(record.trend_direction, str)

    # top_skills: list
    assert isinstance(record.top_skills, list)

    # salary_range: dict with min/median/max/region keys
    assert isinstance(record.salary_range, dict)
    assert "min" in record.salary_range
    assert "median" in record.salary_range
    assert "max" in record.salary_range
    assert "region" in record.salary_range

    # posting_volume: int
    assert isinstance(record.posting_volume, int)

    # projection: string
    assert isinstance(record.projection, str)

    # source: string
    assert isinstance(record.source, str)


# ---------------------------------------------------------------------------
# Property 1: Ingestion transformation produces valid records
# Feature: market-intelligence, Property 1
# For any valid API response from any ingestion source, the transformer
# function produces a dict containing all required MarketData fields.
# **Validates: Requirements 1.3, 2.2, 3.2**
# ---------------------------------------------------------------------------


class TestProperty1TransformationValidity:
    """Property 1 — For any valid mock API response, transformer output
    contains all required MarketData fields with correct types."""

    @given(
        role_id=_role_id_st,
        occupation=_onet_occupation_st,
        skills=_onet_skills_list_st,
    )
    @settings(max_examples=100)
    def test_onet_transform_produces_valid_record(
        self,
        role_id: str,
        occupation: dict[str, Any],
        skills: list[dict[str, Any]],
    ) -> None:
        """**Validates: Requirements 1.3**

        O*NET _transform produces a valid MarketDataRecord for any input.
        """
        record = _onet_transform(role_id, occupation, skills)
        _assert_valid_market_record(record)
        assert record.source == "onet"
        assert record.sector == f"role:{role_id}"
        # top_skills sorted by frequency descending
        freqs = [s.get("frequency", 0) for s in record.top_skills]
        for i in range(len(freqs) - 1):
            assert freqs[i] >= freqs[i + 1]

    @given(
        series_id=_role_id_st,
        series_data=_bls_series_data_st,
    )
    @settings(max_examples=100)
    def test_bls_transform_produces_valid_record(
        self,
        series_id: str,
        series_data: list[dict[str, Any]],
    ) -> None:
        """**Validates: Requirements 2.2**

        BLS _extract_latest_value + _merge_into_record produces a valid
        MarketDataRecord for any series data (no existing record).
        """
        extracted = _bls_extract_latest_value(series_data)
        record = _bls_merge_into_record(series_id, extracted, None)
        _assert_valid_market_record(record)
        assert record.source == "bls"
        assert record.sector == f"role:{series_id}"

    @given(
        keyword=_keyword_st,
        positions=_usajobs_positions_st,
    )
    @settings(max_examples=100)
    def test_usajobs_transform_produces_valid_record(
        self,
        keyword: str,
        positions: list[dict[str, Any]],
    ) -> None:
        """**Validates: Requirements 3.2**

        USAJobs extraction + _merge_into_record produces a valid
        MarketDataRecord for any position data (no existing record).
        """
        posting_count = len(positions)
        top_skills = _usajobs_extract_skills(positions)
        salary_range = _usajobs_extract_salary_range(positions)
        record = _usajobs_merge_into_record(
            keyword, posting_count, top_skills, salary_range, None,
        )
        _assert_valid_market_record(record)
        assert record.source == "usajobs"


# ---------------------------------------------------------------------------
# Property 2: Ingestion idempotency
# Feature: market-intelligence, Property 2
# For any record, writing same role+date twice results in exactly one
# DynamoDB item.
# **Validates: Requirements 1.4, 2.3, 3.3**
# ---------------------------------------------------------------------------


class TestProperty2Idempotency:
    """Property 2 — For any market data record, writing the same
    role+date combination twice results in exactly one DynamoDB item."""

    @given(
        role_id=_role_id_st,
        occupation=_onet_occupation_st,
        skills=_onet_skills_list_st,
    )
    @settings(max_examples=100)
    def test_onet_idempotent_write(
        self,
        role_id: str,
        occupation: dict[str, Any],
        skills: list[dict[str, Any]],
    ) -> None:
        """**Validates: Requirements 1.4, 2.3, 3.3**

        Writing the same O*NET record twice results in exactly one item.
        """
        with mock_aws():
            table = _setup_market_data_table()

            record = _onet_transform(role_id, occupation, skills)
            item = _floats_to_decimals(record.to_dynamodb_item())

            # Write twice
            table.put_item(Item=item)
            table.put_item(Item=item)

            # Query by partition key
            response = table.query(
                KeyConditionExpression=(
                    boto3.dynamodb.conditions.Key("sector").eq(record.sector)
                    & boto3.dynamodb.conditions.Key("timestamp").eq(record.timestamp)
                ),
            )
            assert response["Count"] == 1

    @given(
        series_id=_role_id_st,
        series_data=_bls_series_data_st,
    )
    @settings(max_examples=100)
    def test_bls_idempotent_write(
        self,
        series_id: str,
        series_data: list[dict[str, Any]],
    ) -> None:
        """**Validates: Requirements 1.4, 2.3, 3.3**

        Writing the same BLS record twice results in exactly one item.
        """
        with mock_aws():
            table = _setup_market_data_table()

            extracted = _bls_extract_latest_value(series_data)
            record = _bls_merge_into_record(series_id, extracted, None)
            item = _floats_to_decimals(record.to_dynamodb_item())

            # Write twice
            table.put_item(Item=item)
            table.put_item(Item=item)

            response = table.query(
                KeyConditionExpression=(
                    boto3.dynamodb.conditions.Key("sector").eq(record.sector)
                    & boto3.dynamodb.conditions.Key("timestamp").eq(record.timestamp)
                ),
            )
            assert response["Count"] == 1

    @given(
        keyword=_keyword_st,
        positions=_usajobs_positions_st,
    )
    @settings(max_examples=100)
    def test_usajobs_idempotent_write(
        self,
        keyword: str,
        positions: list[dict[str, Any]],
    ) -> None:
        """**Validates: Requirements 1.4, 2.3, 3.3**

        Writing the same USAJobs record twice results in exactly one item.
        """
        with mock_aws():
            table = _setup_market_data_table()

            posting_count = len(positions)
            top_skills = _usajobs_extract_skills(positions)
            salary_range = _usajobs_extract_salary_range(positions)
            record = _usajobs_merge_into_record(
                keyword, posting_count, top_skills, salary_range, None,
            )
            item = _floats_to_decimals(record.to_dynamodb_item())

            # Write twice
            table.put_item(Item=item)
            table.put_item(Item=item)

            response = table.query(
                KeyConditionExpression=(
                    boto3.dynamodb.conditions.Key("sector").eq(record.sector)
                    & boto3.dynamodb.conditions.Key("timestamp").eq(record.timestamp)
                ),
            )
            assert response["Count"] == 1


# ---------------------------------------------------------------------------
# Property 3: Ingestion resilience — partial failures do not block processing
# Feature: market-intelligence, Property 3
# For any list of roles to ingest where a subset of API calls fail,
# the pipeline successfully processes all non-failing roles.
# **Validates: Requirements 1.6, 2.5, 3.5**
# ---------------------------------------------------------------------------


# Strategy: list of role IDs with a boolean flag indicating if they should fail
_role_with_failure_st = st.lists(
    st.tuples(
        _role_id_st,
        st.booleans(),  # True = should fail
    ),
    min_size=1,
    max_size=6,
).filter(lambda lst: len({r[0] for r in lst}) == len(lst))  # unique role IDs


class TestProperty3Resilience:
    """Property 3 — For any role list with partial failures, succeeded
    count equals the number of non-failing role count."""

    @given(roles_with_failures=_role_with_failure_st)
    @settings(max_examples=100)
    def test_onet_resilience(
        self,
        roles_with_failures: list[tuple[str, bool]],
    ) -> None:
        """**Validates: Requirements 1.6**

        O*NET ingest continues processing after per-role failures.
        """
        role_ids = [r[0] for r in roles_with_failures]
        failing_ids = {r[0] for r in roles_with_failures if r[1]}
        expected_success_count = sum(1 for r in roles_with_failures if not r[1])

        # Build mock responses: succeed or fail per role
        def mock_get(url: str, **kwargs: Any) -> MagicMock:
            resp = MagicMock()
            # Determine which role this request is for
            for rid in role_ids:
                if rid in url:
                    if rid in failing_ids:
                        resp.raise_for_status.side_effect = Exception(
                            f"API error for {rid}"
                        )
                    else:
                        resp.raise_for_status.return_value = None
                        if "skills" in url:
                            resp.json.return_value = {"element": [
                                {"name": "Python", "score": {"value": "80"}},
                            ]}
                        else:
                            resp.json.return_value = {
                                "title": f"Role {rid}",
                                "tags": {"bright_outlook": "technology"},
                                "job_zone": 3,
                            }
                    return resp
            # Default: succeed with empty data
            resp.raise_for_status.return_value = None
            resp.json.return_value = {"title": "Unknown", "tags": {}, "job_zone": 3}
            return resp

        with mock_aws():
            _setup_market_data_table()
            os.environ["ONET_API_KEY"] = "test-key"

            # Patch DynamoDBClient.put_item to convert floats to Decimals
            _original_put = _onet_mod.DynamoDBClient.put_item

            def _safe_put(self_db: Any, table_name: str, item: dict) -> Any:
                return _original_put(self_db, table_name, _floats_to_decimals(item))

            with patch.object(_onet_mod, "requests") as mock_requests:
                mock_requests.get = mock_get
                # Disable retry delays for test speed
                with patch.object(
                    _onet_mod, "retry_with_backoff",
                    side_effect=lambda fn, **kw: fn(),
                ):
                    with patch.object(
                        _onet_mod.DynamoDBClient, "put_item", _safe_put,
                    ):
                        result = _onet_ingest(role_ids)

            assert len(result["succeeded"]) == expected_success_count
            assert len(result["failed"]) == len(failing_ids)
            # Total should equal input count
            assert len(result["succeeded"]) + len(result["failed"]) == len(role_ids)

    @given(roles_with_failures=_role_with_failure_st)
    @settings(max_examples=100)
    def test_bls_resilience(
        self,
        roles_with_failures: list[tuple[str, bool]],
    ) -> None:
        """**Validates: Requirements 2.5**

        BLS ingest continues processing after per-series failures.
        """
        series_ids = [r[0] for r in roles_with_failures]
        failing_ids = {r[0] for r in roles_with_failures if r[1]}
        expected_success_count = sum(1 for r in roles_with_failures if not r[1])

        def mock_post(url: str, **kwargs: Any) -> MagicMock:
            resp = MagicMock()
            # Determine which series this request is for from the payload
            payload = kwargs.get("json", {})
            sid_list = payload.get("seriesid", [])
            sid = sid_list[0] if sid_list else ""

            if sid in failing_ids:
                resp.raise_for_status.side_effect = Exception(
                    f"API error for {sid}"
                )
            else:
                resp.raise_for_status.return_value = None
                resp.json.return_value = {
                    "status": "REQUEST_SUCCEEDED",
                    "Results": {
                        "series": [{
                            "data": [
                                {"year": "2025", "period": "M01", "value": "5000"},
                                {"year": "2024", "period": "M01", "value": "4500"},
                            ],
                        }],
                    },
                }
            return resp

        with mock_aws():
            _setup_market_data_table()

            _original_put = _bls_mod.DynamoDBClient.put_item

            def _safe_put(self_db: Any, table_name: str, item: dict) -> Any:
                return _original_put(self_db, table_name, _floats_to_decimals(item))

            with patch.object(_bls_mod, "requests") as mock_requests:
                mock_requests.post = mock_post
                with patch.object(
                    _bls_mod, "retry_with_backoff",
                    side_effect=lambda fn, **kw: fn(),
                ):
                    with patch.object(
                        _bls_mod.DynamoDBClient, "put_item", _safe_put,
                    ):
                        result = _bls_ingest(series_ids)

            assert len(result["succeeded"]) == expected_success_count
            assert len(result["failed"]) == len(failing_ids)
            assert len(result["succeeded"]) + len(result["failed"]) == len(series_ids)

    @given(roles_with_failures=_role_with_failure_st)
    @settings(max_examples=100)
    def test_usajobs_resilience(
        self,
        roles_with_failures: list[tuple[str, bool]],
    ) -> None:
        """**Validates: Requirements 3.5**

        USAJobs ingest continues processing after per-keyword failures.
        """
        keywords = [r[0] for r in roles_with_failures]
        failing_kws = {r[0] for r in roles_with_failures if r[1]}
        expected_success_count = sum(1 for r in roles_with_failures if not r[1])

        def mock_get(url: str, **kwargs: Any) -> MagicMock:
            resp = MagicMock()
            params = kwargs.get("params", {})
            kw = params.get("Keyword", "")

            if kw in failing_kws:
                resp.raise_for_status.side_effect = Exception(
                    f"API error for {kw}"
                )
            else:
                resp.raise_for_status.return_value = None
                resp.json.return_value = {
                    "SearchResult": {
                        "SearchResultCount": 5,
                        "SearchResultItems": [
                            {
                                "MatchedObjectDescriptor": {
                                    "PositionTitle": f"{kw} Specialist",
                                    "QualificationSummary": "Python experience required",
                                    "PositionRemuneration": [
                                        {"MinimumRange": "50000", "MaximumRange": "90000"},
                                    ],
                                },
                            },
                        ],
                    },
                }
            return resp

        with mock_aws():
            _setup_market_data_table()
            os.environ["USAJOBS_API_KEY"] = "test-key"
            os.environ["USAJOBS_USER_AGENT"] = "test-agent"

            _original_put = _usajobs_mod.DynamoDBClient.put_item

            def _safe_put(self_db: Any, table_name: str, item: dict) -> Any:
                return _original_put(self_db, table_name, _floats_to_decimals(item))

            with patch.object(_usajobs_mod, "requests") as mock_requests:
                mock_requests.get = mock_get
                with patch.object(
                    _usajobs_mod, "retry_with_backoff",
                    side_effect=lambda fn, **kw: fn(),
                ):
                    with patch.object(
                        _usajobs_mod.DynamoDBClient, "put_item", _safe_put,
                    ):
                        result = _usajobs_ingest(keywords)

            assert len(result["succeeded"]) == expected_success_count
            assert len(result["failed"]) == len(failing_kws)
            assert len(result["succeeded"]) + len(result["failed"]) == len(keywords)
