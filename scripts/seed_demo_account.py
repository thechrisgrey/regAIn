#!/usr/bin/env python3
"""Seed a demo account with 30 days of realistic mission + evidence data.

Creates a user journey that demonstrates the full Impact Scorecard:
- 25+ completed missions across all 5 categories
- Evidence entries with varying richness (word count, artifacts)
- Difficulty progression from 1 to 4
- Phase advancement through Foundation → Expansion → Launch

Usage:
    AWS_PROFILE=regain python scripts/seed_demo_account.py <user_id> <campaign_id>

The user and campaign must already exist (created via onboarding).
This script adds missions and evidence to make the scorecard compelling.
"""

import sys
import uuid
from datetime import datetime, timedelta, timezone

import boto3

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

REGION = "us-east-1"

MISSIONS = [
    # (day_offset, category, difficulty, title, skill_tags, reflection, has_artifact)
    # Foundation phase: days 1-10 (mostly difficulty 1-2)
    (1, "reflection", 1, "Reflect on your leadership experience", ["Leadership"], "I led a team of 12 soldiers through complex operations in Afghanistan. The skills I developed — rapid decision-making under pressure, mission planning, and team cohesion — translate directly to product management. I realize now that my ability to prioritize under uncertainty is a core competency that employers value.", False),
    (1, "skill_building", 1, "Complete an introductory project management exercise", ["Project Management"], "I worked through a project scoping exercise using the RICE framework to prioritize features. This mirrors how I used to plan mission objectives — identify high-impact, low-effort tasks first. I scored 5 hypothetical features and created a prioritized backlog. The parallels between military planning and product roadmapping are striking.", False),
    (2, "market_research", 1, "Research job postings for your target role", ["Market Research"], "I analyzed 15 Product Manager job postings on LinkedIn and USAJobs. Common requirements: stakeholder management (14/15), data-driven decision making (12/15), agile methodology (11/15), and technical communication (10/15). My military background covers stakeholder management and decision-making. I need to build visible artifacts for agile and technical communication.", False),
    (3, "networking", 1, "Connect with a professional in your target field", ["Networking", "Communication"], "I reached out to a former Army colleague who successfully transitioned to a PM role at Amazon. Key takeaway: he emphasized that the 'leadership principles' framework maps almost perfectly to military values. He recommended I document specific examples of each principle from my service — this is essentially what REGAIN's evidence vault does.", False),
    (4, "skill_building", 2, "Build a simple product requirements document", ["Technical Writing", "Product Management"], "I created a PRD for a hypothetical veteran job matching app. Sections included: problem statement, user personas (3 types of transitioning service members), success metrics, and MVP feature set. The writing process forced me to articulate user needs precisely — a skill I used constantly when writing operations orders but never in a civilian product context.", True),
    (5, "reflection", 1, "Document your transferable skills inventory", ["Self-Assessment"], "I mapped 8 military skills to civilian equivalents: mission planning → project management, intelligence analysis → data analysis, team leadership → people management, operations briefing → stakeholder communication, risk assessment → risk management, logistics coordination → supply chain, training program design → curriculum development, after-action review → retrospective facilitation.", False),
    (6, "portfolio", 2, "Create a case study from a past accomplishment", ["Portfolio Development", "Leadership"], "I wrote a structured case study about the time I led a 48-hour humanitarian assistance mission after a natural disaster. Format: Situation (earthquake, 2000 displaced civilians), Task (establish medical triage and supply distribution), Action (coordinated 3 agencies, set up 4 distribution points, managed 40 volunteers), Result (served 1,847 people in 36 hours, zero injuries). This is STAR format — exactly what interviewers want.", True),
    (7, "skill_building", 2, "Practice data analysis with a real dataset", ["Data Analysis", "Python Programming"], "I downloaded a public dataset of job market trends and used Python pandas to analyze it. Created 3 visualizations: monthly posting volume by role, salary distribution by experience level, and top skills by frequency. This is the first time I've used Python for analysis rather than scripting — it's more intuitive than I expected.", True),
    (8, "market_research", 2, "Analyze salary ranges for your target role", ["Market Research"], "I compiled salary data from Glassdoor, LinkedIn, and the BLS for Product Manager roles in my target regions. Median: $135K in DC metro, $145K in Seattle, $125K in Austin. Key finding: PM roles requiring security clearance (which I have) pay 15-20% above median. This is a competitive advantage I hadn't considered.", False),
    (10, "networking", 2, "Attend a virtual industry event or webinar", ["Networking", "Industry Knowledge"], "I attended a Product School webinar on 'From Military to Product Management.' Three actionable takeaways: (1) Frame every accomplishment as a hypothesis-test-learn cycle, (2) military planning documents are essentially PRDs — reframe them, (3) veteran-specific PM bootcamps exist at reduced cost through VET TEC. I connected with 4 other transitioning veterans in the chat.", False),

    # Expansion phase: days 11-22 (difficulty 2-3)
    (11, "skill_building", 3, "Complete an agile methodology certification module", ["Agile Methodology", "Project Management"], "I completed the first 4 modules of a Scrum fundamentals course. Key concepts: sprint planning maps to mission briefing cycles, daily standups mirror morning formations, retrospectives are after-action reviews. The terminology is different but the operational cadence is nearly identical. I scored 92% on the assessment.", True),
    (12, "portfolio", 3, "Design a product feature from concept to wireframe", ["Product Design", "User Experience"], "I designed a feature for the veteran job matching concept: a 'skill translator' that converts military occupational specialties to civilian equivalents. Created user flow (3 screens), wireframes in Figma, and a 1-page spec. This is the first time I've used Figma — the interface is intuitive and the output looks professional.", True),
    (13, "reflection", 2, "Assess your progress and identify remaining gaps", ["Self-Assessment"], "After 12 missions, I can see clear patterns. Strengths: leadership narratives, strategic thinking, stakeholder management. Gaps: technical product tools (SQL, A/B testing), quantitative analysis depth, and civilian networking vocabulary. The evidence vault makes these gaps visible — I have 8 entries for leadership but only 2 for technical skills.", False),
    (14, "skill_building", 3, "Learn SQL basics and write 5 practice queries", ["SQL", "Data Analysis"], "I completed SQLZoo tutorials and practiced on a sample e-commerce database. Wrote queries for: top-selling products by region, customer retention cohort analysis, monthly revenue trend, average order value by customer segment, and inventory turnover rate. SQL syntax is logical and structured — similar to how I'd query an intelligence database.", True),
    (16, "market_research", 3, "Interview a hiring manager in your target industry", ["Market Research", "Networking"], "I had a 30-minute informational interview with a Director of Product at a defense tech startup. Key insights: (1) they specifically seek veterans for PM roles because of security clearance + ops experience, (2) the biggest gap they see in veteran candidates is data fluency, not leadership, (3) they value 'evidence of learning velocity' — showing you can pick up new tools quickly.", False),
    (17, "portfolio", 3, "Write a technical blog post about a skill you learned", ["Technical Writing", "Communication"], "I wrote a 1,200-word blog post titled 'What Operations Orders Taught Me About Product Requirements Documents.' I compared the military 5-paragraph OPORD format (Situation, Mission, Execution, Sustainment, Command) to a PRD (Problem, Objective, Solution, Metrics, Timeline). Published on LinkedIn — got 47 reactions and 3 comments from hiring managers.", True),
    (18, "networking", 3, "Conduct a mock interview with a peer", ["Interview Skills", "Communication"], "I did a 45-minute mock PM interview with a mentor. Questions covered: product sense (design a feature for blind users), analytical (how would you measure success of a new feature), and behavioral (tell me about a time you failed). Feedback: strong on behavioral (military stories are compelling), needs work on structured frameworks for product sense questions.", False),
    (20, "skill_building", 3, "Build a data dashboard or analysis project", ["Data Analysis", "Python Programming"], "I built a dashboard analyzing veteran employment trends using public BLS data. Used Python + matplotlib to create 6 charts: unemployment rate by service branch, top industries hiring veterans, salary premium for clearance holders, geographic distribution of veteran-friendly employers, time-to-employment by MOS category, and education level impact on salary. Exported as a PDF report.", True),
    (21, "reflection", 3, "Document lessons learned from your reskilling journey", ["Self-Assessment", "Communication"], "Three weeks in, I can articulate my value proposition clearly: I bring 10 years of leading under uncertainty, a TS/SCI clearance, proven ability to learn complex systems rapidly (evidence: 4 technical skills acquired in 3 weeks), and a documented track record of mission execution. The evidence vault now has 18 entries across 12 skills. That's not a resume claim — it's a portfolio.", False),

    # Launch phase: days 22-30 (difficulty 3-4)
    (22, "skill_building", 4, "Complete an advanced product analytics exercise", ["Product Analytics", "A/B Testing"], "I designed an A/B test framework for a hypothetical feature launch: defined hypothesis, selected metrics (primary: conversion rate, guardrail: page load time), calculated sample size (n=5,000 per variant at 80% power), and wrote the analysis plan including segmentation by user cohort. This is the quantitative rigor hiring managers look for.", True),
    (23, "portfolio", 4, "Create a comprehensive case study with metrics", ["Portfolio Development", "Product Management"], "I wrote a full case study of my capstone military operation — a 6-month capacity building program. Structured as: Context (partner nation capability gap), Approach (phased training program with measurable milestones), Execution (3 phases, 120 personnel trained, 8 joint exercises), Results (partner unit achieved independent operational capability, 94% knowledge retention at 6-month follow-up, program adopted as template for 3 other regions). This is product management in a military context.", True),
    (25, "market_research", 4, "Map the competitive landscape for roles in your target field", ["Market Research", "Strategic Thinking"], "I created a competitive landscape analysis of PM roles in defense tech: 12 companies, mapped by size, clearance requirements, veteran hiring programs, and average compensation. Key finding: mid-size defense tech companies (100-500 employees) offer the best combination of veteran-friendly culture + competitive compensation + meaningful product work. Narrowed my target list to 5 companies.", True),
    (27, "networking", 4, "Deliver a presentation to a professional audience", ["Public Speaking", "Communication"], "I presented my 'OPORD to PRD' framework at a local veteran transition meetup (22 attendees). 15-minute talk + 10 minutes Q&A. Three people asked for my LinkedIn afterward. One attendee is a recruiter at a defense tech company on my target list — we scheduled a follow-up coffee. The presentation itself is now a portfolio artifact.", True),
    (29, "skill_building", 4, "Build an end-to-end product prototype", ["Product Management", "Technical Skills"], "I built a clickable prototype of the veteran skill translator app using Figma. 8 screens covering the full user journey: onboarding, MOS input, skill translation output, job matching, and application tracking. Includes realistic data and interaction patterns. This is the strongest single artifact in my evidence vault — it demonstrates product thinking, design skills, and user empathy in one deliverable.", True),
]


