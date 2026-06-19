"""
AIRD pipeline stages for PrimeData.

This module provides infrastructure for integrating AIRD pipeline stages
into PrimeData's Airflow-based ingestion pipeline.
"""

from .base import AirdStage, StageResult, StageStatus
from .config import AirdConfig, get_aird_config
from .logging import get_aird_logger, setup_aird_logging
from .storage import AirdStorageAdapter
from .tracking import StageTracker, track_stage_execution

__all__ = [
    "AirdStage",
    "StageResult",
    "StageStatus",
    "AirdConfig",
    "get_aird_config",
    "get_aird_logger",
    "setup_aird_logging",
    "AirdStorageAdapter",
    "StageTracker",
    "track_stage_execution",
]
