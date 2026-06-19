"""
Metric registry for RAG quality metrics.
"""

from typing import Dict, List, Optional

from .answer_correctness import AnswerCorrectnessMetric
from .citation_coverage import CitationCoverageMetric
from .groundedness import GroundednessMetric
from .refusal_correctness import RefusalCorrectnessMetric
from .relevance import RelevanceMetric
from .retrieval import RetrievalMetric
from .scoring import MetricScore


class MetricRegistry:
    """Registry for all RAG quality metrics."""

    def __init__(
        self,
        embedding_generator=None,
        llm_client=None,
    ):
        """
        Initialize metric registry.
        
        Args:
            embedding_generator: Embedding generator for similarity calculations
            llm_client: LLM client for LLM-based metrics
        """
        self.embedding_generator = embedding_generator
        self.llm_client = llm_client
        
        # Initialize metric evaluators
        self.groundedness = GroundednessMetric(llm_client=llm_client)
        self.relevance = RelevanceMetric(
            embedding_generator=embedding_generator,
            llm_client=llm_client,
        )
        self.citation_coverage = CitationCoverageMetric()
        self.refusal_correctness = RefusalCorrectnessMetric()
        self.retrieval = RetrievalMetric()
        self.answer_correctness = AnswerCorrectnessMetric(embedding_generator=embedding_generator)

    def evaluate_all(
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
    ) -> Dict[str, MetricScore]:
        """
        Evaluate all metrics.
        
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
            Dictionary of metric name to MetricScore
        """
        if thresholds is None:
            thresholds = {
                "groundedness": 0.80,
                "context_relevance": 0.75,
                "answer_relevance": 0.80,
                "citation_coverage": 0.90,
                "refusal_correctness": 0.95,
                "answer_correctness": 0.75,
            }

        results = {}
        
        # Groundedness
        results["groundedness"] = self.groundedness.evaluate(
            answer=answer,
            retrieved_chunks=retrieved_chunks,
            citations=citations,
            threshold=thresholds.get("groundedness", 0.80),
        )
        
        # Context relevance
        results["context_relevance"] = self.relevance.evaluate_context_relevance(
            query=query,
            retrieved_chunks=retrieved_chunks,
            threshold=thresholds.get("context_relevance", 0.75),
        )
        
        # Answer relevance
        results["answer_relevance"] = self.relevance.evaluate_answer_relevance(
            query=query,
            answer=answer,
            threshold=thresholds.get("answer_relevance", 0.80),
        )

        # Golden answer similarity (only when dataset provides expected_answer)
        if expected_answer and str(expected_answer).strip():
            results["answer_correctness"] = self.answer_correctness.evaluate(
                expected_answer=str(expected_answer).strip(),
                answer=answer,
                threshold=thresholds.get("answer_correctness", 0.75),
            )
        
        # Citation coverage
        results["citation_coverage"] = self.citation_coverage.evaluate(
            answer=answer,
            retrieved_chunks=retrieved_chunks,
            citations=citations,
            threshold=thresholds.get("citation_coverage", 0.90),
        )
        
        # Refusal correctness
        results["refusal_correctness"] = self.refusal_correctness.evaluate(
            answer=answer,
            acl_denied=acl_denied,
            expected_refusal=expected_refusal,
            has_evidence=has_evidence,
            threshold=thresholds.get("refusal_correctness", 0.95),
        )
        
        # Retrieval quality metrics (if expected chunks/docs provided)
        if expected_chunk_ids or expected_docs:
            retrieval_scores = self.retrieval.evaluate_retrieval_quality(
                retrieved_chunks=retrieved_chunks,
                expected_chunk_ids=expected_chunk_ids,
                expected_docs=expected_docs,
                k_values=[5, 10, 20],
            )
            
            # Convert retrieval scores to MetricScore objects
            for metric_name, score in retrieval_scores.items():
                # Use appropriate threshold based on metric type
                if "recall" in metric_name or "hit_rate" in metric_name:
                    threshold_val = thresholds.get("retrieval_recall", 0.80)
                elif "precision" in metric_name:
                    threshold_val = thresholds.get("retrieval_precision", 0.70)
                elif "ndcg" in metric_name:
                    threshold_val = thresholds.get("retrieval_ndcg", 0.75)
                elif "mrr" in metric_name:
                    threshold_val = thresholds.get("retrieval_mrr", 0.80)
                else:
                    threshold_val = 0.75
                
                results[f"retrieval_{metric_name}"] = MetricScore(
                    metric_name=f"retrieval_{metric_name}",
                    score=score,
                    passed=score >= threshold_val,
                    details={"k": metric_name.split("_")[-1] if "_at_" in metric_name else None},
                )
        
        return results

