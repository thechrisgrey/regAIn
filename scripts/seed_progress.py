#!/usr/bin/env python3
"""Seed 15 days of realistic progress data for a Regain user account.

Usage:
    AWS_PROFILE=regain python3 scripts/seed_progress.py

This script:
- Backdates the campaign start to 15 days ago
- Creates 12 completed missions across 4 categories with realistic dates
- Creates corresponding evidence items linked to each mission
- Updates campaign difficulty state to reflect progression
- Does NOT touch existing pending/active missions
"""

import uuid
import json
import boto3
from datetime import datetime, timezone, timedelta

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

REGION = "us-east-1"
USER_ID = "84f82408-20a1-70e5-06dc-9c4c9a94fac4"
CAMPAIGN_ID = "3506cb1b-6a01-4c07-b5f9-97c530e78c11"
DAYS_TO_SEED = 15
COMPANY = "Altivum Inc"
TARGET_ROLE = "AI Implementation"
SKILLS_FOCUS = ["Leadership", "Data Analysis"]

# DynamoDB tables
CAMPAIGNS_TABLE = "RegainCampaigns"
MISSIONS_TABLE = "RegainMissionHistory"
EVIDENCE_TABLE = "RegainEvidenceVault"
PROFILES_TABLE = "RegainUserProfiles"

# ---------------------------------------------------------------------------
# Realistic mission + evidence data (12 completed missions over 15 days)
# ---------------------------------------------------------------------------

