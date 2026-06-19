"""
Products API router.
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
from uuid import uuid4 as uuid_uuid4

import numpy as np
from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from primedata.analysis.content_analyzer import ChunkingConfig, content_analyzer
from primedata.config.models import extraction_type_to_source_quality
from primedata.api.billing import check_billing_limits
from primedata.core.embedding_workspace import validate_embedding_config_for_workspace
from primedata.core.scope import allowed_workspaces, ensure_product_access, ensure_workspace_access
from primedata.core.security import get_current_user
from primedata.core.settings import get_settings
from primedata.core.user_utils import get_user_id
from primedata.db.database import get_db
from primedata.db.models import (
    ArtifactStatus,
    ArtifactType,
    PipelineArtifact,
    PipelineRun,
    PipelineRunStatus,
    Product,
    ProductStatus,
    Workspace,
)
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

router = APIRouter(prefix="/api/v1/products", tags=["Products"])
logger = logging.getLogger(__name__)


def _effective_rag_quality_thresholds(product: Product) -> Dict[str, float]:
    """Merge stored product overrides with taxonomy defaults (same as gate evaluation)."""
    from primedata.evaluation.gates.thresholds import ThresholdManager

    defaults = ThresholdManager.get_default_thresholds()
    custom = product.rag_quality_thresholds or {}
    return ThresholdManager.merge_thresholds(defaults, custom)


def _chunking_config_for_response(chunking_config: Optional[Dict[str, Any]], extraction_type: Optional[str]) -> Optional[Dict[str, Any]]:
    """Ensure chunking_config.resolved_settings has content_type (semantic) and source_quality for backward-compatible API response."""
    if not chunking_config or not isinstance(chunking_config, dict):
        return chunking_config
    resolved = chunking_config.get("resolved_settings")
    if not isinstance(resolved, dict):
        return chunking_config
    out = dict(chunking_config)
    rs = dict(resolved)
    # Normalize content_type: "scanned" is not a content_type
    if rs.get("content_type") and str(rs.get("content_type", "")).strip().lower() == "scanned":
        rs["content_type"] = "general"
    # Backward compat: ensure source_quality present (from product.extraction_type if missing; default native_pdf)
    if rs.get("source_quality") is None:
        rs["source_quality"] = extraction_type_to_source_quality(extraction_type)
    out["resolved_settings"] = rs
    return out


# Removed get_current_user_optional - authentication is always required


class ProductCreateRequest(BaseModel):
    workspace_id: UUID
    name: str
    playbook_id: Optional[str] = None  # Optional playbook ID (M1)
    chunking_config: Optional[Dict[str, Any]] = None  # Optional chunking configuration
    embedding_config: Optional[Dict[str, Any]] = None  # Optional embedding configuration
    vector_creation_enabled: Optional[bool] = True  # Enable vector/embedding creation (default: True)
    use_case_description: Optional[str] = None  # Use case description (only set during creation)


class ChunkingConfigRequest(BaseModel):
    mode: Optional[str] = None  # "auto" or "manual"
    optimization_mode: Optional[str] = None  # "pattern", "hybrid", or "llm"
    auto_settings: Optional[Dict[str, Any]] = None
    manual_settings: Optional[Dict[str, Any]] = None


class ProductUpdateRequest(BaseModel):
    name: Optional[str] = None
    status: Optional[ProductStatus] = None
    playbook_id: Optional[str] = None
    chunking_config: Optional[ChunkingConfigRequest] = None
    embedding_config: Optional[Dict[str, Any]] = None
    vector_creation_enabled: Optional[bool] = None  # Enable/disable vector creation (use_case_description not editable)


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)  # Pydantic v2 syntax

    id: UUID
    workspace_id: UUID
    owner_user_id: UUID
    name: str
    status: ProductStatus
    current_version: int
    promoted_version: Optional[int] = None
    aird_enabled: bool = True  # AIRD pipeline enabled flag
    playbook_id: Optional[str] = None  # M1 (semantic: TECH, REGULATORY, MEDICAL, etc.)
    extraction_type: Optional[str] = None  # digital_pdf | scanned_pdf | mixed (from preprocess; not content_type)
    playbook_selection: Optional[Dict[str, Any]] = None  # Auto-detection metadata: method, reason, detected_at
    preprocessing_stats: Optional[Dict[str, Any]] = None  # M1
    trust_score: Optional[float] = None  # M2
    policy_status: Optional[str] = None  # M2: "passed" or "failed"
    policy_violations: Optional[List[str]] = None  # M2
    chunk_metrics: Optional[List[Dict[str, Any]]] = None  # M2
    validation_summary_path: Optional[str] = None  # M3
    trust_report_path: Optional[str] = None  # M3
    chunking_config: Optional[Dict[str, Any]] = None
    embedding_config: Optional[Dict[str, Any]] = None
    chunking_strategy: Optional[str] = None  # From latest successful pipeline run
    vector_creation_enabled: bool = True  # Enable vector/embedding creation and indexing
    use_case_description: Optional[str] = None  # Use case description (only set during creation)
    rag_quality_thresholds: Optional[Dict[str, float]] = None  # Effective RAG gate thresholds (defaults + overrides)
    created_at: datetime
    updated_at: Optional[datetime] = None


class TrustMetricsResponse(BaseModel):
    """Trust metrics response (M2)."""

    ai_trust_score: float
    metrics: Dict[str, Any]  # All 13 metrics (can contain nested structures)
    chunk_count: int
    aggregated_at: Optional[datetime] = None


class ProductInsightsResponse(BaseModel):
    """Product insights response (M2)."""

    fingerprint: Dict[str, Any]  # Readiness fingerprint (can contain nested structures)
    policy: Dict[str, Any]  # Policy evaluation result
    optimizer: Optional[Dict[str, Any]] = None  # Optimizer suggestions (M3)


@router.post("/", response_model=ProductResponse)
async def create_product(
    request_body: ProductCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Create a new product in the specified workspace.
    """
    try:
        # Ensure user has access to the workspace
        ensure_workspace_access(db, request, request_body.workspace_id)

        # CRITICAL: Double-check workspace is in user's allowed workspaces
        # This prevents products from being created in wrong workspaces
        allowed_workspace_ids = allowed_workspaces(request, db)
        if request_body.workspace_id not in allowed_workspace_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this workspace. Products must be created in your own workspace.",
            )

        # Check billing limits for product creation
        current_product_count = db.query(Product).filter(Product.workspace_id == request_body.workspace_id).count()

        if not check_billing_limits(str(request_body.workspace_id), "max_products", current_product_count, db):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Product limit exceeded. Please upgrade your plan to create more products.",
            )

        # Check if product name already exists in workspace
        existing_product = (
            db.query(Product)
            .filter(Product.workspace_id == request_body.workspace_id, Product.name == request_body.name)
            .first()
        )

        if existing_product:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Product name already exists in this workspace")

        # Create new product
        # Initialize playbook_selection metadata if playbook is provided
        playbook_selection = None
        if request_body.playbook_id:
            playbook_selection = {
                "playbook_id": request_body.playbook_id,
                "method": "manual",  # User manually selected during creation
                "reason": None,
                "detected_at": None,
            }

        embedding_cfg = request_body.embedding_config or {"embedder_name": "minilm", "embedding_dimension": 384}
        validate_embedding_config_for_workspace(db, request_body.workspace_id, embedding_cfg)

        product = Product(
            workspace_id=request_body.workspace_id,
            owner_user_id=get_user_id(current_user),
            name=request_body.name,
            status=ProductStatus.DRAFT,
            aird_enabled=True,  # Enable AIRD by default
            playbook_id=request_body.playbook_id,  # M1
            playbook_selection=playbook_selection,  # Store selection metadata
            chunking_config=request_body.chunking_config,  # Chunking configuration
            embedding_config=embedding_cfg,  # Embedding configuration
            vector_creation_enabled=request_body.vector_creation_enabled if request_body.vector_creation_enabled is not None else True,  # Default to True
            use_case_description=request_body.use_case_description,  # Use case description (only during creation)
        )

        # Log the chunking config being saved
        logger.info(f"Creating product '{request_body.name}' with chunking_config: {request_body.chunking_config}")

        db.add(product)
        db.commit()
        db.refresh(product)

        logger.info(f"Product created with ID {product.id}. Saved chunking_config: {product.chunking_config}")

        return ProductResponse.model_validate(product)
    except HTTPException:
        # Re-raise HTTP exceptions (they already have proper error messages)
        raise
    except Exception as e:
        # Log the full error for debugging
        logger.error(f"Failed to create product: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create product: {str(e)}")


