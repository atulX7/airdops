"""
Report generator for evaluation results.

Generates metrics reports (per-query + aggregate) in various formats.
"""

import json
from typing import Dict, List, Optional
from uuid import UUID

from loguru import logger


class ReportGenerator:
    """Generates evaluation reports."""

    @staticmethod
    def generate_json_report(
        per_query_results: List[Dict],
        aggregate_metrics: Dict,
        metadata: Optional[Dict] = None,
    ) -> Dict:
        """
        Generate JSON report.
        
        Args:
            per_query_results: Per-query evaluation results
            aggregate_metrics: Aggregate metrics
            metadata: Additional metadata
            
        Returns:
            JSON report dictionary
        """
        report = {
            "metadata": metadata or {},
            "summary": {
                "total_queries": len(per_query_results),
                "aggregate_metrics": aggregate_metrics,
            },
            "per_query_results": per_query_results,
        }
        return report

    @staticmethod
    def generate_csv_report(
        per_query_results: List[Dict],
        aggregate_metrics: Dict,
    ) -> str:
        """
        Generate CSV report.
        
        Args:
            per_query_results: Per-query evaluation results
            aggregate_metrics: Aggregate metrics
            
        Returns:
            CSV string
        """
        import csv
        from io import StringIO

        output = StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow([
            "query",
            "groundedness_score",
            "groundedness_passed",
            "context_relevance_score",
            "context_relevance_passed",
            "answer_relevance_score",
            "answer_relevance_passed",
            "answer_correctness_score",
            "answer_correctness_passed",
            "citation_coverage_score",
            "citation_coverage_passed",
            "refusal_correctness_score",
            "refusal_correctness_passed",
        ])

        # Rows
        for result in per_query_results:
            if "error" in result:
                continue
            metrics = result.get("metrics", {})
            writer.writerow([
                result.get("query", ""),
                metrics.get("groundedness", {}).get("score", 0.0),
                metrics.get("groundedness", {}).get("passed", False),
                metrics.get("context_relevance", {}).get("score", 0.0),
                metrics.get("context_relevance", {}).get("passed", False),
                metrics.get("answer_relevance", {}).get("score", 0.0),
                metrics.get("answer_relevance", {}).get("passed", False),
                metrics.get("answer_correctness", {}).get("score", 0.0),
                metrics.get("answer_correctness", {}).get("passed", False),
                metrics.get("citation_coverage", {}).get("score", 0.0),
                metrics.get("citation_coverage", {}).get("passed", False),
                metrics.get("refusal_correctness", {}).get("score", 0.0),
                metrics.get("refusal_correctness", {}).get("passed", False),
            ])

        return output.getvalue()




