"""
API endpoints for embedding model configuration.

This module provides REST API endpoints to serve embedding model configurations
to the frontend, ensuring consistency and centralized management.
"""

from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from primedata.core.scope import ensure_workspace_access
from primedata.core.security import get_current_user
from primedata.db.database import get_db

from ..core.embedding_config import EmbeddingModelConfig, EmbeddingModelRegistry, EmbeddingModelType
from ..core.provider_capabilities import embedding_model_enabled_for_workspace

router = APIRouter(prefix="/api/v1/embedding-models", tags=["embedding-models"])


class EmbeddingModelResponse(BaseModel):
    """Response model for embedding model information."""

    id: str
    name: str
    description: str
    dimension: int
    requires_api_key: bool
    cost_per_token: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None
    enabled: bool = True
    disabled_reason: Optional[str] = None


class EmbeddingModelsListResponse(BaseModel):
    """Response model for list of embedding models."""

    models: List[EmbeddingModelResponse]
    total: int


def _model_to_response(
    model: EmbeddingModelConfig,
    db: Session,
    workspace_id: Optional[UUID],
) -> EmbeddingModelResponse:
    enabled, disabled_reason = embedding_model_enabled_for_workspace(db, workspace_id, model)
    return EmbeddingModelResponse(
        id=model.id,
        name=model.name,
        description=model.description,
        dimension=model.dimension,
        requires_api_key=model.requires_api_key,
        cost_per_token=model.cost_per_token,
        metadata=model.metadata,
        enabled=enabled,
        disabled_reason=disabled_reason,
    )


@router.get("/", response_model=EmbeddingModelsListResponse)
async def get_embedding_models(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    model_type: EmbeddingModelType = Query(None, description="Filter by model type"),
    free_only: bool = Query(False, description="Show only free models (no API key required)"),
    paid_only: bool = Query(False, description="Show only paid models (require API key)"),
    workspace_id: Optional[UUID] = Query(
        None,
        description="When set, paid models are enabled only if the matching provider API key is configured for this workspace.",
    ),
):
    """
    Get all available embedding models.

    Args:
        model_type: Filter by specific model type
        free_only: Show only models that don't require API keys
        paid_only: Show only models that require API keys
        workspace_id: Optional workspace scope for provider key checks (requires access)

    Returns:
        List of available embedding models
    """
    try:
        if workspace_id is not None:
            ensure_workspace_access(db, request, workspace_id)

        # Get models based on filters
        if model_type:
            models = EmbeddingModelRegistry.get_models_by_type(model_type)
        elif free_only:
            models = EmbeddingModelRegistry.get_free_models()
        elif paid_only:
            models = EmbeddingModelRegistry.get_paid_models()
        else:
            models = EmbeddingModelRegistry.get_available_models()

        # Convert to response format (enabled/disabled reflects workspace + env keys when workspace_id set)
        model_responses = [_model_to_response(model, db, workspace_id) for model in models]

        return EmbeddingModelsListResponse(models=model_responses, total=len(model_responses))

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve embedding models: {str(e)}")


@router.get("/{model_id}", response_model=EmbeddingModelResponse)
async def get_embedding_model(
    request: Request,
    model_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    workspace_id: Optional[UUID] = Query(
        None,
        description="When set, include enabled/disabled based on workspace provider keys.",
    ),
):
    """
    Get specific embedding model configuration.

    Args:
        model_id: The ID of the embedding model

    Returns:
        Embedding model configuration
    """
    try:
        model = EmbeddingModelRegistry.get_model(model_id)

        if not model:
            raise HTTPException(status_code=404, detail=f"Embedding model '{model_id}' not found")

        if not model.is_available:
            raise HTTPException(status_code=400, detail=f"Embedding model '{model_id}' is not available")

        if workspace_id is not None:
            ensure_workspace_access(db, request, workspace_id)

        return _model_to_response(model, db, workspace_id)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve embedding model: {str(e)}")


@router.get("/{model_id}/dimension")
async def get_embedding_model_dimension(model_id: str):
    """
    Get the embedding dimension for a specific model.

    Args:
        model_id: The ID of the embedding model

    Returns:
        Embedding dimension
    """
    try:
        dimension = EmbeddingModelRegistry.get_model_dimension(model_id)

        if dimension is None:
            raise HTTPException(status_code=404, detail=f"Embedding model '{model_id}' not found")

        return {"model_id": model_id, "dimension": dimension}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve embedding dimension: {str(e)}")


@router.get("/{model_id}/validate")
async def validate_embedding_model(model_id: str):
    """
    Validate if an embedding model ID is valid and available.

    Args:
        model_id: The ID of the embedding model to validate

    Returns:
        Validation result
    """
    try:
        is_valid = EmbeddingModelRegistry.validate_model_id(model_id)

        return {"model_id": model_id, "is_valid": is_valid, "is_available": is_valid}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to validate embedding model: {str(e)}")


@router.get("/types/", response_model=List[str])
async def get_embedding_model_types():
    """
    Get all available embedding model types.

    Returns:
        List of available model types
    """
    try:
        return [model_type.value for model_type in EmbeddingModelType]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve model types: {str(e)}")
