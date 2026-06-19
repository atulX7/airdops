"""
Recommendation engine for RAG quality improvements.

Generates actionable recommendations based on evaluation failures.
"""

from typing import Dict, List, Optional

from loguru import logger

from primedata.evaluation.improvement.root_cause_analyzer import RootCauseAnalyzer


class RecommendationEngine:
    """Generates actionable recommendations."""

    @staticmethod
    def generate_recommendations(
        root_cause: str,
        metric_name: str,
        current_score: float,
        threshold: float,
        current_config: Dict,
    ) -> Dict:
        """
        Generate actionable recommendations.
        
        Args:
            root_cause: Root cause identifier
            metric_name: Failed metric name
            current_score: Current score
            threshold: Threshold that needs to be met
            current_config: Current product configuration
            
        Returns:
            Recommendation dictionary
        """
        recommendations = []
        
        if root_cause == "chunk_overlap":
            current_overlap = current_config.get("chunking_config", {}).get("manual_settings", {}).get("chunk_overlap", 200)
            recommended_overlap = min(current_overlap + 100, 500)  # Increase by 100, max 500
            
            recommendations.append({
                "type": "chunk_overlap",
                "message": f"{metric_name} ({current_score:.2f}) below threshold ({threshold:.2f}). Increase chunk overlap to improve context continuity.",
                "action": "increase_chunk_overlap",
                "config": {"chunk_overlap": recommended_overlap},
                "expected_impact": f"{metric_name} improvement: +5-10%",
                "priority": "high",
            })
        
        elif root_cause == "chunk_boundaries":
            current_size = current_config.get("chunking_config", {}).get("manual_settings", {}).get("chunk_size", 1000)
            recommended_size = min(current_size + 200, 2000)  # Increase by 200, max 2000
            
            recommendations.append({
                "type": "chunk_size",
                "message": f"{metric_name} ({current_score:.2f}) below threshold ({threshold:.2f}). Increase chunk size to preserve context boundaries.",
                "action": "increase_chunk_size",
                "config": {"chunk_size": recommended_size},
                "expected_impact": f"{metric_name} improvement: +3-8%",
                "priority": "medium",
            })
        
        elif root_cause == "embedding_model":
            current_model = current_config.get("embedding_config", {}).get("embedder_name", "minilm")
            if current_model == "minilm":
                recommended_model = "mpnet"  # Upgrade to better model
            else:
                recommended_model = "e5-large"  # Upgrade to even better model
            
            recommendations.append({
                "type": "embedding_model",
                "message": f"{metric_name} ({current_score:.2f}) below threshold ({threshold:.2f}). Upgrade embedding model for better retrieval quality.",
                "action": "upgrade_embedding_model",
                "config": {"embedder_name": recommended_model},
                "expected_impact": f"{metric_name} improvement: +5-15%",
                "priority": "high",
            })
        
        elif root_cause == "acl_config":
            recommendations.append({
                "type": "acl_config",
                "message": f"{metric_name} ({current_score:.2f}) below threshold ({threshold:.2f}). Review ACL configuration and prompt template for proper refusal handling.",
                "action": "review_acl_config",
                "config": {},
                "expected_impact": f"{metric_name} improvement: +10-20%",
                "priority": "high",
            })
        
        elif root_cause == "prompt_template":
            recommendations.append({
                "type": "prompt_template",
                "message": f"{metric_name} ({current_score:.2f}) below threshold ({threshold:.2f}). Update prompt template to include proper refusal instructions.",
                "action": "update_prompt_template",
                "config": {},
                "expected_impact": f"{metric_name} improvement: +5-15%",
                "priority": "medium",
            })
        
        # Default recommendation if no specific root cause
        if not recommendations:
            recommendations.append({
                "type": "general",
                "message": f"{metric_name} ({current_score:.2f}) below threshold ({threshold:.2f}). Review data quality and processing pipeline.",
                "action": "review_pipeline",
                "config": {},
                "expected_impact": "Varies",
                "priority": "low",
            })
        
        return {
            "recommendations": recommendations,
            "primary_recommendation": recommendations[0] if recommendations else None,
        }




