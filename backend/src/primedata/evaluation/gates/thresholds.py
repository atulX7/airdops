"""
Threshold definitions for RAG quality gates.
"""

from typing import Dict

from primedata.evaluation.taxonomy import EvaluationTaxonomy


class ThresholdManager:
    """Manages quality thresholds."""

    @staticmethod
    def get_default_thresholds() -> Dict[str, float]:
        """Get default thresholds."""
        return EvaluationTaxonomy.get_default_thresholds()

    @staticmethod
    def validate_thresholds(thresholds: Dict[str, float]) -> bool:
        """
        Validate threshold values.
        
        Args:
            thresholds: Threshold dictionary
            
        Returns:
            True if valid
        """
        defaults = ThresholdManager.get_default_thresholds()
        
        for key, value in thresholds.items():
            if key not in defaults:
                return False
            if not isinstance(value, (int, float)):
                return False
            if value < 0.0 or value > 1.0:
                return False
        
        return True

    @staticmethod
    def merge_thresholds(
        default: Dict[str, float],
        custom: Dict[str, float],
    ) -> Dict[str, float]:
        """
        Merge custom thresholds with defaults.
        
        Args:
            default: Default thresholds
            custom: Custom thresholds (overrides defaults)
            
        Returns:
            Merged thresholds
        """
        merged = default.copy()
        merged.update(custom)
        return merged




