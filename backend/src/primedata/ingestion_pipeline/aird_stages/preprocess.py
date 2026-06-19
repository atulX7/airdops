"""
AIRD preprocessing stage for PrimeData.

Ports AIRD preprocessing logic with playbook support, adapted for MinIO storage.
"""

import json
import logging as std_logging  # For Airflow compatibility
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import regex as re
from loguru import logger

# Use Python logging for Airflow compatibility (Airflow captures standard logging)
std_logger = std_logging.getLogger(__name__)

from primedata.ingestion_pipeline.aird_stages.base import AirdStage, StageResult, StageStatus
from primedata.ingestion_pipeline.aird_stages.playbooks import load_playbook_yaml, route_playbook
from primedata.ingestion_pipeline.aird_stages.utils.chunking import (
    char_chunk,
    paragraph_chunk,
    sentence_chunk,
    tokens_estimate,
)
from primedata.services.scoring_utils import estimate_tokens
from primedata.services.lineage import record_dq_finding, record_lineage
from primedata.db.models import LineageType, RuleSeverity
import hashlib
from primedata.ingestion_pipeline.aird_stages.utils.text_processing import (
    apply_normalizers,
    detect_sections_configured,
    normalize_wrapped_lines,
    normalize_encoding_artifacts,
    normalize_repeated_words,
    normalize_whitespace,
    redact_pii,
    split_pages_by_config,
)
from primedata.ingestion_pipeline.aird_stages.utils.ocr_cleanup import (
    ocr_cleanup_and_metrics,
    chunk_cleanup_metrics,
    is_abnormal_repetition,
)
from primedata.analysis.content_analyzer import content_analyzer
from primedata.ingestion_pipeline.pipeline_config import resolve_content_hint

# Audience patterns (aligned with AIRD) - ordered by specificity
AUDIENCE_PATTERNS = {
    "hcp": r"\b(hcp|physician|prescriber|clinical|doctor|nurse|clinician|healthcare provider)\b",
    "executive": r"\b(executive|vp|vice president|steerco|cxo|ceo|cto|cfo|board|director|leadership|management)\b",
    "patient": r"\b(patient|caregiver|consumer|user)\b",
    "regulatory": r"\b(regulatory|compliance|sop|policy|regulation|fda|ema|regulatory authority)\b",
    "finance": r"\b(p&l|profit.*loss|variance|forecast|budget|kpi|quarter|quarterly|financial|revenue|earnings|income statement)\b",
    "ops": r"\b(monitoring|deployment|incident|runbook|oncall|slo|sla|kubernetes|cluster|operations|infrastructure)\b",
    "dev": r"\b(api|cli|sdk|endpoint|json|yaml|code|pipeline|ci/cd|developer|engineer|programmer)\b",
    "general": r"\b(overview|introduction|getting started|guide|tutorial|documentation|help|support)\b",
}


# Extraction type: how the document was obtained (digital vs scanned PDF)
EXTRACTION_TYPE_DIGITAL_PDF = "digital_pdf"
EXTRACTION_TYPE_SCANNED_PDF = "scanned_pdf"
EXTRACTION_TYPE_MIXED = "mixed"


def _infer_extraction_type(raw_text: str, filename: str) -> str:
    """
    Infer extraction_type from raw extracted text and filename.
    Used for preprocess/extraction metadata only; not a content_type.
    Returns: 'digital_pdf' | 'scanned_pdf' | 'mixed'
    """
    if not raw_text or not filename:
        return EXTRACTION_TYPE_DIGITAL_PDF
    fn_lower = filename.lower()
    if not fn_lower.endswith(".pdf"):
        return EXTRACTION_TYPE_DIGITAL_PDF  # Non-PDF is treated as digital
    actual = raw_text.replace("=== PAGE", "").replace("===", "").strip()
    actual_len = len(actual)
    page_markers = raw_text.count("=== PAGE") or 1
    chars_per_page = actual_len / page_markers if page_markers else actual_len
    if actual_len < 500 or chars_per_page < 50:
        return EXTRACTION_TYPE_SCANNED_PDF
    # Check for mixed: some pages with content, some nearly empty
    if "=== PAGE" in raw_text:
        pages = [p.strip() for p in raw_text.split("=== PAGE") if p.strip()]
        if len(pages) >= 2:
            lengths = [len(p.replace("===", "").strip()) for p in pages]
            empty_or_tiny = sum(1 for L in lengths if L < 100)
            if 0 < empty_or_tiny < len(lengths):
                return EXTRACTION_TYPE_MIXED
    return EXTRACTION_TYPE_DIGITAL_PDF


def _audience_for(text: str, section: str = "", default: str = "general") -> str:
    """Detect audience from text and section using patterns."""
    # Combine text and section for better detection
    search_text = f"{section} {text}".lower()

    # Score each audience pattern
    scores = {}
    for name, pat in AUDIENCE_PATTERNS.items():
        matches = len(re.findall(pat, search_text, flags=re.IGNORECASE))
        if matches > 0:
            scores[name] = matches

    if scores:
        # Return the audience with the highest score (most matches)
        return max(scores.items(), key=lambda x: x[1])[0]

    return default


def _remove_boilerplate(text: str, min_repetitions: int = 3) -> Tuple[str, Dict[str, Any]]:
    """
    Remove boilerplate (headers/footers/page numbers/repeated nav) from text.
    
    Detects repeated lines across pages and removes them if they appear more than min_repetitions times.
    
    Args:
        text: Input text (may contain page markers)
        min_repetitions: Minimum number of repetitions to consider a line boilerplate (default: 3)
        
    Returns:
        Tuple of (cleaned_text, boilerplate_flags_dict)
    """
    if not text:
        return text, {}
    
    boilerplate_flags = {
        "headers_removed": False,
        "footers_removed": False,
        "page_numbers_removed": False,
        "repeated_nav_removed": False,
    }
    
    # Split into lines
    lines = text.split('\n')
    if len(lines) < min_repetitions:
        # Too few lines, no boilerplate detection
        return text, boilerplate_flags
    
    # Count line occurrences (normalize whitespace)
    line_counts: Dict[str, int] = {}
    for line in lines:
        normalized = line.strip()
        if normalized:  # Skip empty lines
            line_counts[normalized] = line_counts.get(normalized, 0) + 1
    
    # Find repeated lines (boilerplate candidates)
    repeated_lines = {line: count for line, count in line_counts.items() if count >= min_repetitions}
    
    if not repeated_lines:
        return text, boilerplate_flags
    
    # Remove repeated lines (but keep first occurrence for context)
    cleaned_lines = []
    seen_repeated = set()
    for line in lines:
        normalized = line.strip()
        if normalized in repeated_lines:
            if normalized not in seen_repeated:
                # Keep first occurrence
                cleaned_lines.append(line)
                seen_repeated.add(normalized)
            # Skip subsequent occurrences
            continue
        cleaned_lines.append(line)
    
    cleaned_text = '\n'.join(cleaned_lines)
    
    # Detect specific boilerplate types
    if any('page' in line.lower() and any(c.isdigit() for c in line) for line in repeated_lines.keys()):
        boilerplate_flags["page_numbers_removed"] = True
    
    # Check if removed lines look like headers (short, title case, at start)
    header_candidates = [line for line in repeated_lines.keys() if len(line) < 100]
    if header_candidates:
        boilerplate_flags["headers_removed"] = True
    
    # Check if removed lines look like footers (short, at end, contain copyright/confidential)
    footer_keywords = ['copyright', 'confidential', 'proprietary', 'all rights reserved']
    footer_candidates = [line for line in repeated_lines.keys() 
                        if any(keyword in line.lower() for keyword in footer_keywords)]
    if footer_candidates:
        boilerplate_flags["footers_removed"] = True
    
    # Check for navigation patterns (repeated section names, table of contents patterns)
    nav_patterns = [r'^\s*\d+\.\s+', r'^\s*[A-Z][a-z]+\s+\.{3,}', r'^\s*Chapter\s+\d+']
    nav_candidates = [line for line in repeated_lines.keys()
                     if any(re.search(pattern, line, re.IGNORECASE) for pattern in nav_patterns)]
    if nav_candidates:
        boilerplate_flags["repeated_nav_removed"] = True
    
    return cleaned_text, boilerplate_flags


def _merge_tiny_chunks(chunks: List[str], min_tokens: int = 80) -> List[str]:
    """
    Merge tiny chunks (token_est < MIN_TOKENS) with neighbors.
    
    Args:
        chunks: List of chunk texts
        min_tokens: Minimum token threshold (default: 80-120 range)
        
    Returns:
        List of merged chunks (no chunks with token_est < min_tokens remain)
    """
    if not chunks:
        return chunks
    
    merged = []
    i = 0
    
    while i < len(chunks):
        current_chunk = chunks[i]
        current_tokens = estimate_tokens(current_chunk)
        
        # If chunk is too small, try to merge with next chunk
        if current_tokens < min_tokens and i + 1 < len(chunks):
            next_chunk = chunks[i + 1]
            merged_chunk = current_chunk.strip() + "\n\n" + next_chunk.strip()
            merged_tokens = estimate_tokens(merged_chunk)
            
            # If merged chunk is still too small and there's another chunk, continue merging
            if merged_tokens < min_tokens and i + 2 < len(chunks):
                # Merge with next 2 chunks
                next_next_chunk = chunks[i + 2]
                merged_chunk = merged_chunk + "\n\n" + next_next_chunk.strip()
                merged_tokens = estimate_tokens(merged_chunk)
                i += 3  # Skip next 2 chunks
            else:
                i += 2  # Skip next chunk
            merged.append(merged_chunk)
        else:
            # Chunk is large enough, keep as-is
            merged.append(current_chunk)
            i += 1
    
    return merged


