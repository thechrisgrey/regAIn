"""Data models for REGAIN platform entities.

Each model maps to a DynamoDB table and provides serialization
helpers for converting between Python objects and DynamoDB items.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


@dataclass
class UserProfile:
    """A user's profile in the REGAIN platform."""

    user_id: str
    email: str
    name: str
    persona: str  # 'veteran', 'ai_displaced', 'career_pivoter'
    onboarding_completed: bool
    created_at: str
    target_role: Optional[str] = None
    skills: List[str] = field(default_factory=list)

    def to_dynamodb_item(self) -> Dict[str, Any]:
        """Convert to DynamoDB item format."""
        return {
            "userId": self.user_id,
            "email": self.email,
            "name": self.name,
            "persona": self.persona,
            "onboardingCompleted": self.onboarding_completed,
            "createdAt": self.created_at,
            "targetRole": self.target_role,
            "skills": self.skills,
        }

    @classmethod
    def from_dynamodb_item(cls, item: Dict[str, Any]) -> "UserProfile":
        """Create from DynamoDB item."""
        return cls(
            user_id=item["userId"],
            email=item["email"],
            name=item["name"],
            persona=item["persona"],
            onboarding_completed=item["onboardingCompleted"],
            created_at=item["createdAt"],
            target_role=item.get("targetRole"),
            skills=item.get("skills", []),
        )


@dataclass
class Campaign:
    """A structured reskilling campaign."""

    user_id: str
    campaign_id: str
    title: str
    phase: str  # 'foundation', 'momentum', 'acceleration', 'transition'
    status: str  # 'active', 'paused', 'completed'
    start_date: str
    target_role: str
    skills_focus: List[str] = field(default_factory=list)

    def to_dynamodb_item(self) -> Dict[str, Any]:
        """Convert to DynamoDB item format."""
        return {
            "userId": self.user_id,
            "campaignId": self.campaign_id,
            "title": self.title,
            "phase": self.phase,
            "status": self.status,
            "startDate": self.start_date,
            "targetRole": self.target_role,
            "skillsFocus": self.skills_focus,
        }

    @classmethod
    def from_dynamodb_item(cls, item: Dict[str, Any]) -> "Campaign":
        """Create from DynamoDB item."""
        return cls(
            user_id=item["userId"],
            campaign_id=item["campaignId"],
            title=item["title"],
            phase=item["phase"],
            status=item["status"],
            start_date=item["startDate"],
            target_role=item["targetRole"],
            skills_focus=item.get("skillsFocus", []),
        )


@dataclass
class Mission:
    """A skill-building mission within a campaign."""

    user_id: str
    mission_id: str
    campaign_id: str
    title: str
    description: str
    status: str  # 'pending', 'in_progress', 'completed', 'skipped'
    completed_date: Optional[str] = None
    evidence_id: Optional[str] = None

    def to_dynamodb_item(self) -> Dict[str, Any]:
        """Convert to DynamoDB item format."""
        item: Dict[str, Any] = {
            "userId": self.user_id,
            "missionId": self.mission_id,
            "campaignId": self.campaign_id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
        }
        if self.completed_date is not None:
            item["completedDate"] = self.completed_date
        if self.evidence_id is not None:
            item["evidenceId"] = self.evidence_id
        return item

    @classmethod
    def from_dynamodb_item(cls, item: Dict[str, Any]) -> "Mission":
        """Create from DynamoDB item."""
        return cls(
            user_id=item["userId"],
            mission_id=item["missionId"],
            campaign_id=item["campaignId"],
            title=item["title"],
            description=item["description"],
            status=item["status"],
            completed_date=item.get("completedDate"),
            evidence_id=item.get("evidenceId"),
        )


@dataclass
class Evidence:
    """A piece of evidence from a completed mission."""

    user_id: str
    evidence_id: str
    mission_id: str
    skill_tag: str
    reflection: str
    created_at: str
    artifact_url: Optional[str] = None

    def to_dynamodb_item(self) -> Dict[str, Any]:
        """Convert to DynamoDB item format."""
        item: Dict[str, Any] = {
            "userId": self.user_id,
            "evidenceId": self.evidence_id,
            "missionId": self.mission_id,
            "skillTag": self.skill_tag,
            "reflection": self.reflection,
            "createdAt": self.created_at,
        }
        if self.artifact_url is not None:
            item["artifactUrl"] = self.artifact_url
        return item

    @classmethod
    def from_dynamodb_item(cls, item: Dict[str, Any]) -> "Evidence":
        """Create from DynamoDB item."""
        return cls(
            user_id=item["userId"],
            evidence_id=item["evidenceId"],
            mission_id=item["missionId"],
            skill_tag=item["skillTag"],
            reflection=item["reflection"],
            created_at=item["createdAt"],
            artifact_url=item.get("artifactUrl"),
        )
