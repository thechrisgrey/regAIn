"""Skill taxonomy for the REGAIN Market Intelligence System.

Defines ~200 canonical skills organized into five categories, with alias
mappings from O*NET codes, job posting variants, and natural-language user
descriptions.  A reverse-lookup ``ALIAS_INDEX`` is built at module load
time for O(1) case-insensitive normalization.

The taxonomy is a static Python data structure that deploys with the
Lambda code — no DynamoDB table required.
"""

from __future__ import annotations

import importlib
import json
from typing import Optional

# 'lambda' is a Python keyword, so we use importlib to load the module.
_models_mod = importlib.import_module("backend.handlers.market_intel.models")
CanonicalSkill = _models_mod.CanonicalSkill


# ---------------------------------------------------------------------------
# Taxonomy definition — ~200 skills across 5 categories
# Each skill has UNIQUE onet_codes, job_posting_aliases, and user_aliases
# to ensure deterministic alias → canonical name resolution.
# ---------------------------------------------------------------------------

TAXONOMY: dict[str, CanonicalSkill] = {}


def _add(name: str, category: str, onet_codes: list[str],
         job_posting_aliases: list[str], user_aliases: list[str]) -> None:
    """Register a canonical skill in the taxonomy."""
    TAXONOMY[name] = CanonicalSkill(
        name=name,
        category=category,
        onet_codes=onet_codes,
        job_posting_aliases=job_posting_aliases,
        user_aliases=user_aliases,
    )


# ===== TECHNICAL (~54 skills) ==============================================

_add("Python Programming", "technical",
     ["2.A.1.f.1"],
     ["python", "python developer", "python3", "python programming"],
     ["I code in python", "python scripting", "wrote python scripts"])

_add("Java Programming", "technical",
     ["2.A.1.f.2"],
     ["java", "java developer", "java programming", "j2ee"],
     ["I code in java", "java development", "built java apps"])

_add("JavaScript", "technical",
     ["2.A.1.f.3"],
     ["javascript", "js", "ecmascript", "javascript developer"],
     ["I know javascript", "wrote javascript", "js coding"])

_add("TypeScript", "technical",
     ["2.A.1.f.4"],
     ["typescript", "ts", "typescript developer"],
     ["I use typescript", "wrote typescript code", "ts development"])

_add("SQL", "technical",
     ["2.A.1.f.5"],
     ["sql", "structured query language", "sql developer", "sql programming"],
     ["I write sql queries", "database queries", "sql scripting"])

_add("Cloud Computing", "technical",
     ["2.B.3.a.1"],
     ["cloud computing", "cloud infrastructure", "cloud services", "cloud platforms"],
     ["I work with cloud", "cloud experience", "managed cloud infrastructure"])

_add("AWS", "technical",
     ["2.B.3.a.2"],
     ["aws", "amazon web services", "aws cloud", "aws services"],
     ["I use aws", "worked with aws", "aws experience"])

_add("Azure", "technical",
     ["2.B.3.a.3"],
     ["azure", "microsoft azure", "azure cloud"],
     ["I use azure", "worked with azure", "azure experience"])

_add("Machine Learning", "technical",
     ["2.A.1.e.1"],
     ["machine learning", "ml", "ml engineer", "machine learning engineer"],
     ["I do machine learning", "built ml models", "ml experience"])

_add("Deep Learning", "technical",
     ["2.A.1.e.2"],
     ["deep learning", "neural networks", "dl", "deep neural networks"],
     ["I work with deep learning", "trained neural nets", "dl models"])

_add("Natural Language Processing", "technical",
     ["2.A.1.e.3"],
     ["nlp", "natural language processing", "text analytics", "nlp engineer"],
     ["I do nlp", "text processing", "language models"])

_add("Computer Vision", "technical",
     ["2.A.1.e.4"],
     ["computer vision", "cv", "image recognition", "image processing"],
     ["I work with computer vision", "image analysis", "cv models"])

_add("Test Automation", "technical",
     ["2.B.3.e.1"],
     ["test automation", "automated testing", "qa automation", "automation engineer"],
     ["I automate tests", "wrote automated tests", "test automation experience"])

_add("Quality Assurance", "technical",
     ["2.B.3.e.2"],
     ["quality assurance", "qa", "qa engineer", "quality engineering", "sdet"],
     ["I did testing", "qa lead", "quality assurance work"])

_add("CI/CD", "technical",
     ["2.B.3.a.4"],
     ["ci/cd", "continuous integration", "continuous delivery", "cicd", "devops pipeline"],
     ["I set up ci/cd", "build pipelines", "continuous deployment"])

_add("DevOps", "technical",
     ["2.B.3.a.5"],
     ["devops", "devops engineer", "site reliability", "sre"],
     ["I do devops", "infrastructure automation", "devops practices"])

_add("Docker", "technical",
     ["2.B.3.a.6"],
     ["docker", "containerization", "docker containers"],
     ["I use docker", "containerized apps", "docker experience"])

_add("Kubernetes", "technical",
     ["2.B.3.a.7"],
     ["kubernetes", "k8s", "container orchestration", "kubernetes engineer"],
     ["I manage kubernetes", "k8s clusters", "kubernetes experience"])

_add("API Development", "technical",
     ["2.B.3.a.8"],
     ["api development", "rest api", "api design", "restful services", "api engineer"],
     ["I build apis", "designed rest apis", "api development experience"])

_add("API Testing", "technical",
     ["2.B.3.e.3"],
     ["api testing", "api test automation", "postman", "api validation"],
     ["I test apis", "api testing experience", "tested rest endpoints"])

_add("Performance Testing", "technical",
     ["2.B.3.e.4"],
     ["performance testing", "load testing", "stress testing", "performance engineer"],
     ["I do performance testing", "load tested systems", "perf testing"])

_add("Security Testing", "technical",
     ["2.B.3.e.5"],
     ["security testing", "penetration testing", "security assessment", "appsec"],
     ["I do security testing", "pen testing", "security assessments"])

