"""
Pipeline API endpoints for PrimeData.

This module provides REST API endpoints for managing data processing pipelines,
including triggering pipeline runs and monitoring their status.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from primedata.api.billing import check_billing_limits
from primedata.core.embedding_workspace import validate_embedding_config_for_workspace
from primedata.core.plan_limits import get_plan_limit
from primedata.core.scope import allowed_workspaces, ensure_product_access
from primedata.core.security import get_current_user
from primedata.core.settings import get_settings
from primedata.db.database import get_db
from primedata.db.models import ArtifactStatus, BillingProfile, PipelineArtifact, PipelineRun, PipelineRunStatus, Product, RawFile, RawFileStatus
from primedata.storage.minio_client import minio_client
from pydantic import BaseModel, ConfigDict
from sqlalchemy import and_, func
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/pipeline", tags=["Pipeline"])


class PipelineRunRequest(BaseModel):
    """Request model for triggering a pipeline run."""

    product_id: UUID
    version: Optional[int] = None
    force_run: Optional[bool] = False


class PipelineRunResponse(BaseModel):
    """Response model for pipeline run information."""

    model_config = ConfigDict(from_attributes=True)  # Pydantic v2 syntax

    id: UUID
    product_id: UUID
    version: int
    status: str
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    dag_run_id: Optional[str]
    metrics: Dict[str, Any]
    created_at: datetime


class TriggerPipelineResponse(BaseModel):
    """Response model for pipeline trigger."""

    product_id: UUID
    version: int
    run_id: UUID
    status: str
    message: str


@router.post("/run", response_model=TriggerPipelineResponse)
async def trigger_pipeline(
    request: PipelineRunRequest,
    request_obj: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Trigger a pipeline run for a product.

    **Version Management**:
    - Each pipeline run gets a unique version number, independent of raw file version
    - Pipeline run versions increment sequentially (1, 2, 3, ...) for each product
    - Raw file version is stored separately in metrics for traceability
    - Even if a previous run failed, a new run will get a new version number

    **Smart Version Resolution (Enterprise Best Practice)**:
    - If `version` is explicitly provided: Validates that raw files exist for that version
    - If `version` is `None`: Automatically uses the latest ingested version that has raw files

    This ensures seamless workflow: users can simply click "Run Pipeline" without
    manual version coordination. The system automatically processes the latest available data.

    **Examples**:
    - Auto-detect: `{"product_id": "...", "version": null}` → Uses latest ingested version
    - Explicit: `{"product_id": "...", "version": 3}` → Processes version 3 (validates files exist)
    """
    # Ensure user has access to the product
    ensure_product_access(db, request_obj, request.product_id)

    # Get the product
    product = db.query(Product).filter(Product.id == request.product_id).first()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    if getattr(product, "vector_creation_enabled", True):
        validate_embedding_config_for_workspace(db, product.workspace_id, product.embedding_config)

    # Check pipeline runs limit for current month
    billing_profile = db.query(BillingProfile).filter(
        BillingProfile.workspace_id == product.workspace_id
    ).first()

    if billing_profile:
        plan_name = billing_profile.plan.value.lower() if hasattr(billing_profile.plan, "value") else str(billing_profile.plan).lower()
        max_runs = get_plan_limit(plan_name, "max_pipeline_runs_per_month")
        
        if max_runs != -1:  # If not unlimited
            # Count pipeline runs in current month
            now = datetime.now(timezone.utc)
            month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
            current_month_runs = (
                db.query(func.count(PipelineRun.id))
                .filter(
                    and_(
                        PipelineRun.workspace_id == product.workspace_id,
                        PipelineRun.started_at >= month_start
                    )
                )
                .scalar() or 0
            )
            
            if current_month_runs >= max_runs:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Pipeline runs limit exceeded. You have used {current_month_runs} of {max_runs} runs this month. "
                           f"Please upgrade your plan or wait until next month."
                )

    # Option C: Smart Version Resolution (Enterprise Best Practice)
    # If version is explicitly provided, validate it exists
    # If version is None, auto-detect latest ingested version
    # This determines which raw file version to process (separate from pipeline run version)
    if request.version is not None:
        # Explicit version provided - validate raw files exist
        # Include PROCESSED files to allow reprocessing with new configurations
        raw_file_version = request.version
        raw_file_count = (
            db.query(RawFile)
            .filter(
                RawFile.product_id == product.id,
                RawFile.version == raw_file_version,
                RawFile.status.in_(
                    [RawFileStatus.INGESTED, RawFileStatus.FAILED, RawFileStatus.PROCESSING, RawFileStatus.PROCESSED]
                ),
            )
            .count()
        )

        if raw_file_count == 0:
            # Provide helpful error message with available versions
            latest_version = (
                db.query(func.max(RawFile.version))
                .filter(RawFile.product_id == product.id, RawFile.status != RawFileStatus.DELETED)
                .scalar()
            )

            # Get all available versions
            available_versions = (
                db.query(RawFile.version)
                .filter(RawFile.product_id == product.id, RawFile.status != RawFileStatus.DELETED)
                .distinct()
                .order_by(RawFile.version.desc())
                .all()
            )

            available_versions_list = [v[0] for v in available_versions] if available_versions else []

            error_detail = {
                "message": f"No raw files found for version {raw_file_version}",
                "requested_version": raw_file_version,
                "latest_ingested_version": latest_version,
                "available_versions": available_versions_list,
                "suggestion": (
                    f"Please run initial ingestion for version {raw_file_version}, "
                    f"or use version={latest_version} to process latest ingested data"
                    if latest_version
                    else "Please run initial ingestion first"
                ),
            }

            logger.warning(
                f"Pipeline trigger failed: No raw files for product {product.id}, version {raw_file_version}. "
                f"Available versions: {available_versions_list}"
            )

            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error_detail)

        logger.info(f"Using explicit raw file version {raw_file_version} (validated: {raw_file_count} raw files found)")
    else:
        # Auto-detect: Pick the latest raw file version regardless of status (except DELETED)
        # This allows retrying failed pipelines easily - picks latest version with any status
        latest_raw_file = (
            db.query(RawFile)
            .filter(RawFile.product_id == product.id, RawFile.status != RawFileStatus.DELETED)
            .order_by(RawFile.version.desc())
            .first()
        )

        if not latest_raw_file:
            error_detail = {
                "message": "No raw files found for this product",
                "suggestion": "Please run initial ingestion first to upload data",
            }
            logger.warning(f"Pipeline trigger failed: No raw files for product {product.id}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_detail)

        raw_file_version = latest_raw_file.version
        logger.info(
            f"Auto-detected latest raw file version: {raw_file_version} "
            f"(status: {latest_raw_file.status.value}, filename: {latest_raw_file.filename})"
        )

    # ALWAYS create a new pipeline run version number (independent of raw file version)
    # Get the maximum existing pipeline run version for this product
    max_pipeline_run_version = (
        db.query(func.max(PipelineRun.version))
        .filter(PipelineRun.product_id == request.product_id)
        .scalar()
    ) or 0
    
    # Increment to get the next pipeline run version
    pipeline_run_version = max_pipeline_run_version + 1
    
    logger.info(
        f"Creating new pipeline run version {pipeline_run_version} "
        f"(processing raw files from version {raw_file_version})"
    )

    # Check if there's already a running pipeline (regardless of version)
    # Only block if there's a QUEUED or RUNNING pipeline for this product
    existing_running_run = (
        db.query(PipelineRun)
        .filter(
            PipelineRun.product_id == request.product_id,
            PipelineRun.status.in_([PipelineRunStatus.QUEUED, PipelineRunStatus.RUNNING]),
        )
        .first()
    )

    if existing_running_run:
        # Check if user wants to force run (override existing)
        force_run = request.force_run

        if not force_run:
            # Provide helpful error message with details about existing run
            status_msg = existing_running_run.status.value.lower()
            started_msg = ""
            if existing_running_run.started_at:
                now = datetime.now(timezone.utc)
                elapsed = now - existing_running_run.started_at.replace(tzinfo=timezone.utc)
                started_msg = f" (running for {int(elapsed.total_seconds() / 60)} minutes)"

            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": f"A pipeline run is already {status_msg} for this product (version {existing_running_run.version}){started_msg}",
                    "existing_run_id": str(existing_running_run.id),
                    "existing_status": existing_running_run.status.value,
                    "existing_started_at": existing_running_run.started_at.isoformat() if existing_running_run.started_at else None,
                    "suggestion": "You can force run to cancel the existing run and start a new one, or wait for the current run to complete.",
                },
            )
        else:
            # Cancel existing run and start new one
            logger.info(f"Cancelling existing pipeline run {existing_running_run.id} to start new run")
            existing_running_run.status = PipelineRunStatus.FAILED
            existing_running_run.finished_at = datetime.utcnow()
            existing_running_run.metrics = existing_running_run.metrics or {}
            existing_running_run.metrics["cancelled_reason"] = "Replaced by new pipeline run"
            db.commit()

    # Check if we're reprocessing already-processed files - if so, create a new version
    # Only do this if version was auto-detected (not explicitly provided)
    if request.version is None:
        # First, check if there are any existing raw files for this version that might be missing files in MinIO
        existing_files_for_version = (
            db.query(RawFile)
            .filter(
                RawFile.product_id == request.product_id,
                RawFile.version == raw_file_version,
                RawFile.status.in_([RawFileStatus.FAILED, RawFileStatus.INGESTED, RawFileStatus.PROCESSING]),
            )
            .all()
        )

        # Check if any of these files are missing in MinIO and need to be copied from previous version
        if existing_files_for_version:
            from primedata.storage.minio_client import minio_client as minio_client_instance

            files_need_copy = []

            for existing_file in existing_files_for_version:
                if not minio_client_instance.object_exists(existing_file.storage_bucket, existing_file.storage_key):
                    # File doesn't exist, need to find the original source file from previous version
                    # Find the original PROCESSED file from previous versions
                    original_file = (
                        db.query(RawFile)
                        .filter(
                            RawFile.product_id == request.product_id,
                            RawFile.filename == existing_file.filename,
                            RawFile.status == RawFileStatus.PROCESSED,
                        )
                        .order_by(RawFile.version.desc())
                        .first()
                    )

                    if original_file and minio_client_instance.object_exists(
                        original_file.storage_bucket, original_file.storage_key
                    ):
                        # Copy from original location
                        logger.info(
                            f"Copying missing file from original version: {original_file.storage_key} to {existing_file.storage_key}"
                        )
                        copy_success = minio_client_instance.copy_object(
                            source_bucket=original_file.storage_bucket,
                            source_key=original_file.storage_key,
                            dest_bucket=existing_file.storage_bucket,
                            dest_key=existing_file.storage_key,
                        )

                        if copy_success:
                            # Verify copy succeeded
                            if minio_client_instance.object_exists(existing_file.storage_bucket, existing_file.storage_key):
                                existing_file.status = RawFileStatus.INGESTED
                                existing_file.error_message = None
                                logger.info(f"Successfully copied file and updated status for {existing_file.filename}")
                            else:
                                logger.error(f"Copy verification failed for {existing_file.filename}")
                        else:
                            logger.error(f"Failed to copy file for {existing_file.filename}")
                    else:
                        logger.warning(f"Cannot find source file to copy for {existing_file.filename}")

            if existing_files_for_version:
                db.commit()

        # Now check for PROCESSED files to create a new version from
        processed_files_to_reprocess = (
            db.query(RawFile)
            .filter(
                RawFile.product_id == request.product_id, RawFile.version == raw_file_version, RawFile.status == RawFileStatus.PROCESSED
            )
            .all()
        )

        if processed_files_to_reprocess:
            # We're reprocessing - create a new raw file version by incrementing
            # Get the maximum raw file version number for this product
            max_raw_file_version = db.query(func.max(RawFile.version)).filter(RawFile.product_id == request.product_id).scalar() or 0

            new_raw_file_version = max_raw_file_version + 1
            logger.info(
                f"Reprocessing {len(processed_files_to_reprocess)} PROCESSED files from raw file version {raw_file_version} "
                f"to new raw file version {new_raw_file_version} with new configuration"
            )

            # Create new raw file records with the new version (copy the old ones)
            import uuid as uuid_lib

            from primedata.storage.minio_client import minio_client as minio_client_instance
            from primedata.storage.paths import raw_prefix

            for old_raw_file in processed_files_to_reprocess:
                # Update storage_key to use the new version number
                # Extract just the filename from the old storage_key
                # Old format: ws/{ws}/prod/{prod}/v/{old_version}/raw/{filename}
                # New format: ws/{ws}/prod/{prod}/v/{new_raw_file_version}/raw/{filename}
                old_key_parts = old_raw_file.storage_key.split("/")
                filename = old_key_parts[-1]  # Get the filename
                new_storage_key = f"{raw_prefix(old_raw_file.workspace_id, old_raw_file.product_id, new_raw_file_version)}{filename}"

                # Verify source file exists before copying
                source_exists = minio_client_instance.object_exists(old_raw_file.storage_bucket, old_raw_file.storage_key)

                if not source_exists:
                    logger.error(f"Source file does not exist in storage: {old_raw_file.storage_key}")
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"Source file {old_raw_file.filename} not found in storage at {old_raw_file.storage_key}. Cannot reprocess.",
                    )

                # Check if destination already exists (shouldn't happen, but be safe)
                dest_exists = minio_client_instance.object_exists(old_raw_file.storage_bucket, new_storage_key)
                if dest_exists:
                    logger.info(f"Destination file already exists in storage: {new_storage_key}, skipping copy")
                else:
                    # Copy the file in storage from old version path to new version path
                    logger.info(f"Copying file from {old_raw_file.storage_key} to {new_storage_key}")
                    copy_success = minio_client_instance.copy_object(
                        source_bucket=old_raw_file.storage_bucket,
                        source_key=old_raw_file.storage_key,
                        dest_bucket=old_raw_file.storage_bucket,
                        dest_key=new_storage_key,
                    )

                    if not copy_success:
                        logger.error(f"Failed to copy file from {old_raw_file.storage_key} to {new_storage_key}")
                        raise HTTPException(
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Failed to copy file {old_raw_file.filename} to new version path",
                        )

                    # Verify the copy succeeded
                    verify_exists = minio_client_instance.object_exists(old_raw_file.storage_bucket, new_storage_key)
                    if not verify_exists:
                        logger.error(f"Copy verification failed: file does not exist at {new_storage_key} after copy")
                        raise HTTPException(
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"File copy verification failed for {old_raw_file.filename}",
                        )

                new_raw_file = RawFile(
                    id=uuid_lib.uuid4(),
                    workspace_id=old_raw_file.workspace_id,
                    product_id=old_raw_file.product_id,
                    data_source_id=old_raw_file.data_source_id,
                    version=new_raw_file_version,
                    filename=old_raw_file.filename,
                    file_stem=old_raw_file.file_stem,
                    storage_key=new_storage_key,  # Use new version in the key
                    storage_bucket=old_raw_file.storage_bucket,
                    file_size=old_raw_file.file_size,
                    content_type=old_raw_file.content_type,
                    status=RawFileStatus.INGESTED,  # Start as INGESTED for reprocessing
                    file_checksum=old_raw_file.file_checksum,
                    storage_etag=old_raw_file.storage_etag,
                    ingested_at=datetime.utcnow(),
                    processed_at=None,
                    error_message=None,
                )
                db.add(new_raw_file)
                logger.info(f"Copied file {old_raw_file.filename} from raw file v{raw_file_version} to raw file v{new_raw_file_version} in MinIO")

            raw_file_version = new_raw_file_version  # Update to use the new raw file version
            db.commit()
            logger.info(f"Created new raw file version {raw_file_version} for reprocessing")

    try:
        # Create pipeline run record with the NEW pipeline run version
        # Store raw file version in metrics for traceability
        from primedata.services.s3_content_storage import get_pipeline_run_metrics_path
        
        # Create pipeline run
        pipeline_run = PipelineRun(
            workspace_id=product.workspace_id,
            product_id=request.product_id,
            version=pipeline_run_version,  # Use the new unique pipeline run version
            status=PipelineRunStatus.QUEUED,
            started_at=datetime.now(timezone.utc),  # Explicitly set started_at with timezone
            metrics={
                "raw_file_version": raw_file_version,  # Store the raw file version in metrics for reference
            },
            metrics_path="",  # Temporary, will be set after creation
        )
        db.add(pipeline_run)
        db.flush()  # Flush to get the ID
        
        # Set metrics_path with actual pipeline run ID
        metrics_path = get_pipeline_run_metrics_path(
            product.workspace_id,
            product.id,
            pipeline_run_version,
            pipeline_run.id,
        )
        pipeline_run.metrics_path = metrics_path
        
        # Save initial metrics to S3
        from primedata.storage.minio_client import MinIOClient
        minio_client = MinIOClient()
        initial_metrics = {
            "raw_file_version": raw_file_version,
            "aird_stages": {},
            "aird_stages_completed": [],
        }
        if minio_client.put_json("primedata-exports", metrics_path, initial_metrics):
            # Store small summary in DB
            pipeline_run.metrics = {
                "raw_file_version": raw_file_version,
                "total_stages": 0,
                "completed_stages": 0,
            }
        else:
            # Fallback: keep full metrics in DB
            pipeline_run.metrics = initial_metrics
        
        db.commit()
        db.refresh(pipeline_run)

        # Refresh product from database to ensure we have latest configuration
        db.refresh(product)

        # Get chunking and embedding configuration from product (after refresh)
        chunking_config = product.chunking_config or {}
        embedding_config = product.embedding_config or {}

        # Log the configuration being passed to Airflow for verification
        logger.info(
            f"Triggering pipeline for product {request.product_id}:\n"
            f"  pipeline_run_version: {pipeline_run_version}\n"
            f"  raw_file_version: {raw_file_version}\n"
            f"  chunking_config: {chunking_config}\n"
            f"  embedding_config: {embedding_config}\n"
            f"  playbook_id: {product.playbook_id}"
        )

        # Trigger Airflow DAG with configuration
        # Pass raw_file_version to Airflow, but pipeline_run will have its own version
        dag_run_id = await _trigger_airflow_dag(
            workspace_id=product.workspace_id,
            product_id=request.product_id,
            version=raw_file_version,  # Airflow processes raw files from this version
            pipeline_run_id=pipeline_run.id,
            chunking_config=chunking_config,
            embedding_config=embedding_config,
            playbook_id=product.playbook_id,
        )

        # Update pipeline run with DAG run ID
        pipeline_run.dag_run_id = dag_run_id
        pipeline_run.status = PipelineRunStatus.RUNNING
        pipeline_run.started_at = datetime.utcnow()
        db.commit()

        # Create informative message
        version_source = "explicitly provided" if request.version is not None else "auto-detected (latest ingested)"
        message = (
            f"Pipeline run version {pipeline_run_version} triggered successfully "
            f"(processing raw files from version {raw_file_version}, {version_source}). "
            f"DAG Run ID: {dag_run_id}"
        )

        logger.info(
            f"Triggered pipeline run {pipeline_run.id} for product {request.product_id} "
            f"(pipeline_run_version: {pipeline_run_version}, raw_file_version: {raw_file_version}, {version_source})"
        )

        return TriggerPipelineResponse(
            product_id=request.product_id,
            version=pipeline_run_version,  # Return the pipeline run version
            run_id=pipeline_run.id,
            status=pipeline_run.status.value,
            message=message,
        )

    except Exception as e:
        logger.error(f"Failed to trigger pipeline for product {request.product_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to trigger pipeline: {str(e)}")


