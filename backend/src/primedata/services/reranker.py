"""
Cross-encoder reranker for Playground search pipeline.

Uses a configurable open-source reranker (default: BAAI/bge-reranker-base)
with fallback to MiniLM when GPU is not available. Supports caching and batching
to reduce latency.
"""

import logging
from typing import Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Module-level cache: single model instance (lazy-loaded)
_reranker_model: Any = None
_reranker_model_name: Optional[str] = None

# Optional in-memory score cache for (query_hash, text_hash) -> score (disabled by default to avoid memory growth)
_score_cache: Optional[dict] = None
_score_cache_max_size: int = 0  # 0 = disabled


def _get_reranker_model(model_name: str):
    """Load cross-encoder model with fallback. Cached per process."""
    global _reranker_model, _reranker_model_name
    if _reranker_model is not None and _reranker_model_name == model_name:
        return _reranker_model
    try:
        from sentence_transformers import CrossEncoder
        logger.info("Loading reranker model: %s", model_name)
        _reranker_model = CrossEncoder(model_name)
        _reranker_model_name = model_name
        return _reranker_model
    except Exception as e:
        logger.warning("Failed to load reranker %s: %s", model_name, e)
        if model_name != "cross-encoder/ms-marco-MiniLM-L-6-v2":
            logger.info("Falling back to cross-encoder/ms-marco-MiniLM-L-6-v2 (lighter, CPU-friendly)")
            _reranker_model = None
            _reranker_model_name = None
            return _get_reranker_model("cross-encoder/ms-marco-MiniLM-L-6-v2")
        raise


def get_reranker(model_name: str) -> Optional[Any]:
    """
    Return the cached reranker model for the given name, with fallback.
    Returns None if sentence_transformers is not available or both models fail.
    """
    try:
        return _get_reranker_model(model_name)
    except ImportError:
        logger.warning("sentence-transformers not available; reranking disabled")
        return None
    except Exception as e:
        logger.warning("Reranker unavailable: %s", e)
        return None


def rerank_batch(
    query: str,
    pairs: List[Tuple[str, str]],
    model_name: str,
    batch_size: int = 32,
) -> List[float]:
    """
    Rerank (query, document) pairs with a cross-encoder in batches.

    Args:
        query: Single query string (repeated for each pair).
        pairs: List of (query, doc_text) or (doc_text,) - we use (query, doc_text).
        model_name: HuggingFace model name (e.g. BAAI/bge-reranker-base).
        batch_size: Max pairs per model batch (reduces latency spikes).

    Returns:
        List of relevance scores, one per pair, in same order as pairs.
    """
    model = get_reranker(model_name)
    if model is None:
        return [0.0] * len(pairs)

    # Build list of (query, doc) for CrossEncoder
    if isinstance(pairs[0], tuple):
        if len(pairs[0]) == 2:
            list_pairs = list(pairs)
        else:
            list_pairs = [(query, p[0]) for p in pairs]
    else:
        list_pairs = [(query, p) for p in pairs]

    try:
        # sentence-transformers CrossEncoder.predict batches internally; we can chunk to limit memory
        all_scores: List[float] = []
        for i in range(0, len(list_pairs), batch_size):
            chunk = list_pairs[i : i + batch_size]
            scores = model.predict(chunk, convert_to_numpy=True)
            if hasattr(scores, "tolist"):
                scores = scores.tolist()
            elif hasattr(scores, "__iter__") and not isinstance(scores, (list, tuple)):
                scores = list(scores)
            if isinstance(scores, (int, float)):
                scores = [float(scores)]
            all_scores.extend(scores)
        return all_scores
    except Exception as e:
        logger.warning("Rerank batch failed: %s", e)
        return [0.0] * len(pairs)


def rerank_candidates(
    query: str,
    candidates: List[dict],
    text_key: str = "text",
    model_name: Optional[str] = None,
    batch_size: int = 32,
) -> List[dict]:
    """
    Attach rerank scores to candidate dicts. Each candidate must have text_key (default "text").
    Modifies candidates in place and returns them sorted by rerank score descending.
    """
    if not candidates:
        return []
    if model_name is None:
        from primedata.core.settings import get_settings
        model_name = get_settings().RERANKER_NAME

    texts = [c.get(text_key) or "" for c in candidates]
    pairs = [(query, t) for t in texts]
    scores = rerank_batch(query, pairs, model_name=model_name, batch_size=batch_size)

    for i, c in enumerate(candidates):
        c["rerank_score"] = float(scores[i]) if i < len(scores) else 0.0
    candidates.sort(key=lambda x: x.get("rerank_score", 0.0), reverse=True)
    return candidates