_add("Database Administration", "technical",
     ["2.B.3.k.1"],
     ["database administration", "dba", "database management", "db admin"],
     ["I manage databases", "dba work", "database admin experience"])

_add("Linux Administration", "technical",
     ["2.B.3.a.9"],
     ["linux", "linux administration", "linux sysadmin", "unix"],
     ["I manage linux servers", "linux admin", "unix experience"])

_add("Networking", "technical",
     ["4.A.3.b.1"],
     ["networking", "network engineering", "network administration", "tcp/ip"],
     ["I do networking", "network setup", "managed networks"])

_add("Cybersecurity", "technical",
     ["2.B.3.a.10"],
     ["cybersecurity", "information security", "infosec", "cyber security"],
     ["I work in cybersecurity", "infosec experience", "cybersecurity work"])

_add("Version Control", "technical",
     ["2.B.3.a.11"],
     ["version control", "git", "github", "source control"],
     ["I use git", "version control experience", "github workflow"])

_add("Agile Methodologies", "technical",
     ["4.A.2.b.1"],
     ["agile", "scrum methodology", "agile methodologies", "agile development"],
     ["I work in agile", "scrum experience", "agile teams"])

_add("Software Architecture", "technical",
     ["2.B.3.a.12"],
     ["software architecture", "system design", "solution architecture", "architect"],
     ["I design systems", "architecture experience", "system architecture"])

_add("Data Engineering", "technical",
     ["2.B.3.a.13"],
     ["data engineering", "data pipelines", "data engineer", "data infrastructure"],
     ["I build data pipelines", "data engineering work", "data infrastructure"])

_add("Web Development", "technical",
     ["2.B.3.a.14"],
     ["web development", "web developer", "frontend development", "full stack"],
     ["I build websites", "web dev", "frontend work"])

_add("Mobile Development", "technical",
     ["2.B.3.a.15"],
     ["mobile development", "mobile developer", "ios developer", "android developer"],
     ["I build mobile apps", "mobile dev", "app development"])

_add("React", "technical",
     ["2.B.3.a.16"],
     ["react", "reactjs", "react developer", "react.js"],
     ["I use react", "built react apps", "react experience"])

_add("Node.js", "technical",
     ["2.B.3.a.17"],
     ["node.js", "nodejs", "node developer", "node backend"],
     ["I use node.js", "built node apps", "nodejs experience"])

_add("AI/ML Operations", "technical",
     ["2.B.3.a.18"],
     ["mlops", "ai ops", "ml operations", "model deployment"],
     ["I do mlops", "deployed ml models", "ml operations"])

_add("Prompt Engineering", "technical",
     ["2.B.3.a.19"],
     ["prompt engineering", "llm prompting", "ai prompting"],
     ["I write prompts", "prompt design", "llm prompt engineering"])

_add("AI Quality Assurance", "technical",
     ["2.B.3.e.6"],
     ["ai qa", "ai quality assurance", "ml testing", "ai testing"],
     ["I test ai systems", "ai quality work", "ml model testing"])

_add("Robotic Process Automation", "technical",
     ["2.B.3.a.20"],
     ["rpa", "robotic process automation", "automation developer"],
     ["I build rpa bots", "rpa development", "process automation bots"])

_add("Embedded Systems", "technical",
     ["2.B.3.a.21"],
     ["embedded systems", "firmware", "embedded software", "iot development"],
     ["I work with embedded systems", "firmware development", "iot devices"])

_add("Data Warehousing", "technical",
     ["2.B.3.k.2"],
     ["data warehousing", "data warehouse", "dwh", "data lake"],
     ["I manage data warehouses", "dwh experience", "data lake work"])

_add("ERP Systems", "technical",
     ["2.B.3.k.3"],
     ["erp", "enterprise resource planning", "sap", "oracle erp"],
     ["I work with erp", "sap experience", "erp implementation"])

_add("CRM Systems", "technical",
     ["2.B.3.k.4"],
     ["crm", "salesforce", "customer relationship management", "hubspot"],
     ["I use crm systems", "salesforce admin", "crm experience"])

_add("Business Intelligence Tools", "technical",
     ["2.B.3.k.5"],
     ["bi tools", "business intelligence", "bi platforms", "bi development"],
     ["I build bi dashboards", "bi reporting", "business intelligence work"])

_add("Spreadsheet Software", "technical",
     ["2.B.3.k.6"],
     ["excel", "google sheets", "spreadsheet", "advanced excel"],
     ["I use excel", "spreadsheet expert", "excel formulas"])

_add("R Programming", "technical",
     ["2.A.1.f.6"],
     ["r programming", "r language", "r statistical", "rstudio"],
     ["I use r", "r programming", "statistical computing in r"])

_add("Power BI", "technical",
     ["2.B.3.k.7"],
     ["power bi", "powerbi", "power bi developer", "microsoft power bi"],
     ["I use power bi", "power bi dashboards", "powerbi reports"])

_add("Tableau", "technical",
     ["2.B.3.k.8"],
     ["tableau", "tableau developer", "tableau desktop", "tableau server"],
     ["I use tableau", "tableau dashboards", "tableau visualization"])

_add("Selenium", "technical",
     ["2.B.3.e.7"],
     ["selenium", "selenium webdriver", "selenium automation", "selenium testing"],
     ["I use selenium", "selenium test scripts", "browser automation"])

_add("Terraform", "technical",
     ["2.B.3.a.22"],
     ["terraform", "infrastructure as code", "terraform developer", "hashicorp terraform"],
     ["I use terraform", "terraform configs", "iac experience"])

_add("Data Modeling", "technical",
     ["2.B.3.k.9"],
     ["data modeling", "database design", "er diagrams", "schema design"],
     ["I do data modeling", "database design work", "schema design work"])

