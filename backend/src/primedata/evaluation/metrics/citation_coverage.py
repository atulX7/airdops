"""
Citation coverage metric.

Checks if claims have citations and if citations are correct.
"""

import re
from typing import Dict, List, Optional

from loguru import logger

from ..metrics.scoring import MetricScore


class CitationCoverageMetric:
    """Citation coverage metric evaluator."""

    def evaluate(
        self,
        answer: str,
        retrieved_chunks: List[Dict],
        citations: Optional[List[str]] = None,
        threshold: float = 0.90,
    ) -> MetricScore:
        """
        Evaluate citation coverage.
        
        Args:
            answer: Generated answer text
            retrieved_chunks: List of retrieved chunks
            citations: List of citation IDs/indices
            threshold: Threshold for passing
            
        Returns:
            MetricScore object
        """
        if not answer:
            return MetricScore(
                metric_name="citation_coverage",
                score=0.0,
                passed=False,
                details={"error": "Missing answer"},
            )

        # Extract claims from answer
        claims = self._extract_claims(answer)

        # Validate citations (check if they point to valid chunks)
        valid_citations = 0
        invalid_citations = []

        if citations:
            chunk_ids = [chunk.get("id") for chunk in retrieved_chunks]
            chunk_id_strs = [str(cid) for cid in chunk_ids if cid is not None]
            for citation in citations:
                if citation in chunk_ids or str(citation) in chunk_id_strs:
                    valid_citations += 1
                else:
                    invalid_citations.append(citation)

        citation_validity = valid_citations / len(citations) if citations else 0.0

        # Inline markers like [1], [2] in the answer text
        detected_citations = self._extract_citations(answer)

        claims_with_citations = 0
        for claim in claims:
            if self._claim_has_citation(claim, answer, detected_citations):
                claims_with_citations += 1

        claim_coverage = claims_with_citations / len(claims) if claims else 1.0

        # RAG often supplies citation chunk IDs without inline [n] markers. In that case,
        # score from structured citation validity instead of forcing ~30% from 0.7*0 + 0.3*1.
        if citations and not detected_citations:
            final_score = citation_validity
            citation_mode = "implicit_chunk_ids"
        elif detected_citations:
            final_score = (claim_coverage * 0.7 + citation_validity * 0.3)
            citation_mode = "inline_markers"
        else:
            final_score = claim_coverage
            citation_mode = "claims_only"

        passed = final_score >= threshold

        details = {
            "total_claims": len(claims),
            "claims_with_citations": claims_with_citations,
            "claim_coverage": claim_coverage,
            "citation_mode": citation_mode,
            "total_citations": len(citations) if citations else 0,
            "valid_citations": valid_citations,
            "invalid_citations": len(invalid_citations),
            "citation_validity": citation_validity,
        }

        evidence = {
            "invalid_citations": invalid_citations[:5],  # First 5 invalid citations
        }

        return MetricScore(
            metric_name="citation_coverage",
            score=final_score,
            passed=passed,
            details=details,
            evidence=evidence,
        )

    def _extract_claims(self, text: str) -> List[str]:
        """Extract claims from text."""
        # Split by sentence boundaries more carefully
        sentences = re.split(r'[.!?]+\s+', text)
        # Lower threshold to catch more claims (15 chars instead of 20)
        claims = [s.strip() for s in sentences if len(s.strip()) > 15]
        return claims[:15]  # Increase limit to 15

    def _extract_citations(self, text: str) -> List[str]:
        """Extract citations from answer text."""
        # Look for [1], [2], etc. - be more flexible with spacing
        citation_pattern = r'\[(\d+)\]'
        citations = re.findall(citation_pattern, text)
        return citations

    def _claim_has_citation(self, claim: str, full_answer: str, citations: List[str]) -> bool:
        """Check if a claim has a nearby citation."""
        claim_start = full_answer.find(claim)
        if claim_start == -1:
            return False
        
        claim_end = claim_start + len(claim)
        
        # Increase proximity window to 100 chars (was 50) to be more lenient
        for citation in citations:
            citation_pos = full_answer.find(f"[{citation}]")
            if citation_pos != -1:
                # Check if citation is before, within, or shortly after the claim
                if (abs(citation_pos - claim_start) < 100 or 
                    abs(citation_pos - claim_end) < 100 or
                    (citation_pos >= claim_start and citation_pos <= claim_end + 50)):
                    return True
        
        return False




