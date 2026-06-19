"""
Pattern-based text optimization using regex and rule-based processing.

This module contains functions for fast, deterministic text optimization
without requiring LLM APIs.
"""

from typing import Any, Dict, Optional

import regex as re
from loguru import logger
from primedata.ingestion_pipeline.aird_stages.utils.text_processing import (
    apply_enhanced_normalization,
    apply_error_correction,
)


class PatternBasedOptimizer:
    """Pattern-based text optimizer using regex and rule-based processing."""

    def optimize(self, text: str, flags: Optional[Dict[str, bool]] = None) -> str:
        """
        Optimize text using pattern-based methods.

        Args:
            text: Input text to optimize
            flags: Dictionary of optimization flags:
                - enhanced_normalization: Apply enhanced normalization
                - error_correction: Apply error correction
                - extract_metadata: Extract metadata (handled separately)

        Returns:
            Optimized text
        """
        if not text:
            return text

        optimized = text
        flags = flags or {}

        # Apply enhanced normalization if enabled
        if flags.get("enhanced_normalization"):
            logger.debug("Applying enhanced normalization (pattern-based)")
            optimized = apply_enhanced_normalization(optimized)

        # Apply error correction if enabled
        if flags.get("error_correction"):
            logger.debug("Applying error correction (pattern-based)")
            optimized = apply_error_correction(optimized)

        return optimized

    def estimate_quality(self, text: str) -> float:
        """
        Quick quality estimation using heuristics.

        This is a fast approximation, not full quality scoring.
        Used to decide if LLM enhancement is needed.

        Args:
            text: Text to evaluate

        Returns:
            Quality score (0-100)
        """
        if not text or len(text.strip()) == 0:
            return 0.0

        # Check for excessive spaces (corruption indicator)
        space_ratio = 0.0
        if len(text) > 100:
            sample = text[:500]
            space_ratio = sample.count(" ") / len(sample) if len(sample) > 0 else 0
            if space_ratio > 0.3:
                return 40.0  # Likely corrupted
        elif len(text) > 0:
            # For short text, calculate space ratio on the whole text
            space_ratio = text.count(" ") / len(text) if len(text) > 0 else 0

        # Check for common OCR errors
        ocr_error_patterns = [r"\bteh\b", r"\badn\b", r"\bhte\b", r"\btha\b", r"\btaht\b"]
        ocr_errors = 0
        for pattern in ocr_error_patterns:
            ocr_errors += len(re.findall(pattern, text, re.IGNORECASE))

        word_count = len(text.split())
        error_ratio = ocr_errors / max(word_count, 1)

        # Base score
        base_score = 80.0

        # Deduct for issues
        quality = base_score - (space_ratio * 100) - (error_ratio * 20)

        # Check for basic text quality indicators
        if len(text) < 50:
            quality -= 10  # Very short text

        if not any(c.isupper() for c in text):
            quality -= 5  # No capitalization

        if text.count(".") + text.count("!") + text.count("?") == 0:
            quality -= 5  # No sentence endings

        return max(0.0, min(100.0, quality))