_add("ETL Development", "technical",
     ["2.B.3.k.10"],
     ["etl", "etl development", "data extraction", "data transformation"],
     ["I build etl pipelines", "etl processes", "data extraction work"])

_add("SAS", "technical",
     ["2.A.1.f.7"],
     ["sas", "sas programming", "sas analytics", "sas enterprise"],
     ["I use sas", "sas programming work", "sas analytics work"])

_add("JIRA", "technical",
     ["2.B.3.k.11"],
     ["jira", "jira administration", "atlassian jira", "jira project tracking"],
     ["I use jira", "jira boards", "jira administration"])

_add("Confluence", "technical",
     ["2.B.3.k.12"],
     ["confluence", "atlassian confluence", "wiki management", "confluence documentation"],
     ["I use confluence", "confluence pages", "wiki documentation"])

# ===== ANALYTICAL (~34 skills) =============================================

_add("Data Analysis", "analytical",
     ["2.A.2.a.1"],
     ["data analysis", "data analyst", "data analytics", "analytical skills"],
     ["I analyze data", "data analysis work", "analytical experience"])

_add("Statistical Analysis", "analytical",
     ["2.A.1.e.5"],
     ["statistical analysis", "statistics", "statistical modeling", "biostatistics"],
     ["I do statistics", "statistical work", "stats analysis"])

_add("Data Visualization", "analytical",
     ["2.B.4.g.1"],
     ["data visualization", "data viz", "visualization", "charting"],
     ["I create visualizations", "data viz work", "built dashboards"])

_add("Financial Analysis", "analytical",
     ["2.B.1.b.1"],
     ["financial analysis", "financial analyst", "financial modeling", "financial planning"],
     ["I analyze financials", "financial modeling work", "finance analysis"])

_add("Market Research", "analytical",
     ["2.B.4.g.2"],
     ["market research", "market analysis", "competitive intelligence", "market researcher"],
     ["I do market research", "market studies", "competitive research"])

_add("Business Analysis", "analytical",
     ["2.A.2.a.2"],
     ["business analysis", "business analyst", "ba", "requirements analysis"],
     ["I do business analysis", "gathered requirements", "ba work"])

_add("Quantitative Analysis", "analytical",
     ["2.A.1.e.6"],
     ["quantitative analysis", "quant", "quantitative methods", "numerical analysis"],
     ["I do quantitative work", "quant analysis", "numerical methods"])

_add("Risk Assessment", "analytical",
     ["2.A.2.a.3"],
     ["risk assessment", "risk analysis", "risk evaluation", "risk scoring"],
     ["I assess risks", "risk analysis work", "risk evaluation work"])

_add("Process Improvement", "analytical",
     ["2.A.2.a.4"],
     ["process improvement", "process optimization", "lean", "six sigma"],
     ["I improve processes", "lean six sigma", "process optimization"])

_add("Root Cause Analysis", "analytical",
     ["2.A.2.a.5"],
     ["root cause analysis", "rca", "problem analysis", "failure analysis"],
     ["I do root cause analysis", "rca investigations", "problem solving"])

_add("Forecasting", "analytical",
     ["2.A.1.e.7"],
     ["forecasting", "demand forecasting", "predictive analytics", "trend forecasting"],
     ["I do forecasting", "demand planning work", "predictive analysis"])

_add("Cost Analysis", "analytical",
     ["2.B.1.b.2"],
     ["cost analysis", "cost estimation", "cost-benefit analysis", "cost modeling"],
     ["I analyze costs", "cost estimation work", "cost-benefit studies"])

_add("Reporting", "analytical",
     ["2.B.4.g.3"],
     ["reporting", "business reporting", "analytics reporting", "management reporting"],
     ["I create reports", "reporting experience", "business reports"])

_add("KPI Development", "analytical",
     ["2.B.4.g.4"],
     ["kpi development", "kpi tracking", "metrics development", "performance metrics"],
     ["I define kpis", "metrics tracking", "kpi dashboards"])

_add("Supply Chain Analysis", "analytical",
     ["2.A.2.a.6"],
     ["supply chain analysis", "supply chain analytics", "logistics analysis"],
     ["I analyze supply chains", "logistics analytics", "supply chain work"])

_add("Route Optimization", "analytical",
     ["2.A.2.a.7"],
     ["route optimization", "route planning", "logistics optimization", "fleet routing"],
     ["I optimize routes", "route planning work", "logistics routing"])

_add("Inventory Analysis", "analytical",
     ["2.A.2.a.8"],
     ["inventory analysis", "inventory management analytics", "stock analysis", "inventory optimization"],
     ["I analyze inventory", "stock management work", "inventory analysis work"])

_add("Compliance Analysis", "analytical",
     ["2.A.2.a.9"],
     ["compliance analysis", "regulatory analysis", "compliance review", "audit analysis"],
     ["I do compliance reviews", "regulatory analysis work", "audit work"])

_add("Trend Analysis", "analytical",
     ["2.B.4.g.5"],
     ["trend analysis", "trend identification", "pattern recognition", "market trends"],
     ["I identify trends", "trend analysis work", "pattern analysis"])

_add("Operations Research", "analytical",
     ["2.A.1.e.8"],
     ["operations research", "optimization modeling", "mathematical modeling", "or analysis"],
     ["I do operations research", "optimization work", "mathematical modeling"])

_add("Quality Metrics", "analytical",
     ["2.B.4.g.6"],
     ["quality metrics", "quality analysis", "defect analysis", "quality reporting"],
     ["I track quality metrics", "defect analysis", "quality reporting"])

_add("Budgeting", "analytical",
     ["2.B.1.b.3"],
     ["budgeting", "budget planning", "budget analysis", "fiscal planning"],
     ["I plan budgets", "budget planning work", "budgeting experience"])

_add("Audit", "analytical",
     ["2.B.1.b.4"],
     ["audit", "auditing", "internal audit", "financial audit"],
     ["I conduct audits", "audit experience", "auditing work"])