def _build_record(
    stem: str,
    filename: str,
    document_id: str,
    page: int,
    canon_section: str,
    title_raw: str,
    text: str,
    chunk_idx: int,
    chunk_of: int,
    product_id: UUID,
    domain_type: Optional[str] = None,
    section_confidence: Optional[float] = None,
    # Contract fields
    workspace_id: Optional[str] = None,
    version: Optional[str] = None,
    pipeline_run_id: Optional[str] = None,
    source_uri: Optional[str] = None,
    source_checksum: Optional[str] = None,
    extractor_version: Optional[str] = None,
    chunker_version: Optional[str] = None,
    embedding_model_id: Optional[str] = None,
    extraction_timestamp: Optional[str] = None,
    boilerplate_flags: Optional[Dict[str, Any]] = None,
    cleaned_text_hash: Optional[str] = None,
    raw_text: Optional[str] = None,
    cleaned_text: Optional[str] = None,
    repetition_ratio: Optional[float] = None,
    ocr_noise_score: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Build a chunk record with PrimeData metadata structure.
    
    Implements the strict "Chunk Record Contract" with all required fields.
    cleaned_text is what gets embedded; raw_text is stored for audit.
    """
    # Ensure text is non-empty
    if not text or not text.strip():
        raise ValueError(f"Chunk text cannot be empty (chunk_idx={chunk_idx}, section={canon_section})")
    
    # Compute token_est using shared estimate_tokens helper (always computed, never missing)
    token_est = estimate_tokens(text)
    if token_est <= 0:
        raise ValueError(f"token_est must be > 0 (got {token_est} for chunk_idx={chunk_idx})")
    
    # Compute cleaned_text_hash if not provided (sha256 of cleaned text)
    if cleaned_text_hash is None:
        cleaned_text_hash = hashlib.sha256(text.encode('utf-8')).hexdigest()
    
    # Use current timestamp for created_at/extraction_timestamp if not provided
    now_iso = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    created_at = now_iso
    extraction_timestamp = extraction_timestamp or now_iso
    
    # Default section_id to canon_section if not provided separately
    section_id = canon_section
    
    # cleaned_text is what gets embedded; raw_text stored for audit (default to text when not provided)
    text_for_embed = cleaned_text if cleaned_text is not None else text
    raw_for_audit = raw_text if raw_text is not None else text
    record = {
        # Required contract fields
        "text": text_for_embed,  # non-empty; this is what gets embedded (cleaned)
        "token_est": int(token_est),  # int; always computed; never missing
        "chunk_index": chunk_idx,
        "chunk_of": chunk_of,
        "doc_id": document_id,  # doc_id/file_stem
        "file_stem": stem,
        "section_id": section_id,  # section_id/field_name (if available; else "general")
        "field_name": canon_section,
        "workspace_id": str(workspace_id) if workspace_id else None,
        "product_id": str(product_id),
        "version": version or "unknown",
        "pipeline_run_id": str(pipeline_run_id) if pipeline_run_id else None,
        "source_uri": source_uri,
        "storage_key": source_uri,  # Alias for backward compatibility
        "source_checksum": source_checksum,  # sha256
        "extractor_version": extractor_version or "1.0",
        "chunker_version": chunker_version or "1.0",
        "embedding_model_id": embedding_model_id,  # if known
        "created_at": created_at,
        "extraction_timestamp": extraction_timestamp,
        "boilerplate_flags": boilerplate_flags or {},
        "cleaned_text_hash": cleaned_text_hash,  # sha256
        "raw_text": raw_for_audit,  # stored for audit
        "cleaned_text": text_for_embed,  # what gets embedded (same as "text")
        "repetition_ratio": repetition_ratio,  # OCR cleanup metric for Text Integrity
        "ocr_noise_score": ocr_noise_score,  # OCR cleanup metric for Text Integrity
        
        # Legacy/compatibility fields
        "chunk_id": f"{stem}_p{page}_s{canon_section}_c{chunk_idx}",
        "document_id": document_id,
        "filename": filename,
        "page": page,
        "section_raw": title_raw,
        "section": canon_section,
        "section_confidence": section_confidence if section_confidence is not None else 1.0,  # Default to high confidence if not provided
        "source": "internal",
        "audience": _audience_for(text, section=title_raw or canon_section, default="general"),
        "timestamp": created_at,  # Alias for created_at
        "index_scope": str(product_id),  # Ensure index_scope is always populated
        "doc_scope": document_id,
        "field_scope": canon_section,
        "tags": "",
        "doc_date": None,
    }
    
    # Add domain_type if provided (for domain-adaptive scoring)
    if domain_type:
        record["domain_type"] = domain_type
    
    return record


class PreprocessStage(AirdStage):
    """Preprocessing stage that normalizes, chunks, and sections documents."""

    @property
    def stage_name(self) -> str:
        return "preprocess"

    def get_required_artifacts(self) -> list[str]:
        """Preprocessing requires raw text files from ingestion."""
        return []  # Raw files come from ingestion stage

    def execute(self, context: Dict[str, Any]) -> StageResult:
        """Execute preprocessing stage.

        Args:
            context: Stage execution context with:
                - storage: AirdStorageAdapter
                - raw_files: List of raw file stems to process
                - playbook_id: Optional playbook ID override
                - chunking_config: Optional product chunking configuration

        Returns:
            StageResult with preprocessing metrics
        """
        started_at = datetime.utcnow()

        # Cache context for use in _process_document (for workspace settings lookup)
        self._context_cache = {
            "workspace_id": context.get("workspace_id"),
            "db": context.get("db"),
            "use_case_description": context.get("use_case_description"),
        }

        storage = context.get("storage")
        raw_files = context.get("raw_files", [])
        # Get playbook_id from context or config, but allow None/empty for auto-detection
        initial_playbook_id = context.get("playbook_id") or self.config.get("playbook_id")
        # Normalize empty string to None to allow auto-detection
        if initial_playbook_id == "":
            initial_playbook_id = None
        chunking_config = context.get("chunking_config", {})  # Get product chunking config
        if (
            isinstance(chunking_config, dict)
            and "resolved_settings" not in chunking_config
            and isinstance(chunking_config.get("chunking_config"), dict)
        ):
            chunking_config = chunking_config.get("chunking_config", chunking_config)

        # Track playbook selection metadata for verification
        # Will be updated based on whether playbook is provided or auto-detected
        playbook_selection_metadata = {
            "method": None,  # Will be set to "manual", "auto_detected", or "default"
            "reason": None,
            "detected_at": None,
            "playbook_id": None,  # Will be set when playbook is determined
        }
        context_playbook_selection = context.get("playbook_selection")
        if context_playbook_selection and isinstance(context_playbook_selection, dict):
            playbook_selection_metadata.update(context_playbook_selection)

        if not storage:
            return self._create_result(
                status=StageStatus.FAILED,
                metrics={},
                error="Storage adapter not found in context",
                started_at=started_at,
            )

        if not raw_files:
            self.logger.warning("No raw files to process")
            return self._create_result(
                status=StageStatus.SKIPPED,
                metrics={"reason": "no_raw_files"},
                started_at=started_at,
            )

        # Initialize playbook_id for logging (will be reassigned per file in loop)
        playbook_id = initial_playbook_id
        self.logger.info(f"Starting preprocessing for {len(raw_files)} files, playbook={playbook_id}")

        # Get file_stem to storage_key mapping if provided (for accurate file retrieval)
        file_stem_to_storage_key = context.get("file_stem_to_storage_key", {})

        all_records: List[Dict[str, Any]] = []
        total_sections = 0
        total_mid_sentence_ends = 0
        processed_files = []
        failed_files = []
        last_exception = None
        file_chunk_counts: Dict[str, int] = {}
        file_sections_counts: Dict[str, int] = {}
        file_extraction_types: Dict[str, str] = {}  # file_stem -> digital_pdf | scanned_pdf | mixed
        chunking_config_used: Optional[Dict[str, Any]] = None
        ocr_any_abnormal = False  # set True if any file has abnormal repetition (flag source_quality=scanned_ocr)

        for file_stem in raw_files:
            file_start_time = datetime.utcnow()
            # Use both loguru and std logging for Airflow visibility
            self.logger.info(f"[PreprocessStage] ====== Processing file: {file_stem} ======")
            std_logger.info(f"[PreprocessStage] ====== Processing file: {file_stem} ======")
            try:
                # Load raw text - use exact storage_key if available
                file_info = file_stem_to_storage_key.get(file_stem, {})
                storage_key = file_info.get("storage_key")
                storage_bucket = file_info.get("storage_bucket")
                filename = file_info.get("filename", f"{file_stem}.txt")

                file_info_msg = f"[PreprocessStage] File info for {file_stem}: storage_key={storage_key}, storage_bucket={storage_bucket}, filename={filename}"
                self.logger.info(file_info_msg)
                std_logger.info(file_info_msg)

                keys_msg = (
                    f"[PreprocessStage] Available file_stem_to_storage_key keys: {list(file_stem_to_storage_key.keys())}"
                )
                self.logger.info(keys_msg)
                std_logger.info(keys_msg)

                # OPTIMIZATION: Route playbook BEFORE loading full file (for performance)
                # Route playbook if not provided
                file_playbook_id = initial_playbook_id  # Use initial_playbook_id for this file
                if not file_playbook_id:
                    # OPTIMIZATION: For playbook routing, only read sample text
                    # This avoids extracting full PDF when we only need first 1000-2000 chars
                    sample_for_playbook = None
                    try:
                        if filename.lower().endswith('.pdf'):
                            # For PDFs, extract only first 2 pages for playbook routing
                            sample_for_playbook = self._get_pdf_sample_for_routing(
                                storage, file_stem, storage_key, storage_bucket, max_chars=2000
                            )
                        else:
                            # For text files, read only first 2000 chars
                            sample_for_playbook = self._get_text_sample_for_routing(
                                storage, file_stem, storage_key, storage_bucket, max_chars=2000
                            )
                    except Exception as e:
                        self.logger.warning(f"Failed to get sample for playbook routing: {e}, will use filename only")
                        sample_for_playbook = None
                    
                    # Use sample if available, otherwise use filename only
                    if sample_for_playbook:
                        chosen_id, reason = route_playbook(
                            sample_text=sample_for_playbook[:1000], 
                            filename=file_stem
                        )
                        file_playbook_id = chosen_id
                        # Update selection metadata for auto-detection (only on first file)
                        if playbook_selection_metadata.get("method") is None:
                            playbook_selection_metadata["method"] = "auto_detected"
                            playbook_selection_metadata["playbook_id"] = chosen_id
                            playbook_selection_metadata["reason"] = reason
                            playbook_selection_metadata["detected_at"] = datetime.utcnow().isoformat() + "Z"
                        self.logger.info(f"Auto-routed to playbook {file_playbook_id} ({reason}) using sample text")
                    else:
                        # Fallback: use filename only for routing
                        chosen_id, reason = route_playbook(sample_text=None, filename=file_stem)
                        file_playbook_id = chosen_id
                        if playbook_selection_metadata.get("method") is None:
                            playbook_selection_metadata["method"] = "auto_detected"
                            playbook_selection_metadata["playbook_id"] = chosen_id
                            playbook_selection_metadata["reason"] = reason
                            playbook_selection_metadata["detected_at"] = datetime.utcnow().isoformat() + "Z"
                        self.logger.info(f"Auto-routed to playbook {file_playbook_id} ({reason}) using filename only")
                else:
                    # Playbook was provided, mark as manual (only on first file)
                    if playbook_selection_metadata.get("method") is None:
                        playbook_selection_metadata["method"] = "manual"
                        playbook_selection_metadata["playbook_id"] = file_playbook_id

                # NOW load full file for actual processing
                if storage_key:
                    load_msg = f"[PreprocessStage] Loading raw file {file_stem} from exact MinIO key: {storage_key} (bucket: {storage_bucket or 'primedata-raw'})"
                    self.logger.info(load_msg)
                    std_logger.info(load_msg)
                    try:
                        self.logger.info(
                            f"[PreprocessStage] About to call storage.get_raw_text(file_stem={file_stem}, minio_key={storage_key}, minio_bucket={storage_bucket})"
                        )
                        std_logger.info(
                            f"[PreprocessStage] About to call storage.get_raw_text(file_stem={file_stem}, minio_key={storage_key}, minio_bucket={storage_bucket})"
                        )
                        raw_text = storage.get_raw_text(file_stem, minio_key=storage_key, minio_bucket=storage_bucket)
                        self.logger.info(
                            f"[PreprocessStage] storage.get_raw_text() returned: {'None' if raw_text is None else f'{len(raw_text)} characters'}"
                        )
                        std_logger.info(
                            f"[PreprocessStage] storage.get_raw_text() returned: {'None' if raw_text is None else f'{len(raw_text)} characters'}"
                        )
                    except Exception as e:
                        self.logger.error(
                            f"[PreprocessStage] Exception while calling storage.get_raw_text() for {file_stem}: {type(e).__name__}: {str(e)}",
                            exc_info=True,
                        )
                        import traceback

                        self.logger.error(f"[PreprocessStage] get_raw_text() traceback:\n{traceback.format_exc()}")
                        raw_text = None
                else:
                    self.logger.warning(
                        f"[PreprocessStage] No storage_key found for {file_stem} in file_stem_to_storage_key map. Using constructed path (.txt extension)"
                    )
                    try:
                        raw_text = storage.get_raw_text(file_stem)
                    except Exception as e:
                        self.logger.error(
                            f"[PreprocessStage] Exception while calling storage.get_raw_text() (constructed path) for {file_stem}: {type(e).__name__}: {str(e)}",
                            exc_info=True,
                        )
                        import traceback

                        self.logger.error(
                            f"[PreprocessStage] get_raw_text() (constructed) traceback:\n{traceback.format_exc()}"
                        )
                        raw_text = None

                if not raw_text:
                    # Check if it's an image file (expected to fail)
                    is_image_file = filename.lower().endswith(
                        (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp", ".svg")
                    )
                    if is_image_file:
                        warn_msg = (
                            f"[PreprocessStage] ⚠️ Skipping image file {file_stem} (filename: {filename}). "
                            f"Image files cannot be extracted as text. "
                            f"Only PDF, text, and HTML files are supported for text extraction."
                        )
                        self.logger.warning(warn_msg)
                        std_logger.warning(warn_msg)
                        failed_files.append(file_stem)
                        continue
                    else:
                        error_msg = (
                            f"[PreprocessStage] ❌ Raw text extraction FAILED for {file_stem}. "
                            f"MinIO key: {storage_key if storage_key else 'constructed path'}, "
                            f"Bucket: {storage_bucket or 'primedata-raw'}, "
                            f"Filename: {filename}. "
                            f"File may be missing from MinIO, corrupted, or in unsupported format. "
                            f"Supported formats: PDF, TXT, HTML, JSON, CSV"
                        )
                        # Use both loguru and std logging for Airflow visibility
                        self.logger.error(error_msg)
                        std_logger.error(error_msg)
                        failed_files.append(file_stem)
                        continue

                self.logger.info(
                    f"[PreprocessStage] ✓ Successfully loaded raw text for {file_stem}: {len(raw_text)} characters"
                )
                std_logger.info(
                    f"[PreprocessStage] ✓ Successfully loaded raw text for {file_stem}: {len(raw_text)} characters"
                )

                # Infer extraction_type for preprocess/extraction metadata (not content_type)
                file_extraction_type = _infer_extraction_type(raw_text, filename)
                file_extraction_types[file_stem] = file_extraction_type

                # Validate raw_text has content
                if not raw_text or len(raw_text.strip()) == 0:
                    error_msg = f"[PreprocessStage] ❌ Raw text is empty for {file_stem} after extraction"
                    self.logger.error(error_msg)
                    std_logger.error(error_msg)
                    failed_files.append(file_stem)
                    continue
                
                # Log preview of raw text
                preview = raw_text[:200].replace('\n', '\\n')
                self.logger.debug(f"[PreprocessStage] Raw text preview for {file_stem}: {preview}...")
                std_logger.debug(f"[PreprocessStage] Raw text preview for {file_stem}: {preview[:100]}...")

                # Route playbook if not provided
                file_playbook_id = initial_playbook_id  # Use initial playbook_id for this file
                if not file_playbook_id:
                    # Auto-detect playbook
                    chosen_id, reason = route_playbook(sample_text=raw_text[:1000], filename=file_stem)
                    file_playbook_id = chosen_id
                    # Update selection metadata for auto-detection (only on first file)
                    if playbook_selection_metadata.get("method") is None:
                        playbook_selection_metadata["method"] = "auto_detected"
                        playbook_selection_metadata["playbook_id"] = chosen_id
                        playbook_selection_metadata["reason"] = reason
                        playbook_selection_metadata["detected_at"] = datetime.utcnow().isoformat() + "Z"
                    self.logger.info(f"Auto-routed to playbook {file_playbook_id} ({reason})")
                else:
                    # Playbook was provided, mark as manual (only on first file)
                    if playbook_selection_metadata.get("method") is None:
                        playbook_selection_metadata["method"] = "manual"
                        playbook_selection_metadata["playbook_id"] = file_playbook_id

                # Use file_playbook_id for this file's processing
                playbook_id = file_playbook_id

                # Load playbook (support custom playbooks from database)
                try:
                    workspace_id = context.get("workspace_id")
                    db_session = context.get("db")
                    playbook = load_playbook_yaml(
                        playbook_id, workspace_id=str(workspace_id) if workspace_id else None, db_session=db_session
                    )
                except Exception as e:
                    self.logger.error(f"Failed to load playbook {playbook_id}: {e}, using empty config")
                    playbook = {}

                # Process document
                self.logger.info(
                    f"[PreprocessStage] About to process document {file_stem}: "
                    f"text_length={len(raw_text)}, playbook_id={playbook_id}, "
                    f"chunking_config_mode={chunking_config.get('mode') if chunking_config else 'None'}, "
                    f"has_resolved_settings={'resolved_settings' in (chunking_config or {})}"
                )
                std_logger.info(
                    f"[PreprocessStage] Processing document {file_stem}: "
                    f"text_length={len(raw_text)}, playbook_id={playbook_id}"
                )
                
                # Extract contract fields from context
                workspace_id = context.get("workspace_id")
                version = self.version  # From AirdStage base class
                pipeline_run = context.get("pipeline_run")
                pipeline_run_id = str(pipeline_run.id) if pipeline_run and hasattr(pipeline_run, 'id') else None
                source_uri = storage_key  # Use storage_key as source_uri
                source_checksum = None  # Will be computed in _process_document
                extractor_version = "1.0"  # TODO: Get from config or extractor metadata
                chunker_version = "1.0"  # TODO: Get from config
                embedding_model_id = context.get("embedding_model_id")  # May not be available yet
                extraction_timestamp = datetime.utcnow().isoformat(timespec="seconds") + "Z"
                
                records, stats = self._process_document(
                    raw_text=raw_text,
                    file_stem=file_stem,
                    filename=filename,  # Use actual filename from file_info
                    playbook=playbook,
                    playbook_id=playbook_id,
                    chunking_config=chunking_config,  # Pass product chunking config
                    # Contract fields
                    workspace_id=str(workspace_id) if workspace_id else None,
                    version=version,
                    pipeline_run_id=pipeline_run_id,
                    source_uri=source_uri,
                    source_checksum=source_checksum,  # Will be computed in _process_document
                    extractor_version=extractor_version,
                    chunker_version=chunker_version,
                    embedding_model_id=embedding_model_id,
                    extraction_timestamp=extraction_timestamp,
                )
                
                self.logger.info(
                    f"[PreprocessStage] Document processing completed for {file_stem}: "
                    f"records={len(records)}, sections={stats.get('sections', 0)}, "
                    f"chunks={stats.get('chunks', 0)}"
                )
                std_logger.info(
                    f"[PreprocessStage] Document processing completed: "
                    f"records={len(records)}, sections={stats.get('sections', 0)}"
                )

                all_records.extend(records)
                file_chunk_counts[file_stem] = stats.get("chunks", 0)
                file_sections_counts[file_stem] = stats.get("sections", 0)
                total_sections += stats.get("sections", 0)
                total_mid_sentence_ends += stats.get("mid_sentence_ends", 0)
                if not chunking_config_used and stats.get("chunking_config_used"):
                    chunking_config_used = stats.get("chunking_config_used")
                if stats.get("ocr_repetition_abnormal"):
                    ocr_any_abnormal = True
                processed_files.append(file_stem)

                # Stage-level assertions (fail fast) after preprocess
                # Assert: extracted_text_len>0, num_chunks>0, every chunk has token_est and pipeline_run_id
                if not records:
                    raise AssertionError(f"Preprocess assertion failed: No chunks created for {file_stem}")
                
                for idx, rec in enumerate(records):
                    if not rec.get("text") or not rec["text"].strip():
                        raise AssertionError(f"Preprocess assertion failed: Chunk {idx} has empty text in {file_stem}")
                    if rec.get("token_est") is None or rec.get("token_est") <= 0:
                        raise AssertionError(f"Preprocess assertion failed: Chunk {idx} missing or invalid token_est in {file_stem}")
                    if rec.get("pipeline_run_id") is None:
                        self.logger.warning(f"Preprocess warning: Chunk {idx} missing pipeline_run_id in {file_stem} (may be None if not available)")
                
                self.logger.info(f"✅ Preprocess assertions passed for {file_stem}: {len(records)} chunks, all have token_est")

                # Store processed JSONL for this file
                storage.put_processed_jsonl(file_stem, records)

                # Store manifest (include extraction_type for extraction metadata)
                manifest = {
                    "filename": f"{file_stem}.txt",
                    "stem": file_stem,
                    "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                    "playbook_id": playbook_id,
                    "stats": stats,
                    "extraction_type": file_extraction_types.get(file_stem, EXTRACTION_TYPE_DIGITAL_PDF),
                }
                storage.put_manifest(file_stem, manifest)

            except Exception as e:
                error_msg = f"[PreprocessStage] ❌ EXCEPTION while processing {file_stem}: {type(e).__name__}: {str(e)}"
                self.logger.exception(f"Preprocess failed for file_stem={file_stem}")
                self.logger.error(error_msg, exc_info=True)
                import traceback

                self.logger.error(f"[PreprocessStage] Full traceback for {file_stem}:\n{traceback.format_exc()}")
                self.logger.error(f"[PreprocessStage] Exception details for {file_stem}: {repr(e)}")
                last_exception = error_msg
                failed_files.append(file_stem)
            finally:
                file_duration = (datetime.utcnow() - file_start_time).total_seconds()
                self.logger.info(f"[PreprocessStage] ====== Finished processing {file_stem} in {file_duration:.2f}s ======")

        if not all_records:
            failure_reason = "No records produced from preprocessing"
            if last_exception:
                failure_reason = f"{failure_reason}. Last error: {last_exception}"

            # If all failures are due to scanned/image-only PDFs (OCR required), return SKIPPED instead of FAILED
            if failed_files and last_exception and "OCR required" in last_exception:
                return self._create_result(
                    status=StageStatus.SKIPPED,
                    metrics={
                        "processed_files": len(processed_files),
                        "failed_files": len(failed_files),
                        "failed_file_list": failed_files,
                        "reason": "scanned_pdf_needs_ocr",
                    },
                    error=failure_reason,
                    started_at=started_at,
                )

            return self._create_result(
                status=StageStatus.FAILED,
                metrics={
                    "processed_files": len(processed_files),
                    "failed_files": len(failed_files),
                    "failed_file_list": failed_files,
                },
                error=failure_reason,
                started_at=started_at,
            )

        # Calculate aggregate metrics
        total_chunks = len(all_records)
        mid_sentence_rate = round(total_mid_sentence_ends / max(total_chunks, 1), 4)

        # Ensure playbook_id is set from selection metadata if available
        final_playbook_id = playbook_selection_metadata.get("playbook_id") or playbook_id

        # Store aggregate metrics
        metrics_list = [
            {
                "file_stem": stem,
                "playbook_id": final_playbook_id,
                "sections": file_sections_counts.get(stem, 0),
                "chunks": file_chunk_counts.get(stem, 0),
                "mid_sentence_boundary_rate": mid_sentence_rate,
            }
            for stem in processed_files
        ]
        storage.put_metrics_json(metrics_list)

        finished_at = datetime.utcnow()

        # Build artifacts map
        artifacts = {
            "processed_jsonl": f"processed/{self.product_id}/v{self.version}/",
            "metrics_json": f"processed/{self.product_id}/v{self.version}/metrics.json",
        }

        # Aggregate extraction_type: scanned_pdf > mixed > digital_pdf (product-level)
        extraction_types_seen = list(file_extraction_types.values()) if file_extraction_types else [EXTRACTION_TYPE_DIGITAL_PDF]
        if EXTRACTION_TYPE_SCANNED_PDF in extraction_types_seen:
            product_extraction_type = EXTRACTION_TYPE_SCANNED_PDF
        elif EXTRACTION_TYPE_MIXED in extraction_types_seen:
            product_extraction_type = EXTRACTION_TYPE_MIXED
        else:
            product_extraction_type = EXTRACTION_TYPE_DIGITAL_PDF

        # Set resolved_settings.source_quality in chunking_config_used (native_pdf|scanned_ocr|mixed)
        if chunking_config_used and isinstance(chunking_config_used, dict):
            from primedata.config.models import extraction_type_to_source_quality, SOURCE_QUALITY_SCANNED_OCR
            # Abnormal OCR repetition in any file -> flag scanned_ocr for Text Integrity
            if ocr_any_abnormal:
                chunking_config_used["source_quality"] = SOURCE_QUALITY_SCANNED_OCR
            else:
                chunking_config_used["source_quality"] = extraction_type_to_source_quality(product_extraction_type)

        metrics = {
            "playbook_id": final_playbook_id,
            "playbook_selection": playbook_selection_metadata,  # Include selection metadata
            "processed_files": len(processed_files),
            "failed_files": len(failed_files),
            "total_sections": total_sections,
            "total_chunks": total_chunks,
            "mid_sentence_boundary_rate": mid_sentence_rate,
            "processed_file_list": processed_files,
            "file_chunk_counts": file_chunk_counts,
            "file_extraction_types": file_extraction_types,  # per-file extraction metadata
            "extraction_type": product_extraction_type,  # product-level: digital_pdf | scanned_pdf | mixed
            "chunking_config_used": chunking_config_used,
        }

        return self._create_result(
            status=StageStatus.SUCCEEDED,
            metrics=metrics,
            artifacts=artifacts,
            started_at=started_at,
            finished_at=finished_at,
        )

    def _process_document(
        self,
        raw_text: str,
        file_stem: str,
        filename: str,
        playbook: Dict[str, Any],
        playbook_id: str,
        chunking_config: Optional[Dict[str, Any]] = None,
        # Contract fields
        workspace_id: Optional[str] = None,
        version: Optional[str] = None,
        pipeline_run_id: Optional[str] = None,
        source_uri: Optional[str] = None,
        source_checksum: Optional[str] = None,
        extractor_version: Optional[str] = None,
        chunker_version: Optional[str] = None,
        embedding_model_id: Optional[str] = None,
        extraction_timestamp: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Process a single document through the preprocessing pipeline.

        Args:
            chunking_config: Optional product-level chunking configuration that overrides playbook settings
            Contract fields: workspace_id, version, pipeline_run_id, source_uri, source_checksum, etc.

        Returns:
            Tuple of (records_list, stats_dict)
        """
        # Compute source_checksum if not provided (sha256 of raw_text)
        if source_checksum is None:
            source_checksum = hashlib.sha256(raw_text.encode('utf-8')).hexdigest()
        
        # 1) Basic normalization (unwrap + PII redaction) - but NOT line-joining normalizers yet
        # We need to preserve page markers for page splitting
        unwrapped = normalize_wrapped_lines(raw_text)
        redacted = redact_pii(unwrapped)
        
        # 1.5) Remove boilerplate BEFORE chunking (headers/footers/page numbers/repeated nav)
        redacted, boilerplate_flags = _remove_boilerplate(redacted, min_repetitions=3)

        # 2) Split into pages FIRST (before applying normalizers that join lines)
        # This preserves page markers which are needed for correct page detection
        pages = split_pages_by_config(redacted, playbook.get("page_fences", []))

        # Log page splitting results
        if len(pages) > 1:
            self.logger.info(f"✅ Split text into {len(pages)} pages (page numbers: {[p['page'] for p in pages]})")
            std_logger.info(f"✅ Split text into {len(pages)} pages (page numbers: {[p['page'] for p in pages]})")
        else:
            self.logger.warning(
                f"⚠️ Page splitting found only {len(pages)} page(s). Page markers may be missing or not matching patterns."
            )
            std_logger.warning(
                f"⚠️ Page splitting found only {len(pages)} page(s). Page markers may be missing or not matching patterns."
            )

        # 3) Now apply normalizers to each page separately (after page markers have been used)
        # Filter out normalizers that join lines across page boundaries (we'll apply those per-page)
        line_joining_patterns = [
            r"(?m)(?<![.!?])\r?\n(?!\r?\n)",  # Join continuation lines
            r"(?m)\r?\n(?=[a-z])",  # Join lowercase-leading lines
        ]
        pre_normalizers = playbook.get("pre_normalizers", [])
        safe_normalizers = []
        line_joining_normalizers = []

        for norm in pre_normalizers:
            pattern = norm.get("pattern", "")
            if isinstance(pattern, list):
                pattern = "[" + "".join(str(c) for c in pattern) + "]"
            if not isinstance(pattern, str):
                self.logger.warning(
                    f"Normalizer pattern must be string or list, got {type(pattern)}: {pattern}, skipping"
                )
                continue
            # Check if this normalizer joins lines (could affect page markers)
            is_line_joiner = any(re.search(pat, pattern) for pat in line_joining_patterns)
            if is_line_joiner:
                line_joining_normalizers.append(norm)
            else:
                safe_normalizers.append(norm)

        # Apply safe normalizers to the full text (before page splitting, but they're safe)
        # Actually, we already split pages, so apply safe normalizers per-page
        # But first, let's apply them to the original redacted text for consistency
        # Actually, let's apply normalizers per-page after splitting

        # 4) Apply normalizers to each page
        normalized_pages = []
        for page_data in pages:
            page_text = page_data["text"]
            page_num = page_data["page"]

            # Apply all normalizers to this page
            normalized_text = apply_normalizers(page_text, pre_normalizers)
            
            # Apply preprocessing normalization: encoding artifacts, whitespace, repeated words
            # These are always applied (not conditional on flags) to ensure quality
            normalized_text = normalize_encoding_artifacts(normalized_text)
            normalized_text = normalize_whitespace(normalized_text)
            normalized_text = normalize_repeated_words(normalized_text)
            
            normalized_pages.append({"page": page_num, "text": normalized_text})

        # 5) Fix PDF extraction corruption: spaces between characters (e.g., "B e z o s" -> "Bezos")
        # This is a common issue with certain PDF extraction libraries
        cleaned_pages = []
        for page_data in normalized_pages:
            page_text = page_data["text"]
            page_num = page_data["page"]

            if len(page_text) > 100:
                sample = page_text[:1000]
                space_ratio = sample.count(" ") / len(sample) if len(sample) > 0 else 0
                if space_ratio > 0.3:  # More than 30% spaces suggests corruption
                    self.logger.warning(
                        f"Detected PDF extraction corruption on page {page_num} (space ratio: {space_ratio:.2%}), attempting to fix..."
                    )
                    std_logger.warning(
                        f"Detected PDF extraction corruption on page {page_num} (space ratio: {space_ratio:.2%}), attempting to fix..."
                    )
                    # Remove spaces between alphanumeric characters that are part of words
                    # Pattern: space between single alphanumeric characters -> remove space
                    # This fixes "B e z o s" -> "Bezos" by removing spaces between single chars
                    # Multiple passes needed: "B e z" -> "Be z" -> "Bez" (each pass fixes one space)
                    for _ in range(10):  # Multiple passes to catch all cases (10 should be enough for long corrupted words)
                        old_page_text = page_text
                        # Match: single alphanumeric, space, single alphanumeric
                        page_text = re.sub(r"([A-Za-z0-9]) ([A-Za-z0-9])", r"\1\2", page_text)
                        if page_text == old_page_text:
                            break
                    self.logger.info(f"Applied fix for PDF extraction corruption on page {page_num}")
                    std_logger.info(f"Applied fix for PDF extraction corruption on page {page_num}")

            cleaned_pages.append({"page": page_num, "text": page_text})

        # Log cleaned pages summary
        total_cleaned_chars = sum(len(p.get("text", "")) for p in cleaned_pages)
        pages_with_content = [p for p in cleaned_pages if p.get("text", "").strip()]
        self.logger.info(
            f"✅ Text cleaning completed for {file_stem}: "
            f"{len(cleaned_pages)} total pages, {len(pages_with_content)} pages with content, "
            f"{total_cleaned_chars:,} total characters"
        )
        std_logger.info(
            f"✅ Text cleaning completed: {len(cleaned_pages)} pages, "
            f"{len(pages_with_content)} with content, {total_cleaned_chars:,} chars"
        )
        
        if len(pages_with_content) == 0:
            # Provide a clearer hint for scanned/image-only PDFs (very low extracted text)
            actual_content = raw_text.replace("=== PAGE", "").replace("===", "").strip() if raw_text else ""
            actual_len = len(actual_content)
            msg_base = f"❌ No pages with content after cleaning for {file_stem}. All pages are empty. "
            if actual_len < 500:
                try:
                    record_dq_finding(
                        self._context_cache.get("db"),
                        workspace_id=UUID(str(workspace_id)) if workspace_id else None,
                        product_id=UUID(str(product_id)) if product_id else None,
                        pipeline_run_id=UUID(str(pipeline_run_id)) if pipeline_run_id else None,
                        raw_file_id=context.get("raw_file_id"),
                        chunk_id=None,
                        rule_name="ocr_required",
                        severity=RuleSeverity.ERROR,
                        passed=False,
                        details={"reason": "scanned_pdf", "actual_length": actual_len},
                    )
                except Exception:
                    # Swallow logging errors to avoid breaking pipeline
                    pass
                error_msg = (
                    msg_base
                    + f"Extracted only {actual_len} characters of actual content; this is likely a scanned/image-only PDF. "
                    + "Please OCR the document (e.g., OCRmyPDF/Tesseract/Textract) and re-upload a searchable PDF. "
                    + "Marking file as OCR_REQUIRED."
                )
                self.logger.error(error_msg)
                std_logger.error(error_msg)
                # Raise a specific exception so the caller can treat this as a soft failure (needs OCR)
                raise RuntimeError("OCR required: scanned or image-only PDF")
            else:
                error_msg = msg_base + "Text may have been removed by cleaning or PDF structure is incompatible."
                self.logger.error(error_msg)
                std_logger.error(error_msg)
                return [], {"sections": 0, "chunks": 0, "mid_sentence_ends": 0, "chunking_config_used": {}}

        # Combine pages back into single text for optimization (which works at document level)
        # Add page markers back so they can be detected during re-splitting after optimization
        # This preserves page information through the optimization step
        cleaned = "\n".join([f"\n=== PAGE {p['page']} ===\n{p['text']}" for p in cleaned_pages])

        # OCR cleanup + deduplication: repeated n-grams/lines, normalize whitespace, fix hyphenation
        # cleaned_text is what gets embedded; raw_text is stored for audit (document raw is in MinIO)
        doc_cleaned_after_ocr, doc_repetition_ratio, doc_ocr_noise_score = ocr_cleanup_and_metrics(cleaned)
        cleaned = doc_cleaned_after_ocr
        ocr_repetition_abnormal = is_abnormal_repetition(doc_repetition_ratio)
        if ocr_repetition_abnormal:
            self.logger.info(
                f"OCR cleanup: abnormal repetition_ratio={doc_repetition_ratio:.3f} for {file_stem}, flagging source_quality=scanned_ocr"
            )
            std_logger.info(
                f"OCR cleanup: abnormal repetition for {file_stem}, source_quality=scanned_ocr"
            )
        self.logger.debug(
            f"OCR cleanup for {file_stem}: repetition_ratio={doc_repetition_ratio:.3f}, ocr_noise_score={doc_ocr_noise_score:.3f}"
        )

        # Store page mapping for later use in chunk creation
        # We'll need to map chunk positions back to page numbers
        self._page_boundaries = []
        offset = 0
        for p in cleaned_pages:
            self._page_boundaries.append({"page": p["page"], "start": offset, "end": offset + len(p["text"])})
            offset += len(p["text"]) + 2  # +2 for "\n\n" separator

        # Apply pattern-based optimization at document level (fast, free)
        # LLM/hybrid optimization will be applied per-chunk after chunking
        preprocessing_flags = {}
        optimization_mode = "pattern"  # Default to pattern-based
        llm_config = None
        quality_threshold = 75

        if chunking_config:
            preprocessing_flags = chunking_config.get("preprocessing_flags", {})
            optimization_mode = chunking_config.get("optimization_mode", "pattern")
            quality_threshold = preprocessing_flags.get("llm_quality_threshold", 75)

            # Prepare LLM config if LLM or hybrid mode is enabled (for per-chunk optimization)
            if optimization_mode in ["llm", "hybrid"]:
                # Try to get LLM API key from workspace settings first, then environment
                llm_api_key = None

                # Get workspace_id and db from cached context (set in execute method)
                workspace_id = None
                db_session = None

                if hasattr(self, "_context_cache"):
                    workspace_id = self._context_cache.get("workspace_id")
                    db_session = self._context_cache.get("db")

                # Try to get from workspace settings
                if workspace_id and db_session:
                    try:
                        from uuid import UUID as UUIDType

                        from primedata.db.models import Workspace

                        # Convert string UUID to UUID object if needed
                        if isinstance(workspace_id, str):
                            workspace_id = UUIDType(workspace_id)

                        workspace = db_session.query(Workspace).filter(Workspace.id == workspace_id).first()

                        if workspace and workspace.settings:
                            llm_api_key = workspace.settings.get("openai_api_key")
                            if llm_api_key:
                                self.logger.info(
                                    f"✅ Using OpenAI API key from workspace settings for {optimization_mode} optimization (per-chunk)"
                                )
                                std_logger.info(
                                    f"✅ Using OpenAI API key from workspace settings for {optimization_mode} optimization (per-chunk)"
                                )
                    except Exception as e:
                        self.logger.warning(f"Failed to fetch API key from workspace settings: {e}")
                        std_logger.warning(f"Failed to fetch API key from workspace settings: {e}")

                # Fallback to environment variable if not found in workspace settings
                if not llm_api_key:
                    import os

                    llm_api_key = os.getenv("OPENAI_API_KEY")
                    if llm_api_key:
                        self.logger.info(
                            f"✅ Using OPENAI_API_KEY from environment variable for {optimization_mode} optimization (per-chunk)"
                        )
                        std_logger.info(
                            f"✅ Using OPENAI_API_KEY from environment variable for {optimization_mode} optimization (per-chunk)"
                        )

                if llm_api_key:
                    llm_config = {
                        "api_key": llm_api_key,
                        "model": preprocessing_flags.get("llm_model", "gpt-4-turbo-preview"),
                        "base_url": preprocessing_flags.get("llm_base_url"),  # Optional
                    }
                else:
                    self.logger.warning(
                        f"⚠️ Optimization mode is '{optimization_mode}' but OPENAI_API_KEY not found in workspace settings or environment. "
                        "Falling back to pattern-based optimization."
                    )
                    std_logger.warning(
                        f"⚠️ Optimization mode is '{optimization_mode}' but OPENAI_API_KEY not found in workspace settings or environment. "
                        "Falling back to pattern-based optimization."
                    )
                    optimization_mode = "pattern"  # Fallback to pattern-based

        # Apply pattern-based optimization at document level (fast, free, handles most issues)
        # This improves the base text quality before chunking
        if optimization_mode in ["pattern", "llm", "hybrid"]:
            try:
                from primedata.ingestion_pipeline.aird_stages.optimization.pattern_based import PatternBasedOptimizer

                pattern_optimizer = PatternBasedOptimizer()
                cleaned = pattern_optimizer.optimize(cleaned, preprocessing_flags)

                self.logger.info(f"✅ Pattern-based optimization applied at document level")
                std_logger.info(f"✅ Pattern-based optimization applied at document level")

            except ImportError as e:
                self.logger.warning(f"Pattern optimizer not available ({e}). Using legacy pattern-based optimization.")
                std_logger.warning(f"Pattern optimizer not available ({e}). Using legacy pattern-based optimization.")
                # Fallback to legacy pattern-based optimization
                if preprocessing_flags.get("enhanced_normalization"):
                    from primedata.ingestion_pipeline.aird_stages.utils.text_processing import apply_enhanced_normalization

                    self.logger.info("Applying enhanced normalization (legacy method)")
                    std_logger.info("Applying enhanced normalization (legacy method)")
                    cleaned = apply_enhanced_normalization(cleaned)

                if preprocessing_flags.get("error_correction"):
                    from primedata.ingestion_pipeline.aird_stages.utils.text_processing import apply_error_correction

                    self.logger.info("Applying error correction (legacy method)")
                    std_logger.info("Applying error correction (legacy method)")
                    cleaned = apply_error_correction(cleaned)
            except Exception as e:
                self.logger.error(f"Pattern-based optimization failed: {e}. Using original text.", exc_info=True)
                std_logger.error(f"Pattern-based optimization failed: {e}. Using original text.", exc_info=True)
                # Continue with original cleaned text

        # Store optimization config for per-chunk LLM optimization (if needed)
        self._optimization_config = {
            "mode": optimization_mode,
            "llm_config": llm_config,
            "quality_threshold": quality_threshold,
            "preprocessing_flags": preprocessing_flags,
        }

        # Re-split into pages after optimization (text structure should be preserved)
        # Use the page boundaries we stored earlier, or re-detect if markers are still present
        # Since we combined pages earlier, we need to re-split the optimized text
        # If page markers were preserved in optimization, they'll be detected; otherwise we'll use stored boundaries
        if hasattr(self, "_page_boundaries") and self._page_boundaries:
            # Use stored page boundaries to map back to page numbers
            # For now, re-split and hope markers are still there, or use stored page info
            pages = split_pages_by_config(cleaned, playbook.get("page_fences", []))
            # If re-split only found 1 page, use stored page boundaries
            if len(pages) == 1 and len(self._page_boundaries) > 1:
                # Fall back to stored page info - split by stored boundaries
                pages = []
                text_offset = 0
                for boundary in self._page_boundaries:
                    page_text = cleaned[boundary["start"] : min(boundary["end"], len(cleaned))]
                    if page_text.strip():
                        pages.append({"page": boundary["page"], "text": page_text})
                    text_offset = boundary["end"]
        else:
            # No stored boundaries, just re-split normally
            pages = split_pages_by_config(cleaned, playbook.get("page_fences", []))
        
        # Log re-split results
        self.logger.info(
            f"✅ Re-split after optimization for {file_stem}: "
            f"{len(pages)} pages found, {len(cleaned):,} total characters"
        )
        std_logger.info(
            f"✅ Re-split after optimization: {len(pages)} pages, {len(cleaned):,} chars"
        )

        # Validate that we have pages with content
        if not pages:
            error_msg = f"No pages found after optimization and re-splitting for {file_stem}. Original text length: {len(raw_text)}, Cleaned text length: {len(cleaned)}"
            self.logger.error(error_msg)
            std_logger.error(error_msg)
            return [], {
                "error": "No pages after processing",
                "sections": 0,
                "chunks": 0,
                "sections_detected": 0,
                "mid_sentence_ends": 0,
                "chunking_config_used": None,
            }
        
        # Check if all pages are empty
        pages_with_content = [p for p in pages if p.get("text", "").strip()]
        if not pages_with_content:
            error_msg = (
                f"All pages are empty after processing for {file_stem}. "
                f"Original text length: {len(raw_text)}, Cleaned text length: {len(cleaned)}. "
                f"Total pages: {len(pages)}"
            )
            self.logger.error(error_msg)
            std_logger.error(error_msg)
            return [], {
                "error": "All pages empty after processing",
                "sections": 0,
                "chunks": 0,
                "sections_detected": 0,
                "mid_sentence_ends": 0,
                "chunking_config_used": None,
            }
        
        # Use pages with content
        if len(pages_with_content) < len(pages):
            self.logger.warning(
                f"After processing: {len(pages_with_content)} pages with content (out of {len(pages)} total). "
                f"Some pages were empty and will be skipped."
            )
            std_logger.warning(
                f"After processing: {len(pages_with_content)} pages with content (out of {len(pages)} total)"
            )
        pages = pages_with_content
        self.logger.info(f"Processing {len(pages)} pages with content for {file_stem}")
        std_logger.info(f"Processing {len(pages)} pages with content for {file_stem}")
        
        # Log page content summary for debugging
        if pages:
            total_chars = sum(len(p.get("text", "")) for p in pages)
            avg_chars_per_page = total_chars // len(pages) if pages else 0
            self.logger.info(
                f"📄 Page summary for {file_stem}: "
                f"{len(pages)} pages, {total_chars:,} total chars, "
                f"{avg_chars_per_page:,} avg chars/page"
            )
            std_logger.info(
                f"📄 Page summary: {len(pages)} pages, {total_chars:,} chars"
            )
            
            # Log first few pages' content preview
            for i, page_data in enumerate(pages[:3]):
                page_text = page_data.get("text", "")
                page_num = page_data.get("page", i+1)
                preview = page_text[:150].replace('\n', '\\n')
                self.logger.debug(f"Page {page_num} preview: {preview}...")
        else:
            error_msg = f"❌ No pages with content after re-splitting for {file_stem}. Optimization may have removed all content."
            self.logger.error(error_msg)
            std_logger.error(error_msg)
            return [], {"sections": 0, "chunks": 0, "mid_sentence_ends": 0, "chunking_config_used": resolved_chunking_config}

        # Check for enhanced metadata extraction flag from chunking_config
        preprocessing_flags = {}
        if chunking_config:
            preprocessing_flags = chunking_config.get("preprocessing_flags", {})

        # 3) Get chunking config (product config overrides playbook defaults)
        playbook_chunking = playbook.get("chunking", {})

        # Ensure chunking_config is a valid dict (fix for None or invalid values)
        if not chunking_config or not isinstance(chunking_config, dict):
            self.logger.warning(
                f"chunking_config is {type(chunking_config).__name__}, initializing with defaults"
            )
            chunking_config = {
                "mode": "auto",
                "auto_settings": {"content_type": "general", "model_optimized": True, "confidence_threshold": 0.7},
                "manual_settings": {
                    "chunk_size": 1000,
                    "chunk_overlap": 200,
                    "min_chunk_size": 100,
                    "max_chunk_size": 2000,
                    "chunking_strategy": "fixed_size",
                },
            }

        # Track the resolved chunking configuration actually used
        resolved_chunking_config: Dict[str, Any] = {
            "mode": chunking_config.get("mode", "auto"),
            "source": None,  # manual | product_auto | playbook_default
        }
        hint_reason = None
        confidence_threshold = None
        confidence = None
        confidence_met = None

        # Priority: Product manual settings > Product auto settings > Playbook defaults
        if chunking_config and chunking_config.get("mode") == "manual":
            manual_settings = chunking_config.get("manual_settings", {})
            # Get original strategy from manual_settings (preserve UI value)
            original_strategy = manual_settings.get("chunking_strategy", playbook_chunking.get("strategy", "sentence"))

            # chunk_size is already in tokens, use it directly as max_tokens
            max_tokens = int(manual_settings.get("chunk_size", playbook_chunking.get("max_tokens", 900)))
            chunk_size = max_tokens
            # chunk_overlap is already in tokens
            chunk_overlap = int(manual_settings.get("chunk_overlap", 200))
            # Estimate: 1 sentence ≈ 20 tokens, so overlap_sentences = chunk_overlap / 20
            overlap_sents = max(1, int(chunk_overlap / 20))
            # Convert tokens to chars for hard_overlap: 1 token ≈ 4 chars
            hard_overlap = chunk_overlap * 4

            # Convert strategy for playbook processing (internal use only)
            strategy = original_strategy.lower()
            # Map fixed_size to char_chunk, semantic/sentence to sentence for playbook
            if strategy == "fixed_size":
                playbook_strategy = "char"
            elif strategy == "semantic":
                # Use paragraph chunking for semantic to better preserve context
                playbook_strategy = "paragraph"
            elif strategy == "paragraph_boundary":
                playbook_strategy = "paragraph"
            elif strategy in ["sentence", "sentence_boundary"]:
                playbook_strategy = "sentence"
            elif strategy == "recursive":
                playbook_strategy = "sentence"  # Recursive not directly supported, use sentence
            else:
                playbook_strategy = playbook_chunking.get("strategy", "sentence")

            # Store resolved config with ORIGINAL strategy from UI (not converted playbook strategy)
            resolved_chunking_config.update(
                {
                    "source": "manual",
                    "chunk_size": max_tokens,
                    "chunk_overlap": chunk_overlap,
                    "min_chunk_size": int(manual_settings.get("min_chunk_size", playbook_chunking.get("min_chunk_size", 100))),
                    "max_chunk_size": int(
                        manual_settings.get("max_chunk_size", playbook_chunking.get("max_chunk_size", 2000))
                    ),
                    "chunking_strategy": original_strategy,  # Preserve original UI value (semantic, fixed_size, etc.)
                }
            )
            
            # For manual mode, try to infer domain_type from resolved config if available
            detected_domain_type = None
            if chunking_config:
                resolved = chunking_config.get("resolved_settings", {})
                detected_domain_type = resolved.get("content_type")

            # Use playbook_strategy for actual chunking processing
            strategy = playbook_strategy
        elif chunking_config and chunking_config.get("mode") == "auto":
            # Auto mode: Check if resolved_settings already exist from auto-detection in task_preprocess
            # This avoids redundant content analysis and uses the pre-detected values
            resolved_settings = chunking_config.get("resolved_settings", {})
            
            # Ensure manual_settings exists with defaults (fix for missing structure after vector_creation_enabled changes)
            default_manual_settings = {
                "chunk_size": 1000,
                "chunk_overlap": 200,
                "min_chunk_size": 100,
                "max_chunk_size": 2000,
                "chunking_strategy": "fixed_size",
            }
            manual_settings = chunking_config.get("manual_settings", {})
            manual_settings_provided = (
                isinstance(manual_settings, dict)
                and bool(manual_settings)
                and manual_settings != default_manual_settings
            )
            if not manual_settings or not isinstance(manual_settings, dict):
                # Fallback to defaults if manual_settings is missing or invalid
                manual_settings = default_manual_settings.copy()
                chunking_config["manual_settings"] = manual_settings
                self.logger.info(f"✅ Initialized missing manual_settings with defaults: {manual_settings}")
                std_logger.info(f"✅ Initialized missing manual_settings with defaults")
                manual_settings_provided = False
            
            if resolved_settings and isinstance(resolved_settings, dict):
                confidence_threshold = 0.7
                auto_settings = chunking_config.get("auto_settings", {})
                if isinstance(auto_settings, dict):
                    confidence_threshold = auto_settings.get("confidence_threshold", confidence_threshold)
                resolved_confidence = resolved_settings.get("confidence")
                analysis_confidence = chunking_config.get("analysis_confidence")
                confidence_met = resolved_settings.get("confidence_met")
                low_confidence = (
                    confidence_met is False
                    or (resolved_confidence is not None and resolved_confidence < confidence_threshold)
                    or (analysis_confidence is not None and analysis_confidence < confidence_threshold)
                )
                if low_confidence:
                    self.logger.warning(
                        "Low confidence chunking detection; falling back to default/general chunking settings "
                        "(confidence=%.2f, analysis_confidence=%s, threshold=%.2f).",
                        resolved_confidence if resolved_confidence is not None else -1.0,
                        analysis_confidence,
                        confidence_threshold,
                    )
                    std_logger.warning("Low confidence chunking detection; falling back to defaults.")
                    resolved_settings = {
                        "chunk_size": resolved_settings.get("chunk_size", 1000),
                        "chunk_overlap": resolved_settings.get("chunk_overlap", 200),
                        "min_chunk_size": resolved_settings.get("min_chunk_size", 100),
                        "max_chunk_size": resolved_settings.get("max_chunk_size", 2000),
                        "chunking_strategy": "fixed_size",
                        "content_type": "general",
                        "confidence": resolved_confidence if resolved_confidence is not None else 0.0,
                        "reasoning": "Low confidence fallback to default chunking",
                        "evidence": resolved_settings.get("evidence"),
                    }

            if resolved_settings and isinstance(resolved_settings, dict):
                # Use existing resolved_settings from task_preprocess auto-detection (do not fall back to auto_settings)
                self.logger.info(
                    f"✅ Using existing resolved_settings from auto-detection: "
                    f"content_type={resolved_settings.get('content_type')}, "
                    f"chunk_size={resolved_settings.get('chunk_size')}, "
                    f"chunking_strategy={resolved_settings.get('chunking_strategy')}"
                )
                std_logger.info(
                    f"✅ Using existing resolved_settings from auto-detection"
                )
                self.logger.info(
                    "[CHUNKING_CONFIG] preprocess stage using: source=resolved_settings chunk_size=%s chunk_overlap=%s "
                    "chunking_strategy=%s content_type=%s (never auto_settings when resolved_settings present and confidence_met)",
                    resolved_settings.get("chunk_size"),
                    resolved_settings.get("chunk_overlap"),
                    resolved_settings.get("chunking_strategy"),
                    resolved_settings.get("content_type"),
                )
                std_logger.info(
                    "[CHUNKING_CONFIG] preprocess stage: source=resolved_settings chunk_size=%s content_type=%s",
                    resolved_settings.get("chunk_size"),
                    resolved_settings.get("content_type"),
                )
                # Extract values from resolved_settings with validation
                chunk_size = resolved_settings.get("chunk_size", 1000)
                chunk_overlap = resolved_settings.get("chunk_overlap", 200)
                min_chunk_size = resolved_settings.get("min_chunk_size", 100)
                max_chunk_size = resolved_settings.get("max_chunk_size", 2000)
                strategy = resolved_settings.get("chunking_strategy", "fixed_size")
                content_type = resolved_settings.get("content_type", "general")
                confidence = resolved_settings.get("confidence", 0.5)
                reasoning = resolved_settings.get("reasoning", "Auto-detected from sample files")
                evidence = resolved_settings.get("evidence")
                
                # Validate extracted values
                if not chunk_size or chunk_size <= 0:
                    self.logger.error(f"Invalid chunk_size from resolved_settings: {chunk_size}. Using default 1000.")
                    std_logger.error(f"Invalid chunk_size from resolved_settings: {chunk_size}. Using default 1000.")
                    chunk_size = 1000
                if chunk_overlap is None or chunk_overlap < 0:
                    self.logger.error(f"Invalid chunk_overlap from resolved_settings: {chunk_overlap}. Using default 200.")
                    std_logger.error(f"Invalid chunk_overlap from resolved_settings: {chunk_overlap}. Using default 200.")
                    chunk_overlap = 200
                if not strategy:
                    self.logger.error(f"Invalid strategy from resolved_settings: {strategy}. Using default 'fixed_size'.")
                    std_logger.error(f"Invalid strategy from resolved_settings: {strategy}. Using default 'fixed_size'.")
                    strategy = "fixed_size"
                
                # Allow manual_settings to override only if explicitly provided (not defaults)
                if manual_settings_provided:
                    if "chunk_size" in manual_settings and manual_settings.get("chunk_size"):
                        chunk_size = manual_settings["chunk_size"]
                        self.logger.info(f"Overriding chunk_size with manual_settings: {chunk_size}")
                        std_logger.info(f"Overriding chunk_size with manual_settings: {chunk_size}")
                    if "chunk_overlap" in manual_settings and manual_settings.get("chunk_overlap") is not None:
                        chunk_overlap = manual_settings["chunk_overlap"]
                        self.logger.info(f"Overriding chunk_overlap with manual_settings: {chunk_overlap}")
                    if "min_chunk_size" in manual_settings and manual_settings.get("min_chunk_size"):
                        min_chunk_size = manual_settings["min_chunk_size"]
                    if "max_chunk_size" in manual_settings and manual_settings.get("max_chunk_size"):
                        max_chunk_size = manual_settings["max_chunk_size"]
                    if "chunking_strategy" in manual_settings and manual_settings.get("chunking_strategy"):
                        strategy = manual_settings["chunking_strategy"]
                        self.logger.info(f"Overriding chunking_strategy with manual_settings: {strategy}")
                        std_logger.info(f"Overriding chunking_strategy with manual_settings: {strategy}")

                if chunk_size <= 0:
                    self.logger.warning(f"chunk_size {chunk_size} is invalid; using default 1000.")
                    std_logger.warning(f"chunk_size {chunk_size} is invalid; using default 1000.")
                    chunk_size = 1000
                if chunk_overlap is None or chunk_overlap < 0:
                    self.logger.warning(f"chunk_overlap {chunk_overlap} is invalid; using default 200.")
                    std_logger.warning(f"chunk_overlap {chunk_overlap} is invalid; using default 200.")
                    chunk_overlap = 200
                if chunk_overlap >= chunk_size:
                    adjusted_overlap = max(chunk_size - 1, 0)
                    self.logger.warning(
                        f"chunk_overlap {chunk_overlap} must be less than chunk_size {chunk_size}; "
                        f"using {adjusted_overlap}."
                    )
                    std_logger.warning(
                        f"chunk_overlap {chunk_overlap} must be less than chunk_size {chunk_size}; "
                        f"using {adjusted_overlap}."
                    )
                    chunk_overlap = adjusted_overlap
            else:
                # No resolved_settings, analyze content now (should only happen if auto-detection was skipped)
                self.logger.info("No resolved_settings found, running content analysis in preprocessing stage")
                std_logger.info("No resolved_settings found, running content analysis")
                
                # Sample cleaned text for analysis (use up to 20k chars for good detection)
                sample_text = cleaned[:20000] if len(cleaned) > 20000 else cleaned
                
                use_case_description = None
                if isinstance(self._context_cache, dict):
                    use_case_description = self._context_cache.get("use_case_description")
                playbook_hint = resolve_content_hint(playbook_id, use_case_description)
                hint_reason = None
                if playbook_hint and use_case_description:
                    hint_reason = "use_case_description"
                elif playbook_hint:
                    hint_reason = "playbook_id"
                
                # Analyze content using ContentAnalyzer
                try:
                    detected_config = content_analyzer.analyze_content(
                        content=sample_text,
                        filename=filename,
                        hint=playbook_hint
                    )
                    
                    # Use detected configuration
                    chunk_size = detected_config.chunk_size
                    chunk_overlap = detected_config.chunk_overlap
                    min_chunk_size = detected_config.min_chunk_size
                    max_chunk_size = detected_config.max_chunk_size
                    strategy = detected_config.strategy.value  # Convert enum to string
                    content_type = detected_config.content_type.value  # Convert enum to string
                    confidence = detected_config.confidence
                    reasoning = detected_config.reasoning
                    evidence = detected_config.evidence
                    
                    self.logger.info(
                        f"✅ Content analysis detected: {content_type} (confidence: {confidence:.2f}, strategy: {strategy}, "
                        f"chunk_size: {chunk_size}, overlap: {chunk_overlap})"
                    )
                    std_logger.info(
                        f"✅ Content analysis detected: {content_type} (confidence: {confidence:.2f}, strategy: {strategy}, "
                        f"chunk_size: {chunk_size}, overlap: {chunk_overlap})"
                    )
                    
                    # Allow manual_settings to override only if explicitly provided
                    if manual_settings_provided:
                        if manual_settings.get("chunk_size"):
                            chunk_size = manual_settings["chunk_size"]
                        if manual_settings.get("chunk_overlap"):
                            chunk_overlap = manual_settings["chunk_overlap"]
                        if manual_settings.get("min_chunk_size"):
                            min_chunk_size = manual_settings["min_chunk_size"]
                        if manual_settings.get("max_chunk_size"):
                            max_chunk_size = manual_settings["max_chunk_size"]
                        if manual_settings.get("chunking_strategy"):
                            strategy = manual_settings["chunking_strategy"]
                        
                except Exception as e:
                    # Fallback to default if analysis fails
                    self.logger.warning(f"Content analysis failed: {e}. Falling back to default configuration.", exc_info=True)
                    std_logger.warning(f"Content analysis failed: {e}. Falling back to default configuration.")
                    
                    # Fallback to general config
                    chunk_size = 1000
                    chunk_overlap = 200
                    min_chunk_size = 100
                    max_chunk_size = 2000
                    strategy = "fixed_size"
                    content_type = "general"
                    confidence = 0.3
                    reasoning = "Fallback to default due to analysis error"
                    evidence = None

            # Store domain_type for use when building records
            detected_domain_type = content_type  # Store for later use
            strategy_lower = strategy.lower()
            if strategy_lower == "fixed_size":
                playbook_strategy = "char"
            elif strategy_lower == "semantic":
                # Use paragraph chunking for semantic to better preserve context
                playbook_strategy = "paragraph"
            elif strategy_lower == "paragraph_boundary":
                playbook_strategy = "paragraph"
            elif strategy_lower in ["sentence", "sentence_boundary"]:
                playbook_strategy = "sentence"
            elif strategy_lower == "recursive":
                playbook_strategy = "sentence"  # Recursive not directly supported, use sentence
            else:
                playbook_strategy = playbook_chunking.get("strategy", "sentence")

            # chunk_size is already in tokens, use it directly as max_tokens
            max_tokens = int(chunk_size) if chunk_size else int(playbook_chunking.get("max_tokens", 900))
            
            # Validate max_tokens is reasonable (must be > 0 and < 10000)
            if max_tokens <= 0:
                self.logger.error(f"Invalid max_tokens: {max_tokens} (chunk_size: {chunk_size}). Using default 900.")
                std_logger.error(f"Invalid max_tokens: {max_tokens}. Using default 900.")
                max_tokens = 900
            elif max_tokens > 10000:
                self.logger.warning(f"max_tokens {max_tokens} is very large. Capping at 4000.")
                std_logger.warning(f"max_tokens {max_tokens} is very large. Capping at 4000.")
                max_tokens = 4000
            
            # Estimate: 1 sentence ≈ 20 tokens, so overlap_sentences = chunk_overlap / 20
            overlap_sents = max(1, int(chunk_overlap / 20))  # 1 sentence ≈ 20 tokens
            # Convert tokens to chars for hard_overlap: 1 token ≈ 4 chars
            hard_overlap = chunk_overlap * 4
            
            # Validate hard_overlap is reasonable
            if hard_overlap <= 0:
                hard_overlap = 300
                self.logger.warning(f"Invalid hard_overlap calculated: {hard_overlap}. Using default 300.")
                std_logger.warning(f"Invalid hard_overlap. Using default 300.")

            # Store resolved config with detection evidence
            resolved_chunking_config.update(
                {
                    "source": "product_auto",
                    "chunk_size": chunk_size,
                    "chunk_overlap": chunk_overlap,
                    "min_chunk_size": min_chunk_size,
                    "max_chunk_size": max_chunk_size,
                    "chunking_strategy": strategy,  # Preserve original UI value
                    "content_type": content_type,  # Store detected content type
                    "detection_confidence": confidence,  # Store confidence score
                    "detection_reasoning": reasoning,  # Store reasoning
                    "detection_evidence": evidence,  # Store evidence for UI
                    "hint_applied": bool(evidence and evidence.get("hint_applied")),
                    "hint_reason": hint_reason,
                }
            )

            # Use playbook_strategy for actual chunking processing
            strategy = playbook_strategy
        else:
            # Fallback to playbook defaults
            max_tokens = int(playbook_chunking.get("max_tokens", 900))
            overlap_sents = int(playbook_chunking.get("overlap_sentences", 2))
            hard_overlap = int(playbook_chunking.get("hard_overlap_chars", 300))
            strategy = (playbook_chunking.get("strategy", "sentence") or "sentence").lower()
            chunk_size = max_tokens
            chunk_overlap = overlap_sents * 20  # approximate tokens
            resolved_chunking_config.update(
                {
                    "source": "playbook_default",
                    "chunk_size": max_tokens,
                    "chunk_overlap": overlap_sents * 20,  # approximate tokens
                    "min_chunk_size": int(playbook_chunking.get("min_chunk_size", 100)),
                    "max_chunk_size": int(playbook_chunking.get("max_chunk_size", 2000)),
                    "chunking_strategy": "fixed_size" if strategy == "char" else "semantic",
                }
            )
            # For manual/playbook_default mode, try to infer domain_type from resolved config if available
            detected_domain_type = None
            if chunking_config:
                resolved = chunking_config.get("resolved_settings", {})
                detected_domain_type = resolved.get("content_type")

        # Log final chunking settings being used for processing
        self.logger.info(
            f"🔧 Final chunking settings for {file_stem}: "
            f"mode={chunking_config.get('mode', 'auto') if chunking_config else 'auto'}, "
            f"strategy={strategy}, chunk_size={chunk_size}, chunk_overlap={chunk_overlap}, "
            f"confidence={confidence}, confidence_threshold={confidence_threshold}, confidence_met={confidence_met}"
        )
        std_logger.info(
            f"🔧 Final chunking settings: mode={chunking_config.get('mode', 'auto') if chunking_config else 'auto'}, "
            f"strategy={strategy}, chunk_size={chunk_size}, chunk_overlap={chunk_overlap}"
        )

        # 4) Process pages and sections
        records: List[Dict[str, Any]] = []
        sections_detected = 0
        mid_sentence_ends = 0
        chunks_before_rules = 0

        # Log chunking configuration being used
        self.logger.info(
            f"📊 Chunking configuration for {file_stem}: "
            f"strategy={strategy}, max_tokens={max_tokens}, "
            f"overlap_sents={overlap_sents}, hard_overlap={hard_overlap}"
        )
        std_logger.info(
            f"📊 Chunking config: strategy={strategy}, max_tokens={max_tokens}"
        )
        
        # Validate configuration before processing
        if max_tokens <= 0:
            error_msg = f"Invalid chunking configuration: max_tokens={max_tokens}. Falling back to 900."
            self.logger.error(error_msg)
            std_logger.error(error_msg)
            max_tokens = 900
            chunk_size = max_tokens
        
        # First, estimate total chunks for progress tracking
        estimated_chunks = 0
        total_text_length = 0
        for page_data in pages:
            page_text = page_data["text"]
            total_text_length += len(page_text)
            try:
                sections = detect_sections_configured(
                    page_text,
                    playbook.get("headers", []),
                    playbook.get("section_aliases", {}),
                )
                for section_data in sections:
                    # Handle both old format (3-tuple) and new format (4-tuple with confidence)
                    if len(section_data) == 4:
                        title_raw, canon_section, body_text, _ = section_data
                    else:
                        title_raw, canon_section, body_text = section_data[:3]
                    if strategy == "paragraph":
                        para_overlap = max(1, int(overlap_sents / 2))
                        chunks = paragraph_chunk(body_text, max_tokens, para_overlap, hard_overlap)
                    elif strategy == "sentence":
                        chunks = sentence_chunk(body_text, max_tokens, overlap_sents, hard_overlap)
                    elif strategy == "char":
                        chunks = char_chunk(body_text, max_tokens, hard_overlap)
                    else:
                        chunks = sentence_chunk(body_text, max_tokens, overlap_sents, hard_overlap)
                    estimated_chunks += len(chunks)
            except Exception as e:
                self.logger.warning(f"Error estimating chunks for page {page_data.get('page', '?')}: {e}", exc_info=True)
                # Continue with estimation

        # Log initial progress info
        opt_config = getattr(self, "_optimization_config", None)
        opt_mode = opt_config.get("mode", "pattern") if opt_config else "pattern"
        if opt_mode in ["llm", "hybrid"]:
            self.logger.info(
                f"📊 Starting chunk processing: ~{estimated_chunks} chunks, ~{total_text_length:,} characters, mode={opt_mode}"
            )
            std_logger.info(
                f"📊 Starting chunk processing: ~{estimated_chunks} chunks, ~{total_text_length:,} characters, mode={opt_mode}"
            )

        # Track progress for periodic logging
        chunks_processed = 0
        chars_processed = 0
        last_progress_log_time = datetime.utcnow()
        PROGRESS_LOG_INTERVAL = 20  # Log progress every N chunks

        for page_data in pages:
            page_text = page_data["text"]
            page_num = page_data["page"]

            # Validate page has content
            if not page_text.strip():
                self.logger.warning(f"Skipping empty page {page_num} for {file_stem}")
                std_logger.warning(f"Skipping empty page {page_num} for {file_stem}")
                continue

            # Detect sections
            try:
                sections = detect_sections_configured(
                    page_text,
                    playbook.get("headers", []),
                    playbook.get("section_aliases", {}),
                )
                sections_detected += len(sections)
                
                # Log if no sections detected
                if not sections:
                    self.logger.warning(
                        f"No sections detected on page {page_num} for {file_stem}. "
                        f"Page text length: {len(page_text)}, Preview: {page_text[:100]}..."
                    )
                    std_logger.warning(
                        f"No sections detected on page {page_num} for {file_stem}. "
                        f"Text length: {len(page_text)}"
                    )
                    # Log first few lines of page text to help diagnose
                    if page_text:
                        first_lines = "\n".join(page_text.split("\n")[:3])
                        self.logger.debug(f"First 3 lines of page {page_num}: {first_lines}")
                    sections = [(f"Page {page_num}", "full_page", page_text, 0.0)]  # Low confidence for fallback
                    sections_detected += 1
            except Exception as e:
                self.logger.error(
                    f"Error detecting sections on page {page_num} for {file_stem}: {e}",
                    exc_info=True
                )
                std_logger.error(
                    f"Error detecting sections on page {page_num}: {e}"
                )
                continue

            # Process each section
            for section_data in sections:
                # Handle both old format (3-tuple) and new format (4-tuple with confidence)
                if len(section_data) == 4:
                    title_raw, canon_section, body_text, section_confidence = section_data
                else:
                    # Backward compatibility: old format without confidence
                    title_raw, canon_section, body_text = section_data[:3]
                    section_confidence = 0.5  # Default confidence for old format
                
                # If section confidence is low (< 0.3), mark section as "unknown"
                if section_confidence < 0.3:
                    canon_section = "unknown"
                    self.logger.debug(
                        f"Low section confidence ({section_confidence:.2f}) for '{title_raw}', "
                        f"marking as 'unknown' section"
                    )
                # Validate section has content
                if not body_text.strip():
                    self.logger.warning(
                        f"Skipping empty section '{canon_section}' on page {page_num} for {file_stem}"
                    )
                    std_logger.warning(
                        f"Skipping empty section '{canon_section}' on page {page_num} for {file_stem}"
                    )
                    continue
                # Chunk the section based on strategy
                if strategy == "paragraph":
                    # Use paragraph overlap (approximately 1 paragraph for overlap)
                    para_overlap = max(1, int(overlap_sents / 2))  # Convert sentence overlap to paragraph overlap
                    chunks = paragraph_chunk(body_text, max_tokens, para_overlap, hard_overlap)
                elif strategy == "sentence":
                    chunks = sentence_chunk(body_text, max_tokens, overlap_sents, hard_overlap)
                elif strategy == "char":
                    # Use character-based chunking for fixed_size strategy
                    chunks = char_chunk(body_text, max_tokens, hard_overlap)
                else:
                    # Default to sentence chunking for unknown strategies
                    chunks = sentence_chunk(body_text, max_tokens, overlap_sents, hard_overlap)

                # Log if chunks are empty
                if not chunks:
                    self.logger.error(
                        f"❌ No chunks created for section '{canon_section}' on page {page_num} for {file_stem}. "
                        f"Body text length: {len(body_text)}, Strategy: {strategy}, Max tokens: {max_tokens}, "
                        f"Overlap sentences: {overlap_sents}, Hard overlap: {hard_overlap}"
                    )
                    std_logger.error(
                        f"❌ No chunks created for section '{canon_section}' on page {page_num} for {file_stem}. "
                        f"Text length: {len(body_text)}, Strategy: {strategy}, Max tokens: {max_tokens}"
                    )
                    if body_text:
                        preview = body_text[:200].replace('\n', '\\n')
                        self.logger.debug(f"First 200 chars of body_text for section '{canon_section}': {preview}")
                    self.logger.warning(
                        f"Falling back to single chunk for section '{canon_section}' on page {page_num}."
                    )
                    std_logger.warning(
                        f"Falling back to single chunk for section '{canon_section}' on page {page_num}."
                    )
                    chunks = [body_text]

                chunks_before_rules += len(chunks)
                
                # Fix: Merge heading-only chunks with next chunk to improve quality
                # A chunk is considered heading-only if:
                # 1. Very short (< 200 chars, or < 50 chars is definitely heading)
                # 2. Has few lines (<= 2 lines)
                # 3. Mostly uppercase or title case (likely a heading)
                # 4. Contains only a single word or very few words
                merged_chunks = []
                i = 0
                while i < len(chunks):
                    chunk_text = chunks[i]
                    chunk_stripped = chunk_text.strip()
                    chunk_lines = chunk_stripped.split('\n')
                    is_short = len(chunk_stripped) < 200
                    is_very_short = len(chunk_stripped) < 50  # Definitely a heading
                    has_few_lines = len(chunk_lines) <= 2
                    # Check if mostly title case or uppercase (heading pattern)
                    words = chunk_stripped.split()
                    word_count = len(words)
                    is_single_word = word_count <= 1
                    is_few_words = word_count <= 3
                    
                    if words:
                        title_case_ratio = sum(1 for w in words if w and (w[0].isupper() or not w[0].isalpha())) / len(words)
                        is_mostly_title_case = title_case_ratio > 0.7
                    else:
                        is_mostly_title_case = False
                    
                    # More aggressive heading detection
                    is_likely_heading = (
                        is_very_short or  # Definitely heading if < 50 chars
                        (is_short and has_few_lines and (is_mostly_title_case or is_single_word)) or  # Short + few lines + title case or single word
                        (is_few_words and is_mostly_title_case)  # Few words + mostly title case
                    )
                    
                    # If this looks like a heading and there's a next chunk, merge them
                    if is_likely_heading and i + 1 < len(chunks):
                        next_chunk = chunks[i + 1]
                        merged_chunk = chunk_stripped + "\n\n" + next_chunk.strip()
                        merged_chunks.append(merged_chunk)
                        i += 2  # Skip next chunk as it's been merged
                        self.logger.debug(
                            f"Merged heading chunk with next chunk: section='{canon_section}', "
                            f"heading_length={len(chunk_text)}, merged_length={len(merged_chunk)}, "
                            f"heading_words={word_count}"
                        )
                    else:
                        merged_chunks.append(chunk_text)
                        i += 1
                
                chunks = merged_chunks
                
                # Merge tiny chunks (token_est < MIN_TOKENS) with neighbors
                # MIN_TOKENS default: 80-120 range (use 100 as default)
                min_tokens_threshold = playbook.get("chunking", {}).get("min_tokens", 100)
                if min_tokens_threshold is None:
                    min_tokens_threshold = 100  # Default: 100 tokens
                
                chunks_before_merge = len(chunks)
                chunks = _merge_tiny_chunks(chunks, min_tokens=min_tokens_threshold)
                chunks_after_merge = len(chunks)
                
                if chunks_before_merge != chunks_after_merge:
                    self.logger.info(
                        f"Merged tiny chunks for section '{canon_section}': "
                        f"{chunks_before_merge} -> {chunks_after_merge} chunks "
                        f"(min_tokens={min_tokens_threshold})"
                    )
                
                # Log first few chunks for debugging
                if chunks_processed == 0:
                    self.logger.info(
                        f"First chunk created: section='{canon_section}', page={page_num}, "
                        f"chunk_length={len(chunks[0])}, total_chunks_in_section={len(chunks)}"
                    )
                    std_logger.info(
                        f"First chunk created: section='{canon_section}', page={page_num}"
                    )

                # Build records for each chunk
                for idx, chunk_text in enumerate(chunks):
                    # Check for mid-sentence boundary (improved regex)
                    # Look for sentence-ending punctuation followed by optional quotes/parentheses and whitespace/newline
                    # Also check if chunk ends with a complete word (not mid-word)
                    chunk_stripped = chunk_text.strip()
                    chunk_tokens = estimate_tokens(chunk_text)  # Use shared estimate_tokens helper
                    
                    ends_with_punctuation = bool(re.search(r"[.!?]['\")\]]*\s*$", chunk_stripped))
                    ends_with_word_boundary = bool(re.search(r"\w\s*$", chunk_stripped))  # Ends with word char + optional whitespace
                    
                    # Consider it mid-sentence if:
                    # 1. Doesn't end with sentence punctuation, AND
                    # 2. Doesn't end at a natural word boundary (or is very short)
                    is_mid_sentence = not ends_with_punctuation and (not ends_with_word_boundary or len(chunk_stripped) < 20)
                    
                    if is_mid_sentence:
                        mid_sentence_ends += 1
                        # Diagnostic logging for mid-sentence breaks
                        if chunks_processed < 10 or mid_sentence_ends <= 5:  # Log first few for diagnostics
                            self.logger.warning(
                                f"⚠️ Mid-sentence break detected in chunk {chunks_processed + 1} "
                                f"(section: {canon_section}, page: {page_num}, tokens: {chunk_tokens}): "
                                f"'{chunk_stripped[-50:]}...'"
                            )
                    
                    # Diagnostic logging: log chunk statistics periodically
                    if chunks_processed < 5 or (chunks_processed % 50 == 0):
                        self.logger.info(
                            f"📊 Chunk {chunks_processed + 1}: tokens={chunk_tokens}, "
                            f"chars={len(chunk_text)}, ends_with_punct={ends_with_punctuation}, "
                            f"mid_sentence={is_mid_sentence}"
                        )

                    # Track progress
                    chunks_processed += 1
                    chars_processed += len(chunk_text)

                    # Log progress periodically
                    if opt_mode in ["llm", "hybrid"] and chunks_processed % PROGRESS_LOG_INTERVAL == 0:
                        elapsed_time = (datetime.utcnow() - last_progress_log_time).total_seconds()
                        chunks_per_sec = PROGRESS_LOG_INTERVAL / max(elapsed_time, 0.1)
                        remaining_chunks = estimated_chunks - chunks_processed
                        estimated_remaining_sec = remaining_chunks / max(chunks_per_sec, 0.1)
                        estimated_remaining_min = estimated_remaining_sec / 60

                        progress_msg = (
                            f"📈 Progress: {chunks_processed}/{estimated_chunks} chunks processed "
                            f"({chunks_processed*100//max(estimated_chunks, 1)}%), "
                            f"{chars_processed:,}/{total_text_length:,} chars ({chars_processed*100//max(total_text_length, 1)}%), "
                            f"~{estimated_remaining_min:.1f} min remaining"
                        )
                        self.logger.info(progress_msg)
                        std_logger.info(progress_msg)
                        last_progress_log_time = datetime.utcnow()

                    # Apply per-chunk LLM/hybrid optimization if needed
                    optimized_chunk_text = chunk_text
                    if hasattr(self, "_optimization_config"):
                        opt_config = self._optimization_config
                        opt_mode = opt_config.get("mode", "pattern")

                        # Apply LLM/hybrid optimization per-chunk if mode is llm or hybrid
                        # BUT: Only optimize chunks that need it (quality threshold) and limit total chunks
                        if opt_mode in ["llm", "hybrid"] and opt_config.get("llm_config"):
                            # Initialize stats if not already done
                            if not hasattr(self, "_chunk_optimization_stats"):
                                self._chunk_optimization_stats = {
                                    "total_chunks": 0,
                                    "llm_optimized": 0,
                                    "skipped_high_quality": 0,
                                    "failed": 0,
                                    "pattern_only": 0,
                                    "total_cost": 0.0,
                                }

                            self._chunk_optimization_stats["total_chunks"] += 1

                            # Quick quality check first - skip if already high quality
                            # This avoids unnecessary API calls
                            quality_threshold = opt_config.get("quality_threshold", 75)
                            try:
                                from primedata.ingestion_pipeline.aird_stages.optimization.pattern_based import (
                                    PatternBasedOptimizer,
                                )

                                quick_quality_check = PatternBasedOptimizer()
                                current_quality = quick_quality_check.estimate_quality(chunk_text)

                                # Skip LLM optimization if quality is already above threshold
                                # This significantly speeds up processing for good-quality chunks
                                if current_quality >= quality_threshold:
                                    self._chunk_optimization_stats["skipped_high_quality"] += 1
                                    optimized_chunk_text = chunk_text  # Use as-is
                                else:
                                    # Only optimize chunks that need improvement
                                    try:
                                        from primedata.ingestion_pipeline.aird_stages.optimization.hybrid import (
                                            HybridOptimizer,
                                        )

                                        optimizer = HybridOptimizer()
                                        # Note: pattern_flags is empty because pattern-based optimization
                                        # was already applied at document level. We only need LLM optimization here.
                                        chunk_result = optimizer.optimize(
                                            text=chunk_text,
                                            mode=opt_mode,
                                            pattern_flags={},  # Pattern-based already applied at document level
                                            llm_config=opt_config.get("llm_config"),
                                            quality_threshold=quality_threshold,
                                        )

                                        optimized_chunk_text = chunk_result["optimized_text"]

                                        if chunk_result["method_used"] in ["llm", "hybrid"]:
                                            self._chunk_optimization_stats["llm_optimized"] += 1
                                            self._chunk_optimization_stats["total_cost"] += chunk_result.get("cost", 0.0)
                                        else:
                                            self._chunk_optimization_stats["pattern_only"] += 1

                                    except Exception as e:
                                        self._chunk_optimization_stats["failed"] += 1
                                        self.logger.warning(f"Per-chunk LLM optimization failed for chunk {idx}: {e}")
                                        std_logger.warning(f"Per-chunk LLM optimization failed for chunk {idx}: {e}")
                                        # Use original chunk text on error
                                        optimized_chunk_text = chunk_text
                            except Exception as e:
                                # If quality check fails, try optimization anyway but log warning
                                self.logger.warning(f"Quality check failed for chunk {idx}, attempting optimization: {e}")
                                try:
                                    from primedata.ingestion_pipeline.aird_stages.optimization.hybrid import HybridOptimizer

                                    optimizer = HybridOptimizer()
                                    chunk_result = optimizer.optimize(
                                        text=chunk_text,
                                        mode=opt_mode,
                                        pattern_flags={},
                                        llm_config=opt_config.get("llm_config"),
                                        quality_threshold=quality_threshold,
                                    )
                                    optimized_chunk_text = chunk_result["optimized_text"]
                                    if chunk_result["method_used"] in ["llm", "hybrid"]:
                                        self._chunk_optimization_stats["llm_optimized"] += 1
                                        self._chunk_optimization_stats["total_cost"] += chunk_result.get("cost", 0.0)
                                    else:
                                        self._chunk_optimization_stats["pattern_only"] += 1
                                except Exception as opt_error:
                                    self._chunk_optimization_stats["failed"] += 1
                                    self.logger.warning(f"Per-chunk LLM optimization failed for chunk {idx}: {opt_error}")
                                    optimized_chunk_text = chunk_text

                    # Compute cleaned_text_hash for this chunk (sha256 of cleaned text)
                    cleaned_text_hash = hashlib.sha256(optimized_chunk_text.encode('utf-8')).hexdigest()
                    # OCR cleanup metrics per chunk (for Text Integrity / quality)
                    cleanup_metrics = chunk_cleanup_metrics(optimized_chunk_text)
                    
                    # Build record with optimized chunk text and all contract fields
                    rec = _build_record(
                        stem=file_stem,
                        filename=filename,
                        document_id=file_stem,
                        page=page_num,
                        canon_section=canon_section,
                        title_raw=title_raw,
                        text=optimized_chunk_text,
                        chunk_idx=idx,
                        chunk_of=len(chunks),
                        product_id=self.product_id,
                        domain_type=detected_domain_type,  # Pass domain_type for domain-adaptive scoring
                        section_confidence=section_confidence,  # Pass section confidence for metadata consistency
                        # Contract fields
                        workspace_id=workspace_id,
                        version=version,
                        pipeline_run_id=pipeline_run_id,
                        source_uri=source_uri,
                        source_checksum=source_checksum,
                        extractor_version=extractor_version,
                        chunker_version=chunker_version,
                        embedding_model_id=embedding_model_id,
                        extraction_timestamp=extraction_timestamp,
                        boilerplate_flags=boilerplate_flags,
                        cleaned_text_hash=cleaned_text_hash,
                        raw_text=optimized_chunk_text,
                        cleaned_text=optimized_chunk_text,
                        repetition_ratio=cleanup_metrics.get("repetition_ratio"),
                        ocr_noise_score=cleanup_metrics.get("ocr_noise_score"),
                    )
                    
                    # Log domain_type for verification (only log first chunk to avoid spam)
                    if idx == 0:
                        if detected_domain_type:
                            self.logger.info(f"✅ Record {rec['chunk_id']} has domain_type: {detected_domain_type}")
                            std_logger.info(f"✅ Record {rec['chunk_id']} has domain_type: {detected_domain_type}")
                        else:
                            self.logger.warning(f"⚠️ Record {rec['chunk_id']} missing domain_type (detected_domain_type was None)")
                            std_logger.warning(f"⚠️ Record {rec['chunk_id']} missing domain_type")

                    # Enhanced metadata extraction if flag is set
                    if preprocessing_flags.get("force_metadata_extraction") or preprocessing_flags.get(
                        "additional_metadata_fields"
                    ):
                        # Extract additional metadata fields
                        import re as regex_module

                        # Try to extract dates from text
                        date_patterns = [
                            r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b",  # MM/DD/YYYY or DD/MM/YYYY
                            r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b",  # Month DD, YYYY
                            r"\b\d{4}-\d{2}-\d{2}\b",  # ISO format YYYY-MM-DD
                        ]

                        dates_found = []
                        for pattern in date_patterns:
                            matches = regex_module.findall(pattern, chunk_text, regex_module.IGNORECASE)
                            dates_found.extend(matches[:3])  # Limit to 3 dates per chunk

                        if dates_found:
                            rec["doc_date"] = dates_found[0]  # Use first date found
                            # Store all dates in tags if additional fields requested
                            if preprocessing_flags.get("additional_metadata_fields"):
                                existing_tags = rec.get("tags", "")
                                if existing_tags:
                                    rec["tags"] = f"{existing_tags}; dates:{','.join(dates_found[:3])}"
                                else:
                                    rec["tags"] = f"dates:{','.join(dates_found[:3])}"

                        # Extract additional metadata if additional_fields flag is set
                        if preprocessing_flags.get("additional_metadata_fields"):
                            # Extract potential author names (simple pattern: "By Author Name" or "Author: Name")
                            author_pattern = r"(?:By|Author|Written by|Created by):\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)"
                            author_match = regex_module.search(author_pattern, chunk_text, regex_module.IGNORECASE)
                            if author_match:
                                author = author_match.group(1)
                                existing_tags = rec.get("tags", "")
                                if existing_tags:
                                    rec["tags"] = f"{existing_tags}; author:{author}"
                                else:
                                    rec["tags"] = f"author:{author}"

                            # Extract version numbers
                            version_pattern = r"\b(v|version|ver|v\.)\s*(\d+(?:\.\d+)+)\b"
                            version_matches = regex_module.findall(version_pattern, chunk_text, regex_module.IGNORECASE)
                            if version_matches:
                                versions = [m[1] for m in version_matches[:2]]  # Limit to 2 versions
                                existing_tags = rec.get("tags", "")
                                if existing_tags:
                                    rec["tags"] = f"{existing_tags}; versions:{','.join(versions)}"
                                else:
                                    rec["tags"] = f"versions:{','.join(versions)}"

                    # Apply audience rules from playbook
                    aud = rec["audience"]
                    for rule in playbook.get("audience_rules", []) or []:
                        try:
                            pat = rule.get("pattern")
                            if pat and (
                                re.search(pat, title_raw, flags=re.IGNORECASE)
                                or re.search(pat, chunk_text, flags=re.IGNORECASE)
                            ):
                                aud = rule.get("audience", aud)
                                break
                        except re.error:
                            pass
                    rec["audience"] = aud

                    # Lineage: chunk-level
                    try:
                        record_lineage(
                            self._context_cache.get("db"),
                            workspace_id=UUID(str(workspace_id)) if workspace_id else None,
                            product_id=UUID(str(product_id)) if product_id else None,
                            pipeline_run_id=UUID(str(pipeline_run_id)) if pipeline_run_id else None,
                            raw_file_id=None,
                            lineage_type=LineageType.CHUNK,
                            chunk_id=rec.get("chunk_id"),
                            source_file=filename,
                            page_start=page_num,
                            page_end=page_num,
                            transformation="chunking",
                            transform_version=rec.get("chunker_version") or "1.0",
                            model_name=None,
                            model_version=None,
                            status="succeeded",
                            details={
                                "section": canon_section,
                                "token_est": chunk_tokens,
                                "mid_sentence": is_mid_sentence,
                                "chars": len(chunk_text),
                            },
                        )
                    except Exception:
                        pass

                    records.append(rec)

        # Log final progress
        if opt_mode in ["llm", "hybrid"]:
            final_progress_msg = (
                f"✅ Chunk processing complete: {chunks_processed} chunks processed, "
                f"{chars_processed:,} characters processed"
            )
            self.logger.info(final_progress_msg)
            std_logger.info(final_progress_msg)

        # Log per-chunk optimization summary if LLM/hybrid mode was used
        if hasattr(self, "_chunk_optimization_stats"):
            stats_data = self._chunk_optimization_stats
            opt_config = self._optimization_config
            opt_mode = opt_config.get("mode", "pattern")

            if opt_mode in ["llm", "hybrid"]:
                summary_msg = (
                    f"✅ Per-chunk optimization summary: "
                    f"{stats_data['llm_optimized']}/{stats_data['total_chunks']} chunks optimized with LLM, "
                    f"{stats_data['skipped_high_quality']} skipped (already high quality ≥75%), "
                    f"{stats_data['pattern_only']} pattern-only, "
                    f"{stats_data['failed']} failed, "
                    f"total cost=${stats_data['total_cost']:.4f}"
                )
                self.logger.info(summary_msg)
                std_logger.info(summary_msg)

            # Reset stats for next document
            delattr(self, "_chunk_optimization_stats")

        # Calculate stats
        total_chunks = len(records)
        mid_sentence_rate = round(mid_sentence_ends / max(total_chunks, 1), 4)

        # Log comprehensive summary
        self.logger.info(
            f"📊 Processing summary for {file_stem}: "
            f"pages={len(pages)}, sections_detected={sections_detected}, "
            f"total_chunks={total_chunks}, mid_sentence_rate={mid_sentence_rate:.4f}"
        )
        std_logger.info(
            f"📊 Summary for {file_stem}: pages={len(pages)}, sections={sections_detected}, chunks={total_chunks}"
        )

        self.logger.info(
            f"📊 Chunking diagnostics for {file_stem}: "
            f"pages_with_content={len(pages)}, "
            f"chunks_before_rules={chunks_before_rules}, "
            f"chunks_after_rules={total_chunks}, "
            f"records_written_to_db={len(records)}"
        )
        std_logger.info(
            f"📊 Chunking diagnostics: pages_with_content={len(pages)}, "
            f"chunks_before_rules={chunks_before_rules}, "
            f"chunks_after_rules={total_chunks}, "
            f"records_written_to_db={len(records)}"
            f"chunks_after_rules={total_chunks}"
        )
        std_logger.info(
            f"📊 Chunking diagnostics: pages_with_content={len(pages)}, "
            f"chunks_before_rules={chunks_before_rules}, chunks_after_rules={total_chunks}"
        )
        
        # If no records were created, provide detailed diagnostic info
        if total_chunks == 0:
            self.logger.error(
                f"❌ No records created for {file_stem}! "
                f"Pages processed: {len(pages)}, Sections detected: {sections_detected}, "
                f"Strategy: {strategy}, Max tokens: {max_tokens}, "
                f"chunk_size={chunk_size}, chunk_overlap={chunk_overlap}"
            )
            std_logger.error(
                f"❌ No records created for {file_stem}! "
                f"Pages: {len(pages)}, Sections: {sections_detected}"
            )
            # Log sample page text to help diagnose
            if pages and pages[0].get("text"):
                sample_page = pages[0]["text"]
                self.logger.error(
                    f"Sample page text (first 500 chars): {sample_page[:500]}"
                )

        stats = {
            "playbook_id": playbook_id,
            "sections": sections_detected,
            "chunks": total_chunks,
            "mid_sentence_boundary_rate": mid_sentence_rate,
            "mid_sentence_ends": mid_sentence_ends,
            "chunking_config_used": resolved_chunking_config,
            "ocr_repetition_abnormal": ocr_repetition_abnormal,
        }

        return records, stats

    def _get_pdf_sample_for_routing(
        self, 
        storage, 
        file_stem: str, 
        storage_key: Optional[str], 
        storage_bucket: Optional[str],
        max_chars: int = 2000
    ) -> Optional[str]:
        """
        Extract sample text from PDF for playbook routing (optimization: only first 2 pages).
        
        Args:
            storage: Storage adapter instance
            file_stem: File stem
            storage_key: Optional storage key
            storage_bucket: Optional storage bucket
            max_chars: Maximum characters to extract
            
        Returns:
            Sample text or None if extraction fails
        """
        try:
            from io import BytesIO
            from primedata.storage.minio_client import get_minio_client
            
            minio_client = get_minio_client()
            bucket = storage_bucket or "primedata-raw"
            key = storage_key or f"{storage._get_raw_prefix()}{file_stem}.pdf"
            
            # Get PDF bytes
            pdf_data = minio_client.get_bytes(bucket, key)
            if not pdf_data:
                return None
            
            # Extract only first 2 pages
            try:
                from pypdf import PdfReader
                pdf_file = BytesIO(pdf_data)
                reader = PdfReader(pdf_file)
                
                text_parts = []
                for i, page in enumerate(reader.pages[:2]):  # Only first 2 pages
                    try:
                        page_text = page.extract_text()
                        text_parts.append(page_text)
                        if len(''.join(text_parts)) > max_chars:
                            break
                    except Exception:
                        continue
                
                sample_text = '\n'.join(text_parts)
                return sample_text[:max_chars] if sample_text else None
            except ImportError:
                # Fallback to PyPDF2
                try:
                    from PyPDF2 import PdfReader
                    pdf_file = BytesIO(pdf_data)
                    reader = PdfReader(pdf_file)
                    text_parts = []
                    for page in reader.pages[:2]:  # Only first 2 pages
                        text_parts.append(page.extract_text())
                    sample_text = '\n'.join(text_parts)
                    return sample_text[:max_chars] if sample_text else None
                except Exception:
                    return None
        except Exception as e:
            self.logger.warning(f"Failed to extract PDF sample for routing: {e}")
            return None

    def _get_text_sample_for_routing(
        self,
        storage,
        file_stem: str,
        storage_key: Optional[str],
        storage_bucket: Optional[str],
        max_chars: int = 2000
    ) -> Optional[str]:
        """
        Get sample text from text file for playbook routing (optimization: only first N chars).
        
        Args:
            storage: Storage adapter instance
            file_stem: File stem
            storage_key: Optional storage key
            storage_bucket: Optional storage bucket
            max_chars: Maximum characters to read
            
        Returns:
            Sample text or None if reading fails
        """
        try:
            from primedata.storage.minio_client import get_minio_client
            
            minio_client = get_minio_client()
            bucket = storage_bucket or "primedata-raw"
            key = storage_key or f"{storage._get_raw_prefix()}{file_stem}.txt"
            
            # Get object bytes
            data = minio_client.get_bytes(bucket, key)
            if not data:
                return None
            
            # Try to decode as UTF-8 and return first max_chars
            try:
                text = data.decode("utf-8", errors="ignore")
                return text[:max_chars]
            except Exception:
                return None
        except Exception as e:
            self.logger.warning(f"Failed to read text sample for routing: {e}")
            return None
