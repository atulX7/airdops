"""
Authentication API router - no-auth mode.
Only retains user info and workspace endpoints needed by the product UI.
"""

import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger
from primedata.core.security import get_current_user
from primedata.db.database import get_db
from primedata.db.models import User, Workspace, WorkspaceMember, WorkspaceRole
from pydantic import BaseModel
from sqlalchemy.orm import Session

router = APIRouter()


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    timezone: Optional[str] = None
    roles: List[str]
    picture_url: Optional[str] = None


class WorkspaceResponse(BaseModel):
    id: str
    name: str
    role: str
    created_at: str


class WorkspaceCreateRequest(BaseModel):
    name: Optional[str] = None


class WorkspaceCreateResponse(BaseModel):
    id: str
    name: str
    created_at: str


class UserProfileUpdateRequest(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    timezone: Optional[str] = None


class UserProfileResponse(BaseModel):
    id: str
    email: str
    name: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    timezone: Optional[str] = None
    picture_url: Optional[str] = None


@router.get("/api/v1/users/me", response_model=UserResponse)
async def get_current_user_info(user: Dict[str, Any] = Depends(get_current_user), db: Session = Depends(get_db)):
    user_id = uuid.UUID(user["sub"])
    db_user = db.query(User).filter(User.id == user_id).first()

    if not db_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    roles_list = []
    if db_user.roles:
        if isinstance(db_user.roles, dict):
            for role_group in db_user.roles.values():
                if isinstance(role_group, list):
                    roles_list.extend(role_group)
                elif isinstance(role_group, str):
                    roles_list.append(role_group)
        elif isinstance(db_user.roles, list):
            roles_list = db_user.roles
        elif isinstance(db_user.roles, str):
            roles_list = [db_user.roles]

    return UserResponse(
        id=str(db_user.id),
        email=db_user.email,
        name=db_user.name,
        first_name=db_user.first_name,
        last_name=db_user.last_name,
        timezone=db_user.timezone,
        roles=roles_list,
        picture_url=db_user.picture_url,
    )


@router.get("/api/v1/workspaces/", response_model=List[WorkspaceResponse])
async def get_user_workspaces(user: Dict[str, Any] = Depends(get_current_user), db: Session = Depends(get_db)):
    user_id = uuid.UUID(user["sub"])
    memberships = (
        db.query(WorkspaceMember, Workspace)
        .join(Workspace, WorkspaceMember.workspace_id == Workspace.id)
        .filter(WorkspaceMember.user_id == user_id)
        .all()
    )
    workspaces = []
    for membership, workspace in memberships:
        workspaces.append(
            WorkspaceResponse(
                id=str(workspace.id),
                name=workspace.name,
                role=membership.role.value,
                created_at=workspace.created_at.isoformat(),
            )
        )
    return workspaces


@router.post("/api/v1/workspaces/", response_model=WorkspaceCreateResponse)
async def create_workspace(
    request_body: WorkspaceCreateRequest, user: Dict[str, Any] = Depends(get_current_user), db: Session = Depends(get_db)
):
    from primedata.core.user_utils import get_user_id
    user_id = get_user_id(user)
    existing_memberships = db.query(WorkspaceMember).filter(WorkspaceMember.user_id == user_id).all()

    if existing_memberships:
        workspace = db.query(Workspace).filter(Workspace.id == existing_memberships[0].workspace_id).first()
        if workspace:
            return WorkspaceCreateResponse(
                id=str(workspace.id), name=workspace.name, created_at=workspace.created_at.isoformat()
            )

    workspace_name = request_body.name or f"{user.get('name', 'User')}'s Workspace"
    workspace = Workspace(name=workspace_name)
    db.add(workspace)
    db.commit()
    db.refresh(workspace)
    membership = WorkspaceMember(workspace_id=workspace.id, user_id=user_id, role=WorkspaceRole.OWNER)
    db.add(membership)
    db.commit()

    return WorkspaceCreateResponse(id=str(workspace.id), name=workspace.name, created_at=workspace.created_at.isoformat())


@router.put("/api/v1/user/profile", response_model=UserProfileResponse)
async def update_user_profile(
    request_body: UserProfileUpdateRequest, user: Dict[str, Any] = Depends(get_current_user), db: Session = Depends(get_db)
):
    user_id = uuid.UUID(user["sub"])
    db_user = db.query(User).filter(User.id == user_id).first()

    if not db_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if request_body.first_name is not None:
        db_user.first_name = request_body.first_name
    if request_body.last_name is not None:
        db_user.last_name = request_body.last_name
    if request_body.timezone is not None:
        db_user.timezone = request_body.timezone

    if request_body.first_name is not None or request_body.last_name is not None:
        first_name = request_body.first_name if request_body.first_name is not None else db_user.first_name
        last_name = request_body.last_name if request_body.last_name is not None else db_user.last_name
        if first_name and last_name:
            db_user.name = f"{first_name} {last_name}"
        elif first_name:
            db_user.name = first_name
        elif last_name:
            db_user.name = last_name

    db.commit()
    db.refresh(db_user)

    return UserProfileResponse(
        id=str(db_user.id),
        email=db_user.email,
        name=db_user.name,
        first_name=db_user.first_name,
        last_name=db_user.last_name,
        timezone=db_user.timezone,
        picture_url=db_user.picture_url,
    )
