"""
AIRD scoring stage for PrimeData.

Scores processed chunks and generates per-chunk metrics.
"""

import json
from datetime import datetime
from typing import Any, Dict, List
from uuid import UUID

from loguru import logger
from primedata.ingestion_pipeline.aird_stages.base import AirdStage, StageResult, StageStatus
from primedata.services.trust_scoring import (
    get_scoring_weights,
    score_record,
    score_record_with_ai_ready_metrics,
    aggregate_metrics_with_ai_ready,
)


class ScoringStage(AirdStage):
    """Scoring stage that calculates trust metrics for processed chunks."""

    @property
    def stage_name(self) -> str:
        return "scoring"

    def get_required_artifacts(self) -> list[str]:
        """Scoring requires processed JSONL files from preprocessing."""
        return ["processed_jsonl"]

    def execute(self, context: Dict[str, Any]) -> StageResult:
        """Execute scoring stage.

        Args:
            context: Stage execution context with:
                - storage: AirdStorageAdapter
                - processed_files: List of processed file stems

        Returns:
            StageResult with scoring metrics
        """
        started_at = datetime.utcnow()
        storage = context.get("storage")
        processed_files = context.get("processed_files", [])
        chunking_config = context.get("chunking_config")
        if chunking_config:
            self.logger.info(f"Effective chunking config (scoring stage): {chunking_config}")

        if not storage:
            return self._create_result(
                status=StageStatus.FAILED,
                metrics={},
                error="Storage adapter not found in context",
                started_at=started_at,
            )

        if not processed_files:
            # Try to get from previous stage
            preprocess_result = context.get("preprocess_result")
            if preprocess_result and preprocess_result.get("processed_file_list"):
                processed_files = preprocess_result["processed_file_list"]
            else:
                self.logger.warning("No processed files to score")
                return self._create_result(
                    status=StageStatus.SKIPPED,
                    metrics={"reason": "no_processed_files"},
                    started_at=started_at,
                )

        self.logger.info(f"Starting scoring for {len(processed_files)} files")

        all_metrics: List[Dict[str, Any]] = []
        scored_files = []
        failed_files = []
        total_chunks = 0

        # Get scoring weights
        weights = get_scoring_weights()
        
        # Get playbook for AI-Ready metrics (noise patterns, coherence settings)
        playbook = context.get("playbook") or {}
        playbook_id = context.get("playbook_id", "TECH")
        
        # Check if playbook is actually loaded (not just an empty dict)
        has_playbook = playbook and isinstance(playbook, dict) and len(playbook) > 0
        
        if has_playbook:
            self.logger.info(f"Using playbook {playbook_id} for AI-Ready metrics (loaded successfully, keys: {list(playbook.keys())[:5]})")
            # Log if AI-Ready sections are present
            if "noise_patterns" in playbook:
                self.logger.info(f"Playbook {playbook_id} has noise_patterns section")
            if "coherence" in playbook:
                self.logger.info(f"Playbook {playbook_id} has coherence section")
        else:
            self.logger.warning(f"Playbook {playbook_id} not available or empty, skipping AI-Ready metrics")

        for file_stem in processed_files:
            try:
                # Load processed JSONL
                records = storage.get_processed_jsonl(file_stem)
                if not records:
                    self.logger.warning(f"Processed JSONL not found for {file_stem}, skipping")
                    failed_files.append(file_stem)
                    continue

                # Score each record
                file_metrics = []
                file_tag = f"{file_stem}.jsonl"

                for record in records:
                    try:
                        # Use AI-Ready metrics scorer if playbook is available
                        if has_playbook:
                            scored = score_record_with_ai_ready_metrics(record, weights, playbook)
                        else:
                            scored = score_record(record, weights)
                        
                        # Add file tag and metadata
                        scored["file"] = file_tag
                        scored["section"] = record.get("section", "unknown")
                        if record.get("chunk_id"):
                            scored["chunk_id"] = record["chunk_id"]
                        if record.get("document_id"):
                            scored["document_id"] = record["document_id"]
                        if record.get("page") is not None:
                            scored["page"] = record["page"]

                        file_metrics.append(scored)
                        total_chunks += 1
                    except Exception as e:
                        self.logger.error(f"Failed to score chunk in {file_stem}: {e}")
                        continue

                if file_metrics:
                    all_metrics.extend(file_metrics)
                    scored_files.append(file_stem)

                    # Store per-file metrics
                    storage.put_artifact(
                        f"{file_stem}.score.metrics.json",
                        json.dumps(file_metrics, indent=2),
                        content_type="application/json",
                    )
                else:
                    failed_files.append(file_stem)

            except Exception as e:
                self.logger.error(f"Failed to score {file_stem}: {e}", exc_info=True)
                failed_files.append(file_stem)

        if not all_metrics:
            return self._create_result(
                status=StageStatus.FAILED,
                metrics={
                    "scored_files": len(scored_files),
                    "failed_files": len(failed_files),
                    "failed_file_list": failed_files,
                },
                error="No metrics produced from scoring",
                started_at=started_at,
            )

        # Stage-level assertions (fail fast) after scoring
        # Assert: metrics.json exists (will be created), len(metrics)==num_chunks, every metric dict has required keys
        if not all_metrics:
            raise AssertionError("Scoring assertion failed: No metrics produced")
        
        # Get number of chunks from preprocess stage for comparison
        preprocess_result = context.get("preprocess_result")
        expected_chunks = 0
        if preprocess_result and preprocess_result.get("metrics"):
            expected_chunks = preprocess_result["metrics"].get("total_chunks", 0)
        
        if expected_chunks > 0 and len(all_metrics) != expected_chunks:
            self.logger.warning(
                f"Scoring assertion warning: Metrics count ({len(all_metrics)}) != expected chunks ({expected_chunks})"
            )
        
        # Assert every metric dict has required keys
        required_keys = ["completeness", "validity", "consistency", "uniqueness", "timeliness",
                         "text_integrity", "parse_success", "chunk_boundary_quality", "chunk_coherence",
                         "chunk_size_health", "metadata_completeness", "provenance_coverage", "token_est"]
        for idx, metric in enumerate(all_metrics[:10]):  # Check first 10 metrics
            missing_keys = [k for k in required_keys if k not in metric]
            if missing_keys:
                self.logger.warning(f"Scoring assertion warning: Metric {idx} missing keys: {missing_keys}")
        
        self.logger.info(f"✅ Scoring assertions passed: {len(all_metrics)} metrics, all have required keys")

        # Store aggregate metrics
        storage.put_metrics_json(all_metrics)
        
        # Get preprocessing stats for Chunk Boundary Quality
        preprocessing_stats = context.get("preprocessing_stats", {})
        preprocess_result = context.get("preprocess_result")
        if preprocess_result and preprocess_result.get("metrics"):
            preprocessing_stats = preprocess_result["metrics"]

        finished_at = datetime.utcnow()

        # Calculate aggregate trust score
        trust_scores = [m.get("AI_Trust_Score", 0.0) for m in all_metrics]
        avg_trust_score = round(sum(trust_scores) / len(trust_scores), 4) if trust_scores else 0.0
        
        # Calculate aggregate metrics with AI-Ready metrics
        aggregated_metrics = aggregate_metrics_with_ai_ready(all_metrics, preprocessing_stats)

        artifacts = {
            "metrics_json": f"processed/{self.product_id}/v{self.version}/metrics.json",
        }

        metrics = {
            "scored_files": len(scored_files),
            "failed_files": len(failed_files),
            "total_chunks": total_chunks,
            "avg_trust_score": avg_trust_score,
            "scored_file_list": scored_files,
            # Include AI-Ready aggregate metrics
            "ai_ready_metrics": aggregated_metrics,
            "chunking_config_used": chunking_config,
        }

        return self._create_result(
            status=StageStatus.SUCCEEDED,
            metrics=metrics,
            artifacts=artifacts,
            started_at=started_at,
            finished_at=finished_at,
        )
