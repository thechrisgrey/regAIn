"""PDF export service for the Impact Scorecard.

Renders a branded 5-page Career Evidence Report using WeasyPrint
with a Jinja2 HTML template. The PDF is uploaded to S3 and a
pre-signed download URL is returned.
"""

from __future__ import annotations

import io
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import boto3
from jinja2 import Template

logger = logging.getLogger(__name__)

# Pre-signed URL expiry for PDF downloads
_PRESIGN_EXPIRY_SECONDS = 900  # 15 minutes

# ---------------------------------------------------------------------------
# HTML template for the Career Evidence Report
# ---------------------------------------------------------------------------

_REPORT_TEMPLATE = Template("""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<style>
  @page {
    size: letter;
    margin: 1in 0.75in;
    @bottom-center {
      content: "Generated from verified, timestamped activity data. REGAIN does not issue scores based on self-reported surveys.";
      font-size: 7pt;
      color: #999;
      font-family: sans-serif;
    }
    @bottom-right {
      content: counter(page) " / " counter(pages);
      font-size: 7pt;
      color: #999;
      font-family: sans-serif;
    }
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    color: #3B2D27;
    line-height: 1.5;
    font-size: 10pt;
  }
  h1 { font-size: 28pt; font-weight: 600; color: #3B2D27; }
  h2 { font-size: 14pt; font-weight: 600; color: #916D65; margin-top: 24pt; margin-bottom: 8pt; }
  h3 { font-size: 11pt; font-weight: 600; color: #5A4A44; margin-top: 16pt; margin-bottom: 6pt; }
  .cover { text-align: center; padding-top: 2.5in; page-break-after: always; }
  .cover .score { font-size: 72pt; font-weight: 700; color: #916D65; margin-top: 24pt; }
  .cover .label { font-size: 12pt; color: #999; text-transform: uppercase; letter-spacing: 2pt; margin-top: 4pt; }
  .cover .subtitle { font-size: 14pt; color: #5A4A44; margin-top: 16pt; }
  .cover .date { font-size: 10pt; color: #999; margin-top: 8pt; }
  .cover .brand { font-size: 10pt; color: #BFA8C5; margin-top: 32pt; letter-spacing: 1pt; }
  .page-break { page-break-before: always; }
  .section { margin-bottom: 20pt; }
  .metric-row { display: flex; gap: 12pt; margin-top: 12pt; }
  .metric-box {
    flex: 1;
    background: #FBF8F7;
    border-radius: 6pt;
    padding: 10pt;
    text-align: center;
  }
  .metric-box .value {
    font-size: 22pt;
    font-weight: 600;
    color: #3B2D27;
    font-family: 'Courier New', monospace;
  }
  .metric-box .label { font-size: 8pt; color: #999; text-transform: uppercase; letter-spacing: 1pt; margin-top: 2pt; }
  .dim-bar { margin: 6pt 0; }
  .dim-bar .name { font-size: 9pt; color: #5A4A44; }
  .dim-bar .bar-track { height: 6pt; background: #F4EFED; border-radius: 3pt; margin-top: 3pt; }
  .dim-bar .bar-fill { height: 100%; border-radius: 3pt; background: linear-gradient(90deg, #B39189, #BFA8C5); }
  .dim-bar .score-val { float: right; font-size: 9pt; font-family: monospace; color: #3B2D27; }
  .evidence-item {
    background: #FBF8F7;
    border-radius: 6pt;
    padding: 10pt;
    margin-top: 8pt;
    border-left: 3pt solid #916D65;
  }
  .evidence-item .title { font-weight: 600; font-size: 10pt; color: #3B2D27; }
  .evidence-item .meta { font-size: 8pt; color: #999; margin-top: 2pt; }
  .evidence-item .excerpt { font-size: 9pt; color: #5A4A44; margin-top: 6pt; }
  .gap-item {
    display: inline-block;
    background: #FCE5C7;
    border-radius: 12pt;
    padding: 3pt 10pt;
    font-size: 9pt;
    color: #5A4A44;
    margin: 2pt 4pt 2pt 0;
  }
  table { width: 100%; border-collapse: collapse; margin-top: 8pt; }
  th { text-align: left; font-size: 8pt; color: #999; text-transform: uppercase; letter-spacing: 0.5pt; padding: 4pt 6pt; border-bottom: 1pt solid #E5DBD8; }
  td { font-size: 9pt; padding: 6pt; border-bottom: 0.5pt solid #F4EFED; color: #3B2D27; }
  td.mono { font-family: monospace; }
  .narrative { font-size: 10pt; line-height: 1.7; color: #5A4A44; margin-top: 8pt; }
</style>
</head>
<body>

<!-- PAGE 1: Cover -->
<div class="cover">
  <div class="brand">REGAIN</div>
  <h1>Career Evidence Report</h1>
  <div class="score">{{ cri }}</div>
  <div class="label">Composite Readiness Index</div>
  <div class="subtitle">{{ user_name }} &mdash; {{ target_role }}</div>
  <div class="date">Generated {{ export_date }}</div>
</div>

<!-- PAGE 2: Executive Summary -->
<div class="section">
  <h2>Executive Summary</h2>
  <p class="narrative">{{ narrative }}</p>

  <div class="metric-row">
    <div class="metric-box">
      <div class="value">{{ missions_completed }}</div>
      <div class="label">Missions</div>
    </div>
    <div class="metric-box">
      <div class="value">{{ evidence_count }}</div>
      <div class="label">Evidence</div>
    </div>
    <div class="metric-box">
      <div class="value">{{ unique_skills }}</div>
      <div class="label">Skills</div>
    </div>
  </div>

  <h3>Dimension Scores</h3>
  {% for dim in dimensions %}
  <div class="dim-bar">
    <span class="name">{{ dim.name }}</span>
    <span class="score-val">{{ dim.score }}</span>
    <div class="bar-track">
      <div class="bar-fill" style="width: {{ dim.score }}%"></div>
    </div>
  </div>
  {% endfor %}
</div>

<!-- PAGE 3: Evidence Highlights -->
<div class="page-break section">
  <h2>Evidence Highlights</h2>
  <p style="font-size: 9pt; color: #999;">Top entries selected by evidence richness score.</p>
  {% for entry in evidence_highlights %}
  <div class="evidence-item">
    <div class="title">{{ entry.skill }}</div>
    <div class="meta">{{ entry.date }} &middot; Mission: {{ entry.mission_id }}</div>
    <div class="excerpt">{{ entry.excerpt }}</div>
  </div>
  {% endfor %}

  {% if not evidence_highlights %}
  <p class="narrative">No evidence entries available yet. Complete missions to build your evidence vault.</p>
  {% endif %}
</div>

<!-- PAGE 4: Market Alignment -->
<div class="page-break section">
  <h2>Market Alignment &mdash; {{ target_role }}</h2>

  <div class="metric-row">
    <div class="metric-box">
      <div class="value">{{ matched_skills }}/{{ total_target_skills }}</div>
      <div class="label">Skills Matched</div>
    </div>
    <div class="metric-box">
      <div class="value">{{ market_alignment_score }}</div>
      <div class="label">Alignment Score</div>
    </div>
  </div>

  {% if hot_skills_gap %}
  <h3>Top Skill Gaps</h3>
  <div>
    {% for gap in hot_skills_gap %}
    <span class="gap-item">{{ gap.skill }} (demand: {{ gap.demand }})</span>
    {% endfor %}
  </div>
  {% endif %}

  <h3>Phase Progression</h3>
  <p class="narrative">
    Current phase: <strong>{{ phase }}</strong>.
    {{ phase_detail }}
  </p>
</div>

<!-- PAGE 5: Mission History -->
<div class="page-break section">
  <h2>Mission History</h2>
  <table>
    <thead>
      <tr>
        <th>Category</th>
        <th>Completed</th>
        <th>Difficulty Range</th>
      </tr>
    </thead>
    <tbody>
      {% for cat in category_summary %}
      <tr>
        <td>{{ cat.name }}</td>
        <td class="mono">{{ cat.count }}</td>
        <td class="mono">{{ cat.difficulty_range }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>

  <h3>Difficulty Trajectory</h3>
  <p class="narrative">
    {% for cat, ceiling in difficulty_ceilings.items() %}
    {{ cat }}: peak difficulty {{ ceiling }}.
    {% endfor %}
  </p>
</div>

</body>
</html>
""")


