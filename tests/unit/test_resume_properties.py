"""Property-based tests for the Agent-Friendly Resume feature.

Uses Hypothesis to validate correctness properties across random inputs.
Each property test maps to a design-doc property and validates specific
requirements from the spec.
"""

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest
import yaml
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from backend.handlers.shared.dynamodb import DynamoDBClient
from backend.handlers.shared.models import (
    Campaign,
    Evidence,
    Mission,
    UserProfile,
)
from backend.handlers.shared.resume_models import ResumeData
from backend.handlers.resume.service import (
    MAX_DAILY_GENERATIONS,
    REGAIN_VERSION,
    REQUIRED_SECTIONS,
    SCHEMA_VERSION,
    RateLimitError,
    ResumeGenerationError,
    ResumeService,
    _evidence_count_to_proficiency,
)

# ---------------------------------------------------------------------------
# Hypothesis strategies for generating valid domain objects
# ---------------------------------------------------------------------------

safe_text = st.text(
    min_size=1,
    max_size=30,
    alphabet=st.characters(whitelist_categories=("L", "N", "Zs"), whitelist_characters="-_"),
).filter(lambda s: s.strip())

skill_names = st.sampled_from([
    "Python", "JavaScript", "DataAnalysis", "ProjectManagement",
    "APIDesign", "MachineLearning", "CloudArchitecture", "Testing",
    "Leadership", "Communication", "SQL", "Docker",
])

personas = st.sampled_from(["veteran", "ai_displaced", "career_pivoter"])
phases = st.sampled_from(["foundation", "expansion", "launch"])

user_profiles_st = st.builds(
    UserProfile,
    user_id=st.text(min_size=5, max_size=20, alphabet=st.characters(whitelist_categories=("L", "N"))),
    email=st.from_regex(r"[a-z]{3,8}@[a-z]{3,6}\.(com|org|net)", fullmatch=True),
    name=st.text(min_size=2, max_size=30, alphabet=st.characters(whitelist_categories=("L", "Zs"))).filter(lambda s: s.strip()),
    persona=personas,
    onboarding_completed=st.just(True),
    created_at=st.just("2025-01-01T00:00:00Z"),
    target_role=safe_text,
    skills=st.lists(skill_names, min_size=1, max_size=5, unique=True),
)

campaigns_st = st.builds(
    Campaign,
    user_id=st.just("ignored"),  # overridden in resume_data_st
    campaign_id=st.uuids().map(str),
    title=safe_text,
    phase=phases,
    status=st.just("active"),
    start_date=st.just("2025-01-15"),
    target_role=safe_text,
    skills_focus=st.lists(skill_names, min_size=1, max_size=4, unique=True),
)

missions_st = st.builds(
    Mission,
    user_id=st.just("ignored"),
    mission_id=st.uuids().map(str),
    campaign_id=st.just("ignored"),
    title=safe_text,
    description=st.text(min_size=10, max_size=100, alphabet=st.characters(whitelist_categories=("L", "N", "Zs"))),
    status=st.just("completed"),
    completed_date=st.just("2025-02-01"),
    evidence_id=st.uuids().map(str),
)

evidence_st = st.builds(
    Evidence,
    user_id=st.just("ignored"),
    evidence_id=st.uuids().map(str),
    mission_id=st.just("ignored"),
    skill_tag=skill_names,
    reflection=st.text(min_size=20, max_size=200, alphabet=st.characters(whitelist_categories=("L", "N", "Zs", "Po"))),
    created_at=st.just("2025-02-01T10:00:00Z"),
    artifact_url=st.none(),
)

market_alignment_st = st.fixed_dictionaries({
    "target_role": safe_text,
    "alignment_pct": st.integers(min_value=0, max_value=100),
    "top_skills": st.lists(skill_names, min_size=1, max_size=5),
    "skill_gaps": st.lists(skill_names, min_size=0, max_size=3),
})


def resume_data_st(min_missions: int = 1, max_missions: int = 15,
                   min_evidence: int = 1, max_evidence: int = 20):
    """Strategy for generating valid ResumeData with linked user_ids."""
    return st.builds(
        _build_resume_data,
        profile=user_profiles_st,
        campaign=campaigns_st,
        missions=st.lists(missions_st, min_size=min_missions, max_size=max_missions),
        evidence=st.lists(evidence_st, min_size=min_evidence, max_size=max_evidence),
        market=market_alignment_st,
    )