_add("Tax Analysis", "analytical",
     ["2.B.1.b.5"],
     ["tax analysis", "tax preparation", "tax planning", "tax compliance"],
     ["I do tax work", "tax preparation", "tax analysis work"])

_add("Workforce Analytics", "analytical",
     ["2.B.4.g.7"],
     ["workforce analytics", "people analytics", "hr analytics", "talent analytics"],
     ["I analyze workforce data", "people analytics", "hr metrics"])

_add("Regression Analysis", "analytical",
     ["2.A.1.e.9"],
     ["regression analysis", "regression modeling", "linear regression", "logistic regression"],
     ["I do regression analysis", "regression models", "statistical regression"])

_add("A/B Testing", "analytical",
     ["2.B.4.g.8"],
     ["a/b testing", "split testing", "experimentation", "controlled experiments"],
     ["I run a/b tests", "experimentation work", "split testing"])

_add("Survey Analysis", "analytical",
     ["2.B.4.g.9"],
     ["survey analysis", "survey design", "questionnaire analysis", "survey research"],
     ["I analyze surveys", "survey design work", "questionnaire work"])

_add("Geospatial Analysis", "analytical",
     ["2.B.4.g.10"],
     ["geospatial analysis", "gis", "geographic analysis", "spatial analysis"],
     ["I do geospatial work", "gis analysis", "mapping analysis"])

_add("Capacity Planning", "analytical",
     ["2.A.2.a.10"],
     ["capacity planning", "capacity management", "demand capacity planning"],
     ["I do capacity planning", "capacity management work", "demand capacity work"])

_add("Predictive Modeling", "analytical",
     ["2.A.1.e.10"],
     ["predictive modeling", "prediction models", "forecasting models", "predictive algorithms"],
     ["I build predictive models", "prediction modeling", "forecasting model work"])

_add("Data Cleaning", "analytical",
     ["2.B.4.g.11"],
     ["data cleaning", "data wrangling", "data preparation", "data quality"],
     ["I clean data", "data wrangling work", "data preparation work"])

_add("Benchmarking", "analytical",
     ["2.A.2.a.11"],
     ["benchmarking", "competitive benchmarking", "performance benchmarking", "industry benchmarks"],
     ["I do benchmarking", "competitive benchmarking work", "performance benchmarks"])

_add("Gap Analysis", "analytical",
     ["2.A.2.a.12"],
     ["gap analysis", "needs assessment", "skills gap analysis", "gap identification"],
     ["I do gap analysis", "needs assessment work", "skills gap work"])

# ===== COMMUNICATION (~29 skills) ==========================================

_add("Technical Writing", "communication",
     ["2.A.1.a.1"],
     ["technical writing", "technical writer", "documentation", "tech writing"],
     ["I write technical docs", "documentation work", "technical writing experience"])

_add("Public Speaking", "communication",
     ["2.A.1.a.2"],
     ["public speaking", "presentations", "keynote speaker", "public presenter"],
     ["I give presentations", "public speaking experience", "presented at conferences"])

_add("Client Communication", "communication",
     ["2.A.1.a.3"],
     ["client communication", "client relations", "client management", "client facing"],
     ["I talk to clients", "client relationships", "client-facing work"])

_add("Stakeholder Management", "communication",
     ["4.A.4.a.1"],
     ["stakeholder management", "stakeholder engagement", "stakeholder communication"],
     ["I manage stakeholders", "stakeholder engagement work", "stakeholder relations"])

_add("Report Writing", "communication",
     ["2.B.4.a.1"],
     ["report writing", "business writing", "written communication", "report generation"],
     ["I write reports", "business writing experience", "written communication"])

_add("Cross-Functional Collaboration", "communication",
     ["4.A.4.a.2"],
     ["cross-functional collaboration", "cross-team collaboration", "interdepartmental"],
     ["I work across teams", "cross-functional work", "interdepartmental collaboration"])

_add("Negotiation", "communication",
     ["4.A.4.b.1"],
     ["negotiation", "deal negotiation", "negotiation skills", "negotiator"],
     ["I negotiate deals", "negotiation experience", "deal-making"])

_add("Customer Service", "communication",
     ["4.A.4.a.3"],
     ["customer service", "customer support", "client support", "customer care"],
     ["I help customers", "customer support work", "customer service experience"])

_add("Conflict Resolution", "communication",
     ["4.A.4.b.2"],
     ["conflict resolution", "dispute resolution", "mediation", "conflict management"],
     ["I resolve conflicts", "mediation experience", "conflict management work"])

_add("Training Delivery", "communication",
     ["2.A.1.a.4"],
     ["training delivery", "training facilitation", "instructor", "corporate training"],
     ["I deliver training", "taught classes", "training facilitation"])

_add("Sales Communication", "communication",
     ["4.A.4.b.3"],
     ["sales communication", "sales pitch", "sales presentations", "consultative selling"],
     ["I do sales pitches", "sales presentations", "selling experience"])

_add("Email Communication", "communication",
     ["2.A.1.a.5"],
     ["email communication", "professional email", "business correspondence"],
     ["I write professional emails", "email correspondence", "business emails"])

_add("Active Listening", "communication",
     ["2.A.1.a.6"],
     ["active listening", "listening skills", "empathetic listening"],
     ["I practice active listening", "good listener", "listening skills"])

_add("Interviewing", "communication",
     ["2.A.1.a.7"],
     ["interviewing", "interview skills", "behavioral interviewing", "candidate screening"],
     ["I conduct interviews", "interviewing experience", "candidate screening"])

_add("Persuasion", "communication",
     ["4.A.4.b.4"],
     ["persuasion", "influence", "persuasive communication", "influencing skills"],
     ["I persuade stakeholders", "influence others", "persuasive communication"])

_add("Bilingual Communication", "communication",
     ["2.A.1.a.8"],
     ["bilingual", "multilingual", "language skills", "translation"],
     ["I speak multiple languages", "bilingual skills", "translation work"])

