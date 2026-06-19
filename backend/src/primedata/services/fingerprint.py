"""
Fingerprint service for PrimeData.

Generates readiness fingerprints by aggregating chunk-level metrics.
"""

from typing import Any, Dict, List, Optional

from loguru import logger
from primedata.services.trust_scoring import aggregate_metrics, aggregate_metrics_with_ai_ready


def get_metrics_semantics() -> Dict[str, Dict[str, str]]:
    """
    Get semantics mapping for all metrics.
    
    Returns:
        Dictionary mapping metric keys to their semantic descriptions
    """
    return {
        "Quality": {
            "meaning": "Text quality based on readability metrics and heuristics",
            "computation": "Uses Flesch reading ease (if available) or sentence length heuristics. Domain-aware for regulatory content."
        },
        "Context_Quality": {
            "meaning": "Context quality based on text structure and information richness",
            "computation": "Evaluates structure (paragraphs, lists), information density (numbers, dates, references), contextual keywords, and entity mentions."
        },
        "text_integrity": {
            "meaning": "Text integrity (OCR/text cleanliness)",
            "computation": "Uses spell checker to detect spelling errors and OCR artifacts. Measures text cleanliness and character encoding quality, NOT factual accuracy. Returns score in [0,1] range."
        },
        "completeness": {
            "meaning": "Completeness (playbook-driven or generic extraction completeness)",
            "computation": "If playbook_id present: checks required sections and fields per playbook rules (0.6*sections + 0.4*fields). If no playbook: checks extraction completeness (token count > 1000). Returns score in [0,1] range."
        },
        "validity": {
            "meaning": "Validity/Conformance (playbook rule pass rate)",
            "computation": "If playbook_id present: evaluates validity_rules from playbook (passed_checks / total_checks). If no playbook: returns 1.0 (no validity requirements). Returns score in [0,1] range."
        },
        "consistency": {
            "meaning": "Consistency (playbook rule pass rate with severity weighting)",
            "computation": "If playbook_id present: evaluates consistency_rules from playbook with severity weighting (critical=1.0, high=0.8, medium=0.5, low=0.2). If no playbook: returns 1.0. Returns score in [0,1] range."
        },
        "uniqueness": {
            "meaning": "Uniqueness/Dedup (exact dup + near-dup rate)",
            "computation": "Combines exact duplicate detection (hash-based) and near-duplicate detection (shingles/Jaccard). Score = 0.7*exact_uniqueness + 0.3*near_uniqueness. Returns score in [0,1] range."
        },
        "parse_success": {
            "meaning": "Parse/Extract Success (pages/chunks extracted vs attempted)",
            "computation": "1.0 if chunk text exists and > min_chars (default 50), else 0.0. Returns score in [0,1] range."
        },
        "chunk_boundary_quality": {
            "meaning": "Chunk Boundary Quality (mid-sentence split rate)",
            "computation": "Measures percentage of mid-sentence breaks. Score = 1.0 - boundary_split_rate. 0% mid-sentence breaks = 1.0 score. Returns score in [0,1] range."
        },
        "chunk_coherence": {
            "meaning": "Chunk Coherence (heuristic coherence proxy)",
            "computation": "Measures semantic coherence within chunk using embedding similarity or sentence window analysis. Domain-adaptive thresholds. Returns score in [0,1] range."
        },
        "chunk_size_health": {
            "meaning": "Chunk Size Health (token length distribution vs target window)",
            "computation": "Scores chunk token length vs domain-aware target ranges. Regulatory/legal: 500-900 ideal (600-800 preferred). General: 600-1200 ideal (800-1100 preferred). Returns score in [0,1] range."
        },
        "metadata_completeness": {
            "meaning": "Metadata Completeness (required metadata fields populated)",
            "computation": "Checks presence of required metadata fields (default: source, section, audience, timestamp). Score = present_required_meta / total_required_meta. Returns score in [0,1] range."
        },
        "provenance_coverage": {
            "meaning": "Provenance Coverage (weighted checklist)",
            "computation": "Weighted checklist: source checksum (0.25), pipeline run id (0.20), model_id (0.15), model_version (0.15), timestamp (0.15), extraction_timestamp (0.10). Returns score in [0,1] range."
        },
        "Completeness": {
            "meaning": "Extraction completeness (token count threshold) - legacy alias",
            "computation": "Legacy alias for completeness. Checks if enough content was extracted (token count > 1000). Returns score in [0,1] range."
        },
        "Metadata_Presence": {
            "meaning": "Metadata presence and quality",
            "computation": "Checks presence of required metadata fields (source, section, audience, timestamp) plus quality bonuses for meaningful values."
        },
        "Chunk_Coherence": {
            "meaning": "Chunk coherence score",
            "computation": "Measures semantic coherence within chunk using embedding similarity or sentence window analysis. Domain-adaptive thresholds."
        },
        "Noise_Free_Score": {
            "meaning": "Noise-free score (inverted noise ratio)",
            "computation": "Detects boilerplate, navigation, and legal footer patterns. Lower noise = higher score (0% noise = 100 score)."
        },
        "Chunk_Boundary_Quality": {
            "meaning": "Chunk boundary quality - legacy alias",
            "computation": "Legacy alias for chunk_boundary_quality. Measures percentage of mid-sentence breaks. Returns score in [0,1] range."
        },
        "timeliness": {
            "meaning": "Timeliness/Freshness (staleness vs SLA/threshold)",
            "computation": "Score = clamp(1 - age_hours/sla_hours) where age_hours is time since timestamp. If playbook provides freshness_sla_hours, uses that; else defaults to 365 days. Returns score in [0,1] range."
        },
        "Timeliness": {
            "meaning": "Content timeliness - legacy alias",
            "computation": "Legacy alias for timeliness. Returns score in [0,1] range."
        },
        "Token_Count": {
            "meaning": "Token count score (legacy, kept for backward compatibility)",
            "computation": "Legacy alias of Chunk_Size_Health. Returns score in [0,1] range."
        },
        "Chunk_Size_Health": {
            "meaning": "Chunk token length distribution vs target range - legacy alias",
            "computation": "Legacy alias for chunk_size_health. Returns score in [0,1] range."
        },
        "Parse_Success": {
            "meaning": "Parse success indicator - legacy alias",
            "computation": "Legacy alias for parse_success. Returns score in [0,1] range."
        },
        "Duplicate_Ratio": {
            "meaning": "Near-duplicate/boilerplate indicator - legacy alias",
            "computation": "Legacy alias for uniqueness (inverted). Uses lightweight shingles (5-gram hashes) to detect near-duplicates. Returns score in [0,1] range."
        },
        "Diversity": {
            "meaning": "Vocabulary diversity",
            "computation": "Type-Token Ratio (TTR): unique words / total words. Higher TTR = more diverse vocabulary."
        },
        "KnowledgeBase_Ready": {
            "meaning": "Knowledge base readiness",
            "computation": "100 if text has > 50 words and contains newlines (structured), else 50."
        },
        "Audience_Accessibility": {
            "meaning": "Audience accessibility based on detected audience and readability",
            "computation": "Evaluates audience detection and text readability (sentence length). Well-defined audiences and accessible sentence lengths score higher."
        },
        "Audience_Intentionality": {
            "meaning": "Audience intentionality based on audience signals in text",
            "computation": "Detects domain-specific and generic audience signals (healthcare, business, technical, etc.). Domain-aware scoring."
        },
        "GPT_Confidence": {
            "meaning": "GPT confidence placeholder",
            "computation": "Placeholder metric (currently returns constant 85.0). Zero-weighted in trust score calculation."
        },
        # New canonical metrics
        "duplicate_ratio": {
            "meaning": "Duplicate ratio (1 - uniqueness)",
            "computation": "Duplicate ratio = 1 - uniqueness. Both are in [0,1] range. Never converted to percent, never clamped after percent conversion."
        },
        "total_tokens": {
            "meaning": "Total tokens across all chunks",
            "computation": "Sum of token_est across all chunks. Raw metric (NOT clamped, NOT a score)."
        },
        "avg_tokens_per_chunk": {
            "meaning": "Average tokens per chunk",
            "computation": "Derived from total_tokens / num_chunks. Raw metric (NOT clamped, NOT a score)."
        },
        "num_chunks": {
            "meaning": "Number of chunks",
            "computation": "Count of chunks processed. Raw metric (NOT clamped, NOT a score)."
        },
        "min_tokens": {
            "meaning": "Minimum tokens per chunk",
            "computation": "Minimum token_est value across all chunks. Raw metric (NOT clamped, NOT a score)."
        },
        "max_tokens": {
            "meaning": "Maximum tokens per chunk",
            "computation": "Maximum token_est value across all chunks. Raw metric (NOT clamped, NOT a score)."
        },
        "p95_tokens_per_chunk": {
            "meaning": "95th percentile tokens per chunk",
            "computation": "95th percentile of token_est values across all chunks. Raw metric (NOT clamped, NOT a score)."
        },
        "token_est": {
            "meaning": "Estimated token count for a chunk",
            "computation": "Computed using shared estimate_tokens(text) helper with tiktoken fallback (word_count * 1.3). Raw metric (NOT clamped, NOT a score)."
        }
    }


