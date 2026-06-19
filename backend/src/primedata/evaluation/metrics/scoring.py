"""
Unified scoring interface for RAG quality metrics.
"""

from typing import Dict, List, Optional, Any

import numpy as np


class MetricScore:
    """Represents a metric score result."""

    def __init__(
        self,
        metric_name: str,
        score: float,
        passed: bool,
        details: Optional[Dict] = None,
        evidence: Optional[List] = None,
    ):
        """
        Initialize metric score.
        
        Args:
            metric_name: Name of the metric
            score: Score value (0-1 scale)
            passed: Whether metric passed threshold
            details: Metric-specific details
            evidence: Supporting evidence
        """
        self.metric_name = metric_name
        self.score = score
        self.passed = passed
        self.details = details or {}
        self.evidence = evidence or []

    def _convert_numpy_types(self, obj: Any) -> Any:
        """Recursively convert numpy types to native Python types."""
        if isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.bool_):
            return bool(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, dict):
            return {key: self._convert_numpy_types(value) for key, value in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [self._convert_numpy_types(item) for item in obj]
        else:
            return obj

    def to_dict(self) -> Dict:
        """Convert to dictionary with numpy types converted to native Python types."""
        result = {
            "metric_name": self.metric_name,
            "score": float(self.score) if isinstance(self.score, (np.integer, np.floating)) else self.score,
            "passed": bool(self.passed) if isinstance(self.passed, np.bool_) else self.passed,
            "details": self._convert_numpy_types(self.details),
            "evidence": self._convert_numpy_types(self.evidence),
        }
        return result




