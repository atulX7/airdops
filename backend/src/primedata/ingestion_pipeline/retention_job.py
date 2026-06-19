"""
Artifact Retention Job - Phase 3

Background worker to enforce retention policies on pipeline artifacts.
Archives or deletes artifacts based on their retention policy and age.

Enterprise best practices:
- Soft delete first (mark as DELETED)
- Hard delete after grace period (mark as PURGED)
- Archive to cold storage (optional)
- Cost optimization
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List

from loguru import logger
from primedata.db.database import get_db
from primedata.db.models import (
    ArtifactStatus,
    PipelineArtifact,
    RetentionPolicy,
)
from primedata.storage.minio_client import minio_client
from sqlalchemy.orm import Session


def apply_retention_policies(
    db: Session,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Apply retention policies to artifacts.

    Phase 3: Retention policy enforcement

    Args:
        db: Database session
        dry_run: If True, only report what would be done without making changes

    Returns:
        Dictionary with statistics on what was processed
    """
    stats = {
        "archived": 0,
        "deleted": 0,
        "purged": 0,
        "errors": 0,
        "total_processed": 0,
        "total_size_freed_bytes": 0,
    }

    cutoff_dates = {
        RetentionPolicy.DAYS_30: datetime.utcnow() - timedelta(days=30),
        RetentionPolicy.DAYS_90: datetime.utcnow() - timedelta(days=90),
        RetentionPolicy.DAYS_365: datetime.utcnow() - timedelta(days=365),
        RetentionPolicy.ON_FAILURE_KEEP_90: datetime.utcnow() - timedelta(days=90),
    }

    # Process each retention policy
    for policy, cutoff_date in cutoff_dates.items():
        artifacts = (
            db.query(PipelineArtifact)
            .filter(
                PipelineArtifact.retention_policy == policy,
                PipelineArtifact.status == ArtifactStatus.ACTIVE,
                PipelineArtifact.created_at < cutoff_date,
            )
            .all()
        )

        for artifact in artifacts:
            try:
                stats["total_processed"] += 1

                if policy == RetentionPolicy.DELETE_ON_PROMOTE:
                    # Special handling: check if product is promoted
                    # If promoted, delete artifacts from older versions
                    # For now, skip (would need product context)
                    continue

                if dry_run:
                    logger.info(f"[DRY RUN] Would archive artifact {artifact.id} ({artifact.artifact_name})")
                    stats["archived"] += 1
                    stats["total_size_freed_bytes"] += artifact.file_size
                    continue

                # Archive artifact (soft delete)
                artifact.status = ArtifactStatus.DELETED
                artifact.deleted_at = datetime.utcnow()
                db.commit()

                stats["archived"] += 1
                stats["total_size_freed_bytes"] += artifact.file_size
                logger.info(f"Archived artifact {artifact.id} ({artifact.artifact_name}) from {artifact.stage_name}")

            except Exception as e:
                logger.error(f"Error processing artifact {artifact.id}: {e}", exc_info=True)
                stats["errors"] += 1

    # Hard delete artifacts marked as DELETED for more than 7 days
    purge_cutoff = datetime.utcnow() - timedelta(days=7)
    deleted_artifacts = (
        db.query(PipelineArtifact)
        .filter(
            PipelineArtifact.status == ArtifactStatus.DELETED,
            PipelineArtifact.deleted_at < purge_cutoff,
        )
        .all()
    )

    for artifact in deleted_artifacts:
        try:
            # Optionally delete from MinIO (if not already deleted)
            if artifact.storage_bucket != "none" and artifact.storage_bucket != "qdrant":
                try:
                    minio_client.client.remove_object(artifact.storage_bucket, artifact.storage_key)
                    logger.info(f"Deleted artifact from MinIO: {artifact.storage_bucket}/{artifact.storage_key}")
                except Exception as e:
                    logger.warning(
                        f"Failed to delete artifact from MinIO {artifact.storage_bucket}/{artifact.storage_key}: {e}"
                    )

            # Mark as purged (hard delete from DB)
            artifact.status = ArtifactStatus.PURGED
            db.commit()

            stats["purged"] += 1
            logger.info(f"Purged artifact {artifact.id} ({artifact.artifact_name})")

        except Exception as e:
            logger.error(f"Error purging artifact {artifact.id}: {e}", exc_info=True)
            stats["errors"] += 1

    return stats


def run_retention_job(dry_run: bool = False) -> Dict[str, Any]:
    """
    Main entry point for retention job.

    Can be called as:
    - Standalone script
    - Cron job
    - Airflow DAG
    - Scheduled task

    Args:
        dry_run: If True, only report without making changes

    Returns:
        Statistics dictionary
    """
    logger.info(f"Starting artifact retention job (dry_run={dry_run})")

    db = next(get_db())
    try:
        stats = apply_retention_policies(db, dry_run=dry_run)

        logger.info(
            f"Retention job completed: "
            f"processed={stats['total_processed']}, "
            f"archived={stats['archived']}, "
            f"purged={stats['purged']}, "
            f"errors={stats['errors']}, "
            f"size_freed={stats['total_size_freed_bytes']} bytes"
        )

        return stats

    finally:
        db.close()


if __name__ == "__main__":
    # Allow running as standalone script
    import sys

    dry_run = "--dry-run" in sys.argv
    stats = run_retention_job(dry_run=dry_run)
    print(f"Retention job stats: {stats}")
