"""
OCR cleanup and deduplication for preprocessing.

- Remove repeated n-grams and repeated lines (exact and near-duplicates).
- Normalize whitespace, fix broken hyphenation, remove repeated headers/footers.
- Compute repetition_ratio and ocr_noise_score per text/chunk for quality metrics.
"""

import re
from typing import Any, Dict, Tuple

from loguru import logger

from .text_processing import (
    normalize_whitespace,
    normalize_wrapped_lines,
)


# Threshold above which we consider repetition "abnormal" (flag source_quality=scanned_ocr)
REPETITION_RATIO_SCANNED_OCR_THRESHOLD = 0.20

# Minimum line length to count as "content" for repetition (skip very short lines)
MIN_LINE_LEN_FOR_REPETITION = 3

# N-gram size and min occurrences for n-gram dedupe
NGRAM_SIZE = 4
NGRAM_MIN_OCCURRENCES = 3


def _normalize_line_for_dedup(line: str) -> str:
    """Normalize a line for near-duplicate detection (lowercase, collapse whitespace)."""
    return re.sub(r"\s+", " ", (line or "").strip().lower())


def _remove_repeated_lines(text: str, min_repetitions: int = 2) -> Tuple[str, float]:
    """
    Remove repeated lines (exact and near-duplicate). Keep first occurrence.
    Returns (cleaned_text, repetition_ratio) where repetition_ratio is the fraction
    of non-empty lines that were duplicates (0 = none, 1 = all duplicate).
    """
    if not text or not text.strip():
        return text, 0.0
    lines = text.split("\n")
    # Count by normalized form for near-duplicate detection
    norm_to_first: Dict[str, str] = {}
    norm_count: Dict[str, int] = {}
    for line in lines:
        stripped = line.strip()
        if len(stripped) < MIN_LINE_LEN_FOR_REPETITION:
            continue
        norm = _normalize_line_for_dedup(stripped)
        if norm not in norm_to_first:
            norm_to_first[norm] = stripped
            norm_count[norm] = 0
        norm_count[norm] += 1
    # Build cleaned: keep first occurrence of each normalized line; drop repeats
    seen_norm = set()
    cleaned_lines = []
    duplicate_line_count = 0
    content_line_count = 0
    for line in lines:
        stripped = line.strip()
        if len(stripped) < MIN_LINE_LEN_FOR_REPETITION:
            cleaned_lines.append(line)
            continue
        norm = _normalize_line_for_dedup(stripped)
        content_line_count += 1
        if norm_count[norm] >= min_repetitions:
            if norm in seen_norm:
                duplicate_line_count += 1
                continue
            seen_norm.add(norm)
        cleaned_lines.append(line)
    repetition_ratio = (
        duplicate_line_count / content_line_count if content_line_count else 0.0
    )
    return "\n".join(cleaned_lines), min(1.0, repetition_ratio)


def _remove_repeated_ngrams(text: str, n: int = NGRAM_SIZE, min_occ: int = NGRAM_MIN_OCCURRENCES) -> str:
    """
    Remove repeated word n-grams: keep first occurrence of each n-gram that appears min_occ+ times.
    Skips subsequent occurrences of repeated n-grams (dedupe).
    """
    if not text or n <= 0:
        return text
    words = text.split()
    if len(words) < n * min_occ:
        return text
    ngram_counts: Dict[Tuple[str, ...], int] = {}
    for i in range(len(words) - n + 1):
        ng = tuple(words[i : i + n])
        ngram_counts[ng] = ngram_counts.get(ng, 0) + 1
    repeated_ngrams = {ng for ng, c in ngram_counts.items() if c >= min_occ}
    if not repeated_ngrams:
        return text
    # Emit words; skip runs that are duplicate of an already-emitted repeated n-gram
    out_words: list = []
    emitted_ngrams: set = set()
    i = 0
    while i < len(words):
        if i + n <= len(words):
            ng = tuple(words[i : i + n])
            if ng in repeated_ngrams and ng in emitted_ngrams:
                i += 1
                continue
            if ng in repeated_ngrams:
                emitted_ngrams.add(ng)
        out_words.append(words[i])
        i += 1
    return " ".join(out_words)


