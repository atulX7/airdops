"""
S3 content storage service for PrimeData.

Handles saving and loading text/YAML content to/from S3 (MinIO) for large content fields.
"""

from typing import Optional
from uuid import UUID

from loguru import logger
from primedata.storage.minio_client import MinIOClient
from primedata.storage.paths import (
    playbook_prefix,
    eval_prefix,
    rag_logs_prefix,
    eval_dataset_prefix,
    compliance_reports_prefix,
    pipeline_runs_prefix,
    safe_filename,
)

# Bucket for storing content
CONTENT_BUCKET = "primedata-exports"


def save_text_to_s3(
    s3_path: str,
    content: str,
    content_type: str = "text/plain",
    minio_client: Optional[MinIOClient] = None,
) -> bool:
    """Save text content to S3.

    Args:
        s3_path: S3 path (key) where to save
        content: Text content to save
        content_type: MIME type (default: text/plain)
        minio_client: Optional MinIO client (creates new one if not provided)

    Returns:
        True if successful, False otherwise
    """
    try:
        client = minio_client or MinIOClient()
        success = client.put_bytes(CONTENT_BUCKET, s3_path, content.encode("utf-8"), content_type)
        if success:
            logger.info(f"Saved text content to S3: {s3_path}")
        else:
            logger.error(f"Failed to save text content to S3: {s3_path}")
        return success
    except Exception as e:
        logger.error(f"Error saving text content to S3 {s3_path}: {e}", exc_info=True)
        return False


def load_text_from_s3(s3_path: str, minio_client: Optional[MinIOClient] = None) -> Optional[str]:
    """Load text content from S3.

    Args:
        s3_path: S3 path (key) to the text object
        minio_client: Optional MinIO client (creates new one if not provided)

    Returns:
        Text content or None if failed
    """
    try:
        client = minio_client or MinIOClient()
        data = client.get_bytes(CONTENT_BUCKET, s3_path)
        if data:
            content = data.decode("utf-8")
            logger.debug(f"Loaded text content from S3: {s3_path}")
            return content
        else:
            logger.warning(f"Failed to load text content from S3: {s3_path}")
            return None
    except Exception as e:
        logger.error(f"Error loading text content from S3 {s3_path}: {e}", exc_info=True)
        return None


def get_playbook_yaml_path(workspace_id: UUID, playbook_id: UUID) -> str:
    """Get S3 path for playbook YAML content.

    Args:
        workspace_id: Workspace UUID
        playbook_id: Playbook UUID

    Returns:
        S3 path string
    """
    return f"{playbook_prefix(workspace_id, playbook_id)}content.yaml"


def get_pipeline_run_metrics_path(workspace_id: UUID, product_id: UUID, version: int, pipeline_run_id: UUID) -> str:
    """Get S3 path for pipeline run metrics.

    Args:
        workspace_id: Workspace UUID
        product_id: Product UUID
        version: Version number
        pipeline_run_id: Pipeline run UUID

    Returns:
        S3 path string
    """
    return f"{pipeline_runs_prefix(workspace_id, product_id, version)}{pipeline_run_id}/metrics.json"


def get_eval_run_trend_data_path(workspace_id: UUID, product_id: UUID, version: int, eval_run_id: UUID) -> str:
    """Get S3 path for eval run trend data.

    Args:
        workspace_id: Workspace UUID
        product_id: Product UUID
        version: Version number
        eval_run_id: Eval run UUID

    Returns:
        S3 path string
    """
    return f"{eval_prefix(workspace_id, product_id, version)}{eval_run_id}/trend_data.json"


def get_rag_log_response_path(workspace_id: UUID, product_id: UUID, version: int, log_id: UUID) -> str:
    """Get S3 path for RAG log response.

    Args:
        workspace_id: Workspace UUID
        product_id: Product UUID
        version: Version number
        log_id: Log UUID

    Returns:
        S3 path string
    """
    return f"{rag_logs_prefix(workspace_id, product_id, version)}{log_id}/response.txt"


def get_eval_dataset_item_answer_path(workspace_id: UUID, product_id: UUID, dataset_id: UUID, item_id: UUID) -> str:
    """Get S3 path for eval dataset item expected answer.

    Args:
        workspace_id: Workspace UUID
        product_id: Product UUID
        dataset_id: Dataset UUID
        item_id: Item UUID

    Returns:
        S3 path string
    """
    return f"{eval_dataset_prefix(workspace_id, product_id, dataset_id)}items/{item_id}/expected_answer.txt"


def get_compliance_report_data_path(workspace_id: UUID, report_id: UUID) -> str:
    """Get S3 path for compliance report data.

    Args:
        workspace_id: Workspace UUID
        report_id: Report UUID

    Returns:
        S3 path string
    """
    return f"{compliance_reports_prefix(workspace_id)}{report_id}/report_data.json"

