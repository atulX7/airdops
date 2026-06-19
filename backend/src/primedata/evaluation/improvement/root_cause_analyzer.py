"""
Root cause analyzer for RAG quality failures.

Simple rule-based root cause analysis (not ML-based).
"""

from typing import Dict, Optional

from loguru import logger


class RootCauseAnalyzer:
    """Analyzes root causes of RAG quality failures."""

    @staticmethod
    def analyze_failure(
        metric_name: str,
        score: float,
        threshold: float,
        evaluation_details: Optional[Dict] = None,
    ) -> str:
        """
        Analyze root cause of a metric failure.
        
        Args:
            metric_name: Name of the failed metric
            score: Actual score
            threshold: Threshold that was not met
            evaluation_details: Optional detailed evaluation results
            
        Returns:
            Root cause identifier
        """
        evaluation_details = evaluation_details or {}
        
        if metric_name == "groundedness":
            # Low groundedness could be due to:
            # - Poor chunk boundaries (chunks cut off context)
            # - Low chunk overlap (missing context between chunks)
            # - Poor retrieval (wrong chunks retrieved)
            if evaluation_details.get("unsupported_claims", 0) > evaluation_details.get("supported_claims", 0):
                return "chunk_boundaries"  # Likely chunking issue
            elif evaluation_details.get("citation_issues"):
                return "chunk_overlap"  # Missing context between chunks
            else:
                return "retrieval_quality"  # Wrong chunks retrieved
        
        elif metric_name == "citation_coverage":
            # Low citation coverage could be due to:
            # - Poor chunk boundaries
            # - Citation format issues
            if evaluation_details.get("invalid_citations", 0) > 0:
                return "citation_format"  # Citations not properly formatted
            else:
                return "chunk_boundaries"  # Chunks not properly cited
        
        elif metric_name == "refusal_correctness":
            # Refusal issues could be due to:
            # - ACL configuration
            # - Prompt template
            if evaluation_details.get("acl_denied"):
                return "acl_config"  # ACL not properly configured
            else:
                return "prompt_template"  # Prompt not instructing proper refusal
        
        elif metric_name in ["context_relevance", "answer_relevance"]:
            # Relevance issues could be due to:
            # - Embedding model
            # - Retrieval configuration
            return "embedding_model"  # Or "retrieval_config"
        
        else:
            return "unknown"  # Unknown root cause




