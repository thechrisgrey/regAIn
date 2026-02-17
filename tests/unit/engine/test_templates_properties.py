"""Property-based tests for backend.engine.templates module.

Uses Hypothesis to validate that template instantiation always produces
valid MissionCandidate instances regardless of input data.
"""

from __future__ import annotations

import re
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from backend.engine.models import SkillGapReport
from backend.engine.templates import (
    get_all_templates,
    instantiate_template,
    instantiate_all_templates,
)

# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Realistic skill names: short lowercase identifiers.
skill_name_st = st.from_regex(r"[a-z][a-z_]{1,14}", fullmatch=True)

# Non-empty text for roles and sectors.
role_st = st.from_regex(r"[A-Za-z][A-Za-z ]{2,24}", fullmatch=True)
sector_st = st.from_regex(r"[A-Za-z][A-Za-z ]{2,18}", fullmatch=True)
person_name_st = st.from_regex(r"[A-Z][a-z]{1,10} [A-Z][a-z]{1,10}", fullmatch=True)
company_name_st = st.from_regex(r"[A-Z][a-z]{2,12}", fullmatch=True)


@st.composite
def profile_st(draw: st.DrawFn) -> dict[str, Any]:
    """Generate a valid user profile dict with non-empty skills, target role, and experience."""
    skills = draw(st.lists(skill_name_st, min_size=1, max_size=6, unique=True))
    target_role = draw(role_st)
    name = draw(person_name_st)
    company = draw(company_name_st)
    role = draw(role_st)
    experience = [{"company": company, "role": role}]
    return {
        "target_role": target_role,
        "skills": skills,
        "experience": experience,
        "name": name,
    }


@st.composite
def skill_gap_report_st(draw: st.DrawFn) -> SkillGapReport:
    """Generate a SkillGapReport with at least one priority skill."""
    skills = draw(st.lists(skill_name_st, min_size=1, max_size=6, unique=True))
    skill_scores = {s: draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False)) for s in skills}
    market_alignment = draw(st.floats(min_value=0.0, max_value=100.0, allow_nan=False))
    evidence_density = {s: draw(st.integers(min_value=0, max_value=20)) for s in skills}
    return SkillGapReport(
        skill_scores=skill_scores,
        market_alignment_pct=market_alignment,
        priority_skills=skills,
        evidence_density=evidence_density,
    )


@st.composite
def market_data_st(draw: st.DrawFn) -> dict[str, Any]:
    """Generate a market data dict with top_skills, sector, and trending_roles."""
    top_skills = draw(st.lists(skill_name_st, min_size=1, max_size=6, unique=True))
    sector = draw(sector_st)
    trending_roles = draw(st.lists(role_st, min_size=1, max_size=4, unique=True))
    return {
        "top_skills": top_skills,
        "sector": sector,
        "trending_roles": trending_roles,
    }


# Regex to detect raw {placeholder} tokens in text.
RAW_PLACEHOLDER_RE = re.compile(r"\{[a-z_]+\}")

ALL_TEMPLATES = get_all_templates()
PHASES = ["foundation", "expansion", "launch"]


# ---------------------------------------------------------------------------
# Property 1: Template instantiation produces valid candidates
# Feature: mission-engine, Property 1: Template instantiation produces valid candidates
# ---------------------------------------------------------------------------


