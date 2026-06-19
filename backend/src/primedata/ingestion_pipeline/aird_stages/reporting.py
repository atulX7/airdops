"""
AIRD PDF report generation stage for PrimeData.

Generates PDF trust reports from chunk-level metrics.
"""

from datetime import datetime
from typing import Any, Dict
from uuid import UUID

from loguru import logger
from primedata.ingestion_pipeline.aird_stages.base import AirdStage, StageResult, StageStatus
from primedata.ingestion_pipeline.aird_stages.config import get_aird_config
from primedata.services.reporting import generate_trust_report


class ReportingStage(AirdStage):
    """Reporting stage that generates PDF trust reports."""

    @property
    def stage_name(self) -> str:
        return "reporting"

    def get_required_artifacts(self) -> list[str]:
        """Reporting requires metrics from scoring stage."""
        return ["metrics_json"]

    def execute(self, context: Dict[str, Any]) -> StageResult:
        """Execute PDF report generation stage.

        Args:
            context: Stage execution context with:
                - storage: AirdStorageAdapter
                - scoring_result: Optional result from scoring stage

        Returns:
            StageResult with reporting metrics
        """
        started_at = datetime.utcnow()
        storage = context.get("storage")

        if not storage:
            return self._create_result(
                status=StageStatus.FAILED,
                metrics={},
                error="Storage adapter not found in context",
                started_at=started_at,
            )

        try:
            # Load metrics from storage
            metrics = storage.get_metrics_json()
            if not metrics:
                self.logger.warning("No metrics found for PDF report generation")
                return self._create_result(
                    status=StageStatus.SKIPPED,
                    metrics={"reason": "no_metrics"},
                    started_at=started_at,
                )

            self.logger.info(f"Generating PDF report from {len(metrics)} metric entries")

            # Get threshold from config (convert to 0-100 scale for report)
            config = get_aird_config()
            threshold = config.default_scoring_threshold  # Already 0-100 scale

            # Generate PDF report (may raise RuntimeError if matplotlib is not available)
            try:
                pdf_bytes = generate_trust_report(metrics, threshold)
            except RuntimeError as e:
                if "matplotlib is required" in str(e):
                    self.logger.warning("matplotlib not available, skipping PDF report generation")
                    return self._create_result(
                        status=StageStatus.SKIPPED,
                        metrics={"reason": "matplotlib_not_available"},
                        started_at=started_at,
                    )
                raise  # Re-raise if it's a different RuntimeError

            if not pdf_bytes:
                return self._create_result(
                    status=StageStatus.FAILED,
                    metrics={},
                    error="Failed to generate PDF report",
                    started_at=started_at,
                )

            # Store PDF report
            report_path = storage.put_artifact(
                "ai_trust_report.pdf",
                pdf_bytes,
                content_type="application/pdf",
            )

            finished_at = datetime.utcnow()

            artifacts = {
                "trust_report_pdf": report_path,
            }

            metrics_result = {
                "entries_processed": len(metrics),
                "threshold": threshold,
                "pdf_size_bytes": len(pdf_bytes),
            }

            return self._create_result(
                status=StageStatus.SUCCEEDED,
                metrics=metrics_result,
                artifacts=artifacts,
                started_at=started_at,
                finished_at=finished_at,
            )

        except Exception as e:
            self.logger.error(f"PDF report generation failed: {e}", exc_info=True)
            return self._create_result(
                status=StageStatus.FAILED,
                metrics={},
                error=str(e),
                started_at=started_at,
            )