def _build_resume_data(
    profile: UserProfile,
    campaign: Campaign,
    missions: List[Mission],
    evidence: List[Evidence],
    market: Dict[str, Any],
) -> ResumeData:
    """Link user_ids across all objects for consistency."""
    uid = profile.user_id
    campaign.user_id = uid
    for m in missions:
        m.user_id = uid
        m.campaign_id = campaign.campaign_id
    for e in evidence:
        e.user_id = uid
    return ResumeData(
        profile=profile,
        campaign=campaign,
        completed_missions=missions,
        evidence_entries=evidence,
        market_alignment=market,
    )


# ---------------------------------------------------------------------------
# Helper: build a deterministic valid resume from ResumeData
# ---------------------------------------------------------------------------

def _build_valid_resume(data: ResumeData) -> str:
    """Build a structurally valid resume mimicking Nova Lite output.

    Used as the mock Bedrock response so property tests can validate
    structural invariants without calling a real LLM.
    """
    # Build skills for frontmatter
    skill_evidence: Dict[str, List[Evidence]] = {}
    for ev in data.evidence_entries:
        skill_evidence.setdefault(ev.skill_tag, []).append(ev)

    skills_yaml = []
    for skill_name, entries in skill_evidence.items():
        count = len(entries)
        best = max(entries, key=lambda e: len(e.reflection))
        skills_yaml.append({
            "skill_name": skill_name,
            "evidence_count": count,
            "strongest_evidence_summary": best.reflection[:200],
            "proficiency_indicator": _evidence_count_to_proficiency(count),
        })

    # Top accomplishments (3-5)
    sorted_evidence = sorted(data.evidence_entries, key=lambda e: len(e.reflection), reverse=True)
    num_accomplishments = min(max(3, len(sorted_evidence)), 5)
    top_accomplishments = [e.reflection[:100] for e in sorted_evidence[:num_accomplishments]]

    # Calculate progress
    progress_pct = min(round(len(data.completed_missions) / 30 * 100, 1), 100.0)

    frontmatter = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "regain_version": REGAIN_VERSION,
        "name": data.profile.name,
        "target_role": data.campaign.target_role,
        "transition_type": data.profile.persona,
        "skills": skills_yaml,
        "campaign_phase": data.campaign.phase,
        "campaign_progress_pct": progress_pct,
        "market_alignment_score": data.market_alignment.get("alignment_pct", 0),
        "missions_completed": len(data.completed_missions),
        "evidence_items": len(data.evidence_entries),
        "top_accomplishments": top_accomplishments,
    }

    yaml_str = yaml.safe_dump(frontmatter, default_flow_style=False, sort_keys=False)

    # Build mission highlights
    num_missions = len(data.completed_missions)
    if num_missions >= 8:
        highlights = data.completed_missions[:min(num_missions, 8)]
    else:
        highlights = data.completed_missions

    highlights_text = ""
    for m in highlights:
        highlights_text += f"- **{m.title}** (completed {m.completed_date or 'N/A'}): {m.description[:100]}\n"

    # Build skills section
    skills_body = ""
    for skill_name, entries in skill_evidence.items():
        skills_body += f"### {skill_name}\n"
        for e in entries[:3]:
            skills_body += f"- {e.reflection[:100]}\n"

    body = f"""## Professional Summary

{data.profile.name} is a {data.profile.persona.replace('_', ' ')} transitioning to {data.campaign.target_role}. With {num_missions} completed missions and documented evidence, they demonstrate consistent growth. Their campaign is in the {data.campaign.phase} phase.

## Skills and Demonstrated Capabilities

{skills_body}

## Campaign Progress

Currently in the {data.campaign.phase} phase with {progress_pct}% progress. Trajectory is positive based on mission completion rate.

## Mission History Highlights

{highlights_text}

## Market Alignment

Target role: {data.campaign.target_role}. Alignment score: {data.market_alignment.get('alignment_pct', 0)}%. Key demonstrated skills align with market demand."""

    return f"---\n{yaml_str}---\n{body}"


def _mock_bedrock_response(resume_content: str) -> MagicMock:
    """Create a mock Bedrock invoke_model response."""
    body_payload = json.dumps({
        "output": {"message": {"content": [{"text": resume_content}]}}
    }).encode("utf-8")
    mock_body = MagicMock()
    mock_body.read.return_value = body_payload
    return {"body": mock_body}


# ===========================================================================
# Property 1: Resume document structure validity
# Feature: agent-friendly-resume, Property 1: Resume document structure validity
# Validates: Requirements 1.1, 1.2, 1.3, 1.5, 11.2, 11.3
# ===========================================================================

