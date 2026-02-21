"""Seed data loader for the Market Intelligence System.

Provides pre-loaded market data for five representative transition paths
so the platform works immediately without waiting for API refresh cycles.
All values are marked source="synthetic". Salary and demand figures are
informed by O*NET/BLS public data where available.

Requirements: 9.1, 9.2, 9.3, 9.4, 9.5
"""

from __future__ import annotations

import importlib
import logging
from datetime import date
from typing import Any

_models_mod = importlib.import_module("backend.handlers.market_intel.models")
MarketDataRecord = _models_mod.MarketDataRecord

_db_mod = importlib.import_module("backend.handlers.shared.dynamodb")
DynamoDBClient = _db_mod.DynamoDBClient

logger = logging.getLogger(__name__)


def _get_trend_direction(growth_rate: float) -> str:
    """Derive trend label from year-over-year growth rate.

    Args:
        growth_rate: YoY growth percentage.

    Returns:
        "surging", "growing", "stable", or "declining".
    """
    if growth_rate > 20:
        return "surging"
    if growth_rate >= 5:
        return "growing"
    if growth_rate >= -5:
        return "stable"
    return "declining"


def _build_seed_records() -> list[MarketDataRecord]:
    """Build MarketDataRecord instances for all five transition paths.

    Returns:
        List of five MarketDataRecord objects ready for DynamoDB.
    """
    today = date.today().isoformat()

    records: list[MarketDataRecord] = [
        # 1. Software QA Engineer → AI Quality Assurance Engineer
        MarketDataRecord(
            sector="role:ai_qa_engineer",
            timestamp=today,
            role_title="AI Quality Assurance Engineer",
            category="technology",
            demand_score=82,
            growth_rate=25.0,
            trend_direction=_get_trend_direction(25.0),
            top_skills=[
                {"skill": "Python", "frequency": 88.0, "canonical": "Python"},
                {"skill": "Test Automation", "frequency": 82.0, "canonical": "Test Automation"},
                {"skill": "Machine Learning", "frequency": 75.0, "canonical": "Machine Learning"},
                {"skill": "CI/CD", "frequency": 68.0, "canonical": "CI/CD"},
                {"skill": "Data Validation", "frequency": 62.0, "canonical": "Data Validation"},
                {"skill": "API Testing", "frequency": 58.0, "canonical": "API Testing"},
                {"skill": "Statistical Analysis", "frequency": 52.0, "canonical": "Statistical Analysis"},
                {"skill": "Cloud Computing", "frequency": 48.0, "canonical": "Cloud Computing"},
                {"skill": "Agile Methodology", "frequency": 45.0, "canonical": "Agile Methodology"},
                {"skill": "SQL", "frequency": 40.0, "canonical": "SQL"},
            ],
            salary_range={"min": 95000, "median": 125000, "max": 165000, "region": "national"},
            posting_volume=3200,
            projection="Much faster than average",
            source="synthetic",
            insights=[],
        ),
        # 2. Infantry/Combat Arms → Project Manager/Operations Manager
        MarketDataRecord(
            sector="role:project_manager_ops",
            timestamp=today,
            role_title="Project Manager/Operations Manager",
            category="management",
            demand_score=71,
            growth_rate=6.0,
            trend_direction=_get_trend_direction(6.0),
            top_skills=[
                {"skill": "Project Management", "frequency": 90.0, "canonical": "Project Management"},
                {"skill": "Leadership", "frequency": 85.0, "canonical": "Leadership"},
                {"skill": "Risk Management", "frequency": 72.0, "canonical": "Risk Management"},
                {"skill": "Budgeting", "frequency": 68.0, "canonical": "Budgeting"},
                {"skill": "Stakeholder Management", "frequency": 65.0, "canonical": "Stakeholder Management"},
                {"skill": "Agile Methodology", "frequency": 60.0, "canonical": "Agile Methodology"},
                {"skill": "Strategic Planning", "frequency": 55.0, "canonical": "Strategic Planning"},
                {"skill": "Communication", "frequency": 52.0, "canonical": "Communication"},
                {"skill": "Data Analysis", "frequency": 45.0, "canonical": "Data Analysis"},
                {"skill": "Process Improvement", "frequency": 42.0, "canonical": "Process Improvement"},
            ],
            salary_range={"min": 75000, "median": 98000, "max": 140000, "region": "national"},
            posting_volume=8500,
            projection="Faster than average",
            source="synthetic",
            insights=[],
        ),
        # 3. Retail Manager → Customer Success Manager
        MarketDataRecord(
            sector="role:customer_success_manager",
            timestamp=today,
            role_title="Customer Success Manager",
            category="management",
            demand_score=76,
            growth_rate=18.0,
            trend_direction=_get_trend_direction(18.0),
            top_skills=[
                {"skill": "Customer Relationship Management", "frequency": 92.0, "canonical": "Customer Relationship Management"},
                {"skill": "Communication", "frequency": 85.0, "canonical": "Communication"},
                {"skill": "Data Analysis", "frequency": 70.0, "canonical": "Data Analysis"},
                {"skill": "SaaS Knowledge", "frequency": 65.0, "canonical": "SaaS Knowledge"},
                {"skill": "Project Management", "frequency": 60.0, "canonical": "Project Management"},
                {"skill": "Problem Solving", "frequency": 58.0, "canonical": "Problem Solving"},
                {"skill": "Negotiation", "frequency": 52.0, "canonical": "Negotiation"},
                {"skill": "Technical Aptitude", "frequency": 48.0, "canonical": "Technical Aptitude"},
                {"skill": "Presentation Skills", "frequency": 44.0, "canonical": "Presentation Skills"},
                {"skill": "CRM Software", "frequency": 40.0, "canonical": "CRM Software"},
            ],
            salary_range={"min": 60000, "median": 82000, "max": 120000, "region": "national"},
            posting_volume=5400,
            projection="Faster than average",
            source="synthetic",
            insights=[],
        ),
        # 4. Truck Driver → Fleet Operations/Logistics Analyst
        MarketDataRecord(
            sector="role:fleet_ops_logistics_analyst",
            timestamp=today,
            role_title="Fleet Operations/Logistics Analyst",
            category="operations",
            demand_score=65,
            growth_rate=12.0,
            trend_direction=_get_trend_direction(12.0),
            top_skills=[
                {"skill": "Supply Chain Management", "frequency": 85.0, "canonical": "Supply Chain Management"},
                {"skill": "Data Analysis", "frequency": 78.0, "canonical": "Data Analysis"},
                {"skill": "Logistics Coordination", "frequency": 75.0, "canonical": "Logistics Coordination"},
                {"skill": "Fleet Management Software", "frequency": 68.0, "canonical": "Fleet Management Software"},
                {"skill": "Excel", "frequency": 65.0, "canonical": "Excel"},
                {"skill": "Route Optimization", "frequency": 58.0, "canonical": "Route Optimization"},
                {"skill": "Regulatory Compliance", "frequency": 52.0, "canonical": "Regulatory Compliance"},
                {"skill": "SQL", "frequency": 48.0, "canonical": "SQL"},
                {"skill": "Communication", "frequency": 44.0, "canonical": "Communication"},
                {"skill": "Cost Analysis", "frequency": 40.0, "canonical": "Cost Analysis"},
            ],
            salary_range={"min": 52000, "median": 68000, "max": 95000, "region": "national"},
            posting_volume=4100,
            projection="Average",
            source="synthetic",
            insights=[],
        ),
        # 5. Accountant → Data Analyst/Financial Systems Analyst
        MarketDataRecord(
            sector="role:data_analyst_financial",
            timestamp=today,
            role_title="Data Analyst/Financial Systems Analyst",
            category="analytical",
            demand_score=78,
            growth_rate=22.0,
            trend_direction=_get_trend_direction(22.0),
            top_skills=[
                {"skill": "SQL", "frequency": 90.0, "canonical": "SQL"},
                {"skill": "Python", "frequency": 82.0, "canonical": "Python"},
                {"skill": "Data Visualization", "frequency": 78.0, "canonical": "Data Visualization"},
                {"skill": "Excel", "frequency": 75.0, "canonical": "Excel"},
                {"skill": "Financial Modeling", "frequency": 70.0, "canonical": "Financial Modeling"},
                {"skill": "Statistical Analysis", "frequency": 65.0, "canonical": "Statistical Analysis"},
                {"skill": "Business Intelligence", "frequency": 58.0, "canonical": "Business Intelligence"},
                {"skill": "ETL Processes", "frequency": 52.0, "canonical": "ETL Processes"},
                {"skill": "Communication", "frequency": 48.0, "canonical": "Communication"},
                {"skill": "Accounting Principles", "frequency": 42.0, "canonical": "Accounting Principles"},
            ],
            salary_range={"min": 62000, "median": 85000, "max": 120000, "region": "national"},
            posting_volume=6800,
            projection="Much faster than average",
            source="synthetic",
            insights=[],
        ),
    ]

    return records


def load_seed_data() -> dict[str, Any]:
    """Write all seed market data records to the MarketData DynamoDB table.

    Idempotent — uses put_item which overwrites existing records with the
    same sector+timestamp key. Safe to call multiple times.

    Returns:
        Dict with "succeeded" (list of sector keys written) and
        "failed" (list of dicts with "sector" and "error" keys).
    """
    db = DynamoDBClient()
    records = _build_seed_records()

    succeeded: list[str] = []
    failed: list[dict[str, str]] = []

    for record in records:
        try:
            db.put_item("market_data", record.to_dynamodb_item())
            succeeded.append(record.sector)
            logger.info("Loaded seed data for %s", record.sector)
        except Exception as exc:
            logger.error(
                "Failed to load seed data for %s: %s",
                record.sector,
                exc,
            )
            failed.append({"sector": record.sector, "error": str(exc)})

    logger.info(
        "Seed data loading complete: %d succeeded, %d failed",
        len(succeeded),
        len(failed),
    )
    return {"succeeded": succeeded, "failed": failed}