@router.get("/", response_model=List[ProductResponse])
async def list_products(
    request: Request,
    workspace_id: Optional[UUID] = Query(None, description="Filter by workspace ID"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    List products. If workspace_id is provided, filter by that workspace.
    Otherwise, return products from all accessible workspaces.
    """
    allowed_workspace_ids = allowed_workspaces(request, db)

    # CRITICAL: If user has no workspace access, return empty list
    if not allowed_workspace_ids:
        return []

    query = db.query(Product).filter(Product.workspace_id.in_(allowed_workspace_ids))

    if workspace_id:
        # Ensure user has access to the specified workspace
        if workspace_id not in allowed_workspace_ids:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to workspace")
        query = query.filter(Product.workspace_id == workspace_id)

    products = query.all()
    # Fix 5: Optimize backend - Skip loading large JSON fields for list view
    # These fields are only needed in detail view, not list view
    # This avoids unnecessary S3 calls when listing products
    from primedata.services.lazy_json_loader import load_product_json_field

    result = []
    for product in products:
        # Create response - skip preprocessing_stats and chunk_metrics for list view
        # These are large fields that trigger S3 calls and aren't needed in list view
        product_dict = {
            "id": product.id,
            "workspace_id": product.workspace_id,
            "owner_user_id": product.owner_user_id,
            "name": product.name,
            "status": product.status,
            "current_version": product.current_version,
            "promoted_version": product.promoted_version,
            "aird_enabled": product.aird_enabled,
            "playbook_id": product.playbook_id,
            "extraction_type": getattr(product, "extraction_type", None),
            "playbook_selection": product.playbook_selection,
            "preprocessing_stats": None,  # Skip loading for list view (not needed)
            "trust_score": product.trust_score,
            "policy_status": product.policy_status.value if product.policy_status else None,
            "policy_violations": product.policy_violations,
            "chunk_metrics": None,  # Skip loading for list view (not needed)
            "validation_summary_path": product.validation_summary_path,
            "trust_report_path": product.trust_report_path,
            "chunking_config": _chunking_config_for_response(
                product.chunking_config, getattr(product, "extraction_type", None)
            ),
            "embedding_config": product.embedding_config,
            "vector_creation_enabled": product.vector_creation_enabled,
            "use_case_description": product.use_case_description,
            "rag_quality_thresholds": None,
            "created_at": product.created_at,
            "updated_at": product.updated_at,
        }
        result.append(ProductResponse(**product_dict))
    return result


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: UUID, request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)
):
    """
    Get a specific product by ID.
    """
    from primedata.core.scope import ensure_product_access

    product = ensure_product_access(db, request, product_id)
    # Refresh to ensure we get the latest data from database (in case of recent updates)
    db.refresh(product)
    # Lazy-load JSON fields from S3 if needed
    from primedata.services.lazy_json_loader import load_product_json_field

    # Get chunking strategy from latest successful pipeline run
    chunking_strategy = None
    latest_successful_run = (
        db.query(PipelineRun)
        .filter(
            PipelineRun.product_id == product_id,
            PipelineRun.status == PipelineRunStatus.SUCCEEDED
        )
        .order_by(PipelineRun.finished_at.desc(), PipelineRun.started_at.desc())
        .first()
    )
    
    if latest_successful_run:
        from primedata.services.lazy_json_loader import load_pipeline_run_metrics
        metrics = load_pipeline_run_metrics(latest_successful_run)
        chunking_strategy = metrics.get("chunking_config", {}).get("resolved_settings", {}).get("chunking_strategy")

    product_dict = {
        "id": product.id,
        "workspace_id": product.workspace_id,
        "owner_user_id": product.owner_user_id,
        "name": product.name,
        "status": product.status,
        "current_version": product.current_version,
        "promoted_version": product.promoted_version,
        "aird_enabled": product.aird_enabled,
        "playbook_id": product.playbook_id,
        "extraction_type": getattr(product, "extraction_type", None),
        "playbook_selection": product.playbook_selection,
        "preprocessing_stats": load_product_json_field(product, "preprocessing_stats"),
        "trust_score": product.trust_score,
        "policy_status": product.policy_status.value if product.policy_status else None,
        "policy_violations": product.policy_violations,
        "chunk_metrics": load_product_json_field(product, "chunk_metrics"),
        "validation_summary_path": product.validation_summary_path,
        "trust_report_path": product.trust_report_path,
        "chunking_config": _chunking_config_for_response(
            product.chunking_config, getattr(product, "extraction_type", None)
        ),
        "embedding_config": product.embedding_config,
        "chunking_strategy": chunking_strategy,
        "vector_creation_enabled": product.vector_creation_enabled,
        "use_case_description": product.use_case_description,
        "rag_quality_thresholds": _effective_rag_quality_thresholds(product),
        "created_at": product.created_at,
        "updated_at": product.updated_at,
    }
    return ProductResponse(**product_dict)


@router.patch("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: UUID,
    request_body: ProductUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Update a product's name or status.
    """
    logger.info(f"PATCH /api/v1/products/{product_id} - Received update request")
    logger.info(f"Request body: {request_body.dict()}")

    try:
        from primedata.core.scope import ensure_product_access

        product = ensure_product_access(db, request, product_id)

        # Check if new name conflicts with existing product in same workspace
        if request_body.name and request_body.name != product.name:
            existing_product = (
                db.query(Product)
                .filter(
                    Product.workspace_id == product.workspace_id, Product.name == request_body.name, Product.id != product_id
                )
                .first()
            )

            if existing_product:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT, detail="Product name already exists in this workspace"
                )

        # Update fields
        if request_body.name is not None:
            product.name = request_body.name
        if request_body.status is not None:
            product.status = request_body.status
        if request_body.playbook_id is not None:
            product.playbook_id = request_body.playbook_id

        # Update chunking configuration
        if request_body.chunking_config is not None:
            current_config = product.chunking_config or {}

            # Preserve resolved_settings if it exists (from previous pipeline runs) before updating
            resolved_settings = current_config.get("resolved_settings")

            if request_body.chunking_config.mode is not None:
                current_config["mode"] = request_body.chunking_config.mode

            # Update optimization_mode if provided (preserve existing if not provided, default to 'pattern')
            if request_body.chunking_config.optimization_mode is not None:
                current_config["optimization_mode"] = request_body.chunking_config.optimization_mode
                logger.info(f"Updated optimization_mode to: {request_body.chunking_config.optimization_mode}")
            elif "optimization_mode" not in current_config:
                # Set default if not present
                current_config["optimization_mode"] = "pattern"
                logger.info(f"Set default optimization_mode to: pattern")

            # Get the new mode to determine what to update
            new_mode = (
                request_body.chunking_config.mode
                if request_body.chunking_config.mode is not None
                else current_config.get("mode", "auto")
            )

            # Update auto_settings
            if request_body.chunking_config.auto_settings is not None:
                current_config["auto_settings"] = request_body.chunking_config.auto_settings
            elif new_mode == "auto":
                # If switching to auto mode but auto_settings not provided, ensure we have defaults
                if "auto_settings" not in current_config or not current_config.get("auto_settings"):
                    current_config["auto_settings"] = {
                        "content_type": "general",
                        "model_optimized": True,
                        "confidence_threshold": 0.7,
                    }

            # Update manual_settings - ALWAYS overwrite when provided, even if mode is manual
            if request_body.chunking_config.manual_settings is not None:
                # Completely replace manual_settings with new values (don't merge)
                # Create a fresh dict to ensure no reference issues
                current_config["manual_settings"] = dict(request_body.chunking_config.manual_settings)
                logger.info(f"🔄 REPLACING manual_settings with: {current_config['manual_settings']}")
                logger.info(f"   Old manual_settings was: {current_config.get('manual_settings', 'None')}")
            elif new_mode == "manual":
                # If switching to manual mode but manual_settings not provided, keep existing or use defaults
                if "manual_settings" not in current_config or not current_config.get("manual_settings"):
                    current_config["manual_settings"] = {
                        "chunk_size": 1000,
                        "chunk_overlap": 200,
                        "min_chunk_size": 100,
                        "max_chunk_size": 2000,
                        "chunking_strategy": "fixed_size",
                    }
                    logger.info(f"Using default manual_settings for new manual mode")

            # Restore resolved_settings if it existed (for reference only, won't affect editing)
            if resolved_settings:
                current_config["resolved_settings"] = resolved_settings

            # CRITICAL: Assign the entire config dict to ensure SQLAlchemy detects the change
            # Create a fresh dict to avoid any reference issues
            product.chunking_config = dict(current_config)

            # Force SQLAlchemy to mark this as changed (required for JSON columns)
            flag_modified(product, "chunking_config")

            logger.info(f"📝 Product chunking_config assigned: {product.chunking_config}")

            # Log the saved configuration for verification
            logger.info(
                f"Updated chunking_config for product {product_id}: "
                f"mode={current_config.get('mode')}, "
                f"optimization_mode={current_config.get('optimization_mode')}, "
                f"manual_settings={current_config.get('manual_settings')}, "
                f"auto_settings={current_config.get('auto_settings')}"
            )

        # Update embedding configuration
        if request_body.embedding_config is not None:
            validate_embedding_config_for_workspace(db, product.workspace_id, request_body.embedding_config)
            product.embedding_config = request_body.embedding_config
            logger.info(f"Updated embedding_config for product {product_id}: {product.embedding_config}")

        # Update vector_creation_enabled (use_case_description is not editable)
        if request_body.vector_creation_enabled is not None:
            product.vector_creation_enabled = request_body.vector_creation_enabled
            logger.info(f"Updated vector_creation_enabled for product {product_id}: {product.vector_creation_enabled}")

        # Log playbook_id update
        if request_body.playbook_id is not None:
            logger.info(f"Updated playbook_id for product {product_id}: {product.playbook_id}")

        # Commit all changes
        logger.info(f"Committing changes to database for product {product_id}")
        db.commit()
        logger.info(f"Commit successful, refreshing product")
        db.refresh(product)

        # Log final saved state for verification
        logger.info(
            f"Product {product_id} saved successfully. "
            f"chunking_config={product.chunking_config}, "
            f"embedding_config={product.embedding_config}, "
            f"playbook_id={product.playbook_id}"
        )

        # Verify the saved values, especially manual_settings
        if product.chunking_config and product.chunking_config.get("manual_settings"):
            manual = product.chunking_config["manual_settings"]
            logger.info(
                f"✅ Verified saved manual_settings: "
                f"chunk_size={manual.get('chunk_size')}, "
                f"chunk_overlap={manual.get('chunk_overlap')}, "
                f"strategy={manual.get('chunking_strategy')}"
            )

        # Lazy-load JSON fields from S3 if needed
        from primedata.services.lazy_json_loader import load_product_json_field

        product_dict = {
            "id": product.id,
            "workspace_id": product.workspace_id,
            "owner_user_id": product.owner_user_id,
            "name": product.name,
            "status": product.status,
            "current_version": product.current_version,
            "promoted_version": product.promoted_version,
            "aird_enabled": product.aird_enabled,
            "playbook_id": product.playbook_id,
            "playbook_selection": product.playbook_selection,
            "preprocessing_stats": load_product_json_field(product, "preprocessing_stats"),
            "trust_score": product.trust_score,
            "policy_status": product.policy_status.value if product.policy_status else None,
            "policy_violations": product.policy_violations,
            "chunk_metrics": load_product_json_field(product, "chunk_metrics"),
            "validation_summary_path": product.validation_summary_path,
            "trust_report_path": product.trust_report_path,
            "chunking_config": product.chunking_config,
            "embedding_config": product.embedding_config,
            "vector_creation_enabled": product.vector_creation_enabled,
            "use_case_description": product.use_case_description,
            "rag_quality_thresholds": _effective_rag_quality_thresholds(product),
            "created_at": product.created_at,
            "updated_at": product.updated_at,
        }
        return ProductResponse(**product_dict)

    except HTTPException:
        # Re-raise HTTP exceptions (they already have proper error messages)
        raise
    except Exception as e:
        # Log the full error for debugging
        logger.error(f"Failed to update product {product_id}: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to update product: {str(e)}")


@router.delete("/{product_id}")
async def delete_product(
    product_id: UUID, request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)
):
    """
    Delete a product and all related data.
    """
    from primedata.db.models import ACL, DataSource, DqViolation, PipelineArtifact, PipelineRun, RawFile

    # Try to import enterprise models if available
    try:
        from primedata.db.models_enterprise import DataQualityRule

        has_dq_rules = True
    except ImportError:
        has_dq_rules = False

    # Ensure user has access to the product
    product = ensure_product_access(db, request, product_id)

    try:
        # Delete all related records that have foreign key constraints
        # Use synchronize_session=False to avoid loading objects into memory
        # IMPORTANT: Delete order matters due to foreign key constraints

        # Delete raw files FIRST (they reference data_sources via data_source_id)
        db.query(RawFile).filter(RawFile.product_id == product_id).delete(synchronize_session=False)

        # Delete data sources (after raw files, since raw_files references data_sources)
        db.query(DataSource).filter(DataSource.product_id == product_id).delete(synchronize_session=False)

        # Delete pipeline artifacts (deleted before pipeline runs due to foreign key)
        db.query(PipelineArtifact).filter(PipelineArtifact.product_id == product_id).delete(synchronize_session=False)

        # Delete pipeline runs
        db.query(PipelineRun).filter(PipelineRun.product_id == product_id).delete(synchronize_session=False)

        # Delete data quality violations
        db.query(DqViolation).filter(DqViolation.product_id == product_id).delete(synchronize_session=False)

        # Delete data quality rules (if available)
        if has_dq_rules:
            db.query(DataQualityRule).filter(DataQualityRule.product_id == product_id).delete(synchronize_session=False)

        # Delete document metadata
        # Note: Metadata is now stored in Qdrant payloads, not PostgreSQL
        # Qdrant collections are deleted separately when product is deleted

        # Delete ACLs
        db.query(ACL).filter(ACL.product_id == product_id).delete(synchronize_session=False)

        # Now delete the product itself
        db.delete(product)
        db.commit()

        return {"message": "Product deleted successfully"}
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete product {product_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to delete product: {str(e)}")


@router.get("/{product_id}/trust-metrics", response_model=TrustMetricsResponse)
async def get_trust_metrics(
    product_id: UUID, request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)
):
    """
    Get aggregated trust metrics for a product (M2).
    """
    from primedata.core.scope import ensure_product_access
    from primedata.ingestion_pipeline.aird_stages.storage import AirdStorageAdapter

    product = ensure_product_access(db, request, product_id)

    # Try to get from product model first (lazy load from S3 if needed)
    from primedata.services.lazy_json_loader import load_product_json_field

    fingerprint_data = load_product_json_field(product, "readiness_fingerprint")

    if fingerprint_data:

        # Handle both old format (nested in metrics) and new format (direct fingerprint)
        if isinstance(fingerprint_data, dict):
            # Check if it's the old format with nested fingerprint
            if "fingerprint" in fingerprint_data and isinstance(fingerprint_data["fingerprint"], dict):
                fingerprint = fingerprint_data["fingerprint"]
                # Try canonical ai_trust_score first, then legacy AI_Trust_Score
                trust_score = fingerprint.get(
                    "ai_trust_score", 
                    fingerprint.get("AI_Trust_Score", fingerprint_data.get("trust_score", product.trust_score or 0.0))
                )
            else:
                # New format: fingerprint is directly the metrics dict
                fingerprint = fingerprint_data
                # Try canonical ai_trust_score first, then legacy AI_Trust_Score
                trust_score = fingerprint.get(
                    "ai_trust_score",
                    fingerprint.get("AI_Trust_Score", product.trust_score or 0.0)
                )
        else:
            fingerprint = {}
            trust_score = product.trust_score or 0.0

        # Calculate chunk count from token metrics if available
        chunk_count = fingerprint.get("num_chunks", 0)
        if chunk_count == 0:
            # Fallback: try to get from chunk_metrics if available
            chunk_metrics = load_product_json_field(product, "chunk_metrics")
            if chunk_metrics and isinstance(chunk_metrics, list):
                chunk_count = len(chunk_metrics)

        return TrustMetricsResponse(
            ai_trust_score=float(trust_score) if trust_score is not None else 0.0,
            metrics=fingerprint,
            chunk_count=chunk_count,
        )

    # Fingerprint not generated yet - return 409 Conflict with clear message
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Fingerprint not generated yet; run pipeline to generate trust metrics"
    )