class TestProperty1ResumeStructure:
    """Property 1: Resume document structure validity."""

    @given(data=resume_data_st())
    @settings(max_examples=100)
    def test_resume_has_valid_yaml_frontmatter(self, data: ResumeData) -> None:
        """Generated resume starts with valid YAML frontmatter delimited by ---."""
        resume = _build_valid_resume(data)
        service = ResumeService(
            db_client=MagicMock(),
            s3_client=MagicMock(),
            bedrock_client=MagicMock(),
        )
        service.bedrock.invoke_model.return_value = _mock_bedrock_response(resume)

        result = service._synthesize(data)

        # Must start with ---
        assert result.startswith("---"), "Resume must start with YAML frontmatter delimiter"

        # Split on --- to get frontmatter
        parts = result.split("---", 2)
        assert len(parts) >= 3, "Resume must have opening and closing --- delimiters"

        # YAML must be parseable
        parsed = yaml.safe_load(parts[1])
        assert isinstance(parsed, dict), "Frontmatter must parse to a dict"

        # All required frontmatter fields present with correct types
        required_str_fields = [
            "schema_version", "generated_at", "regain_version",
            "name", "target_role", "transition_type", "campaign_phase",
        ]
        for field in required_str_fields:
            assert field in parsed, f"Missing frontmatter field: {field}"
            assert isinstance(parsed[field], str), f"{field} must be a string"

        required_num_fields = [
            "campaign_progress_pct", "market_alignment_score",
            "missions_completed", "evidence_items",
        ]
        for field in required_num_fields:
            assert field in parsed, f"Missing frontmatter field: {field}"
            assert isinstance(parsed[field], (int, float)), f"{field} must be a number"

        # Skills array
        assert "skills" in parsed, "Missing skills array"
        assert isinstance(parsed["skills"], list), "skills must be a list"
        for skill in parsed["skills"]:
            assert isinstance(skill, dict), "Each skill must be a dict"
            assert "skill_name" in skill
            assert "evidence_count" in skill
            assert isinstance(skill["evidence_count"], int)
            assert "strongest_evidence_summary" in skill
            assert "proficiency_indicator" in skill

        # Top accomplishments
        assert "top_accomplishments" in parsed
        assert isinstance(parsed["top_accomplishments"], list)

    @given(data=resume_data_st())
    @settings(max_examples=100)
    def test_resume_has_five_sections_in_order(self, data: ResumeData) -> None:
        """Resume body contains all 5 required sections in correct order."""
        resume = _build_valid_resume(data)
        service = ResumeService(
            db_client=MagicMock(),
            s3_client=MagicMock(),
            bedrock_client=MagicMock(),
        )
        service.bedrock.invoke_model.return_value = _mock_bedrock_response(resume)

        result = service._synthesize(data)

        # Extract body after frontmatter
        parts = result.split("---", 2)
        body = parts[2]

        # All 5 sections present in order
        last_pos = -1
        for section in REQUIRED_SECTIONS:
            header = f"## {section}"
            pos = body.find(header)
            assert pos != -1, f"Missing section: {section}"
            assert pos > last_pos, f"Section '{section}' is out of order"
            last_pos = pos


# ===========================================================================
# Property 2: YAML frontmatter round-trip
# Feature: agent-friendly-resume, Property 2: YAML frontmatter round-trip
# Validates: Requirements 1.6
# ===========================================================================

# Strategy for generating YAML-safe frontmatter dicts
frontmatter_dicts_st = st.fixed_dictionaries({
    "schema_version": st.just("1.0"),
    "generated_at": st.just("2025-01-15T14:30:00Z"),
    "regain_version": st.just("1.0.0"),
    "name": safe_text,
    "target_role": safe_text,
    "transition_type": personas,
    "skills": st.lists(
        st.fixed_dictionaries({
            "skill_name": skill_names,
            "evidence_count": st.integers(min_value=1, max_value=50),
            "strongest_evidence_summary": safe_text,
            "proficiency_indicator": st.sampled_from(["beginner", "intermediate", "advanced", "expert"]),
        }),
        min_size=1,
        max_size=5,
    ),
    "campaign_phase": phases,
    "campaign_progress_pct": st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    "market_alignment_score": st.integers(min_value=0, max_value=100),
    "missions_completed": st.integers(min_value=1, max_value=100),
    "evidence_items": st.integers(min_value=1, max_value=200),
    "top_accomplishments": st.lists(safe_text, min_size=3, max_size=5),
})


