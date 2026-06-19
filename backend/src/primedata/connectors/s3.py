"""
AWS S3 connector for reading files from S3 buckets.
"""

import logging
import time
from typing import Any, Dict, List, Tuple

import boto3
from botocore.exceptions import ClientError

from ..storage.minio_client import minio_client
from ..storage.paths import safe_filename
from .base import BaseConnector

logger = logging.getLogger(__name__)


class S3Connector(BaseConnector):
    """Connector for reading files from AWS S3 buckets."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize S3 connector.

        Expected config:
        {
            'bucket_name': str,        # S3 bucket name
            'access_key_id': str,      # AWS Access Key ID
            'secret_access_key': str,   # AWS Secret Access Key
            'region': str,             # AWS region (optional, default: us-east-1)
            'prefix': str,              # Prefix/path within bucket (optional)
            'include': List[str],       # Include patterns (optional)
            'exclude': List[str],       # Exclude patterns (optional)
            'max_file_size': int        # Maximum file size in bytes (default: 100MB)
        }
        """
        super().__init__(config)
        self.bucket_name = config.get("bucket_name", "")
        self.access_key_id = config.get("access_key_id", "")
        self.secret_access_key = config.get("secret_access_key", "")
        self.region = config.get("region", "us-east-1")
        self.prefix = config.get("prefix", "")
        self.include_patterns = config.get("include", ["*"])
        self.exclude_patterns = config.get("exclude", [])
        self.max_file_size = config.get("max_file_size", 100 * 1024 * 1024)  # 100MB

        # Initialize S3 client
        self.s3_client = boto3.client(
            "s3", aws_access_key_id=self.access_key_id, aws_secret_access_key=self.secret_access_key, region_name=self.region
        )

    def validate_config(self) -> Tuple[bool, str]:
        """Validate S3 connector configuration."""
        if not self.bucket_name:
            return False, "Bucket name is required"
        if not self.access_key_id:
            return False, "AWS Access Key ID is required"
        if not self.secret_access_key:
            return False, "AWS Secret Access Key is required"
        return True, "Configuration is valid"

    def test_connection(self) -> Tuple[bool, str]:
        """Test connection to S3 bucket."""
        try:
            # Try to list bucket or head bucket
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            return True, f"Successfully connected to S3 bucket: {self.bucket_name}"
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            if error_code == "404":
                return False, f"S3 bucket not found: {self.bucket_name}"
            elif error_code == "403":
                return False, f"Access denied to S3 bucket: {self.bucket_name}"
            else:
                return False, f"Error connecting to S3: {str(e)}"
        except Exception as e:
            return False, f"Error connecting to S3: {str(e)}"

    def sync_full(self, output_bucket: str, output_prefix: str) -> Dict[str, Any]:
        """Sync files from S3 to MinIO/GCS."""
        start_time = time.time()
        files_processed = 0
        bytes_transferred = 0
        errors = 0
        details = {"files_processed": [], "files_failed": [], "files_skipped": []}

        try:
            # List objects in S3 bucket
            paginator = self.s3_client.get_paginator("list_objects_v2")
            pages = paginator.paginate(Bucket=self.bucket_name, Prefix=self.prefix)

            for page in pages:
                if "Contents" not in page:
                    continue

                for obj in page["Contents"]:
                    try:
                        key = obj["Key"]
                        file_size = obj["Size"]

                        # Skip if too large
                        if file_size > self.max_file_size:
                            details["files_skipped"].append({"key": key, "reason": f"File too large: {file_size} bytes"})
                            continue

                        # Download from S3
                        response = self.s3_client.get_object(Bucket=self.bucket_name, Key=key)
                        content = response["Body"].read()

                        # Upload to MinIO/GCS
                        safe_key = safe_filename(key)
                        minio_key = f"{output_prefix}{safe_key}"

                        success = minio_client.put_bytes(
                            output_bucket, minio_key, content, response.get("ContentType", "application/octet-stream")
                        )

                        if success:
                            files_processed += 1
                            bytes_transferred += len(content)
                            details["files_processed"].append({"key": key, "minio_key": minio_key, "size": len(content)})
                        else:
                            errors += 1
                            details["files_failed"].append({"key": key, "error": "Failed to upload to storage"})
                    except Exception as e:
                        errors += 1
                        details["files_failed"].append({"key": obj.get("Key", "unknown"), "error": str(e)})
                        logger.error(f"Error processing S3 object: {e}")

        except Exception as e:
            logger.error(f"Error during S3 sync: {e}")
            return {"files": 0, "bytes": 0, "errors": 1, "duration": time.time() - start_time, "details": {"error": str(e)}}

        duration = time.time() - start_time
        return {
            "files": files_processed,
            "bytes": bytes_transferred,
            "errors": errors,
            "duration": duration,
            "details": details,
        }

    def _get_config_schema(self) -> Dict[str, Any]:
        """Get JSON schema for S3 connector configuration."""
        return {
            "type": "object",
            "properties": {
                "bucket_name": {"type": "string", "description": "S3 bucket name"},
                "access_key_id": {"type": "string", "description": "AWS Access Key ID"},
                "secret_access_key": {"type": "string", "description": "AWS Secret Access Key"},
                "region": {"type": "string", "default": "us-east-1", "description": "AWS region"},
                "prefix": {"type": "string", "default": "", "description": "Prefix/path within bucket"},
                "include": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": ["*"],
                    "description": "Include file patterns",
                },
                "exclude": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": [],
                    "description": "Exclude file patterns",
                },
                "max_file_size": {
                    "type": "integer",
                    "minimum": 1024,
                    "default": 104857600,
                    "description": "Maximum file size in bytes (default: 100MB)",
                },
            },
            "required": ["bucket_name", "access_key_id", "secret_access_key"],
        }
