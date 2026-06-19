"""
Artifact Registry Service for Enterprise Traceability

This module provides functions for registering and managing pipeline artifacts
with full traceability, lineage, and retention policy support.

Phases:
- Phase 1: Basic artifact tracking (MinIO location, size, checksum)
- Phase 2: Data lineage (input artifacts dependencies)
- Phase 3: Retention policies (lifecycle management)
- Phase 4: Advanced features (comparison, diffing, analytics)
"""

import hashlib
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from loguru import logger
from primedata.db.models import (
    ArtifactStatus,
    ArtifactType,
    PipelineArtifact,
    PipelineRun,
    PipelineRunStatus,
    RetentionPolicy,
)
from sqlalchemy.orm import Session


def calculate_checksum(data: bytes, algorithm: str = "sha256") -> str:
    """Calculate checksum for data integrity verification.

    Args:
        data: Data bytes to checksum
        algorithm: Hash algorithm ("md5" or "sha256")

    Returns:
        Hexadecimal checksum string
    """
    if algorithm == "md5":
        return hashlib.md5(data).hexdigest()
    elif algorithm == "sha256":
        return hashlib.sha256(data).hexdigest()
    else:
        raise ValueError(f"Unsupported algorithm: {algorithm}")


def register_artifact(
    db: Session,
    pipeline_run_id: UUID,
    workspace_id: UUID,
    product_id: UUID,
    version: int,
    stage_name: str,
    artifact_type: ArtifactType,
    artifact_name: str,
    storage_bucket: str,
    storage_key: str,
    file_size: int,
    checksum: Optional[str] = None,
    storage_etag: Optional[str] = None,
    input_artifact_ids: Optional[List[UUID]] = None,
    artifact_metadata: Optional[Dict[str, Any]] = None,
    retention_policy: RetentionPolicy = RetentionPolicy.DAYS_90,
    created_by: Optional[UUID] = None,
) -> PipelineArtifact:
    """
    Register a new pipeline artifact.

    Phase 1 & 2: Basic tracking + lineage

    Args:
        db: Database session
        pipeline_run_id: Pipeline run that generated this artifact
        workspace_id: Workspace ID
        product_id: Product ID
        version: Product version
        stage_name: Stage that generated artifact ("preprocess", "scoring", etc.)
        artifact_type: Type of artifact (JSONL, JSON, CSV, PDF, VECTOR)
        artifact_name: Name of artifact ("processed_chunks", "metrics", etc.)
        storage_bucket: MinIO bucket name
        storage_key: Full MinIO object key
        file_size: File size in bytes
        checksum: Optional checksum (MD5 or SHA256)
        storage_etag: Optional MinIO ETag
        input_artifact_ids: List of artifact IDs this depends on (Phase 2: lineage)
        metadata: Stage-specific metadata dictionary
        retention_policy: Retention policy (Phase 3)
        created_by: Optional user ID if user-triggered

    Returns:
        Created PipelineArtifact instance
    """
    # Build input_artifacts lineage data (Phase 2)
    input_artifacts_data = []
    if input_artifact_ids:
        # Fetch input artifacts to get their details for lineage
        input_artifacts = db.query(PipelineArtifact).filter(PipelineArtifact.id.in_(input_artifact_ids)).all()

        for input_artifact in input_artifacts:
            input_artifacts_data.append(
                {
                    "artifact_id": str(input_artifact.id),
                    "stage": input_artifact.stage_name,
                    "artifact_name": input_artifact.artifact_name,
                    "storage_key": input_artifact.storage_key,
                }
            )

    # Determine retention policy based on pipeline run status
    if retention_policy == RetentionPolicy.DAYS_90:
        # Check if pipeline failed - use longer retention for failures
        pipeline_run = db.query(PipelineRun).filter(PipelineRun.id == pipeline_run_id).first()
        if pipeline_run and pipeline_run.status == PipelineRunStatus.FAILED:
            retention_policy = RetentionPolicy.ON_FAILURE_KEEP_90

    artifact = PipelineArtifact(
        pipeline_run_id=pipeline_run_id,
        workspace_id=workspace_id,
        product_id=product_id,
        version=version,
        stage_name=stage_name,
        artifact_type=artifact_type,
        artifact_name=artifact_name,
        storage_bucket=storage_bucket,
        storage_key=storage_key,
        file_size=file_size,
        checksum=checksum,
        storage_etag=storage_etag,
        input_artifacts=input_artifacts_data,
        artifact_metadata=artifact_metadata or {},
        retention_policy=retention_policy,
        status=ArtifactStatus.ACTIVE,
        created_by=created_by,
    )

    db.add(artifact)
    db.commit()
    db.refresh(artifact)

    logger.info(
        f"Registered artifact: {artifact_name} ({artifact_type.value}) from {stage_name} "
        f"for product {product_id} v{version}, size={file_size} bytes, "
        f"lineage={len(input_artifacts_data)} inputs"
    )

    return artifact


def get_artifacts_by_stage(
    db: Session,
    pipeline_run_id: UUID,
    stage_name: str,
) -> List[PipelineArtifact]:
    """Get all artifacts for a specific stage in a pipeline run.

    Args:
        db: Database session
        pipeline_run_id: Pipeline run ID
        stage_name: Stage name

    Returns:
        List of PipelineArtifact instances
    """
    return (
        db.query(PipelineArtifact)
        .filter(
            PipelineArtifact.pipeline_run_id == pipeline_run_id,
            PipelineArtifact.stage_name == stage_name,
            PipelineArtifact.status != ArtifactStatus.PURGED,
        )
        .all()
    )


