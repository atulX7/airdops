"""
Relevance metrics.

Includes:
- Context relevance: How relevant are retrieved chunks to the query
- Answer relevance: How well does the answer address the query
"""

from typing import Dict, List, Optional

import numpy as np
from loguru import logger

from ..metrics.scoring import MetricScore


class RelevanceMetric:
    """Relevance metric evaluator."""

    def __init__(self, embedding_generator=None, llm_client=None):
        """
        Initialize relevance metric.
        
        Args:
            embedding_generator: Embedding generator for similarity calculation
            llm_client: LLM client for answer relevance (optional)
        """
        self.embedding_generator = embedding_generator
        self.llm_client = llm_client

    def evaluate_context_relevance(
        self,
        query: str,
        retrieved_chunks: List[Dict],
        threshold: float = 0.75,
    ) -> MetricScore:
        """
        Evaluate context relevance (how relevant are retrieved chunks to query).
        
        Args:
            query: Query text
            retrieved_chunks: List of retrieved chunks with text and optionally embeddings
            threshold: Threshold for passing
            
        Returns:
            MetricScore object
        """
        if not query or not retrieved_chunks:
            return MetricScore(
                metric_name="context_relevance",
                score=0.0,
                passed=False,
                details={"error": "Missing query or chunks"},
            )

        if self.embedding_generator:
            # Use embedding similarity
            try:
                query_embedding = self.embedding_generator.embed_batch([query])[0]
                similarities = []
                
                for chunk in retrieved_chunks:
                    chunk_text = chunk.get("text", "")
                    if not chunk_text:
                        continue
                    
                    # Get or generate chunk embedding
                    if "embedding" in chunk:
                        chunk_embedding = chunk["embedding"]
                    else:
                        chunk_embeddings = self.embedding_generator.embed_batch([chunk_text])
                        chunk_embedding = chunk_embeddings[0] if chunk_embeddings else None
                    
                    if chunk_embedding is not None:
                        # Cosine similarity
                        similarity = np.dot(query_embedding, chunk_embedding) / (
                            np.linalg.norm(query_embedding) * np.linalg.norm(chunk_embedding)
                        )
                        similarities.append(similarity)
                
                if similarities:
                    avg_similarity = np.mean(similarities)
                    score = max(0.0, min(1.0, avg_similarity))  # Clamp to [0, 1]
                else:
                    score = 0.0
            except Exception as e:
                logger.warning(f"Error calculating embedding similarity: {e}")
                score = 0.5  # Fallback score
        else:
            # Simple keyword-based fallback
            query_words = set(query.lower().split())
            relevant_chunks = 0
            
            for chunk in retrieved_chunks:
                chunk_text = chunk.get("text", "").lower()
                chunk_words = set(chunk_text.split())
                overlap = query_words.intersection(chunk_words)
                if len(overlap) / len(query_words) > 0.3:  # >30% keyword overlap
                    relevant_chunks += 1
            
            score = relevant_chunks / len(retrieved_chunks) if retrieved_chunks else 0.0

        passed = score >= threshold

        details = {
            "chunks_evaluated": len(retrieved_chunks),
            "avg_similarity": score,
        }

        return MetricScore(
            metric_name="context_relevance",
            score=score,
            passed=passed,
            details=details,
        )

    def evaluate_answer_relevance(
        self,
        query: str,
        answer: str,
        threshold: float = 0.80,
    ) -> MetricScore:
        """
        Evaluate answer relevance (how well does answer address the query).
        
        Args:
            query: Query text
            answer: Generated answer
            threshold: Threshold for passing
            
        Returns:
            MetricScore object
        """
        if not query or not answer:
            return MetricScore(
                metric_name="answer_relevance",
                score=0.0,
                passed=False,
                details={"error": "Missing query or answer"},
            )

        # Use LLM-based evaluation if available, otherwise fallback to keyword matching
        if self.llm_client:
            score = self._llm_answer_relevance(query, answer)
        else:
            score = self._simple_answer_relevance(query, answer)

        passed = score >= threshold

        details = {
            "query_length": len(query),
            "answer_length": len(answer),
            "evaluation_method": "llm" if self.llm_client else "keyword",
        }

        return MetricScore(
            metric_name="answer_relevance",
            score=score,
            passed=passed,
            details=details,
        )

    def _llm_answer_relevance(self, query: str, answer: str) -> float:
        """
        Use LLM-as-judge to evaluate answer relevance.
        
        Returns a score from 0.0 to 1.0 indicating how well the answer addresses the query.
        """
        try:
            prompt = f"""You are evaluating how well an answer addresses a question.

Question: {query}

Answer: {answer}

Rate how well the answer addresses the question on a scale of 0.0 to 1.0, where:
- 1.0 = The answer fully and directly addresses the question
- 0.7-0.9 = The answer mostly addresses the question but may be incomplete or slightly off-topic
- 0.4-0.6 = The answer partially addresses the question but misses key aspects
- 0.0-0.3 = The answer does not address the question or is irrelevant

Respond with ONLY a number between 0.0 and 1.0 (e.g., "0.85"). Do not provide explanation."""
            
            response = self.llm_client.generate(
                prompt=prompt,
                temperature=0.0,  # Deterministic
                max_tokens=10,  # Just need a number
            )
            
            answer_text = response.get("text", "").strip()
            
            # Extract numeric score
            import re
            match = re.search(r'0?\.?\d+', answer_text)
            if match:
                score = float(match.group())
                # Clamp to [0, 1]
                return max(0.0, min(1.0, score))
            
            # If parsing fails, return moderate score
            logger.warning(f"Failed to parse LLM relevance score from: {answer_text}")
            return 0.5
            
        except Exception as e:
            logger.warning(f"LLM-based answer relevance check failed: {e}, falling back to keyword matching")
            return self._simple_answer_relevance(query, answer)

    def _simple_answer_relevance(self, query: str, answer: str) -> float:
        """Simple keyword-based answer relevance."""
        query_words = set(query.lower().split())
        answer_words = set(answer.lower().split())
        
        # Check if answer contains query keywords
        overlap = query_words.intersection(answer_words)
        keyword_coverage = len(overlap) / len(query_words) if query_words else 0.0
        
        # Check if answer is not too short (should be substantial)
        length_score = min(1.0, len(answer) / 100.0)  # Normalize by 100 chars
        
        # Combined score
        score = (keyword_coverage * 0.7 + length_score * 0.3)
        return max(0.0, min(1.0, score))