_add("Meeting Facilitation", "communication",
     ["2.A.1.a.9"],
     ["meeting facilitation", "facilitator", "workshop facilitation", "meeting management"],
     ["I facilitate meetings", "workshop facilitation", "meeting management"])

_add("Feedback Delivery", "communication",
     ["2.A.1.a.10"],
     ["feedback delivery", "constructive feedback", "performance feedback", "coaching feedback"],
     ["I give feedback", "constructive criticism", "feedback experience"])

_add("Proposal Writing", "communication",
     ["2.B.4.a.2"],
     ["proposal writing", "rfp response", "business proposals", "grant writing"],
     ["I write proposals", "rfp responses", "business proposals"])

_add("Customer Onboarding", "communication",
     ["4.A.4.a.4"],
     ["customer onboarding", "client onboarding", "user onboarding", "onboarding specialist"],
     ["I onboard customers", "client onboarding work", "onboarding experience"])

_add("Account Management", "communication",
     ["4.A.4.a.5"],
     ["account management", "account manager", "key account management", "client account"],
     ["I manage accounts", "account management work", "key accounts"])

_add("Customer Success", "communication",
     ["4.A.4.a.6"],
     ["customer success", "customer success manager", "csm", "client success"],
     ["I do customer success", "csm work", "client success work"])

_add("Upselling", "communication",
     ["4.A.4.b.5"],
     ["upselling", "cross-selling", "revenue expansion", "upsell"],
     ["I upsell products", "cross-selling work", "revenue growth"])

_add("Empathy", "communication",
     ["2.A.1.a.11"],
     ["empathy", "emotional intelligence", "eq", "empathetic communication"],
     ["I show empathy", "emotional intelligence", "empathetic approach"])

_add("Briefing", "communication",
     ["2.A.1.a.12"],
     ["briefing", "military briefing", "situation report", "sitrep"],
     ["I give briefings", "situation reports", "military briefings"])

_add("Crisis Communication", "communication",
     ["2.A.1.a.13"],
     ["crisis communication", "crisis comms", "emergency communication", "crisis messaging"],
     ["I handle crisis comms", "emergency communication work", "crisis messaging"])

_add("Social Media Communication", "communication",
     ["2.B.4.a.3"],
     ["social media", "social media management", "social media marketing", "content creation"],
     ["I manage social media", "social media content", "online presence"])

_add("Presentation Design", "communication",
     ["2.B.4.a.4"],
     ["presentation design", "slide design", "powerpoint", "keynote presentations"],
     ["I design presentations", "slide decks", "powerpoint presentations"])

_add("Storytelling", "communication",
     ["2.A.1.a.14"],
     ["storytelling", "narrative building", "business storytelling", "data storytelling"],
     ["I tell stories with data", "narrative building", "business storytelling"])

# ===== LEADERSHIP (~32 skills) =============================================

_add("Project Management", "leadership",
     ["4.A.2.b.2"],
     ["project management", "project manager", "pm", "pmp"],
     ["I manage projects", "project management experience", "pm work"])

_add("Team Leadership", "leadership",
     ["4.A.2.b.3"],
     ["team leadership", "team lead", "team management", "people management"],
     ["I lead teams", "team management work", "people leadership"])

_add("Strategic Planning", "leadership",
     ["4.A.2.b.4"],
     ["strategic planning", "strategy", "strategic management", "business strategy"],
     ["I do strategic planning", "strategy work", "strategic initiatives"])

_add("Change Management", "leadership",
     ["4.A.2.b.5"],
     ["change management", "organizational change", "transformation management"],
     ["I manage change", "change initiatives", "organizational transformation"])

_add("Operations Management", "leadership",
     ["4.A.2.b.6"],
     ["operations management", "operations manager", "ops management", "operational excellence"],
     ["I manage operations", "ops management work", "operational leadership"])

_add("Resource Allocation", "leadership",
     ["4.A.2.b.7"],
     ["resource allocation", "resource management", "resource planning", "capacity allocation"],
     ["I allocate resources", "resource management work", "resource planning work"])

_add("Risk Management", "leadership",
     ["4.A.2.b.8"],
     ["risk management", "risk mitigation", "enterprise risk", "risk officer"],
     ["I manage risks", "risk mitigation work", "enterprise risk management"])

_add("Decision Making", "leadership",
     ["4.A.2.b.9"],
     ["decision making", "executive decision making", "strategic decisions"],
     ["I make decisions", "decision-making skills", "strategic decisions"])

_add("Mentoring", "leadership",
     ["4.A.4.a.7"],
     ["mentoring", "coaching", "mentorship", "employee development"],
     ["I mentor people", "coaching others", "mentorship experience"])

_add("Performance Management", "leadership",
     ["4.A.2.b.10"],
     ["performance management", "performance reviews", "employee evaluation", "performance tracking"],
     ["I manage performance", "performance review work", "employee evaluations"])

_add("Budget Management", "leadership",
     ["4.A.2.b.11"],
     ["budget management", "financial management", "budget oversight", "fiscal management"],
     ["I manage department budgets", "financial oversight", "budget responsibility"])

_add("Vendor Management", "leadership",
     ["4.A.2.b.12"],
     ["vendor management", "supplier management", "third-party management", "vendor relations"],
     ["I manage vendors", "supplier relationships", "vendor oversight"])

_add("Program Management", "leadership",
     ["4.A.2.b.13"],
     ["program management", "program manager", "pgm", "portfolio management"],
     ["I manage programs", "program management work", "portfolio oversight"])

_add("Scrum Master", "leadership",
     ["4.A.2.b.14"],
     ["scrum master", "agile coach", "scrum facilitator", "certified scrum master"],
     ["I am a scrum master", "agile coaching work", "scrum facilitation"])

_add("Product Management", "leadership",
     ["4.A.2.b.15"],
     ["product management", "product manager", "product owner", "product strategy"],
     ["I manage products", "product ownership", "product strategy work"])

