"""
AIRD policy evaluation stage for PrimeData.

Evaluates readiness fingerprints against policy thresholds.
"""

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from loguru import logger
from primedata.ingestion_pipeline.aird_stages.base import AirdStage, StageResult, StageStatus
from primedata.ingestion_pipeline.aird_stages.config import get_aird_config
from primedata.services.policy_engine import evaluate_policy


class PolicyStage(AirdStage):
    """Policy stage that evaluates fingerprints against policy thresholds."""

    @property
    def stage_name(self) -> str:
        return "policy"

    def get_required_artifacts(self) -> list[str]:
        """Policy requires fingerprint from fingerprint stage."""
        return ["fingerprint_json"]

    def execute(self, context: Dict[str, Any]) -> StageResult:
        """Execute policy evaluation stage.

        Args:
            context: Stage execution context with:
                - storage: AirdStorageAdapter
                - fingerprint_result: Optional result from fingerprint stage

        Returns:
            StageResult with policy evaluation metrics
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
            # Get fingerprint from previous stage or load from storage
            fingerprint_result = context.get("fingerprint_result")
            if fingerprint_result and fingerprint_result.get("metrics", {}).get("fingerprint"):
                fingerprint = fingerprint_result["metrics"]["fingerprint"]
            else:
                # Try to load from storage
                fingerprint_data = storage.get_artifact("fingerprint.json")
                if fingerprint_data:
                    import json

                    fingerprint_obj = json.loads(fingerprint_data.decode("utf-8"))
                    fingerprint = fingerprint_obj.get("fingerprint", {})
                else:
                    self.logger.warning("No fingerprint found for policy evaluation")
                    return self._create_result(
                        status=StageStatus.SKIPPED,
                        metrics={"reason": "no_fingerprint"},
                        started_at=started_at,
                    )

            if not fingerprint:
                return self._create_result(
                    status=StageStatus.FAILED,
                    metrics={},
                    error="Empty fingerprint",
                    started_at=started_at,
                )

            self.logger.info("Evaluating policy against fingerprint")

            # Get policy thresholds from config
            config = get_aird_config()
            thresholds = {
                "min_trust_score": config.policy_min_trust_score,
                "min_secure": config.policy_min_secure,
                "min_metadata_presence": config.policy_min_metadata_presence,
                "min_kb_ready": config.policy_min_kb_ready,
            }

            # Evaluate policy
            policy_result = evaluate_policy(fingerprint, thresholds)

            finished_at = datetime.utcnow()

            metrics = {
                "policy_passed": policy_result["policy_passed"],
                "violations": policy_result["violations"],
                "violations_count": len(policy_result["violations"]),
                "thresholds": policy_result["thresholds"],
            }

            return self._create_result(
                status=StageStatus.SUCCEEDED if policy_result["policy_passed"] else StageStatus.FAILED,
                metrics=metrics,
                started_at=started_at,
                finished_at=finished_at,
            )

        except Exception as e:
            self.logger.error(f"Policy evaluation failed: {e}", exc_info=True)
            return self._create_result(
                status=StageStatus.FAILED,
                metrics={},
                error=str(e),
                started_at=started_at,
            )
