"""
Trust scoring service for PrimeData.

Ports AIRD scoring logic with support for primary scorer (scoring_utils) and fallback scorer.
"""

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional

import regex as re
from loguru import logger

# Import AI-Ready metric services
from primedata.services.chunk_coherence import calculate_chunk_coherence
from primedata.services.noise_detection import calculate_noise_ratio
from primedata.services.scoring_utils import estimate_tokens

# Try to import primary scorer
try:
    from primedata.services.scoring_utils import load_weights, score_file_data

    _PRIMARY_SCORER = True
    logger.info("Primary scorer (scoring_utils) available")
except ImportError:
    _PRIMARY_SCORER = False
    logger.warning("Primary scorer not available, using fallback scorer")
    score_file_data = None
    load_weights = None

# Regex patterns for fallback scorer
ASCII_RE = re.compile(r"^[\x00-\x7F]+$")
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PHONE_RE = re.compile(r"(?:\+?\d[\s-]?)?(?:\(\d{3}\)|\d{3})[\s-]?\d{3}[\s-]?\d{4}")
SENT_SPLIT_RE = re.compile(r"(?<!\b[A-Z])[.!?。۔؟]+(?=\s+[A-Z0-9\"'])")


def _ttr(tokens: List[str]) -> float:
    """Type-token ratio."""
    if not tokens:
        return 0.0
    return len(set(tokens)) / max(1, len(tokens))


def _ascii_ratio(s: str, probe: int = 1000) -> float:
    """Calculate ASCII character ratio."""
    ss = s[:probe]
    if not ss:
        return 1.0
    ascii_count = sum(1 for c in ss if ord(c) < 128)
    return ascii_count / len(ss)


def _avg_sentence_len(s: str) -> float:
    """Calculate average sentence length."""
    sents = [x.strip() for x in re.split(SENT_SPLIT_RE, s) if x and x.strip()]
    if not sents:
        return float(len(s.split()))
    return sum(len(x.split()) for x in sents) / max(1, len(sents))


def _clip01(x: float) -> float:
    """Clip value to [0, 1] range."""
    return max(0.0, min(1.0, x))


def _normalize_token_count(n_tokens: float, target: float = 900.0) -> float:
    """Normalize token count to 0-1 range around target."""
    if n_tokens <= 0:
        return 0.0
    ratio = n_tokens / target
    return _clip01(math.exp(-((ratio - 1.0) ** 2) / 0.5))


def _fallback_weights() -> Dict[str, float]:
    """Default weights for fallback scorer (weights sum to 1.0)."""
    return {
        "completeness": 0.10,
        "text_integrity": 0.10,  # Renamed from Accuracy
        "validity": 0.08,
        "consistency": 0.08,
        "uniqueness": 0.08,
        "timeliness": 0.05,
        "parse_success": 0.05,
        "chunk_boundary_quality": 0.05,
        "chunk_coherence": 0.10,
        "chunk_size_health": 0.08,
        "metadata_completeness": 0.10,
        "provenance_coverage": 0.13,
        # Legacy metrics (backward compatibility)
        "Completeness": 0.10,
        "Secure": 0.0,  # Not in trust score by default
        "Quality": 0.0,
        "Token_Count": 0.0,
        "GPT_Confidence": 0.0,
        "Context_Quality": 0.0,
        "Metadata_Presence": 0.0,
        "Audience_Intentionality": 0.0,
        "Diversity": 0.0,
        "Audience_Accessibility": 0.0,
        "KnowledgeBase_Ready": 0.0,
    }


