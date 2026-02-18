"""Unit tests for the REGAIN ingestion retry module.

Tests retry_with_backoff for correct retry count, backoff timing,
exception propagation, and logging behavior.

**Validates: Requirements 1.5, 2.4, 3.4**
"""

import importlib
from unittest.mock import MagicMock, patch

import pytest

_retry_mod = importlib.import_module(
    "backend.lambda.market_intel.ingestion.retry"
)
retry_with_backoff = _retry_mod.retry_with_backoff


class TestRetryWithBackoff:
    """Tests for retry_with_backoff."""

    def test_succeeds_on_first_call(self) -> None:
        """Returns immediately when fn succeeds on first attempt."""
        fn = MagicMock(return_value="ok")
        result = retry_with_backoff(fn, max_retries=3, base_delay=0.0)

        assert result == "ok"
        assert fn.call_count == 1

    def test_succeeds_after_retries(self) -> None:
        """Returns result when fn succeeds after transient failures."""
        fn = MagicMock(side_effect=[ValueError("fail"), ValueError("fail"), "ok"])
        result = retry_with_backoff(fn, max_retries=3, base_delay=0.0)

        assert result == "ok"
        assert fn.call_count == 3

    def test_raises_after_exhausting_retries(self) -> None:
        """Re-raises the last exception after all retries are exhausted."""
        fn = MagicMock(side_effect=RuntimeError("boom"))

        with pytest.raises(RuntimeError, match="boom"):
            retry_with_backoff(fn, max_retries=3, base_delay=0.0)

        assert fn.call_count == 3

    def test_raises_last_exception(self) -> None:
        """Re-raises the exception from the final attempt, not earlier ones."""
        fn = MagicMock(
            side_effect=[ValueError("first"), TypeError("second"), OSError("third")]
        )

        with pytest.raises(OSError, match="third"):
            retry_with_backoff(fn, max_retries=3, base_delay=0.0)

    @patch("backend.lambda.market_intel.ingestion.retry.time.sleep")
    def test_exponential_backoff_delays(self, mock_sleep: MagicMock) -> None:
        """Applies exponential backoff: base_delay * 2^attempt."""
        fn = MagicMock(side_effect=[ValueError("a"), ValueError("b"), "ok"])
        retry_with_backoff(fn, max_retries=3, base_delay=1.0)

        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(1.0)   # 1.0 * 2^0
        mock_sleep.assert_any_call(2.0)   # 1.0 * 2^1

    @patch("backend.lambda.market_intel.ingestion.retry.time.sleep")
    def test_all_three_delays_on_full_failure(self, mock_sleep: MagicMock) -> None:
        """Delays are 1s, 2s, 4s for default params when all retries fail."""
        fn = MagicMock(side_effect=RuntimeError("fail"))

        with pytest.raises(RuntimeError):
            retry_with_backoff(fn, max_retries=3, base_delay=1.0)

        assert mock_sleep.call_count == 3
        calls = [c.args[0] for c in mock_sleep.call_args_list]
        assert calls == [1.0, 2.0, 4.0]

    def test_logs_retry_attempts(self) -> None:
        """Logs a warning for each retry attempt."""
        fn = MagicMock(side_effect=[ValueError("oops"), "ok"])

        with patch.object(_retry_mod.logger, "warning") as mock_warn:
            retry_with_backoff(fn, max_retries=3, base_delay=0.0)

        assert mock_warn.call_count == 1
        assert "1/3" in mock_warn.call_args[0][0] % mock_warn.call_args[0][1:]

    def test_logs_error_on_exhaustion(self) -> None:
        """Logs an error when all retries are exhausted."""
        fn = MagicMock(side_effect=RuntimeError("fatal"))

        with patch.object(_retry_mod.logger, "error") as mock_err:
            with pytest.raises(RuntimeError):
                retry_with_backoff(fn, max_retries=2, base_delay=0.0)

        assert mock_err.call_count == 1

    def test_custom_max_retries(self) -> None:
        """Respects custom max_retries parameter."""
        fn = MagicMock(side_effect=RuntimeError("fail"))

        with pytest.raises(RuntimeError):
            retry_with_backoff(fn, max_retries=5, base_delay=0.0)

        assert fn.call_count == 5

    def test_single_retry(self) -> None:
        """Works with max_retries=1 — calls fn exactly once."""
        fn = MagicMock(side_effect=RuntimeError("fail"))

        with pytest.raises(RuntimeError):
            retry_with_backoff(fn, max_retries=1, base_delay=0.0)

        assert fn.call_count == 1
