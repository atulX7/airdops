"""
Base connector class for data source integrations.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Tuple


class BaseConnector(ABC):
    """Abstract base class for all data source connectors."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize connector with configuration.

        Args:
            config: Connector-specific configuration dictionary
        """
        self.config = config

    @abstractmethod
    def test_connection(self) -> Tuple[bool, str]:
        """Test connection to the data source.

        Returns:
            Tuple of (success: bool, message: str)
        """
        pass

    @abstractmethod
    def sync_full(self, output_bucket: str, output_prefix: str) -> Dict[str, Any]:
        """Perform full synchronization of data source.

        Args:
            output_bucket: MinIO bucket to store data
            output_prefix: Prefix path within bucket

        Returns:
            Dictionary with sync results:
            {
                'files': int,      # Number of files processed
                'bytes': int,      # Total bytes transferred
                'errors': int,     # Number of errors encountered
                'duration': float, # Sync duration in seconds
                'details': dict    # Connector-specific details
            }
        """
        pass

    def sync_incremental(self, cursor: Optional[str], output_bucket: str, output_prefix: str) -> Dict[str, Any]:
        """Perform incremental synchronization of data source.

        Args:
            cursor: Cursor from previous sync (optional)
            output_bucket: MinIO bucket to store data
            output_prefix: Prefix path within bucket

        Returns:
            Dictionary with sync results (same format as sync_full)
        """
        # Default implementation falls back to full sync
        # Subclasses can override for true incremental behavior
        return self.sync_full(output_bucket, output_prefix)

    def validate_config(self) -> Tuple[bool, str]:
        """Validate connector configuration.

        Returns:
            Tuple of (valid: bool, error_message: str)
        """
        return True, "Configuration is valid"

    def get_connector_info(self) -> Dict[str, Any]:
        """Get connector metadata and capabilities.

        Returns:
            Dictionary with connector information
        """
        return {
            "name": self.__class__.__name__,
            "supports_incremental": hasattr(self, "sync_incremental")
            and self.sync_incremental != BaseConnector.sync_incremental,
            "config_schema": self._get_config_schema(),
        }

    def _get_config_schema(self) -> Dict[str, Any]:
        """Get JSON schema for connector configuration.

        Returns:
            JSON schema dictionary
        """
        return {"type": "object", "properties": {}, "required": []}