def _fallback_score_record(entry: Dict[str, Any], weights: Dict[str, float]) -> Dict[str, Any]:
    """
    Fallback heuristic scorer that emits the same metric keys as primary scorer.
    All metric values are in [0,1] range; AI_Trust_Score is a weighted sum.
    """
    text = (entry.get("text") or "").strip()
    section = (entry.get("section") or "").strip().lower()
    field_name = (entry.get("field_name") or "").strip().lower()
    document_id = (entry.get("document_id") or "").strip()
    audience = (entry.get("audience") or "unknown").strip().lower()
    # Use shared estimate_tokens helper, fallback to existing token_est if present
    token_est = float(entry.get("token_est") or estimate_tokens(text))

    # Get playbook for playbook-driven metrics
    playbook = entry.get("playbook") or {}
    playbook_id = entry.get("playbook_id")

    # 1) Completeness (playbook-driven if playbook_id present)
    from primedata.services.scoring_utils import _score_completeness_with_playbook
    completeness = _score_completeness_with_playbook(entry, [token_est], playbook if playbook_id else None)

    # 2) Text integrity (renamed from Accuracy): use OCR cleanup metrics when present
    repetition_ratio = entry.get("repetition_ratio")
    ocr_noise_score = entry.get("ocr_noise_score")
    if repetition_ratio is not None and ocr_noise_score is not None:
        integrity_from_cleanup = max(0.0, min(1.0, float(ocr_noise_score) * (1.0 - 0.5 * float(repetition_ratio))))
        text_integrity = 0.6 * integrity_from_cleanup + 0.4 * _ascii_ratio(text)
    else:
        text_integrity = _ascii_ratio(text)

    # 3) Validity (playbook-driven)
    from primedata.services.scoring_utils import _score_validity_with_playbook
    validity = _score_validity_with_playbook(entry, playbook if playbook_id else None)

    # 4) Consistency (playbook-driven)
    from primedata.services.scoring_utils import _score_consistency_with_playbook
    consistency = _score_consistency_with_playbook(entry, playbook if playbook_id else None)

    # 5) Uniqueness (placeholder, computed at aggregate level)
    uniqueness = 1.0

    # 6) Timeliness (no date here) -> neutral 0.5
    timeliness = 0.5

    # 7) Parse success
    parse_success = 1.0 if text and len(text.strip()) >= 50 else 0.0

    # 8) Chunk boundary quality (placeholder, computed at aggregate level)
    chunk_boundary_quality = 1.0

    # 9) Chunk coherence (placeholder, computed via AI-Ready metrics)
    chunk_coherence = 1.0

    # 10) Chunk size health (domain-aware)
    domain_type = entry.get("domain_type") or entry.get("metadata", {}).get("domain_type")
    domain_type_lower = (domain_type or "").lower()
    if domain_type_lower in ["regulatory", "reg", "legal", "finance_banking"]:
        min_ideal, max_ideal = 500, 900
        min_pref, max_pref = 600, 800
    else:
        min_ideal, max_ideal = 600, 1200
        min_pref, max_pref = 800, 1100
    
    if min_pref <= token_est <= max_pref:
        chunk_size_health = 1.0
    elif min_ideal <= token_est < min_pref:
        ratio = (token_est - min_ideal) / (min_pref - min_ideal)
        chunk_size_health = 0.7 + (ratio * 0.3)
    elif max_pref < token_est <= max_ideal:
        ratio = (max_ideal - token_est) / (max_ideal - max_pref)
        chunk_size_health = 0.7 + (ratio * 0.3)
    elif token_est < min_ideal:
        ratio = token_est / min_ideal
        chunk_size_health = max(0.0, ratio * 0.7)
    else:
        excess = token_est - max_ideal
        penalty = min(1.0, excess / max_ideal)
        chunk_size_health = max(0.0, 0.7 * (1.0 - penalty))

    # 11) Metadata completeness
    from primedata.services.scoring_utils import score_metadata_completeness
    metadata_completeness = score_metadata_completeness(entry)

    # 12) Provenance coverage
    from primedata.services.scoring_utils import _score_provenance_coverage
    provenance_coverage = _score_provenance_coverage(entry)

    # Legacy metrics (for backward compatibility)
    pii_hits = bool(EMAIL_RE.search(text) or PHONE_RE.search(text))
    secure = 1.0 if not pii_hits else 0.75
    
    avg_sl = _avg_sentence_len(text) if text else 0.0
    if avg_sl <= 0:
        quality = 0.0
    elif avg_sl < 10:
        quality = avg_sl / 10.0
    elif avg_sl > 30:
        quality = max(0.0, 1.0 - (avg_sl - 30) / 30.0)
    else:
        quality = 1.0
    
    ctx_hit = 1.0 if (section and section in text.lower()) else 0.5
    context_quality = ctx_hit
    meta_presence = 1.0 if (section and field_name and document_id) else 0.5
    aud_intent = 1.0 if audience not in ("", "unknown") else 0.25
    toks = re.findall(r"\w+", text.lower())
    diversity = _ttr(toks)
    if 10 <= avg_sl <= 25:
        aud_access = 1.0
    else:
        d = min(abs(avg_sl - 17.5) / 25.0, 1.0) if avg_sl > 0 else 1.0
        aud_access = max(0.0, 1.0 - d)
    kbr = _clip01(0.4 * meta_presence + 0.4 * quality + 0.2 * context_quality)
    gpt_conf = 0.85

    # Canonical metrics (snake_case, all in [0,1] range for scores)
    metrics = {
        "completeness": completeness,
        "validity": validity,
        "consistency": consistency,
        "uniqueness": uniqueness,
        "timeliness": timeliness,
        "text_integrity": text_integrity,
        "parse_success": parse_success,
        "chunk_boundary_quality": chunk_boundary_quality,
        "chunk_coherence": chunk_coherence,
        "chunk_size_health": round(chunk_size_health, 4),
        "metadata_completeness": metadata_completeness,
        "provenance_coverage": provenance_coverage,
        # Raw token metrics (NOT clamped, NOT scores)
        "token_est": int(token_est),  # Raw token count for this chunk
    }
    
    # Legacy aliases (for backward compatibility, optional)
    # NOTE: Token_Count is NOT included - it's misleading (not an alias of chunk_size_health)
    legacy_aliases = {
        "Completeness": completeness,
        "Secure": secure,
        "Quality": quality,
        "Chunk_Size_Health": round(chunk_size_health, 4),
        "Parse_Success": parse_success,
        "GPT_Confidence": gpt_conf,
        "Context_Quality": context_quality,
        "Metadata_Presence": meta_presence,
        "Audience_Intentionality": aud_intent,  # Weight 0.0, informational only
        "Diversity": diversity,
        "Audience_Accessibility": aud_access,
        "KnowledgeBase_Ready": kbr,
    }
    
    # Store legacy aliases separately (optional, can be omitted if not needed)
    metrics["legacy_aliases"] = legacy_aliases

    # Ensure all SCORE metrics are in [0,1] range (but NOT raw token metrics)
    score_keys = ["completeness", "validity", "consistency", "uniqueness", "timeliness",
                  "text_integrity", "parse_success", "chunk_boundary_quality", "chunk_coherence",
                  "chunk_size_health", "metadata_completeness", "provenance_coverage"]
    for k in score_keys:
        if k in metrics and isinstance(metrics[k], (int, float)):
            metrics[k] = max(0.0, min(1.0, float(metrics[k])))
    
    # Clamp legacy aliases (they are scores)
    if "legacy_aliases" in metrics:
        for k, v in metrics["legacy_aliases"].items():
            if isinstance(v, (int, float)):
                metrics["legacy_aliases"][k] = max(0.0, min(1.0, float(v)))

    # Weighted trust: weights should sum to 1.0
    total_weight = sum(weights.values())
    if abs(total_weight - 1.0) > 0.01:
        logger.warning(f"Weights sum to {total_weight}, expected 1.0. Normalizing weights.")
        weights_normalized = {k: (v / total_weight) for k, v in weights.items()}
        weights = weights_normalized
        total_weight = 1.0
    
    weighted_sum = 0.0
    missing_metrics = []
    for weight_key, weight_value in weights.items():
        if weight_key in metrics:
            # Scores are already in [0,1], weights sum to 1.0
            weighted_sum += metrics[weight_key] * weight_value
        else:
            missing_metrics.append(weight_key)
    
    if missing_metrics:
        logger.warning(f"Missing metrics in scores (defaulting to 0): {missing_metrics}")
    
    # Trust score is in [0,1] range
    metrics["AI_Trust_Score"] = round(weighted_sum, 4)
    return metrics