class TestProperty1TemplateInstantiationProducesValidCandidates:
    """**Validates: Requirements 1.2, 1.3, 1.4**

    For ANY mission template and ANY valid user profile data (with non-empty
    skills, target role, and experience), instantiating the template shall
    produce a MissionCandidate where:
    - all required fields are non-empty (title, description, rationale,
      skill_tags, expected_evidence_type)
    - no raw placeholder strings remain in the title or description
    - difficulty is between 1 and 5
    - estimated_minutes is between 15 and 45
    """

    @given(
        template_idx=st.integers(min_value=0, max_value=len(ALL_TEMPLATES) - 1),
        profile=profile_st(),
        skill_gaps=skill_gap_report_st(),
        market_data=market_data_st(),
    )
    @settings(max_examples=200)
    def test_instantiated_candidate_has_nonempty_required_fields(
        self,
        template_idx: int,
        profile: dict[str, Any],
        skill_gaps: SkillGapReport,
        market_data: dict[str, Any],
    ) -> None:
        """Every required field on the candidate must be non-empty."""
        # Feature: mission-engine, Property 1: Template instantiation produces valid candidates
        # **Validates: Requirements 1.2, 1.3, 1.4**
        template = ALL_TEMPLATES[template_idx]
        candidate = instantiate_template(template, profile, skill_gaps, market_data)

        assert candidate.title, "title must be non-empty"
        assert candidate.description, "description must be non-empty"
        assert candidate.rationale, "rationale must be non-empty"
        assert len(candidate.skill_tags) > 0, "skill_tags must be non-empty"
        assert candidate.expected_evidence_type, "expected_evidence_type must be non-empty"

    @given(
        template_idx=st.integers(min_value=0, max_value=len(ALL_TEMPLATES) - 1),
        profile=profile_st(),
        skill_gaps=skill_gap_report_st(),
        market_data=market_data_st(),
    )
    @settings(max_examples=200)
    def test_no_raw_placeholders_in_title_or_description(
        self,
        template_idx: int,
        profile: dict[str, Any],
        skill_gaps: SkillGapReport,
        market_data: dict[str, Any],
    ) -> None:
        """No raw {placeholder} tokens should remain in title or description."""
        # Feature: mission-engine, Property 1: Template instantiation produces valid candidates
        # **Validates: Requirements 1.2, 1.3, 1.4**
        template = ALL_TEMPLATES[template_idx]
        candidate = instantiate_template(template, profile, skill_gaps, market_data)

        assert not RAW_PLACEHOLDER_RE.search(candidate.title), (
            f"Raw placeholder found in title: {candidate.title!r}"
        )
        assert not RAW_PLACEHOLDER_RE.search(candidate.description), (
            f"Raw placeholder found in description: {candidate.description!r}"
        )

    @given(
        template_idx=st.integers(min_value=0, max_value=len(ALL_TEMPLATES) - 1),
        profile=profile_st(),
        skill_gaps=skill_gap_report_st(),
        market_data=market_data_st(),
    )
    @settings(max_examples=200)
    def test_difficulty_between_1_and_5(
        self,
        template_idx: int,
        profile: dict[str, Any],
        skill_gaps: SkillGapReport,
        market_data: dict[str, Any],
    ) -> None:
        """Difficulty must be between 1 and 5 inclusive."""
        # Feature: mission-engine, Property 1: Template instantiation produces valid candidates
        # **Validates: Requirements 1.2, 1.3, 1.4**
        template = ALL_TEMPLATES[template_idx]
        candidate = instantiate_template(template, profile, skill_gaps, market_data)

        assert 1 <= candidate.difficulty <= 5, (
            f"difficulty {candidate.difficulty} out of bounds [1, 5]"
        )

    @given(
        template_idx=st.integers(min_value=0, max_value=len(ALL_TEMPLATES) - 1),
        profile=profile_st(),
        skill_gaps=skill_gap_report_st(),
        market_data=market_data_st(),
    )
    @settings(max_examples=200)
    def test_estimated_minutes_between_15_and_45(
        self,
        template_idx: int,
        profile: dict[str, Any],
        skill_gaps: SkillGapReport,
        market_data: dict[str, Any],
    ) -> None:
        """Estimated minutes must be between 15 and 45 inclusive."""
        # Feature: mission-engine, Property 1: Template instantiation produces valid candidates
        # **Validates: Requirements 1.2, 1.3, 1.4**
        template = ALL_TEMPLATES[template_idx]
        candidate = instantiate_template(template, profile, skill_gaps, market_data)

        assert 15 <= candidate.estimated_minutes <= 45, (
            f"estimated_minutes {candidate.estimated_minutes} out of bounds [15, 45]"
        )

    @given(
        phase=st.sampled_from(PHASES),
        profile=profile_st(),
        skill_gaps=skill_gap_report_st(),
        market_data=market_data_st(),
    )
    @settings(max_examples=200)
    def test_instantiate_all_templates_produces_valid_candidates(
        self,
        phase: str,
        profile: dict[str, Any],
        skill_gaps: SkillGapReport,
        market_data: dict[str, Any],
    ) -> None:
        """instantiate_all_templates produces candidates that all satisfy the property."""
        # Feature: mission-engine, Property 1: Template instantiation produces valid candidates
        # **Validates: Requirements 1.2, 1.3, 1.4**
        candidates = instantiate_all_templates(profile, skill_gaps, market_data, phase)

        assert len(candidates) > 0, f"No candidates generated for phase {phase!r}"

        for candidate in candidates:
            # Non-empty required fields
            assert candidate.title, "title must be non-empty"
            assert candidate.description, "description must be non-empty"
            assert candidate.rationale, "rationale must be non-empty"
            assert len(candidate.skill_tags) > 0, "skill_tags must be non-empty"
            assert candidate.expected_evidence_type, "expected_evidence_type must be non-empty"

            # No raw placeholders
            assert not RAW_PLACEHOLDER_RE.search(candidate.title), (
                f"Raw placeholder in title: {candidate.title!r}"
            )
            assert not RAW_PLACEHOLDER_RE.search(candidate.description), (
                f"Raw placeholder in description: {candidate.description!r}"
            )

            # Bounds
            assert 1 <= candidate.difficulty <= 5
            assert 15 <= candidate.estimated_minutes <= 45
