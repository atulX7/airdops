"""
Playbooks API router.

Provides endpoints for listing and retrieving playbook configurations.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

import yaml
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from loguru import logger
from primedata.core.scope import ensure_workspace_access
from primedata.core.security import get_current_user
from primedata.db.database import get_db
from primedata.db.models import CustomPlaybook
from primedata.ingestion_pipeline.aird_stages.playbooks import list_playbooks, load_playbook_yaml, refresh_index
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/v1/playbooks", tags=["Playbooks"])


class PlaybookInfo(BaseModel):
    """Playbook information."""

    id: str
    description: str
    path: str


class PlaybookResponse(BaseModel):
    """Full playbook configuration response."""

    id: str
    description: str
    config: Dict[str, Any]


@router.get("/{playbook_id}/yaml")
async def get_playbook_yaml(
    playbook_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Get playbook YAML content as plain text.
    Supports both built-in and custom playbooks.
    """
    try:
        # Try custom playbook first (if table exists)
        try:
            custom_playbook = (
                db.query(CustomPlaybook)
                .filter(CustomPlaybook.playbook_id == playbook_id.upper(), CustomPlaybook.is_active == True)
                .first()
            )

            if custom_playbook:
                from primedata.core.scope import ensure_workspace_access
                from primedata.services.s3_content_storage import load_text_from_s3

                ensure_workspace_access(db, request, custom_playbook.workspace_id)
                # Load YAML content from S3
                yaml_content = load_text_from_s3(custom_playbook.yaml_content_path)
                if yaml_content is None:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND, detail=f"Playbook YAML content not found in storage"
                    )
                return {"yaml": yaml_content, "is_custom": True}
        except Exception as db_error:
            # If table doesn't exist or other DB error, log and continue to file-based lookup
            if "does not exist" in str(db_error) or "UndefinedTable" in str(type(db_error).__name__):
                logger.debug(f"Custom playbooks table not available, using file-based lookup: {db_error}")
            else:
                logger.warning(f"Error querying custom playbooks, falling back to file-based: {db_error}")

        # Try built-in playbook
        from primedata.ingestion_pipeline.aird_stages.playbooks.router import resolve_playbook_file

        playbook_path = resolve_playbook_file(playbook_id)

        if playbook_path and playbook_path.exists():
            with open(playbook_path, "r", encoding="utf-8") as f:
                yaml_content = f.read()
            return {"yaml": yaml_content, "is_custom": False}

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Playbook '{playbook_id}' not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get playbook YAML: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get playbook YAML: {str(e)}")