class TestProperty2YAMLRoundTrip:
    """Property 2: YAML frontmatter round-trip equivalence."""

    @given(frontmatter=frontmatter_dicts_st)
    @settings(max_examples=100)
    def test_yaml_round_trip_equivalence(self, frontmatter: Dict[str, Any]) -> None:
        """Parsing YAML, serializing, then parsing again produces equivalent object."""
        # First serialization
        yaml_str = yaml.safe_dump(frontmatter, default_flow_style=False)

        # Parse back
        parsed_once = yaml.safe_load(yaml_str)

        # Serialize again
        yaml_str_2 = yaml.safe_dump(parsed_once, default_flow_style=False)

        # Parse again
        parsed_twice = yaml.safe_load(yaml_str_2)

        assert parsed_once == parsed_twice, "YAML round-trip must produce equivalent objects"


# ===========================================================================
# Property 3: Output excludes sensitive data
# Feature: agent-friendly-resume, Property 3: Output excludes sensitive data
# Validates: Requirements 1.4, 11.4
# ===========================================================================

# Strategy for profiles with explicit PII fields
pii_profiles_st = st.builds(
    UserProfile,
    user_id=st.uuids().map(str),
    email=st.from_regex(r"[a-z]{3,8}@[a-z]{3,6}\.(com|org|net)", fullmatch=True),
    name=st.text(min_size=2, max_size=20, alphabet=st.characters(whitelist_categories=("L",))).filter(lambda s: s.strip()),
    persona=personas,
    onboarding_completed=st.just(True),
    created_at=st.just("2025-01-01T00:00:00Z"),
    target_role=safe_text,
    skills=st.lists(skill_names, min_size=1, max_size=3, unique=True),
)


class TestProperty3SensitiveDataExclusion:
    """Property 3: Output excludes sensitive data."""

    @given(
        profile=pii_profiles_st,
        campaign=campaigns_st,
        missions=st.lists(missions_st, min_size=1, max_size=5),
        evidence=st.lists(evidence_st, min_size=1, max_size=5),
        market=market_alignment_st,
    )
    @settings(max_examples=100)
    def test_no_pii_in_resume_output(
        self,
        profile: UserProfile,
        campaign: Campaign,
        missions: List[Mission],
        evidence: List[Evidence],
        market: Dict[str, Any],
    ) -> None:
        """Resume output must not contain email, phone, address, or internal IDs."""
        data = _build_resume_data(profile, campaign, missions, evidence, market)
        resume = _build_valid_resume(data)

        service = ResumeService(
            db_client=MagicMock(),
            s3_client=MagicMock(),
            bedrock_client=MagicMock(),
        )
        service.bedrock.invoke_model.return_value = _mock_bedrock_response(resume)
        result = service._synthesize(data)

        # Email must not appear
        assert profile.email not in result, f"Email '{profile.email}' leaked into resume"

        # User ID (UUID) must not appear
        assert profile.user_id not in result, f"User ID '{profile.user_id}' leaked into resume"

        # Evidence IDs must not appear
        for ev in evidence:
            assert ev.evidence_id not in result, f"Evidence ID '{ev.evidence_id}' leaked"

        # Mission IDs must not appear
        for m in missions:
            assert m.mission_id not in result, f"Mission ID '{m.mission_id}' leaked"

        # Campaign ID must not appear
        assert campaign.campaign_id not in result, f"Campaign ID leaked"

        # No phone number patterns (formatted phone numbers with separators)
        phone_pattern = re.compile(r"\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b")
        assert not phone_pattern.search(result), "Phone number pattern found in resume"


# ===========================================================================
# Property 4: Professional summary sentence count
# Feature: agent-friendly-resume, Property 4: Professional summary sentence count
# Validates: Requirements 2.1
# ===========================================================================

class TestProperty4ProfessionalSummarySentenceCount:
    """Property 4: Professional Summary contains 2-3 sentences."""

    @given(data=resume_data_st())
    @settings(max_examples=100)
    def test_professional_summary_has_2_to_3_sentences(self, data: ResumeData) -> None:
        """Professional Summary section must contain 2-3 sentences."""
        resume = _build_valid_resume(data)

        service = ResumeService(
            db_client=MagicMock(),
            s3_client=MagicMock(),
            bedrock_client=MagicMock(),
        )
        service.bedrock.invoke_model.return_value = _mock_bedrock_response(resume)
        result = service._synthesize(data)

        # Extract Professional Summary section
        parts = result.split("---", 2)
        body = parts[2]

        summary_start = body.find("## Professional Summary")
        assert summary_start != -1

        # Find the next section header
        next_section = body.find("## Skills and Demonstrated Capabilities")
        assert next_section != -1

        summary_text = body[summary_start + len("## Professional Summary"):next_section].strip()

        # Count sentences (split on period followed by space or end of string)
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', summary_text) if s.strip()]
        # Filter out empty strings and very short fragments
        sentences = [s for s in sentences if len(s) > 10]

        assert 2 <= len(sentences) <= 3, (
            f"Expected 2-3 sentences, got {len(sentences)}: {sentences}"
        )


