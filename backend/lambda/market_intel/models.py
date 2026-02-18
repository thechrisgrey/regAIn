"""Data models for the Market Intelligence System.

Defines dataclasses for market data records, canonical skills,
alignment results, and market insights. MarketDataRecord includes
DynamoDB serialization helpers matching the MarketData table schema
(PK: sector, SK: timestamp).
"""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class CanonicalSkill:
    """A single skill in the REGAIN taxonomy.

    Attributes:
        name: Canonical skill name, e.g. "Quality Assurance".
        category: One of "technical", "analytical", "communication",
            "leadership", "domain_specific".
        onet_codes: O*NET skill/knowledge codes mapped to this skill.
        job_posting_aliases: Common variants found in job postings.
        user_aliases: Natural-language descriptions users might provide.
    """

    name: str
    category: str
    onet_codes: list[str] = field(default_factory=list)
    job_posting_aliases: list[str] = field(default_factory=list)
    user_aliases: list[str] = field(default_factory=list)


@dataclass
class MarketDataRecord:
    """A single market data record stored in the MarketData DynamoDB table.

    PK is ``sector`` (e.g. "role:ai_qa_engineer"), SK is ``timestamp``
    (ISO date string).

    Attributes:
        sector: Partition key — role identifier prefixed with "role:".
        timestamp: Sort key — ISO date string, e.g. "2025-01-15".
        role_title: Human-readable role name.
        category: Role category such as "technology" or "management".
        demand_score: Composite score 0–100.
        growth_rate: Year-over-year growth percentage.
        trend_direction: One of "surging", "growing", "stable", "declining".
        top_skills: Ranked skill requirements with frequency data.
        salary_range: Dict with min, median, max, and region.
        posting_volume: Raw job posting count.
        projection: BLS projection category string.
        source: Data origin — "onet", "bls", "usajobs", "synthetic",
            or "composite".
        insights: Embedded insight objects for this role.
    """

    sector: str
    timestamp: str
    role_title: str
    category: str
    demand_score: int
    growth_rate: float
    trend_direction: str
    top_skills: list[dict] = field(default_factory=list)
    salary_range: dict = field(default_factory=dict)
    posting_volume: int = 0
    projection: str = ""
    source: str = ""
    insights: list[dict] = field(default_factory=list)

    def to_dynamodb_item(self) -> dict[str, Any]:
        """Convert to DynamoDB item format.

        Returns:
            Dict ready for DynamoDB put_item. Keys use camelCase to
            match the existing table convention.
        """
        return {
            "sector": self.sector,
            "timestamp": self.timestamp,
            "roleTitle": self.role_title,
            "category": self.category,
            "demandScore": self.demand_score,
            "growthRate": str(self.growth_rate),
            "trendDirection": self.trend_direction,
            "topSkills": self.top_skills,
            "salaryRange": self.salary_range,
            "postingVolume": self.posting_volume,
            "projection": self.projection,
            "source": self.source,
            "insights": self.insights,
        }

    @classmethod
    def from_dynamodb_item(cls, item: dict[str, Any]) -> "MarketDataRecord":
        """Create a MarketDataRecord from a DynamoDB item dict.

        Args:
            item: Raw DynamoDB item with camelCase keys.

        Returns:
            Populated MarketDataRecord instance.
        """
        return cls(
            sector=item["sector"],
            timestamp=item["timestamp"],
            role_title=item.get("roleTitle", ""),
            category=item.get("category", ""),
            demand_score=int(item.get("demandScore", 0)),
            growth_rate=float(item.get("growthRate", 0.0)),
            trend_direction=item.get("trendDirection", "stable"),
            top_skills=item.get("topSkills", []),
            salary_range=item.get("salaryRange", {}),
            posting_volume=int(item.get("postingVolume", 0)),
            projection=item.get("projection", ""),
            source=item.get("source", ""),
            insights=item.get("insights", []),
        )


@dataclass
class AlignmentResult:
    """Result of a user-to-market alignment calculation.

    Attributes:
        alignment_pct: Weighted alignment percentage 0.0–100.0.
        skill_breakdown: Per-skill detail with user_score, market_weight,
            and gap value.
        top_gaps: Top 3 skills sorted by market_weight × (1 − user_score).
        top_strengths: Top 3 skills sorted by market_weight × user_score.
        target_role_id: The role being compared against.
        user_id: The user whose skills are evaluated.
        calculated_at: ISO timestamp of the calculation.
    """

    alignment_pct: float
    skill_breakdown: list[dict] = field(default_factory=list)
    top_gaps: list[dict] = field(default_factory=list)
    top_strengths: list[dict] = field(default_factory=list)
    target_role_id: str = ""
    user_id: str = ""
    calculated_at: str = ""


@dataclass
class MarketInsight:
    """A structured insight object consumed by the Coaching Agent.

    Attributes:
        type: Insight category — one of "role_trend", "alignment",
            "gap_opportunity", "emerging_role", "milestone".
        role_id: Associated role identifier.
        message_template: Template string with {placeholders}.
        data_payload: Data dict whose keys fill template placeholders.
        generated_date: ISO timestamp when the insight was created.
        shown: Whether the insight has been presented to the user.
        user_id: Set for user-scoped insights; None for role-level ones.
    """

    type: str
    role_id: str
    message_template: str
    data_payload: dict = field(default_factory=dict)
    generated_date: str = ""
    shown: bool = False
    user_id: Optional[str] = None
