"""Coaching service module.

Bridges the Lambda handler to the Strands Coaching Agent.
The service is intentionally thin — it instantiates the agent,
passes the formatted message, and returns the structured response.
All business logic lives inside the agent and its tools.
"""

import logging
from typing import Any, Dict

from backend.agents.coaching.agent import create_coaching_agent

logger = logging.getLogger(__name__)


class CoachingService:
    """Delegates coaching interactions to the Strands Coaching Agent."""

    def checkin(
        self,
        user_id: str,
        message: str,
        session_type: str = "checkin",
    ) -> Dict[str, Any]:
        """Process a coaching interaction via the Strands Agent.

        Args:
            user_id: The authenticated user's ID.
            message: The user's message.
            session_type: One of 'onboarding', 'checkin', or 'general'.

        Returns:
            Dict with the agent's response text and the userId.
        """
        try:
            agent = create_coaching_agent(user_id)
            result = agent(
                f"[session_type={session_type}] [user_id={user_id}] {message}"
            )
            return {
                "response": str(result),
                "userId": user_id,
            }
        except Exception:
            logger.exception("Coaching agent invocation failed for user %s", user_id)
            return {
                "error": "agent_error",
                "message": "Coaching agent is temporarily unavailable. Please try again.",
                "userId": user_id,
            }
