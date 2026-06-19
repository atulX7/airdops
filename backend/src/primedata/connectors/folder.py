"""
Folder connector for reading files from local filesystem.
"""

import fnmatch
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

from ..storage.minio_client import minio_client
from ..storage.paths import safe_filename
from .base import BaseConnector

logger = logging.getLogger(__name__)


class FolderConnector(BaseConnector):
    """Connector for reading files from local filesystem directories."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize folder connector.

        Expected config:
        {
            'root_path': str,           # Root directory path
            'include': List[str],       # Include patterns (e.g., ['*.txt', '*.pdf'])
            'exclude': List[str],       # Exclude patterns (e.g., ['*.tmp', '*.log'])
            'recursive': bool,          # Whether to scan subdirectories (default: True)
            'max_file_size': int        # Maximum file size in bytes (default: 100MB)
        }
        """
        super().__init__(config)
        self.root_path = config.get("root_path", "")
        self.include_patterns = config.get("include", ["*"])
        self.exclude_patterns = config.get("exclude", [])
        self.recursive = config.get("recursive", True)
        self.max_file_size = config.get("max_file_size", 100 * 1024 * 1024)  # 100MB

    def validate_config(self) -> Tuple[bool, str]:
        """Validate folder connector configuration.

        If no root_path is provided, this indicates upload mode and validation passes.
        """
        # If no path provided, this is upload mode - validation passes
        if not self.root_path:
            return True, "Configuration is valid (upload mode)"

        # Path mode - validate the server-side path
        if not isinstance(self.root_path, str):
            return False, "Root path must be a string"

        # Check if path exists
        if not os.path.exists(self.root_path):
            return False, f"Path does not exist: {self.root_path}"

        if not os.path.isdir(self.root_path):
            return False, f"Path is not a directory: {self.root_path}"

        # Check if path is readable
        if not os.access(self.root_path, os.R_OK):
            return False, f"Path is not readable: {self.root_path}"

        if self.max_file_size <= 0:
            return False, "Max file size must be positive"

        return True, "Configuration is valid"

    def test_connection(self) -> Tuple[bool, str]:
        """Test connection by checking if the root path is accessible.

        If no path is provided, this indicates upload mode and returns success.
        """
        try:
            # If no path provided, this is upload mode - no path validation needed
            if not self.root_path:
                return True, "Folder datasource configured for file uploads. Use the upload endpoint to add files."

            # Path mode - validate the server-side path
            if not os.path.exists(self.root_path):
                return False, f"Path does not exist: {self.root_path}"

            if not os.path.isdir(self.root_path):
                return False, f"Path is not a directory: {self.root_path}"

            if not os.access(self.root_path, os.R_OK):
                return False, f"Path is not readable: {self.root_path}"

            # Try to list one file to ensure we can read the directory
            try:
                next(os.scandir(self.root_path), None)
            except PermissionError:
                return False, f"Permission denied accessing: {self.root_path}"

            return True, f"Successfully connected to directory: {self.root_path}"

        except Exception as e:
            return False, f"Error accessing {self.root_path}: {str(e)}"

    def _should_include_file(self, file_path: str) -> bool:
        """Check if file should be included based on patterns."""
        filename = os.path.basename(file_path)

        # Check exclude patterns first
        for pattern in self.exclude_patterns:
            if fnmatch.fnmatch(filename, pattern) or fnmatch.fnmatch(file_path, pattern):
                return False

        # If no include patterns specified, include all files (after exclude check)
        if not self.include_patterns:
            return True

        # Check include patterns
        for pattern in self.include_patterns:
            if fnmatch.fnmatch(filename, pattern) or fnmatch.fnmatch(file_path, pattern):
                return True

        return False

    def _get_files_to_process(self) -> List[Path]:
        """Get list of files to process based on configuration."""
        files = []
        root = Path(self.root_path)

        # Log path details for debugging
        logger.info(f"Scanning directory: {root} (absolute: {root.resolve()})")
        logger.info(f"Path exists: {root.exists()}")
        logger.info(f"Is directory: {root.is_dir() if root.exists() else 'N/A'}")

        if not root.exists():
            logger.error(f"Directory does not exist: {self.root_path}")
            logger.error(f"Absolute path: {root.resolve()}")
            # Try to list parent directory to see what's available
            parent = root.parent
            if parent.exists():
                try:
                    items = list(parent.iterdir())
                    logger.info(f"Parent directory '{parent}' contains: {[str(p.name) for p in items[:10]]}")
                except Exception as pe:
                    logger.warning(f"Could not list parent directory: {pe}")
            raise FileNotFoundError(f"Directory does not exist: {self.root_path}")

        if not root.is_dir():
            raise NotADirectoryError(f"Path is not a directory: {self.root_path}")

        try:
            if self.recursive:
                # Recursive scan
                logger.info(f"Performing recursive scan...")
                for file_path in root.rglob("*"):
                    if file_path.is_file():
                        logger.debug(f"Found file: {file_path}")
                        if self._should_include_file(str(file_path)):
                            logger.debug(f"Including file: {file_path}")
                            files.append(file_path)
                        else:
                            logger.debug(f"Excluding file: {file_path}")
            else:
                # Non-recursive scan
                logger.info(f"Performing non-recursive scan...")
                for file_path in root.iterdir():
                    if file_path.is_file():
                        logger.debug(f"Found file: {file_path}")
                        if self._should_include_file(str(file_path)):
                            logger.debug(f"Including file: {file_path}")
                            files.append(file_path)
                        else:
                            logger.debug(f"Excluding file: {file_path}")

            logger.info(f"Total files found: {len(files)}")
            if len(files) > 0:
                logger.info(f"Sample files: {[str(f) for f in files[:5]]}")
        except Exception as e:
            logger.error(f"Error scanning directory {self.root_path}: {e}")
            import traceback

            logger.error(f"Traceback: {traceback.format_exc()}")
            raise

        return files

    def sync_full(self, output_bucket: str, output_prefix: str) -> Dict[str, Any]:
        """Read all files from the directory and upload to MinIO/GCS.

        If no root_path is provided (upload mode), lists files already in storage
        for the given output_prefix and returns them as already processed.
        """
        start_time = time.time()
        files_processed = 0
        bytes_transferred = 0
        errors = 0
        details = {"files_processed": [], "files_failed": [], "files_skipped": []}

        # If no path provided, this is upload mode - list files from storage
        if not self.root_path:
            logger.info(
                f"Folder connector in upload mode - listing files from storage (bucket: {output_bucket}, prefix: {output_prefix})"
            )
            try:
                # List all objects in storage with the given prefix
                objects = minio_client.list_objects(output_bucket, output_prefix)
                logger.info(f"Found {len(objects)} files in storage with prefix {output_prefix}")

                files_processed = len(objects)
                for obj in objects:
                    file_size = obj.get("size", 0)
                    bytes_transferred += file_size
                    # Extract filename from the object key (remove prefix)
                    object_key = obj.get("name", "")
                    if object_key.startswith(output_prefix):
                        filename = object_key[len(output_prefix) :]
                    else:
                        filename = Path(object_key).name

                    details["files_processed"].append(
                        {
                            "path": filename,
                            "key": object_key,
                            "size": file_size,
                            "content_type": obj.get("content_type", "application/octet-stream"),
                        }
                    )

                logger.info(
                    f"Upload mode sync completed: {files_processed} files already in storage, {bytes_transferred} bytes"
                )

                return {
                    "files": files_processed,
                    "bytes": bytes_transferred,
                    "errors": 0,
                    "duration": time.time() - start_time,
                    "details": {
                        **details,
                        "message": f"Found {files_processed} files already in storage (upload mode)",
                    },
                }
            except Exception as e:
                logger.error(f"Error listing files from storage in upload mode: {e}", exc_info=True)
                return {
                    "files": 0,
                    "bytes": 0,
                    "errors": 1,
                    "duration": time.time() - start_time,
                    "details": {"error": f"Failed to list files from storage: {str(e)}"},
                }

        logger.info(f"Starting folder sync from {self.root_path}")

        try:
            files_to_process = self._get_files_to_process()
            logger.info(f"Found {len(files_to_process)} files to process")
            logger.info(f"Root path: {self.root_path}")
            logger.info(f"Include patterns: {self.include_patterns}")
            logger.info(f"Exclude patterns: {self.exclude_patterns}")
            logger.info(f"Recursive: {self.recursive}")

            for file_path in files_to_process:
                try:
                    # Check file size
                    file_size = file_path.stat().st_size
                    if file_size > self.max_file_size:
                        details["files_skipped"].append(
                            {"path": str(file_path), "reason": f"File too large: {file_size} bytes"}
                        )
                        logger.warning(f"Skipping large file: {file_path} ({file_size} bytes)")
                        continue

                    # Read file content
                    with open(file_path, "rb") as f:
                        content = f.read()

                    # Generate safe key
                    relative_path = file_path.relative_to(Path(self.root_path))
                    safe_key = safe_filename(str(relative_path))
                    key = f"{output_prefix}{safe_key}"

                    # Determine content type
                    content_type = self._get_content_type(file_path)

                    # Upload to MinIO
                    success = minio_client.put_bytes(output_bucket, key, content, content_type)

                    if success:
                        files_processed += 1
                        bytes_transferred += len(content)
                        details["files_processed"].append(
                            {"path": str(file_path), "key": key, "size": len(content), "content_type": content_type}
                        )
                        logger.info(f"Uploaded {file_path} as {key} ({len(content)} bytes)")
                    else:
                        errors += 1
                        details["files_failed"].append({"path": str(file_path), "error": "Failed to upload to MinIO"})
                        logger.error(f"Failed to upload {file_path}")

                except FileNotFoundError:
                    errors += 1
                    details["files_failed"].append({"path": str(file_path), "error": "File not found"})
                    logger.error(f"File not found: {file_path}")
                except PermissionError:
                    errors += 1
                    details["files_failed"].append({"path": str(file_path), "error": "Permission denied"})
                    logger.error(f"Permission denied: {file_path}")
                except Exception as e:
                    errors += 1
                    details["files_failed"].append({"path": str(file_path), "error": str(e)})
                    logger.error(f"Error processing {file_path}: {e}")

        except Exception as e:
            logger.error(f"Error during folder sync: {e}")
            return {"files": 0, "bytes": 0, "errors": 1, "duration": time.time() - start_time, "details": {"error": str(e)}}

        duration = time.time() - start_time

        result = {
            "files": files_processed,
            "bytes": bytes_transferred,
            "errors": errors,
            "duration": duration,
            "details": details,
        }

        logger.info(
            f"Folder sync completed: {files_processed} files, {bytes_transferred} bytes, {errors} errors in {duration:.2f}s"
        )
        return result

    def _get_content_type(self, file_path: Path) -> str:
        """Determine content type based on file extension."""
        suffix = file_path.suffix.lower()

        content_types = {
            ".txt": "text/plain",
            ".html": "text/html",
            ".htm": "text/html",
            ".css": "text/css",
            ".js": "application/javascript",
            ".json": "application/json",
            ".xml": "application/xml",
            ".pdf": "application/pdf",
            ".doc": "application/msword",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".xls": "application/vnd.ms-excel",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".csv": "text/csv",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".svg": "image/svg+xml",
            ".zip": "application/zip",
            ".tar": "application/x-tar",
            ".gz": "application/gzip",
        }

        return content_types.get(suffix, "application/octet-stream")

    def _get_config_schema(self) -> Dict[str, Any]:
        """Get JSON schema for folder connector configuration."""
        return {
            "type": "object",
            "properties": {
                "root_path": {"type": "string", "description": "Root directory path to scan"},
                "include": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": ["*"],
                    "description": 'Include file patterns (e.g., ["*.txt", "*.pdf"])',
                },
                "exclude": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": [],
                    "description": 'Exclude file patterns (e.g., ["*.tmp", "*.log"])',
                },
                "recursive": {"type": "boolean", "default": True, "description": "Whether to scan subdirectories recursively"},
                "max_file_size": {
                    "type": "integer",
                    "minimum": 1024,
                    "default": 104857600,
                    "description": "Maximum file size in bytes (default: 100MB)",
                },
            },
            "required": ["root_path"],
        }