# ===========================================================================
# Property 5: Mission highlights count invariant
# Feature: agent-friendly-resume, Property 5: Mission highlights count invariant
# Validates: Requirements 2.3
# ===========================================================================

class TestProperty5MissionHighlightsCount:
    """Property 5: 5-8 highlights for 8+ missions, all for fewer."""

    @given(data=resume_data_st(min_missions=8, max_missions=20, min_evidence=3, max_evidence=15))
    @settings(max_examples=100)
    def test_8_plus_missions_yields_5_to_8_highlights(self, data: ResumeData) -> None:
        """With 8+ completed missions, highlights section has 5-8 entries."""
        resume = _build_valid_resume(data)

        service = ResumeService(
            db_client=MagicMock(),
            s3_client=MagicMock(),
            bedrock_client=MagicMock(),
        )
        service.bedrock.invoke_model.return_value = _mock_bedrock_response(resume)
        result = service._synthesize(data)

        # Extract Mission History Highlights section
        parts = result.split("---", 2)
        body = parts[2]

        highlights_start = body.find("## Mission History Highlights")
        market_start = body.find("## Market Alignment")
        highlights_text = body[highlights_start + len("## Mission History Highlights"):market_start].strip()

        # Count bullet points (each highlight is a "- **" line)
        highlights = [line for line in highlights_text.split("\n") if line.strip().startswith("- ")]
        assert 5 <= len(highlights) <= 8, (
            f"Expected 5-8 highlights for {len(data.completed_missions)} missions, got {len(highlights)}"
        )

    @given(data=resume_data_st(min_missions=1, max_missions=7, min_evidence=1, max_evidence=10))
    @settings(max_examples=100)
    def test_fewer_than_8_missions_shows_all(self, data: ResumeData) -> None:
        """With fewer than 8 missions, all missions appear as highlights."""
        assume(len(data.completed_missions) < 8)
        resume = _build_valid_resume(data)

        service = ResumeService(
            db_client=MagicMock(),
            s3_client=MagicMock(),
            bedrock_client=MagicMock(),
        )
        service.bedrock.invoke_model.return_value = _mock_bedrock_response(resume)
        result = service._synthesize(data)

        parts = result.split("---", 2)
        body = parts[2]

        highlights_start = body.find("## Mission History Highlights")
        market_start = body.find("## Market Alignment")
        highlights_text = body[highlights_start + len("## Mission History Highlights"):market_start].strip()

        highlights = [line for line in highlights_text.split("\n") if line.strip().startswith("- ")]
        assert len(highlights) == len(data.completed_missions), (
            f"Expected {len(data.completed_missions)} highlights, got {len(highlights)}"
        )


# ===========================================================================
# Property 6: Top accomplishments count invariant
# Feature: agent-friendly-resume, Property 6: Top accomplishments count invariant
# Validates: Requirements 2.4
# ===========================================================================

class TestProperty6TopAccomplishmentsCount:
    """Property 6: 3-5 accomplishments in frontmatter."""

    @given(data=resume_data_st(min_evidence=3, max_evidence=20))
    @settings(max_examples=100)
    def test_top_accomplishments_count_3_to_5(self, data: ResumeData) -> None:
        """Frontmatter top_accomplishments has 3-5 items when sufficient evidence exists."""
        resume = _build_valid_resume(data)

        service = ResumeService(
            db_client=MagicMock(),
            s3_client=MagicMock(),
            bedrock_client=MagicMock(),
        )
        service.bedrock.invoke_model.return_value = _mock_bedrock_response(resume)
        result = service._synthesize(data)

        parts = result.split("---", 2)
        parsed = yaml.safe_load(parts[1])

        accomplishments = parsed["top_accomplishments"]
        assert 3 <= len(accomplishments) <= 5, (
            f"Expected 3-5 accomplishments, got {len(accomplishments)}"
        )


# ===========================================================================
# Property 7: Proficiency indicator derived from evidence depth
# Feature: agent-friendly-resume, Property 7: Proficiency indicator determinism
# Validates: Requirements 2.5
# ===========================================================================