def _ocr_noise_heuristic(text: str, repetition_ratio: float) -> float:
    """
    Compute OCR noise score in [0, 1] (1 = clean, 0 = very noisy).
    Combines repetition ratio with odd-character ratio (non-alpha, non-punct, non-space).
    """
    if not text or len(text) < 10:
        return 1.0
    # Odd chars: not alphanumeric, not common punctuation, not space
    odd = sum(
        1
        for c in text
        if not (c.isalnum() or c.isspace() or c in ".,;:!?-'\"()[]/\\@#%&*")
    )
    odd_ratio = odd / len(text)
    # Repetition penalty
    rep_penalty = min(1.0, repetition_ratio * 2.0)  # scale so 0.5 rep -> 1.0 penalty
    # Odd-char penalty
    odd_penalty = min(1.0, odd_ratio * 5.0)  # 20% odd -> 1.0 penalty
    # Combined: 1 - weighted penalty
    penalty = 0.6 * rep_penalty + 0.4 * odd_penalty
    return max(0.0, min(1.0, 1.0 - penalty))


def ocr_cleanup_and_metrics(
    text: str,
    *,
    normalize_ws: bool = True,
    fix_hyphenation: bool = True,
    remove_repeated_lines: bool = True,
    remove_repeated_ngrams: bool = True,
    min_line_repetitions: int = 2,
) -> Tuple[str, float, float]:
    """
    Run OCR cleanup and compute quality metrics.

    Steps (all optional):
    - Normalize whitespace
    - Fix broken hyphenation (wrapped lines)
    - Remove repeated lines (exact + near-duplicate)
    - Remove repeated n-grams

    Returns:
        (cleaned_text, repetition_ratio, ocr_noise_score)
        - repetition_ratio: fraction of content that was duplicate (0-1)
        - ocr_noise_score: 0-1, 1 = clean (for Text Integrity / quality)
    """
    if not text or not text.strip():
        return text or "", 0.0, 1.0
    current = text.strip()
    total_content_len = len(current)
    repetition_ratio = 0.0

    if fix_hyphenation:
        current = normalize_wrapped_lines(current)
    if normalize_ws:
        current = normalize_whitespace(current)

    if remove_repeated_lines:
        current, line_rep_ratio = _remove_repeated_lines(current, min_repetitions=min_line_repetitions)
        repetition_ratio = max(repetition_ratio, line_rep_ratio)
    if remove_repeated_ngrams:
        current = _remove_repeated_ngrams(current, n=NGRAM_SIZE, min_occ=NGRAM_MIN_OCCURRENCES)
        # Recompute line repetition on result for metric (ngram dedupe doesn't change line rep much)
        _, line_rep_after = _remove_repeated_lines(current, min_repetitions=min_line_repetitions)
        repetition_ratio = max(repetition_ratio, line_rep_after)

    ocr_noise_score = _ocr_noise_heuristic(current, repetition_ratio)
    return current, repetition_ratio, ocr_noise_score


def chunk_cleanup_metrics(chunk_text: str) -> Dict[str, Any]:
    """
    Compute cleanup metrics for a single chunk (for storage in record).
    Runs full OCR cleanup pipeline and returns repetition_ratio and ocr_noise_score.
    """
    if not chunk_text or not chunk_text.strip():
        return {"repetition_ratio": 0.0, "ocr_noise_score": 1.0}
    _, repetition_ratio, ocr_noise_score = ocr_cleanup_and_metrics(
        chunk_text,
        normalize_ws=True,
        fix_hyphenation=True,
        remove_repeated_lines=True,
        remove_repeated_ngrams=True,
    )
    return {
        "repetition_ratio": round(repetition_ratio, 4),
        "ocr_noise_score": round(ocr_noise_score, 4),
    }


def is_abnormal_repetition(repetition_ratio: float) -> bool:
    """Return True if repetition ratio indicates scanned/OCR content (flag source_quality=scanned_ocr)."""
    return repetition_ratio >= REPETITION_RATIO_SCANNED_OCR_THRESHOLD
