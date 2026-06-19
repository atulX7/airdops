"""
Violation archiver service for PrimeData.

Archives old data quality violations to S3 to reduce PostgreSQL storage costs.
"""

import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

from loguru import logger
from primedata.db.models import DqViolation
from primedata.services.s3_json_storage import METADATA_BUCKET, save_json_to_s3
from primedata.storage.minio_client import MinIOClient
from sqlalchemy import and_
from sqlalchemy.orm import Session


def archive_old_violations(
    db: Session, days: int = 90, batch_size: int = 1000, minio_client=None, hard_delete: bool = False
) -> dict:
    """Archive violations older than specified days to S3.

    Args:
        db: Database session
        days: Number of days to keep violations in DB (default: 90)
        batch_size: Number of violations to process per batch (default: 1000)
        minio_client: Optional MinIO client
        hard_delete: If True, delete from DB after archiving (default: False)

    Returns:
        Dictionary with archiving statistics
    """
    cutoff_date = datetime.utcnow() - timedelta(days=days)

    # Find violations older than cutoff that haven't been archived yet
    violations_to_archive = (
        db.query(DqViolation)
        .filter(and_(DqViolation.created_at < cutoff_date, DqViolation.archived_to_s3 == False))  # Not yet archived
        .limit(batch_size)
        .all()
    )

    archived_count = 0
    failed_count = 0
    deleted_count = 0

    # Group violations by product_id and version for efficient archiving
    violations_by_product = {}
    for violation in violations_to_archive:
        key = (violation.product_id, violation.version)
        if key not in violations_by_product:
            violations_by_product[key] = []
        violations_by_product[key].append(violation)

    client = minio_client or MinIOClient()

    for (product_id, version), violations in violations_by_product.items():
        try:
            # Convert violations to JSON-serializable format
            violations_data = []
            for v in violations:
                violations_data.append(
                    {
                        "id": str(v.id),
                        "product_id": str(v.product_id),
                        "version": v.version,
                        "pipeline_run_id": str(v.pipeline_run_id) if v.pipeline_run_id else None,
                        "rule_name": v.rule_name,
                        "rule_type": v.rule_type,
                        "severity": v.severity.value,
                        "message": v.message,
                        "details": v.details,
                        "affected_count": v.affected_count,
                        "total_count": v.total_count,
                        "violation_rate": v.violation_rate,
                        "created_at": v.created_at.isoformat() if v.created_at else None,
                    }
                )

            # Save to S3 as JSON
            # Path: ws/{workspace_id}/prod/{product_id}/v/{version}/violations/{timestamp}.json
            # We need to get workspace_id from product
            from primedata.db.models import Product

            product = db.query(Product).filter(Product.id == product_id).first()
            if not product:
                logger.warning(f"Product {product_id} not found, skipping violations")
                failed_count += len(violations)
                continue

            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            s3_key = f"ws/{product.workspace_id}/prod/{product_id}/v/{version}/violations/archived_{timestamp}.json"

            success = client.put_json(METADATA_BUCKET, s3_key, violations_data)

            if success:
                # Mark violations as archived
                for v in violations:
                    v.archived_to_s3 = True
                    v.archived_at = datetime.utcnow()

                archived_count += len(violations)

                # Hard delete if requested
                if hard_delete:
                    for v in violations:
                        db.delete(v)
                    deleted_count += len(violations)

                logger.info(f"Archived {len(violations)} violations for product {product_id} v{version} to S3: {s3_key}")
            else:
                failed_count += len(violations)
                logger.error(f"Failed to archive violations for product {product_id} v{version}")
        except Exception as e:
            failed_count += len(violations)
            logger.error(f"Error archiving violations for product {product_id} v{version}: {e}", exc_info=True)

    # Commit all changes
    if archived_count > 0:
        db.commit()
        logger.info(f"Archived {archived_count} violations, failed {failed_count}, deleted {deleted_count}")

    return {
        "archived_count": archived_count,
        "failed_count": failed_count,
        "deleted_count": deleted_count,
        "cutoff_date": cutoff_date.isoformat(),
    }


def load_archived_violations(product_id: UUID, version: int, minio_client=None) -> List[Dict[str, Any]]:
    """Load archived violations from S3 for a product/version.

    Args:
        product_id: Product UUID
        version: Version number
        minio_client: Optional MinIO client

    Returns:
        List of violation dictionaries
    """
    try:
        from primedata.db.database import get_db
        from primedata.db.models import Product

        db = next(get_db())
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            logger.error(f"Product {product_id} not found")
            return []

        client = minio_client or MinIOClient()

        # List all archived violation files for this product/version
        prefix = f"ws/{product.workspace_id}/prod/{product_id}/v/{version}/violations/"
        objects = client.list_objects(METADATA_BUCKET, prefix=prefix)

        all_violations = []
        for obj in objects:
            if obj["name"].startswith(prefix) and "archived_" in obj["name"]:
                violations = client.get_json(METADATA_BUCKET, obj["name"])
                if violations:
                    all_violations.extend(violations)

        logger.info(f"Loaded {len(all_violations)} archived violations for product {product_id} v{version}")
        return all_violations
    except Exception as e:
        logger.error(f"Error loading archived violations for product {product_id} v{version}: {e}", exc_info=True)
        return []



