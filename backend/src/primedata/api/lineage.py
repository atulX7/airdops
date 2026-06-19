from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from loguru import logger
from sqlalchemy.orm import Session

from primedata.core.scope import ensure_product_access
from primedata.db.database import get_db
from primedata.db.models import DataQualityFinding, LineageRecord
from primedata.core.security import get_current_user

router = APIRouter(prefix="/api/v1/lineage", tags=["lineage"])


def _ensure_product(request: Request, db: Session, product_id: UUID):
    return ensure_product_access(db, request, product_id)


@router.get("/{product_id}/runs/{pipeline_run_id}", response_model=dict)
def get_lineage_for_run(
    product_id: UUID,
    pipeline_run_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    lineage_type: Optional[str] = Query(None, description="Filter by lineage type"),
) -> dict:
    """Return lineage records for a given product + pipeline run."""
    _ensure_product(request, db, product_id)

    query = db.query(LineageRecord).filter(
        LineageRecord.product_id == product_id,
        LineageRecord.pipeline_run_id == pipeline_run_id,
    )
    if lineage_type:
        query = query.filter(LineageRecord.lineage_type == lineage_type)

    records = query.order_by(LineageRecord.created_at.asc()).all()
    return {"count": len(records), "records": [lr_to_dict(r) for r in records]}


@router.get("/{product_id}/overview", response_model=dict)
def get_lineage_overview(
    product_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Lightweight overview: chunk/vector counts and data-quality findings."""
    _ensure_product(request, db, product_id)

    chunk_count = (
        db.query(LineageRecord)
        .filter(LineageRecord.product_id == product_id, LineageRecord.lineage_type == "chunk")
        .count()
    )
    vector_count = (
        db.query(LineageRecord)
        .filter(LineageRecord.product_id == product_id, LineageRecord.lineage_type == "vector")
        .count()
    )
    dq_failures = (
        db.query(DataQualityFinding)
        .filter(DataQualityFinding.product_id == product_id, DataQualityFinding.passed == False)  # noqa: E712
        .count()
    )

    return {
        "chunk_count": chunk_count,
        "vector_count": vector_count,
        "dq_failures": dq_failures,
    }


def lr_to_dict(r: LineageRecord) -> dict:
    return {
        "id": str(r.id),
        "lineage_type": r.lineage_type.value if hasattr(r.lineage_type, "value") else str(r.lineage_type),
        "chunk_id": r.chunk_id,
        "vector_id": r.vector_id,
        "metadata_id": r.metadata_id,
        "source_file": r.source_file,
        "page_start": r.page_start,
        "page_end": r.page_end,
        "transformation": r.transformation,
        "transform_version": r.transform_version,
        "model_name": r.model_name,
        "model_version": r.model_version,
        "status": r.status,
        "details": r.details,
        "created_at": r.created_at,
    }
