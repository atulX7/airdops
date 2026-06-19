"""
Base stage class for AIRD pipeline stages.

Provides common interface and utilities for all AIRD stages integrated into PrimeData.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
from uuid import UUID

from loguru import logger


class StageStatus(str, Enum):
    """Status of a pipeline stage execution."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class StageResult:
    """Result of a pipeline stage execution."""

    status: StageStatus
    stage_name: str
    product_id: UUID
    version: int
    metrics: Dict[str, Any]
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    artifacts: Optional[Dict[str, str]] = None  # Map of artifact name to MinIO path

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "status": self.status.value,
            "stage_name": self.stage_name,
            "product_id": str(self.product_id),
            "version": self.version,
            "metrics": self.metrics,
            "error": self.error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "artifacts": self.artifacts,
        }


class AirdStage(ABC):
    """Base class for AIRD pipeline stages.

    All AIRD stages should inherit from this class and implement the execute method.
    Stages are designed to be stateless and can be executed multiple times.
    """

    def __init__(
        self,
        product_id: UUID,
        version: int,
        workspace_id: UUID,
        config: Optional[Dict[str, Any]] = None,
    ):
        """Initialize stage.

        Args:
            product_id: Product UUID
            version: Product version number
            workspace_id: Workspace UUID
            config: Optional stage-specific configuration
        """
        self.product_id = product_id
        self.version = version
        self.workspace_id = workspace_id
        self.config = config or {}
        self.logger = logger.bind(
            stage=self.stage_name,
            product_id=str(product_id),
            version=version,
            workspace_id=str(workspace_id),
        )

    @property
    @abstractmethod
    def stage_name(self) -> str:
        """Return the name of this stage (e.g., 'preprocess', 'score')."""
        pass

    @abstractmethod
    def execute(self, context: Dict[str, Any]) -> StageResult:
        """Execute the stage.

        Args:
            context: Stage execution context (may include previous stage results)

        Returns:
            StageResult with execution status and metrics
        """
        pass

    def validate_inputs(self, context: Dict[str, Any]) -> bool:
        """Validate inputs before execution.

        Args:
            context: Stage execution context

        Returns:
            True if inputs are valid, False otherwise
        """
        return True

    def get_required_artifacts(self) -> list[str]:
        """Return list of required artifact names from previous stages.

        Returns:
            List of artifact names (e.g., ['processed_jsonl', 'metrics'])
        """
        return []

    def _create_result(
        self,
        status: StageStatus,
        metrics: Dict[str, Any],
        error: Optional[str] = None,
        artifacts: Optional[Dict[str, str]] = None,
        started_at: Optional[datetime] = None,
        finished_at: Optional[datetime] = None,
    ) -> StageResult:
        """Create a StageResult with common fields.

        Args:
            status: Execution status
            metrics: Stage metrics
            error: Error message if failed
            artifacts: Map of artifact names to MinIO paths
            started_at: Stage start time
            finished_at: Stage finish time

        Returns:
            StageResult instance
        """
        return StageResult(
            status=status,
            stage_name=self.stage_name,
            product_id=self.product_id,
            version=self.version,
            metrics=metrics,
            error=error,
            artifacts=artifacts,
            started_at=started_at or datetime.utcnow(),
            finished_at=finished_at or datetime.utcnow(),
        )
