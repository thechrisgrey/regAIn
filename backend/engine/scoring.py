"""Priority scoring for the Mission Engine.

Ranks MissionCandidates using a weighted formula: gap priority 40%,
category balance 20%, difficulty appropriateness 15%, phase alignment 15%,
and streak momentum 10%. Each sub-score returns a value between 0.0 and 1.0.
"""

from __future__ import annotations

from typing import Any

from backend.engine.models import (
    CATEGORIES,
    DifficultyState,
    MissionCandidate,
    SkillGapReport,
)

WEIGHTS: dict[str, float] = {
    "gap_priority": 0.40,
    "category_balance": 0.20,
    "difficulty_appropriateness": 0.15,
    "phase_alignment": 0.15,
    "streak_momentum": 0.10,
}

# Phase → preferred mission categories.
PHASE_PREFERRED_CATEGORIES: dict[str, set[str]] = {
    "foundation": {"reflection", "skill_building"},
    "expansion": {"portfolio", "market_research"},
    "launch": {"networking"},
}


def score_gap_priority(candidate: MissionCandidate, skill_gaps: SkillGapReport) -> float:
    """Score based on how critical the targeted skill gap is.

    Higher scores for missions targeting wider gaps in skills with higher
    market demand. Gap = 1.0 - skill_score. The final score is the average
    of (gap * demand_weight) across the candidate's skill tags.

    Args:
        candidate: The mission candidate to score.
        skill_gaps: Current skill gap report with per-skill scores.

    Returns:
        Float between 0.0 and 1.0.
    """
    if not candidate.skill_tags:
        return 0.0

    total = 0.0
    count = 0
    for skill in candidate.skill_tags:
        skill_score = skill_gaps.skill_scores.get(skill, 0.0)
        gap = 1.0 - skill_score
        # Use market_relevance_score on the candidate as a proxy for demand
        # when individual skill demand isn't available. Priority skills get
        # a boost.
        demand = 1.0
        if skill in skill_gaps.priority_skills:
            # Higher rank in priority_skills → higher demand weight.
            rank = skill_gaps.priority_skills.index(skill)
            total_priority = len(skill_gaps.priority_skills)
            demand = 1.0 - (rank / max(total_priority, 1)) * 0.5  # 1.0 → 0.5
        total += gap * demand
        count += 1

    score = total / count
    return max(0.0, min(1.0, score))


def score_category_balance(
    candidate: MissionCandidate,
    mission_history: list[dict[str, Any]],
) -> float:
    """Score based on category representation balance.

    Penalizes categories the user has overindexed on. Categories with fewer
    completed missions get higher scores.

    Args:
        candidate: The mission candidate to score.
        mission_history: List of past mission dicts with 'category' and 'status'.

    Returns:
        Float between 0.0 and 1.0.
    """
    # Count completed missions per category.
    category_counts: dict[str, int] = {c: 0 for c in CATEGORIES}
    for mission in mission_history:
        cat = mission.get("category", "")
        if mission.get("status") == "completed" and cat in category_counts:
            category_counts[cat] += 1

    total_completed = sum(category_counts.values())
    if total_completed == 0:
        # No history — all categories equally balanced.
        return 1.0

    # Score inversely proportional to how overrepresented this category is.
    candidate_count = category_counts.get(candidate.category, 0)
    max_count = max(category_counts.values())

    if max_count == 0:
        return 1.0

    # Ratio of this category's count to the max count. 0 = underrepresented, 1 = most overindexed.
    overindex_ratio = candidate_count / max_count
    return max(0.0, min(1.0, 1.0 - overindex_ratio))


def score_difficulty_appropriateness(
    candidate: MissionCandidate,
    difficulty_state: DifficultyState,
) -> float:
    """Score based on match between mission and user difficulty level.

    Peak score (1.0) at exact match. Decreases linearly with distance.

    Args:
        candidate: The mission candidate to score.
        difficulty_state: Current per-category difficulty levels.

    Returns:
        Float between 0.0 and 1.0.
    """
    user_level = difficulty_state.levels.get(candidate.category, 1)
    distance = abs(candidate.difficulty - user_level)
    # Max possible distance is 4 (level 1 vs difficulty 5).
    score = max(0.0, 1.0 - distance / 4.0)
    return score