@router.get("/runs")
async def list_pipeline_runs(
    product_id: UUID,
    request_obj: Request,
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    sync: bool = Query(True, description="Sync with Airflow before returning"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    List pipeline runs for a product with pagination support.
    """
    # Ensure user has access to the product
    product = ensure_product_access(db, request_obj, product_id)

    # Sync with Airflow if requested
    if sync:
        _sync_pipeline_runs_with_airflow(db)

    # Get pipeline runs - filter by product_id AND workspace_id for security
    # This ensures users can only see pipeline runs for products in their workspaces
    allowed_workspace_ids = allowed_workspaces(request_obj, db)
    
    # Get total count for pagination
    total_count = (
        db.query(func.count(PipelineRun.id))
        .join(Product, PipelineRun.product_id == Product.id)
        .filter(PipelineRun.product_id == product_id, Product.workspace_id.in_(allowed_workspace_ids))
        .scalar()
    )
    
    runs = (
        db.query(PipelineRun)
        .join(Product, PipelineRun.product_id == Product.id)
        .filter(PipelineRun.product_id == product_id, Product.workspace_id.in_(allowed_workspace_ids))
        .order_by(PipelineRun.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    # Lazy-load metrics from S3 if archived
    from primedata.services.lazy_json_loader import load_pipeline_run_metrics

    return {
        "runs": [
            PipelineRunResponse(
                id=run.id,
                product_id=run.product_id,
                version=run.version,
                status=run.status.value,
                started_at=run.started_at,
                finished_at=run.finished_at,
                dag_run_id=run.dag_run_id,
                metrics=load_pipeline_run_metrics(run),
                created_at=run.created_at,
            )
            for run in runs
        ],
        "total": total_count,
        "limit": limit,
        "offset": offset,
    }


@router.get("/runs/{run_id}", response_model=PipelineRunResponse)
async def get_pipeline_run(
    run_id: UUID, request_obj: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)
):
    """
    Get details of a specific pipeline run.
    """
    # Get pipeline run
    run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline run not found")

    # Ensure user has access to the product
    ensure_product_access(db, request_obj, run.product_id)

    # Lazy-load metrics from S3 if archived
    from primedata.services.lazy_json_loader import load_pipeline_run_metrics

    metrics = load_pipeline_run_metrics(run)

    return PipelineRunResponse(
        id=run.id,
        product_id=run.product_id,
        version=run.version,
        status=run.status.value,
        started_at=run.started_at,
        finished_at=run.finished_at,
        dag_run_id=run.dag_run_id,
        metrics=metrics,
        created_at=run.created_at,
    )


class PipelineRunUpdateRequest(BaseModel):
    """Request model for updating a pipeline run."""

    status: Optional[str] = None
    finished_at: Optional[str] = None
    metrics: Optional[Dict[str, Any]] = None


@router.patch("/runs/{run_id}")
async def update_pipeline_run(
    run_id: UUID,
    request_body: PipelineRunUpdateRequest,
    request_obj: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Update a pipeline run status (used by Airflow DAG or for manual cancellation).
    """
    run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline run not found")

    # Ensure user has access to the product
    ensure_product_access(db, request_obj, run.product_id)

    # Update fields if provided
    if request_body.status is not None:
        try:
            new_status = PipelineRunStatus(request_body.status)
            # If cancelling a running/queued pipeline, mark it as failed
            if new_status == PipelineRunStatus.FAILED and run.status in [PipelineRunStatus.RUNNING, PipelineRunStatus.QUEUED]:
                logger.info(f"Cancelling pipeline run {run_id} (was {run.status.value})")
                
                # Cancel the DAG run in Airflow if dag_run_id exists
                if run.dag_run_id:
                    try:
                        import requests
                        from requests.auth import HTTPBasicAuth
                        
                        # Use Settings for Airflow configuration (loads from .env.local, .env, or environment variables)
                        settings = get_settings()
                        airflow_url = settings.AIRFLOW_URL
                        airflow_username = settings.AIRFLOW_USERNAME
                        airflow_password = settings.AIRFLOW_PASSWORD
                        
                        if not airflow_username:
                            logger.error("AIRFLOW_USERNAME environment variable must be set")
                            raise ValueError("AIRFLOW_USERNAME environment variable must be set")
                        if not airflow_password:
                            logger.error("AIRFLOW_PASSWORD environment variable must be set")
                            raise ValueError("AIRFLOW_PASSWORD environment variable must be set")
                        
                        dag_id = "data_ingestion_pipeline"
                        # Use PATCH to update DAG run state to failed (stops execution)
                        cancel_url = f"{airflow_url}/api/v1/dags/{dag_id}/dagRuns/{run.dag_run_id}"
                        
                        cancel_response = requests.patch(
                            cancel_url,
                            json={"state": "failed"},
                            auth=HTTPBasicAuth(airflow_username, airflow_password),
                            timeout=10,
                        )
                        
                        if cancel_response.status_code == 200:
                            logger.info(f"Successfully cancelled DAG run {run.dag_run_id} in Airflow")
                        else:
                            logger.warning(f"Failed to cancel DAG run in Airflow: {cancel_response.status_code} - {cancel_response.text}")
                    except Exception as e:
                        logger.warning(f"Failed to cancel DAG run in Airflow (continuing with DB update): {e}")
                
                run.status = PipelineRunStatus.FAILED
                run.finished_at = datetime.utcnow()
                if not run.metrics:
                    run.metrics = {}
                run.metrics["cancelled_reason"] = "Manually cancelled by user"
            else:
                run.status = new_status
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid status: {request_body.status}")

    if request_body.finished_at is not None:
        try:
            run.finished_at = datetime.fromisoformat(request_body.finished_at.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid finished_at format: {request_body.finished_at}"
            )

    if request_body.metrics is not None:
        from primedata.services.lazy_json_loader import load_pipeline_run_metrics
        from primedata.storage.minio_client import MinIOClient
        
        # Load current metrics from S3 or DB
        current_metrics = load_pipeline_run_metrics(run)
        if not current_metrics:
            current_metrics = {}
        
        # Update metrics
        current_metrics.update(request_body.metrics)
        
        # Save to S3
        if not run.metrics_path:
            from primedata.services.s3_content_storage import get_pipeline_run_metrics_path
            run.metrics_path = get_pipeline_run_metrics_path(
                run.workspace_id,
                run.product_id,
                run.version,
                run.id,
            )
        
        minio_client = MinIOClient()
        if minio_client.put_json("primedata-exports", run.metrics_path, current_metrics):
            # Store small summary in DB
            run.metrics = {
                "total_stages": len(current_metrics.get("aird_stages", {})),
                "completed_stages": len(current_metrics.get("aird_stages_completed", [])),
            }
        else:
            # Fallback: keep in DB
            run.metrics = current_metrics

    db.commit()
    db.refresh(run)

    logger.info(f"Updated pipeline run {run_id} to status {run.status.value}")

    # Lazy-load metrics from S3 if archived
    from primedata.services.lazy_json_loader import load_pipeline_run_metrics

    metrics = load_pipeline_run_metrics(run)

    return PipelineRunResponse(
        id=run.id,
        product_id=run.product_id,
        version=run.version,
        status=run.status.value,
        started_at=run.started_at,
        finished_at=run.finished_at,
        dag_run_id=run.dag_run_id,
        metrics=metrics,
        created_at=run.created_at,
    )


@router.post("/sync")
async def sync_pipeline_runs_with_airflow(
    request_obj: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)
):
    """
    Manually sync all running pipeline runs with Airflow status.
    """
    try:
        updated_count = _sync_pipeline_runs_with_airflow(db)
        return {"message": f"Successfully synced {updated_count} pipeline runs with Airflow", "updated_count": updated_count}
    except Exception as e:
        logger.error(f"Error in manual sync: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to sync with Airflow: {str(e)}")


@router.get("/status/{run_id}")
async def get_pipeline_status(
    run_id: UUID, request_obj: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)
):
    """
    Get the current status of a pipeline run.
    """
    # Get pipeline run
    run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline run not found")

    # Ensure user has access to the product
    ensure_product_access(db, request_obj, run.product_id)

    return {
        "run_id": str(run.id),
        "status": run.status.value,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "dag_run_id": run.dag_run_id,
        "metrics": run.metrics,
    }


