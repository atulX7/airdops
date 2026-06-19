"""
Retrieval quality metrics.

Includes industry-standard retrieval metrics:
- Mean Reciprocal Rank (MRR)
- Normalized Discounted Cumulative Gain (NDCG@K)
- Hit Rate@K
- Recall@K (already exists, but adding here for completeness)
- Precision@K
"""

from typing import Dict, List, Optional

import numpy as np
from loguru import logger

from ..metrics.scoring import MetricScore


class RetrievalMetric:
    """Retrieval quality metric evaluator."""

    def calculate_mrr(
        self,
        retrieved_chunk_ids: List[str],
        expected_chunk_ids: List[str],
    ) -> float:
        """
        Calculate Mean Reciprocal Rank (MRR).
        
        MRR = 1/rank of first relevant item, or 0 if no relevant item found.
        
        Args:
            retrieved_chunk_ids: List of retrieved chunk IDs in order
            expected_chunk_ids: List of expected/relevant chunk IDs
            
        Returns:
            MRR score (0.0 to 1.0)
        """
        if not retrieved_chunk_ids or not expected_chunk_ids:
            return 0.0
        
        # Find the rank of the first relevant chunk
        for rank, chunk_id in enumerate(retrieved_chunk_ids, start=1):
            if chunk_id in expected_chunk_ids:
                return 1.0 / float(rank)
        
        return 0.0

    def calculate_ndcg_at_k(
        self,
        retrieved_chunk_ids: List[str],
        expected_chunk_ids: List[str],
        k: int = 10,
    ) -> float:
        """
        Calculate Normalized Discounted Cumulative Gain at K (NDCG@K).
        
        NDCG@K measures ranking quality by considering position of relevant items.
        Uses binary relevance (1 if relevant, 0 if not).
        
        Args:
            retrieved_chunk_ids: List of retrieved chunk IDs in order
            expected_chunk_ids: List of expected/relevant chunk IDs
            k: Top K items to consider
            
        Returns:
            NDCG@K score (0.0 to 1.0)
        """
        if not retrieved_chunk_ids or not expected_chunk_ids:
            return 0.0
        
        # Take top K
        top_k = retrieved_chunk_ids[:k]
        
        # Calculate DCG (Discounted Cumulative Gain)
        dcg = 0.0
        for i, chunk_id in enumerate(top_k, start=1):
            if chunk_id in expected_chunk_ids:
                # Binary relevance: 1 if relevant, 0 if not
                relevance = 1.0
                # Discount factor: log2(i+1) for position i
                dcg += relevance / np.log2(i + 1)
        
        # Calculate IDCG (Ideal DCG) - perfect ranking
        num_relevant = min(len(expected_chunk_ids), k)
        idcg = 0.0
        for i in range(1, num_relevant + 1):
            idcg += 1.0 / np.log2(i + 1)
        
        # NDCG = DCG / IDCG
        if idcg == 0.0:
            return 0.0
        
        return dcg / idcg

    def calculate_hit_rate_at_k(
        self,
        retrieved_chunk_ids: List[str],
        expected_chunk_ids: List[str],
        k: int = 10,
    ) -> float:
        """
        Calculate Hit Rate@K.
        
        Hit Rate@K = 1 if at least one relevant item in top K, else 0.
        
        Args:
            retrieved_chunk_ids: List of retrieved chunk IDs in order
            expected_chunk_ids: List of expected/relevant chunk IDs
            k: Top K items to consider
            
        Returns:
            Hit Rate@K (0.0 or 1.0)
        """
        if not retrieved_chunk_ids or not expected_chunk_ids:
            return 0.0
        
        top_k = retrieved_chunk_ids[:k]
        
        # Check if any expected chunk is in top K
        for chunk_id in top_k:
            if chunk_id in expected_chunk_ids:
                return 1.0
        
        return 0.0

    def calculate_recall_at_k(
        self,
        retrieved_chunk_ids: List[str],
        expected_chunk_ids: List[str],
        k: int = 10,
    ) -> float:
        """
        Calculate Recall@K.
        
        Recall@K = (number of relevant items in top K) / (total number of relevant items)
        
        Args:
            retrieved_chunk_ids: List of retrieved chunk IDs in order
            expected_chunk_ids: List of expected/relevant chunk IDs
            k: Top K items to consider
            
        Returns:
            Recall@K score (0.0 to 1.0)
        """
        if not retrieved_chunk_ids or not expected_chunk_ids:
            return 0.0
        
        top_k = retrieved_chunk_ids[:k]
        
        # Count how many expected chunks are in top K
        relevant_retrieved = sum(1 for cid in top_k if cid in expected_chunk_ids)
        
        # Recall = relevant_retrieved / total_relevant
        return float(relevant_retrieved) / float(len(expected_chunk_ids))

    def calculate_precision_at_k(
        self,
        retrieved_chunk_ids: List[str],
        expected_chunk_ids: List[str],
        k: int = 5,
    ) -> float:
        """
        Calculate Precision@K.
        
        Precision@K = (number of relevant items in top K) / K
        
        Args:
            retrieved_chunk_ids: List of retrieved chunk IDs in order
            expected_chunk_ids: List of expected/relevant chunk IDs
            k: Top K items to consider
            
        Returns:
            Precision@K score (0.0 to 1.0)
        """
        if not retrieved_chunk_ids or k == 0:
            return 0.0
        
        top_k = retrieved_chunk_ids[:k]
        
        # Count how many expected chunks are in top K
        relevant_retrieved = sum(1 for cid in top_k if cid in expected_chunk_ids)
        
        # Precision = relevant_retrieved / k
        return float(relevant_retrieved) / float(k)

    def evaluate_retrieval_quality(
        self,
        retrieved_chunks: List[Dict],
        expected_chunk_ids: Optional[List[str]] = None,
        expected_docs: Optional[List[str]] = None,
        k_values: List[int] = [5, 10, 20],
    ) -> Dict[str, float]:
        """
        Evaluate comprehensive retrieval quality metrics.
        
        Args:
            retrieved_chunks: List of retrieved chunks with 'id' field
            expected_chunk_ids: List of expected chunk IDs (for chunk-level evaluation)
            expected_docs: List of expected document IDs (for doc-level evaluation)
            k_values: List of K values to calculate metrics for
            
        Returns:
            Dictionary of metric names to scores
        """
        results = {}
        
        # Extract chunk IDs from retrieved chunks
        retrieved_chunk_ids = [chunk.get("id") for chunk in retrieved_chunks if chunk.get("id")]
        
        # If we have expected chunk IDs, calculate chunk-level metrics
        if expected_chunk_ids:
            for k in k_values:
                results[f"recall_at_{k}"] = self.calculate_recall_at_k(
                    retrieved_chunk_ids, expected_chunk_ids, k=k
                )
                results[f"precision_at_{k}"] = self.calculate_precision_at_k(
                    retrieved_chunk_ids, expected_chunk_ids, k=k
                )
                results[f"hit_rate_at_{k}"] = self.calculate_hit_rate_at_k(
                    retrieved_chunk_ids, expected_chunk_ids, k=k
                )
                results[f"ndcg_at_{k}"] = self.calculate_ndcg_at_k(
                    retrieved_chunk_ids, expected_chunk_ids, k=k
                )
            
            # MRR (uses all retrieved, not just top K)
            results["mrr"] = self.calculate_mrr(retrieved_chunk_ids, expected_chunk_ids)
        
        # If we have expected docs, calculate doc-level metrics
        if expected_docs:
            # Extract doc IDs from retrieved chunks
            retrieved_doc_ids = []
            for chunk in retrieved_chunks:
                doc_id = chunk.get("doc_path") or chunk.get("source_file") or chunk.get("document_id")
                if doc_id:
                    # Extract just the filename/document name
                    if "/" in str(doc_id):
                        doc_id = str(doc_id).split("/")[-1]
                    retrieved_doc_ids.append(doc_id)
            
            # Remove duplicates while preserving order
            seen = set()
            unique_retrieved_docs = []
            for doc_id in retrieved_doc_ids:
                if doc_id not in seen:
                    seen.add(doc_id)
                    unique_retrieved_docs.append(doc_id)
            
            for k in k_values:
                top_k_docs = unique_retrieved_docs[:k]
                relevant_docs = sum(1 for doc_id in top_k_docs if doc_id in expected_docs)
                results[f"doc_recall_at_{k}"] = float(relevant_docs) / float(len(expected_docs)) if expected_docs else 0.0
                results[f"doc_hit_rate_at_{k}"] = 1.0 if any(doc_id in expected_docs for doc_id in top_k_docs) else 0.0
        
        return results