@router.get("/{product_id}/insights", response_model=ProductInsightsResponse)
async def get_product_insights(
    product_id: UUID, request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)
):
    """
    Get product insights including fingerprint, policy, and optimizer (M2).
    """
    from primedata.core.scope import ensure_product_access
    from primedata.ingestion_pipeline.aird_stages.config import get_aird_config
    from primedata.ingestion_pipeline.aird_stages.storage import AirdStorageAdapter
    from primedata.services.policy_engine import evaluate_policy

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
                from primedata.services.fingerprint import generate_fingerprint

                fingerprint = generate_fingerprint(metrics)
        except Exception as e:
            logger.warning(f"Failed to load fingerprint from storage: {e}")

    if not fingerprint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fingerprint not available for this product")

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
    from primedata.services.optimizer import suggest_next_config

    optimizer = suggest_next_config(
        fingerprint=fingerprint,
        policy=policy_result,
        current_playbook=product.playbook_id,
    )

    return ProductInsightsResponse(
        fingerprint=fingerprint,
        policy=policy_result,
        optimizer=optimizer,
    )


class ApplyRecommendationRequest(BaseModel):
    """Request model for applying an optimizer recommendation."""

    action: str = Field(
        ...,
        description="Action to apply: 'increase_chunk_overlap', 'switch_playbook', 'enhance_normalization', 'extract_metadata'",
    )
    recommendation_config: Dict[str, Any] = Field(
        default_factory=dict, description="Configuration for the recommendation action"
    )


class ApplyRecommendationResponse(BaseModel):
    """Response model for applying an optimizer recommendation."""

    success: bool
    message: str
    applied_changes: Dict[str, Any]
    requires_pipeline_rerun: bool = Field(default=True, description="Whether a pipeline rerun is required to see the changes")