_add("Mission Planning", "leadership",
     ["4.A.2.b.16"],
     ["mission planning", "operational planning", "tactical planning", "mission commander"],
     ["I plan missions", "operational planning work", "tactical leadership"])

_add("Crisis Management", "leadership",
     ["4.A.2.b.17"],
     ["crisis management", "emergency management", "incident management", "crisis response"],
     ["I handle crises", "emergency response work", "crisis management work"])

_add("Delegation", "leadership",
     ["4.A.2.b.18"],
     ["delegation", "task delegation", "work delegation", "empowerment"],
     ["I delegate tasks", "delegation skills", "empowering teams"])

_add("Workforce Planning", "leadership",
     ["4.A.2.b.19"],
     ["workforce planning", "staffing", "talent planning", "headcount planning"],
     ["I plan workforce needs", "staffing decisions", "talent planning"])

_add("Quality Management", "leadership",
     ["4.A.2.b.20"],
     ["quality management", "quality control", "qms", "total quality management"],
     ["I manage quality", "quality control work", "tqm experience"])

_add("Logistics Management", "leadership",
     ["4.A.2.b.21"],
     ["logistics management", "logistics coordinator", "supply chain management", "logistics leadership"],
     ["I manage logistics", "logistics coordination", "supply chain leadership"])

_add("Fleet Management", "leadership",
     ["4.A.2.b.22"],
     ["fleet management", "fleet operations", "vehicle management", "fleet coordinator"],
     ["I manage fleets", "fleet operations work", "vehicle fleet management"])

_add("Safety Management", "leadership",
     ["4.A.2.b.23"],
     ["safety management", "safety officer", "osha compliance", "workplace safety management"],
     ["I manage safety programs", "safety compliance work", "osha management"])

_add("Continuous Improvement", "leadership",
     ["4.A.2.b.24"],
     ["continuous improvement", "kaizen", "process excellence", "ci methodology"],
     ["I drive continuous improvement", "kaizen practices", "process excellence"])

_add("Stakeholder Alignment", "leadership",
     ["4.A.2.b.25"],
     ["stakeholder alignment", "executive alignment", "organizational alignment"],
     ["I align stakeholders", "executive buy-in", "organizational alignment"])

_add("Succession Planning", "leadership",
     ["4.A.2.b.26"],
     ["succession planning", "talent pipeline", "leadership development", "succession management"],
     ["I do succession planning", "talent pipeline work", "leadership development"])

_add("Regulatory Compliance", "leadership",
     ["4.A.2.b.27"],
     ["regulatory compliance", "compliance management", "regulatory affairs", "compliance officer"],
     ["I ensure compliance", "regulatory management", "compliance oversight"])

_add("Contract Management", "leadership",
     ["4.A.2.b.28"],
     ["contract management", "contract administration", "contract negotiation", "procurement management"],
     ["I manage contracts", "contract administration work", "procurement work"])

_add("Incident Command", "leadership",
     ["4.A.2.b.29"],
     ["incident command", "incident commander", "ics", "incident management system"],
     ["I command incidents", "incident response work", "ics experience"])

_add("Cross-Cultural Leadership", "leadership",
     ["4.A.2.b.30"],
     ["cross-cultural leadership", "diversity leadership", "multicultural management", "global leadership"],
     ["I lead diverse teams", "cross-cultural work", "multicultural leadership"])

_add("Lean Management", "leadership",
     ["4.A.2.b.31"],
     ["lean management", "lean manufacturing", "lean principles", "waste reduction"],
     ["I apply lean principles", "lean management work", "waste reduction"])

_add("Talent Acquisition", "leadership",
     ["4.A.2.b.32"],
     ["talent acquisition", "recruiting", "hiring", "talent sourcing"],
     ["I recruit talent", "hiring experience", "talent acquisition work"])

# ===== DOMAIN_SPECIFIC (~49 skills) ========================================

_add("Accounting", "domain_specific",
     ["2.B.1.b.6"],
     ["accounting", "accountant", "bookkeeping", "general ledger"],
     ["I do accounting", "bookkeeping work", "accounting experience"])

_add("Financial Reporting", "domain_specific",
     ["2.B.1.b.7"],
     ["financial reporting", "financial statements", "gaap reporting", "sec reporting"],
     ["I prepare financial reports", "financial statements work", "gaap compliance"])

_add("Accounts Payable/Receivable", "domain_specific",
     ["2.B.1.b.8"],
     ["accounts payable", "accounts receivable", "ap/ar", "billing"],
     ["I manage ap/ar", "billing work", "accounts payable work"])

_add("Payroll Processing", "domain_specific",
     ["2.B.1.b.9"],
     ["payroll", "payroll processing", "payroll management", "payroll administration"],
     ["I process payroll", "payroll management work", "payroll experience"])

_add("Retail Operations", "domain_specific",
     ["4.A.1.a.1"],
     ["retail operations", "retail management", "store operations", "retail"],
     ["I manage retail stores", "store operations work", "retail experience"])

_add("Merchandising", "domain_specific",
     ["4.A.1.a.2"],
     ["merchandising", "visual merchandising", "product merchandising", "planogram"],
     ["I do merchandising", "visual displays", "product placement"])

_add("Point of Sale Systems", "domain_specific",
     ["2.B.3.k.13"],
     ["pos systems", "point of sale", "pos", "register systems"],
     ["I use pos systems", "register operations", "point of sale work"])

_add("Loss Prevention", "domain_specific",
     ["4.A.1.a.3"],
     ["loss prevention", "asset protection", "shrinkage control", "lp"],
     ["I do loss prevention", "asset protection work", "shrinkage management"])

_add("Transportation Regulations", "domain_specific",
     ["2.B.1.b.10"],
     ["dot regulations", "transportation regulations", "fmcsa", "cdl regulations"],
     ["I know dot regulations", "transportation compliance", "cdl requirements"])

