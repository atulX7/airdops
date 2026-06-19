"""
Resolve which paid/provider-backed features are available for a workspace.

Today embedding models that require an API key are OpenAI-only; this module
centralizes that check so API, UI, and product validation stay consistent.
"""

from __future__ import annotations

from typing import Optional, Tuple
from uuid import UUID

from sqlalchemy.orm import Session

from primedata.core.embedding_config import EmbeddingModelConfig, EmbeddingModelType
from primedata.core.settings import get_settings
from primedata.db.models import Workspace


def openai_api_key_configured(db: Optional[Session], workspace_id: Optional[UUID]) -> bool:
    """
    True if OpenAI can be used: global env key and/or workspace-stored key.

    When workspace_id is omitted, only the environment variable is considered
    (useful for workers or unscoped calls).
    """
    settings = get_settings()
    if getattr(settings, "OPENAI_API_KEY", None):
        return True
    if db is not None and workspace_id is not None:
        ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
        if ws and ws.settings and ws.settings.get("openai_api_key"):
            return True
    return False


def embedding_model_enabled_for_workspace(
    db: Optional[Session],
    workspace_id: Optional[UUID],
    model: EmbeddingModelConfig,
) -> Tuple[bool, Optional[str]]:
    """
    Whether an embedding model can be selected/used for this workspace context.

    Returns (enabled, disabled_reason). Local models are always enabled.
    """
    if not model.requires_api_key:
        return True, None

    if model.model_type == EmbeddingModelType.OPENAI:
        if openai_api_key_configured(db, workspace_id):
            return True, None
        return (
            False,
            "OpenAI API key required. Add it in Workspace Settings (API & Integrations) or set OPENAI_API_KEY on the server.",
        )

    # Future: HuggingFace token, custom providers, etc.
    return True, None


def assert_embedding_model_allowed_for_workspace(
    db: Session,
    workspace_id: UUID,
    model: EmbeddingModelConfig,
) -> None:
    """Raise HTTPException if the embedding model is not allowed."""
    from fastapi import HTTPException, status

    enabled, reason = embedding_model_enabled_for_workspace(db, workspace_id, model)
    if not enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=reason or "This embedding model is not available for the current workspace configuration.",
        )
