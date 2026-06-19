"""
Lineage and data-quality recording helpers.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import UUID

from loguru import logger
from sqlalchemy.orm import Session

from primedata.db.models import DataQualityFinding, LineageRecord, LineageType, RuleSeverity


def record_lineage(
    db: Optional[Session],
    *,
    workspace_id: UUID,
    product_id: UUID,
    lineage_type: LineageType,
    pipeline_run_id: Optional[UUID] = None,
    raw_file_id: Optional[UUID] = None,
    chunk_id: Optional[str] = None,
    vector_id: Optional[str] = None,
    metadata_id: Optional[str] = None,
    source_file: Optional[str] = None,
    page_start: Optional[int] = None,
    page_end: Optional[int] = None,
    transformation: Optional[str] = None,
    transform_version: Optional[str] = None,
    model_name: Optional[str] = None,
    model_version: Optional[str] = None,
    status: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """Persist a lineage record; safe no-op if db is None."""
    if db is None:
        logger.debug("record_lineage skipped (db session missing)")
        return
    try:
        rec = LineageRecord(
            workspace_id=workspace_id,
            product_id=product_id,
            pipeline_run_id=pipeline_run_id,
            raw_file_id=raw_file_id,
            lineage_type=lineage_type,
            chunk_id=chunk_id,
            vector_id=vector_id,
            metadata_id=metadata_id,
            source_file=source_file,
            page_start=page_start,
            page_end=page_end,
            transformation=transformation,
            transform_version=transform_version,
            model_name=model_name,
            model_version=model_version,
            status=status,
            details=details or {},
        )
        db.add(rec)
        db.flush()
    except Exception as e:
        logger.warning(f"record_lineage failed for {lineage_type} (chunk_id={chunk_id}, vector_id={vector_id}): {e}")


def record_dq_finding(
    db: Optional[Session],
    *,
    workspace_id: UUID,
    product_id: UUID,
    rule_name: str,
    severity: RuleSeverity = RuleSeverity.WARNING,
    passed: bool = True,
    pipeline_run_id: Optional[UUID] = None,
    raw_file_id: Optional[UUID] = None,
    chunk_id: Optional[str] = None,
    vector_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """Persist a data-quality finding; safe no-op if db is None."""
    if db is None:
        logger.debug("record_dq_finding skipped (db session missing)")
        return
    try:
        finding = DataQualityFinding(
            workspace_id=workspace_id,
            product_id=product_id,
            pipeline_run_id=pipeline_run_id,
            raw_file_id=raw_file_id,
            chunk_id=chunk_id,
            vector_id=vector_id,
            rule_name=rule_name,
            severity=severity,
            passed=passed,
            details=details or {},
        )
        db.add(finding)
        db.flush()
    except Exception as e:
        logger.warning(f"record_dq_finding failed for rule {rule_name}: {e}")
