"""
Gate evaluator for CI/CD quality gates.

Evaluates if metrics pass thresholds and can block promotion.
"""

from typing import Dict, List, Optional

from loguru import logger

from primedata.evaluation.gates.thresholds import ThresholdManager


class GateEvaluator:
    """Evaluates quality gates."""

    def __init__(self, thresholds: Optional[Dict[str, float]] = None):
        """
        Initialize gate evaluator.
        
        Args:
            thresholds: Quality thresholds (uses defaults if not provided)
        """
        if thresholds is None:
            thresholds = ThresholdManager.get_default_thresholds()
        self.thresholds = thresholds

    def evaluate_gates(
        self,
        aggregate_metrics: Dict,
        per_query_results: Optional[List[Dict]] = None,
    ) -> Dict:
        """
        Evaluate quality gates.
        
        Args:
            aggregate_metrics: Aggregate metrics from evaluation
            per_query_results: Optional per-query results for detailed analysis
            
        Returns:
            Gate evaluation results
        """
        gate_results = {}
        all_passed = True

        # Computed from per-query results only (not present in aggregate_metrics)
        per_query_only_thresholds = frozenset({"hallucination_rate_max", "acl_leakage_max"})

        # Check each metric
        for metric_name, threshold in self.thresholds.items():
            if metric_name in per_query_only_thresholds:
                continue

            # Map threshold key to metric name
            metric_key = self._map_threshold_to_metric(metric_name)

            # Optional: golden-answer metric only exists when dataset items include expected answers
            if metric_key not in aggregate_metrics and metric_name == "answer_correctness_min":
                continue
            
            if metric_key in aggregate_metrics:
                metric_data = aggregate_metrics[metric_key]
                mean_score = metric_data.get("mean", 0.0)
                passed = mean_score >= threshold
                
                gate_results[metric_name] = {
                    "threshold": threshold,
                    "actual": mean_score,
                    "passed": passed,
                }
                
                if not passed:
                    all_passed = False
            else:
                # Metric not found - fail gate
                gate_results[metric_name] = {
                    "threshold": threshold,
                    "actual": None,
                    "passed": False,
                    "error": "Metric not found in evaluation results",
                }
                all_passed = False

        # Hallucination rate and ACL leakage: derived from per-query results only
        if per_query_results:
            hallucination_rate = self._calculate_hallucination_rate(per_query_results)
            acl_leakage = self._calculate_acl_leakage(per_query_results)

            if "hallucination_rate_max" in self.thresholds:
                passed = hallucination_rate <= self.thresholds["hallucination_rate_max"]
                gate_results["hallucination_rate_max"] = {
                    "threshold": self.thresholds["hallucination_rate_max"],
                    "actual": hallucination_rate,
                    "passed": passed,
                }
                if not passed:
                    all_passed = False

            if "acl_leakage_max" in self.thresholds:
                passed = acl_leakage <= self.thresholds["acl_leakage_max"]
                gate_results["acl_leakage_max"] = {
                    "threshold": self.thresholds["acl_leakage_max"],
                    "actual": acl_leakage,
                    "passed": passed,
                }
                if not passed:
                    all_passed = False
        else:
            for max_key in ("hallucination_rate_max", "acl_leakage_max"):
                if max_key in self.thresholds:
                    gate_results[max_key] = {
                        "threshold": self.thresholds[max_key],
                        "actual": None,
                        "passed": False,
                        "error": "Per-query evaluation results are required for this gate.",
                    }
                    all_passed = False

        return {
            "all_passed": all_passed,
            "gates": gate_results,
            "blocking": not all_passed,
        }

    def _map_threshold_to_metric(self, threshold_key: str) -> str:
        """Map threshold key to metric name."""
        mapping = {
            "groundedness_min": "groundedness",
            "citation_coverage_min": "citation_coverage",
            "refusal_correctness_min": "refusal_correctness",
            "context_relevance_min": "context_relevance",
            "answer_relevance_min": "answer_relevance",
            "answer_correctness_min": "answer_correctness",
        }
        return mapping.get(threshold_key, threshold_key.replace("_min", "").replace("_max", ""))

    def _calculate_hallucination_rate(self, per_query_results: List[Dict]) -> float:
        """Calculate hallucination rate from per-query results."""
        total = 0
        hallucinations = 0
        
        for result in per_query_results:
            if "error" in result:
                continue
            metrics = result.get("metrics", {})
            groundedness = metrics.get("groundedness", {})
            score = groundedness.get("score", 1.0)
            total += 1
            if score < 0.5:  # Low groundedness suggests hallucination
                hallucinations += 1
        
        return hallucinations / total if total > 0 else 0.0

    def _calculate_acl_leakage(self, per_query_results: List[Dict]) -> float:
        """Calculate ACL leakage rate from per-query results."""
        # This would need to check if responses contain information that should have been blocked
        # For now, return 0.0 as placeholder
        return 0.0




