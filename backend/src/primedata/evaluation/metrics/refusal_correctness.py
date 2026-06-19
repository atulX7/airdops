"""
Refusal correctness metric.

Checks if system correctly refuses when evidence is missing or ACL denies.
"""

from typing import Dict, List, Optional

from loguru import logger

from ..metrics.scoring import MetricScore


class RefusalCorrectnessMetric:
    """Refusal correctness metric evaluator."""

    def evaluate(
        self,
        answer: str,
        acl_denied: bool,
        expected_refusal: bool,
        has_evidence: bool = True,
        threshold: float = 0.95,
    ) -> MetricScore:
        """
        Evaluate refusal correctness.
        
        Args:
            answer: Generated answer
            acl_denied: Whether ACL denied the request
            expected_refusal: Whether refusal was expected
            has_evidence: Whether evidence was available
            threshold: Threshold for passing
            
        Returns:
            MetricScore object
        """
        # Determine if refusal was correct
        should_refuse = expected_refusal or (acl_denied and not has_evidence)
        did_refuse = self._is_refusal(answer, acl_denied)
        
        if should_refuse and did_refuse:
            score = 1.0
            passed = True
            correctness = "correct_refusal"
        elif should_refuse and not did_refuse:
            score = 0.0
            passed = False
            correctness = "should_have_refused"
        elif not should_refuse and did_refuse:
            score = 0.3
            passed = False
            correctness = "incorrect_refusal"
        else:
            score = 1.0
            passed = True
            correctness = "correct_answer"

        passed = score >= threshold

        details = {
            "should_refuse": should_refuse,
            "did_refuse": did_refuse,
            "correctness": correctness,
            "acl_denied": acl_denied,
            "expected_refusal": expected_refusal,
            "has_evidence": has_evidence,
        }

        return MetricScore(
            metric_name="refusal_correctness",
            score=score,
            passed=passed,
            details=details,
        )

    def _is_refusal(self, answer: str, acl_denied: bool) -> bool:
        """Check if answer is a refusal."""
        if acl_denied:
            return True
        
        if not answer:
            return True
        
        refusal_indicators = [
            "i don't know",
            "i cannot",
            "i don't have",
            "i'm not able",
            "i cannot provide",
            "i don't have access",
            "i'm unable",
            "not available",
            "cannot answer",
        ]
        
        answer_lower = answer.lower()
        for indicator in refusal_indicators:
            if indicator in answer_lower:
                return True
        
        return False




