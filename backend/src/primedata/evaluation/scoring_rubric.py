"""
Scoring rubric for RAG evaluation.

Defines pass/fail behavior and scoring criteria for ACL scenarios and different question types.
"""

from typing import Dict, Optional

from .question_types import QuestionType
from .taxonomy import EvaluationTaxonomy


class ScoringRubric:
    """Scoring rubric for RAG quality evaluation."""

    @staticmethod
    def evaluate_answer(
        question_type: QuestionType,
        answer: str,
        citations: List[str],
        retrieved_chunks: List[Dict],
        acl_denied: bool = False,
        expected_refusal: bool = False,
    ) -> Dict[str, any]:
        """
        Evaluate an answer against the scoring rubric.
        
        Args:
            question_type: Type of question
            answer: The generated answer
            citations: List of citation IDs
            retrieved_chunks: List of retrieved chunks with metadata
            acl_denied: Whether ACL denied the request
            expected_refusal: Whether refusal was expected
            
        Returns:
            Dictionary with evaluation results
        """
        criteria = EvaluationTaxonomy.get_pass_criteria(question_type)
        
        result = {
            "passed": True,
            "score": 1.0,
            "violations": [],
            "details": {},
        }
        
        # Check ACL handling
        if acl_denied and expected_refusal:
            # "Deny + explain" is valid success for policy questions
            if question_type == QuestionType.POLICY:
                result["details"]["acl_handling"] = "correct_refusal"
                return result
            else:
                result["violations"].append("Unexpected ACL denial")
                result["passed"] = False
                result["score"] = 0.0
        
        # Check citation requirements
        if criteria.get("requires_citation", True):
            if not citations or len(citations) == 0:
                result["violations"].append("Missing citations")
                result["passed"] = False
                result["score"] *= 0.5
        
        # Check refusal correctness
        if expected_refusal and not acl_denied:
            if "I don't know" in answer.lower() or "I cannot" in answer.lower():
                result["details"]["refusal"] = "correct"
            else:
                result["violations"].append("Should have refused but didn't")
                result["passed"] = False
                result["score"] *= 0.3
        
        # Check for hallucination indicators
        if not citations and len(answer) > 50:
            # Long answer without citations might be hallucination
            result["violations"].append("Potential hallucination (no citations)")
            result["score"] *= 0.7
        
        return result

    @staticmethod
    def get_metric_weights() -> Dict[str, float]:
        """Get weights for different metrics in overall score."""
        return {
            "groundedness": 0.30,
            "relevance": 0.25,
            "citation_coverage": 0.20,
            "refusal_correctness": 0.15,
            "hallucination_rate": 0.10,
        }




