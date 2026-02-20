"""Property test for environment-based table configuration.

**Property 3: Environment-Based Table Configuration**
**Validates: Requirements 3.2**

Verifies that the DynamoDB data access layer reads table names from
environment variables rather than using hardcoded values.
"""

import importlib
import os
import sys
from unittest.mock import patch, MagicMock

import pytest
from hypothesis import given, settings, strategies as st

_DYNAMODB_MODULE = "backend.lambda.shared.dynamodb"

# Ensure the module is imported so patch targets resolve.
_dynamodb_mod = importlib.import_module(_DYNAMODB_MODULE)


# Strategy: generate non-empty table name strings (simulating env var values)
table_name_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P")),
    min_size=1,
    max_size=64,
).filter(lambda s: s.strip())


@given(
    user_profiles=table_name_strategy,
    campaigns=table_name_strategy,
    mission_history=table_name_strategy,
    evidence_vault=table_name_strategy,
    market_data=table_name_strategy,
)
@settings(max_examples=100)
def test_table_names_come_from_environment_variables(
    user_profiles: str,
    campaigns: str,
    mission_history: str,
    evidence_vault: str,
    market_data: str,
) -> None:
    """For any set of table name strings provided via environment variables,
    the DynamoDBClient must use exactly those values when resolving tables.

    This confirms no table name is hardcoded in the data access layer.
    """
    env = {
        "USER_PROFILES_TABLE": user_profiles,
        "CAMPAIGNS_TABLE": campaigns,
        "MISSION_HISTORY_TABLE": mission_history,
        "EVIDENCE_VAULT_TABLE": evidence_vault,
        "MARKET_DATA_TABLE": market_data,
    }

    mock_resource = MagicMock()
    mock_boto3 = MagicMock()
    mock_boto3.resource.return_value = mock_resource

    with patch.dict(os.environ, env, clear=False):
        # Directly set the module attribute so DynamoDBClient.__init__
        # picks up the mock regardless of prior import state.
        original_boto3 = _dynamodb_mod.boto3
        _dynamodb_mod.boto3 = mock_boto3
        try:
            client = _dynamodb_mod.DynamoDBClient()
        finally:
            _dynamodb_mod.boto3 = original_boto3

    # Verify boto3.Table was called with each env-var-provided name
    expected_calls = {user_profiles, campaigns, mission_history,
                     evidence_vault, market_data}
    actual_calls = {
        call.args[0] for call in mock_resource.Table.call_args_list
    }
    assert expected_calls == actual_calls, (
        f"Expected table names {expected_calls}, got {actual_calls}"
    )


@given(table_name_value=table_name_strategy)
@settings(max_examples=100)
def test_missing_env_var_raises_on_access(table_name_value: str) -> None:
    """For any logical table name whose env var is unset, accessing it
    must raise ValueError rather than silently using a default.
    """
    # Set only one env var, leave the rest unset
    env = {"USER_PROFILES_TABLE": table_name_value}
    cleared = {
        "CAMPAIGNS_TABLE": "",
        "MISSION_HISTORY_TABLE": "",
        "EVIDENCE_VAULT_TABLE": "",
        "MARKET_DATA_TABLE": "",
    }

    mock_resource = MagicMock()
    mock_boto3 = MagicMock()
    mock_boto3.resource.return_value = mock_resource

    with patch.dict(os.environ, {**env, **cleared}, clear=False):
        original_boto3 = _dynamodb_mod.boto3
        _dynamodb_mod.boto3 = mock_boto3
        try:
            client = _dynamodb_mod.DynamoDBClient()
        finally:
            _dynamodb_mod.boto3 = original_boto3

        # Accessing an unconfigured table must raise
        with pytest.raises(ValueError, match="not configured"):
            client._get_table("campaigns")
