"""
Settings API router for managing workspace and user settings.
"""

from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from primedata.core.scope import ensure_workspace_access
from primedata.core.security import get_current_user
from primedata.core.provider_capabilities import openai_api_key_configured
from primedata.db.database import get_db
from primedata.db.models import Workspace
from pydantic import BaseModel
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/v1/settings", tags=["Settings"])


class SettingsResponse(BaseModel):
    """Settings response model."""

    workspace_id: str
    openai_api_key: Optional[str] = None  # Masked key (shows only last 4 chars)
    openai_api_key_configured: bool = False
    # True if OpenAI embeddings/API can run: workspace key and/or server OPENAI_API_KEY
    openai_available_for_embeddings: bool = False


class SettingsUpdateRequest(BaseModel):
    """Settings update request model."""

    openai_api_key: Optional[str] = None


@router.get("/workspace/{workspace_id}", response_model=SettingsResponse)
async def get_workspace_settings(
    workspace_id: UUID, request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)
):
    """
    Get workspace settings.

    Returns settings with masked API keys for security.
    """
    # Ensure user has access to the workspace
    ensure_workspace_access(db, request, workspace_id)

    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    # Get settings from workspace.settings JSON column
    settings = workspace.settings or {}
    openai_key = settings.get("openai_api_key")

    # Mask the API key for display (show only last 4 characters)
    masked_key = None
    if openai_key:
        masked_key = f"sk-...{openai_key[-4:]}" if len(openai_key) > 4 else "sk-****"

    return SettingsResponse(
        workspace_id=str(workspace_id),
        openai_api_key=masked_key,
        openai_api_key_configured=bool(openai_key),
        openai_available_for_embeddings=openai_api_key_configured(db, workspace_id),
    )


@router.patch("/workspace/{workspace_id}", response_model=SettingsResponse)
async def update_workspace_settings(
    workspace_id: UUID,
    request_body: SettingsUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Update workspace settings.

    Stores API keys securely in the workspace settings JSON column.
    """
    # Ensure user has access to the workspace
    ensure_workspace_access(db, request, workspace_id)

    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    # Initialize settings if it doesn't exist
    if workspace.settings is None:
        workspace.settings = {}

    # Update OpenAI API key if provided
    if request_body.openai_api_key is not None:
        # If empty string, remove the key
        if request_body.openai_api_key.strip() == "":
            workspace.settings.pop("openai_api_key", None)
        else:
            # Validate that it starts with sk- (basic validation)
            if not request_body.openai_api_key.startswith("sk-"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid OpenAI API key format. OpenAI keys should start with 'sk-'",
                )
            workspace.settings["openai_api_key"] = request_body.openai_api_key.strip()

    db.commit()
    db.refresh(workspace)

    # Get updated settings
    settings = workspace.settings or {}
    openai_key = settings.get("openai_api_key")

    # Mask the API key for response
    masked_key = None
    if openai_key:
        masked_key = f"sk-...{openai_key[-4:]}" if len(openai_key) > 4 else "sk-****"

    return SettingsResponse(
        workspace_id=str(workspace_id),
        openai_api_key=masked_key,
        openai_api_key_configured=bool(openai_key),
        openai_available_for_embeddings=openai_api_key_configured(db, workspace_id),
    )