class TestProperty7ProficiencyDeterminism:
    """Property 7: Same evidence count always produces same proficiency."""

    @given(count=st.integers(min_value=0, max_value=100))
    @settings(max_examples=100)
    def test_proficiency_is_deterministic(self, count: int) -> None:
        """Same evidence count always maps to the same proficiency indicator."""
        result_1 = _evidence_count_to_proficiency(count)
        result_2 = _evidence_count_to_proficiency(count)
        assert result_1 == result_2, "Proficiency must be deterministic"

    @given(count=st.integers(min_value=0, max_value=100))
    @settings(max_examples=100)
    def test_proficiency_is_valid_value(self, count: int) -> None:
        """Proficiency indicator is always one of the four valid values."""
        result = _evidence_count_to_proficiency(count)
        assert result in {"beginner", "intermediate", "advanced", "expert"}, (
            f"Invalid proficiency: {result}"
        )

    @given(count=st.integers(min_value=0, max_value=2))
    @settings(max_examples=100)
    def test_low_evidence_is_beginner(self, count: int) -> None:
        """0-2 evidence items map to beginner."""
        assert _evidence_count_to_proficiency(count) == "beginner"

    @given(count=st.integers(min_value=3, max_value=5))
    @settings(max_examples=100)
    def test_mid_evidence_is_intermediate(self, count: int) -> None:
        """3-5 evidence items map to intermediate."""
        assert _evidence_count_to_proficiency(count) == "intermediate"

    @given(count=st.integers(min_value=6, max_value=9))
    @settings(max_examples=100)
    def test_high_evidence_is_advanced(self, count: int) -> None:
        """6-9 evidence items map to advanced."""
        assert _evidence_count_to_proficiency(count) == "advanced"

    @given(count=st.integers(min_value=10, max_value=100))
    @settings(max_examples=100)
    def test_expert_evidence_is_expert(self, count: int) -> None:
        """10+ evidence items map to expert."""
        assert _evidence_count_to_proficiency(count) == "expert"


# ===========================================================================
# Property 8: Table failure produces specific error
# Feature: agent-friendly-resume, Property 8: Table failure produces specific error
# Validates: Requirements 3.4
# ===========================================================================

TABLE_NAMES_TO_LOGICAL = {
    "UserProfiles": "user_profiles",
    "Campaigns": "campaigns",
    "MissionHistory": "mission_history",
    "EvidenceVault": "evidence_vault",
    "MarketData": "market_data",
}


class TestProperty8TableFailureError:
    """Property 8: Table failure names the specific table, no partial resume."""

    @pytest.mark.parametrize("failed_table", [
        "UserProfiles", "Campaigns", "MissionHistory", "EvidenceVault",
    ])
    def test_table_failure_names_specific_table(self, failed_table: str) -> None:
        """When a DynamoDB table query fails, error names that table."""
        mock_db = MagicMock()

        # Set up the mock to raise on the specific table's method
        def mock_get_item(table_name: str, key: dict):
            if table_name == TABLE_NAMES_TO_LOGICAL.get(failed_table):
                raise Exception(f"Simulated {failed_table} failure")
            return {
                "userId": "user123",
                "email": "test@example.com",
                "name": "Test User",
                "persona": "veteran",
                "onboardingCompleted": True,
                "createdAt": "2025-01-01T00:00:00Z",
                "targetRole": "Engineer",
                "skills": ["Python"],
            }

        def mock_query(table_name: str, key_condition, **kwargs):
            if table_name == TABLE_NAMES_TO_LOGICAL.get(failed_table):
                raise Exception(f"Simulated {failed_table} failure")
            if table_name == "campaigns":
                return [{
                    "userId": "user123", "campaignId": "c1", "title": "Test",
                    "phase": "foundation", "status": "active",
                    "startDate": "2025-01-15", "targetRole": "Engineer",
                    "skillsFocus": ["Python"],
                }]
            if table_name == "mission_history":
                return [{
                    "userId": "user123", "missionId": "m1", "campaignId": "c1",
                    "title": "Mission 1", "description": "Do something",
                    "status": "completed", "completedDate": "2025-02-01",
                }]
            if table_name == "evidence_vault":
                return [{
                    "userId": "user123", "evidenceId": "e1", "missionId": "m1",
                    "skillTag": "Python", "reflection": "Learned a lot about Python",
                    "createdAt": "2025-02-01T10:00:00Z",
                }]
            if table_name == "market_data":
                return [{
                    "sector": "role:Engineer", "timestamp": "2025-01-01",
                    "alignmentPct": 75, "topSkills": ["Python"], "skillGaps": [],
                }]
            return []

        mock_db.get_item = MagicMock(side_effect=mock_get_item)
        mock_db.query = MagicMock(side_effect=mock_query)

        service = ResumeService(
            db_client=mock_db,
            s3_client=MagicMock(),
            bedrock_client=MagicMock(),
        )

        with pytest.raises(ResumeGenerationError) as exc_info:
            service._gather_data("user123")

        assert failed_table in str(exc_info.value), (
            f"Error should name '{failed_table}', got: {exc_info.value}"
        )

    def test_market_data_failure_names_table(self) -> None:
        """When MarketData query fails, error names MarketData."""
        mock_db = MagicMock()

        mock_db.get_item.return_value = {
            "userId": "user123", "email": "test@example.com",
            "name": "Test User", "persona": "veteran",
            "onboardingCompleted": True, "createdAt": "2025-01-01T00:00:00Z",
            "targetRole": "Engineer", "skills": ["Python"],
        }

        def mock_query(table_name: str, key_condition, **kwargs):
            if table_name == "market_data":
                raise Exception("Simulated MarketData failure")
            if table_name == "campaigns":
                return [{
                    "userId": "user123", "campaignId": "c1", "title": "Test",
                    "phase": "foundation", "status": "active",
                    "startDate": "2025-01-15", "targetRole": "Engineer",
                    "skillsFocus": ["Python"],
                }]
            if table_name == "mission_history":
                return [{
                    "userId": "user123", "missionId": "m1", "campaignId": "c1",
                    "title": "Mission 1", "description": "Do something",
                    "status": "completed", "completedDate": "2025-02-01",
                }]
            if table_name == "evidence_vault":
                return [{
                    "userId": "user123", "evidenceId": "e1", "missionId": "m1",
                    "skillTag": "Python", "reflection": "Learned a lot about Python",
                    "createdAt": "2025-02-01T10:00:00Z",
                }]
            return []

        mock_db.query = MagicMock(side_effect=mock_query)

        service = ResumeService(
            db_client=mock_db,
            s3_client=MagicMock(),
            bedrock_client=MagicMock(),
        )

        with pytest.raises(ResumeGenerationError) as exc_info:
            service._gather_data("user123")

        assert "MarketData" in str(exc_info.value), (
            f"Error should name 'MarketData', got: {exc_info.value}"
        )


