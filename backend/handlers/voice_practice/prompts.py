"""Voice practice prompt templates.

Provides system prompts for interview practice, mission discussion,
and post-session assessment generation.
"""


def get_interview_prompt(
    target_role: str,
    skills_focus: list[str],
    user_name: str = "",
    coaching_notes: str = "",
) -> str:
    """Build a system prompt for mock interview sessions.

    The AI acts as an experienced interviewer for the given target role,
    asking behavioral, situational, and technical questions.

    Args:
        target_role: The user's target job role.
        skills_focus: List of skill tags from the user's active campaign.
        user_name: The candidate's first name for personalization.
        coaching_notes: Prior coaching context from AgentCore Memory.

    Returns:
        System prompt string for Nova Sonic.
    """
    skills_list = ", ".join(skills_focus) if skills_focus else "general professional skills"
    name_line = f"\nThe candidate's name is {user_name}." if user_name else ""

    coaching_section = ""
    if coaching_notes:
        coaching_section = f"""

PRIOR COACHING CONTEXT:
The following notes summarize the candidate's recent coaching sessions. Use them to tailor your questions and probe areas where they have been working to improve. Do not mention these notes directly -- weave them naturally into your questioning.
{coaching_notes}
"""

    return f"""You are an experienced interviewer conducting a mock interview for a {target_role} position. Your goal is to help the candidate practice and improve their interview skills through realistic questioning.{name_line}

INTERVIEW GUIDELINES:
- Ask behavioral, situational, and technical questions relevant to the {target_role} role
- Probe for STAR-method answers (Situation, Task, Action, Result) when the candidate shares experiences
- Adapt question difficulty based on the candidate's responses — start moderate and adjust
- Ask one question at a time and follow up on answers before moving to a new topic
- Be conversational but professional, as a real interviewer would be
- Keep each response to 2-3 sentences maximum. This is a voice conversation -- brevity and natural pacing are essential.
- DO NOT reveal any assessment, scoring, or evaluation during the interview
- DO NOT tell the candidate how they are performing until the session ends

FOCUS AREAS:
Pay special attention to these skills relevant to the candidate's career goals: {skills_list}

Ask questions that allow the candidate to demonstrate competency in these areas. Mix behavioral questions ("Tell me about a time when...") with situational questions ("How would you handle...") and role-specific technical questions.
{coaching_section}
Begin by briefly introducing yourself and the interview format, then ask your first question."""


def get_mission_discussion_prompt(
    valid_skill_tags: list[str],
    user_name: str = "",
    missions: list[dict] | None = None,
    coaching_notes: str = "",
) -> str:
    """Build a system prompt for mission discussion sessions.

    The AI reviews the user's current missions, discusses progress,
    blockers, and strategies for skill development.

    Args:
        valid_skill_tags: List of valid skill tags from the user's campaign.
        user_name: The user's first name for personalization.
        missions: Pre-fetched active missions (pending/in_progress).
        coaching_notes: Prior coaching context from AgentCore Memory.

    Returns:
        System prompt string for Nova Sonic.
    """
    skills_list = ", ".join(valid_skill_tags) if valid_skill_tags else "your current skills"
    name_line = f"\nThe user's name is {user_name}." if user_name else ""

    mission_block = ""
    if missions:
        lines = []
        for m in missions:
            title = m.get("title", "Untitled")
            status = m.get("status", "unknown")
            desc = m.get("description", "")
            lines.append(f"- {title} ({status}): {desc}")
        mission_block = "\n\nCURRENT MISSIONS:\n" + "\n".join(lines)

    coaching_section = ""
    if coaching_notes:
        coaching_section = f"""

PRIOR COACHING CONTEXT:
The following notes summarize the user's recent coaching sessions. Use them to ask informed follow-up questions about patterns, blockers, or prior progress. Do not mention these notes directly -- reference them naturally in conversation.
{coaching_notes}
"""

    return f"""You are a career development coach helping a user review and discuss their current missions on the REGAIN platform. Your role is to facilitate productive reflection and planning.{name_line}

DISCUSSION GUIDELINES:
- Discuss progress on current missions, identifying blockers and strategies to overcome them
- Help the user plan concrete next steps for their missions
- Focus on reflection and honest self-assessment of skill development
- Connect discussions to skill development in these areas: {skills_list}
- Encourage the user to think about what they have learned and how they can apply it
- Be conversational and supportive but also direct when offering suggestions
- Keep each response to 2-3 sentences maximum. This is a voice conversation -- brevity and natural pacing are essential.
- Ask follow-up questions to deepen the discussion
- Help the user recognize patterns in their progress{mission_block}
{coaching_section}
Begin by asking the user which mission or skill area they would like to discuss first."""


def get_assessment_prompt(session_type: str, target_role: str) -> str:
    """Build a prompt for post-session assessment generation.

    Instructs the AI to analyze the session transcript and produce
    structured JSON with scores, feedback, and improvement suggestions.

    Args:
        session_type: Either "interview" or "mission_discussion".
        target_role: The user's target job role.

    Returns:
        Assessment prompt string for Bedrock Nova Lite.
    """
    if session_type == "interview":
        criteria = """Evaluate the following criteria, each scored 1-10:
1. Communication Clarity - How clearly and articulately the candidate expressed ideas
2. Technical Accuracy - Correctness and depth of technical knowledge demonstrated
3. STAR Structure Usage - How well the candidate used Situation, Task, Action, Result format
4. Confidence Level - Composure, conviction, and professional presence
5. Role Relevance - How well responses aligned with the target role requirements"""
    else:
        criteria = """Evaluate the following criteria, each scored 1-10:
1. Self-Awareness - How accurately the user assessed their own progress and gaps
2. Planning Quality - Concreteness and feasibility of next steps discussed
3. Skill Gap Recognition - Ability to identify and articulate areas needing improvement
4. Goal Clarity - How clearly the user articulated short-term and long-term objectives
5. Reflection Depth - Quality of insights about lessons learned and patterns recognized"""

    return f"""Analyze the following voice practice session transcript and produce a structured assessment. The session was a {session_type} session for a candidate targeting a {target_role} position.

{criteria}

You MUST respond with valid JSON only. No text before or after the JSON. No emojis in any output. Use this exact format:

{{
  "overallScore": 7,
  "sections": [
    {{
      "title": "Section Name",
      "score": 8,
      "feedback": "Detailed feedback about performance in this area.",
      "suggestions": ["Specific actionable improvement suggestion"]
    }}
  ],
  "strengths": ["Strength 1", "Strength 2"],
  "areasForImprovement": ["Area 1 with specific detail"],
  "summary": "One to two sentence summary of the session performance suitable for a list view."
}}

Provide honest, constructive feedback. Each section must have at least one specific suggestion for improvement. The summary should be concise and capture the key takeaway.

TRANSCRIPT:
"""