def score_phase_alignment(candidate: MissionCandidate, current_phase: str) -> float:
    """Score based on mission type fit for current campaign phase.

    Preferred categories for the phase get 1.0, others get 0.3.

    Args:
        candidate: The mission candidate to score.
        current_phase: Current campaign phase ("foundation", "expansion", "launch").

    Returns:
        Float between 0.0 and 1.0.
    """
    preferred = PHASE_PREFERRED_CATEGORIES.get(current_phase, set())
    if candidate.category in preferred:
        return 1.0
    return 0.3


def score_streak_momentum(
    candidate: MissionCandidate,
    streak_info: dict[str, Any],
) -> float:
    """Score based on streak state.

    On a completion streak: favor missions in categories similar to recent
    completions (momentum). On a broken streak: favor easier missions
    (recovery).

    Args:
        candidate: The mission candidate to score.
        streak_info: Dict with keys 'type' ("completion" or "broken"),
            'count' (int), and 'recent_categories' (list[str]).

    Returns:
        Float between 0.0 and 1.0.
    """
    streak_type = streak_info.get("type", "")
    recent_categories = streak_info.get("recent_categories", [])

    if streak_type == "completion":
        # Favor missions in recently completed categories to maintain momentum.
        if candidate.category in recent_categories:
            return 1.0
        return 0.4

    if streak_type == "broken":
        # Favor easier missions to rebuild confidence.
        # Lower difficulty → higher score.
        score = max(0.0, 1.0 - (candidate.difficulty - 1) / 4.0)
        return score

    # No streak info — neutral score.
    return 0.5


def score_candidate(
    candidate: MissionCandidate,
    skill_gaps: SkillGapReport,
    mission_history: list[dict[str, Any]],
    current_phase: str,
    streak_info: dict[str, Any],
    difficulty_state: DifficultyState,
) -> float:
    """Compute the priority score for a single candidate.

    Applies weighted sub-scores: gap 40%, balance 20%, difficulty 15%,
    phase 15%, streak 10%.

    Args:
        candidate: The mission candidate to score.
        skill_gaps: Current skill gap report.
        mission_history: List of past mission dicts.
        current_phase: Current campaign phase.
        streak_info: Streak state dict.
        difficulty_state: Current per-category difficulty levels.

    Returns:
        Float between 0.0 and 1.0.
    """
    gap = score_gap_priority(candidate, skill_gaps)
    balance = score_category_balance(candidate, mission_history)
    difficulty = score_difficulty_appropriateness(candidate, difficulty_state)
    phase = score_phase_alignment(candidate, current_phase)
    streak = score_streak_momentum(candidate, streak_info)

    total = (
        WEIGHTS["gap_priority"] * gap
        + WEIGHTS["category_balance"] * balance
        + WEIGHTS["difficulty_appropriateness"] * difficulty
        + WEIGHTS["phase_alignment"] * phase
        + WEIGHTS["streak_momentum"] * streak
    )
    return max(0.0, min(1.0, total))


def score_and_rank(
    candidates: list[MissionCandidate],
    skill_gaps: SkillGapReport,
    mission_history: list[dict[str, Any]],
    current_phase: str,
    streak_info: dict[str, Any],
    difficulty_state: DifficultyState,
) -> list[MissionCandidate]:
    """Score all candidates and return sorted by priority_score descending.

    Each candidate's priority_score field is updated in place before sorting.

    Args:
        candidates: List of mission candidates to score and rank.
        skill_gaps: Current skill gap report.
        mission_history: List of past mission dicts.
        current_phase: Current campaign phase.
        streak_info: Streak state dict.
        difficulty_state: Current per-category difficulty levels.

    Returns:
        New list of MissionCandidates sorted by priority_score descending.
    """
    for candidate in candidates:
        candidate.priority_score = score_candidate(
            candidate, skill_gaps, mission_history, current_phase,
            streak_info, difficulty_state,
        )

    return sorted(candidates, key=lambda c: c.priority_score, reverse=True)
