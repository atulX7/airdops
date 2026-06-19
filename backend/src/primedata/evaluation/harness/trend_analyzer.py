"""
Trend analyzer for evaluation results.

Analyzes trends by content type, product, model over time.
"""

from typing import Dict, List, Optional
from uuid import UUID

from loguru import logger
from sqlalchemy.orm import Session

from primedata.db.models import EvalRun, RAGQualityMetric


class TrendAnalyzer:
    """Analyzes trends in evaluation results."""

    def __init__(self, db: Session):
        """Initialize trend analyzer."""
        self.db = db

    def analyze_trends(
        self,
        product_id: UUID,
        metric_name: Optional[str] = None,
        days: int = 30,
    ) -> Dict:
        """
        Analyze trends for a product.
        
        Args:
            product_id: Product ID
            metric_name: Optional metric name to filter
            days: Number of days to analyze
            
        Returns:
            Trend analysis results
        """
        from datetime import datetime, timedelta

        cutoff_date = datetime.utcnow() - timedelta(days=days)

        # Get metrics
        query = self.db.query(RAGQualityMetric).filter(
            RAGQualityMetric.product_id == product_id,
            RAGQualityMetric.timestamp >= cutoff_date,
        )

        if metric_name:
            query = query.filter(RAGQualityMetric.metric_name == metric_name)

        metrics = query.order_by(RAGQualityMetric.timestamp).all()

        # Group by metric name
        trends = {}
        for metric in metrics:
            if metric.metric_name not in trends:
                trends[metric.metric_name] = {
                    "values": [],
                    "timestamps": [],
                    "passed_count": 0,
                    "total_count": 0,
                }
            trends[metric.metric_name]["values"].append(metric.value)
            trends[metric.metric_name]["timestamps"].append(metric.timestamp.isoformat())
            trends[metric.metric_name]["total_count"] += 1
            if metric.passed:
                trends[metric.metric_name]["passed_count"] += 1

        # Calculate statistics
        for metric_name, data in trends.items():
            if data["values"]:
                data["mean"] = sum(data["values"]) / len(data["values"])
                data["min"] = min(data["values"])
                data["max"] = max(data["values"])
                data["trend"] = "improving" if len(data["values"]) > 1 and data["values"][-1] > data["values"][0] else "declining"
                data["pass_rate"] = data["passed_count"] / data["total_count"] if data["total_count"] > 0 else 0.0

        return {
            "product_id": str(product_id),
            "period_days": days,
            "trends": trends,
        }

    def compare_runs(
        self,
        run_id_1: UUID,
        run_id_2: UUID,
    ) -> Dict:
        """
        Compare two evaluation runs.
        
        Args:
            run_id_1: First run ID
            run_id_2: Second run ID
            
        Returns:
            Comparison results
        """
        run1 = self.db.query(EvalRun).filter(EvalRun.id == run_id_1).first()
        run2 = self.db.query(EvalRun).filter(EvalRun.id == run_id_2).first()

        if not run1 or not run2:
            raise ValueError("One or both runs not found")

        aggregate1 = run1.metrics.get("aggregate", {}) if run1.metrics else {}
        aggregate2 = run2.metrics.get("aggregate", {}) if run2.metrics else {}

        comparison = {}
        for metric_name in [
            "groundedness",
            "context_relevance",
            "answer_relevance",
            "answer_correctness",
            "citation_coverage",
            "refusal_correctness",
        ]:
            mean1 = aggregate1.get(metric_name, {}).get("mean", 0.0)
            mean2 = aggregate2.get(metric_name, {}).get("mean", 0.0)
            diff = mean2 - mean1
            comparison[metric_name] = {
                "run1_mean": mean1,
                "run2_mean": mean2,
                "difference": diff,
                "improvement": diff > 0,
                "improvement_percent": (diff / mean1 * 100) if mean1 > 0 else 0.0,
            }

        return comparison




