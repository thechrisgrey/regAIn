"""Resume generation service.

Orchestrates data gathering from DynamoDB, LLM synthesis via
Amazon Bedrock (Nova Lite), and S3 storage for the agent-friendly
resume feature.
"""

import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import boto3
from boto3.dynamodb.conditions import Attr, Key

from backend.handlers.shared.dynamodb import DynamoDBClient
from backend.handlers.shared.models import Campaign, Evidence, Mission, UserProfile
from backend.handlers.shared.resume_models import ResumeData, ResumeResult

logger = logging.getLogger(__name__)

REGAIN_VERSION = "1.0.0"
SCHEMA_VERSION = "1.0"
MAX_DAILY_GENERATIONS = 3

REQUIRED_SECTIONS = [
    "Professional Summary",
    "Skills and Demonstrated Capabilities",
    "Campaign Progress",
    "Mission History Highlights",
    "Market Alignment",
]


class ResumeGenerationError(Exception):
    """Base error for resume generation failures."""

    def __init__(self, message: str, status_code: int = 500) -> None:
        super().__init__(message)
        self.status_code = status_code


class RateLimitError(ResumeGenerationError):
    """Raised when the daily generation limit is exceeded."""

    def __init__(self, message: str = "Daily generation limit reached (3/day). Resume regenerates automatically on mission completion.") -> None:
        super().__init__(message, status_code=429)