def generate_fingerprint(
    metrics: List[Dict[str, Any]], 
    preprocessing_stats: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Generate a readiness fingerprint from chunk-level metrics.

    Args:
        metrics: List of metric dictionaries (one per chunk)
        preprocessing_stats: Optional preprocessing statistics for Chunk Boundary Quality

    Returns:
        Readiness fingerprint dictionary with aggregated metrics and metrics_semantics
    """
    if not metrics:
        logger.warning("No metrics provided for fingerprint generation")
        return {}

    # Use AI-Ready aggregation if preprocessing stats are available
    if preprocessing_stats:
        fingerprint = aggregate_metrics_with_ai_ready(metrics, preprocessing_stats)
    else:
        fingerprint = aggregate_metrics(metrics)

    # Stage-level assertions (fail fast) after fingerprint
    # Assert: ai_trust_score exists, canonical key schema enforced
    if "ai_trust_score" not in fingerprint:
        raise AssertionError("Fingerprint assertion failed: ai_trust_score missing")
    
    # Assert canonical keys are snake_case only (no Title_Case at top-level except legacy_aliases)
    canonical_score_keys = ["completeness", "validity", "consistency", "uniqueness", "timeliness",
                           "text_integrity", "parse_success", "chunk_boundary_quality", "chunk_coherence",
                           "chunk_size_health", "metadata_completeness", "provenance_coverage", "duplicate_ratio"]
    title_case_keys_at_top = [k for k in fingerprint.keys() 
                              if k[0].isupper() and k not in ["legacy_aliases", "metrics_semantics", "ai_trust_score"]]
    if title_case_keys_at_top:
        logger.warning(f"Fingerprint assertion warning: Title_Case keys at top-level (should be in legacy_aliases): {title_case_keys_at_top}")
    
    # Assert legacy aliases are in legacy_aliases dict, not at top-level
    if "legacy_aliases" in fingerprint:
        legacy_keys = list(fingerprint["legacy_aliases"].keys())
        title_case_in_legacy = [k for k in legacy_keys if k[0].isupper()]
        if not title_case_in_legacy:
            logger.warning("Fingerprint assertion warning: legacy_aliases dict exists but contains no Title_Case keys")
    
    # Assert Audience_Intentionality weight is 0.0 (informational only)
    # This is checked in scoring_weights.json, but verify it's not affecting ai_trust_score
    if "legacy_aliases" in fingerprint and "Audience_Intentionality" in fingerprint["legacy_aliases"]:
        aud_intent_value = fingerprint["legacy_aliases"]["Audience_Intentionality"]
        logger.debug(f"Audience_Intentionality value: {aud_intent_value} (should be informational only, weight=0.0)")
    
    logger.info(f"✅ Fingerprint assertions passed: ai_trust_score={fingerprint.get('ai_trust_score', 'N/A')}, canonical schema enforced")
    
    # Add metrics_semantics mapping
    semantics = get_metrics_semantics()
    
    # Filter semantics to only include metrics present in fingerprint
    filtered_semantics = {
        key: value for key, value in semantics.items()
        if key in fingerprint
    }
    
    # Add semantics to fingerprint
    fingerprint["metrics_semantics"] = filtered_semantics

    logger.info(f"Generated fingerprint with {len(fingerprint)} metrics")
    return fingerprint


def aggregate_metrics_by_file(
    metrics: List[Dict[str, Any]],
    file_tag: str,
) -> Optional[Dict[str, float]]:
    """
    Aggregate metrics for a specific file tag.

    Args:
        metrics: List of all metrics
        file_tag: File identifier (e.g., "MyDoc.jsonl")

    Returns:
        Aggregated metrics for the file, or None if no metrics found
    """
    from primedata.services.trust_scoring import aggregate_metrics
    
    file_metrics = [m for m in metrics if m.get("file") == file_tag]
    if not file_metrics:
        return None

    return aggregate_metrics(file_metrics)
