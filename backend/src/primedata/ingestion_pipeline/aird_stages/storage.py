"""
MinIO storage adapter for AIRD pipeline stages.

Provides file-like operations that map AIRD's local filesystem patterns
to PrimeData's MinIO object storage.
"""

import json
import logging as std_logging  # For Airflow compatibility
import os
import shutil
import subprocess
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from loguru import logger

# Use Python logging for Airflow compatibility (Airflow captures standard logging)
std_logger = std_logging.getLogger(__name__)

from primedata.storage.minio_client import MinIOClient
from primedata.storage.paths import (
    chunk_prefix,
    clean_prefix,
    raw_prefix,
    safe_filename,
)


class AirdStorageAdapter:
    """Adapter that provides AIRD-compatible file operations using MinIO.

    Maps AIRD's local filesystem patterns to MinIO storage:
    - data/raw/{stem}.txt → MinIO raw bucket
    - data/processed/{stem}.jsonl → MinIO processed bucket
    - data/processed/metrics.json → MinIO processed bucket
    """

    def __init__(
        self,
        workspace_id: UUID,
        product_id: UUID,
        version: int,
        minio_client: Optional[MinIOClient] = None,
    ):
        """Initialize storage adapter.

        Args:
            workspace_id: Workspace UUID
            product_id: Product UUID
            version: Product version number
            minio_client: Optional MinIO client (creates new one if not provided)
        """
        self.workspace_id = workspace_id
        self.product_id = product_id
        self.version = version
        self.minio_client = minio_client or MinIOClient()
        self.logger = logger.bind(
            workspace_id=str(workspace_id),
            product_id=str(product_id),
            version=version,
        )

    def _get_raw_prefix(self) -> str:
        """Get MinIO prefix for raw data."""
        return raw_prefix(self.workspace_id, self.product_id, self.version)

    def _get_processed_prefix(self) -> str:
        """Get MinIO prefix for processed data."""
        return clean_prefix(self.workspace_id, self.product_id, self.version)

    def _get_chunk_prefix(self) -> str:
        """Get MinIO prefix for chunked data."""
        return chunk_prefix(self.workspace_id, self.product_id, self.version)

    def put_raw_text(self, stem: str, text: str) -> str:
        """Store raw text file (equivalent to data/raw/{stem}.txt).

        Args:
            stem: File stem (without extension)
            text: Text content

        Returns:
            MinIO object key
        """
        key = f"{self._get_raw_prefix()}{safe_filename(stem)}.txt"
        success = self.minio_client.put_bytes(
            bucket="primedata-raw",
            key=key,
            data=text.encode("utf-8"),
            content_type="text/plain",
        )
        if not success:
            raise RuntimeError(f"Failed to store raw text: {key}")
        self.logger.info(f"Stored raw text: {key}")
        return key

    def put_manifest(self, stem: str, manifest: Dict[str, Any]) -> str:
        """Store manifest JSON (equivalent to data/raw/{stem}.manifest.json).

        Args:
            stem: File stem
            manifest: Manifest dictionary

        Returns:
            MinIO object key
        """
        key = f"{self._get_raw_prefix()}{safe_filename(stem)}.manifest.json"
        success = self.minio_client.put_json(
            bucket="primedata-raw",
            key=key,
            obj=manifest,
        )
        if not success:
            raise RuntimeError(f"Failed to store manifest: {key}")
        self.logger.info(f"Stored manifest: {key}")
        return key

    def put_processed_jsonl(self, stem: str, records: List[Dict[str, Any]]) -> str:
        """Store processed JSONL file (equivalent to data/processed/{stem}.jsonl).

        Args:
            stem: File stem
            records: List of record dictionaries

        Returns:
            MinIO object key
        """
        key = f"{self._get_processed_prefix()}{safe_filename(stem)}.jsonl"
        # Convert records to JSONL format (one JSON object per line)
        jsonl_content = "\n".join(json.dumps(rec, ensure_ascii=False) for rec in records)
        success = self.minio_client.put_bytes(
            bucket="primedata-clean",
            key=key,
            data=jsonl_content.encode("utf-8"),
            content_type="application/x-ndjson",
        )
        if not success:
            raise RuntimeError(f"Failed to store processed JSONL: {key}")
        self.logger.info(f"Stored processed JSONL: {key} ({len(records)} records)")
        return key

    def put_metrics_json(self, metrics: List[Dict[str, Any]]) -> str:
        """Store metrics JSON (equivalent to data/processed/metrics.json).

        Args:
            metrics: List of metric dictionaries

        Returns:
            MinIO object key
        """
        key = f"{self._get_processed_prefix()}metrics.json"
        success = self.minio_client.put_json(
            bucket="primedata-clean",
            key=key,
            obj=metrics,
        )
        if not success:
            raise RuntimeError(f"Failed to store metrics: {key}")
        self.logger.info(f"Stored metrics: {key} ({len(metrics)} entries)")
        return key

    def get_raw_text(self, stem: str, minio_key: Optional[str] = None, minio_bucket: Optional[str] = None) -> Optional[str]:
        """Retrieve raw text file.

        Supports both text files and binary files (PDFs) with automatic format detection.

        Args:
            stem: File stem (for backward compatibility)
            minio_key: Optional exact MinIO key from database (takes precedence)
            minio_bucket: Optional bucket name (defaults to primedata-raw)

        Returns:
            Text content, or None if not found
        """
        # If exact minio_key provided (from database), use it directly
        if minio_key:
            bucket = minio_bucket or "primedata-raw"
            # Use both loguru and std logging for Airflow visibility
            self.logger.info(f"[get_raw_text] Attempting to fetch from MinIO: bucket={bucket}, key={minio_key}")
            std_logger.info(f"[get_raw_text] Attempting to fetch from MinIO: bucket={bucket}, key={minio_key}")
            try:
                # Log before calling get_bytes
                self.logger.info(f"[get_raw_text] Calling minio_client.get_bytes(bucket={bucket}, key={minio_key})")
                std_logger.info(f"[get_raw_text] Calling minio_client.get_bytes(bucket={bucket}, key={minio_key})")
                data = self.minio_client.get_bytes(bucket, minio_key)
                self.logger.info(
                    f"[get_raw_text] get_bytes() returned: type={type(data)}, value={'None' if data is None else f'{len(data)} bytes'}"
                )
                std_logger.info(
                    f"[get_raw_text] get_bytes() returned: type={type(data)}, value={'None' if data is None else f'{len(data)} bytes'}"
                )

                if data is None:
                    error_msg = f"[get_raw_text] Failed to retrieve file from MinIO: bucket={bucket}, key={minio_key} - file does not exist or access denied"
                    self.logger.error(error_msg)
                    std_logger.error(error_msg)
                    return None

                success_msg = f"[get_raw_text] Successfully retrieved {len(data)} bytes from MinIO: {minio_key}"
                self.logger.info(success_msg)
                std_logger.info(success_msg)

                # Try to decode as text first
                try:
                    decoded_text = data.decode("utf-8")
                    decode_success_msg = f"[get_raw_text] Successfully decoded as UTF-8 text ({len(decoded_text)} characters)"
                    self.logger.info(decode_success_msg)
                    std_logger.info(decode_success_msg)
                    return decoded_text
                except UnicodeDecodeError as e:
                    self.logger.info(f"[get_raw_text] File is not UTF-8 text (binary detected). Attempting PDF extraction...")
                    # Binary file detected - try PDF extraction
                    if minio_key.lower().endswith(".pdf"):
                        try:
                            # Use both loguru and std logging for Airflow visibility
                            log_msg = (
                                f"[get_raw_text] Attempting to extract text from PDF: {minio_key} (size: {len(data)} bytes)"
                            )
                            self.logger.info(log_msg)
                            std_logger.info(log_msg)
                            extracted_text = self._extract_pdf_text(data)
                            if extracted_text and extracted_text.strip():
                                success_msg = f"[get_raw_text] Successfully extracted {len(extracted_text)} characters from PDF: {minio_key}"
                                self.logger.info(success_msg)
                                std_logger.info(success_msg)

                                # Heuristic: if text is suspiciously small, likely scanned → try OCR fallback
                                actual_content = extracted_text.replace("=== PAGE", "").replace("===", "").strip()
                                actual_len = len(actual_content)
                                page_count = extracted_text.count("=== PAGE") or 1
                                chars_per_page = actual_len / page_count if page_count else actual_len
                                if actual_len < 500 or chars_per_page < 50:
                                    warn_msg = (
                                        f"[get_raw_text] Low-text PDF detected ({actual_len} chars, "
                                        f"{chars_per_page:.1f} chars/page). Likely scanned/image-only; "
                                        f"Attempting OCR fallback."
                                    )
                                    self.logger.warning(warn_msg)
                                    std_logger.warning(warn_msg)

                                    ocr_text = self._try_ocr_pdf(data)
                                    if ocr_text and ocr_text.strip():
                                        ocr_success = (
                                            f"[get_raw_text] OCR fallback succeeded; returning {len(ocr_text)} characters"
                                        )
                                        self.logger.info(ocr_success)
                                        std_logger.info(ocr_success)
                                        return ocr_text
                                    else:
                                        self.logger.warning("[get_raw_text] OCR fallback produced no text")
                                        std_logger.warning("[get_raw_text] OCR fallback produced no text")

                                return extracted_text
                            else:
                                warn_msg = f"[get_raw_text] PDF extraction returned empty text for {minio_key} - PDF may be image-based, encrypted, or corrupted"
                                self.logger.warning(warn_msg)
                                std_logger.warning(warn_msg)
                                return None
                        except Exception as e:
                            error_msg = (
                                f"[get_raw_text] Exception during PDF extraction for {minio_key}: {type(e).__name__}: {str(e)}"
                            )
                            self.logger.error(error_msg, exc_info=True)
                            std_logger.error(error_msg, exc_info=True)
                            import traceback

                            tb = traceback.format_exc()
                            self.logger.error(f"[get_raw_text] PDF extraction traceback:\n{tb}")
                            std_logger.error(f"[get_raw_text] PDF extraction traceback:\n{tb}")
                            return None
                    else:
                        warn_msg = f"[get_raw_text] Failed to decode file {minio_key} as UTF-8 and it's not a PDF file (extension: {minio_key.split('.')[-1] if '.' in minio_key else 'none'})"
                        self.logger.warning(warn_msg)
                        std_logger.warning(warn_msg)
                        return None
            except Exception as e:
                error_msg = f"[get_raw_text] Unexpected exception while fetching from MinIO (bucket={bucket}, key={minio_key}): {type(e).__name__}: {str(e)}"
                self.logger.error(error_msg, exc_info=True)
                std_logger.error(error_msg, exc_info=True)
                import traceback

                tb = traceback.format_exc()
                self.logger.error(f"[get_raw_text] MinIO fetch traceback:\n{tb}")
                std_logger.error(f"[get_raw_text] MinIO fetch traceback:\n{tb}")
                return None

        # Fallback: Try to construct path with .txt extension (original behavior)
        key = f"{self._get_raw_prefix()}{safe_filename(stem)}.txt"
        data = self.minio_client.get_bytes("primedata-raw", key)
        if data is None:
            return None
        return data.decode("utf-8")

    def _extract_pdf_text(self, pdf_data: bytes) -> str:
        """Extract text content from PDF bytes.

        Args:
            pdf_data: PDF file content as bytes

        Returns:
            Extracted text content
        """
        from io import BytesIO

        self.logger.info(f"[_extract_pdf_text] Starting PDF text extraction for {len(pdf_data)} bytes")

        try:
            # Try pypdf (modern, actively maintained)
            try:
                from pypdf import PdfReader

                self.logger.info(f"[_extract_pdf_text] Using pypdf library for extraction")

                pdf_file = BytesIO(pdf_data)
                self.logger.info(f"[_extract_pdf_text] Created BytesIO object, attempting to read PDF...")

                try:
                    reader = PdfReader(pdf_file)
                    self.logger.info(
                        f"[_extract_pdf_text] PdfReader created successfully. Number of pages: {len(reader.pages)}"
                    )
                except Exception as e:
                    self.logger.error(
                        f"[_extract_pdf_text] Failed to create PdfReader: {type(e).__name__}: {str(e)}", exc_info=True
                    )
                    import traceback

                    self.logger.error(f"[_extract_pdf_text] PdfReader creation traceback:\n{traceback.format_exc()}")
                    raise

                text_parts = []
                for i, page in enumerate(reader.pages):
                    try:
                        page_text = page.extract_text()
                        # Add page marker for page detection in preprocessing
                        # Format: "=== PAGE N ===" to match page_fences pattern
                        page_marker = f"\n=== PAGE {i+1} ===\n"
                        text_parts.append(page_marker + page_text)
                        self.logger.debug(f"[_extract_pdf_text] Extracted {len(page_text)} characters from page {i+1}")
                    except Exception as e:
                        self.logger.warning(
                            f"[_extract_pdf_text] Failed to extract text from page {i+1}: {type(e).__name__}: {str(e)}"
                        )
                        # Still add page marker even for empty pages
                        page_marker = f"\n=== PAGE {i+1} ===\n"
                        text_parts.append(page_marker)

                extracted_text = "\n".join(text_parts)
                total_msg = f"[_extract_pdf_text] Total extracted text length: {len(extracted_text)} characters"
                self.logger.info(total_msg)
                std_logger.info(total_msg)

                if not extracted_text.strip():
                    warn_msg = "[_extract_pdf_text] PDF extraction returned empty text - PDF may be image-based, encrypted, or contain no text content"
                    self.logger.warning(warn_msg)
                    std_logger.warning(warn_msg)
                else:
                    # Show preview of extracted text (skip page markers in preview)
                    preview_text = extracted_text[:200].replace("=== PAGE", "[PAGE").replace("===\n", "]")
                    # Count total pages extracted
                    page_count = extracted_text.count("=== PAGE")
                    success_msg = (
                        f"[_extract_pdf_text] Successfully extracted text ({page_count} pages, "
                        f"{len(extracted_text)} chars). Preview: {preview_text}..."
                    )
                    self.logger.info(success_msg)
                    std_logger.info(success_msg)

                    # Heuristic: detect likely scanned/image-only PDFs (large file, tiny text)
                    pdf_size_mb = len(pdf_data) / (1024 * 1024)
                    actual_content = extracted_text.replace("=== PAGE", "").replace("===", "").strip()
                    actual_content_length = len(actual_content)
                    pages = max(1, page_count)
                    chars_per_page = actual_content_length / pages if pages else actual_content_length

                    if (pdf_size_mb > 1.0 and actual_content_length < 1000) or chars_per_page < 50:
                        warn_msg = (
                            f"[_extract_pdf_text] ⚠️ PDF is {pdf_size_mb:.2f} MB but has very little text "
                            f"({actual_content_length} chars, {chars_per_page:.1f} chars/page). "
                            f"Likely scanned/image-only; OCR is recommended."
                        )
                        self.logger.warning(warn_msg)
                        std_logger.warning(warn_msg)

                return extracted_text
            except ImportError:
                # Fallback to PyPDF2 if pypdf not available
                try:
                    from PyPDF2 import PdfReader

                    pdf_file = BytesIO(pdf_data)
                    reader = PdfReader(pdf_file)
                    text_parts = []

                    for page in reader.pages:
                        text_parts.append(page.extract_text())

                    extracted_text = "\n\n".join(text_parts)
                    if not extracted_text.strip():
                        self.logger.warning("PDF extraction returned empty text - PDF may be image-based or encrypted")
                    return extracted_text
                except ImportError:
                    self.logger.error("pypdf/PyPDF2 not installed, cannot extract PDF text")
                    raise ImportError("PDF parsing library (pypdf or PyPDF2) is required for PDF files")
        except Exception as e:
            self.logger.error(f"Error extracting PDF text: {e}", exc_info=True)
            raise

    def _try_ocr_pdf(self, pdf_data: bytes) -> Optional[str]:
        """Attempt OCR using ocrmypdf if available; returns extracted text or None."""
        if not shutil.which("ocrmypdf"):
            self.logger.info("[_try_ocr_pdf] ocrmypdf not installed; skipping OCR fallback")
            std_logger.info("[_try_ocr_pdf] ocrmypdf not installed; skipping OCR fallback")
            return None

        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = os.path.join(tmpdir, "input.pdf")
            output_path = os.path.join(tmpdir, "output.pdf")
            try:
                with open(input_path, "wb") as f:
                    f.write(pdf_data)

                cmd = [
                    "ocrmypdf",
                    "--skip-text",
                    "--optimize",
                    "3",
                    "--deskew",
                    "--clean",
                    input_path,
                    output_path,
                ]
                self.logger.info(f"[_try_ocr_pdf] Running OCR: {' '.join(cmd)}")
                std_logger.info(f"[_try_ocr_pdf] Running OCR: {' '.join(cmd)}")
                subprocess.run(cmd, check=True, timeout=180)

                with open(output_path, "rb") as f:
                    ocr_bytes = f.read()

                ocr_text = self._extract_pdf_text(ocr_bytes)
                return ocr_text if ocr_text and ocr_text.strip() else None
            except Exception as e:
                self.logger.warning(f"[_try_ocr_pdf] OCR fallback failed: {e}")
                std_logger.warning(f"[_try_ocr_pdf] OCR fallback failed: {e}")
                return None

    def get_manifest(self, stem: str) -> Optional[Dict[str, Any]]:
        """Retrieve manifest JSON.

        Args:
            stem: File stem

        Returns:
            Manifest dictionary, or None if not found
        """
        key = f"{self._get_raw_prefix()}{safe_filename(stem)}.manifest.json"
        return self.minio_client.get_json("primedata-raw", key)

    def get_processed_jsonl(self, stem: str) -> Optional[List[Dict[str, Any]]]:
        """Retrieve processed JSONL file.

        Args:
            stem: File stem

        Returns:
            List of record dictionaries, or None if not found
        """
        key = f"{self._get_processed_prefix()}{safe_filename(stem)}.jsonl"
        data = self.minio_client.get_bytes("primedata-clean", key)
        if data is None:
            return None

        # Parse JSONL (one JSON object per line)
        records = []
        for line in data.decode("utf-8").splitlines():
            line = line.strip()
            if line:
                records.append(json.loads(line))
        return records

    def get_metrics_json(self) -> Optional[List[Dict[str, Any]]]:
        """Retrieve metrics JSON.

        Returns:
            List of metric dictionaries, or None if not found
        """
        key = f"{self._get_processed_prefix()}metrics.json"
        metrics = self.minio_client.get_json("primedata-clean", key)
        if metrics is None:
            return None
        # Ensure it's a list
        if isinstance(metrics, list):
            return metrics
        return [metrics]

    def put_artifact(
        self, artifact_name: str, content: Union[str, bytes], content_type: str = "application/octet-stream"
    ) -> str:
        """Store an artifact (PDF, CSV, etc.).

        Args:
            artifact_name: Artifact name (e.g., "ai_trust_report.pdf")
            content: Artifact content (string or bytes)
            content_type: MIME type

        Returns:
            MinIO object key
        """
        # Use exports bucket for artifacts
        key = f"ws/{self.workspace_id}/prod/{self.product_id}/v/{self.version}/artifacts/{safe_filename(artifact_name)}"

        if isinstance(content, str):
            data = content.encode("utf-8")
        else:
            data = content

        success = self.minio_client.put_bytes(
            bucket="primedata-exports",
            key=key,
            data=data,
            content_type=content_type,
        )
        if not success:
            raise RuntimeError(f"Failed to store artifact: {key}")
        self.logger.info(f"Stored artifact: {key}")
        return key

    def get_artifact(self, artifact_name: str) -> Optional[bytes]:
        """Retrieve an artifact.

        Args:
            artifact_name: Artifact name

        Returns:
            Artifact content as bytes, or None if not found
        """
        key = f"ws/{self.workspace_id}/prod/{self.product_id}/v/{self.version}/artifacts/{safe_filename(artifact_name)}"
        return self.minio_client.get_bytes("primedata-exports", key)
