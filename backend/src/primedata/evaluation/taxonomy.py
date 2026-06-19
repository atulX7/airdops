"""
Evaluation taxonomy and scope definitions.

Defines the evaluation scope, question types, and pass/fail criteria for RAG quality assessment.
"""

from typing import Dict, List, Optional

from .question_types import QuestionType


class EvaluationTaxonomy:
    """Evaluation taxonomy for RAG quality assessment."""

    # Evaluation targets
    EVALUATION_TARGETS = [
        "rag_answers",  # RAG answers from /chat endpoint
        "retrieval",  # Retrieval quality
        "generation",  # LLM generation quality
    ]

    # Question type taxonomy
    QUESTION_TYPES = [qt.value for qt in QuestionType]

    # Pass/fail criteria
    @staticmethod
    def get_pass_criteria(question_type: QuestionType) -> Dict[str, any]:
        """
        Get pass/fail criteria for a question type.
        
        Args:
            question_type: The question type
            
        Returns:
            Dictionary with pass criteria
        """
        criteria = {
            QuestionType.FACTUAL: {
                "requires_exact_match": False,
                "requires_citation": True,
                "allows_refusal": False,
                "min_groundedness": 0.85,
            },
            QuestionType.SUMMARIZATION: {
                "requires_exact_match": False,
                "requires_citation": True,
                "allows_refusal": False,
                "min_groundedness": 0.80,
            },
            QuestionType.POLICY: {
                "requires_exact_match": False,
                "requires_citation": True,
                "allows_refusal": True,  # "Deny + explain" is valid
                "min_groundedness": 0.90,
            },
            QuestionType.SYNTHESIS: {
                "requires_exact_match": False,
                "requires_citation": True,
                "allows_refusal": False,
                "min_groundedness": 0.80,
            },
            QuestionType.ADVERSARIAL: {
                "requires_exact_match": False,
                "requires_citation": False,
                "allows_refusal": True,  # Should refuse when context missing
                "min_groundedness": 0.95,  # High bar for adversarial
            },
            QuestionType.COMPARISON: {
                "requires_exact_match": False,
                "requires_citation": True,
                "allows_refusal": False,
                "min_groundedness": 0.80,
            },
            QuestionType.CAUSAL: {
                "requires_exact_match": False,
                "requires_citation": True,
                "allows_refusal": False,
                "min_groundedness": 0.80,
            },
            QuestionType.TEMPORAL: {
                "requires_exact_match": False,
                "requires_citation": True,
                "allows_refusal": False,
                "min_groundedness": 0.85,
            },
        }
        return criteria.get(question_type, {})

    @staticmethod
    def is_valid_question_type(question_type: str) -> bool:
        """Check if question type is valid."""
        try:
            QuestionType(question_type)
            return True
        except ValueError:
            return False

    @staticmethod
    def get_default_thresholds() -> Dict[str, float]:
        """Get default quality thresholds."""
        return {
            "groundedness_min": 0.80,
            "hallucination_rate_max": 0.05,
            "acl_leakage_max": 0.0,
            "citation_coverage_min": 0.90,
            "refusal_correctness_min": 0.95,
            "context_relevance_min": 0.75,
            "answer_relevance_min": 0.80,
        }




