"""
Pipeline archiver service for PrimeData.

Archives old pipeline run metrics to S3 to reduce PostgreSQL storage costs.
"""

from datetime import datetime, timedelta
from typing import List, Optional
from uuid import UUID

from loguru import logger
from primedata.db.models import PipelineRun, PipelineRunStatus
from primedata.services.s3_json_storage import save_json_to_s3
from sqlalchemy import and_
from sqlalchemy.orm import Session


def archive_old_pipeline_runs(db: Session, days: int = 90, batch_size: int = 100, minio_client=None) -> dict:
    """Archive metrics for pipeline runs older than specified days to S3.

    Args:
        db: Database session
        days: Number of days to keep metrics in DB (default: 90)
        batch_size: Number of runs to process per batch (default: 100)
        minio_client: Optional MinIO client

    Returns:
        Dictionary with archiving statistics
    """
    cutoff_date = datetime.utcnow() - timedelta(days=days)

    # Find runs older than cutoff that haven't been archived yet
    runs_to_archive = (
        db.query(PipelineRun)
        .filter(
            and_(
                PipelineRun.created_at < cutoff_date,
                PipelineRun.metrics_path.is_(None),  # Not yet archived
                PipelineRun.metrics.isnot(None),  # Has metrics
                PipelineRun.metrics != {},  # Metrics not empty
            )
        )
        .limit(batch_size)
        .all()
    )

    archived_count = 0
    failed_count = 0
    total_size_saved = 0

    for run in runs_to_archive:
        try:
            # Save metrics to S3
            s3_path = save_json_to_s3(
                run.workspace_id,
                run.product_id,
                "metrics",
                run.metrics,
                minio_client=minio_client,
                version=run.version,
                subfolder="pipeline_runs",
            )

            if s3_path:
                # Update run with S3 path and archive timestamp
                run.metrics_path = s3_path
                run.archived_at = datetime.utcnow()

                # Estimate size saved (rough calculation)
                import json

                metrics_json = json.dumps(run.metrics, default=str)
                total_size_saved += len(metrics_json.encode("utf-8"))

                # Clear DB field
                run.metrics = {}

                archived_count += 1
                logger.info(f"Archived metrics for pipeline run {run.id} to S3: {s3_path}")
            else:
                failed_count += 1
                logger.error(f"Failed to archive metrics for pipeline run {run.id}")
        except Exception as e:
            failed_count += 1
            logger.error(f"Error archiving pipeline run {run.id}: {e}", exc_info=True)

    # Commit all changes
    if archived_count > 0:
        db.commit()
        logger.info(
            f"Archived {archived_count} pipeline runs, failed {failed_count}, saved ~{total_size_saved / 1024 / 1024:.2f} MB"
        )

    return {
        "archived_count": archived_count,
        "failed_count": failed_count,
        "total_size_saved_bytes": total_size_saved,
        "cutoff_date": cutoff_date.isoformat(),
    }


def archive_pipeline_run_metrics(db: Session, pipeline_run_id: UUID, minio_client=None) -> Optional[str]:
    """Archive metrics for a specific pipeline run to S3.

    Args:
        db: Database session
        pipeline_run_id: Pipeline run UUID
        minio_client: Optional MinIO client

    Returns:
        S3 path if successful, None otherwise
    """
    run = db.query(PipelineRun).filter(PipelineRun.id == pipeline_run_id).first()
    if not run:
        logger.error(f"Pipeline run {pipeline_run_id} not found")
        return None

    if not run.metrics or run.metrics == {}:
        logger.warning(f"Pipeline run {pipeline_run_id} has no metrics to archive")
        return None

    if run.metrics_path:
        logger.info(f"Pipeline run {pipeline_run_id} already archived to {run.metrics_path}")
        return run.metrics_path

    try:
        # Save metrics to S3
        s3_path = save_json_to_s3(
            run.workspace_id,
            run.product_id,
            "metrics",
            run.metrics,
            minio_client=minio_client,
            version=run.version,
            subfolder="pipeline_runs",
        )

        if s3_path:
            run.metrics_path = s3_path
            run.archived_at = datetime.utcnow()
            run.metrics = {}  # Clear DB field
            db.commit()
            logger.info(f"Archived metrics for pipeline run {pipeline_run_id} to S3: {s3_path}")
            return s3_path
        else:
            logger.error(f"Failed to save metrics to S3 for pipeline run {pipeline_run_id}")
            return None
    except Exception as e:
        logger.error(f"Error archiving pipeline run {pipeline_run_id}: {e}", exc_info=True)
        return None



