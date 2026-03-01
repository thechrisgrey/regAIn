"""Voice practice service layer.

Handles listing and retrieving voice practice sessions, including
S3 reads for transcript and assessment data.
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

import boto3
from boto3.dynamodb.conditions import Key

from backend.handlers.shared.dynamodb import DynamoDBClient

logger = logging.getLogger(__name__)


class VoicePracticeService:
    """Service for querying voice practice sessions and their artifacts.

    Reads session metadata from DynamoDB and transcript/assessment
    data from S3.
    """

    def __init__(
        self,
        db_client: DynamoDBClient | None = None,
        s3_client: Any | None = None,
    ) -> None:
        self.db = db_client or DynamoDBClient()
        self.s3 = s3_client or boto3.client("s3")
        self.bucket_name = os.environ.get("VOICE_PRACTICE_BUCKET_NAME", "")

    def list_sessions(
        self,
        user_id: str,
        limit: int = 50,
        cursor: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List voice practice sessions for a user with cursor-based pagination.

        Queries the VoiceSessions table by userId and returns session
        metadata sorted by sessionId descending. No S3 reads are
        performed.

        Args:
            user_id: The authenticated user's ID.
            limit: Maximum items per page (capped at 200).
            cursor: Opaque pagination cursor from a previous response.

        Returns:
            Dict with "items" list and "nextCursor" (str or None).
        """
        page = self.db.query_page(
            "voice_sessions",
            Key("userId").eq(user_id),
            limit=limit,
            cursor=cursor,
            scan_forward=False,
        )

        page["items"] = [
            {
                "sessionId": item.get("sessionId", ""),
                "sessionType": item.get("sessionType", ""),
                "status": item.get("status", ""),
                "targetRole": item.get("targetRole", ""),
                "durationSeconds": int(item.get("durationSeconds", 0)),
                "turnCount": int(item.get("turnCount", 0)),
                "overallScore": int(item.get("overallScore", 0)),
                "assessmentSummary": item.get("assessmentSummary", ""),
                "createdAt": item.get("createdAt", ""),
            }
            for item in page["items"]
        ]

        return page

    def get_session_detail(
        self, user_id: str, session_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get full session detail including transcript and assessment.

        Reads the DynamoDB record and fetches transcript.json and
        assessment.json from S3 if the keys are present.

        Args:
            user_id: The authenticated user's ID.
            session_id: The session to retrieve.

        Returns:
            Combined dict with session metadata, transcript, and
            assessment, or None if the session does not exist.
        """
        item = self.db.get_item(
            "voice_sessions",
            {"userId": user_id, "sessionId": session_id},
        )
        if not item:
            return None

        result: Dict[str, Any] = {
            "sessionId": item.get("sessionId", ""),
            "sessionType": item.get("sessionType", ""),
            "status": item.get("status", ""),
            "targetRole": item.get("targetRole", ""),
            "durationSeconds": int(item.get("durationSeconds", 0)),
            "turnCount": int(item.get("turnCount", 0)),
            "overallScore": int(item.get("overallScore", 0)),
            "assessmentSummary": item.get("assessmentSummary", ""),
            "createdAt": item.get("createdAt", ""),
            "transcript": [],
            "assessment": None,
        }

        # Read transcript from S3
        s3_transcript_key = item.get("s3TranscriptKey", "")
        if s3_transcript_key:
            try:
                response = self.s3.get_object(
                    Bucket=self.bucket_name, Key=s3_transcript_key
                )
                result["transcript"] = json.loads(
                    response["Body"].read().decode("utf-8")
                )
            except Exception:
                logger.warning(
                    "Failed to read transcript from S3: %s", s3_transcript_key
                )

        # Read assessment from S3
        s3_assessment_key = item.get("s3AssessmentKey", "")
        if s3_assessment_key:
            try:
                response = self.s3.get_object(
                    Bucket=self.bucket_name, Key=s3_assessment_key
                )
                result["assessment"] = json.loads(
                    response["Body"].read().decode("utf-8")
                )
            except Exception:
                logger.warning(
                    "Failed to read assessment from S3: %s", s3_assessment_key
                )

        return result
