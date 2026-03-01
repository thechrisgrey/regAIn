"""Structured JSON logging with request context.

Provides a LoggerAdapter that injects requestId, userId, and traceId
into every log record for CloudWatch Logs Insights queries.
"""

import json
import logging
import os
from typing import Any, Dict, Optional


class _JsonFormatter(logging.Formatter):
    """Formats log records as single-line JSON."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: Dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }

        # Inject context fields from LoggerAdapter's extra dict.
        for key in ("requestId", "userId", "traceId"):
            value = getattr(record, key, None)
            if value:
                log_entry[key] = value

        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, default=str)


def get_logger(
    event: Optional[Dict[str, Any]] = None,
    name: str = __name__,
) -> logging.LoggerAdapter:
    """Create a structured logger with request context.

    Args:
        event: API Gateway or WebSocket event dict.
            REST events use requestContext.requestId.
            WebSocket events use requestContext.connectionId.
        name: Logger name (defaults to module name).

    Returns:
        A LoggerAdapter that injects requestId, userId, and traceId.
    """
    logger = logging.getLogger(name)

    # Only add the JSON handler if not already set up (avoid duplicates
    # across multiple invocations in the same Lambda container).
    if not any(isinstance(h.formatter, _JsonFormatter) for h in logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(_JsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        # Prevent duplicate output from root logger propagation.
        logger.propagate = False

    extra: Dict[str, str] = {
        "requestId": "",
        "userId": "",
        "traceId": os.environ.get("_X_AMZN_TRACE_ID", ""),
    }

    if event:
        request_ctx = event.get("requestContext", {})
        # REST API uses requestId; WebSocket uses connectionId.
        extra["requestId"] = (
            request_ctx.get("requestId", "")
            or request_ctx.get("connectionId", "")
        )

        # Extract userId from Cognito authorizer claims.
        try:
            extra["userId"] = (
                request_ctx.get("authorizer", {})
                .get("claims", {})
                .get("sub", "")
            )
        except (AttributeError, TypeError):
            pass

    return logging.LoggerAdapter(logger, extra)
