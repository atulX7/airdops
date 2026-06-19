"""
Web connector for scraping HTML content from URLs.
"""

import logging
import time
from typing import Any, Dict, List, Tuple
from urllib.parse import urljoin, urlparse

import requests

from ..storage.minio_client import minio_client
from ..storage.paths import safe_filename
from .base import BaseConnector

logger = logging.getLogger(__name__)


class WebConnector(BaseConnector):
    """Connector for web scraping and HTML content extraction."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize web connector.

        Expected config:
        {
            'urls': List[str],           # URLs to scrape
            'obey_robots': bool,         # Whether to respect robots.txt (default: True)
            'rate_limit_rps': float,     # Rate limit in requests per second (default: 1.0)
            'max_pages': int,            # Maximum pages to scrape (default: 50)
            'timeout': int,              # Request timeout in seconds (default: 30)
            'headers': Dict[str, str]    # Custom headers (optional)
        }
        """
        super().__init__(config)
        self.urls = config.get("urls", [])
        self.obey_robots = config.get("obey_robots", True)
        self.rate_limit_rps = config.get("rate_limit_rps", 1.0)
        self.max_pages = config.get("max_pages", 50)
        self.timeout = config.get("timeout", 30)
        self.headers = config.get("headers", {})

        # Default headers
        default_headers = {"User-Agent": "PrimeData-WebConnector/1.0"}
        self.headers = {**default_headers, **self.headers}

    def validate_config(self) -> Tuple[bool, str]:
        """Validate web connector configuration."""
        if not self.urls:
            return False, "No URLs provided"

        if not isinstance(self.urls, list):
            return False, "URLs must be a list"

        # Validate URLs
        for url in self.urls:
            try:
                parsed = urlparse(url)
                if not parsed.scheme or not parsed.netloc:
                    return False, f"Invalid URL: {url}"
            except Exception:
                return False, f"Invalid URL: {url}"

        if self.rate_limit_rps <= 0:
            return False, "Rate limit must be positive"

        if self.max_pages <= 0:
            return False, "Max pages must be positive"

        return True, "Configuration is valid"

    def test_connection(self) -> Tuple[bool, str]:
        """Test connection by making a request to the first URL."""
        if not self.urls:
            return False, "No URLs configured"

        try:
            url = self.urls[0]
            response = requests.get(url, headers=self.headers, timeout=self.timeout, allow_redirects=True)

            if response.status_code == 200:
                return True, f"Successfully connected to {url} (status: {response.status_code})"
            else:
                return False, f"HTTP {response.status_code} from {url}"

        except requests.exceptions.Timeout:
            return False, f"Timeout connecting to {url}"
        except requests.exceptions.ConnectionError:
            return False, f"Connection error to {url}"
        except Exception as e:
            return False, f"Error connecting to {url}: {str(e)}"

    def sync_full(self, output_bucket: str, output_prefix: str) -> Dict[str, Any]:
        """Scrape all configured URLs and store HTML content."""
        start_time = time.time()
        files_processed = 0
        bytes_transferred = 0
        errors = 0
        details = {"urls_processed": [], "urls_failed": [], "total_requests": 0}

        logger.info(f"Starting web sync for {len(self.urls)} URLs")

        # Limit URLs to max_pages
        urls_to_process = self.urls[: self.max_pages]

        for i, url in enumerate(urls_to_process):
            try:
                # Rate limiting
                if i > 0:
                    time.sleep(1.0 / self.rate_limit_rps)

                # Make request
                response = requests.get(url, headers=self.headers, timeout=self.timeout, allow_redirects=True)
                details["total_requests"] += 1

                if response.status_code == 200:
                    # Generate safe filename
                    parsed_url = urlparse(url)
                    filename = f"{parsed_url.netloc}_{safe_filename(parsed_url.path)}"
                    if not filename.endswith(".html"):
                        filename += ".html"

                    # Store content
                    key = f"{output_prefix}{filename}"
                    content = response.content

                    success = minio_client.put_bytes(output_bucket, key, content, "text/html")

                    if success:
                        files_processed += 1
                        bytes_transferred += len(content)
                        details["urls_processed"].append(
                            {"url": url, "filename": filename, "size": len(content), "status_code": response.status_code}
                        )
                        logger.info(f"Stored {url} as {filename} ({len(content)} bytes)")
                    else:
                        errors += 1
                        details["urls_failed"].append({"url": url, "error": "Failed to store in MinIO"})
                        logger.error(f"Failed to store {url}")
                else:
                    errors += 1
                    details["urls_failed"].append({"url": url, "error": f"HTTP {response.status_code}"})
                    logger.warning(f"HTTP {response.status_code} for {url}")

            except requests.exceptions.Timeout:
                errors += 1
                details["urls_failed"].append({"url": url, "error": "Timeout"})
                logger.error(f"Timeout for {url}")
            except Exception as e:
                errors += 1
                details["urls_failed"].append({"url": url, "error": str(e)})
                logger.error(f"Error processing {url}: {e}")

        duration = time.time() - start_time

        result = {
            "files": files_processed,
            "bytes": bytes_transferred,
            "errors": errors,
            "duration": duration,
            "details": details,
        }

        logger.info(
            f"Web sync completed: {files_processed} files, {bytes_transferred} bytes, {errors} errors in {duration:.2f}s"
        )
        return result

    def _get_config_schema(self) -> Dict[str, Any]:
        """Get JSON schema for web connector configuration."""
        return {
            "type": "object",
            "properties": {
                "urls": {
                    "type": "array",
                    "items": {"type": "string", "format": "uri"},
                    "description": "List of URLs to scrape",
                },
                "obey_robots": {"type": "boolean", "default": True, "description": "Whether to respect robots.txt"},
                "rate_limit_rps": {
                    "type": "number",
                    "minimum": 0.1,
                    "maximum": 10.0,
                    "default": 1.0,
                    "description": "Rate limit in requests per second",
                },
                "max_pages": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 1000,
                    "default": 50,
                    "description": "Maximum number of pages to scrape",
                },
                "timeout": {
                    "type": "integer",
                    "minimum": 5,
                    "maximum": 300,
                    "default": 30,
                    "description": "Request timeout in seconds",
                },
                "headers": {"type": "object", "description": "Custom HTTP headers"},
            },
            "required": ["urls"],
        }
