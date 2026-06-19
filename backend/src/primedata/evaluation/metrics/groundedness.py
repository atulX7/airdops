"""
Groundedness/Faithfulness metric.

Checks if answer claims are supported by retrieved chunks.
"""

import re
from typing import Dict, List, Optional

from loguru import logger

from ..metrics.scoring import MetricScore


class GroundednessMetric:
    """Groundedness metric evaluator."""

    def __init__(self, llm_client=None):
        """
        Initialize groundedness metric.
        
        Args:
            llm_client: LLM client for evaluation (optional, can use simple heuristics if not provided)
        """
        self.llm_client = llm_client

    def evaluate(
        self,
        answer: str,
        retrieved_chunks: List[Dict],
        citations: Optional[List[str]] = None,
        threshold: float = 0.80,
    ) -> MetricScore:
        """
        Evaluate groundedness of an answer.
        
        Args:
            answer: Generated answer text
            retrieved_chunks: List of retrieved chunks with text
            citations: Optional list of citation IDs
            threshold: Threshold for passing
            
        Returns:
            MetricScore object
        """
        if not answer or not retrieved_chunks:
            return MetricScore(
                metric_name="groundedness",
                score=0.0,
                passed=False,
                details={"error": "Missing answer or retrieved chunks"},
            )

        # Extract claims from answer (simple heuristic: sentences)
        claims = self._extract_claims(answer)
        
        if not claims:
            return MetricScore(
                metric_name="groundedness",
                score=1.0,  # Empty answer is technically grounded
                passed=True,
                details={"claims_count": 0},
            )

        # Check if claims are supported by chunks
        supported_claims = []
        unsupported_claims = []
        
        for claim in claims:
            if self._is_claim_supported(claim, retrieved_chunks):
                supported_claims.append(claim)
            else:
                unsupported_claims.append(claim)

        # Calculate score
        support_ratio = len(supported_claims) / len(claims) if claims else 0.0
        score = support_ratio

        # Check citations if provided
        citation_issues = []
        if citations:
            # Check if all key claims have citations
            if len(citations) < len(claims) * 0.5:  # At least 50% of claims should have citations
                citation_issues.append("Low citation coverage")

        passed = score >= threshold and len(citation_issues) == 0

        details = {
            "total_claims": len(claims),
            "supported_claims": len(supported_claims),
            "unsupported_claims": len(unsupported_claims),
            "support_ratio": support_ratio,
            "citation_issues": citation_issues,
        }

        evidence = {
            "supported": supported_claims[:3],  # First 3 supported claims
            "unsupported": unsupported_claims[:3],  # First 3 unsupported claims
        }

        return MetricScore(
            metric_name="groundedness",
            score=score,
            passed=passed,
            details=details,
            evidence=evidence,
        )

    def _extract_claims(self, text: str) -> List[str]:
        """Extract claims from text (simple sentence-based approach)."""
        # Split by sentence endings
        sentences = re.split(r'[.!?]+', text)
        claims = [s.strip() for s in sentences if len(s.strip()) > 20]  # Filter very short sentences
        return claims[:10]  # Limit to first 10 claims

    def _is_claim_supported(self, claim: str, chunks: List[Dict]) -> bool:
        """
        Check if a claim is supported by any chunk.
        
        Uses LLM-as-judge if available, falls back to keyword matching.
        """
        # Try LLM-based evaluation first if available
        if self.llm_client:
            return self._is_claim_supported_llm(claim, chunks)
        
        # Fallback to keyword matching
        return self._is_claim_supported_keyword(claim, chunks)
    
    def _is_claim_supported_llm(self, claim: str, chunks: List[Dict]) -> bool:
        """
        Use LLM-as-judge to check if claim is supported by chunks.
        
        This provides more accurate semantic evaluation than keyword matching.
        """
        if not chunks:
            return False
        
        try:
            # Build context from top chunks (limit to avoid token limits)
            context_chunks = chunks[:3]  # Use top 3 chunks
            context = "\n\n".join([
                f"[Chunk {i+1}]: {chunk.get('text', '')[:500]}"  # Limit chunk size
                for i, chunk in enumerate(context_chunks)
            ])
            
            # Create structured prompt for LLM judge
            prompt = f"""You are evaluating whether a claim is supported by the provided context.

Context:
{context}

Claim: {claim}

Determine if the claim is directly supported by the context. The claim must be:
1. Factually stated in the context (not inferred or assumed)
2. Not contradicted by the context
3. Not requiring external knowledge beyond what's in the context

Answer ONLY with "yes" or "no". Do not provide explanation."""
            
            # Call LLM with low temperature for consistent results
            response = self.llm_client.generate(
                prompt=prompt,
                temperature=0.0,  # Deterministic
                max_tokens=10,  # Just need yes/no
            )
            
            answer = response.get("text", "").strip().lower()
            
            # Check for yes/no response
            if "yes" in answer and "no" not in answer[:10]:  # Avoid "no" in "not supported"
                return True
            return False
            
        except Exception as e:
            from loguru import logger
            logger.warning(f"LLM-based groundedness check failed: {e}, falling back to keyword matching")
            return self._is_claim_supported_keyword(claim, chunks)
    
    def _is_claim_supported_keyword(self, claim: str, chunks: List[Dict]) -> bool:
        """
        Fallback keyword-based claim support check.
        """
        claim_lower = claim.lower()
        claim_keywords = set(claim_lower.split())
        
        for chunk in chunks:
            chunk_text = chunk.get("text", "").lower()
            if not chunk_text:
                continue
            
            # Check if significant keywords from claim appear in chunk
            chunk_words = set(chunk_text.split())
            overlap = claim_keywords.intersection(chunk_words)
            
            # If >30% of claim keywords appear in chunk, consider it supported
            if len(claim_keywords) > 0 and len(overlap) / len(claim_keywords) > 0.3:
                return True
        
        return False




