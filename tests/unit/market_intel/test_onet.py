"""Unit tests for the O*NET ingestion module.

Tests API fetching, transformation to MarketDataRecord, DynamoDB writes,
per-role error handling, and the ingest() orchestration function.

**Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6**
"""

import importlib
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

_onet_mod = importlib.import_module(
    "backend.handlers.market_intel.ingestion.onet"
)
_transform = _onet_mod._transform
_get_auth = _onet_mod._get_auth
ingest = _onet_mod.ingest


# -- Fixtures ---------------------------------------------------------------

SAMPLE_OCCUPATION = {
    "code": "15-1256.00",
    "title": "Software Developers and Programmers",
    "tags": {"bright_outlook": "technology"},
    "job_zone": 4,
}

SAMPLE_SKILLS = [
    {"name": "Programming", "score": {"value": "85"}},
    {"name": "Critical Thinking", "score": {"value": "72"}},
    {"name": "Complex Problem Solving", "score": {"value": "68"}},
]


# -- _get_auth tests --------------------------------------------------------

class TestGetAuth:
    """Tests for _get_auth helper."""

    def test_returns_auth_tuple(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ONET_API_KEY", "test-key-123")
        auth = _get_auth()
        assert auth == ("test-key-123", "")

    def test_raises_when_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ONET_API_KEY", raising=False)
        with pytest.raises(ValueError, match="ONET_API_KEY"):
            _get_auth()


# -- _transform tests -------------------------------------------------------

class TestTransform:
    """Tests for _transform — O*NET response to MarketDataRecord."""

    def test_produces_valid_record(self) -> None:
        record = _transform("15-1256.00", SAMPLE_OCCUPATION, SAMPLE_SKILLS)

        assert record.sector == "role:15-1256.00"
        assert record.timestamp == date.today().isoformat()
        assert record.role_title == "Software Developers and Programmers"
        assert record.category == "technology"
        assert record.source == "onet"
        assert record.demand_score == 0  # Calculated later by scoring module
        assert record.projection == "Faster"  # job_zone 4

    def test_skills_sorted_by_score_descending(self) -> None:
        record = _transform("15-1256.00", SAMPLE_OCCUPATION, SAMPLE_SKILLS)

        frequencies = [s["frequency"] for s in record.top_skills]
        assert frequencies == sorted(frequencies, reverse=True)
        assert record.top_skills[0]["skill"] == "Programming"
        assert record.top_skills[0]["frequency"] == 85.0

    def test_skills_include_canonical_mapping(self) -> None:
        record = _transform("15-1256.00", SAMPLE_OCCUPATION, SAMPLE_SKILLS)

        for skill in record.top_skills:
            assert "canonical" in skill
            assert "skill" in skill
            assert "frequency" in skill

    def test_salary_range_structure(self) -> None:
        record = _transform("15-1256.00", SAMPLE_OCCUPATION, SAMPLE_SKILLS)

        assert "min" in record.salary_range
        assert "median" in record.salary_range
        assert "max" in record.salary_range
        assert "region" in record.salary_range

    def test_empty_skills_list(self) -> None:
        record = _transform("15-1256.00", SAMPLE_OCCUPATION, [])
        assert record.top_skills == []

    def test_missing_title_falls_back_to_role_id(self) -> None:
        occupation = {"tags": {}, "job_zone": 3}
        record = _transform("99-9999.00", occupation, [])
        assert record.role_title == "99-9999.00"

    def test_job_zone_to_projection_mapping(self) -> None:
        for zone, expected in [(1, "Slower"), (2, "Average"), (3, "Average"),
                               (4, "Faster"), (5, "Much faster than average")]:
            occ = {**SAMPLE_OCCUPATION, "job_zone": zone}
            record = _transform("test", occ, [])
            assert record.projection == expected

    def test_to_dynamodb_item_roundtrip(self) -> None:
        """Record can serialize to DynamoDB format and back."""
        _models_mod = importlib.import_module("backend.handlers.market_intel.models")
        record = _transform("15-1256.00", SAMPLE_OCCUPATION, SAMPLE_SKILLS)
        item = record.to_dynamodb_item()
        restored = _models_mod.MarketDataRecord.from_dynamodb_item(item)

        assert restored.sector == record.sector
        assert restored.role_title == record.role_title
        assert restored.source == "onet"


# -- ingest tests -----------------------------------------------------------

class TestIngest:
    """Tests for the ingest() orchestration function."""

    @patch.object(_onet_mod, "DynamoDBClient")
    @patch.object(_onet_mod, "_fetch_skills", return_value=SAMPLE_SKILLS)
    @patch.object(_onet_mod, "_fetch_occupation", return_value=SAMPLE_OCCUPATION)
    def test_successful_ingestion(
        self, mock_fetch_occ: MagicMock, mock_fetch_skills: MagicMock,
        mock_db_cls: MagicMock, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ONET_API_KEY", "test-key")
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db

        result = ingest(["15-1256.00"])

        assert result["succeeded"] == ["15-1256.00"]
        assert result["failed"] == []
        mock_db.put_item.assert_called_once()

    @patch.object(_onet_mod, "DynamoDBClient")
    @patch.object(_onet_mod, "_fetch_skills", return_value=SAMPLE_SKILLS)
    @patch.object(_onet_mod, "_fetch_occupation", return_value=SAMPLE_OCCUPATION)
    def test_multiple_roles(
        self, mock_fetch_occ: MagicMock, mock_fetch_skills: MagicMock,
        mock_db_cls: MagicMock, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ONET_API_KEY", "test-key")
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db

        result = ingest(["15-1256.00", "11-1021.00"])

        assert len(result["succeeded"]) == 2
        assert mock_db.put_item.call_count == 2

    @patch.object(_onet_mod, "DynamoDBClient")
    @patch.object(_onet_mod, "_fetch_occupation", side_effect=RuntimeError("API down"))
    def test_per_role_failure_continues(
        self, mock_fetch_occ: MagicMock, mock_db_cls: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Failed roles are logged; remaining roles still process."""
        monkeypatch.setenv("ONET_API_KEY", "test-key")
        mock_db_cls.return_value = MagicMock()

        result = ingest(["bad-role", "also-bad"])

        assert result["succeeded"] == []
        assert len(result["failed"]) == 2
        assert result["failed"][0]["role_id"] == "bad-role"
        assert "API down" in result["failed"][0]["error"]

    @patch.object(_onet_mod, "DynamoDBClient")
    @patch.object(_onet_mod, "_fetch_skills", return_value=SAMPLE_SKILLS)
    @patch.object(_onet_mod, "_fetch_occupation")
    def test_partial_failure(
        self, mock_fetch_occ: MagicMock, mock_fetch_skills: MagicMock,
        mock_db_cls: MagicMock, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Mix of successes and failures returns both lists."""
        monkeypatch.setenv("ONET_API_KEY", "test-key")
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db
        mock_fetch_occ.side_effect = [
            SAMPLE_OCCUPATION,
            RuntimeError("timeout"),
            SAMPLE_OCCUPATION,
        ]

        result = ingest(["role-a", "role-b", "role-c"])

        assert result["succeeded"] == ["role-a", "role-c"]
        assert len(result["failed"]) == 1
        assert result["failed"][0]["role_id"] == "role-b"

    @patch.object(_onet_mod, "DynamoDBClient")
    @patch.object(_onet_mod, "_fetch_skills", return_value=SAMPLE_SKILLS)
    @patch.object(_onet_mod, "_fetch_occupation", return_value=SAMPLE_OCCUPATION)
    def test_empty_role_list(
        self, mock_fetch_occ: MagicMock, mock_fetch_skills: MagicMock,
        mock_db_cls: MagicMock, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ONET_API_KEY", "test-key")
        mock_db_cls.return_value = MagicMock()

        result = ingest([])

        assert result == {"succeeded": [], "failed": []}

    @patch.object(_onet_mod, "DynamoDBClient")
    @patch.object(_onet_mod, "_fetch_skills", return_value=SAMPLE_SKILLS)
    @patch.object(_onet_mod, "_fetch_occupation", return_value=SAMPLE_OCCUPATION)
    def test_writes_correct_dynamodb_item(
        self, mock_fetch_occ: MagicMock, mock_fetch_skills: MagicMock,
        mock_db_cls: MagicMock, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verifies the DynamoDB put_item receives correct table and item shape."""
        monkeypatch.setenv("ONET_API_KEY", "test-key")
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db

        ingest(["15-1256.00"])

        call_args = mock_db.put_item.call_args
        assert call_args[0][0] == "market_data"
        item = call_args[0][1]
        assert item["sector"] == "role:15-1256.00"
        assert item["source"] == "onet"
        assert "topSkills" in item