def get_artifact_lineage(
    db: Session,
    artifact_id: UUID,
    direction: str = "downstream",  # "upstream" or "downstream"
) -> List[PipelineArtifact]:
    """Get artifact lineage (Phase 2).

    Args:
        db: Database session
        artifact_id: Artifact ID
        direction: "upstream" (inputs) or "downstream" (outputs using this)

    Returns:
        List of related artifacts
    """
    artifact = db.query(PipelineArtifact).filter(PipelineArtifact.id == artifact_id).first()
    if not artifact:
        return []

    if direction == "upstream":
        # Get input artifacts (artifacts this one depends on)
        input_ids = []
        for input_ref in artifact.input_artifacts or []:
            if isinstance(input_ref, dict) and "artifact_id" in input_ref:
                try:
                    input_ids.append(UUID(input_ref["artifact_id"]))
                except (ValueError, TypeError):
                    continue

        if not input_ids:
            return []

        return (
            db.query(PipelineArtifact)
            .filter(
                PipelineArtifact.id.in_(input_ids),
                PipelineArtifact.status != ArtifactStatus.PURGED,
            )
            .all()
        )

    elif direction == "downstream":
        # Get artifacts that depend on this one (artifacts with this in their input_artifacts)
        # This requires a JSON query - PostgreSQL supports this
        artifact_id_str = str(artifact_id)

        # Query artifacts where input_artifacts contains this artifact_id
        # PostgreSQL JSON query: WHERE input_artifacts @> '[{"artifact_id": "..."}]'::jsonb
        from sqlalchemy import text

        result = db.execute(
            text(
                """
                SELECT * FROM pipeline_artifacts
                WHERE input_artifacts::text LIKE :pattern
                AND status != 'purged'
            """
            ),
            {"pattern": f"%{artifact_id_str}%"},
        )

        artifacts = []
        for row in result:
            artifact_obj = db.query(PipelineArtifact).filter(PipelineArtifact.id == row.id).first()
            if artifact_obj:
                artifacts.append(artifact_obj)

        return artifacts

    else:
        raise ValueError(f"Invalid direction: {direction}. Use 'upstream' or 'downstream'")


def update_artifact_status(
    db: Session,
    artifact_id: UUID,
    status: ArtifactStatus,
    archived_at: Optional[datetime] = None,
    deleted_at: Optional[datetime] = None,
) -> PipelineArtifact:
    """Update artifact status (Phase 3: retention).

    Args:
        db: Database session
        artifact_id: Artifact ID
        status: New status
        archived_at: Timestamp if archiving
        deleted_at: Timestamp if deleting

    Returns:
        Updated PipelineArtifact instance
    """
    artifact = db.query(PipelineArtifact).filter(PipelineArtifact.id == artifact_id).first()
    if not artifact:
        raise ValueError(f"Artifact {artifact_id} not found")

    artifact.status = status
    if archived_at:
        artifact.archived_at = archived_at
    if deleted_at:
        artifact.deleted_at = deleted_at

    db.commit()
    db.refresh(artifact)

    logger.info(f"Updated artifact {artifact_id} status to {status.value}")

    return artifact


def get_artifacts_for_retention(
    db: Session,
    retention_policy: RetentionPolicy,
    older_than_days: int,
) -> List[PipelineArtifact]:
    """Get artifacts that should be archived/deleted based on retention policy (Phase 3).

    Args:
        db: Database session
        retention_policy: Retention policy to check
        older_than_days: Artifacts older than this many days

    Returns:
        List of artifacts that match criteria
    """
    from datetime import timedelta

    cutoff_date = datetime.utcnow() - timedelta(days=older_than_days)

    return (
        db.query(PipelineArtifact)
        .filter(
            PipelineArtifact.retention_policy == retention_policy,
            PipelineArtifact.status == ArtifactStatus.ACTIVE,
            PipelineArtifact.created_at < cutoff_date,
        )
        .all()
    )


def get_artifact_summary_for_run(
    db: Session,
    pipeline_run_id: UUID,
) -> Dict[str, Any]:
    """Get artifact summary for a pipeline run (for lightweight metadata in pipeline_runs.metrics).

    Returns lightweight summary for pipeline_runs.metrics JSON field.

    Args:
        db: Database session
        pipeline_run_id: Pipeline run ID

    Returns:
        Dictionary with artifact summary
    """
    artifacts = (
        db.query(PipelineArtifact)
        .filter(
            PipelineArtifact.pipeline_run_id == pipeline_run_id,
            PipelineArtifact.status != ArtifactStatus.PURGED,
        )
        .all()
    )

    summary = {
        "total_artifacts": len(artifacts),
        "total_size_bytes": sum(a.file_size for a in artifacts),
        "by_stage": {},
        "by_type": {},
    }

    for artifact in artifacts:
        # By stage
        if artifact.stage_name not in summary["by_stage"]:
            summary["by_stage"][artifact.stage_name] = {
                "count": 0,
                "total_size_bytes": 0,
                "artifacts": [],
            }

        summary["by_stage"][artifact.stage_name]["count"] += 1
        summary["by_stage"][artifact.stage_name]["total_size_bytes"] += artifact.file_size
        summary["by_stage"][artifact.stage_name]["artifacts"].append(
            {
                "id": str(artifact.id),
                "name": artifact.artifact_name,
                "type": artifact.artifact_type.value,
                "size_bytes": artifact.file_size,
                "storage_key": artifact.storage_key,
            }
        )

        # By type
        type_key = artifact.artifact_type.value
        if type_key not in summary["by_type"]:
            summary["by_type"][type_key] = {"count": 0, "total_size_bytes": 0}
        summary["by_type"][type_key]["count"] += 1
        summary["by_type"][type_key]["total_size_bytes"] += artifact.file_size

    return summary
