"""
Analytics API endpoints for dashboard metrics and insights.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import and_, desc, func
from sqlalchemy.orm import Session

from ..core.security import get_current_user
from ..db.database import get_db
from ..db.models import DataSource, DqViolation, PipelineArtifact, PipelineRun, PipelineRunStatus, Product, RawFile, User, Workspace

logger = logging.getLogger(__name__)

router = APIRouter()


class ProductInsightsResponse(BaseModel):
    """Product insights response (M2)."""

    fingerprint: Optional[Dict[str, Any]] = None  # Readiness fingerprint (can contain nested structures)
    policy: Optional[Dict[str, Any]] = None  # Policy evaluation result
    optimizer: Optional[Dict[str, Any]] = None  # Optimizer suggestions (M3)
    status: str = "available"  # "available", "draft", "no_data"
    message: Optional[str] = None  # Optional message explaining the status


class AnalyticsMetrics(BaseModel):
    """Analytics metrics response model."""

    total_products: int
    total_data_sources: int
    total_pipeline_runs: int
    success_rate: float
    avg_processing_time: float
    data_quality_score: float
    recent_activity: List[Dict[str, Any]]
    monthly_stats: List[Dict[str, Any]]


@router.get("/metrics", response_model=AnalyticsMetrics)
async def get_analytics_metrics(
    request: Request,
    workspace_id: str = Query(..., description="Workspace ID"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Get analytics metrics for the workspace.
    """
    try:
        from uuid import UUID

        from ..core.scope import ensure_workspace_access

        # Ensure user has access to the workspace
        workspace_uuid = UUID(workspace_id)
        workspace = ensure_workspace_access(db, request, workspace_uuid)

        # Basic counts - filter by workspace_id (already verified access above)
        total_products = db.query(Product).filter(Product.workspace_id == workspace_uuid).count()
        total_data_sources = db.query(DataSource).filter(DataSource.workspace_id == workspace_uuid).count()

        # Pipeline runs metrics - filter by workspace_id (already verified access above)
        pipeline_runs = db.query(PipelineRun).filter(PipelineRun.workspace_id == workspace_uuid)
        total_pipeline_runs = pipeline_runs.count()

        # Success rate calculation
        successful_runs = pipeline_runs.filter(PipelineRun.status == PipelineRunStatus.SUCCEEDED).count()
        success_rate = (successful_runs / max(total_pipeline_runs, 1)) * 100

        # Average processing time (in minutes)
        completed_runs = pipeline_runs.filter(
            and_(
                PipelineRun.status == PipelineRunStatus.SUCCEEDED,
                PipelineRun.started_at.isnot(None),
                PipelineRun.finished_at.isnot(None),
            )
        ).all()

        avg_processing_time = 0
        if completed_runs:
            total_time = sum(
                [
                    (run.finished_at - run.started_at).total_seconds()
                    for run in completed_runs
                    if run.finished_at and run.started_at
                ]
            )
            avg_processing_time = (total_time / len(completed_runs)) / 60  # Convert to minutes

        # Data quality score (based on violations)
        # Get violations through product relationship - filter by workspace_id (already verified access above)
        workspace_products = db.query(Product.id).filter(Product.workspace_id == workspace_uuid).subquery()
        total_violations = db.query(DqViolation).filter(DqViolation.product_id.in_(workspace_products)).count()
        # Simple quality score: higher is better, based on violation rate
        data_quality_score = max(0, 100 - (total_violations * 2))  # Each violation reduces score by 2%

        # Recent activity (last 10 pipeline runs)
        recent_runs = pipeline_runs.order_by(desc(PipelineRun.started_at)).limit(10).all()
        recent_activity = []

        for run in recent_runs:
            status_icon = (
                "success"
                if run.status == PipelineRunStatus.SUCCEEDED
                else "error" if run.status == PipelineRunStatus.FAILED else "warning"
            )
            activity_type = "pipeline"

            if run.status == PipelineRunStatus.SUCCEEDED:
                message = f"Product pipeline completed successfully"
            elif run.status == PipelineRunStatus.FAILED:
                message = f"Product pipeline failed"
            else:
                message = f"Product pipeline {run.status.value}"

            recent_activity.append(
                {
                    "id": str(run.id),
                    "type": activity_type,
                    "message": message,
                    "timestamp": run.started_at.isoformat() if run.started_at else datetime.now(timezone.utc).isoformat(),
                    "status": status_icon,
                }
            )

        # Monthly stats - show recent 6 months:
        # - If user joined < 6 months ago: show all months from join date to current
        # - If user joined >= 6 months ago: show only last 6 months (current + previous 5)
        # Get the earliest date: workspace creation or user creation
        # Ensure timezone-aware datetime
        now_utc = datetime.now(timezone.utc)
        workspace_created = workspace.created_at if workspace.created_at else now_utc
        # If workspace_created is timezone-naive, make it timezone-aware (UTC)
        if workspace_created.tzinfo is None:
            workspace_created = workspace_created.replace(tzinfo=timezone.utc)
        
        user_created = None
        if current_user and current_user.get("id"):
            user = db.query(User).filter(User.id == UUID(current_user["id"])).first()
            if user and user.created_at:
                user_created = user.created_at
                # If user_created is timezone-naive, make it timezone-aware (UTC)
                if user_created.tzinfo is None:
                    user_created = user_created.replace(tzinfo=timezone.utc)
        
        # Determine the earliest date - prioritize user creation date to show months from when user joined
        if user_created:
            earliest_date = user_created
        else:
            earliest_date = workspace_created
        
        # Calculate how many months to show (up to 6 months)
        # Ensure timezone-aware datetime
        current_month_start = now_utc.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        # Ensure earliest_date is timezone-aware before using replace
        if earliest_date.tzinfo is None:
            earliest_date = earliest_date.replace(tzinfo=timezone.utc)
        earliest_month_start = earliest_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        # Calculate months difference (number of months from join to current, inclusive)
        months_diff = (current_month_start.year - earliest_month_start.year) * 12 + (current_month_start.month - earliest_month_start.month)
        total_months = months_diff + 1  # +1 to include current month
        
        # Determine start month for display
        # If user joined less than 6 months ago: start from join month
        # If user joined 6+ months ago: start from 5 months before current (to show last 6 months)
        MAX_MONTHS_TO_SHOW = 6
        if total_months <= MAX_MONTHS_TO_SHOW:
            # Show all months from join to current
            display_start_month = earliest_month_start
        else:
            # Show only last 6 months: go back 5 months from current
            display_start_month = current_month_start
            for _ in range(MAX_MONTHS_TO_SHOW - 1):
                if display_start_month.month == 1:
                    display_start_month = display_start_month.replace(year=display_start_month.year - 1, month=12, day=1)
                else:
                    display_start_month = display_start_month.replace(month=display_start_month.month - 1, day=1)
        
        # Debug logging
        logger.debug(f"Analytics monthly stats calculation: current_month_start={current_month_start}, earliest_month_start={earliest_month_start}, months_diff={months_diff}, total_months={total_months}, display_start_month={display_start_month}")
        
        monthly_stats = []
        
        # Build list of months from display_start_month to current (inclusive), then reverse to get current first
        months_to_process = []
        temp_month = display_start_month
        
        # Ensure display_start_month is timezone-aware
        if temp_month.tzinfo is None:
            temp_month = temp_month.replace(tzinfo=timezone.utc)
        
        # Build the list - iterate until we include current_month_start
        while len(months_to_process) < MAX_MONTHS_TO_SHOW:
            # Ensure temp_month is timezone-aware
            if temp_month.tzinfo is None:
                temp_month = temp_month.replace(tzinfo=timezone.utc)
            
            months_to_process.append(temp_month)
            
            # Stop if we've reached or passed current month
            if temp_month >= current_month_start:
                break
            
            # Move to next month (replace preserves timezone if present)
            if temp_month.month == 12:
                temp_month = temp_month.replace(year=temp_month.year + 1, month=1, day=1)
            else:
                temp_month = temp_month.replace(month=temp_month.month + 1, day=1)
        
        # Reverse to show current month first
        months_to_process.reverse()
        
        # Process each month
        for month_start in months_to_process:
            # Ensure month_start is timezone-aware
            if month_start.tzinfo is None:
                month_start = month_start.replace(tzinfo=timezone.utc)
            
            # Calculate month end (first day of next month)
            if month_start.month == 12:
                month_end = month_start.replace(year=month_start.year + 1, month=1, day=1)
            else:
                month_end = month_start.replace(month=month_start.month + 1, day=1)
            
            # Ensure month_end is timezone-aware
            if month_end.tzinfo is None:
                month_end = month_end.replace(tzinfo=timezone.utc)

            # Pipeline runs for this month
            month_runs = pipeline_runs.filter(
                and_(PipelineRun.started_at >= month_start, PipelineRun.started_at < month_end)
            ).count()

            # Products created in this month
            month_products = db.query(Product).filter(
                and_(
                    Product.workspace_id == workspace_uuid,
                    Product.created_at >= month_start,
                    Product.created_at < month_end
                )
            ).count()

            # Data sources created in this month
            month_data_sources = db.query(DataSource).filter(
                and_(
                    DataSource.workspace_id == workspace_uuid,
                    DataSource.created_at >= month_start,
                    DataSource.created_at < month_end
                )
            ).count()

            # Calculate data size from pipeline artifacts for this month
            # Get pipeline runs for this month
            month_pipeline_runs = pipeline_runs.filter(
                and_(PipelineRun.started_at >= month_start, PipelineRun.started_at < month_end)
            ).all()
            
            month_run_ids = [run.id for run in month_pipeline_runs]
            data_size_bytes = 0
            if month_run_ids:
                # Sum up artifact sizes for runs in this month
                artifacts = db.query(PipelineArtifact).filter(
                    PipelineArtifact.pipeline_run_id.in_(month_run_ids)
                ).all()
                data_size_bytes = sum(artifact.file_size for artifact in artifacts)
            
            # Get workspace products subquery (used for raw files and violations)
            workspace_products = db.query(Product.id).filter(Product.workspace_id == workspace_uuid).subquery()
            
            # If no artifacts, try to get from raw files processed in this month
            if data_size_bytes == 0:
                raw_files = db.query(RawFile).filter(
                    and_(
                        RawFile.product_id.in_(workspace_products),
                        RawFile.processed_at >= month_start,
                        RawFile.processed_at < month_end
                    )
                ).all()
                data_size_bytes = sum(raw_file.file_size for raw_file in raw_files)
            
            # Convert to TB
            data_processed_tb = data_size_bytes / (1024 ** 4)  # Convert bytes to TB

            # Calculate success rate for this month (percentage of successful pipeline runs)
            month_success_rate = 0.0
            if month_runs > 0:
                month_successful_runs = pipeline_runs.filter(
                    and_(
                        PipelineRun.started_at >= month_start,
                        PipelineRun.started_at < month_end,
                        PipelineRun.status == PipelineRunStatus.SUCCEEDED
                    )
                ).count()
                month_success_rate = (month_successful_runs / month_runs) * 100

            monthly_stats.append(
                {
                    "month": month_start.strftime("%b %Y"),
                    "pipeline_runs": month_runs,
                    "products": month_products,
                    "data_sources": month_data_sources,
                    "data_processed": round(data_processed_tb, 2),
                    "success_rate": round(month_success_rate, 1),
                }
            )
        
        # List is already in correct order: current month first, then previous months

        return AnalyticsMetrics(
            total_products=total_products,
            total_data_sources=total_data_sources,
            total_pipeline_runs=total_pipeline_runs,
            success_rate=round(success_rate, 1),
            avg_processing_time=round(avg_processing_time, 1),
            data_quality_score=round(data_quality_score, 1),
            recent_activity=recent_activity,
            monthly_stats=monthly_stats,
        )

    except Exception as e:
        logger.error(f"Failed to get analytics metrics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get analytics metrics: {str(e)}"
        )