def seed(user_id: str, campaign_id: str) -> None:
    """Seed missions and evidence for a demo account."""
    dynamodb = boto3.resource("dynamodb", region_name=REGION)
    missions_table = dynamodb.Table("RegainMissionHistory")
    evidence_table = dynamodb.Table("RegainEvidenceVault")

    now = datetime.now(timezone.utc)
    base_date = now - timedelta(days=30)

    mission_count = 0
    evidence_count = 0

    for day_offset, category, difficulty, title, skill_tags, reflection, has_artifact in MISSIONS:
        mission_date = base_date + timedelta(days=day_offset)
        mission_id = f"demo-mission-{uuid.uuid4()}"
        evidence_id = f"demo-evidence-{uuid.uuid4()}"

        completed_at = mission_date.replace(
            hour=10 + (day_offset % 8),
            minute=(day_offset * 7) % 60,
        ).isoformat()

        # Write mission
        mission_item = {
            "userId": user_id,
            "missionId": mission_id,
            "campaignId": campaign_id,
            "title": title,
            "description": f"Complete this {category.replace('_', ' ')} mission to build your evidence vault.",
            "status": "completed",
            "category": category,
            "difficulty": difficulty,
            "skillTags": skill_tags,
            "completedAt": completed_at,
            "completedDate": completed_at[:10],
            "evidenceId": evidence_id,
        }
        missions_table.put_item(Item=mission_item)
        mission_count += 1

        # Write evidence
        evidence_item = {
            "userId": user_id,
            "evidenceId": evidence_id,
            "missionId": mission_id,
            "skillTag": skill_tags[0],
            "reflection": reflection,
            "createdAt": completed_at,
            "wordCount": len(reflection.split()),
        }
        if has_artifact:
            evidence_item["artifactUrl"] = f"https://example.com/artifacts/{evidence_id}.pdf"

        evidence_table.put_item(Item=evidence_item)
        evidence_count += 1

    print(f"Seeded {mission_count} missions and {evidence_count} evidence entries for user {user_id}")
    print(f"Date range: {base_date.strftime('%Y-%m-%d')} to {now.strftime('%Y-%m-%d')}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <user_id> <campaign_id>")
        sys.exit(1)
    seed(sys.argv[1], sys.argv[2])
