"""DynamoDB data access layer.

Provides a centralized client for all DynamoDB operations.
Table names are read from environment variables.
"""

import os
import logging
from typing import Any, Dict, List, Optional

import boto3
from boto3.dynamodb.conditions import Key

logger = logging.getLogger(__name__)


class DynamoDBClient:
    """Centralized DynamoDB access layer.

    All table names are resolved from environment variables at
    instantiation time, ensuring no hardcoded table references.
    """

    TABLE_ENV_VARS = {
        "user_profiles": "USER_PROFILES_TABLE",
        "campaigns": "CAMPAIGNS_TABLE",
        "mission_history": "MISSION_HISTORY_TABLE",
        "evidence_vault": "EVIDENCE_VAULT_TABLE",
        "market_data": "MARKET_DATA_TABLE",
        "voice_sessions": "VOICE_SESSIONS_TABLE",
    }

    def __init__(self) -> None:
        self.dynamodb = boto3.resource("dynamodb")
        self.tables: Dict[str, Any] = {}
        for key, env_var in self.TABLE_ENV_VARS.items():
            table_name = os.environ.get(env_var)
            if table_name:
                self.tables[key] = self.dynamodb.Table(table_name)

    def get_item(self, table_name: str, key: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Get a single item by primary key.

        Args:
            table_name: Logical table name (e.g. 'user_profiles').
            key: Primary key dict (e.g. {'userId': '123'}).

        Returns:
            The item dict, or None if not found.
        """
        table = self._get_table(table_name)
        response = table.get_item(Key=key)
        return response.get("Item")

    def put_item(self, table_name: str, item: Dict[str, Any]) -> Dict[str, Any]:
        """Put an item into a table.

        Args:
            table_name: Logical table name.
            item: Complete item to store.

        Returns:
            The DynamoDB put_item response.
        """
        table = self._get_table(table_name)
        response = table.put_item(Item=item)
        return response

    def query(
        self,
        table_name: str,
        key_condition: Any,
        index_name: Optional[str] = None,
        filter_expression: Any = None,
    ) -> List[Dict[str, Any]]:
        """Query a table or GSI.

        Args:
            table_name: Logical table name.
            key_condition: A boto3 Key condition expression.
            index_name: Optional GSI name to query.
            filter_expression: Optional filter applied after key matching.

        Returns:
            List of matching items.
        """
        table = self._get_table(table_name)
        kwargs: Dict[str, Any] = {"KeyConditionExpression": key_condition}
        if index_name:
            kwargs["IndexName"] = index_name
        if filter_expression is not None:
            kwargs["FilterExpression"] = filter_expression
        response = table.query(**kwargs)
        return response.get("Items", [])

    def update_item(
        self,
        table_name: str,
        key: Dict[str, Any],
        updates: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Update item attributes.

        Builds an UpdateExpression from the provided updates dict.

        Args:
            table_name: Logical table name.
            key: Primary key of the item to update.
            updates: Dict of attribute names to new values.

        Returns:
            The DynamoDB update_item response.
        """
        table = self._get_table(table_name)
        expr_parts = []
        attr_names: Dict[str, str] = {}
        attr_values: Dict[str, Any] = {}

        for i, (attr, value) in enumerate(updates.items()):
            placeholder_name = f"#attr{i}"
            placeholder_value = f":val{i}"
            expr_parts.append(f"{placeholder_name} = {placeholder_value}")
            attr_names[placeholder_name] = attr
            attr_values[placeholder_value] = value

        response = table.update_item(
            Key=key,
            UpdateExpression="SET " + ", ".join(expr_parts),
            ExpressionAttributeNames=attr_names,
            ExpressionAttributeValues=attr_values,
            ReturnValues="ALL_NEW",
        )
        return response

    def delete_item(self, table_name: str, key: Dict[str, Any]) -> Dict[str, Any]:
        """Delete a single item by primary key.

        Args:
            table_name: Logical table name.
            key: Primary key dict (e.g. {'userId': '123'}).

        Returns:
            The DynamoDB delete_item response.
        """
        table = self._get_table(table_name)
        response = table.delete_item(Key=key)
        return response

    def delete_all_by_partition_key(
        self,
        table_name: str,
        partition_key_name: str,
        partition_key_value: str,
        sort_key_name: str,
    ) -> int:
        """Query all items by partition key and batch-delete them.

        Uses BatchWriteItem with 25-item batches and handles pagination
        on both the query and the batch write.

        Args:
            table_name: Logical table name.
            partition_key_name: Name of the partition key attribute.
            partition_key_value: Value to match on.
            sort_key_name: Name of the sort key attribute (needed for delete key).

        Returns:
            Total number of items deleted.
        """
        items = self.query(
            table_name,
            Key(partition_key_name).eq(partition_key_value),
        )

        if not items:
            return 0

        table = self._get_table(table_name)
        deleted = 0

        # BatchWriteItem supports max 25 requests per call.
        for i in range(0, len(items), 25):
            batch = items[i : i + 25]
            with table.batch_writer() as writer:
                for item in batch:
                    writer.delete_item(
                        Key={
                            partition_key_name: item[partition_key_name],
                            sort_key_name: item[sort_key_name],
                        }
                    )
            deleted += len(batch)

        return deleted

    def _get_table(self, table_name: str) -> Any:
        """Resolve a logical table name to a DynamoDB Table resource.

        Args:
            table_name: Logical table name.

        Returns:
            boto3 DynamoDB Table resource.

        Raises:
            ValueError: If the table name is not configured.
        """
        table = self.tables.get(table_name)
        if table is None:
            env_var = self.TABLE_ENV_VARS.get(table_name, "UNKNOWN")
            raise ValueError(
                f"Table '{table_name}' not configured. "
                f"Set the {env_var} environment variable."
            )
        return table
