"""Validate product embedding_config against workspace / server provider keys."""

from typing import Any, Dict
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from primedata.core.embedding_config import get_embedding_model_config
from primedata.core.provider_capabilities import assert_embedding_model_allowed_for_workspace


def validate_embedding_config_for_workspace(
    db: Session, workspace_id: UUID, embedding_config: Dict[str, Any] | None
) -> None:
    """
    Reject unknown embedders and paid models when no matching API key is configured.

    Used by product APIs, pipeline trigger, playground, evaluation, and promotion.
    """
    cfg = embedding_config if isinstance(embedding_config, dict) else {}
    embedder = cfg.get("embedder_name", "minilm")
    model = get_embedding_model_config(embedder)
    if not model:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown embedding model: {embedder}",
        )
    assert_embedding_model_allowed_for_workspace(db, workspace_id, model)