@router.post("/{product_id}/apply-recommendation", response_model=ApplyRecommendationResponse)
async def apply_recommendation(
    product_id: UUID,
    request_body: ApplyRecommendationRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Apply an optimizer recommendation to improve AI readiness.

    This endpoint allows users to apply specific recommendations from the optimizer
    service, such as increasing chunk overlap, switching playbooks, or enhancing
    text normalization.
    """
    from primedata.core.scope import ensure_product_access
    from primedata.ingestion_pipeline.aird_stages.config import get_aird_config
    from primedata.services.optimizer import suggest_next_config
    from primedata.services.policy_engine import evaluate_policy
    from sqlalchemy.orm.attributes import flag_modified

    logger.info(f"POST /api/v1/products/{product_id}/apply-recommendation - Action: {request_body.action}")

    try:
        product = ensure_product_access(db, request, product_id)

        # Get current optimizer recommendations to validate the action
        fingerprint_data = product.readiness_fingerprint
        fingerprint = None

        if fingerprint_data:
            if isinstance(fingerprint_data, dict):
                if "fingerprint" in fingerprint_data and isinstance(fingerprint_data["fingerprint"], dict):
                    fingerprint = fingerprint_data["fingerprint"]
                else:
                    fingerprint = fingerprint_data

        if not fingerprint:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No fingerprint data available. Run a pipeline first to generate metrics.",
            )

        # Evaluate policy and get optimizer recommendations
        config = get_aird_config()
        thresholds = {
            "min_trust_score": config.policy_min_trust_score,
            "min_secure": config.policy_min_secure,
            "min_metadata_presence": config.policy_min_metadata_presence,
            "min_kb_ready": config.policy_min_kb_ready,
        }

        policy_result = evaluate_policy(fingerprint, thresholds)
        optimizer = suggest_next_config(
            fingerprint=fingerprint,
            policy=policy_result,
            current_playbook=product.playbook_id,
        )

        applied_changes = {}
        requires_rerun = True

        # Apply the requested action
        if request_body.action == "increase_chunk_overlap":
            # Increase chunk overlap in manual settings
            current_config = product.chunking_config or {}
            manual_settings = current_config.get("manual_settings", {})

            # Get current overlap or default
            current_overlap = manual_settings.get("chunk_overlap", 200)
            chunk_size = manual_settings.get("chunk_size", 1000)

            # Calculate new overlap (increase by 20-25% or use min from config)
            increase_percent = request_body.recommendation_config.get("increase_by_percent", 20)
            min_overlap = request_body.recommendation_config.get("min_overlap", 200)

            new_overlap = max(min_overlap, int(current_overlap * (1 + increase_percent / 100)))

            # Ensure overlap doesn't exceed chunk_size - 10%
            max_overlap = int(chunk_size * 0.9)
            new_overlap = min(new_overlap, max_overlap)

            # Ensure mode is manual to apply manual settings
            if current_config.get("mode") != "manual":
                current_config["mode"] = "manual"
                # If switching from auto, preserve some auto settings
                if "auto_settings" not in current_config or not current_config.get("auto_settings"):
                    current_config["auto_settings"] = {
                        "content_type": "general",
                        "model_optimized": True,
                        "confidence_threshold": 0.7,
                    }

            # Update manual settings
            if "manual_settings" not in current_config:
                current_config["manual_settings"] = {}

            current_config["manual_settings"]["chunk_overlap"] = new_overlap
            # Ensure chunk_size is set if not already
            if "chunk_size" not in current_config["manual_settings"]:
                current_config["manual_settings"]["chunk_size"] = chunk_size
            if "chunking_strategy" not in current_config["manual_settings"]:
                current_config["manual_settings"]["chunking_strategy"] = manual_settings.get("chunking_strategy", "semantic")

            product.chunking_config = current_config
            flag_modified(product, "chunking_config")

            applied_changes = {"chunk_overlap": {"old": current_overlap, "new": new_overlap}}

            message = f"Chunk overlap increased from {current_overlap} to {new_overlap} tokens."

        elif request_body.action == "switch_playbook":
            # Switch to recommended playbook
            new_playbook_id = request_body.recommendation_config.get("playbook_id")
            if not new_playbook_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="playbook_id is required for switch_playbook action"
                )

            old_playbook_id = product.playbook_id
            product.playbook_id = new_playbook_id

            applied_changes = {"playbook_id": {"old": old_playbook_id, "new": new_playbook_id}}

            message = f"Playbook switched from {old_playbook_id} to {new_playbook_id}."

        elif request_body.action == "enhance_normalization":
            # This would require changes to the playbook or preprocessing config
            # For now, we'll add a flag to the chunking config to indicate enhanced normalization is desired
            current_config = product.chunking_config or {}
            # Preserve optimization_mode if it exists
            existing_optimization_mode = current_config.get("optimization_mode", "pattern")
            if "preprocessing_flags" not in current_config:
                current_config["preprocessing_flags"] = {}
            current_config["preprocessing_flags"]["enhanced_normalization"] = True
            current_config["preprocessing_flags"]["error_correction"] = request_body.recommendation_config.get(
                "error_correction", True
            )
            # Preserve optimization_mode
            current_config["optimization_mode"] = existing_optimization_mode

            product.chunking_config = current_config
            flag_modified(product, "chunking_config")

            applied_changes = {
                "enhanced_normalization": True,
                "error_correction": current_config["preprocessing_flags"]["error_correction"],
            }

            message = (
                "Enhanced text normalization and error correction enabled. This will be applied on the next pipeline run."
            )

        elif request_body.action == "extract_metadata":
            # Add metadata extraction flags
            current_config = product.chunking_config or {}
            # Preserve optimization_mode if it exists
            existing_optimization_mode = current_config.get("optimization_mode", "pattern")
            if "preprocessing_flags" not in current_config:
                current_config["preprocessing_flags"] = {}
            current_config["preprocessing_flags"]["extract_metadata"] = True
            current_config["preprocessing_flags"]["force_metadata_extraction"] = request_body.recommendation_config.get(
                "force_extraction", True
            )
            current_config["preprocessing_flags"]["additional_metadata_fields"] = request_body.recommendation_config.get(
                "additional_fields", True
            )
            # Preserve optimization_mode
            current_config["optimization_mode"] = existing_optimization_mode

            product.chunking_config = current_config
            flag_modified(product, "chunking_config")

            applied_changes = {
                "extract_metadata": True,
                "force_metadata_extraction": current_config["preprocessing_flags"]["force_metadata_extraction"],
                "additional_metadata_fields": current_config["preprocessing_flags"]["additional_metadata_fields"],
            }

            message = "Enhanced metadata extraction enabled. This will be applied on the next pipeline run."
            requires_rerun = True

        elif request_body.action == "error_correction":
            # Enable error correction specifically
            current_config = product.chunking_config or {}
            # Preserve optimization_mode if it exists
            existing_optimization_mode = current_config.get("optimization_mode", "pattern")
            if "preprocessing_flags" not in current_config:
                current_config["preprocessing_flags"] = {}
            current_config["preprocessing_flags"]["error_correction"] = True
            # Preserve optimization_mode
            current_config["optimization_mode"] = existing_optimization_mode

            product.chunking_config = current_config
            flag_modified(product, "chunking_config")

            applied_changes = {"error_correction": True}

            message = "Error correction enabled. This will fix OCR mistakes and typos on the next pipeline run."
            requires_rerun = True

        elif request_body.action == "apply_all_quality_improvements":
            # Apply all quality improvements at once for maximum impact
            current_config = product.chunking_config or {}
            # Preserve optimization_mode if it exists
            existing_optimization_mode = current_config.get("optimization_mode", "pattern")
            if "preprocessing_flags" not in current_config:
                current_config["preprocessing_flags"] = {}

            # Enable all quality improvements
            current_config["preprocessing_flags"]["enhanced_normalization"] = True
            current_config["preprocessing_flags"]["error_correction"] = True
            current_config["preprocessing_flags"]["extract_metadata"] = True
            # Preserve optimization_mode
            current_config["optimization_mode"] = existing_optimization_mode

            # Also increase chunk overlap if recommended
            if request_body.recommendation_config.get("increase_overlap", False):
                if "manual_settings" not in current_config:
                    current_config["manual_settings"] = {}
                current_overlap = current_config["manual_settings"].get("chunk_overlap", 200)
                new_overlap = min(int(current_overlap * 1.25), 400)  # Increase by 25%, max 400
                current_config["manual_settings"]["chunk_overlap"] = new_overlap
                applied_changes = {
                    "enhanced_normalization": True,
                    "error_correction": True,
                    "extract_metadata": True,
                    "chunk_overlap": {"old": current_overlap, "new": new_overlap},
                }
            else:
                applied_changes = {"enhanced_normalization": True, "error_correction": True, "extract_metadata": True}

            product.chunking_config = current_config
            flag_modified(product, "chunking_config")

            message = "All quality improvements enabled (enhanced normalization, error correction, metadata extraction). This will maximize AI readiness scores on the next pipeline run."
            requires_rerun = True

        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown action: {request_body.action}. Supported actions: increase_chunk_overlap, switch_playbook, enhance_normalization, error_correction, extract_metadata, apply_all_quality_improvements",
            )

        # Commit changes
        db.commit()
        db.refresh(product)

        # Log optimization_mode being used
        saved_config = product.chunking_config or {}
        optimization_mode = saved_config.get("optimization_mode", "pattern")
        logger.info(
            f"Successfully applied recommendation {request_body.action} for product {product_id}: {applied_changes}. "
            f"Optimization mode: {optimization_mode} (this will be used during next pipeline run)"
        )

        return ApplyRecommendationResponse(
            success=True, message=message, applied_changes=applied_changes, requires_pipeline_rerun=requires_rerun
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to apply recommendation for product {product_id}: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to apply recommendation: {str(e)}"
        )


class ApplyRAGRecommendationRequest(BaseModel):
    """Request model for applying a RAG quality recommendation."""
    
    recommendation_type: str = Field(..., description="Recommendation type: 'chunk_overlap', 'chunk_size', 'embedding_model', etc.")
    config: Dict[str, Any] = Field(..., description="Configuration changes to apply")


@router.get("/{product_id}/rag-recommendations")
async def get_rag_recommendations(
    product_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Get RAG quality improvement recommendations based on latest evaluation run.
    """
    from primedata.core.scope import ensure_product_access
    from primedata.db.models import EvalRun, RAGQualityMetric
    from primedata.evaluation.improvement.recommendation_engine import RecommendationEngine
    from primedata.evaluation.improvement.root_cause_analyzer import RootCauseAnalyzer

    product = ensure_product_access(db, request, product_id)

    # Get latest completed evaluation run
    latest_run = db.query(EvalRun).filter(
        EvalRun.product_id == product_id,
        EvalRun.status == 'completed'
    ).order_by(EvalRun.created_at.desc()).first()

    if not latest_run or not latest_run.metrics:
        return {
            "recommendations": [],
            "primary_recommendation": None,
            "message": "No completed evaluation runs found. Run an evaluation first."
        }

    # Get product thresholds
    thresholds = product.rag_quality_thresholds or {}
    
    # Get metrics from latest run
    metrics = latest_run.metrics.get('metrics_summary', {})
    
    # Analyze failures and generate recommendations
    root_cause_analyzer = RootCauseAnalyzer()
    recommendation_engine = RecommendationEngine()
    all_recommendations = []

    current_config = {
        "chunking_config": product.chunking_config or {},
        "embedding_config": product.embedding_config or {},
    }

    for metric_name, metric_data in metrics.items():
        avg_score = metric_data.get('average_score', 0.0)
        threshold_key = f"{metric_name}_min"
        threshold = thresholds.get(threshold_key, 0.8)  # Default threshold

        if avg_score < threshold:
            # Analyze root cause
            root_cause = root_cause_analyzer.analyze_failure(
                metric_name=metric_name,
                score=avg_score,
                threshold=threshold,
                evaluation_details=metric_data.get('details', {})
            )

            if root_cause:
                # Generate recommendation
                recommendation = recommendation_engine.generate_recommendations(
                    root_cause=root_cause,
                    metric_name=metric_name,
                    current_score=avg_score,
                    threshold=threshold,
                    current_config=current_config
                )
                if recommendation.get('recommendations'):
                    all_recommendations.extend(recommendation['recommendations'])

    return {
        "recommendations": all_recommendations,
        "primary_recommendation": all_recommendations[0] if all_recommendations else None
    }


@router.get("/{product_id}/rag-quality-gates")
async def get_rag_quality_gates(
    product_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Get RAG quality gates status based on latest evaluation run.
    
    Returns gate evaluation results showing which quality thresholds passed/failed.
    """
    from primedata.core.scope import ensure_product_access
    from primedata.db.models import EvalRun
    from primedata.evaluation.gates.gate_evaluator import GateEvaluator
    from primedata.evaluation.gates.thresholds import ThresholdManager
    
    product = ensure_product_access(db, request, product_id)
    
    # Get latest completed evaluation run
    latest_run = db.query(EvalRun).filter(
        EvalRun.product_id == product_id,
        EvalRun.status == 'completed'
    ).order_by(EvalRun.created_at.desc()).first()
    
    if not latest_run or not latest_run.metrics:
        # No evaluation run yet - return non-blocking gates
        # Quality gates should not block when no evaluation has been run
        default_thresholds = ThresholdManager.get_default_thresholds()
        gates = {}
        for key, threshold in default_thresholds.items():
            gates[key] = {
                "threshold": threshold,
                "actual": None,
                "passed": False,
                "evaluated": False  # Indicate this hasn't been evaluated yet
            }
        
        return {
            "all_passed": False,
            "blocking": False,  # Changed from True to False - don't block if no eval run
            "evaluated": False,  # New field to indicate evaluation hasn't been run
            "gates": gates,
            "message": "No evaluation run found. Run an evaluation to check quality gates."
        }
    
    # Get product thresholds (custom or defaults)
    custom_thresholds = product.rag_quality_thresholds or {}
    default_thresholds = ThresholdManager.get_default_thresholds()
    thresholds = ThresholdManager.merge_thresholds(default_thresholds, custom_thresholds)
    
    # Get aggregate metrics from latest run
    aggregate_metrics = latest_run.metrics.get('aggregate', {})
    per_query_results = latest_run.metrics.get('per_query', [])
    
    # Evaluate gates
    gate_evaluator = GateEvaluator(thresholds=thresholds)
    gate_results = gate_evaluator.evaluate_gates(
        aggregate_metrics=aggregate_metrics,
        per_query_results=per_query_results
    )
    
    # Add evaluated flag to indicate evaluation has been run
    gate_results["evaluated"] = True
    
    return gate_results


@router.post("/{product_id}/rag-quality-thresholds")
async def update_rag_quality_thresholds(
    product_id: UUID,
    request: Request,
    body: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Update RAG quality gate thresholds for a product.

    Body is a JSON object of threshold keys to values in [0.0, 1.0] (same keys as evaluation taxonomy).
    Values are merged into any existing per-product overrides.
    """
    from primedata.evaluation.gates.thresholds import ThresholdManager

    product = ensure_product_access(db, request, product_id)
    defaults = ThresholdManager.get_default_thresholds()

    if not body:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request body must include at least one threshold",
        )

    incoming: Dict[str, float] = {}
    for k, v in body.items():
        if k not in defaults:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown threshold key: {k}",
            )
        try:
            incoming[k] = float(v)
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid numeric value for threshold '{k}'",
            )

    if not ThresholdManager.validate_thresholds(incoming):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Each threshold must be a number between 0.0 and 1.0",
        )

    existing = product.rag_quality_thresholds or {}
    merged_stored = {**existing, **incoming}
    product.rag_quality_thresholds = merged_stored
    flag_modified(product, "rag_quality_thresholds")
    db.commit()
    db.refresh(product)

    effective = _effective_rag_quality_thresholds(product)
    return {"success": True, "rag_quality_thresholds": effective}