_add("Vehicle Maintenance", "domain_specific",
     ["4.A.3.a.1"],
     ["vehicle maintenance", "fleet maintenance", "preventive maintenance", "vehicle inspection"],
     ["I maintain vehicles", "fleet maintenance work", "vehicle inspections"])

_add("Hazmat Handling", "domain_specific",
     ["2.B.1.b.11"],
     ["hazmat", "hazardous materials", "hazmat handling", "dangerous goods"],
     ["I handle hazmat", "hazardous materials work", "dangerous goods handling"])

_add("GPS/Navigation Systems", "domain_specific",
     ["2.B.3.k.14"],
     ["gps", "navigation systems", "gps tracking", "fleet tracking"],
     ["I use gps systems", "navigation experience", "fleet tracking work"])

_add("Warehouse Management", "domain_specific",
     ["4.A.1.a.4"],
     ["warehouse management", "wms", "warehouse operations", "distribution center"],
     ["I manage warehouses", "warehouse operations work", "distribution work"])

_add("Military Operations", "domain_specific",
     ["4.A.2.b.33"],
     ["military operations", "combat operations", "tactical operations", "military service"],
     ["I served in military", "combat experience", "military operations work"])

_add("Physical Security", "domain_specific",
     ["4.A.1.a.5"],
     ["physical security", "security operations", "force protection", "security management"],
     ["I manage physical security", "force protection work", "security operations work"])

_add("Weapons Systems", "domain_specific",
     ["4.A.3.a.2"],
     ["weapons systems", "weapons qualification", "marksmanship", "armament"],
     ["I qualified on weapons", "marksmanship training", "weapons training"])

_add("First Aid/Medical", "domain_specific",
     ["2.B.1.b.12"],
     ["first aid", "combat medic", "emergency medical", "cpr certified"],
     ["I know first aid", "medical training", "emergency medical work"])

_add("Intelligence Analysis", "domain_specific",
     ["2.A.2.a.13"],
     ["intelligence analysis", "intel analysis", "threat assessment", "intelligence gathering"],
     ["I analyze intelligence", "threat assessment work", "intel work"])

_add("Customer Retention", "domain_specific",
     ["4.A.4.a.8"],
     ["customer retention", "churn reduction", "retention strategy", "customer loyalty"],
     ["I improve retention", "churn reduction work", "customer loyalty work"])

_add("SaaS Knowledge", "domain_specific",
     ["2.B.3.k.15"],
     ["saas", "software as a service", "saas platforms", "cloud software"],
     ["I work with saas", "saas experience", "cloud software work"])

_add("Onboarding Programs", "domain_specific",
     ["4.A.4.a.9"],
     ["onboarding programs", "employee onboarding", "new hire orientation", "onboarding design"],
     ["I design onboarding programs", "new hire programs", "onboarding design work"])

_add("Health and Safety", "domain_specific",
     ["2.B.1.b.13"],
     ["health and safety", "occupational health", "ehs", "workplace health"],
     ["I manage health and safety", "ehs compliance", "workplace health work"])

_add("Environmental Compliance", "domain_specific",
     ["2.B.1.b.14"],
     ["environmental compliance", "environmental regulations", "epa compliance", "sustainability"],
     ["I ensure environmental compliance", "epa regulations", "sustainability work"])

_add("Real Estate", "domain_specific",
     ["2.B.1.b.15"],
     ["real estate", "property management", "real estate analysis", "commercial real estate"],
     ["I work in real estate", "property management work", "real estate experience"])

_add("Healthcare Administration", "domain_specific",
     ["4.A.1.a.6"],
     ["healthcare administration", "health admin", "medical administration", "hospital management"],
     ["I work in healthcare admin", "medical administration work", "hospital management"])

_add("Insurance", "domain_specific",
     ["2.B.1.b.16"],
     ["insurance", "insurance analysis", "underwriting", "claims processing"],
     ["I work in insurance", "underwriting work", "claims processing work"])

_add("Manufacturing", "domain_specific",
     ["4.A.1.a.7"],
     ["manufacturing", "production management", "manufacturing operations", "plant operations"],
     ["I work in manufacturing", "production management work", "plant operations work"])

_add("Construction Management", "domain_specific",
     ["4.A.2.b.34"],
     ["construction management", "construction", "site management", "general contractor"],
     ["I manage construction", "site management work", "construction experience"])

_add("Telecommunications", "domain_specific",
     ["2.B.3.a.23"],
     ["telecommunications", "telecom", "radio communications", "signal systems"],
     ["I work in telecom", "radio communications work", "signal experience"])

_add("E-Commerce", "domain_specific",
     ["4.A.1.a.8"],
     ["e-commerce", "ecommerce", "online retail", "digital commerce"],
     ["I work in e-commerce", "online retail work", "ecommerce experience"])

_add("Digital Marketing", "domain_specific",
     ["2.B.4.a.5"],
     ["digital marketing", "online marketing", "seo", "sem"],
     ["I do digital marketing", "online marketing work", "seo work"])

_add("Human Resources", "domain_specific",
     ["4.A.4.a.10"],
     ["human resources", "hr", "hr management", "people operations"],
     ["I work in hr", "human resources work", "people operations work"])

_add("Procurement", "domain_specific",
     ["4.A.2.b.35"],
     ["procurement", "purchasing", "sourcing", "supply management"],
     ["I do procurement", "purchasing work", "sourcing experience"])

_add("Legal Compliance", "domain_specific",
     ["2.B.1.b.17"],
     ["legal compliance", "legal analysis", "regulatory law", "corporate law"],
     ["I handle legal compliance", "legal analysis work", "regulatory work"])

_add("Government Contracting", "domain_specific",
     ["4.A.2.b.36"],
     ["government contracting", "federal contracting", "govcon", "far/dfar"],
     ["I do government contracting", "federal contracts", "govcon experience"])

