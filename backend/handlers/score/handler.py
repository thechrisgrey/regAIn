"""Score Lambda handler.

Thin handler for GET /score and GET /score/history.
"""

import logging
from typing import Any, Dict

from backend.handlers.shared.auth import get_user_id
from backend.handlers.shared.responses import error_response, success_response
from backend.handlers.shared.structured_log import get_logger
from backend.handlers.score.service import ScoreService

logger = logging.getLogger(__name__)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handle GET /score and GET /score/history requests.

    Args:
        event: API Gateway event.
        context: Lambda context.

    Returns:
        API Gateway-compatible response.
    """
    slog = get_logger(event, __name__)
    user_id = get_user_id(event)
    if not user_id:
        return error_response("Unauthorized", 401)

    resource = event.get("resource", "")

    try:
        service = ScoreService()

        if resource == "/score/history":
            # Return cached daily snapshots for longitudinal charts
            scores_table = service.db._get_table("impact_scores")
            from boto3.dynamodb.conditions import Key as DKey
            result = scores_table.query(
                KeyConditionExpression=(
                    DKey("userId").eq(user_id)
                    & DKey("sk").begins_with("SNAPSHOT#")
                ),
                ScanIndexForward=True,
            )
            snapshots = result.get("Items", [])
            return success_response({"snapshots": snapshots})

        # GET /score — compute current scorecard
        scorecard = service.compute_scorecard(user_id)
        return success_response(scorecard)
    except Exception:
        slog.exception("Score handler failed")
        return error_response("Internal server error", 500)