SEED_MISSIONS = [
    # Day 1-2: Reflection missions (getting started)
    {
        "day_offset": 1,
        "category": "reflection",
        "difficulty": 1,
        "title": "Reflect on your Leadership experience at Altivum Inc",
        "description": "Write a 300-word reflection on a specific leadership moment from your time at Altivum Inc. Focus on what you learned and how it connects to AI Implementation.",
        "skillTags": ["Leadership"],
        "reflection": "During my time as Software QA Lead at Altivum Inc, I led the migration of our entire test automation framework from Selenium to Playwright. This wasn't just a technical decision -- it required convincing stakeholders, managing a team of 4 QA engineers through the transition, and maintaining test coverage throughout. The biggest challenge was resistance from senior engineers who were comfortable with the existing tools. I organized weekly knowledge-sharing sessions and paired junior and senior engineers together. Within 6 weeks, we had full coverage restored and test execution time dropped by 40%. This experience taught me that technical leadership is really about building consensus and creating safe spaces for people to learn. As I transition toward AI Implementation, I see direct parallels -- introducing AI tools into existing workflows requires the same change management skills. People need to understand the 'why' before they can embrace the 'how'. I plan to leverage this experience in helping organizations adopt AI tools by focusing on the human side of implementation, not just the technical deployment.",
    },
    {
        "day_offset": 2,
        "category": "reflection",
        "difficulty": 1,
        "title": "Map your Data Analysis strengths to AI Implementation requirements",
        "description": "Analyze how your existing data analysis skills transfer to AI implementation roles. Identify gaps and strengths.",
        "skillTags": ["Data Analysis"],
        "reflection": "My data analysis background gives me a unique perspective on AI implementation. At Altivum, I built dashboards tracking test coverage metrics, defect trends, and release quality scores. I became proficient in SQL queries against our test results database and used Python scripts to automate weekly reporting. These skills translate directly to AI implementation: understanding data pipelines, evaluating model performance metrics, and communicating results to non-technical stakeholders. The gap I see is in ML-specific data preparation -- feature engineering, handling training/test splits, and dealing with bias in datasets. However, my analytical mindset and comfort with large datasets is a strong foundation. I also have experience with A/B testing from our feature flag rollouts, which maps to evaluating AI model performance in production. My biggest strength is translating complex data insights into actionable recommendations for leadership, which is critical when presenting AI implementation ROI.",
    },
    # Day 3-4: Skill building
    {
        "day_offset": 3,
        "category": "skill_building",
        "difficulty": 1,
        "title": "Complete a beginner tutorial on AI fundamentals",
        "description": "Work through an introductory AI/ML course covering key concepts, terminology, and use cases relevant to AI Implementation.",
        "skillTags": ["AI Fundamentals"],
        "reflection": "Completed the Google AI Essentials course on Coursera. Key takeaways: supervised vs unsupervised learning, the difference between ML and deep learning, and practical applications like NLP and computer vision. The most relevant section for my target role was the module on AI implementation strategy -- understanding when to build vs buy, how to evaluate vendor solutions, and the importance of data readiness assessments. I also learned about the concept of 'AI maturity levels' in organizations, which gives me a framework for assessing where a company stands and what implementation approach would work best.",
    },
    {
        "day_offset": 4,
        "category": "skill_building",
        "difficulty": 2,
        "title": "Build a simple data pipeline using Python",
        "description": "Create a basic ETL pipeline that extracts data, transforms it, and loads it into a structured format. Document your process.",
        "skillTags": ["Data Analysis", "Python Programming"],
        "reflection": "Built a Python ETL pipeline that pulls job posting data from a CSV, cleans and normalizes it, then outputs structured JSON. Used pandas for data manipulation and implemented basic error handling. The pipeline extracts job titles, required skills, salary ranges, and location data. Learned about handling messy real-world data -- missing values, inconsistent formatting, duplicate entries. This directly applies to AI implementation where data quality is the foundation of any successful deployment. Also experimented with basic NLP using spaCy to extract skill keywords from job descriptions, which gave me hands-on experience with a common AI implementation task.",
        "artifactUrl": "https://github.com/example/data-pipeline-exercise",
    },
    # Day 5-6: Market research
    {
        "day_offset": 5,
        "category": "market_research",
        "difficulty": 1,
        "title": "Research AI Implementation job postings in your target market",
        "description": "Analyze 10+ job postings for AI Implementation roles. Identify common requirements, tools, and qualifications.",
        "skillTags": ["Market Research"],
        "reflection": "Analyzed 15 AI Implementation job postings across LinkedIn, Indeed, and company career pages. Key findings: (1) Most roles require 3-5 years experience with some combination of technical and business skills. (2) Top tools mentioned: Python (80%), SQL (67%), cloud platforms like AWS/Azure (60%), and MLOps tools like MLflow/SageMaker (40%). (3) Soft skills emphasized: stakeholder communication (73%), project management (60%), and change management (47%). (4) Salary range: $110K-$160K in major metros. My QA background covers the structured thinking and automation aspects. Gaps to fill: hands-on ML model deployment, cloud AI services (SageMaker, Bedrock), and formal project management certification. The change management emphasis confirms my leadership experience is highly relevant.",
    },
    {
        "day_offset": 6,
        "category": "market_research",
        "difficulty": 2,
        "title": "Analyze AI adoption trends in the Technology sector",
        "description": "Research how companies in your industry are adopting AI. Identify opportunities and common implementation patterns.",
        "skillTags": ["Market Research", "AI Fundamentals"],
        "reflection": "Researched AI adoption trends across 8 technology companies ranging from startups to enterprises. Key patterns: (1) Most companies start with customer-facing AI (chatbots, recommendation engines) before internal process automation. (2) The biggest implementation bottleneck is data readiness, not technology -- 60% of projects stall due to data quality issues. (3) Companies with dedicated AI implementation roles (vs. pure ML engineering) report higher success rates because they bridge the gap between technical teams and business stakeholders. (4) Cloud-native AI services (AWS Bedrock, Azure AI) are rapidly replacing custom model training for most enterprise use cases. This validates my transition strategy: focusing on implementation and integration rather than model building, and leveraging my QA background's emphasis on quality and process.",
    },
    # Day 7-8: Networking + Portfolio
    {
        "day_offset": 7,
        "category": "networking",
        "difficulty": 1,
        "title": "Identify 5 professionals in AI Implementation roles",
        "description": "Research and list 5 professionals currently working in AI Implementation or similar roles. Note their backgrounds and career paths.",
        "skillTags": ["Networking"],
        "reflection": "Identified and researched 5 AI Implementation professionals on LinkedIn: (1) Sarah Chen, AI Solutions Architect at AWS -- transitioned from software engineering, emphasizes customer obsession. (2) Marcus Johnson, AI Implementation Lead at Deloitte -- came from management consulting, focuses on change management. (3) Priya Patel, Director of AI Strategy at a mid-size fintech -- former data analyst who upskilled into AI. (4) David Kim, AI Program Manager at Microsoft -- background in QA/testing like mine, leveraged quality mindset for AI validation. (5) Rachel Torres, AI Implementation Consultant (independent) -- former project manager. Key insight: none of them had traditional ML engineering backgrounds. Most transitioned from adjacent roles by combining domain expertise with AI literacy. David Kim's path is especially relevant -- QA to AI implementation.",
    },
    {
        "day_offset": 8,
        "category": "portfolio",
        "difficulty": 1,
        "title": "Draft an outline for your AI Implementation portfolio",
        "description": "Create a structured outline for a portfolio that showcases your skills and experience relevant to AI Implementation.",
        "skillTags": ["Portfolio Development"],
        "reflection": "Created a portfolio outline with 5 sections: (1) About Me -- narrative connecting QA leadership to AI implementation, emphasizing quality mindset and change management. (2) Case Studies -- plan to write 3 detailed case studies: test automation migration (leadership), data dashboard project (analytics), and a new AI tool evaluation (to be completed). (3) Technical Skills -- Python, SQL, data analysis, test automation, with plans to add cloud AI services. (4) Thought Leadership -- plan to write 2 blog posts on AI implementation from a quality perspective. (5) Testimonials/Endorsements -- will request from former colleagues and managers. Target completion: portfolio draft in 3 weeks, published version in 6 weeks. Will host on a personal site with clean, professional design.",
    },
    # Day 9-11: More skill building + reflection
    {
        "day_offset": 9,
        "category": "skill_building",
        "difficulty": 2,
        "title": "Explore AWS AI services relevant to implementation",
        "description": "Get hands-on with AWS AI services like Bedrock, SageMaker, or Comprehend. Document what you learned and how it applies to your target role.",
        "skillTags": ["AI Fundamentals", "Cloud Computing"],
        "reflection": "Spent 3 hours exploring AWS AI services in a free-tier account. Tested Amazon Bedrock with Claude and Titan models -- impressed by how accessible LLM integration has become through simple API calls. Also explored Amazon Comprehend for text analysis (sentiment, entity extraction) and Rekognition for image analysis. Key realization: AI implementation roles increasingly focus on orchestrating these managed services rather than building models from scratch. Created a simple Python script that chains Bedrock for text generation with Comprehend for sentiment analysis. This is exactly the kind of integration work that AI Implementation roles handle. Also learned about SageMaker Canvas for no-code ML, which is relevant for enabling non-technical teams to use AI.",
    },
    {
        "day_offset": 10,
        "category": "reflection",
        "difficulty": 2,
        "title": "Write a STAR-format story about leading a technical transformation",
        "description": "Use the STAR method to document a specific instance where you led a significant technical change. Focus on measurable outcomes.",
        "skillTags": ["Leadership", "Communication"],
        "reflection": "Situation: At Altivum Inc, our manual QA process was causing 2-week release delays, and the team was burning out from repetitive regression testing. Task: As QA Lead, I was tasked with reducing regression cycle time by 50% while maintaining quality standards. Action: I proposed and led the adoption of a CI/CD pipeline with automated test execution. First, I conducted a tool evaluation (Jenkins vs GitHub Actions vs CircleCI), presented cost-benefit analysis to leadership, and secured budget approval. Then I created a phased rollout plan: Phase 1 (weeks 1-3) automated smoke tests, Phase 2 (weeks 4-6) regression suite, Phase 3 (weeks 7-8) performance tests. I mentored 3 junior QA engineers in test automation, conducted code reviews, and established testing standards. Result: Regression cycle time dropped from 10 days to 3 days (70% reduction), release frequency increased from bi-weekly to weekly, and team satisfaction scores improved by 25% in the next engagement survey. This story demonstrates the exact skills needed for AI implementation: evaluating tools, building business cases, managing phased rollouts, and measuring outcomes.",
    },
    {
        "day_offset": 12,
        "category": "skill_building",
        "difficulty": 2,
        "title": "Complete an intermediate Data Analysis project",
        "description": "Work on a data analysis project that demonstrates your ability to extract insights from complex datasets and present findings clearly.",
        "skillTags": ["Data Analysis", "Python Programming"],
        "reflection": "Analyzed a public dataset of AI adoption rates across industries using pandas and matplotlib. Created visualizations showing: (1) adoption rates by industry sector, (2) correlation between company size and AI maturity, (3) most common AI use cases by sector. Key finding: mid-size companies (500-5000 employees) have the fastest growing adoption rates but the least structured implementation processes -- this is exactly the gap that AI Implementation roles fill. Built a Jupyter notebook with clear documentation and exported it as both HTML and PDF for portfolio use. Also practiced presenting findings in a non-technical summary format, which is a critical skill for AI implementation roles where you bridge technical and business teams.",
        "artifactUrl": "https://github.com/example/ai-adoption-analysis",
    },
    # Day 14: Networking follow-up
    {
        "day_offset": 14,
        "category": "networking",
        "difficulty": 2,
        "title": "Send outreach messages to 3 AI professionals",
        "description": "Draft and send personalized connection requests or messages to professionals in AI Implementation roles you identified.",
        "skillTags": ["Networking", "Communication"],
        "reflection": "Sent personalized LinkedIn messages to 3 of the 5 professionals I identified earlier: David Kim (QA to AI path), Priya Patel (data analyst to AI), and Marcus Johnson (consulting to AI). Each message was tailored to their specific background with a clear ask. For David, I mentioned our shared QA background and asked about his transition experience. For Priya, I referenced her article on data-driven AI adoption. For Marcus, I asked about the change management frameworks he uses for AI rollouts. David responded within 2 hours and agreed to a 20-minute virtual coffee. Priya liked my message (pending response). No response from Marcus yet. Key learning: personalized messages with specific references to the person's work get much better response rates than generic connection requests. Planning the coffee chat with David for next week.",
    },
]


