"""
Evaluator orchestrates metric computation for each query.
"""

from typing import Dict, List, Optional
from uuid import UUID

from loguru import logger

from primedata.evaluation.metrics.metric_registry import MetricRegistry
from primedata.indexing.embeddings import EmbeddingGenerator


class Evaluator:
    """Orchestrates metric computation for evaluation queries."""

    def __init__(
        self,
        embedding_generator: Optional[EmbeddingGenerator] = None,
        llm_client=None,
    ):
        """
        Initialize evaluator.
        
        Args:
            embedding_generator: Embedding generator for similarity calculations
            llm_client: LLM client for LLM-based metrics
        """
        self.metric_registry = MetricRegistry(
            embedding_generator=embedding_generator,
            llm_client=llm_client,
        )

    def evaluate_query(
        self,
        query: str,
        answer: str,
        retrieved_chunks: List[Dict],
        citations: Optional[List[str]] = None,
        acl_denied: bool = False,
        expected_refusal: bool = False,
        has_evidence: bool = True,
        expected_chunk_ids: Optional[List[str]] = None,
        expected_docs: Optional[List[str]] = None,
        expected_answer: Optional[str] = None,
        thresholds: Optional[Dict[str, float]] = None,
    ) -> Dict[str, any]:
        """
        Evaluate a single query.
        
        Args:
            query: Query text
            answer: Generated answer
            retrieved_chunks: List of retrieved chunks
            citations: Optional citations
            acl_denied: Whether ACL denied
            expected_refusal: Whether refusal was expected
            has_evidence: Whether evidence was available
            thresholds: Optional custom thresholds
            
        Returns:
            Dictionary of metric results
        """
        try:
            results = self.metric_registry.evaluate_all(
                query=query,
                answer=answer,
                retrieved_chunks=retrieved_chunks,
                citations=citations,
                acl_denied=acl_denied,
                expected_refusal=expected_refusal,
                has_evidence=has_evidence,
                expected_chunk_ids=expected_chunk_ids,
                expected_docs=expected_docs,
                expected_answer=expected_answer,
                thresholds=thresholds,
            )
            
            # Convert MetricScore objects to dicts
            return {name: score.to_dict() for name, score in results.items()}
        except Exception as e:
            logger.error(f"Error evaluating query: {e}", exc_info=True)
            return {
                "error": str(e),
                "groundedness": {"score": 0.0, "passed": False},
                "context_relevance": {"score": 0.0, "passed": False},
                "answer_relevance": {"score": 0.0, "passed": False},
                "citation_coverage": {"score": 0.0, "passed": False},
                "refusal_correctness": {"score": 0.0, "passed": False},
            }




