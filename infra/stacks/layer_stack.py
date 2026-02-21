"""REGAIN Layer Stack — Shared Lambda Layer for Strands Agents SDK."""
from pathlib import Path

import aws_cdk as cdk
from aws_cdk import aws_lambda as _lambda
from constructs import Construct


class LayerStack(cdk.Stack):
    """Shared Lambda Layer containing the strands-agents Python package."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self._strands_layer = _lambda.LayerVersion(
            self,
            "RegainStrandsAgentsLayer",
            layer_version_name="RegainStrandsAgents",
            code=_lambda.Code.from_asset(
                str(Path(__file__).resolve().parent.parent / "layer_build"),
            ),
            compatible_runtimes=[_lambda.Runtime.PYTHON_3_12],
            description="Strands Agents SDK for REGAIN coaching and voice Lambdas",
        )

    @property
    def strands_layer(self) -> _lambda.LayerVersion:
        """The Strands Agents Lambda Layer."""
        return self._strands_layer
