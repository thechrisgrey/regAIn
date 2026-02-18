"""Shared retry logic with exponential backoff for ingestion pipeline."""

import logging
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)


def retry_with_backoff(
    fn: Callable,
    max_retries: int = 3,
    base_delay: float = 1.0,
) -> Any:
    """Execute fn with exponential backoff retry.

    Calls fn() and returns its result. On failure, retries up to max_retries
    times with exponential backoff delays (base_delay * 2^attempt).

    Default delays: 1s, 2s, 4s.

    Args:
        fn: Callable to execute. Takes no arguments.
        max_retries: Maximum number of retry attempts.
        base_delay: Base delay in seconds. Multiplied by 2^attempt.

    Returns:
        The return value of fn().

    Raises:
        Exception: The last exception raised by fn after all retries
            are exhausted.
    """
    last_exception: Exception | None = None

    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as exc:
            last_exception = exc
            delay = base_delay * (2 ** attempt)
            logger.warning(
                "Retry attempt %d/%d failed: %s. Retrying in %.1fs...",
                attempt + 1,
                max_retries,
                exc,
                delay,
            )
            time.sleep(delay)

    logger.error(
        "All %d retries exhausted. Last error: %s",
        max_retries,
        last_exception,
    )
    raise last_exception  # type: ignore[misc]