@router.get("/runs/{run_id}/logs")
async def get_pipeline_run_logs(
    run_id: UUID,
    request_obj: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Get logs for a specific pipeline run.
    Fetches logs from Airflow in a secure, workspace-scoped manner.
    """
    # Get pipeline run
    run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline run not found")

    # Ensure user has access to the product (security check)
    ensure_product_access(db, request_obj, run.product_id)

    # Lazy-load metrics from S3 if archived (do this early so we always have stage metrics)
    from primedata.services.lazy_json_loader import load_pipeline_run_metrics

    metrics = load_pipeline_run_metrics(run)
    stage_metrics = metrics.get("aird_stages", {}) if metrics else {}

    if not run.dag_run_id:
        return {
            "run_id": str(run.id),
            "dag_run_id": None,
            "logs": {},
            "stage_metrics": stage_metrics,
            "metrics": metrics,  # Include full metrics object
            "message": "No DAG run ID available for this pipeline run",
        }

    # Fetch logs from Airflow
    # Get Airflow configuration from Settings (loads from .env.local, .env, or environment variables)
    settings = get_settings()
    airflow_url = settings.AIRFLOW_URL
    airflow_username = settings.AIRFLOW_USERNAME
    airflow_password = settings.AIRFLOW_PASSWORD
    
    if not airflow_username:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AIRFLOW_USERNAME environment variable must be set",
        )
    if not airflow_password:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AIRFLOW_PASSWORD environment variable must be set",
        )

    try:
        import requests
        from requests.auth import HTTPBasicAuth

        # Get DAG run details
        dag_run_url = f"{airflow_url}/api/v1/dags/data_ingestion_pipeline/dagRuns/{run.dag_run_id}"
        dag_run_response = requests.get(
            dag_run_url,
            auth=HTTPBasicAuth(airflow_username, airflow_password),
            timeout=10,
        )

        if dag_run_response.status_code != 200:
            logger.warning(f"Failed to get DAG run details: {dag_run_response.status_code}")
            # Return stage metrics even if Airflow is unavailable
            return {
                "run_id": str(run.id),
                "dag_run_id": run.dag_run_id,
                "logs": {},
                "stage_metrics": stage_metrics,
                "metrics": metrics,  # Include full metrics object
                "error": "Failed to fetch logs from Airflow",
            }

        dag_run_data = dag_run_response.json()

        # Get task instances for this DAG run
        task_instances_url = f"{airflow_url}/api/v1/dags/data_ingestion_pipeline/dagRuns/{run.dag_run_id}/taskInstances"
        task_instances_response = requests.get(
            task_instances_url,
            auth=HTTPBasicAuth(airflow_username, airflow_password),
            timeout=10,
        )

        logs = {}
        if task_instances_response.status_code == 200:
            task_instances = task_instances_response.json().get("task_instances", [])

            for task_instance in task_instances:
                task_id = task_instance.get("task_id")
                if not task_id:
                    continue

                # Get logs for this task
                # Airflow logs API returns plain text, not JSON
                log_url = f"{airflow_url}/api/v1/dags/data_ingestion_pipeline/dagRuns/{run.dag_run_id}/taskInstances/{task_id}/logs/1"
                log_response = requests.get(
                    log_url,
                    auth=HTTPBasicAuth(airflow_username, airflow_password),
                    timeout=10,
                )

                if log_response.status_code == 200:
                    # Airflow returns logs as plain text, not JSON
                    log_content = log_response.text
                    logs[task_id] = {
                        "content": log_content,
                        "status": task_instance.get("state", "unknown"),
                        "start_date": task_instance.get("start_date"),
                        "end_date": task_instance.get("end_date"),
                    }
                else:
                    logs[task_id] = {
                        "content": "",
                        "status": task_instance.get("state", "unknown"),
                        "error": f"Failed to fetch logs: {log_response.status_code}",
                    }

        return {
            "run_id": str(run.id),
            "dag_run_id": run.dag_run_id,
            "dag_run_state": dag_run_data.get("state", "unknown"),
            "logs": logs,
            "stage_metrics": stage_metrics,
            "metrics": metrics,  # Include full metrics object for cancelled_reason and other metadata
        }

    except Exception as e:
        logger.error(f"Error fetching logs from Airflow: {e}", exc_info=True)
        # Return stage metrics even if Airflow fetch fails
        return {
            "run_id": str(run.id),
            "dag_run_id": run.dag_run_id,
            "logs": {},
            "stage_metrics": stage_metrics,
            "metrics": metrics,  # Include full metrics object
            "error": f"Failed to fetch logs: {str(e)}",
        }


@router.get("/runs/{run_id}/chunking-config")
async def get_pipeline_chunking_config(
    run_id: UUID,
    request_obj: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Get chunking configuration for a pipeline run from stored metrics.
    Returns resolved_settings that were used during preprocessing.
    """
    run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline run not found")
    
    ensure_product_access(db, request_obj, run.product_id)
    
    # Load metrics (handles S3 archival)
    from primedata.services.lazy_json_loader import load_pipeline_run_metrics
    metrics = load_pipeline_run_metrics(run)
    
    chunking_config = metrics.get("chunking_config", {})
    resolved_settings = chunking_config.get("resolved_settings")
    
    return {
        "resolved_settings": resolved_settings,
        "timestamp": chunking_config.get("timestamp"),
        "version": chunking_config.get("version")
    }


class PipelineArtifactResponse(BaseModel):
    """Response model for pipeline artifact information."""

    id: str
    stage_name: str
    artifact_name: str
    artifact_type: str
    file_size: int
    created_at: str
    download_url: Optional[str] = None
    display_name: Optional[str] = None
    description: Optional[str] = None


@router.get("/artifacts")
async def get_pipeline_artifacts(
    product_id: UUID,
    version: Optional[int] = Query(None, description="Version number (defaults to latest)"),
    pipeline_run_id: Optional[UUID] = Query(None, description="Pipeline run ID (optional, for more specific query)"),
    request_obj: Request = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Get pipeline artifacts for a product and version.
    Returns artifacts grouped by stage from successful pipeline runs.
    
    If pipeline_run_id is provided, queries artifacts for that specific run.
    Otherwise, queries by product_id and version.
    """
    # Ensure user has access to the product
    product = ensure_product_access(db, request_obj, product_id)

    # Determine version
    # Use promoted_version if available (actual production), otherwise current_version (latest)
    if version is None:
        version = product.promoted_version if product.promoted_version is not None else product.current_version

    # Build query - prefer pipeline_run_id if provided, otherwise use product_id + version
    query = db.query(PipelineArtifact).filter(
        PipelineArtifact.status == ArtifactStatus.ACTIVE,  # Only show active artifacts
    )
    
    if pipeline_run_id:
        # Query by specific pipeline run (most reliable)
        query = query.filter(PipelineArtifact.pipeline_run_id == pipeline_run_id)
        logger.info(f"Querying artifacts by pipeline_run_id={pipeline_run_id}")
    else:
        # Query by product_id and version
        query = query.filter(
            PipelineArtifact.product_id == product_id,
            PipelineArtifact.version == version,
        )
        logger.info(f"Querying artifacts by product_id={product_id}, version={version}")

    # Get artifacts
    artifacts = query.order_by(PipelineArtifact.stage_name, PipelineArtifact.created_at.desc()).all()
    
    # Debug logging: Check what artifacts exist for this product
    if len(artifacts) == 0:
        # Log all artifacts for this product to debug
        all_artifacts = (
            db.query(PipelineArtifact)
            .filter(PipelineArtifact.product_id == product_id)
            .all()
        )
        logger.warning(
            f"No artifacts found for product_id={product_id}, version={version}, pipeline_run_id={pipeline_run_id}. "
            f"Total artifacts for product: {len(all_artifacts)}. "
            f"Versions found: {sorted(set(a.version for a in all_artifacts))} "
            f"Statuses found: {sorted(set(a.status.value for a in all_artifacts))}"
        )
    else:
        logger.info(f"Found {len(artifacts)} artifacts for product_id={product_id}, version={version}, pipeline_run_id={pipeline_run_id}")

    # Initialize Qdrant client for vector artifacts
    from primedata.indexing.qdrant_client import QdrantClient
    qdrant_client = QdrantClient()
    
    # Artifact display names mapping
    artifact_display_names = {
        "fingerprint": "AI Readiness Fingerprint",
        "trust_report": "AI Trust Report",
        "validation_summary": "Validation Summary",
        "processed_chunks": "Processed Chunks",
        "metrics": "Trust Metrics",
        "vectors": "Vector Index",
    }

    # Artifact descriptions
    artifact_descriptions = {
        "fingerprint": "AI readiness metrics and fingerprint data",
        "trust_report": "Comprehensive AI trust assessment report",
        "validation_summary": "AI validation results and compliance summary",
        "processed_chunks": "Cleaned and chunked document data",
        "metrics": "Trust scoring and quality metrics",
        "vectors": "Embedded vector index metadata",
    }

    result = []
    for artifact in artifacts:
        # Generate presigned URL for download (only for non-vector artifacts)
        download_url = None
        file_size = artifact.file_size
        
        # For vector artifacts, get size from Qdrant collection
        if artifact.artifact_type.value.lower() == 'vector':
            try:
                # Find collection name for this product/version
                collection_name = qdrant_client.find_collection_name(
                    workspace_id=str(product.workspace_id),
                    product_id=str(product.id),
                    version=version,
                    product_name=product.name,
                )
                
                if collection_name and qdrant_client.is_connected():
                    collection_info = qdrant_client.get_collection_info(collection_name)
                    if collection_info:
                        points_count = collection_info.get("points_count", 0)
                        vector_size = collection_info.get("config", {}).get("vector_size", 0)
                        # Estimate size: points_count * (vector_size * 4 bytes per float32 + payload overhead)
                        # Rough estimate: vector_size * 4 bytes per point + 1KB payload overhead per point
                        estimated_bytes = points_count * (vector_size * 4 + 1024)
                        file_size = estimated_bytes
                        logger.debug(f"Calculated vector artifact size: {estimated_bytes} bytes ({points_count} points, {vector_size} dims)")
            except Exception as e:
                logger.warning(f"Failed to get Qdrant collection size for vector artifact: {e}")
                # Keep original file_size if available
        else:
            # For non-vector artifacts, generate presigned URL
            # Skip artifacts that don't have files in storage
            if not artifact.storage_bucket or artifact.storage_bucket.lower() in ("none", "qdrant"):
                # These artifacts don't have physical files in MinIO/GCS
                # - "none": Metadata-only artifacts (e.g., policy evaluation results)
                # - "qdrant": Vector artifacts stored in Qdrant
                logger.debug(
                    f"Artifact {artifact.id} has storage_bucket='{artifact.storage_bucket}', "
                    f"skipping presigned URL generation (no file in storage)"
                )
                download_url = None
            elif not artifact.storage_key or artifact.storage_key.strip() == "":
                logger.warning(
                    f"Artifact {artifact.id} has invalid storage_key: '{artifact.storage_key}'. "
                    f"Skipping presigned URL generation."
                )
                download_url = None
            else:
                try:
                    # Generate download URL (attachment) for downloading files
                    download_url = minio_client.presign(
                        artifact.storage_bucket,
                        artifact.storage_key,
                        expiry=3600,  # 1 hour expiry
                        inline=False,  # Explicit for downloads
                    )
                    
                    # Validate the presigned URL
                    if download_url:
                        # Check if it's a valid signed URL (contains signature parameters)
                        if 'X-Goog-Signature' in download_url or 'Signature' in download_url or 'Expires' in download_url:
                            logger.debug(f"Generated valid presigned URL for artifact {artifact.id}")
                        else:
                            # If it's a direct GCS URL without signature, it won't work for private blobs
                            logger.warning(f"Presigned URL for artifact {artifact.id} doesn't contain signature parameters")
                            download_url = None
                    else:
                        logger.warning(
                            f"Failed to generate presigned URL for artifact {artifact.id} "
                            f"(bucket={artifact.storage_bucket}, key={artifact.storage_key[:50] if artifact.storage_key else 'None'}...)"
                        )
                except Exception as e:
                    # Log the full exception details to understand what's failing
                    error_type = type(e).__name__
                    error_msg = str(e)
                    logger.warning(
                        f"Failed to generate presigned URL for artifact {artifact.id}: {error_type}: {error_msg}. "
                        f"Bucket: '{artifact.storage_bucket}', Key: '{artifact.storage_key[:80] if artifact.storage_key else 'None'}...'",
                        exc_info=True
                    )
                    download_url = None

        # Get display name
        display_name = artifact_display_names.get(artifact.artifact_name, artifact.artifact_name.replace("_", " ").title())

        # Get description
        description = artifact_descriptions.get(artifact.artifact_name)

        result.append(
            PipelineArtifactResponse(
                id=str(artifact.id),
                stage_name=artifact.stage_name,
                artifact_name=artifact.artifact_name,
                artifact_type=artifact.artifact_type.value,
                file_size=file_size,  # Use calculated size for vectors
                created_at=artifact.created_at.isoformat() if artifact.created_at else "",
                download_url=download_url,  # Only set if presigned URL was successfully generated
                display_name=display_name,
                description=description,
            )
        )

    return {"artifacts": result, "total": len(result)}


@router.get("/artifacts/{artifact_id}/content")
async def get_artifact_content(
    artifact_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Get artifact content by ID. Acts as a proxy to avoid CORS issues.
    Returns the file content with proper content-type headers.
    """
    # Get the artifact
    artifact = db.query(PipelineArtifact).filter(PipelineArtifact.id == artifact_id).first()
    if not artifact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")
    
    # Ensure user has access to the product
    ensure_product_access(db, request, artifact.product_id)
    
    # Skip vector artifacts
    if artifact.artifact_type.value.lower() == 'vector':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vector artifacts cannot be viewed as files. Use the RAG Playground to query them."
        )
    
    # Handle metadata-only artifacts (e.g., policy evaluation results)
    # These artifacts have storage_bucket="none" and store data in artifact_metadata
    if not artifact.storage_bucket or artifact.storage_bucket.lower() == "none":
        logger.info(f"Artifact {artifact_id} is metadata-only, returning artifact_metadata as JSON")
        import json
        from fastapi.responses import Response
        
        # Return artifact metadata as JSON
        metadata_content = artifact.artifact_metadata or {}
        # Include additional artifact info for context
        response_data = {
            "artifact_id": str(artifact.id),
            "artifact_name": artifact.artifact_name,
            "artifact_type": artifact.artifact_type.value,
            "stage_name": artifact.stage_name,
            "version": artifact.version,
            "metadata": metadata_content,
        }
        
        json_content = json.dumps(response_data, indent=2, default=str)
        return Response(
            content=json_content.encode('utf-8'),
            media_type="application/json",
            headers={
                "Content-Disposition": "inline",
                "Cache-Control": "private, max-age=3600",
            }
        )
    
    # Check if artifact has storage info for file-based artifacts
    if not artifact.storage_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Artifact does not have storage information"
        )
    
    try:
        logger.info(f"Fetching artifact content: id={artifact_id}, bucket={artifact.storage_bucket}, key={artifact.storage_key}")
        # Fetch file content from storage
        file_content = minio_client.get_bytes(artifact.storage_bucket, artifact.storage_key)
        
        if not file_content:
            logger.error(f"Artifact file not found in storage: bucket={artifact.storage_bucket}, key={artifact.storage_key}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Artifact file not found in storage (bucket: {artifact.storage_bucket}, key: {artifact.storage_key})"
            )
        
        # Determine content type based on artifact type or file extension
        content_type = "application/octet-stream"
        if artifact.artifact_type.value.lower() == 'json':
            content_type = "application/json"
        elif artifact.artifact_type.value.lower() == 'csv':
            content_type = "text/csv"
        elif artifact.artifact_type.value.lower() == 'pdf':
            content_type = "application/pdf"
        elif artifact.artifact_type.value.lower() == 'jsonl':
            content_type = "application/x-ndjson"
        elif artifact.storage_key.endswith('.json'):
            content_type = "application/json"
        elif artifact.storage_key.endswith('.csv'):
            content_type = "text/csv"
        elif artifact.storage_key.endswith('.pdf'):
            content_type = "application/pdf"
        elif artifact.storage_key.endswith('.jsonl'):
            content_type = "application/x-ndjson"
        elif artifact.storage_key.endswith('.txt'):
            content_type = "text/plain"
        
        from fastapi.responses import Response
        return Response(
            content=file_content,
            media_type=content_type,
            headers={
                "Content-Disposition": "inline",
                "Cache-Control": "private, max-age=3600",
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch artifact content for {artifact_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch artifact content: {str(e)}"
        )


def _check_airflow_dag_run_status(
    airflow_url: str, airflow_username: str, airflow_password: str, dag_run_id: str
) -> Dict[str, Any]:
    """
    Check the status of a specific DAG run in Airflow.
    Returns the DAG run status and details.
    """
    try:
        import requests
        from requests.auth import HTTPBasicAuth

        # Get DAG run status from Airflow REST API
        dag_run_url = f"{airflow_url}/api/v1/dags/data_ingestion_pipeline/dagRuns/{dag_run_id}"

        response = requests.get(
            dag_run_url,
            auth=HTTPBasicAuth(airflow_username, airflow_password),
            headers={"Content-Type": "application/json"},
            timeout=30,
        )

        if response.status_code == 200:
            dag_run_data = response.json()
            return {
                "status": dag_run_data.get("state", "unknown"),
                "start_date": dag_run_data.get("start_date"),
                "end_date": dag_run_data.get("end_date"),
                "execution_date": dag_run_data.get("execution_date"),
                "dag_run_id": dag_run_data.get("dag_run_id"),
            }
        else:
            logger.error(f"Failed to get DAG run status: {response.status_code} - {response.text}")
            return {"status": "unknown", "error": f"HTTP {response.status_code}"}

    except Exception as e:
        logger.error(f"Error checking DAG run status: {e}")
        return {"status": "unknown", "error": str(e)}


def _sync_pipeline_runs_with_airflow(db: Session) -> int:
    """
    Sync running pipeline runs with Airflow status.
    Returns the number of runs updated.
    """
    try:
        # Get Airflow configuration from Settings (loads from .env.local, .env, or environment variables)
        settings = get_settings()
        airflow_url = settings.AIRFLOW_URL
        airflow_username = settings.AIRFLOW_USERNAME
        airflow_password = settings.AIRFLOW_PASSWORD
        
        if not airflow_username:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="AIRFLOW_USERNAME environment variable must be set",
            )
        if not airflow_password:
            logger.error("AIRFLOW_PASSWORD environment variable must be set")
            return  # Skip sync if password not configured

        # Get all running pipeline runs
        running_runs = (
            db.query(PipelineRun).filter(PipelineRun.status.in_([PipelineRunStatus.RUNNING, PipelineRunStatus.QUEUED])).all()
        )

        updated_count = 0

        for run in running_runs:
            if not run.dag_run_id:
                continue

            # Check Airflow status
            airflow_status = _check_airflow_dag_run_status(airflow_url, airflow_username, airflow_password, run.dag_run_id)

            if airflow_status.get("status") in ["success", "failed"]:
                # Update the pipeline run status
                if airflow_status["status"] == "success":
                    run.status = PipelineRunStatus.SUCCEEDED
                else:
                    run.status = PipelineRunStatus.FAILED

                # Update finished_at if available
                if airflow_status.get("end_date"):
                    try:
                        from datetime import datetime, timezone

                        run.finished_at = datetime.fromisoformat(airflow_status["end_date"].replace("Z", "+00:00"))
                    except ValueError:
                        run.finished_at = datetime.utcnow()
                else:
                    run.finished_at = datetime.utcnow()

                # Add some basic metrics
                if not run.metrics:
                    run.metrics = {}
                run.metrics["airflow_sync"] = True
                run.metrics["airflow_status"] = airflow_status["status"]

                updated_count += 1
                logger.info(f"Updated pipeline run {run.id} to status {run.status.value}")

        if updated_count > 0:
            db.commit()
            logger.info(f"Synced {updated_count} pipeline runs with Airflow")

        return updated_count

    except Exception as e:
        logger.error(f"Error syncing pipeline runs with Airflow: {e}")
        return 0


def _ensure_dag_unpaused(airflow_url: str, airflow_username: str, airflow_password: str, dag_id: str) -> bool:
    """
    Ensure a DAG is unpaused. Returns True if successful, False otherwise.
    """
    try:
        import requests
        from requests.auth import HTTPBasicAuth

        # Get DAG info
        dag_info_url = f"{airflow_url}/api/v1/dags/{dag_id}"
        dag_info_response = requests.get(
            dag_info_url,
            auth=HTTPBasicAuth(airflow_username, airflow_password),
            headers={"Content-Type": "application/json"},
            timeout=30,
        )

        if dag_info_response.status_code == 200:
            dag_info = dag_info_response.json()
            is_paused = dag_info.get("is_paused", True)

            if is_paused:
                logger.info(f"DAG {dag_id} is paused, attempting to unpause")
                unpause_data = {"is_paused": False}

                unpause_response = requests.patch(
                    dag_info_url,
                    json=unpause_data,
                    auth=HTTPBasicAuth(airflow_username, airflow_password),
                    headers={"Content-Type": "application/json"},
                    timeout=30,
                )

                if unpause_response.status_code == 200:
                    logger.info(f"Successfully unpaused DAG {dag_id}")
                    return True
                else:
                    logger.error(f"Failed to unpause DAG {dag_id}: {unpause_response.status_code} - {unpause_response.text}")
                    return False
            else:
                logger.info(f"DAG {dag_id} is already unpaused")
                return True
        elif dag_info_response.status_code == 404:
            logger.error(f"DAG {dag_id} not found in Airflow")
            return False
        else:
            logger.error(f"Failed to get DAG info for {dag_id}: {dag_info_response.status_code} - {dag_info_response.text}")
            return False

    except Exception as e:
        logger.error(f"Error checking/unpausing DAG {dag_id}: {e}")
        return False


async def _trigger_airflow_dag(
    workspace_id: UUID,
    product_id: UUID,
    version: int,
    pipeline_run_id: UUID,
    chunking_config: Dict[str, Any] = None,
    embedding_config: Dict[str, Any] = None,
    playbook_id: str = None,
) -> str:
    """
    Trigger Airflow DAG for pipeline execution.

    This function creates a trigger file that the Airflow scheduler can read
    to trigger the DAG with the appropriate parameters.

    Args:
        workspace_id: Workspace ID
        product_id: Product ID
        version: Version number
        pipeline_run_id: Pipeline run ID

    Returns:
        DAG run ID
    """
    try:
        # Generate DAG run ID
        dag_run_id = f"data_ingestion_pipeline_{pipeline_run_id}_{int(datetime.utcnow().timestamp())}"

        # Trigger DAG using Airflow REST API
        # Get Airflow configuration from Settings (loads from .env.local, .env, or environment variables)
        settings = get_settings()
        airflow_url = settings.AIRFLOW_URL
        airflow_username = settings.AIRFLOW_USERNAME
        airflow_password = settings.AIRFLOW_PASSWORD
        
        if not airflow_username:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="AIRFLOW_USERNAME environment variable must be set",
            )
        if not airflow_password:
            error_detail = {
                "message": "AIRFLOW_PASSWORD environment variable must be set",
                "suggestion": "Please set AIRFLOW_PASSWORD environment variable to authenticate with Airflow",
            }
            logger.error("Pipeline trigger failed: AIRFLOW_PASSWORD not set")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=error_detail)

        trigger_url = f"{airflow_url}/api/v1/dags/data_ingestion_pipeline/dagRuns"

        trigger_data = {
            "dag_run_id": dag_run_id,
            "conf": {
                "workspace_id": str(workspace_id),
                "product_id": str(product_id),
                "version": version,
                "pipeline_run_id": str(pipeline_run_id),
                "chunking_config": chunking_config or {},
                "embedding_config": embedding_config or {},
                "playbook_id": playbook_id,
            },
        }

        # Log the exact configuration being sent to Airflow
        logger.info(
            f"Sending to Airflow DAG:\n"
            f"  chunking_config: {json.dumps(chunking_config or {}, indent=2)}\n"
            f"  embedding_config: {json.dumps(embedding_config or {}, indent=2)}\n"
            f"  playbook_id: {playbook_id}"
        )

        try:
            import requests
            from requests.auth import HTTPBasicAuth

            # Ensure DAG is unpaused before triggering
            if not _ensure_dag_unpaused(airflow_url, airflow_username, airflow_password, "data_ingestion_pipeline"):
                raise Exception("Failed to ensure DAG is unpaused")

            # Now trigger the DAG run
            response = requests.post(
                trigger_url,
                json=trigger_data,
                auth=HTTPBasicAuth(airflow_username, airflow_password),
                headers={"Content-Type": "application/json"},
                timeout=30,
            )

            if response.status_code in [200, 201]:
                logger.info(f"Successfully triggered DAG run {dag_run_id} via REST API (status {response.status_code})")
            else:
                error_msg = f"Failed to trigger DAG run via REST API: {response.status_code} - {response.text}"
                logger.error(error_msg)
                raise Exception(error_msg)

        except Exception as e:
            logger.error(f"Error triggering DAG via REST API: {e}", exc_info=True)
            # Fallback to file-based trigger (use tmp directory that's writable)
            import tempfile

            trigger_dir = os.getenv("AIRFLOW_TRIGGER_DIR", os.path.join(tempfile.gettempdir(), "airflow_triggers"))

            try:
                os.makedirs(trigger_dir, exist_ok=True)
            except OSError as dir_error:
                logger.error(f"Failed to create trigger directory {trigger_dir}: {dir_error}")
                # Last resort: use tempfile.gettempdir() directly
                trigger_dir = tempfile.gettempdir()
                logger.warning(f"Using temp directory as fallback: {trigger_dir}")

            trigger_file = os.path.join(trigger_dir, f"{dag_run_id}.json")

            try:
                with open(trigger_file, "w") as f:
                    json.dump(trigger_data, f, indent=2)
                logger.info(f"Created trigger file {trigger_file} for DAG run {dag_run_id}")
                logger.warning(
                    f"Using file-based trigger fallback. Ensure Airflow can read from {trigger_dir}. "
                    f"REST API error was: {e}"
                )
            except OSError as file_error:
                error_msg = (
                    f"Failed to create trigger file {trigger_file}: {file_error}. "
                    f"REST API error was: {e}. "
                    f"Please check AIRFLOW_URL, AIRFLOW_USERNAME, and AIRFLOW_PASSWORD environment variables."
                )
                logger.error(error_msg)
                raise Exception(error_msg) from e

        return dag_run_id

    except Exception as e:
        error_msg = f"Failed to trigger Airflow DAG: {e}"
        logger.error(error_msg, exc_info=True)
        raise Exception(error_msg) from e