class ResumeService:
    """Orchestrates resume generation, retrieval, and storage.

    Gathers data from all DynamoDB tables in parallel, invokes
    Nova Lite for synthesis, stores results in S3, and manages
    resume metadata in UserProfiles.
    """

    def __init__(
        self,
        db_client: DynamoDBClient | None = None,
        s3_client: Any | None = None,
        bedrock_client: Any | None = None,
    ) -> None:
        self.db = db_client or DynamoDBClient()
        self.s3 = s3_client or boto3.client("s3")
        self.bedrock = bedrock_client or boto3.client("bedrock-runtime")
        self.bucket_name = os.environ.get("RESUME_BUCKET_NAME", "")
        self.model_id = os.environ.get("BEDROCK_MODEL_ID", "us.amazon.nova-lite-v2:0")

    def generate_resume(self, user_id: str) -> ResumeResult:
        """Orchestrate full resume generation: gather, synthesize, store.

        Args:
            user_id: The authenticated user's ID.

        Returns:
            ResumeResult with content, S3 key, version, timestamp,
            and a presigned download URL (1-hour expiry).

        Raises:
            ResumeGenerationError: On data, synthesis, or storage failure.
            RateLimitError: If daily generation limit exceeded.
        """
        self._enforce_rate_limit(user_id)
        data = self._gather_data(user_id)
        content = self._synthesize(data)
        generated_at = datetime.now(timezone.utc).isoformat()
        storage = self._store(user_id, content, generated_at)

        presigned_url = self.s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket_name, "Key": storage["latest_key"]},
            ExpiresIn=3600,
        )

        return ResumeResult(
            content=content,
            s3_key=storage["latest_key"],
            version=storage["version"],
            generated_at=generated_at,
            presigned_url=presigned_url,
        )

    def get_resume(self, user_id: str) -> ResumeResult:
        """Retrieve the latest resume without regenerating.

        Args:
            user_id: The authenticated user's ID.

        Returns:
            ResumeResult with content, metadata, and presigned URL.

        Raises:
            ResumeGenerationError: If no resume exists for the user.
        """
        profile_item = self.db.get_item("user_profiles", {"userId": user_id})
        if not profile_item:
            raise ResumeGenerationError("User not found", status_code=404)

        s3_key = profile_item.get("resumeS3Key")
        if not s3_key:
            raise ResumeGenerationError(
                "Complete your first mission to generate your resume",
                status_code=404,
            )

        try:
            response = self.s3.get_object(Bucket=self.bucket_name, Key=s3_key)
            content = response["Body"].read().decode("utf-8")
        except Exception as exc:
            logger.exception("Failed to read resume from S3: %s", s3_key)
            raise ResumeGenerationError(
                "Failed to retrieve resume", status_code=500
            ) from exc

        presigned_url = self.s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket_name, "Key": s3_key},
            ExpiresIn=3600,
        )

        return ResumeResult(
            content=content,
            s3_key=s3_key,
            version=int(profile_item.get("resumeVersion", 1)),
            generated_at=profile_item.get("lastResumeGeneratedAt", ""),
            presigned_url=presigned_url,
        )

    def _enforce_rate_limit(self, user_id: str) -> None:
        """Atomically enforce 3-per-day resume generation limit.

        Uses conditional DynamoDB updates (same pattern as mission rate limiting).

        Args:
            user_id: The authenticated user's ID.

        Raises:
            RateLimitError: If the user has already generated 3 resumes today.
        """
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        table = self.db._get_table("user_profiles")

        # Step 1: Reset counter if date changed
        try:
            table.update_item(
                Key={"userId": user_id},
                UpdateExpression="SET dailyResumeGenCount = :zero, dailyResumeGenDate = :today",
                ConditionExpression=(
                    "attribute_not_exists(dailyResumeGenDate) OR dailyResumeGenDate <> :today"
                ),
                ExpressionAttributeValues={":zero": 0, ":today": today},
            )
        except table.meta.client.exceptions.ConditionalCheckFailedException:
            pass

        # Step 2: Atomically increment, fail if >= 3
        try:
            table.update_item(
                Key={"userId": user_id},
                UpdateExpression="ADD dailyResumeGenCount :inc",
                ConditionExpression="dailyResumeGenCount < :limit",
                ExpressionAttributeValues={":inc": 1, ":limit": MAX_DAILY_GENERATIONS},
            )
        except table.meta.client.exceptions.ConditionalCheckFailedException:
            raise RateLimitError()

    def _gather_data(self, user_id: str) -> ResumeData:
        """Gather all user data from DynamoDB tables in parallel.

        Reads UserProfiles, Campaigns, MissionHistory, EvidenceVault,
        and MarketData concurrently using ThreadPoolExecutor.

        Args:
            user_id: The authenticated user's ID.

        Returns:
            ResumeData with all gathered information.

        Raises:
            ResumeGenerationError: On table read failure or missing data.
        """
        results: Dict[str, Any] = {}
        errors: Dict[str, str] = {}

        def read_profile() -> Optional[Dict[str, Any]]:
            return self.db.get_item("user_profiles", {"userId": user_id})

        def read_campaigns() -> list:
            return self.db.query(
                "campaigns",
                Key("userId").eq(user_id),
                filter_expression=Attr("status").eq("active"),
            )

        def read_missions() -> list:
            return self.db.query(
                "mission_history",
                Key("userId").eq(user_id),
                filter_expression=Attr("status").eq("completed"),
            )

        def read_evidence() -> list:
            return self.db.query(
                "evidence_vault",
                Key("userId").eq(user_id),
            )

        def read_market_data(target_role: str) -> list:
            return self.db.query(
                "market_data",
                Key("sector").eq(f"role:{target_role}"),
            )

        tasks = {
            "UserProfiles": read_profile,
            "Campaigns": read_campaigns,
            "MissionHistory": read_missions,
            "EvidenceVault": read_evidence,
        }

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {
                executor.submit(fn): table_name
                for table_name, fn in tasks.items()
            }
            for future in as_completed(futures):
                table_name = futures[future]
                try:
                    results[table_name] = future.result()
                except Exception as exc:
                    errors[table_name] = str(exc)

        if errors:
            failed_tables = ", ".join(errors.keys())
            raise ResumeGenerationError(
                f"Failed to read from table(s): {failed_tables}",
                status_code=500,
            )

        # Validate profile
        profile_item = results["UserProfiles"]
        if not profile_item:
            raise ResumeGenerationError("User not found", status_code=404)
        profile = UserProfile.from_dynamodb_item(profile_item)

        # Validate campaign
        campaign_items = results["Campaigns"]
        if not campaign_items:
            raise ResumeGenerationError("No active campaign", status_code=400)
        campaign = Campaign.from_dynamodb_item(campaign_items[0])

        # Validate missions
        mission_items = results["MissionHistory"]
        if not mission_items:
            raise ResumeGenerationError(
                "Complete your first mission to generate your resume",
                status_code=400,
            )
        completed_missions = [Mission.from_dynamodb_item(m) for m in mission_items]

        # Parse evidence
        evidence_entries = [Evidence.from_dynamodb_item(e) for e in results["EvidenceVault"]]

        # Fetch market data (depends on profile target_role)
        target_role = profile.target_role or campaign.target_role
        market_alignment: Dict[str, Any] = {}
        try:
            market_items = read_market_data(target_role)
            if market_items:
                latest = sorted(market_items, key=lambda r: r.get("timestamp", ""))[-1]
                market_alignment = {
                    "target_role": target_role,
                    "alignment_pct": latest.get("alignmentPct", 0),
                    "top_skills": latest.get("topSkills", []),
                    "skill_gaps": latest.get("skillGaps", []),
                }
        except Exception as exc:
            errors["MarketData"] = str(exc)

        if "MarketData" in errors:
            raise ResumeGenerationError(
                "Failed to read from table(s): MarketData",
                status_code=500,
            )

        return ResumeData(
            profile=profile,
            campaign=campaign,
            completed_missions=completed_missions,
            evidence_entries=evidence_entries,
            market_alignment=market_alignment,
        )

    def _synthesize(self, data: ResumeData) -> str:
        """Construct a prompt and invoke Nova Lite to generate the resume.

        Builds a detailed prompt from ResumeData, calls Bedrock, and
        validates the output has correct YAML frontmatter and all 5
        markdown sections. Retries once on validation failure.

        Args:
            data: Gathered user data for resume generation.

        Returns:
            The full resume markdown string with YAML frontmatter.

        Raises:
            ResumeGenerationError: If Bedrock fails or output is invalid
                after retry.
        """
        prompt = self._build_prompt(data)

        for attempt in range(2):
            try:
                response = self.bedrock.invoke_model(
                    modelId=self.model_id,
                    contentType="application/json",
                    accept="application/json",
                    body=json.dumps({
                        "messages": [{"role": "user", "content": [{"text": prompt}]}],
                        "inferenceConfig": {"maxTokens": 4096, "temperature": 0.7},
                    }),
                )
                result = json.loads(response["body"].read())
                text = result["output"]["message"]["content"][0]["text"]
            except Exception as exc:
                logger.exception("Bedrock invocation failed (attempt %d)", attempt + 1)
                if attempt == 1:
                    raise ResumeGenerationError(
                        "Resume generation failed — please try again",
                        status_code=502,
                    ) from exc
                continue

            text = self._clean_llm_output(text)

            if self._validate_resume(text):
                return text

            logger.warning(
                "Resume validation failed (attempt %d): starts_with_dashes=%s, "
                "first_80_chars=%r",
                attempt + 1,
                text.startswith("---"),
                text[:80],
            )

        raise ResumeGenerationError(
            "Resume generation failed — please try again",
            status_code=502,
        )

    def _build_prompt(self, data: ResumeData) -> str:
        """Build the Nova Lite prompt from gathered data.

        Args:
            data: Gathered user data for resume generation.

        Returns:
            The prompt string for Bedrock invocation.
        """
        # Build skills summary with evidence counts
        skill_evidence: Dict[str, list] = {}
        for evidence in data.evidence_entries:
            skill_evidence.setdefault(evidence.skill_tag, []).append(evidence)

        skills_text = ""
        for skill_name, entries in skill_evidence.items():
            count = len(entries)
            proficiency = _evidence_count_to_proficiency(count)
            best_reflection = max(entries, key=lambda e: len(e.reflection)).reflection
            skills_text += (
                f"- {skill_name}: {count} evidence items, "
                f"proficiency={proficiency}, "
                f"strongest evidence: \"{best_reflection[:200]}\"\n"
            )

        missions_text = ""
        for m in data.completed_missions:
            missions_text += (
                f"- \"{m.title}\" (completed {m.completed_date or 'N/A'}): "
                f"{m.description[:150]}\n"
            )

        market_text = json.dumps(data.market_alignment, indent=2)

        # Build accomplishments hint from evidence
        top_evidence = sorted(
            data.evidence_entries,
            key=lambda e: len(e.reflection),
            reverse=True,
        )[:10]
        accomplishments_text = ""
        for e in top_evidence:
            accomplishments_text += f"- [{e.skill_tag}] {e.reflection[:200]}\n"

        return f"""Generate a professional resume in markdown format with YAML frontmatter for a career transitioner on the REGAIN platform.

IMPORTANT RULES:
- The document MUST start with "---" on the first line, followed by YAML frontmatter, then "---" on its own line.
- After the frontmatter, write 5 markdown sections in this exact order using ## headers.
- Do NOT include any email addresses, phone numbers, physical addresses, or internal IDs (UUIDs, DynamoDB keys, evidence IDs).
- Only include the person's name and target role as identifying information.
- Write as a professional narrative backed by evidence, not a template with placeholders.

USER DATA:
Name: {data.profile.name}
Target Role: {data.campaign.target_role}
Transition Type: {data.profile.persona}
Campaign Phase: {data.campaign.phase}
Campaign Title: {data.campaign.title}
Total Completed Missions: {len(data.completed_missions)}
Total Evidence Items: {len(data.evidence_entries)}

SKILLS WITH EVIDENCE:
{skills_text}

COMPLETED MISSIONS:
{missions_text}

TOP EVIDENCE FOR ACCOMPLISHMENTS:
{accomplishments_text}

MARKET ALIGNMENT DATA:
{market_text}

YAML FRONTMATTER REQUIREMENTS:
The frontmatter MUST include these exact fields:
- schema_version: "{SCHEMA_VERSION}"
- generated_at: Use current ISO 8601 timestamp
- regain_version: "{REGAIN_VERSION}"
- name: "{data.profile.name}"
- target_role: "{data.campaign.target_role}"
- transition_type: "{data.profile.persona}"
- skills: Array of objects, each with skill_name, evidence_count (integer), strongest_evidence_summary (string), proficiency_indicator (one of: beginner, intermediate, advanced, expert based on evidence count: 1-2=beginner, 3-5=intermediate, 6-9=advanced, 10+=expert)
- campaign_phase: "{data.campaign.phase}"
- campaign_progress_pct: Calculate based on missions completed vs typical campaign size
- market_alignment_score: {data.market_alignment.get("alignment_pct", 0)}
- missions_completed: {len(data.completed_missions)}
- evidence_items: {len(data.evidence_entries)}
- top_accomplishments: Array of 3-5 achievement strings, each backed by evidence

MARKDOWN BODY SECTIONS (use ## headers, in this exact order):
1. ## Professional Summary — Write 2-3 sentences about the user's background, trajectory, and documented growth. Base this on their evidence and missions, not generic filler.
2. ## Skills and Demonstrated Capabilities — List each skill with evidence-backed bullet points referencing specific mission titles, completion dates, and evidence reflections.
3. ## Campaign Progress — Describe the current phase, progress percentage, and trajectory.
4. ## Mission History Highlights — Include {"5-8" if len(data.completed_missions) >= 8 else "all"} completed missions curated for relevance to the target role, each with a reflection excerpt.
5. ## Market Alignment — Include target role, alignment percentage, demonstrated in-demand skills, and active skill gaps."""

    @staticmethod
    def _clean_llm_output(text: str) -> str:
        """Strip markdown code fences and leading preamble from LLM output.

        Nova Lite sometimes wraps its response in ```markdown ... ``` or
        adds explanatory text before the actual resume content.
        """
        text = text.strip()

        # Strip outer markdown code fences (```markdown ... ``` or ``` ... ```)
        if text.startswith("```"):
            first_newline = text.index("\n") if "\n" in text else len(text)
            text = text[first_newline + 1:]
            if text.rstrip().endswith("```"):
                text = text.rstrip()[:-3]
            text = text.strip()

        # If LLM added preamble before "---", discard everything before it
        if not text.startswith("---") and "\n---\n" in text:
            idx = text.index("\n---\n")
            text = text[idx + 1:]
        elif not text.startswith("---") and text.find("---") > 0:
            idx = text.index("---")
            text = text[idx:]

        return text.strip()

    def _validate_resume(self, content: str) -> bool:
        """Validate resume has correct YAML frontmatter and 5 sections.

        Args:
            content: The raw resume markdown string.

        Returns:
            True if valid, False otherwise.
        """
        # Check frontmatter delimiters
        if not content.startswith("---"):
            logger.warning("Validation fail: no leading ---. First 120 chars: %r", content[:120])
            return False

        parts = content.split("---", 2)
        if len(parts) < 3:
            logger.warning("Validation fail: fewer than 3 parts after splitting on ---")
            return False

        # Validate frontmatter block is non-empty and has at least one key: value line
        fm_content = parts[1].strip()
        if not fm_content:
            logger.warning("Validation fail: frontmatter block is empty")
            return False

        has_kv = any(":" in line for line in fm_content.splitlines() if line.strip())
        if not has_kv:
            logger.warning("Validation fail: no key:value lines in frontmatter")
            return False

        # Validate all 5 section headers present (case-insensitive, order not required)
        body = parts[2].lower()
        for section in REQUIRED_SECTIONS:
            if f"## {section.lower()}" not in body:
                logger.warning(
                    "Validation fail: section %r not found in body. "
                    "Found headers: %s",
                    section,
                    [line.strip() for line in parts[2].splitlines() if line.strip().startswith("## ")],
                )
                return False

        return True

    def _store(
        self,
        user_id: str,
        content: str,
        generated_at: str,
    ) -> Dict[str, Any]:
        """Store resume in S3 and update UserProfiles metadata.

        Writes a timestamped copy and overwrites latest.md. Updates
        the UserProfiles table with the new pointer and version.

        Args:
            user_id: The authenticated user's ID.
            content: The full resume markdown content.
            generated_at: ISO 8601 timestamp of generation.

        Returns:
            Dict with latest_key and version.

        Raises:
            ResumeGenerationError: If S3 write fails.
        """
        timestamp_key = f"{user_id}/resume/resume-{generated_at}.md"
        latest_key = f"{user_id}/resume/latest.md"

        try:
            self.s3.put_object(
                Bucket=self.bucket_name,
                Key=timestamp_key,
                Body=content.encode("utf-8"),
                ContentType="text/markdown",
            )
            self.s3.put_object(
                Bucket=self.bucket_name,
                Key=latest_key,
                Body=content.encode("utf-8"),
                ContentType="text/markdown",
            )
        except Exception as exc:
            logger.exception("Failed to store resume in S3")
            raise ResumeGenerationError(
                "Failed to store resume", status_code=500
            ) from exc

        # Get current version and increment
        profile_item = self.db.get_item("user_profiles", {"userId": user_id})
        current_version = int(profile_item.get("resumeVersion", 0)) if profile_item else 0
        new_version = current_version + 1

        try:
            self.db.update_item(
                "user_profiles",
                {"userId": user_id},
                {
                    "lastResumeGeneratedAt": generated_at,
                    "resumeS3Key": latest_key,
                    "resumeVersion": new_version,
                },
            )
        except Exception:
            logger.warning(
                "Failed to update UserProfiles metadata for %s; "
                "resume is stored in S3 but pointer may be stale",
                user_id,
            )

        return {"latest_key": latest_key, "version": new_version}


def _evidence_count_to_proficiency(count: int) -> str:
    """Map evidence count to proficiency indicator.

    Args:
        count: Number of evidence items for a skill.

    Returns:
        One of 'beginner', 'intermediate', 'advanced', 'expert'.
    """
    if count >= 10:
        return "expert"
    if count >= 6:
        return "advanced"
    if count >= 3:
        return "intermediate"
    return "beginner"
