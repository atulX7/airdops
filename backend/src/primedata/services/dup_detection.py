"""
Lightweight duplicate detection for chunk-level duplicate ratio scoring.

Uses simple shingles (n-grams) approach without external heavy libraries.
"""

import hashlib
from typing import List, Set


def compute_shingles(text: str, n: int = 5) -> Set[int]:
    """
    Compute n-gram shingles (hashed) from normalized text.
    
    Args:
        text: Input text
        n: Size of n-grams (default 5)
        
    Returns:
        Set of hash values for each n-gram
    """
    # Normalize: lowercase, remove extra whitespace
    normalized = " ".join(text.lower().split())
    
    if len(normalized) < n:
        return set()
    
    shingles = set()
    for i in range(len(normalized) - n + 1):
        ngram = normalized[i:i+n]
        # Use hash for memory efficiency
        shingle_hash = hash(ngram)
        shingles.add(shingle_hash)
    
    return shingles


def detect_line_repetition(text: str, min_repeats: int = 3) -> float:
    """
    Detect repeated lines (headers/footers) in text.
    
    Args:
        text: Input text
        min_repeats: Minimum number of repetitions to consider as duplicate
        
    Returns:
        Ratio of repeated lines (0.0 = no repetition, 1.0 = all lines repeated)
    """
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    if len(lines) < min_repeats:
        return 0.0
    
    # Count line frequencies
    line_counts = {}
    for line in lines:
        line_counts[line] = line_counts.get(line, 0) + 1
    
    # Count repeated lines
    repeated_count = sum(count - 1 for count in line_counts.values() if count >= min_repeats)
    
    if not lines:
        return 0.0
    
    return min(1.0, repeated_count / len(lines))


def calculate_duplicate_ratio(chunks: List[str]) -> float:
    """
    Calculate duplicate ratio across chunks within a document.
    
    Uses shingle-based similarity to detect near-duplicates.
    Also penalizes repeated headers/footers.
    
    Args:
        chunks: List of chunk texts from the same document
        
    Returns:
        Duplicate ratio score (0-100, where 100 = no duplication, 0 = high duplication)
    """
    if not chunks or len(chunks) < 2:
        return 100.0  # Single chunk or no chunks = no duplication
    
    # Compute shingles for each chunk
    chunk_shingles = [compute_shingles(chunk) for chunk in chunks]
    
    # Calculate pairwise overlap
    total_overlap = 0.0
    comparisons = 0
    
    for i in range(len(chunk_shingles)):
        for j in range(i + 1, len(chunk_shingles)):
            shingles_i = chunk_shingles[i]
            shingles_j = chunk_shingles[j]
            
            if not shingles_i or not shingles_j:
                continue
            
            # Jaccard similarity
            intersection = len(shingles_i & shingles_j)
            union = len(shingles_i | shingles_j)
            
            if union > 0:
                similarity = intersection / union
                total_overlap += similarity
                comparisons += 1
    
    # Average overlap across all pairs
    avg_overlap = total_overlap / comparisons if comparisons > 0 else 0.0
    
    # Also check for line repetition within chunks
    line_repetition_penalty = 0.0
    for chunk in chunks:
        repetition_ratio = detect_line_repetition(chunk)
        line_repetition_penalty += repetition_ratio
    
    avg_line_repetition = line_repetition_penalty / len(chunks) if chunks else 0.0
    
    # Combine shingle overlap and line repetition
    # High overlap or repetition = low score
    duplicate_ratio = avg_overlap * 0.7 + avg_line_repetition * 0.3
    
    # Convert to score: 0% duplication = 100 score, 100% duplication = 0 score
    score = max(0.0, min(100.0, (1.0 - duplicate_ratio) * 100.0))
    
    return round(score, 2)
