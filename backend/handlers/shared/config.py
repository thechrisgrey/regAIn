"""Environment configuration.

Centralizes access to environment variables used by Lambda functions.
"""

import os
from typing import Optional


class Config:
    """Environment configuration for Lambda functions.

    All AWS resource identifiers are read from environment variables
    set by the CDK ApiStack during Lambda creation.
    """

    @staticmethod
    def user_profiles_table() -> Optional[str]:
        """Return the UserProfiles table name."""
        return os.environ.get("USER_PROFILES_TABLE")

    @staticmethod
    def campaigns_table() -> Optional[str]:
        """Return the Campaigns table name."""
        return os.environ.get("CAMPAIGNS_TABLE")

    @staticmethod
    def mission_history_table() -> Optional[str]:
        """Return the MissionHistory table name."""
        return os.environ.get("MISSION_HISTORY_TABLE")

    @staticmethod
    def evidence_vault_table() -> Optional[str]:
        """Return the EvidenceVault table name."""
        return os.environ.get("EVIDENCE_VAULT_TABLE")

    @staticmethod
    def market_data_table() -> Optional[str]:
        """Return the MarketData table name."""
        return os.environ.get("MARKET_DATA_TABLE")

    @staticmethod
    def region() -> str:
        """Return the AWS region."""
        return os.environ.get("AWS_REGION", "us-east-1")