def update_pipeline_run_status(
    db: Session, dag_run_id: str, status: PipelineRunStatus, metrics: Optional[Dict[str, Any]] = None
):
    """
    Update pipeline run status from Airflow.

    This function is called by the Airflow DAG to update the pipeline run status.

    Args:
        db: Database session
        dag_run_id: DAG run ID
        status: New status
        metrics: Optional metrics to update
    """
    try:
        # Find pipeline run by DAG run ID
        pipeline_run = db.query(PipelineRun).filter(PipelineRun.dag_run_id == dag_run_id).first()

        if not pipeline_run:
            logger.warning(f"Pipeline run not found for DAG run ID: {dag_run_id}")
            return

        # Update status
        pipeline_run.status = status

        if status == PipelineRunStatus.RUNNING and not pipeline_run.started_at:
            pipeline_run.started_at = datetime.utcnow()
        elif status in [PipelineRunStatus.SUCCEEDED, PipelineRunStatus.FAILED]:
            pipeline_run.finished_at = datetime.utcnow()

        # Update metrics if provided (save to S3 if large)
        if metrics:
            from primedata.services.s3_json_storage import save_json_to_s3, should_save_to_s3

            # Merge with existing metrics
            if pipeline_run.metrics is None:
                pipeline_run.metrics = {}
            pipeline_run.metrics.update(metrics)

            # Check if metrics should be saved to S3 (if >1MB)
            if should_save_to_s3(pipeline_run.metrics):
                s3_path = save_json_to_s3(
                    pipeline_run.workspace_id,
                    pipeline_run.product_id,
                    "metrics",
                    pipeline_run.metrics,
                    version=pipeline_run.version,
                    subfolder="pipeline_runs",
                )
                if s3_path:
                    pipeline_run.metrics_path = s3_path
                    pipeline_run.archived_at = datetime.utcnow()
                    pipeline_run.metrics = {}  # Clear DB field after archiving
                    logger.info(f"Archived metrics to S3 for pipeline run {pipeline_run.id}")

        db.commit()

        logger.info(f"Updated pipeline run {pipeline_run.id} status to {status.value}")

    except Exception as e:
        logger.error(f"Failed to update pipeline run status: {e}")
        db.rollback()
        raise