class PdfExportService:
    """Generates and stores Career Evidence Report PDFs."""

    def __init__(
        self,
        s3_client: Any = None,
        bucket_name: str | None = None,
    ) -> None:
        self.s3 = s3_client or boto3.client("s3")
        self.bucket = bucket_name or os.environ.get("SCORE_EXPORTS_BUCKET", "")

    def generate_report(
        self,
        user_id: str,
        scorecard: dict[str, Any],
        profile: dict[str, Any],
        evidence: list[dict[str, Any]],
    ) -> str:
        """Generate a PDF Career Evidence Report and upload to S3.

        Args:
            user_id: Cognito user ID.
            scorecard: Full scorecard dict from ScoreService.compute_scorecard().
            profile: User profile from DynamoDB.
            evidence: Evidence vault entries.

        Returns:
            Pre-signed S3 URL for PDF download.
        """
        html = self._render_html(scorecard, profile, evidence)
        pdf_bytes = self._html_to_pdf(html)

        # Upload to S3
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        s3_key = f"{user_id}/reports/career-evidence-report-{timestamp}.pdf"

        self.s3.put_object(
            Bucket=self.bucket,
            Key=s3_key,
            Body=pdf_bytes,
            ContentType="application/pdf",
        )

        # Generate pre-signed URL
        url = self.s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": s3_key},
            ExpiresIn=_PRESIGN_EXPIRY_SECONDS,
        )

        logger.info("PDF report generated for user %s at %s", user_id, s3_key)
        return url

    def _render_html(
        self,
        scorecard: dict[str, Any],
        profile: dict[str, Any],
        evidence: list[dict[str, Any]],
    ) -> str:
        """Render the HTML template with scorecard data."""
        detail = scorecard.get("dimensionDetail", {})
        ed = detail.get("evidenceDensity", {})
        ma = detail.get("marketAlignment", {})
        pp = detail.get("phaseProgression", {})
        ad = detail.get("adaptiveDifficulty", {})
        mv = detail.get("missionVelocity", {})

        user_name = profile.get("name", "")
        target_role = scorecard.get("targetRole", "")
        now = datetime.now(timezone.utc)

        # Build narrative
        narrative = (
            f"As of {now.strftime('%B %d, %Y')}, {user_name} has completed "
            f"{scorecard.get('missionsCompleted', 0)} missions across "
            f"{len(mv.get('categoryBreakdown', {}))} categories, "
            f"documented {scorecard.get('evidenceCount', 0)} pieces of evidence "
            f"demonstrating {ed.get('uniqueSkills', 0)} distinct skills, "
            f"and is progressing through REGAIN's {pp.get('phase', 'Foundation').title()} phase."
        )
        if ma.get("hasMarketData") and target_role:
            narrative += (
                f" Skill development aligns with {ma.get('matchedSkills', 0)} of the "
                f"top {ma.get('totalTargetSkills', 0)} skills in demand for "
                f"{target_role} roles."
            )

        # Dimensions list
        dimensions = [
            {"name": "Evidence Density", "score": round(scorecard.get("evidenceDensityScore", 0), 1)},
            {"name": "Market Alignment", "score": round(scorecard.get("marketAlignmentScore", 0), 1)},
            {"name": "Mission Velocity", "score": round(scorecard.get("missionVelocityScore", 0), 1)},
            {"name": "Phase Progression", "score": round(scorecard.get("phaseProgressionScore", 0), 1)},
            {"name": "Adaptive Difficulty", "score": round(scorecard.get("adaptiveDifficultyScore", 0), 1)},
        ]

        # Top evidence entries by word count (proxy for richness)
        sorted_evidence = sorted(
            evidence,
            key=lambda e: int(e.get("wordCount") or len(e.get("reflection", "").split())),
            reverse=True,
        )
        highlights = []
        for e in sorted_evidence[:5]:
            reflection = e.get("reflection", "")
            highlights.append({
                "skill": e.get("skillTag", "General"),
                "date": e.get("createdAt", "")[:10],
                "mission_id": e.get("missionId", "")[:12],
                "excerpt": reflection[:300] + ("..." if len(reflection) > 300 else ""),
            })

        # Category summary from mission velocity breakdown
        cat_breakdown = mv.get("categoryBreakdown", {})
        cat_labels = {
            "reflection": "Reflection",
            "skill_building": "Skill Building",
            "portfolio": "Portfolio Development",
            "networking": "Networking",
            "market_research": "Market Research",
            "general": "General",
        }
        ceilings = ad.get("difficultyCeilings", {})
        category_summary = []
        for cat, count in sorted(cat_breakdown.items(), key=lambda x: -x[1]):
            ceiling = ceilings.get(cat, "N/A")
            category_summary.append({
                "name": cat_labels.get(cat, cat.replace("_", " ").title()),
                "count": count,
                "difficulty_range": f"1-{ceiling}" if isinstance(ceiling, int) else "N/A",
            })

        # Phase detail
        gates = pp.get("gatesMet", {})
        met_count = sum(1 for g in gates.values() if g.get("met"))
        phase_detail = f"{met_count} of {len(gates)} phase gates satisfied."

        return _REPORT_TEMPLATE.render(
            cri=round(scorecard.get("cri", 0), 1),
            user_name=user_name,
            target_role=target_role,
            export_date=now.strftime("%B %d, %Y"),
            narrative=narrative,
            missions_completed=scorecard.get("missionsCompleted", 0),
            evidence_count=scorecard.get("evidenceCount", 0),
            unique_skills=ed.get("uniqueSkills", 0),
            dimensions=dimensions,
            evidence_highlights=highlights,
            matched_skills=ma.get("matchedSkills", 0),
            total_target_skills=ma.get("totalTargetSkills", 0),
            market_alignment_score=round(scorecard.get("marketAlignmentScore", 0), 1),
            hot_skills_gap=ma.get("hotSkillsGap", []),
            phase=pp.get("phase", "Foundation").title(),
            phase_detail=phase_detail,
            category_summary=category_summary,
            difficulty_ceilings=ceilings,
        )

    def _html_to_pdf(self, html: str) -> bytes:
        """Convert HTML string to PDF bytes using WeasyPrint."""
        try:
            from weasyprint import HTML
            pdf_buffer = io.BytesIO()
            HTML(string=html).write_pdf(pdf_buffer)
            return pdf_buffer.getvalue()
        except ImportError:
            logger.warning(
                "WeasyPrint not available — falling back to HTML-only export. "
                "Install WeasyPrint Lambda layer for PDF generation."
            )
            # Fallback: return HTML as bytes (still useful for debugging)
            return html.encode("utf-8")
