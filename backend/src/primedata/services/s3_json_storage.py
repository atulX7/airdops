"""
S3 JSON storage service for PrimeData.

Handles saving and loading large JSON objects to/from S3 (MinIO) to reduce PostgreSQL storage costs.
Uses hybrid storage pattern: small JSON stays in DB, large JSON moves to S3.
"""

import json
from typing import Any, Dict, Optional, Tuple
from uuid import UUID

from loguru import logger
from primedata.storage.minio_client import MinIOClient

# Size threshold for moving JSON to S3 (1MB)
JSON_SIZE_THRESHOLD = 1024 * 1024  # 1MB

# Bucket for storing JSON metadata
METADATA_BUCKET = "primedata-exports"


def _get_json_size(data: Any) -> int:
    """Calculate size of JSON data when serialized.

    Args:
        data: Python object to serialize

    Returns:
        Size in bytes
    """
    try:
        json_str = json.dumps(data, default=str)
        return len(json_str.encode("utf-8"))
    except Exception as e:
        logger.error(f"Failed to calculate JSON size: {e}")
        return 0


def save_json_to_s3(
    workspace_id: UUID,
    product_id: UUID,
    field_name: str,
    data: Any,
    minio_client: Optional[MinIOClient] = None,
    version: Optional[int] = None,
    subfolder: str = "metadata",
) -> Optional[str]:
    """Save JSON data to S3 and return the S3 path.

    Args:
        workspace_id: Workspace UUID
        product_id: Product UUID
        field_name: Name of the field (e.g., "chunk_metrics", "readiness_fingerprint")
        data: Python object to serialize as JSON
        minio_client: Optional MinIO client (creates new one if not provided)
        version: Optional version number (for versioned storage)
        subfolder: Subfolder within the product path (default: "metadata")

    Returns:
        S3 path (key) if successful, None otherwise
    """
    try:
        client = minio_client or MinIOClient()

        # Build S3 path: ws/{workspace_id}/prod/{product_id}/metadata/{field_name}.json
        # Or: ws/{workspace_id}/prod/{product_id}/v/{version}/metadata/{field_name}.json
        if version is not None:
            key = f"ws/{workspace_id}/prod/{product_id}/v/{version}/{subfolder}/{field_name}.json"
        else:
            key = f"ws/{workspace_id}/prod/{product_id}/{subfolder}/{field_name}.json"

        # Save to S3
        success = client.put_json(METADATA_BUCKET, key, data)
        if success:
            logger.info(f"Saved {field_name} to S3: {key}")
            return key
        else:
            logger.error(f"Failed to save {field_name} to S3: {key}")
            return None
    except Exception as e:
        logger.error(f"Error saving {field_name} to S3: {e}", exc_info=True)
        return None


def load_json_from_s3(s3_path: str, minio_client: Optional[MinIOClient] = None) -> Optional[Any]:
    """Load JSON data from S3.

    Args:
        s3_path: S3 path (key) to the JSON object
        minio_client: Optional MinIO client (creates new one if not provided)

    Returns:
        Parsed JSON object (dict/list) or None if failed
    """
    try:
        client = minio_client or MinIOClient()
        data = client.get_json(METADATA_BUCKET, s3_path)
        if data is not None:
            logger.info(f"Loaded JSON from S3: {s3_path}")
        else:
            logger.warning(f"Failed to load JSON from S3: {s3_path}")
        return data
    except Exception as e:
        logger.error(f"Error loading JSON from S3 {s3_path}: {e}", exc_info=True)
        return None


def delete_json_from_s3(s3_path: str, minio_client: Optional[MinIOClient] = None) -> bool:
    """Delete JSON data from S3.

    Args:
        s3_path: S3 path (key) to the JSON object
        minio_client: Optional MinIO client (creates new one if not provided)

    Returns:
        True if successful, False otherwise
    """
    try:
        client = minio_client or MinIOClient()
        # MinIO client doesn't have a delete method in our wrapper, so we'll need to add it
        # For now, we'll use the underlying client
        from minio.error import S3Error

        try:
            client._ensure_buckets()
            client.client.remove_object(METADATA_BUCKET, s3_path)
            logger.info(f"Deleted JSON from S3: {s3_path}")
            return True
        except S3Error as e:
            logger.error(f"Failed to delete JSON from S3 {s3_path}: {e}")
            return False
    except Exception as e:
        logger.error(f"Error deleting JSON from S3 {s3_path}: {e}", exc_info=True)
        return False


def should_save_to_s3(data: Any, threshold: int = JSON_SIZE_THRESHOLD) -> bool:
    """Determine if JSON data should be saved to S3 based on size.

    Args:
        data: Python object to check
        threshold: Size threshold in bytes (default: 1MB)

    Returns:
        True if data should be saved to S3, False otherwise
    """
    size = _get_json_size(data)
    return size >= threshold


def save_product_json_field(
    workspace_id: UUID,
    product_id: UUID,
    field_name: str,
    data: Any,
    minio_client: Optional[MinIOClient] = None,
    threshold: int = JSON_SIZE_THRESHOLD,
) -> Tuple[Optional[str], bool]:
    """Save product JSON field, choosing between DB and S3 based on size.

    Args:
        workspace_id: Workspace UUID
        product_id: Product UUID
        field_name: Name of the field
        data: Python object to save
        minio_client: Optional MinIO client
        threshold: Size threshold for S3 storage (default: 1MB)

    Returns:
        Tuple of (s3_path, should_save_to_s3)
        - s3_path: S3 path if saved to S3, None if should stay in DB
        - should_save_to_s3: Whether data should be saved to S3
    """
    if should_save_to_s3(data, threshold):
        s3_path = save_json_to_s3(workspace_id, product_id, field_name, data, minio_client)
        return (s3_path, True)
    else:
        return (None, False)
