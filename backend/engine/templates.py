"""Mission template definitions and instantiation.

Stores parameterized mission templates across five categories and provides
functions to instantiate them with user-specific data (profile, skill gaps,
market data) to produce personalized MissionCandidate instances.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.engine.models import MissionCandidate, SkillGapReport


@dataclass
class MissionTemplate:
    """A parameterized mission template.

    Fields containing curly-brace placeholders (e.g. ``{target_skill}``) are
    substituted at instantiation time with user-specific data.
    """

    template_id: str
    category: str
    title_template: str
    description_template: str
    rationale_template: str
    skill_tags: list[str] = field(default_factory=list)
    difficulty: int = 1
    estimated_minutes: int = 20
    expected_evidence_type: str = "reflection"
    phases: list[str] = field(default_factory=lambda: ["foundation", "expansion", "launch"])


# ---------------------------------------------------------------------------
# Template registry
# ---------------------------------------------------------------------------

_TEMPLATES: list[MissionTemplate] = [
    # -----------------------------------------------------------------------
    # REFLECTION
    # -----------------------------------------------------------------------
    MissionTemplate(
        template_id="reflection_d1_foundation",
        category="reflection",
        title_template="Reflect on your {skill} experience at {company}",
        description_template=(
            "Write a 300-word reflection on how you applied {skill} in your role "
            "at {company}. Include one specific outcome you achieved and what you "
            "would do differently today."
        ),
        rationale_template=(
            "{skill} is a transferable skill relevant to {target_role} roles. "
            "Documenting concrete examples builds your evidence portfolio."
        ),
        skill_tags=["{target_skill}", "{skill}"],
        difficulty=1,
        estimated_minutes=20,
        expected_evidence_type="reflection",
        phases=["foundation"],
    ),
    MissionTemplate(
        template_id="reflection_d2_foundation",
        category="reflection",
        title_template="Map your {skill} strengths to {target_role} requirements",
        description_template=(
            "List three situations where you used {skill} effectively. For each, "
            "write two sentences explaining how that experience translates to a "
            "{target_role} position. Save your mapping as a document."
        ),
        rationale_template=(
            "Connecting past {skill} experience to {target_role} demands helps "
            "you articulate your value in interviews and applications."
        ),
        skill_tags=["{target_skill}", "{skill}"],
        difficulty=2,
        estimated_minutes=25,
        expected_evidence_type="reflection",
        phases=["foundation"],
    ),
    MissionTemplate(
        template_id="reflection_d3_expansion",
        category="reflection",
        title_template="Analyze a challenge you overcame using {skill}",
        description_template=(
            "Describe a professional challenge where {skill} was critical. "
            "Use the STAR format (Situation, Task, Action, Result) and explain "
            "how this experience prepares you for {target_role} work."
        ),
        rationale_template=(
            "STAR-formatted stories are directly usable in {target_role} interviews "
            "and demonstrate depth in {skill}."
        ),
        skill_tags=["{target_skill}", "{skill}"],
        difficulty=3,
        estimated_minutes=30,
        expected_evidence_type="reflection",
        phases=["expansion"],
    ),
    MissionTemplate(
        template_id="reflection_d4_expansion",
        category="reflection",
        title_template="Write a case study on your {skill} impact",
        description_template=(
            "Draft a 500-word case study about a project where {skill} drove "
            "measurable results at {company}. Include metrics, your role, and "
            "lessons learned that apply to {target_role}."
        ),
        rationale_template=(
            "Case studies with metrics are powerful evidence for {target_role} "
            "applications and demonstrate {skill} mastery."
        ),
        skill_tags=["{target_skill}", "{skill}"],
        difficulty=4,
        estimated_minutes=40,
        expected_evidence_type="reflection",
        phases=["expansion"],
    ),
    MissionTemplate(
        template_id="reflection_d5_launch",
        category="reflection",
        title_template="Synthesize your {skill} journey into a career narrative",
        description_template=(
            "Write a cohesive narrative connecting your {skill} experiences across "
            "roles into a compelling career story for {target_role} positions. "
            "Include at least three evidence points and quantified outcomes."
        ),
        rationale_template=(
            "A polished career narrative tying {skill} to {target_role} is essential "
            "for cover letters, interviews, and networking conversations."
        ),
        skill_tags=["{target_skill}", "{skill}"],
        difficulty=5,
        estimated_minutes=45,
        expected_evidence_type="reflection",
        phases=["launch"],
    ),

    # -----------------------------------------------------------------------
    # SKILL BUILDING
    # -----------------------------------------------------------------------
    MissionTemplate(
        template_id="skill_building_d1_foundation",
        category="skill_building",
        title_template="Complete a beginner tutorial on {target_skill}",
        description_template=(
            "Find and complete a beginner-level tutorial on {target_skill}. "
            "Take notes on three key concepts you learned and save a screenshot "
            "or certificate of completion as evidence."
        ),
        rationale_template=(
            "{target_skill} is a priority skill for {target_role} roles in the "
            "{sector} sector. Building foundational knowledge now accelerates "
            "your transition."
        ),
        skill_tags=["{target_skill}"],
        difficulty=1,
        estimated_minutes=25,
        expected_evidence_type="artifact",
        phases=["foundation"],
    ),
    MissionTemplate(
        template_id="skill_building_d2_foundation",
        category="skill_building",
        title_template="Build a small exercise using {target_skill}",
        description_template=(
            "Create a hands-on exercise applying {target_skill}. This could be "
            "a code snippet, a spreadsheet model, a design mockup, or a written "
            "analysis. Document what you built and what you learned."
        ),
        rationale_template=(
            "Hands-on practice with {target_skill} builds demonstrable competence "
            "that {target_role} hiring managers look for."
        ),
        skill_tags=["{target_skill}"],
        difficulty=2,
        estimated_minutes=30,
        expected_evidence_type="artifact",
        phases=["foundation"],
    ),
    MissionTemplate(
        template_id="skill_building_d3_expansion",
        category="skill_building",
        title_template="Solve a real-world problem using {target_skill}",
        description_template=(
            "Identify a real-world problem in the {sector} sector and create a "
            "solution using {target_skill}. Document your approach, the solution, "
            "and the outcome in a brief write-up."
        ),
        rationale_template=(
            "Applying {target_skill} to real {sector} problems demonstrates "
            "practical readiness for {target_role} positions."
        ),
        skill_tags=["{target_skill}"],
        difficulty=3,
        estimated_minutes=35,
        expected_evidence_type="artifact",
        phases=["expansion"],
    ),
    MissionTemplate(
        template_id="skill_building_d4_expansion",
        category="skill_building",
        title_template="Teach someone a concept in {target_skill}",
        description_template=(
            "Prepare a short explanation of a {target_skill} concept and teach it "
            "to a peer or record a 5-minute video walkthrough. Save the recording "
            "or written feedback as evidence."
        ),
        rationale_template=(
            "Teaching {target_skill} deepens your understanding and demonstrates "
            "communication skills valued in {target_role} roles."
        ),
        skill_tags=["{target_skill}"],
        difficulty=4,
        estimated_minutes=40,
        expected_evidence_type="artifact",
        phases=["expansion"],
    ),
    MissionTemplate(
        template_id="skill_building_d5_launch",
        category="skill_building",
        title_template="Build a portfolio-ready project using {target_skill}",
        description_template=(
            "Create a polished project showcasing {target_skill} that you can "
            "include in your portfolio. Write a README explaining the problem, "
            "your approach, and the results."
        ),
        rationale_template=(
            "A portfolio-ready {target_skill} project is direct evidence of "
            "competence for {target_role} applications."
        ),
        skill_tags=["{target_skill}"],
        difficulty=5,
        estimated_minutes=45,
        expected_evidence_type="artifact",
        phases=["launch"],
    ),

    # -----------------------------------------------------------------------
    # PORTFOLIO
    # -----------------------------------------------------------------------
    MissionTemplate(
        template_id="portfolio_d1_foundation",
        category="portfolio",
        title_template="Draft an outline for your {target_role} portfolio",
        description_template=(
            "Create a structured outline for a portfolio targeting {target_role} "
            "positions. List at least five sections and note which skills each "
            "section will demonstrate. Save the outline as a document."
        ),
        rationale_template=(
            "A well-structured portfolio outline ensures your {target_skill} "
            "evidence is organized for maximum impact with {target_role} reviewers."
        ),
        skill_tags=["{target_skill}"],
        difficulty=1,
        estimated_minutes=20,
        expected_evidence_type="artifact",
        phases=["foundation", "expansion"],
    ),
    MissionTemplate(
        template_id="portfolio_d2_expansion",
        category="portfolio",
        title_template="Create a portfolio piece demonstrating {target_skill}",
        description_template=(
            "Produce a concrete artifact showcasing {target_skill}: a code sample, "
            "design document, analysis report, or presentation. Include a brief "
            "description of the problem solved and skills demonstrated."
        ),
        rationale_template=(
            "Tangible artifacts demonstrating {target_skill} are the strongest "
            "evidence for {target_role} applications in the {sector} sector."
        ),
        skill_tags=["{target_skill}"],
        difficulty=2,
        estimated_minutes=30,
        expected_evidence_type="artifact",
        phases=["expansion"],
    ),
    MissionTemplate(
        template_id="portfolio_d3_expansion",
        category="portfolio",
        title_template="Write a detailed project write-up for your portfolio",
        description_template=(
            "Select a completed project and write a detailed case study for your "
            "portfolio. Cover the problem, your approach using {target_skill}, "
            "results achieved, and lessons learned."
        ),
        rationale_template=(
            "Detailed write-ups transform raw experience into compelling evidence "
            "of {target_skill} competence for {target_role} roles."
        ),
        skill_tags=["{target_skill}"],
        difficulty=3,
        estimated_minutes=35,
        expected_evidence_type="artifact",
        phases=["expansion"],
    ),
    MissionTemplate(
        template_id="portfolio_d4_expansion",
        category="portfolio",
        title_template="Get feedback on your {target_skill} portfolio piece",
        description_template=(
            "Share a portfolio piece with a peer or mentor and collect structured "
            "feedback. Document the feedback received and the improvements you "
            "plan to make."
        ),
        rationale_template=(
            "External feedback on your {target_skill} work ensures your portfolio "
            "meets {target_role} industry standards in the {sector} sector."
        ),
        skill_tags=["{target_skill}"],
        difficulty=4,
        estimated_minutes=35,
        expected_evidence_type="artifact",
        phases=["expansion"],
    ),
    MissionTemplate(
        template_id="portfolio_d5_launch",
        category="portfolio",
        title_template="Publish and share your {target_role} portfolio",
        description_template=(
            "Finalize your portfolio and publish it on a platform visible to "
            "{target_role} hiring managers (GitHub, personal site, LinkedIn). "
            "Save the published URL and a screenshot as evidence."
        ),
        rationale_template=(
            "A published portfolio is the culmination of your evidence-building "
            "journey and a direct asset for {target_role} job applications."
        ),
        skill_tags=["{target_skill}"],
        difficulty=5,
        estimated_minutes=40,
        expected_evidence_type="artifact",
        phases=["launch"],
    ),

    # -----------------------------------------------------------------------
    # NETWORKING
    # -----------------------------------------------------------------------
    MissionTemplate(
        template_id="networking_d1_foundation",
        category="networking",
        title_template="Identify five {target_role} professionals to connect with",
        description_template=(
            "Research and list five professionals currently working in {target_role} "
            "roles in the {sector} sector. For each, note their background and one "
            "reason you'd like to connect. Save your list as evidence."
        ),
        rationale_template=(
            "Building a targeted networking list is the first step toward "
            "meaningful connections in the {target_role} space."
        ),
        skill_tags=["{target_skill}", "networking"],
        difficulty=1,
        estimated_minutes=20,
        expected_evidence_type="connection",
        phases=["foundation", "expansion"],
    ),
    MissionTemplate(
        template_id="networking_d2_expansion",
        category="networking",
        title_template="Send a personalized outreach message to a {target_role} professional",
        description_template=(
            "Draft and send a personalized connection request or message to a "
            "professional in the {target_role} field. Reference a specific aspect "
            "of their work and mention your {target_skill} background. Save the "
            "message as evidence."
        ),
        rationale_template=(
            "Personalized outreach builds genuine connections that can lead to "
            "{target_role} opportunities in the {sector} sector."
        ),
        skill_tags=["{target_skill}", "networking"],
        difficulty=2,
        estimated_minutes=20,
        expected_evidence_type="connection",
        phases=["expansion"],
    ),
    MissionTemplate(
        template_id="networking_d3_expansion",
        category="networking",
        title_template="Attend a {sector} industry event or webinar",
        description_template=(
            "Find and attend a virtual or in-person event related to {sector} or "
            "{target_role}. Take notes on three key takeaways and identify one "
            "person you could follow up with. Save your notes as evidence."
        ),
        rationale_template=(
            "Industry events expose you to current {sector} trends and create "
            "natural networking opportunities for {target_role} transitions."
        ),
        skill_tags=["{target_skill}", "networking"],
        difficulty=3,
        estimated_minutes=35,
        expected_evidence_type="connection",
        phases=["expansion"],
    ),
    MissionTemplate(
        template_id="networking_d4_launch",
        category="networking",
        title_template="Conduct an informational interview about {target_role}",
        description_template=(
            "Schedule and conduct a 20-minute informational interview with someone "
            "working in a {target_role} position. Prepare five questions about "
            "their career path and {target_skill} usage. Document key insights."
        ),
        rationale_template=(
            "Informational interviews provide insider knowledge about {target_role} "
            "roles and can lead to referrals."
        ),
        skill_tags=["{target_skill}", "networking"],
        difficulty=4,
        estimated_minutes=40,
        expected_evidence_type="connection",
        phases=["launch"],
    ),
    MissionTemplate(
        template_id="networking_d5_launch",
        category="networking",
        title_template="Request a referral or introduction for a {target_role} opportunity",
        description_template=(
            "Reach out to a contact in your network and ask for a referral or "
            "introduction to a {target_role} opportunity. Prepare a brief pitch "
            "highlighting your {target_skill} evidence. Document the interaction."
        ),
        rationale_template=(
            "Referrals are the most effective path to {target_role} positions. "
            "Your documented {target_skill} evidence supports a strong ask."
        ),
        skill_tags=["{target_skill}", "networking"],
        difficulty=5,
        estimated_minutes=30,
        expected_evidence_type="connection",
        phases=["launch"],
    ),

    # -----------------------------------------------------------------------
    # MARKET RESEARCH
    # -----------------------------------------------------------------------
    MissionTemplate(
        template_id="market_research_d1_foundation",
        category="market_research",
        title_template="Research {target_role} job postings in the {sector} sector",
        description_template=(
            "Find and analyze three current {target_role} job postings in the "
            "{sector} sector. For each, list the required skills, experience level, "
            "and any mention of {target_skill}. Save your analysis as evidence."
        ),
        rationale_template=(
            "Understanding what {sector} employers want for {target_role} roles "
            "ensures your skill-building efforts are market-aligned."
        ),
        skill_tags=["{target_skill}", "market_research"],
        difficulty=1,
        estimated_minutes=20,
        expected_evidence_type="research",
        phases=["foundation", "expansion"],
    ),
    MissionTemplate(
        template_id="market_research_d2_expansion",
        category="market_research",
        title_template="Compare your skills against {target_role} requirements",
        description_template=(
            "Using the job postings you've researched, create a skills comparison "
            "matrix. Map your current skills against the top requirements for "
            "{target_role} positions. Identify your three biggest gaps and save "
            "the matrix as evidence."
        ),
        rationale_template=(
            "A skills gap matrix gives you a clear roadmap for what to build "
            "next on your path to {target_role}."
        ),
        skill_tags=["{target_skill}", "market_research"],
        difficulty=2,
        estimated_minutes=25,
        expected_evidence_type="research",
        phases=["expansion"],
    ),
    MissionTemplate(
        template_id="market_research_d3_expansion",
        category="market_research",
        title_template="Analyze {sector} industry trends affecting {target_role}",
        description_template=(
            "Research current trends in the {sector} sector that impact "
            "{target_role} roles. Write a brief report covering emerging "
            "technologies, shifting skill demands, and how {target_skill} "
            "fits into the landscape. Save your report."
        ),
        rationale_template=(
            "Trend awareness in {sector} helps you position your {target_skill} "
            "experience for maximum relevance to {target_role} employers."
        ),
        skill_tags=["{target_skill}", "market_research"],
        difficulty=3,
        estimated_minutes=30,
        expected_evidence_type="research",
        phases=["expansion"],
    ),
    MissionTemplate(
        template_id="market_research_d4_launch",
        category="market_research",
        title_template="Identify target companies hiring for {target_role}",
        description_template=(
            "Research and create a list of five companies in the {sector} sector "
            "actively hiring for {target_role} positions. For each, note their "
            "culture, tech stack, and how your {target_skill} background aligns. "
            "Save your research."
        ),
        rationale_template=(
            "A targeted company list focuses your job search and lets you tailor "
            "your {target_skill} portfolio to specific {target_role} opportunities."
        ),
        skill_tags=["{target_skill}", "market_research"],
        difficulty=4,
        estimated_minutes=35,
        expected_evidence_type="research",
        phases=["launch"],
    ),
    MissionTemplate(
        template_id="market_research_d5_launch",
        category="market_research",
        title_template="Create a {target_role} application strategy",
        description_template=(
            "Based on your market research, draft a targeted application strategy "
            "for {target_role} positions. Include your top three target companies, "
            "how you'll position {target_skill}, and a timeline. Save the strategy."
        ),
        rationale_template=(
            "A concrete application strategy turns your research and evidence "
            "into actionable steps toward landing a {target_role} position."
        ),
        skill_tags=["{target_skill}", "market_research"],
        difficulty=5,
        estimated_minutes=40,
        expected_evidence_type="research",
        phases=["launch"],
    ),
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_all_templates() -> list[MissionTemplate]:
    """Return all registered mission templates.

    Returns:
        A list of every MissionTemplate in the registry.
    """
    return list(_TEMPLATES)


def _resolve_placeholder(value: str, substitutions: dict[str, str]) -> str:
    """Replace ``{key}`` placeholders in *value* using *substitutions*.

    Unknown placeholders are replaced with an empty string so no raw
    ``{…}`` tokens leak into user-facing text.
    """
    result = value
    for key, replacement in substitutions.items():
        result = result.replace(f"{{{key}}}", replacement)
    return result


def _build_substitutions(
    profile: dict[str, Any],
    skill_gaps: SkillGapReport,
    market_data: dict[str, Any],
) -> dict[str, str]:
    """Build the placeholder → value mapping from user data.

    Args:
        profile: User profile with keys target_role, skills, experience, name.
        skill_gaps: Skill gap analysis result.
        market_data: Market data with keys top_skills, sector, trending_roles.

    Returns:
        Dict mapping placeholder names to concrete string values.
    """
    # Pick the highest-priority skill gap as the target skill
    target_skill = (
        skill_gaps.priority_skills[0]
        if skill_gaps.priority_skills
        else (profile.get("skills", ["general"])[0] if profile.get("skills") else "general")
    )

    # Pick a representative skill from the user's existing skills
    skill = (
        profile.get("skills", ["general"])[0]
        if profile.get("skills")
        else "general"
    )

    # Pick the most recent company from experience
    experience = profile.get("experience", [])
    company = (
        experience[0].get("company", "your previous employer")
        if experience
        else "your previous employer"
    )

    return {
        "target_skill": str(target_skill),
        "skill": str(skill),
        "target_role": str(profile.get("target_role", "your target role")),
        "company": str(company),
        "sector": str(market_data.get("sector", "your target sector")),
        "name": str(profile.get("name", "")),
    }


def instantiate_template(
    template: MissionTemplate,
    profile: dict[str, Any],
    skill_gaps: SkillGapReport,
    market_data: dict[str, Any],
) -> MissionCandidate:
    """Substitute user data into a template to produce a mission candidate.

    Args:
        template: The parameterized mission template.
        profile: User profile dict (target_role, skills, experience, name).
        skill_gaps: Skill gap analysis result.
        market_data: Market data dict (top_skills, sector, trending_roles).

    Returns:
        A fully instantiated MissionCandidate with no raw placeholders.
    """
    subs = _build_substitutions(profile, skill_gaps, market_data)

    resolved_tags = [
        _resolve_placeholder(tag, subs) for tag in template.skill_tags
    ]
    # Remove empty tags and deduplicate while preserving order
    seen: set[str] = set()
    unique_tags: list[str] = []
    for tag in resolved_tags:
        if tag and tag not in seen:
            seen.add(tag)
            unique_tags.append(tag)

    # Compute a simple market relevance score based on whether the target
    # skill appears in the market's top skills list.
    top_skills = [s.lower() for s in market_data.get("top_skills", [])]
    target_skill_lower = subs["target_skill"].lower()
    market_relevance = 1.0 if target_skill_lower in top_skills else 0.5

    return MissionCandidate(
        template_id=template.template_id,
        category=template.category,
        title=_resolve_placeholder(template.title_template, subs),
        description=_resolve_placeholder(template.description_template, subs),
        rationale=_resolve_placeholder(template.rationale_template, subs),
        skill_tags=unique_tags,
        difficulty=template.difficulty,
        estimated_minutes=template.estimated_minutes,
        expected_evidence_type=template.expected_evidence_type,
        phase=template.phases[0],
        market_relevance_score=market_relevance,
    )


def instantiate_all_templates(
    profile: dict[str, Any],
    skill_gaps: SkillGapReport,
    market_data: dict[str, Any],
    phase: str,
) -> list[MissionCandidate]:
    """Instantiate all templates valid for the given campaign phase.

    Args:
        profile: User profile dict (target_role, skills, experience, name).
        skill_gaps: Skill gap analysis result.
        market_data: Market data dict (top_skills, sector, trending_roles).
        phase: Current campaign phase ("foundation", "expansion", or "launch").

    Returns:
        List of MissionCandidates from templates whose phases include *phase*.
    """
    candidates: list[MissionCandidate] = []
    for template in _TEMPLATES:
        if phase in template.phases:
            candidate = instantiate_template(template, profile, skill_gaps, market_data)
            # Ensure the candidate's phase reflects the requested phase
            candidate.phase = phase
            candidates.append(candidate)
    return candidates