_add("Nonprofit Management", "domain_specific",
     ["4.A.2.b.37"],
     ["nonprofit management", "ngo management", "nonprofit operations", "charitable organizations"],
     ["I manage nonprofits", "ngo work", "nonprofit experience"])

_add("Education/Training Design", "domain_specific",
     ["2.B.4.a.6"],
     ["instructional design", "curriculum development", "training design", "learning design"],
     ["I design training programs", "curriculum development work", "instructional design work"])

_add("Technical Support", "domain_specific",
     ["4.A.4.a.11"],
     ["technical support", "tech support", "it support", "help desk"],
     ["I provide tech support", "help desk work", "it support work"])

_add("Data Privacy", "domain_specific",
     ["2.B.1.b.18"],
     ["data privacy", "gdpr", "data protection", "privacy compliance"],
     ["I handle data privacy", "gdpr compliance", "data protection work"])

_add("Freight Management", "domain_specific",
     ["4.A.1.a.9"],
     ["freight management", "freight logistics", "freight brokerage", "shipping management"],
     ["I manage freight", "freight logistics work", "shipping operations"])

_add("CDL Operations", "domain_specific",
     ["4.A.3.a.3"],
     ["cdl", "commercial driving", "cdl operations", "commercial driver"],
     ["I have a cdl", "commercial driving experience", "cdl experience"])

_add("Dispatch Operations", "domain_specific",
     ["4.A.1.a.10"],
     ["dispatch", "dispatch operations", "fleet dispatch", "logistics dispatch"],
     ["I do dispatch work", "fleet dispatch work", "dispatch operations work"])

_add("Customs/Import-Export", "domain_specific",
     ["2.B.1.b.19"],
     ["customs", "import export", "customs compliance", "trade compliance"],
     ["I handle customs", "import export work", "trade compliance work"])

_add("Customer Analytics", "domain_specific",
     ["2.B.4.g.12"],
     ["customer analytics", "customer insights", "customer data analysis", "customer segmentation"],
     ["I analyze customer data", "customer insights work", "customer segmentation work"])

_add("Revenue Operations", "domain_specific",
     ["4.A.1.a.11"],
     ["revenue operations", "revops", "revenue management", "revenue optimization"],
     ["I do revops", "revenue operations work", "revenue management work"])

_add("Veteran Transition", "domain_specific",
     ["4.A.4.a.12"],
     ["veteran transition", "military transition", "mos translation", "veteran employment"],
     ["I help veterans transition", "military to civilian", "mos translation work"])

_add("Career Coaching", "domain_specific",
     ["4.A.4.a.13"],
     ["career coaching", "career counseling", "career development", "career guidance"],
     ["I coach careers", "career counseling work", "career development work"])

_add("Inventory Control Systems", "domain_specific",
     ["2.B.3.k.16"],
     ["inventory control", "inventory systems", "stock control", "inventory tracking systems"],
     ["I manage inventory systems", "stock control work", "inventory tracking work"])

_add("Last Mile Delivery", "domain_specific",
     ["4.A.1.a.12"],
     ["last mile delivery", "last mile logistics", "delivery operations", "final mile"],
     ["I manage last mile", "delivery operations work", "last mile logistics work"])


# ---------------------------------------------------------------------------
# Build reverse-lookup index at module load time
# ---------------------------------------------------------------------------

ALIAS_INDEX: dict[str, str] = {}


def _build_alias_index() -> None:
    """Populate ALIAS_INDEX from all alias sources in TAXONOMY."""
    for skill in TAXONOMY.values():
        canonical = skill.name
        for alias in skill.onet_codes:
            ALIAS_INDEX[alias.lower()] = canonical
        for alias in skill.job_posting_aliases:
            ALIAS_INDEX[alias.lower()] = canonical
        for alias in skill.user_aliases:
            ALIAS_INDEX[alias.lower()] = canonical


_build_alias_index()


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def normalize_skill(skill_string: str) -> Optional[str]:
    """Normalize a skill string to its canonical name via alias lookup.

    Performs case-insensitive matching against all aliases in the taxonomy
    (O*NET codes, job posting variants, and user descriptions).

    Args:
        skill_string: Raw skill string from any source.

    Returns:
        Canonical skill name if matched, None otherwise.
    """
    return ALIAS_INDEX.get(skill_string.lower())


def get_canonical_skill(name: str) -> Optional[CanonicalSkill]:
    """Look up a CanonicalSkill by its canonical name.

    Args:
        name: Exact canonical skill name (case-sensitive).

    Returns:
        The CanonicalSkill dataclass instance, or None if not found.
    """
    return TAXONOMY.get(name)


def serialize_taxonomy() -> str:
    """Serialize the full taxonomy to a JSON string.

    Each skill is represented as a dict with name, category,
    onet_codes, job_posting_aliases, and user_aliases.

    Returns:
        JSON string of the taxonomy keyed by canonical name.
    """
    data: dict[str, dict] = {}
    for name, skill in TAXONOMY.items():
        data[name] = {
            "name": skill.name,
            "category": skill.category,
            "onet_codes": skill.onet_codes,
            "job_posting_aliases": skill.job_posting_aliases,
            "user_aliases": skill.user_aliases,
        }
    return json.dumps(data, indent=2)


def deserialize_taxonomy(json_str: str) -> dict[str, CanonicalSkill]:
    """Deserialize a JSON string into a dict of CanonicalSkill objects.

    Args:
        json_str: JSON string produced by ``serialize_taxonomy()``.

    Returns:
        Dict mapping canonical name to CanonicalSkill instances.
    """
    raw: dict[str, dict] = json.loads(json_str)
    result: dict[str, CanonicalSkill] = {}
    for name, fields in raw.items():
        result[name] = CanonicalSkill(
            name=fields["name"],
            category=fields["category"],
            onet_codes=fields.get("onet_codes", []),
            job_posting_aliases=fields.get("job_posting_aliases", []),
            user_aliases=fields.get("user_aliases", []),
        )
    return result