@router.get("/", response_model=List[PlaybookInfo])
async def list_available_playbooks(
    request: Request,
    workspace_id: Optional[UUID] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    List all available playbooks.

    Returns all playbooks found in the configured playbook directory,
    including TECH, SCANNED, REGULATORY, and any other playbooks.
    """
    try:
        # Refresh the playbook index to ensure we have the latest playbooks
        refresh_index()
        playbook_map = list_playbooks()

        if not playbook_map:
            logger.warning("No playbooks found in configured directory")
            return []

        playbooks = []

        # Sort by playbook ID (case-insensitive) for consistent ordering
        sorted_items = sorted(playbook_map.items(), key=lambda x: x[0].lower())

        for playbook_id, path in sorted_items:
            try:
                # Load playbook to get description and actual ID from YAML
                config = load_playbook_yaml(playbook_id)
                # Use the ID from the YAML file, or fallback to uppercase version of the key
                playbook_id_from_yaml = config.get("id", playbook_id.upper())
                playbooks.append(
                    PlaybookInfo(
                        id=playbook_id_from_yaml,
                        description=config.get("description", "No description"),
                        path=str(path),
                    )
                )
            except Exception as e:
                logger.warning(f"Failed to load playbook {playbook_id}: {e}")
                # Still include it with minimal info using the filename as ID
                playbooks.append(
                    PlaybookInfo(
                        id=playbook_id.upper(),
                        description="Playbook available but failed to load",
                        path=str(path),
                    )
                )

        # Add custom playbooks if workspace_id is provided
        if workspace_id:
            try:
                from primedata.core.scope import ensure_workspace_access

                ensure_workspace_access(db, request, workspace_id)

                custom_playbooks = (
                    db.query(CustomPlaybook)
                    .filter(CustomPlaybook.workspace_id == workspace_id, CustomPlaybook.is_active == True)
                    .all()
                )

                for custom_pb in custom_playbooks:
                    playbooks.append(
                        PlaybookInfo(
                            id=custom_pb.playbook_id,
                            description=custom_pb.description or f"Custom playbook: {custom_pb.name}",
                            path=f"custom:{custom_pb.id}",  # Mark as custom
                        )
                    )
            except Exception as e:
                logger.warning(f"Failed to load custom playbooks: {e}")

        return playbooks
    except Exception as e:
        logger.error(f"Failed to list playbooks: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to list playbooks")


@router.get("/{playbook_id}", response_model=PlaybookResponse)
async def get_playbook(
    playbook_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Get playbook configuration by ID.
    Supports both built-in playbooks (from files) and custom playbooks (from database).
    """
    try:
        # First try to load from database (custom playbooks) - if table exists
        try:
            custom_playbook = (
                db.query(CustomPlaybook)
                .filter(CustomPlaybook.playbook_id == playbook_id.upper(), CustomPlaybook.is_active == True)
                .first()
            )

            if custom_playbook:
                # Check workspace access
                from primedata.core.scope import ensure_workspace_access

                ensure_workspace_access(db, request, custom_playbook.workspace_id)

                # Load and parse YAML content from S3
                from primedata.services.s3_content_storage import load_text_from_s3

                yaml_content = load_text_from_s3(custom_playbook.yaml_content_path)
                if yaml_content is None:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND, detail=f"Playbook YAML content not found in storage"
                    )

                try:
                    config = yaml.safe_load(yaml_content)
                    return PlaybookResponse(
                        id=config.get("id", custom_playbook.playbook_id),
                        description=custom_playbook.description or config.get("description", "Custom playbook"),
                        config=config,
                    )
                except yaml.YAMLError as e:
                    logger.error(f"Failed to parse custom playbook YAML: {e}")
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Invalid YAML in custom playbook: {str(e)}"
                    )
        except Exception as db_error:
            # If table doesn't exist, just skip custom playbook lookup
            if "does not exist" in str(db_error) or "UndefinedTable" in str(type(db_error).__name__):
                logger.debug(f"Custom playbooks table not available, using file-based lookup: {db_error}")
            else:
                logger.warning(f"Error querying custom playbooks, falling back to file-based: {db_error}")

        # Fallback to built-in playbooks (from files)
        config = load_playbook_yaml(playbook_id)
        return PlaybookResponse(
            id=config.get("id", playbook_id.upper()),
            description=config.get("description", "No description"),
            config=config,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Playbook '{playbook_id}' not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to load playbook {playbook_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to load playbook: {str(e)}")


# Custom Playbook Endpoints


class CustomPlaybookCreateRequest(BaseModel):
    name: str
    playbook_id: str
    description: Optional[str] = None
    yaml_content: str
    base_playbook_id: Optional[str] = None


class CustomPlaybookUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    yaml_content: Optional[str] = None


class CustomPlaybookResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)  # Pydantic v2 syntax

    id: UUID
    workspace_id: UUID
    owner_user_id: UUID
    name: str
    playbook_id: str
    description: Optional[str]
    yaml_content_path: str
    base_playbook_id: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime]
    
    @property
    def yaml_content(self) -> str:
        """Load YAML content from S3 (for backward compatibility)."""
        from primedata.services.s3_content_storage import load_text_from_s3
        content = load_text_from_s3(self.yaml_content_path)
        if content is None:
            raise ValueError(f"YAML content not found at {self.yaml_content_path}")
        return content


