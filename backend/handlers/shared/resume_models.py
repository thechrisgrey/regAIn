"""Data models for resume generation.

Defines the data structures used by the resume generation service
for gathering input data, representing frontmatter fields, and
returning generation results.
"""

from dataclasses import dataclass
from typing import Any, List

from backend.handlers.shared.models import Campaign, Evidence, Mission, UserProfile


@dataclass
class ResumeSkill:
    """A skill entry in the resume frontmatter.

    Represents a demonstrated skill with evidence-backed metrics
    for AI recruiting agents to parse programmatically.
    """

    skill_name: str
    evidence_count: int
    strongest_evidence_summary: str
    proficiency_indicator: str  # 'beginner', 'intermediate', 'advanced', 'expert'


@dataclass
class ResumeFrontmatter:
    """Structured YAML frontmatter for the resume document.

    Contains all machine-readable fields that AI recruiting agents
    use to score candidates programmatically.
    """

    schema_version: str
    generated_at: str  # ISO 8601 timestamp
    regain_version: str
    name: str
    target_role: str
    transition_type: str  # 'veteran', 'ai_displaced', 'career_pivoter'
    skills: List[ResumeSkill]
    campaign_phase: str
    campaign_progress_pct: float
    market_alignment_score: float
    missions_completed: int
    evidence_items: int
    top_accomplishments: List[str]


@dataclass
class ResumeData:
    """Input data gathered from all tables before LLM synthesis.

    Aggregates the user's profile, campaign, missions, evidence,
    and market alignment data for the resume generation prompt.
    """

    profile: UserProfile
    campaign: Campaign
    completed_missions: List[Mission]
    evidence_entries: List[Evidence]
    market_alignment: dict[str, Any]  # From get_alignment calculation


@dataclass
class ResumeResult:
    """Output of a successful resume generation.

    Returned to callers (API, coaching tools, async triggers)
    after the resume has been synthesized and stored.
    """

    content: str  # Full markdown with YAML frontmatter
    s3_key: str  # S3 object key for latest.md
    version: int  # Incrementing version number
    generated_at: str  # ISO 8601 timestamp
    presigned_url: str  # 1-hour expiry download URL
