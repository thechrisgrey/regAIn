"""Lightweight CloudWatch business metrics emitter for REGAIN.

Emits custom metrics to the ``REGAIN/Business`` namespace.  Failures are
logged as warnings but never bubble up — metric emission must not break
request handling.

Set the ``REGAIN_METRICS_DISABLED=true`` environment variable to disable
emission entirely (useful in tests).
"""

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_NAMESPACE = "REGAIN/Business"
_DISABLED = os.environ.get("REGAIN_METRICS_DISABLED", "").lower() == "true"

# Lazy-initialized boto3 CloudWatch client.
_cw_client: Any = None


def _get_client() -> Any:
    """Return a lazily-created CloudWatch client."""
    global _cw_client
    if _cw_client is None:
        import boto3

        _cw_client = boto3.client("cloudwatch")
    return _cw_client


def emit_metric(
    metric_name: str,
    value: float = 1.0,
    unit: str = "Count",
    dimensions: dict[str, str] | None = None,
    namespace: str | None = None,
) -> None:
    """Emit a single metric data point to CloudWatch.

    Args:
        metric_name: The metric name (e.g. ``missions_completed``).
        value: Numeric value (default 1.0).
        unit: CloudWatch unit string (default ``"Count"``).
        dimensions: Optional mapping of dimension name to value.
        namespace: CloudWatch namespace (default ``REGAIN/Business``).
    """
    if _DISABLED:
        return

    try:
        metric_data: dict[str, Any] = {
            "MetricName": metric_name,
            "Value": value,
            "Unit": unit,
        }
        if dimensions:
            metric_data["Dimensions"] = [
                {"Name": k, "Value": v} for k, v in dimensions.items()
            ]

        _get_client().put_metric_data(
            Namespace=namespace or _NAMESPACE,
            MetricData=[metric_data],
        )
    except Exception:
        logger.warning("Failed to emit metric %s", metric_name, exc_info=True)
