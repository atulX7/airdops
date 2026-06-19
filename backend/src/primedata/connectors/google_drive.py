"""
Google Drive connector for reading files from Google Drive.
"""

import logging
import time
from io import BytesIO
from typing import Any, Dict, List, Tuple

from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

from ..storage.minio_client import minio_client
from ..storage.paths import safe_filename
from .base import BaseConnector

logger = logging.getLogger(__name__)


class GoogleDriveConnector(BaseConnector):
    """Connector for reading files from Google Drive."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize Google Drive connector.

        Expected config:
        {
            'folder_id': str,              # Google Drive folder ID (optional, for specific folder)
            'credentials': dict,            # OAuth2 credentials dict (for user auth)
            'service_account_json': dict,   # Service account JSON (alternative to credentials)
            'include': List[str],           # Include patterns (optional)
            'exclude': List[str],           # Exclude patterns (optional)
            'max_file_size': int            # Maximum file size in bytes (default: 100MB)
        }
        """
        super().__init__(config)
        self.folder_id = config.get("folder_id", "")
        self.credentials_dict = config.get("credentials", {})
        self.service_account_json = config.get("service_account_json", {})
        self.include_patterns = config.get("include", ["*"])
        self.exclude_patterns = config.get("exclude", [])
        self.max_file_size = config.get("max_file_size", 100 * 1024 * 1024)  # 100MB

        # Initialize Google Drive client
        if self.service_account_json:
            credentials = service_account.Credentials.from_service_account_info(
                self.service_account_json, scopes=["https://www.googleapis.com/auth/drive.readonly"]
            )
        elif self.credentials_dict:
            credentials = Credentials.from_authorized_user_info(self.credentials_dict)
        else:
            raise ValueError("Either credentials or service_account_json must be provided")

        self.drive_service = build("drive", "v3", credentials=credentials)

    def validate_config(self) -> Tuple[bool, str]:
        """Validate Google Drive connector configuration."""
        if not self.credentials_dict and not self.service_account_json:
            return False, "Either credentials or service_account_json is required"
        return True, "Configuration is valid"

    def test_connection(self) -> Tuple[bool, str]:
        """Test connection to Google Drive."""
        try:
            # Try to list files or get folder info
            if self.folder_id:
                file = self.drive_service.files().get(fileId=self.folder_id).execute()
                return True, f"Successfully connected to Google Drive folder: {file.get('name', self.folder_id)}"
            else:
                # List root files
                results = self.drive_service.files().list(pageSize=1).execute()
                return True, "Successfully connected to Google Drive"
        except HttpError as e:
            return False, f"Error connecting to Google Drive: {str(e)}"
        except Exception as e:
            return False, f"Error connecting to Google Drive: {str(e)}"

    def _list_files_recursive(self, folder_id: str = None) -> List[Dict]:
        """List all files recursively from Google Drive folder."""
        files = []
        query = "trashed=false and mimeType != 'application/vnd.google-apps.folder'"

        if folder_id:
            query += f" and '{folder_id}' in parents"

        page_token = None
        while True:
            try:
                results = (
                    self.drive_service.files()
                    .list(q=query, pageSize=100, pageToken=page_token, fields="nextPageToken, files(id, name, mimeType, size)")
                    .execute()
                )

                items = results.get("files", [])
                files.extend(items)

                page_token = results.get("nextPageToken")
                if not page_token:
                    break
            except HttpError as e:
                logger.error(f"Error listing Google Drive files: {e}")
                break

        return files

    def sync_full(self, output_bucket: str, output_prefix: str) -> Dict[str, Any]:
        """Sync files from Google Drive to MinIO/GCS."""
        start_time = time.time()
        files_processed = 0
        bytes_transferred = 0
        errors = 0
        details = {"files_processed": [], "files_failed": [], "files_skipped": []}

        try:
            # List all files
            drive_files = self._list_files_recursive(self.folder_id if self.folder_id else None)

            for drive_file in drive_files:
                try:
                    file_id = drive_file["id"]
                    file_name = drive_file["name"]
                    file_size = int(drive_file.get("size", 0))

                    if file_size > self.max_file_size:
                        details["files_skipped"].append({"name": file_name, "reason": f"File too large: {file_size} bytes"})
                        continue

                    # Download file
                    request = self.drive_service.files().get_media(fileId=file_id)
                    file_content = BytesIO()
                    downloader = MediaIoBaseDownload(file_content, request)

                    done = False
                    while not done:
                        status, done = downloader.next_chunk()

                    content = file_content.getvalue()

                    # Upload to MinIO/GCS
                    safe_key = safe_filename(file_name)
                    minio_key = f"{output_prefix}{safe_key}"

                    mime_type = drive_file.get("mimeType", "application/octet-stream")
                    success = minio_client.put_bytes(output_bucket, minio_key, content, mime_type)

                    if success:
                        files_processed += 1
                        bytes_transferred += len(content)
                        details["files_processed"].append({"name": file_name, "minio_key": minio_key, "size": len(content)})
                    else:
                        errors += 1
                        details["files_failed"].append({"name": file_name, "error": "Failed to upload to storage"})
                except Exception as e:
                    errors += 1
                    details["files_failed"].append({"name": drive_file.get("name", "unknown"), "error": str(e)})
                    logger.error(f"Error processing Google Drive file: {e}")

        except Exception as e:
            logger.error(f"Error during Google Drive sync: {e}")
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
        """Get JSON schema for Google Drive connector configuration."""
        return {
            "type": "object",
            "properties": {
                "folder_id": {"type": "string", "description": "Google Drive folder ID (optional)"},
                "credentials": {"type": "object", "description": "OAuth2 credentials dict"},
                "service_account_json": {"type": "object", "description": "Service account JSON"},
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
            "required": [],
        }