@router.post("/{product_id}/apply-rag-recommendation", response_model=ApplyRecommendationResponse)
async def apply_rag_recommendation(
    product_id: UUID,
    request_body: ApplyRAGRecommendationRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Apply a RAG quality recommendation.
    
    Updates product configuration based on evaluation results and triggers pipeline re-run.
    """
    from primedata.api.pipeline import trigger_pipeline
    from primedata.core.scope import ensure_product_access
    from sqlalchemy.orm.attributes import flag_modified

    logger.info(f"POST /api/v1/products/{product_id}/apply-rag-recommendation - Type: {request_body.recommendation_type}")

    try:
        product = ensure_product_access(db, request, product_id)
        applied_changes = {}
        requires_rerun = True

        # Apply recommendation based on type
        if request_body.recommendation_type == "increase_chunk_overlap":
            current_config = product.chunking_config or {}
            if current_config.get("mode") != "manual":
                current_config["mode"] = "manual"
            if "manual_settings" not in current_config:
                current_config["manual_settings"] = {}
            
            new_overlap = request_body.config.get("chunk_overlap")
            if new_overlap:
                current_config["manual_settings"]["chunk_overlap"] = new_overlap
                applied_changes["chunk_overlap"] = new_overlap
                product.chunking_config = current_config
                flag_modified(product, "chunking_config")

        elif request_body.recommendation_type == "increase_chunk_size":
            current_config = product.chunking_config or {}
            if current_config.get("mode") != "manual":
                current_config["mode"] = "manual"
            if "manual_settings" not in current_config:
                current_config["manual_settings"] = {}
            
            new_size = request_body.config.get("chunk_size")
            if new_size:
                current_config["manual_settings"]["chunk_size"] = new_size
                applied_changes["chunk_size"] = new_size
                product.chunking_config = current_config
                flag_modified(product, "chunking_config")

        elif request_body.recommendation_type == "upgrade_embedding_model":
            new_model = request_body.config.get("embedder_name")
            if new_model:
                current_embedding = product.embedding_config or {}
                current_embedding["embedder_name"] = new_model
                # Update dimension based on model
                from primedata.core.embedding_config import get_embedding_model_config
                model_config = get_embedding_model_config(new_model)
                if model_config:
                    current_embedding["embedding_dimension"] = model_config.dimension
                validate_embedding_config_for_workspace(db, product.workspace_id, current_embedding)
                product.embedding_config = current_embedding
                flag_modified(product, "embedding_config")
                applied_changes["embedding_model"] = new_model

        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown recommendation type: {request_body.recommendation_type}",
            )

        db.commit()

        # Trigger pipeline re-run if needed
        if requires_rerun:
            from primedata.api.pipeline import PipelineRunRequest
            pipeline_request = PipelineRunRequest(product_id=str(product_id), version=None)
            # Note: This would need to be called properly - for now just return success
            # In production, you'd trigger the pipeline asynchronously

        return ApplyRecommendationResponse(
            success=True,
            message=f"Applied {request_body.recommendation_type} recommendation",
            applied_changes=applied_changes,
            requires_pipeline_rerun=requires_rerun,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error applying RAG recommendation: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to apply recommendation: {str(e)}",
        )


@router.get("/{product_id}/validation-summary")
async def download_validation_summary(
    product_id: UUID, request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)
):
    """
    Download validation summary CSV for a product (M3).
    """
    from primedata.core.scope import ensure_product_access
    from primedata.ingestion_pipeline.aird_stages.storage import AirdStorageAdapter

    product = ensure_product_access(db, request, product_id)

    # Try to get from product model first
    if product.validation_summary_path:
        try:
            from primedata.storage.minio_client import minio_client

            # Extract bucket and key from path
            # Path format: "ws/{ws}/prod/{prod}/v/{version}/artifacts/ai_validation_summary.csv"
            # Or full MinIO path
            if product.validation_summary_path.startswith("primedata-exports/"):
                key = product.validation_summary_path.replace("primedata-exports/", "")
                bucket = "primedata-exports"
            else:
                # Assume it's a key in primedata-exports bucket
                bucket = "primedata-exports"
                key = product.validation_summary_path

            csv_data = minio_client.get_bytes(bucket, key)
            if csv_data:
                return Response(
                    content=csv_data,
                    media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="validation_summary_{product_id}.csv"'},
                )
        except Exception as e:
            logger.warning(f"Failed to load validation summary from path: {e}")

    # Fallback: try to generate on-the-fly from storage
    try:
        storage = AirdStorageAdapter(
            workspace_id=product.workspace_id,
            product_id=product.id,
            version=product.current_version,
        )

        metrics = storage.get_metrics_json()
        if metrics:
            from primedata.ingestion_pipeline.aird_stages.config import get_aird_config
            from primedata.services.reporting import generate_validation_summary

            config = get_aird_config()
            csv_content = generate_validation_summary(metrics, config.default_scoring_threshold)

            return Response(
                content=csv_content.encode("utf-8"),
                media_type="text/csv",
                headers={"Content-Disposition": f'attachment; filename="validation_summary_{product_id}.csv"'},
            )
    except Exception as e:
        logger.warning(f"Failed to generate validation summary: {e}")

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Validation summary not available for this product")


@router.get("/{product_id}/trust-report")
async def download_trust_report(
    product_id: UUID, request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)
):
    """
    Download trust report PDF for a product (M3).
    """
    from primedata.core.scope import ensure_product_access
    from primedata.ingestion_pipeline.aird_stages.storage import AirdStorageAdapter

    product = ensure_product_access(db, request, product_id)

    # Try to get from product model first
    if product.trust_report_path:
        try:
            from primedata.storage.minio_client import minio_client

            # Extract bucket and key from path
            if product.trust_report_path.startswith("primedata-exports/"):
                key = product.trust_report_path.replace("primedata-exports/", "")
                bucket = "primedata-exports"
            else:
                bucket = "primedata-exports"
                key = product.trust_report_path

            pdf_data = minio_client.get_bytes(bucket, key)
            if pdf_data:
                return Response(
                    content=pdf_data,
                    media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="trust_report_{product_id}.pdf"'},
                )
        except Exception as e:
            logger.warning(f"Failed to load trust report from path: {e}")

    # Fallback: try to generate on-the-fly from storage
    try:
        storage = AirdStorageAdapter(
            workspace_id=product.workspace_id,
            product_id=product.id,
            version=product.current_version,
        )

        metrics = storage.get_metrics_json()
        if metrics:
            from primedata.ingestion_pipeline.aird_stages.config import get_aird_config
            from primedata.services.reporting import generate_trust_report

            config = get_aird_config()
            pdf_bytes = generate_trust_report(metrics, config.default_scoring_threshold)

            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={"Content-Disposition": f'attachment; filename="trust_report_{product_id}.pdf"'},
            )
    except Exception as e:
        logger.warning(f"Failed to generate trust report: {e}")

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trust report not available for this product")


class ChunkMetadataResponse(BaseModel):
    """Chunk metadata response (M4)."""

    model_config = ConfigDict(from_attributes=True)  # Pydantic v2 syntax

    id: UUID
    chunk_id: str
    score: Optional[float]
    source_file: Optional[str]
    page_number: Optional[int]
    section: Optional[str]
    field_name: Optional[str]
    extra_tags: Optional[Dict[str, Any]]
    created_at: datetime


@router.get("/{product_id}/embedding-diagnostics")
async def get_embedding_diagnostics(
    product_id: UUID, request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)
):
    """
    Diagnostic endpoint to check embedding model configuration and status.

    Returns information about:
    - Embedding model configured for the product
    - API key status (configured/not configured)
    - Model availability and status
    - Whether hash-based fallback is being used
    """
    # Ensure user has access to the product
    ensure_product_access(db, request, product_id)

    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    # Get embedding configuration
    embedding_config = product.embedding_config or {}
    model_name = embedding_config.get("embedder_name", "minilm")
    dimension = embedding_config.get("embedding_dimension", 384)

    # Check workspace settings for API key
    workspace = db.query(Workspace).filter(Workspace.id == product.workspace_id).first()
    workspace_has_key = False
    if workspace and workspace.settings:
        workspace_has_key = bool(workspace.settings.get("openai_api_key"))

    # Check environment variable
    from primedata.core.settings import get_settings

    settings = get_settings()
    env_has_key = bool(settings.OPENAI_API_KEY)

    # Try to initialize embedding generator to check status
    from primedata.indexing.embeddings import EmbeddingGenerator

    try:
        embedder = EmbeddingGenerator(model_name=model_name, dimension=dimension, workspace_id=product.workspace_id, db=db)
        model_info = embedder.get_model_info()
        actual_dimension = embedder.get_dimension()

        is_loaded = model_info.get("is_loaded", False)
        is_openai = model_info.get("is_openai", False)
        fallback_mode = model_info.get("fallback_mode", False)
        model_type = model_info.get("model_type", "unknown")
        model_loaded = model_info.get("model_loaded", False)

        # Test embedding generation to verify actual status
        test_text = "This is a test sentence for embedding generation."
        try:
            test_embedding = embedder.embed(test_text)
            embedding_works = True
            embedding_error = None

            # Verify it's actually OpenAI if configured as such
            # Check if openai_client is set (most reliable indicator)
            if model_name.startswith("openai"):
                if hasattr(embedder, "openai_client") and embedder.openai_client is not None:
                    is_openai = True
                    fallback_mode = False
                    model_type = "openai"
                elif len(test_embedding) == dimension and dimension >= 1536:
                    # High dimension suggests OpenAI (hash-based would be different)
                    # But verify by checking if it's consistent (OpenAI embeddings are deterministic)
                    test_embedding2 = embedder.embed(test_text)
                    if np.allclose(test_embedding, test_embedding2, atol=1e-6):
                        # Consistent embeddings suggest OpenAI
                        is_openai = True
                        fallback_mode = False
                        model_type = "openai"
        except Exception as e:
            embedding_works = False
            embedding_error = str(e)
    except Exception as e:
        is_loaded = False
        is_openai = False
        fallback_mode = True
        model_type = "unknown"
        actual_dimension = dimension
        embedding_works = False
        embedding_error = str(e)

    # Get model configuration details
    from primedata.core.embedding_config import get_embedding_model_config

    model_config = get_embedding_model_config(model_name)
    model_config_details = None
    if model_config:
        model_config_details = {
            "name": model_config.name,
            "model_type": model_config.model_type.value,
            "dimension": model_config.dimension,
            "requires_api_key": model_config.requires_api_key,
            "is_available": model_config.is_available,
            "model_path": model_config.model_path if hasattr(model_config, "model_path") else None,
        }

    return {
        "product_id": str(product_id),
        "product_name": product.name,
        "embedding_config": {
            "model_name": model_name,
            "configured_dimension": dimension,
            "actual_dimension": actual_dimension,
        },
        "api_key_status": {
            "workspace_configured": workspace_has_key,
            "environment_configured": env_has_key,
            "has_api_key": workspace_has_key or env_has_key,
            "note": "OpenAI models require API key. Check workspace settings or OPENAI_API_KEY environment variable.",
        },
        "model_status": {
            "is_loaded": is_loaded,
            "is_openai": is_openai,
            "model_type": model_type,
            "using_fallback": fallback_mode,
            "embedding_works": embedding_works,
            "embedding_error": embedding_error,
        },
        "model_config": model_config_details,
        "recommendations": _get_embedding_recommendations(
            model_name, fallback_mode, workspace_has_key, env_has_key, embedding_works
        ),
    }


def _get_embedding_recommendations(
    model_name: str, fallback_mode: bool, workspace_has_key: bool, env_has_key: bool, embedding_works: bool
) -> List[str]:
    """Generate recommendations based on diagnostic results."""
    recommendations = []

    if fallback_mode:
        recommendations.append(
            "⚠️ CRITICAL: Using hash-based fallback embeddings. Semantic search will NOT work correctly. "
            "Results will be random and irrelevant."
        )

    if "openai" in model_name.lower():
        if not workspace_has_key and not env_has_key:
            recommendations.append(
                "❌ OpenAI API key not configured. Configure it in workspace settings or set OPENAI_API_KEY environment variable."
            )
        elif not embedding_works:
            recommendations.append("❌ OpenAI API key is configured but embedding generation failed. Check API key validity.")
        else:
            recommendations.append("✅ OpenAI API key is configured and working correctly.")

    if not embedding_works and not fallback_mode:
        recommendations.append("❌ Embedding generation failed. Check model installation and configuration.")

    if not fallback_mode and embedding_works:
        recommendations.append("✅ Embedding model is working correctly. Semantic search should function properly.")

    return recommendations


@router.get("/{product_id}/chunk-metadata", response_model=List[ChunkMetadataResponse])
async def list_chunk_metadata(
    product_id: UUID,
    request: Request,
    version: Optional[int] = Query(None, description="Filter by version"),
    section: Optional[str] = Query(None, description="Filter by section"),
    field_name: Optional[str] = Query(None, description="Filter by field name"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    List chunk metadata for a product (M4).
    """
    from primedata.core.scope import ensure_product_access
    from primedata.services.vector_metadata import get_chunk_metadata

    product = ensure_product_access(db, request, product_id)

    # Default version/collection from latest successful indexed run so UI matches Qdrant
    # even when products.current_version lags pipeline_run.version.
    chunk_collection_name: Optional[str] = None
    if version is None:
        # DB enum `pipelinerunstatus` may not include READY_WITH_WARNINGS (see legacy migrations);
        # only SUCCEEDED is safe for all deployments.
        success_statuses = (PipelineRunStatus.SUCCEEDED,)
        base_q = db.query(PipelineRun).filter(
            PipelineRun.product_id == product_id,
            PipelineRun.status.in_(success_statuses),
        )
        latest_indexed = (
            base_q.filter(PipelineRun.collection_name.isnot(None))
            .order_by(PipelineRun.version.desc(), PipelineRun.created_at.desc())
            .first()
        )
        if latest_indexed:
            version = latest_indexed.version
            chunk_collection_name = latest_indexed.collection_name
        else:
            latest = (
                base_q.order_by(PipelineRun.version.desc(), PipelineRun.created_at.desc()).first()
            )
            if latest:
                version = latest.version
            else:
                version = product.current_version

    metadata = get_chunk_metadata(
        db=db,
        product_id=product_id,
        version=version,
        section=section,
        field_name=field_name,
        limit=limit,
        offset=offset,
        collection_name=chunk_collection_name,
    )

    # Metadata is now returned as dicts from Qdrant, not ORM objects
    # Map dict keys to ChunkMetadataResponse fields
    result = []
    for m in metadata:
        # Map Qdrant payload fields to response model
        result.append(
            ChunkMetadataResponse(
                id=uuid_uuid4(),  # Generate new UUID for response (not stored in Qdrant)
                chunk_id=m.get("chunk_id", ""),
                score=m.get("score"),
                source_file=m.get("source_file"),
                page_number=m.get("page_number"),
                section=m.get("section"),
                field_name=m.get("field_name"),
                extra_tags=m.get("extra_tags"),
                created_at=(
                    datetime.fromisoformat(m.get("created_at", datetime.utcnow().isoformat()))
                    if isinstance(m.get("created_at"), str)
                    else m.get("created_at", datetime.utcnow())
                ),
            )
        )
    return result


class CostEstimateRequest(BaseModel):
    """Request model for cost estimation (M5)."""

    playbook_id: Optional[str] = None  # REGULATORY/SCANNED/TECH/None


class CostEstimateResponse(BaseModel):
    """Response model for cost estimation (M5)."""

    filename: str
    playbook: str
    estimated_tokens: int
    estimated_chunks: int
    price_model: Dict[str, float]
    estimated_cost_usd: float


@router.post("/estimate", response_model=CostEstimateResponse, status_code=status.HTTP_200_OK)
async def estimate_cost(
    request: Request,
    file: UploadFile = File(...),
    playbook_id: Optional[str] = Form(None),  # REGULATORY/SCANNED/TECH/None
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Estimate cost for creating AI-ready data from a file (M5).

    Lightweight estimate endpoint:
      • Extracts text from file
      • Selects playbook (forced or via router)
      • Reads chunking.max_tokens from that playbook YAML
      • Computes estimated chunks and cost
    Does NOT create a Product or run the full pipeline.
    """
    import math
    import shutil
    import tempfile
    from pathlib import Path

    from primedata.ingestion_pipeline.aird_stages.playbooks.loader import load_playbook_yaml
    from primedata.ingestion_pipeline.aird_stages.playbooks.router import resolve_playbook_file, route_playbook
    from primedata.ingestion_pipeline.aird_stages.utils.text_processing import tokens_estimate

    # Create temp file
    tmp_dir = Path(tempfile.gettempdir()) / "primedata_estimates"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / file.filename

    try:
        # 1) Save temp file
        with tmp_path.open("wb") as buf:
            shutil.copyfileobj(file.file, buf)

        # 2) Extract text - use simple text extraction for estimate
        try:
            # For cost estimation, we'll use a simple text extraction
            # In production, this should match the actual preprocessing extraction logic
            if tmp_path.suffix.lower() == ".txt":
                text = tmp_path.read_text(encoding="utf-8", errors="ignore")
            elif tmp_path.suffix.lower() == ".pdf":
                # Try PDF extraction if available
                try:
                    import PyPDF2

                    with tmp_path.open("rb") as f:
                        pdf_reader = PyPDF2.PdfReader(f)
                        text = "\n".join([page.extract_text() for page in pdf_reader.pages])
                except ImportError:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="PDF extraction requires PyPDF2. Please install it or use a .txt file.",
                    )
            else:
                # Try to read as text
                text = tmp_path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            logger.error(f"Failed to extract text: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to extract text for estimate: {e}",
            )

        if not text.strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No text extracted from file.")

        # 3) Choose playbook (forced or via router)
        if playbook_id and playbook_id.upper() in {"REGULATORY", "SCANNED", "TECH"}:
            pb_id = playbook_id.upper()
        else:
            # Use router to select playbook
            pb_id, _ = route_playbook(sample_text=text[:1000], filename=file.filename)

        # 4) Load chunking config to get max_tokens
        playbook_file = resolve_playbook_file(pb_id)
        if not playbook_file:
            # Fallback to default
            chunk_cfg = {"max_tokens": 900}
        else:
            try:
                playbook_data = load_playbook_yaml(playbook_file)
                chunk_cfg = playbook_data.get("chunking", {}) or {}
            except Exception as e:
                logger.warning(f"Failed to load playbook {pb_id}: {e}, using defaults")
                chunk_cfg = {}

        max_tokens = int(chunk_cfg.get("max_tokens", 900) or 900)

        # 5) Estimate tokens using same heuristic as preprocess
        token_est = tokens_estimate(text)

        # 6) Estimate chunk count
        est_chunks = max(1, math.ceil(token_est / max_tokens)) if max_tokens > 0 else 1

        # 7) Simple cost model (adjust to your real infra/API costs)
        PRICE_PREPROC_PER_1K = 0.0001  # $ per 1k tokens for preprocessing
        PRICE_EMBED_PER_1K = 0.0002  # $ per 1k tokens for embedding
        total_per_1k = PRICE_PREPROC_PER_1K + PRICE_EMBED_PER_1K

        est_cost = (token_est / 1000.0) * total_per_1k

        logger.info(
            f"Cost estimate: file={file.filename}, playbook={pb_id}, tokens={token_est}, chunks={est_chunks}, cost=${est_cost:.6f}"
        )

        return CostEstimateResponse(
            filename=file.filename,
            playbook=pb_id,
            estimated_tokens=token_est,
            estimated_chunks=est_chunks,
            price_model={
                "preprocess_per_1k_tokens": PRICE_PREPROC_PER_1K,
                "embed_per_1k_tokens": PRICE_EMBED_PER_1K,
                "total_per_1k_tokens": total_per_1k,
            },
            estimated_cost_usd=round(est_cost, 6),
        )

    finally:
        # Cleanup
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception as e:
            logger.warning(f"Failed to cleanup temp file {tmp_path}: {e}")


class ContentAnalysisRequest(BaseModel):
    content: str
    filename: Optional[str] = None


class ContentAnalysisResponse(BaseModel):
    content_type: str
    confidence: float
    recommended_config: Dict[str, Any]
    reasoning: str


class ChunkingPreviewRequest(BaseModel):
    content: str
    config: Dict[str, Any]


class ChunkingPreviewResponse(BaseModel):
    total_chunks: int
    avg_chunk_size: float
    min_chunk_size: int
    max_chunk_size: int
    estimated_retrieval_quality: str
    preview_chunks: List[Dict[str, Any]]


@router.post("/{product_id}/analyze-content", response_model=ContentAnalysisResponse)
async def analyze_content(
    product_id: UUID,
    request_body: ContentAnalysisRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Analyze content and recommend optimal chunking configuration.
    """
    # Ensure user has access to the product
    product = ensure_product_access(db, request, product_id)

    try:
        # Analyze content
        chunking_config = content_analyzer.analyze_content(request_body.content, request_body.filename)

        return ContentAnalysisResponse(
            content_type=chunking_config.content_type.value,
            confidence=chunking_config.confidence,
            recommended_config={
                "chunk_size": chunking_config.chunk_size,
                "chunk_overlap": chunking_config.chunk_overlap,
                "min_chunk_size": chunking_config.min_chunk_size,
                "max_chunk_size": chunking_config.max_chunk_size,
                "strategy": chunking_config.strategy.value,
            },
            reasoning=chunking_config.reasoning,
        )

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Content analysis failed: {str(e)}")


@router.post("/{product_id}/preview-chunking", response_model=ChunkingPreviewResponse)
async def preview_chunking(
    product_id: UUID,
    request_body: ChunkingPreviewRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Preview how content would be chunked with given configuration.
    """
    # Ensure user has access to the product
    product = ensure_product_access(db, request, product_id)

    try:
        # Create ChunkingConfig object from request
        from primedata.analysis.content_analyzer import ChunkingConfig, ChunkingStrategy, ContentType

        config = ChunkingConfig(
            chunk_size=request_body.config.get("chunk_size", 1000),
            chunk_overlap=request_body.config.get("chunk_overlap", 200),
            min_chunk_size=request_body.config.get("min_chunk_size", 100),
            max_chunk_size=request_body.config.get("max_chunk_size", 2000),
            strategy=ChunkingStrategy(request_body.config.get("strategy", "fixed_size")),
            content_type=ContentType(request_body.config.get("content_type", "general")),
            confidence=1.0,
            reasoning="User preview",
        )

        # Generate preview
        preview = content_analyzer.preview_chunking(request_body.content, config)

        return ChunkingPreviewResponse(
            total_chunks=preview["total_chunks"],
            avg_chunk_size=preview["avg_chunk_size"],
            min_chunk_size=preview["min_chunk_size"],
            max_chunk_size=preview["max_chunk_size"],
            estimated_retrieval_quality=preview["estimated_retrieval_quality"],
            preview_chunks=preview["chunks"],
        )

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Chunking preview failed: {str(e)}")


@router.post("/{product_id}/auto-configure-chunking")
async def auto_configure_chunking(
    product_id: UUID, request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)
):
    """
    Automatically configure chunking settings based on product's data sources.
    Uses AirdStorageAdapter to properly extract text from PDFs and other formats.
    """
    # Ensure user has access to the product
    product = ensure_product_access(db, request, product_id)

    try:
        # Use AirdStorageAdapter to properly extract text from files (handles PDFs)
        from primedata.ingestion_pipeline.aird_stages.storage import AirdStorageAdapter
        from primedata.db.models import RawFile
        from primedata.analysis.content_analyzer import content_analyzer

        # Get raw files for the product
        version = product.current_version or 1
        raw_files = db.query(RawFile).filter(
            RawFile.product_id == product_id,
            RawFile.version == version,
            RawFile.status != "DELETED"
        ).limit(3).all()  # Sample first 3 files
        
        if not raw_files:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="No raw files found to analyze. Please run data ingestion first."
            )
        
        # Use storage adapter to extract text (handles PDFs properly)
        storage = AirdStorageAdapter(
            workspace_id=product.workspace_id,
            product_id=product_id,
            version=version
        )
        
        sample_content = ""
        filename_hint = None
        for raw_file in raw_files:
            try:
                # Use get_raw_text which handles PDF extraction
                file_stem = raw_file.file_stem
                text = storage.get_raw_text(
                    file_stem,
                    minio_key=raw_file.storage_key,
                    minio_bucket=raw_file.storage_bucket
                )
                if text:
                    sample_content += text[:5000]  # First 5000 chars per file
                    if not filename_hint:
                        filename_hint = raw_file.filename
                    if len(sample_content) > 15000:  # Limit total sample size
                        break
            except Exception as e:
                logger.warning(f"Failed to extract text from {raw_file.filename}: {e}")
                continue
        
        if not sample_content or len(sample_content.strip()) < 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="Insufficient content found to analyze. Please ensure files contain extractable text."
            )
        
        # Analyze content and get recommended configuration
        chunking_config = content_analyzer.analyze_content(
            content=sample_content,
            filename=filename_hint
        )

        # Update product configuration
        current_config = product.chunking_config or {}
        current_config.update(
            {
                "mode": "auto",
                "auto_settings": {
                    "content_type": chunking_config.content_type.value,
                    "model_optimized": True,
                    "confidence_threshold": 0.7,
                },
                "manual_settings": {
                    "chunk_size": chunking_config.chunk_size,
                    "chunk_overlap": chunking_config.chunk_overlap,
                    "min_chunk_size": chunking_config.min_chunk_size,
                    "max_chunk_size": chunking_config.max_chunk_size,
                    "chunking_strategy": chunking_config.strategy.value,
                },
                "last_analyzed": datetime.utcnow().isoformat(),
                "analysis_confidence": chunking_config.confidence,
            }
        )

        product.chunking_config = current_config
        db.commit()

        return {
            "message": "Chunking configuration updated automatically",
            "content_type": chunking_config.content_type.value,
            "confidence": chunking_config.confidence,
            "reasoning": chunking_config.reasoning,
            "recommended_config": {
                "chunk_size": chunking_config.chunk_size,
                "chunk_overlap": chunking_config.chunk_overlap,
                "min_chunk_size": chunking_config.min_chunk_size,
                "max_chunk_size": chunking_config.max_chunk_size,
                "strategy": chunking_config.strategy.value,
            },
        }

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Auto-configuration failed: {str(e)}")


class PromoteVersionRequest(BaseModel):
    """Request model for promoting a version to production."""

    version: int
    force_override: bool = Field(default=False, description="Force promotion even if quality gates fail")


@router.post("/{product_id}/promote")
async def promote_version(
    product_id: UUID,
    request_body: PromoteVersionRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Promote a specific version to production by setting up a Qdrant alias.
    """
    # Log promotion attempt with full context
    user_id = current_user.get("user_id") or current_user.get("id") or "unknown"
    user_email = current_user.get("email") or "unknown"
    version = request_body.version
    force_override = request_body.force_override
    
    logger.info(
        f"PROMOTION ATTEMPT: User {user_id} ({user_email}) attempting to promote version {version} "
        f"for product {product_id}. Force override: {force_override}. "
        f"Request IP: {request.client.host if request.client else 'unknown'}"
    )
    
    # Ensure user has access to the product
    product = ensure_product_access(db, request, product_id)

    if getattr(product, "vector_creation_enabled", True):
        validate_embedding_config_for_workspace(db, product.workspace_id, product.embedding_config)

    # Log current state before promotion
    current_promoted = product.promoted_version
    current_version = product.current_version
    logger.info(
        f"PROMOTION STATE: Product {product_id} ({product.name}) - "
        f"Current promoted_version: {current_promoted}, current_version: {current_version}, "
        f"Requested promotion to version: {version}"
    )

    # Check if the version exists and has succeeded
    pipeline_run = (
        db.query(PipelineRun)
        .filter(
            PipelineRun.product_id == product_id,
            PipelineRun.version == version,
            PipelineRun.status == PipelineRunStatus.SUCCEEDED,
        )
        .first()
    )

    if not pipeline_run:
        # Check if pipeline run exists with different status
        pipeline_run_any_status = db.query(PipelineRun).filter(
            PipelineRun.product_id == product_id,
            PipelineRun.version == version
        ).first()
        
        if pipeline_run_any_status:
            logger.warning(
                f"PROMOTION VALIDATION FAILED: User {user_id} ({user_email}) attempted to promote version {version} "
                f"for product {product_id}, but pipeline run exists with status '{pipeline_run_any_status.status.value}' "
                f"(not 'succeeded'). Pipeline run ID: {pipeline_run_any_status.id}"
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Version {version} exists but has status '{pipeline_run_any_status.status.value}', not 'succeeded'. Cannot promote a version that hasn't completed successfully."
            )
        else:
            logger.warning(
                f"PROMOTION VALIDATION FAILED: User {user_id} ({user_email}) attempted to promote version {version} "
                f"for product {product_id}, but no pipeline run found for this version."
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Version {version} not found. Please run the pipeline for this version first."
            )
    
    # Store pipeline_run_id for artifact lookup
    pipeline_run_id = pipeline_run.id

    # Check quality gates unless force_override is True
    if not request_body.force_override:
        from primedata.db.models import EvalRun
        from primedata.evaluation.gates.gate_evaluator import GateEvaluator
        from primedata.evaluation.gates.thresholds import ThresholdManager
        
        # Get latest completed evaluation run for this version or any version
        latest_run = db.query(EvalRun).filter(
            EvalRun.product_id == product_id,
            EvalRun.status == 'completed'
        ).order_by(EvalRun.created_at.desc()).first()
        
        if latest_run and latest_run.metrics:
            # Get product thresholds
            custom_thresholds = product.rag_quality_thresholds or {}
            default_thresholds = ThresholdManager.get_default_thresholds()
            thresholds = ThresholdManager.merge_thresholds(default_thresholds, custom_thresholds)
            
            # Get aggregate metrics from latest run
            aggregate_metrics = latest_run.metrics.get('aggregate', {})
            per_query_results = latest_run.metrics.get('per_query', [])
            
            # Evaluate gates
            gate_evaluator = GateEvaluator(thresholds=thresholds)
            gate_results = gate_evaluator.evaluate_gates(
                aggregate_metrics=aggregate_metrics,
                per_query_results=per_query_results
            )
            
            # If gates are blocking, reject promotion
            if gate_results.get('blocking', False):
                failed_gates = [
                    name for name, gate in gate_results.get('gates', {}).items()
                    if not gate.get('passed', False)
                ]
                logger.warning(
                    f"PROMOTION BLOCKED BY QUALITY GATES: User {user_id} ({user_email}) attempted to promote version {version} "
                    f"for product {product_id}, but quality gates failed. Failed gates: {', '.join(failed_gates)}"
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Quality gates failed. Failed gates: {', '.join(failed_gates)}. Use force_override=true to promote anyway."
                )
        else:
            # No evaluation run - warn but don't block (allows first-time promotion)
            # Could optionally block here if you want eval runs to be mandatory
            pass

    try:
        from primedata.indexing.qdrant_client import qdrant_client

        if not qdrant_client.is_connected():
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Qdrant client not connected")

        # Check if vector creation is enabled
        if product.vector_creation_enabled is False:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot promote version {version}: Vector creation is disabled for this product. Enable vector creation in product settings to promote versions."
            )

        # Fetch the actual collection name from the pipeline artifact (more reliable than reconstructing)
        # Try multiple approaches to find the artifact:
        # 1. By pipeline_run_id (most reliable - direct relationship)
        # 2. By product_id + version + stage + type
        vector_artifact = None
        
        # First, try to find through pipeline run relationship
        if pipeline_run_id:
            vector_artifact = db.query(PipelineArtifact).filter(
                PipelineArtifact.pipeline_run_id == pipeline_run_id,
                PipelineArtifact.stage_name == "indexing",
                PipelineArtifact.artifact_type == ArtifactType.VECTOR,
                PipelineArtifact.status == ArtifactStatus.ACTIVE
            ).first()
        
        # If not found, try by product_id + version (fallback)
        if not vector_artifact:
            vector_artifact = db.query(PipelineArtifact).filter(
                PipelineArtifact.product_id == product_id,
                PipelineArtifact.version == version,
                PipelineArtifact.stage_name == "indexing",
                PipelineArtifact.artifact_type == ArtifactType.VECTOR,
                PipelineArtifact.status == ArtifactStatus.ACTIVE
            ).first()

        # If still not found, try without status filter (in case artifact exists but status changed)
        if not vector_artifact:
            if pipeline_run_id:
                vector_artifact = db.query(PipelineArtifact).filter(
                    PipelineArtifact.pipeline_run_id == pipeline_run_id,
                    PipelineArtifact.stage_name == "indexing",
                    PipelineArtifact.artifact_type == ArtifactType.VECTOR
                ).first()
            
            if not vector_artifact:
                vector_artifact = db.query(PipelineArtifact).filter(
                    PipelineArtifact.product_id == product_id,
                    PipelineArtifact.version == version,
                    PipelineArtifact.stage_name == "indexing",
                    PipelineArtifact.artifact_type == ArtifactType.VECTOR
                ).first()

        if not vector_artifact:
            # Check if any indexing artifacts exist for this version/pipeline run (for debugging)
            all_indexing_artifacts = []
            if pipeline_run_id:
                all_indexing_artifacts = db.query(PipelineArtifact).filter(
                    PipelineArtifact.pipeline_run_id == pipeline_run_id,
                    PipelineArtifact.stage_name == "indexing"
                ).all()
            
            if not all_indexing_artifacts:
                all_indexing_artifacts = db.query(PipelineArtifact).filter(
                    PipelineArtifact.product_id == product_id,
                    PipelineArtifact.version == version,
                    PipelineArtifact.stage_name == "indexing"
                ).all()
            
            error_detail = f"Cannot promote version {version}: No indexing artifact found."
            
            if all_indexing_artifacts:
                artifact_info = []
                for art in all_indexing_artifacts:
                    artifact_info.append(f"type={art.artifact_type.value}, status={art.status.value}, name={art.artifact_name}")
                error_detail += f" Found {len(all_indexing_artifacts)} indexing artifact(s): {', '.join(artifact_info)}."
            
            # Check if there are artifacts for other versions
            other_version_artifacts = db.query(PipelineArtifact).filter(
                PipelineArtifact.product_id == product_id,
                PipelineArtifact.stage_name == "indexing",
                PipelineArtifact.artifact_type == ArtifactType.VECTOR,
                PipelineArtifact.status == ArtifactStatus.ACTIVE
            ).distinct(PipelineArtifact.version).with_entities(PipelineArtifact.version).all()
            
            if other_version_artifacts:
                available_versions = [v[0] for v in other_version_artifacts]
                available_versions.sort(reverse=True)
                error_detail += f" Available versions with indexing artifacts: {', '.join(map(str, available_versions))}."
            
            error_detail += " Please ensure the indexing stage completed successfully for this version."
            
            logger.warning(
                f"Promotion failed for version {version} (pipeline_run_id={pipeline_run_id}): {error_detail}. "
                f"Pipeline run status: {pipeline_run.status.value}"
            )
            
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_detail
            )

        # Get collection name from PipelineRun (primary source - enterprise-grade)
        collection_name = None
        if pipeline_run and pipeline_run.collection_name:
            collection_name = pipeline_run.collection_name
            logger.info(f"Found collection name from PipelineRun: {collection_name}")
        
        if not collection_name:
            # Fallback: reconstruct collection name if not stored in PipelineRun
            sanitized_name = qdrant_client._sanitize_collection_name(product.name)
            collection_name = f"ws_{product.workspace_id}__{sanitized_name}__v_{version}"
            logger.warning(
                f"Collection name not found in PipelineRun for version {version}, "
                f"using reconstructed name: {collection_name}"
            )

        # Verify the collection actually exists in Qdrant
        collections = qdrant_client.client.get_collections()
        collection_exists = any(col.name == collection_name for col in collections.collections)

        if not collection_exists:
            # Try alternative collection name format (product_id based) as fallback
            alt_collection_name = f"ws_{product.workspace_id}__prod_{product_id}__v_{version}"
            collection_exists = any(col.name == alt_collection_name for col in collections.collections)

            if collection_exists:
                collection_name = alt_collection_name
                logger.info(f"Found collection using alternative format: {collection_name}")
            else:
                # Find available collections for this product to suggest alternatives
                available_versions = []
                product_collections = [
                    col.name for col in collections.collections
                    if (f"ws_{product.workspace_id}__" in col.name and
                        (str(product_id) in col.name or product.name.lower().replace(" ", "_") in col.name.lower()))
                ]

                # Extract version numbers from collection names
                import re
                for col_name in product_collections:
                    version_match = re.search(r'__v_(\d+)', col_name)
                    if version_match:
                        available_versions.append(int(version_match.group(1)))

                available_versions.sort(reverse=True)

                error_msg = (
                    f"Cannot promote version {version}: Collection does not exist in Qdrant. "
                    f"Expected collection '{collection_name}' or '{alt_collection_name}'. "
                )

                if available_versions:
                    error_msg += (
                        f"Available versions with collections: {', '.join(map(str, available_versions))}. "
                        f"Please promote one of these versions or run the pipeline for version {version} first."
                    )
                else:
                    error_msg += (
                        f"No collections found for this product. "
                        f"Please run the pipeline for version {version} first to create the collection."
                    )

                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=error_msg
                )

        # Set the production alias in Qdrant using the actual collection name
        sanitized_name = qdrant_client._sanitize_collection_name(product.name)
        alias_name = f"prod_ws_{product.workspace_id}__{sanitized_name}"
        
        # Use the collection name we found (either from artifact or verified in Qdrant)
        success = qdrant_client.set_prod_alias(
            workspace_id=str(product.workspace_id),
            product_id=str(product_id),
            version=version,
            product_name=product.name
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to set production alias in Qdrant for collection '{collection_name}'. "
                       f"Please verify the collection exists and try again."
            )

        # Update the product's promoted_version
        old_promoted_version = product.promoted_version
        product.promoted_version = version
        db.commit()
        db.refresh(product)
        
        # Log successful promotion with full details
        logger.info(
            f"PROMOTION SUCCESS: Version {version} promoted to production for product {product_id} ({product.name}). "
            f"Previous promoted_version: {old_promoted_version} -> New promoted_version: {version}. "
            f"Promoted by user {user_id} ({user_email}). "
            f"Force override used: {force_override}. "
            f"Collection: {collection_name}, Alias: {alias_name}"
        )

        return {
            "message": f"Version {version} promoted to production successfully",
            "promoted_version": version,
            "alias_name": alias_name,
            "collection_name": collection_name,
        }

    except HTTPException as http_exc:
        # Log HTTP exceptions (validation errors, etc.)
        logger.warning(
            f"PROMOTION FAILED (HTTP): User {user_id} ({user_email}) failed to promote version {version} "
            f"for product {product_id}. Status: {http_exc.status_code}, Detail: {http_exc.detail}"
        )
        raise
    except Exception as e:
        # Log unexpected errors
        logger.error(
            f"PROMOTION FAILED (ERROR): User {user_id} ({user_email}) failed to promote version {version} "
            f"for product {product_id}. Error: {str(e)}",
            exc_info=True
        )
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to promote version: {str(e)}")