@router.get("/products/{product_id}/insights", response_model=ProductInsightsResponse)
async def get_product_insights(
    product_id: UUID, request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)
):
    """
    Get product insights including fingerprint, policy, and optimizer (M2).
    This endpoint is available under /api/v1/analytics/products/{product_id}/insights
    """
    from ..core.scope import ensure_product_access
    from ..ingestion_pipeline.aird_stages.config import get_aird_config
    from ..ingestion_pipeline.aird_stages.storage import AirdStorageAdapter
    from ..services.policy_engine import evaluate_policy

    product = ensure_product_access(db, request, product_id)

    # Get fingerprint (lazy load from S3 if needed)
    from primedata.services.lazy_json_loader import load_product_json_field

    fingerprint_data = load_product_json_field(product, "readiness_fingerprint")
    fingerprint = None

    if fingerprint_data:
        # Handle both old format (nested in metrics) and new format (direct fingerprint)
        if isinstance(fingerprint_data, dict):
            # Check if it's the old format with nested fingerprint
            if "fingerprint" in fingerprint_data and isinstance(fingerprint_data["fingerprint"], dict):
                fingerprint = fingerprint_data["fingerprint"]
            else:
                # New format: fingerprint is directly the metrics dict
                fingerprint = fingerprint_data

    if not fingerprint:
        # Try to load from storage
        try:
            storage = AirdStorageAdapter(
                workspace_id=product.workspace_id,
                product_id=product.id,
                version=product.current_version,
            )

            metrics = storage.get_metrics_json()
            if metrics:
                from ..services.fingerprint import generate_fingerprint

                fingerprint = generate_fingerprint(metrics)
        except Exception as e:
            logger.warning(f"Failed to load fingerprint from storage: {e}")

    # If no fingerprint, return a response indicating the product needs a pipeline run
    if not fingerprint:
        # Check if product is in draft state or has no pipeline runs
        from ..db.models import ProductStatus

        if product.status == ProductStatus.DRAFT or product.current_version <= 0:
            return ProductInsightsResponse(
                fingerprint=None,
                policy=None,
                optimizer=None,
                status="draft",
                message="Product is in draft state. Run a pipeline to generate insights.",
            )
        else:
            return ProductInsightsResponse(
                fingerprint=None,
                policy=None,
                optimizer=None,
                status="no_data",
                message="No fingerprint data available. Run a pipeline to generate insights.",
            )

    # Evaluate policy
    config = get_aird_config()
    thresholds = {
        "min_trust_score": config.policy_min_trust_score,
        "min_secure": config.policy_min_secure,
        "min_metadata_presence": config.policy_min_metadata_presence,
        "min_kb_ready": config.policy_min_kb_ready,
    }

    policy_result = evaluate_policy(fingerprint, thresholds)

    # Optimizer suggestions (M5)
    from ..services.optimizer import suggest_next_config

    optimizer = suggest_next_config(
        fingerprint=fingerprint,
        policy=policy_result,
        current_playbook=product.playbook_id,
    )

    return ProductInsightsResponse(
        fingerprint=fingerprint,
        policy=policy_result,
        optimizer=optimizer,
        status="available",
        message=None,
    )