def main():
    ddb = boto3.resource("dynamodb", region_name=REGION)
    campaigns_table = ddb.Table(CAMPAIGNS_TABLE)
    missions_table = ddb.Table(MISSIONS_TABLE)
    evidence_table = ddb.Table(EVIDENCE_TABLE)

    now = datetime.now(timezone.utc)
    campaign_start = now - timedelta(days=DAYS_TO_SEED)

    # 1. Backdate campaign start
    print(f"Backdating campaign start to {campaign_start.isoformat()}")
    campaigns_table.update_item(
        Key={"userId": USER_ID, "campaignId": CAMPAIGN_ID},
        UpdateExpression="SET startDate = :sd",
        ExpressionAttributeValues={":sd": campaign_start.isoformat()},
    )

    # 2. Create completed missions + evidence
    created_missions = 0
    created_evidence = 0
    unique_skills = set()

    for mission_data in SEED_MISSIONS:
        mission_id = str(uuid.uuid4())
        evidence_id = str(uuid.uuid4())

        # Compute timestamps
        day = mission_data["day_offset"]
        assigned_at = campaign_start + timedelta(days=day, hours=8)
        started_at = assigned_at + timedelta(minutes=15)
        completed_at = started_at + timedelta(hours=2)

        # Mission item
        mission_item = {
            "userId": USER_ID,
            "missionId": mission_id,
            "campaignId": CAMPAIGN_ID,
            "title": mission_data["title"],
            "description": mission_data["description"],
            "status": "completed",
            "category": mission_data["category"],
            "difficulty": mission_data["difficulty"],
            "skillTags": mission_data["skillTags"],
            "assignedAt": assigned_at.isoformat(),
            "startedAt": started_at.isoformat(),
            "completedAt": completed_at.isoformat(),
            "completedDate": completed_at.isoformat(),
            "evidenceId": evidence_id,
            "evidenceIds": [evidence_id],
        }
        missions_table.put_item(Item=mission_item)
        created_missions += 1

        # Evidence item
        primary_skill = mission_data["skillTags"][0]
        unique_skills.add(primary_skill)
        evidence_item = {
            "userId": USER_ID,
            "evidenceId": evidence_id,
            "missionId": mission_id,
            "skillTag": primary_skill,
            "reflection": mission_data["reflection"],
            "createdAt": completed_at.isoformat(),
            "wordCount": len(mission_data["reflection"].split()),
        }
        if "artifactUrl" in mission_data:
            evidence_item["artifactUrl"] = mission_data["artifactUrl"]
        evidence_table.put_item(Item=evidence_item)
        created_evidence += 1

        print(f"  Day {day:2d} | {mission_data['category']:15s} | {mission_data['title'][:60]}")

    # 3. Update campaign difficulty state
    difficulty_state = {
        "levels": {
            "reflection": 2,
            "skill_building": 2,
            "portfolio": 1,
            "networking": 2,
            "market_research": 2,
        },
        "consecutive_completions": {
            "reflection": 3,
            "skill_building": 3,
            "portfolio": 1,
            "networking": 2,
            "market_research": 2,
        },
        "consecutive_skips": {
            "reflection": 0,
            "skill_building": 0,
            "portfolio": 0,
            "networking": 0,
            "market_research": 0,
        },
        "last_advancement_dates": {},
    }

    campaigns_table.update_item(
        Key={"userId": USER_ID, "campaignId": CAMPAIGN_ID},
        UpdateExpression="SET difficultyState = :ds",
        ExpressionAttributeValues={":ds": difficulty_state},
    )

    print(f"\nSeeded {created_missions} completed missions")
    print(f"Seeded {created_evidence} evidence items")
    print(f"Unique skills covered: {len(unique_skills)} ({', '.join(sorted(unique_skills))})")
    print(f"Categories covered: reflection, skill_building, portfolio, networking, market_research")
    print(f"\nFoundation -> Expansion gate requires 10 completed missions, 3 categories, 8 unique skills.")
    print(f"Current: {created_missions} missions, 5 categories, {len(unique_skills)} unique skills.")
    print(f"Phase gate: {'MET' if created_missions >= 10 and len(unique_skills) >= 8 else 'NOT YET MET'}")
    print("\nDone.")


if __name__ == "__main__":
    main()
