"""
Path helper functions for organizing data in MinIO storage.
"""

import uuid
from typing import Union


def raw_prefix(workspace_id: Union[str, uuid.UUID], product_id: Union[str, uuid.UUID], version: int) -> str:
    """Generate prefix for raw data storage.

    Args:
        workspace_id: Workspace identifier
        product_id: Product identifier
        version: Version number

    Returns:
        Storage prefix string like "ws/{ws}/prod/{prod}/v/{version}/raw/"
    """
    return f"ws/{workspace_id}/prod/{product_id}/v/{version}/raw/"


def clean_prefix(workspace_id: Union[str, uuid.UUID], product_id: Union[str, uuid.UUID], version: int) -> str:
    """Generate prefix for cleaned data storage.

    Args:
        workspace_id: Workspace identifier
        product_id: Product identifier
        version: Version number

    Returns:
        Storage prefix string like "ws/{ws}/prod/{prod}/v/{version}/clean/"
    """
    return f"ws/{workspace_id}/prod/{product_id}/v/{version}/clean/"


def chunk_prefix(workspace_id: Union[str, uuid.UUID], product_id: Union[str, uuid.UUID], version: int) -> str:
    """Generate prefix for chunked data storage.

    Args:
        workspace_id: Workspace identifier
        product_id: Product identifier
        version: Version number

    Returns:
        Storage prefix string like "ws/{ws}/prod/{prod}/v/{version}/chunk/"
    """
    return f"ws/{workspace_id}/prod/{product_id}/v/{version}/chunk/"


def embed_prefix(workspace_id: Union[str, uuid.UUID], product_id: Union[str, uuid.UUID], version: int) -> str:
    """Generate prefix for embedded data storage.

    Args:
        workspace_id: Workspace identifier
        product_id: Product identifier
        version: Version number

    Returns:
        Storage prefix string like "ws/{ws}/prod/{prod}/v/{version}/embed/"
    """
    return f"ws/{workspace_id}/prod/{product_id}/v/{version}/embed/"


def export_prefix(workspace_id: Union[str, uuid.UUID], product_id: Union[str, uuid.UUID], version: int) -> str:
    """Generate prefix for exported data storage.

    Args:
        workspace_id: Workspace identifier
        product_id: Product identifier
        version: Version number

    Returns:
        Storage prefix string like "ws/{ws}/prod/{prod}/v/{version}/export/"
    """
    return f"ws/{workspace_id}/prod/{product_id}/v/{version}/export/"


def playbook_prefix(workspace_id: Union[str, uuid.UUID], playbook_id: Union[str, uuid.UUID]) -> str:
    """Generate prefix for playbook storage.

    Args:
        workspace_id: Workspace identifier
        playbook_id: Playbook identifier

    Returns:
        Storage prefix string like "ws/{ws}/playbooks/{playbook_id}/"
    """
    return f"ws/{workspace_id}/playbooks/{playbook_id}/"


def eval_prefix(workspace_id: Union[str, uuid.UUID], product_id: Union[str, uuid.UUID], version: int) -> str:
    """Generate prefix for evaluation data storage.

    Args:
        workspace_id: Workspace identifier
        product_id: Product identifier
        version: Version number

    Returns:
        Storage prefix string like "ws/{ws}/prod/{prod}/v/{version}/eval/"
    """
    return f"ws/{workspace_id}/prod/{product_id}/v/{version}/eval/"


def rag_logs_prefix(workspace_id: Union[str, uuid.UUID], product_id: Union[str, uuid.UUID], version: int) -> str:
    """Generate prefix for RAG request logs storage.

    Args:
        workspace_id: Workspace identifier
        product_id: Product identifier
        version: Version number

    Returns:
        Storage prefix string like "ws/{ws}/prod/{prod}/v/{version}/rag_logs/"
    """
    return f"ws/{workspace_id}/prod/{product_id}/v/{version}/rag_logs/"


def eval_dataset_prefix(workspace_id: Union[str, uuid.UUID], product_id: Union[str, uuid.UUID], dataset_id: Union[str, uuid.UUID]) -> str:
    """Generate prefix for evaluation dataset storage.

    Args:
        workspace_id: Workspace identifier
        product_id: Product identifier
        dataset_id: Dataset identifier

    Returns:
        Storage prefix string like "ws/{ws}/prod/{prod}/eval_datasets/{dataset_id}/"
    """
    return f"ws/{workspace_id}/prod/{product_id}/eval_datasets/{dataset_id}/"


def compliance_reports_prefix(workspace_id: Union[str, uuid.UUID]) -> str:
    """Generate prefix for compliance reports storage.

    Args:
        workspace_id: Workspace identifier

    Returns:
        Storage prefix string like "ws/{ws}/compliance/reports/"
    """
    return f"ws/{workspace_id}/compliance/reports/"


def pipeline_runs_prefix(workspace_id: Union[str, uuid.UUID], product_id: Union[str, uuid.UUID], version: int) -> str:
    """Generate prefix for pipeline runs storage.

    Args:
        workspace_id: Workspace identifier
        product_id: Product identifier
        version: Version number

    Returns:
        Storage prefix string like "ws/{ws}/prod/{prod}/v/{version}/pipeline_runs/"
    """
    return f"ws/{workspace_id}/prod/{product_id}/v/{version}/pipeline_runs/"


def safe_filename(filename: str) -> str:
    """Convert filename to safe storage key by removing/replacing unsafe characters.

    Args:
        filename: Original filename

    Returns:
        Safe filename for storage
    """
    import re

    # Replace unsafe characters with underscores
    safe = re.sub(r"[^\w\-_\.]", "_", filename)
    # Remove multiple consecutive underscores
    safe = re.sub(r"_+", "_", safe)
    # Remove leading/trailing underscores
    safe = safe.strip("_")
    return safe or "unnamed_file"
