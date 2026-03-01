"""Simple circuit breaker for AgentCore Gateway calls.

Opens after consecutive failures and recovers after a timeout,
falling back to direct tool invocation while the circuit is open.
"""

import logging
import threading
import time

logger = logging.getLogger(__name__)

_FAILURE_THRESHOLD = 3
_RECOVERY_TIMEOUT = 30  # seconds


class CircuitBreaker:
    """Thread-safe circuit breaker with consecutive-failure counter."""

    def __init__(
        self,
        failure_threshold: int = _FAILURE_THRESHOLD,
        recovery_timeout: float = _RECOVERY_TIMEOUT,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._consecutive_failures = 0
        self._last_failure_time: float = 0.0
        self._lock = threading.Lock()

    @property
    def is_open(self) -> bool:
        """True if the circuit is open (failures >= threshold and recovery timeout hasn't elapsed)."""
        with self._lock:
            if self._consecutive_failures < self._failure_threshold:
                return False
            elapsed = time.time() - self._last_failure_time
            if elapsed >= self._recovery_timeout:
                # Recovery timeout elapsed — allow a probe attempt.
                return False
            return True

    def record_success(self) -> None:
        """Reset the failure counter on success."""
        with self._lock:
            self._consecutive_failures = 0

    def record_failure(self) -> None:
        """Increment the consecutive failure counter."""
        with self._lock:
            self._consecutive_failures += 1
            self._last_failure_time = time.time()
            if self._consecutive_failures >= self._failure_threshold:
                logger.warning(
                    "Circuit breaker opened after %d consecutive failures",
                    self._consecutive_failures,
                )


# Module-level singleton for the Gateway circuit.
gateway_circuit = CircuitBreaker()