def get_scoring_weights(config_path: Optional[str] = None) -> Dict[str, float]:
    """Load scoring weights from config or use defaults."""
    if _PRIMARY_SCORER and load_weights:
        try:
            if config_path:
                return load_weights(config_path)
            # Try default path
            from primedata.ingestion_pipeline.aird_stages.config import get_aird_config

            config = get_aird_config()
            if config.scoring_weights_path:
                return load_weights(config.scoring_weights_path)
        except Exception as e:
            logger.warning(f"Failed to load weights from config: {e}, using fallback")

    return _fallback_weights()


def score_record(record: Dict[str, Any], weights: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    """
    Score a single record (chunk).

    Args:
        record: Chunk record with text, metadata, etc.
        weights: Optional scoring weights (uses defaults if not provided)

    Returns:
        Dict with all metrics + AI_Trust_Score (all in [0,1] range)
    """
    if weights is None:
        weights = get_scoring_weights()

    if _PRIMARY_SCORER and score_file_data:
        try:
            return score_file_data(record, weights)
        except Exception as e:
            logger.warning(f"Primary scorer failed: {e}, falling back to heuristic scorer")

    return _fallback_score_record(record, weights)


def aggregate_metrics(metrics: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Aggregate metrics across multiple chunks using explicit aggregation rules.

    Args:
        metrics: List of metric dictionaries (one per chunk)

    Returns:
        Aggregated metrics dictionary (Readiness Fingerprint) with canonical schema:
        - snake_case metrics at top-level
        - scores in [0,1] range
        - raw token metrics NOT clamped
        - legacy_aliases object (optional)
    """
    if not metrics:
        return {}

    # Define aggregation rules
    # Score metrics: use mean (average)
    score_metrics = [
        "completeness", "validity", "consistency", "uniqueness", "timeliness",
        "text_integrity", "parse_success", "chunk_boundary_quality", "chunk_coherence",
        "chunk_size_health", "metadata_completeness", "provenance_coverage"
    ]
    
    # Token metrics: use sum (for totals) or mean (for averages)
    token_metrics = ["token_est"]  # Will be aggregated separately
    
    # Risk metrics: use min (if present)
    risk_metrics = []  # Can be extended in future
    
    # Keys to exclude from aggregation (non-numeric or metadata)
    exclude_keys = {"file", "chunk_id", "document_id", "section", "page", 
                    "metrics_semantics", "_timeliness_reason", "text", "fields", "sections",
                    "legacy_aliases"}  # Legacy aliases aggregated separately

    # Aggregate score metrics (mean)
    score_sums: Dict[str, float] = {}
    score_counts: Dict[str, int] = {}
    
    # Aggregate token metrics (sum for totals)
    token_sums: Dict[str, float] = {}
    token_counts: Dict[str, int] = {}
    
    # Aggregate legacy aliases (mean)
    legacy_sums: Dict[str, float] = {}
    legacy_counts: Dict[str, int] = {}
    
    for m in metrics:
        # Process canonical metrics
        for k, v in m.items():
            if k in exclude_keys:
                continue
            
            if k in score_metrics and isinstance(v, (int, float)):
                score_sums[k] = score_sums.get(k, 0.0) + float(v)
                score_counts[k] = score_counts.get(k, 0) + 1
            elif k in token_metrics and isinstance(v, (int, float)):
                token_sums[k] = token_sums.get(k, 0.0) + float(v)
                token_counts[k] = token_counts.get(k, 0) + 1
        
        # Process legacy aliases
        if "legacy_aliases" in m and isinstance(m["legacy_aliases"], dict):
            for k, v in m["legacy_aliases"].items():
                if isinstance(v, (int, float)):
                    legacy_sums[k] = legacy_sums.get(k, 0.0) + float(v)
                    legacy_counts[k] = legacy_counts.get(k, 0) + 1

    agg: Dict[str, Any] = {}
    
    # Aggregate score metrics (mean, clamped to [0,1])
    for k in score_metrics:
        if k in score_sums and score_counts[k] > 0:
            agg[k] = round(score_sums[k] / score_counts[k], 4)
            agg[k] = max(0.0, min(1.0, agg[k]))
    
    # Compute AI_Trust_Score from aggregated metrics using weights
    # This should be computed at aggregate level, not averaged from chunk scores
    weights = get_scoring_weights()
    weighted_sum = 0.0
    total_weight = sum(weights.values())
    if abs(total_weight - 1.0) > 0.01:
        weights_normalized = {k: (v / total_weight) for k, v in weights.items()}
        weights = weights_normalized
    
    for weight_key, weight_value in weights.items():
        # Check canonical metrics first
        if weight_key in agg:
            weighted_sum += agg[weight_key] * weight_value
        # Check legacy aliases
        elif "legacy_aliases" in agg and weight_key in agg["legacy_aliases"]:
            weighted_sum += agg["legacy_aliases"][weight_key] * weight_value
    
    agg["ai_trust_score"] = round(weighted_sum, 4)
    agg["ai_trust_score"] = max(0.0, min(1.0, agg["ai_trust_score"]))
    
    # Aggregate token metrics
    num_chunks = len(metrics)
    if token_sums:
        total_tokens = int(sum(token_sums.values()))
        agg["total_tokens"] = total_tokens
        agg["num_chunks"] = num_chunks
        if num_chunks > 0:
            agg["avg_tokens_per_chunk"] = round(total_tokens / num_chunks, 2)
            
            # Optional: p95, min, max tokens per chunk
            token_values = []
            for m in metrics:
                if "token_est" in m:
                    token_values.append(int(m["token_est"]))
            
            if token_values:
                token_values.sort()
                agg["min_tokens"] = min(token_values)
                agg["max_tokens"] = max(token_values)
                # p95: value at 95th percentile
                p95_idx = int(0.95 * len(token_values))
                agg["p95_tokens_per_chunk"] = token_values[min(p95_idx, len(token_values) - 1)]
    
    # Aggregate legacy aliases (mean, clamped to [0,1])
    if legacy_sums:
        legacy_aliases = {}
        for k, total in legacy_sums.items():
            c = legacy_counts.get(k, 0)
            if c > 0:
                legacy_aliases[k] = round(total / c, 4)
                legacy_aliases[k] = max(0.0, min(1.0, legacy_aliases[k]))
        if legacy_aliases:
            agg["legacy_aliases"] = legacy_aliases

    return agg


def score_record_with_ai_ready_metrics(
    record: Dict[str, Any],
    weights: Optional[Dict[str, float]] = None,
    playbook: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Score a record with AI-Ready metrics included.
    
    This extends the existing score_record function with:
    - Chunk Coherence Score
    - Noise Ratio (converted to Noise_Free_Score)
    - Chunk Boundary Quality (calculated at aggregate level)
    - Duplicate Rate (calculated separately at aggregate level)
    
    Args:
        record: Chunk record with text, metadata, etc.
        weights: Optional scoring weights (uses defaults if not provided)
        playbook: Optional playbook configuration for noise patterns and coherence settings
        
    Returns:
        Dict with all metrics including AI-Ready metrics (0-100 scale)
    """
    # Get base metrics from existing scorer
    base_metrics = score_record(record, weights)
    
    # Extract chunk text and domain_type
    chunk_text = (record.get("text") or "").strip()
    domain_type = record.get("domain_type") or record.get("metadata", {}).get("domain_type")
    
    # 1. Calculate Chunk Coherence with domain-adaptive thresholds
    coherence_config = playbook.get("coherence", {}) if playbook else {}
    
    # Get domain-specific threshold if available, otherwise use default
    domain_thresholds = coherence_config.get("domain_min_thresholds", {})
    default_threshold = coherence_config.get("min_coherence_threshold", 0.6)
    
    if domain_type and domain_type.lower() in domain_thresholds:
        min_coherence_threshold = domain_thresholds[domain_type.lower()]
    elif domain_type and domain_type.lower() in ["regulatory", "finance_banking"]:
        # Regulatory/finance content may have lower coherence due to cross-references
        min_coherence_threshold = coherence_config.get("regulatory_min_threshold", 0.5)
    else:
        min_coherence_threshold = default_threshold
    
    coherence_result = calculate_chunk_coherence(
        chunk_text=chunk_text,
        method=coherence_config.get("method", "embedding_similarity"),
        sentence_window=coherence_config.get("sentence_window", 3),
        min_coherence_threshold=min_coherence_threshold
    )
    # Normalize coherence score to [0,1] (coherence_result may return 0-100 or 0-1)
    raw_coherence = coherence_result.get("coherence_score", 0.0)
    if raw_coherence > 1.0:
        coherence_score = raw_coherence / 100.0  # Convert from 0-100 to [0,1]
    else:
        coherence_score = raw_coherence
    coherence_score = max(0.0, min(1.0, coherence_score))
    base_metrics["chunk_coherence"] = round(coherence_score, 4)
    base_metrics["Chunk_Coherence"] = round(coherence_score, 4)  # Legacy alias
    
    # 2. Calculate Noise Ratio (inverted to score: lower noise = higher score)
    noise_patterns = playbook.get("noise_patterns") if playbook else None
    noise_result = calculate_noise_ratio(chunk_text, noise_patterns)
    # Convert noise ratio to score in [0,1] (where 0% noise = 1.0 score)
    noise_ratio = noise_result.get("noise_ratio", 0.0)
    if noise_ratio > 1.0:
        noise_ratio = noise_ratio / 100.0  # Convert from percentage to [0,1]
    noise_score = max(0.0, min(1.0, 1.0 - noise_ratio))
    base_metrics["Noise_Free_Score"] = round(noise_score, 4)  # Legacy alias
    
    # 3. Recalculate AI_Trust_Score with new metrics included
    # Chunk Boundary Quality is calculated at aggregate level only
    
    # Recalculate weighted trust score with updated metrics
    if weights is None:
        weights = get_scoring_weights()
    
    total_weight = sum(weights.values())
    if abs(total_weight - 1.0) > 0.01:
        logger.warning(f"Weights sum to {total_weight}, expected 1.0. Normalizing weights.")
        weights_normalized = {k: (v / total_weight) for k, v in weights.items()}
        weights = weights_normalized
        total_weight = 1.0
    
    weighted_sum = 0.0
    missing_metrics = []
    for weight_key, weight_value in weights.items():
        if weight_key in base_metrics:
            # Ensure metric is in [0,1] range
            metric_value = max(0.0, min(1.0, base_metrics[weight_key]))
            weighted_sum += metric_value * weight_value
        else:
            missing_metrics.append(weight_key)
    
    if missing_metrics:
        logger.warning(f"Missing metrics in scores (defaulting to 0): {missing_metrics}")
    
    base_metrics["AI_Trust_Score"] = round(weighted_sum, 4)
    
    return base_metrics


def aggregate_metrics_with_ai_ready(
    metrics: List[Dict[str, Any]],
    preprocessing_stats: Optional[Dict[str, Any]] = None
) -> Dict[str, float]:
    """
    Aggregate metrics including AI-Ready metrics.
    
    Args:
        metrics: List of metric dictionaries (one per chunk)
        preprocessing_stats: Preprocessing statistics including mid_sentence_boundary_rate
        
    Returns:
        Aggregated metrics dictionary with AI-Ready metrics included
    """
    # Get base aggregated metrics
    agg = aggregate_metrics(metrics)
    
    # Add AI-Ready aggregate metrics
    # Note: Chunk_Coherence and Noise_Free_Score are already averaged by aggregate_metrics()
    # so we don't need separate "Avg_" versions
    
    # Chunk Boundary Quality (from preprocessing stats)
    if preprocessing_stats:
        mid_sentence_rate = preprocessing_stats.get("mid_sentence_boundary_rate", 0.0)
        # Convert to score: 0% mid-sentence breaks = 1.0 score (normalized to [0,1])
        boundary_quality = max(0.0, 1.0 - mid_sentence_rate)
        agg["chunk_boundary_quality"] = round(boundary_quality, 4)
        agg["Chunk_Boundary_Quality"] = round(boundary_quality, 4)  # Legacy alias
    
    # Calculate Uniqueness (exact + near-dup) per document and aggregate
    try:
        from primedata.services.dup_detection import calculate_duplicate_ratio
        
        # Group chunks by document_id
        doc_chunks: Dict[str, List[str]] = {}
        doc_chunk_hashes: Dict[str, List[str]] = {}
        for m in metrics:
            doc_id = m.get("document_id") or m.get("file", "unknown")
            chunk_text = m.get("text") or ""
            if doc_id not in doc_chunks:
                doc_chunks[doc_id] = []
                doc_chunk_hashes[doc_id] = []
            doc_chunks[doc_id].append(chunk_text)
            # For exact dup detection, use simple hash
            import hashlib
            chunk_hash = hashlib.md5(chunk_text.encode()).hexdigest()
            doc_chunk_hashes[doc_id].append(chunk_hash)
        
        # Calculate uniqueness per document
        doc_uniqueness_scores = []
        for doc_id, chunks in doc_chunks.items():
            if len(chunks) < 2:
                # Single chunk = perfect uniqueness
                doc_uniqueness_scores.append(1.0)
                continue
            
            # Exact duplicates: 1 - (duplicate_hashes / total_hashes)
            hashes = doc_chunk_hashes[doc_id]
            unique_hashes = len(set(hashes))
            exact_dup_rate = 1.0 - (unique_hashes / len(hashes))
            exact_uniqueness = 1.0 - exact_dup_rate
            
            # Near-duplicates: use shingle-based similarity
            dup_score_100 = calculate_duplicate_ratio(chunks)  # Returns 0-100
            near_dup_rate = 1.0 - (dup_score_100 / 100.0)  # Convert to [0,1] rate
            near_uniqueness = 1.0 - near_dup_rate
            
            # Combine: 0.7*exact + 0.3*near (exact duplicates are more important)
            uniqueness = 0.7 * exact_uniqueness + 0.3 * near_uniqueness
            # Ensure uniqueness is in [0,1]
            uniqueness = max(0.0, min(1.0, uniqueness))
            doc_uniqueness_scores.append(uniqueness)
        
        # Average across documents
        if doc_uniqueness_scores:
            agg["uniqueness"] = round(sum(doc_uniqueness_scores) / len(doc_uniqueness_scores), 4)
            # Ensure uniqueness is in [0,1]
            agg["uniqueness"] = max(0.0, min(1.0, agg["uniqueness"]))
        else:
            agg["uniqueness"] = 1.0
        
        # duplicate_ratio = 1 - uniqueness (in [0,1], NOT converted to percent)
        agg["duplicate_ratio"] = round(1.0 - agg["uniqueness"], 4)
        # Ensure duplicate_ratio is in [0,1]
        agg["duplicate_ratio"] = max(0.0, min(1.0, agg["duplicate_ratio"]))
        
        # Legacy alias (for backward compatibility, in legacy_aliases)
        if "legacy_aliases" not in agg:
            agg["legacy_aliases"] = {}
        # Legacy expects percentage (0-100), but we keep it in [0,1] in canonical
        dup_ratio_percent = agg["duplicate_ratio"] * 100.0
        agg["legacy_aliases"]["Duplicate_Ratio"] = round(dup_ratio_percent, 2)
    except ImportError:
        logger.warning("dup_detection module not available, skipping uniqueness calculation")
        agg["uniqueness"] = 0.5  # Neutral score if module unavailable
        agg["duplicate_ratio"] = 0.5  # duplicate_ratio = 1 - uniqueness
        # Ensure both are in [0,1]
        agg["uniqueness"] = max(0.0, min(1.0, agg["uniqueness"]))
        agg["duplicate_ratio"] = max(0.0, min(1.0, agg["duplicate_ratio"]))
        
        # Legacy alias
        if "legacy_aliases" not in agg:
            agg["legacy_aliases"] = {}
        agg["legacy_aliases"]["Duplicate_Ratio"] = 50.0  # Legacy expects percentage
    
    # Ensure all aggregated SCORE metrics are in [0,1] (but NOT raw token metrics)
    score_keys = ["completeness", "validity", "consistency", "uniqueness", "timeliness",
                  "text_integrity", "parse_success", "chunk_boundary_quality", "chunk_coherence",
                  "chunk_size_health", "metadata_completeness", "provenance_coverage", "duplicate_ratio"]
    for k in score_keys:
        if k in agg and isinstance(agg[k], (int, float)):
            agg[k] = max(0.0, min(1.0, float(agg[k])))
    
    # Clamp legacy aliases (they are scores)
    if "legacy_aliases" in agg:
        for k, v in agg["legacy_aliases"].items():
            if isinstance(v, (int, float)):
                agg["legacy_aliases"][k] = max(0.0, min(1.0, float(v)))
    
    # Compute AI_Trust_Score from aggregated metrics using weights
    weights = get_scoring_weights()
    weighted_sum = 0.0
    total_weight = sum(weights.values())
    if abs(total_weight - 1.0) > 0.01:
        weights_normalized = {k: (v / total_weight) for k, v in weights.items()}
        weights = weights_normalized
    
    for weight_key, weight_value in weights.items():
        # Check canonical metrics first
        if weight_key in agg:
            weighted_sum += agg[weight_key] * weight_value
        # Check legacy aliases
        elif "legacy_aliases" in agg and weight_key in agg["legacy_aliases"]:
            weighted_sum += agg["legacy_aliases"][weight_key] * weight_value
    
    agg["ai_trust_score"] = round(weighted_sum, 4)
    agg["ai_trust_score"] = max(0.0, min(1.0, agg["ai_trust_score"]))
    
    return agg
