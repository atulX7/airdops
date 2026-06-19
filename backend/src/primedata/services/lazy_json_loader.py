"""
Lazy JSON loader service for PrimeData.

Provides transparent loading of JSON fields from either PostgreSQL or S3,
maintaining backward compatibility during the migration.
"""

from typing import Any, Dict, Optional
from uuid import UUID

from loguru import logger
from primedata.services.s3_json_storage import load_json_from_s3
from primedata.storage.minio_client import MinIOClient


def load_product_json_field(product: Any, field_name: str, minio_client: Optional[MinIOClient] = None) -> Optional[Any]:
    """Load product JSON field from S3 if path exists, else from DB.

    This function provides backward compatibility:
    - If S3 path exists (e.g., chunk_metrics_path), load from S3
    - Else if DB field exists (e.g., chunk_metrics), return from DB
    - Else return None

    Args:
        product: Product SQLAlchemy model instance
        field_name: Name of the field (e.g., "chunk_metrics", "readiness_fingerprint")
        minio_client: Optional MinIO client

    Returns:
        JSON data (dict/list) or None
    """
    try:
        # Check for S3 path field (e.g., chunk_metrics_path)
        path_field_name = f"{field_name}_path"
        s3_path = getattr(product, path_field_name, None)

        if s3_path:
            # Load from S3
            logger.debug(f"Loading {field_name} from S3: {s3_path}")
            return load_json_from_s3(s3_path, minio_client)

        # Fallback to DB field
        db_field = getattr(product, field_name, None)
        if db_field is not None:
            logger.debug(f"Loading {field_name} from DB")
            return db_field

        # Field doesn't exist
        logger.debug(f"Field {field_name} not found in S3 or DB")
        return None
    except Exception as e:
        logger.error(f"Error loading {field_name} for product {product.id}: {e}", exc_info=True)
        return None


def load_pipeline_run_metrics(pipeline_run: Any, minio_client: Optional[MinIOClient] = None) -> Dict[str, Any]:
    """Load pipeline run metrics from S3 if archived, else from DB.

    Args:
        pipeline_run: PipelineRun SQLAlchemy model instance
        minio_client: Optional MinIO client

    Returns:
        Metrics dictionary (empty dict if not found)
    """
    try:
        # Check if metrics are archived to S3
        metrics_path = getattr(pipeline_run, "metrics_path", None)
        if metrics_path:
            logger.debug(f"Loading metrics from S3: {metrics_path}")
            metrics = load_json_from_s3(metrics_path, minio_client)
            if metrics is not None:
                return metrics

        # Fallback to DB field
        db_metrics = getattr(pipeline_run, "metrics", None)
        if db_metrics:
            logger.debug("Loading metrics from DB")
            return db_metrics if isinstance(db_metrics, dict) else {}

        # Return empty dict if not found
        logger.debug("Metrics not found in S3 or DB")
        return {}
    except Exception as e:
        logger.error(f"Error loading metrics for pipeline run {pipeline_run.id}: {e}", exc_info=True)
        return {}


def save_product_json_field_with_auto_storage(
    product: Any,
    field_name: str,
    data: Any,
    minio_client: Optional[MinIOClient] = None,
    threshold: int = 1024 * 1024,  # 1MB default
) -> bool:
    """Save product JSON field, automatically choosing DB or S3 based on size.

    Updates both the DB field and S3 path field as needed.

    Args:
        product: Product SQLAlchemy model instance
        field_name: Name of the field
        data: Python object to save
        minio_client: Optional MinIO client
        threshold: Size threshold for S3 storage

    Returns:
        True if successful, False otherwise
    """
    try:
        from primedata.services.s3_json_storage import save_json_to_s3, should_save_to_s3

        # Determine if should save to S3
        if should_save_to_s3(data, threshold):
            # Save to S3
            s3_path = save_json_to_s3(product.workspace_id, product.id, field_name, data, minio_client)
            if s3_path:
                # Update S3 path field
                path_field_name = f"{field_name}_path"
                setattr(product, path_field_name, s3_path)
                # Clear DB field
                setattr(product, field_name, None)
                logger.info(f"Saved {field_name} to S3 and cleared DB field")
                return True
            else:
                logger.error(f"Failed to save {field_name} to S3, keeping in DB")
                # Fallback: save to DB
                setattr(product, field_name, data)
                return False
        else:
            # Save to DB
            setattr(product, field_name, data)
            # Clear S3 path if exists
            path_field_name = f"{field_name}_path"
            if hasattr(product, path_field_name):
                setattr(product, path_field_name, None)
            logger.debug(f"Saved {field_name} to DB (small size)")
            return True
    except Exception as e:
        logger.error(f"Error saving {field_name} for product {product.id}: {e}", exc_info=True)
        return False



