"""Data models for the Mission Engine.

Defines all engine-specific dataclasses used across the generation pipeline,
scoring, difficulty tracking, phase gates, and lifecycle management.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MissionCandidate:
    """A scored candidate mission produced by the generation pipeline."""

    template_id: str
    category: str  # "reflection", "skill_building", "portfolio", "networking", "market_research"
    title: str
    description: str
    rationale: str
    skill_tags: list[str]
    difficulty: int  # 1-5
    estimated_minutes: int  # 15-45
    expected_evidence_type: str  # "reflection", "artifact", "connection", "research"
    phase: str  # "foundation", "expansion", "launch"
    market_relevance_score: float = 0.0  # 0.0-1.0
    priority_score: float = 0.0  # 0.0-1.0, computed by scorer


@dataclass
class SkillGapReport:
    """Result of skill gap analysis."""

    skill_scores: dict[str, float]  # skill_name → 0.0-1.0
    market_alignment_pct: float  # 0.0-100.0
    priority_skills: list[str]  # Skills sorted by gap × demand, descending
    evidence_density: dict[str, int]  # skill_name → evidence count


@dataclass
class GateCondition:
    """Status of a single gate condition."""

    required: float | int
    current: float | int
    met: bool


@dataclass
class GateResult:
    """Result of a phase gate evaluation."""

    passed: bool
    current_phase: str
    next_phase: str | None  # None if not passed or at final phase
    conditions: dict[str, GateCondition] = field(default_factory=dict)


CATEGORIES = [
    "reflection",
    "skill_building",
    "portfolio",
    "networking",
    "market_research",
]


@dataclass
class DifficultyState:
    """Per-category difficulty tracking for a user.

    Serializable to/from a DynamoDB-compatible dict via to_dict()/from_dict().
    """

    levels: dict[str, int] = field(default_factory=lambda: {c: 1 for c in CATEGORIES})
    consecutive_completions: dict[str, int] = field(
        default_factory=lambda: {c: 0 for c in CATEGORIES}
    )
    consecutive_skips: dict[str, int] = field(
        default_factory=lambda: {c: 0 for c in CATEGORIES}
    )
    last_advancement_dates: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a DynamoDB-compatible dict."""
        return {
            "levels": dict(self.levels),
            "consecutive_completions": dict(self.consecutive_completions),
            "consecutive_skips": dict(self.consecutive_skips),
            "last_advancement_dates": dict(self.last_advancement_dates),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DifficultyState:
        """Deserialize from a DynamoDB-compatible dict.

        Args:
            data: Dict with keys levels, consecutive_completions,
                  consecutive_skips, and last_advancement_dates.

        Returns:
            A new DifficultyState instance.
        """
        return cls(
            levels=dict(data.get("levels", {})),
            consecutive_completions=dict(data.get("consecutive_completions", {})),
            consecutive_skips=dict(data.get("consecutive_skips", {})),
            last_advancement_dates=dict(data.get("last_advancement_dates", {})),
        )


@dataclass
class CompletionResult:
    """Result returned after completing a mission."""

    mission_id: str
    difficulty_change: dict[str, int] | None  # category → new level, if changed
    gate_result: GateResult
    behavioral_update: dict[str, Any] = field(default_factory=dict)


@dataclass
class GenerationResult:
    """Result of the mission generation pipeline."""

    primary: MissionCandidate
    alternates: list[MissionCandidate]  # Exactly 2
    skill_gap_report: SkillGapReport