# ===========================================================================
# Property 9: Storage produces both files with metadata update
# Feature: agent-friendly-resume, Property 9: Storage completeness
# Validates: Requirements 4.1, 4.2, 4.3
# ===========================================================================

class TestProperty9StorageCompleteness:
    """Property 9: Storage produces timestamped copy, latest.md, and metadata update."""

    @given(
        user_id=st.text(min_size=5, max_size=20, alphabet=st.characters(whitelist_categories=("L", "N"))),
        content=st.text(min_size=50, max_size=500, alphabet=st.characters(whitelist_categories=("L", "N", "Zs"))),
    )
    @settings(max_examples=100)
    def test_store_creates_both_s3_objects_and_updates_metadata(
        self, user_id: str, content: str,
    ) -> None:
        """_store writes timestamped copy, overwrites latest.md, updates UserProfiles."""
        mock_s3 = MagicMock()
        mock_db = MagicMock()
        mock_db.get_item.return_value = {"resumeVersion": 3}

        service = ResumeService(
            db_client=mock_db,
            s3_client=mock_s3,
            bedrock_client=MagicMock(),
        )
        service.bucket_name = "test-bucket"

        generated_at = "2025-01-15T14:30:00Z"
        result = service._store(user_id, content, generated_at)

        # Verify two S3 put_object calls
        put_calls = mock_s3.put_object.call_args_list
        assert len(put_calls) == 2, f"Expected 2 S3 puts, got {len(put_calls)}"

        # First call: timestamped copy
        first_call = put_calls[0]
        assert first_call.kwargs["Key"] == f"{user_id}/resume/resume-{generated_at}.md"
        assert first_call.kwargs["Bucket"] == "test-bucket"

        # Second call: latest.md
        second_call = put_calls[1]
        assert second_call.kwargs["Key"] == f"{user_id}/resume/latest.md"
        assert second_call.kwargs["Bucket"] == "test-bucket"

        # Both have same content
        assert first_call.kwargs["Body"] == content.encode("utf-8")
        assert second_call.kwargs["Body"] == content.encode("utf-8")

        # Verify UserProfiles metadata update
        mock_db.update_item.assert_called_once()
        update_call = mock_db.update_item.call_args
        assert update_call.args[0] == "user_profiles"
        assert update_call.args[1] == {"userId": user_id}

        updates = update_call.args[2]
        assert updates["lastResumeGeneratedAt"] == generated_at
        assert updates["resumeS3Key"] == f"{user_id}/resume/latest.md"
        assert updates["resumeVersion"] == 4  # incremented from 3

        # Verify return value
        assert result["latest_key"] == f"{user_id}/resume/latest.md"
        assert result["version"] == 4


# ===========================================================================
# Property 11: Rate limit enforced at 3 per day
# Feature: agent-friendly-resume, Property 11: Rate limit enforcement
# Validates: Requirements 8.4, 8.5
# ===========================================================================