@router.post("/custom", response_model=CustomPlaybookResponse, status_code=status.HTTP_201_CREATED)
async def create_custom_playbook(
    request_body: CustomPlaybookCreateRequest,
    request: Request,
    workspace_id: UUID = Query(..., description="Workspace ID"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Create a custom playbook based on an existing playbook or from scratch.
    """
    from primedata.core.scope import ensure_workspace_access
    from primedata.core.user_utils import get_user_id
    from primedata.services.s3_content_storage import CONTENT_BUCKET

    ensure_workspace_access(db, request, workspace_id)

    # Validate YAML
    try:
        config = yaml.safe_load(request_body.yaml_content)
        if not isinstance(config, dict):
            raise ValueError("YAML must be a dictionary")
        # Ensure playbook has required fields
        if "id" not in config:
            config["id"] = request_body.playbook_id.upper()
    except yaml.YAMLError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid YAML: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid playbook configuration: {str(e)}")

    # Check if playbook_id already exists in this workspace
    try:
        existing = (
            db.query(CustomPlaybook)
            .filter(
                CustomPlaybook.workspace_id == workspace_id,
                CustomPlaybook.playbook_id == request_body.playbook_id.upper(),
                CustomPlaybook.is_active == True,
            )
            .first()
        )

        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Playbook with ID '{request_body.playbook_id}' already exists in this workspace",
            )
    except Exception as db_error:
        # If table doesn't exist, provide a helpful error message
        if "does not exist" in str(db_error) or "UndefinedTable" in str(type(db_error).__name__):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Custom playbooks feature is not available. Please run the database migration first: 'alembic upgrade head'",
            )
        # Re-raise other database errors
        raise

    # Create custom playbook first to get the ID
    custom_playbook = CustomPlaybook(
        workspace_id=workspace_id,
        owner_user_id=get_user_id(current_user),
        name=request_body.name,
        playbook_id=request_body.playbook_id.upper(),
        description=request_body.description,
        yaml_content_path="",  # Temporary, will be set after saving to S3
        config=config,  # Store parsed YAML for quick access
        base_playbook_id=request_body.base_playbook_id.upper() if request_body.base_playbook_id else None,
        is_active=True,
    )

    db.add(custom_playbook)
    db.flush()  # Flush to get the ID without committing
    
    # Save YAML content to S3 with actual playbook ID
    from primedata.services.s3_content_storage import (
        get_playbook_yaml_path,
        save_text_to_s3,
    )

    yaml_content_path = get_playbook_yaml_path(workspace_id, custom_playbook.id)
    
    # Save YAML to S3
    if not save_text_to_s3(yaml_content_path, request_body.yaml_content, "application/x-yaml"):
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save playbook YAML to storage"
        )

    # Update the path
    custom_playbook.yaml_content_path = yaml_content_path
    db.commit()
    db.refresh(custom_playbook)

    logger.info(f"Created custom playbook {custom_playbook.playbook_id} in workspace {workspace_id}")

    return CustomPlaybookResponse.model_validate(custom_playbook)


@router.get("/custom", response_model=List[CustomPlaybookResponse])
async def list_custom_playbooks(
    request: Request,
    workspace_id: UUID = Query(..., description="Workspace ID"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    List all custom playbooks in a workspace.
    """
    from primedata.core.scope import ensure_workspace_access

    ensure_workspace_access(db, request, workspace_id)

    try:
        custom_playbooks = (
            db.query(CustomPlaybook)
            .filter(CustomPlaybook.workspace_id == workspace_id, CustomPlaybook.is_active == True)
            .all()
        )

        return [CustomPlaybookResponse.model_validate(pb) for pb in custom_playbooks]
    except Exception as db_error:
        # If table doesn't exist, return empty list
        if "does not exist" in str(db_error) or "UndefinedTable" in str(type(db_error).__name__):
            logger.debug(f"Custom playbooks table not available: {db_error}")
            return []
        raise


@router.get("/custom/{playbook_id}", response_model=CustomPlaybookResponse)
async def get_custom_playbook(
    playbook_id: str,
    request: Request,
    workspace_id: UUID = Query(..., description="Workspace ID"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Get a specific custom playbook.
    """
    from primedata.core.scope import ensure_workspace_access

    ensure_workspace_access(db, request, workspace_id)

    try:
        custom_playbook = (
            db.query(CustomPlaybook)
            .filter(
                CustomPlaybook.workspace_id == workspace_id,
                CustomPlaybook.playbook_id == playbook_id.upper(),
                CustomPlaybook.is_active == True,
            )
            .first()
        )

        if not custom_playbook:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Custom playbook '{playbook_id}' not found")

        return CustomPlaybookResponse.model_validate(custom_playbook)
    except HTTPException:
        raise
    except Exception as db_error:
        # If table doesn't exist, return 404
        if "does not exist" in str(db_error) or "UndefinedTable" in str(type(db_error).__name__):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Custom playbook '{playbook_id}' not found. Custom playbooks feature is not available. Please run the database migration first.",
            )
        raise


@router.patch("/custom/{playbook_id}", response_model=CustomPlaybookResponse)
async def update_custom_playbook(
    playbook_id: str,
    request_body: CustomPlaybookUpdateRequest,
    request: Request,
    workspace_id: UUID = Query(..., description="Workspace ID"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Update a custom playbook.
    """
    from primedata.core.scope import ensure_workspace_access
    from sqlalchemy.orm.attributes import flag_modified

    ensure_workspace_access(db, request, workspace_id)

    try:
        custom_playbook = (
            db.query(CustomPlaybook)
            .filter(
                CustomPlaybook.workspace_id == workspace_id,
                CustomPlaybook.playbook_id == playbook_id.upper(),
                CustomPlaybook.is_active == True,
            )
            .first()
        )

        if not custom_playbook:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Custom playbook '{playbook_id}' not found")

        # Update fields
        if request_body.name is not None:
            custom_playbook.name = request_body.name
        if request_body.description is not None:
            custom_playbook.description = request_body.description
        if request_body.yaml_content is not None:
            # Validate YAML
            try:
                config = yaml.safe_load(request_body.yaml_content)
                if not isinstance(config, dict):
                    raise ValueError("YAML must be a dictionary")
                
                # Save updated YAML to S3
                from primedata.services.s3_content_storage import (
                    get_playbook_yaml_path,
                    save_text_to_s3,
                )
                
                yaml_content_path = get_playbook_yaml_path(custom_playbook.workspace_id, custom_playbook.id)
                if not save_text_to_s3(yaml_content_path, request_body.yaml_content, "application/x-yaml"):
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save playbook YAML to storage"
                    )
                
                custom_playbook.yaml_content_path = yaml_content_path
                custom_playbook.config = config
                flag_modified(custom_playbook, "config")
            except yaml.YAMLError as e:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid YAML: {str(e)}")

        db.commit()
        db.refresh(custom_playbook)

        logger.info(f"Updated custom playbook {custom_playbook.playbook_id}")

        return CustomPlaybookResponse.model_validate(custom_playbook)
    except HTTPException:
        raise
    except Exception as db_error:
        # If table doesn't exist, provide helpful error
        if "does not exist" in str(db_error) or "UndefinedTable" in str(type(db_error).__name__):
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Custom playbooks feature is not available. Please run the database migration first: 'alembic upgrade head'",
            )
        # Re-raise other database errors
        db.rollback()
        raise
    except Exception as db_error:
        # If table doesn't exist, provide helpful error
        if "does not exist" in str(db_error) or "UndefinedTable" in str(type(db_error).__name__):
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Custom playbooks feature is not available. Please run the database migration first: 'alembic upgrade head'",
            )
        # Re-raise other database errors
        db.rollback()
        raise


@router.delete("/custom/{playbook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_custom_playbook(
    playbook_id: str,
    request: Request,
    workspace_id: UUID = Query(..., description="Workspace ID"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Delete (soft delete) a custom playbook.
    """
    from primedata.core.scope import ensure_workspace_access

    ensure_workspace_access(db, request, workspace_id)

    try:
        custom_playbook = (
            db.query(CustomPlaybook)
            .filter(
                CustomPlaybook.workspace_id == workspace_id,
                CustomPlaybook.playbook_id == playbook_id.upper(),
                CustomPlaybook.is_active == True,
            )
            .first()
        )

        if not custom_playbook:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Custom playbook '{playbook_id}' not found")

        # Soft delete
        custom_playbook.is_active = False
        db.commit()

        logger.info(f"Deleted custom playbook {custom_playbook.playbook_id}")

        return None
    except HTTPException:
        raise
    except Exception as db_error:
        # If table doesn't exist, return 404
        if "does not exist" in str(db_error) or "UndefinedTable" in str(type(db_error).__name__):
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Custom playbook '{playbook_id}' not found. Custom playbooks feature is not available.",
            )
        # Re-raise other database errors
        db.rollback()
        raise