class TestProperty11RateLimitEnforcement:
    """Property 11: 4th generation request on same day returns 429.

    Uses moto-backed DynamoDB since _enforce_rate_limit uses conditional
    updates directly on the table.
    """

    def test_fourth_request_raises_rate_limit_error(self, dynamodb_tables) -> None:
        """After 3 generations today, the 4th raises RateLimitError (429)."""
        user_id = "ratelimit_user_001"
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Seed user profile at the limit
        dynamodb_tables["user_profiles"].put_item(Item={
            "userId": user_id,
            "dailyResumeGenDate": today,
            "dailyResumeGenCount": MAX_DAILY_GENERATIONS,
        })

        db = DynamoDBClient()
        service = ResumeService(
            db_client=db,
            s3_client=MagicMock(),
            bedrock_client=MagicMock(),
        )

        with pytest.raises(RateLimitError) as exc_info:
            service._enforce_rate_limit(user_id)

        assert exc_info.value.status_code == 429

    def test_under_limit_does_not_raise(self, dynamodb_tables) -> None:
        """Requests under the daily limit proceed without error."""
        user_id = "ratelimit_user_002"
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Seed user with count under limit
        dynamodb_tables["user_profiles"].put_item(Item={
            "userId": user_id,
            "dailyResumeGenDate": today,
            "dailyResumeGenCount": 1,
        })

        db = DynamoDBClient()
        service = ResumeService(
            db_client=db,
            s3_client=MagicMock(),
            bedrock_client=MagicMock(),
        )

        # Should not raise
        service._enforce_rate_limit(user_id)

    def test_new_day_resets_count(self, dynamodb_tables) -> None:
        """Count from a previous day does not block today's requests."""
        user_id = "ratelimit_user_003"

        # Seed user with count from yesterday
        dynamodb_tables["user_profiles"].put_item(Item={
            "userId": user_id,
            "dailyResumeGenDate": "2020-01-01",
            "dailyResumeGenCount": 99,
        })

        db = DynamoDBClient()
        service = ResumeService(
            db_client=db,
            s3_client=MagicMock(),
            bedrock_client=MagicMock(),
        )

        # Should not raise -- old date means count resets
        service._enforce_rate_limit(user_id)

    def test_atomic_increment_prevents_over_limit(self, dynamodb_tables) -> None:
        """Three sequential calls succeed, fourth raises RateLimitError."""
        user_id = "ratelimit_user_004"

        # Seed fresh user profile
        dynamodb_tables["user_profiles"].put_item(Item={
            "userId": user_id,
        })

        db = DynamoDBClient()
        service = ResumeService(
            db_client=db,
            s3_client=MagicMock(),
            bedrock_client=MagicMock(),
        )

        # First 3 calls should succeed
        for _ in range(MAX_DAILY_GENERATIONS):
            service._enforce_rate_limit(user_id)

        # 4th call should fail
        with pytest.raises(RateLimitError):
            service._enforce_rate_limit(user_id)


# ===========================================================================
# Property 10: Phase advancement updates campaign phase
# Feature: agent-friendly-resume, Property 10: Phase advancement updates campaign phase
# Validates: Requirements 6.2
# ===========================================================================

class TestProperty10PhaseAdvancementPhase:
    """Property 10: Phase advancement updates campaign phase in frontmatter."""

    @given(
        data=resume_data_st(),
        new_phase=st.sampled_from(["expansion", "launch"]),
    )
    @settings(max_examples=100, deadline=None)
    def test_frontmatter_campaign_phase_matches_post_transition_phase(
        self, data: ResumeData, new_phase: str,
    ) -> None:
        """When phase advancement triggers resume generation, the frontmatter
        campaign_phase matches the user's new (post-transition) phase.

        **Validates: Requirements 6.2**
        """
        # Override campaign phase to the post-transition phase
        data.campaign.phase = new_phase

        # Build a valid resume reflecting the updated phase
        resume = _build_valid_resume(data)

        service = ResumeService(
            db_client=MagicMock(),
            s3_client=MagicMock(),
            bedrock_client=MagicMock(),
        )
        service.bedrock.invoke_model.return_value = _mock_bedrock_response(resume)

        result = service._synthesize(data)

        # Parse YAML frontmatter
        parts = result.split("---", 2)
        assert len(parts) >= 3, "Resume must have opening and closing --- delimiters"
        parsed = yaml.safe_load(parts[1])

        assert parsed["campaign_phase"] == new_phase, (
            f"Expected campaign_phase '{new_phase}', got '{parsed['campaign_phase']}'"
        )


