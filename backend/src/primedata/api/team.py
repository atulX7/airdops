"""
Team/Workspace Members API endpoints for PrimeData.

This module provides endpoints for managing workspace team members,
including listing, inviting, updating roles, and removing members.
"""

import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from ..core.scope import ensure_workspace_access
from ..core.security import get_current_user
from ..db.database import get_db
from ..db.models import User, Workspace, WorkspaceMember, WorkspaceRole

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/workspaces", tags=["Team"])


class TeamMemberResponse(BaseModel):
    """Team member response model."""

    id: str
    user_id: str
    email: str
    name: str
    role: str
    created_at: str


class InviteMemberRequest(BaseModel):
    """Invite team member request model."""

    email: EmailStr
    role: str  # "admin", "editor", or "viewer"


class UpdateMemberRoleRequest(BaseModel):
    """Update member role request model."""

    role: str  # "admin", "editor", or "viewer"


@router.get("/{workspace_id}/members", response_model=List[TeamMemberResponse])
async def list_workspace_members(
    workspace_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    List all members of a workspace.

    Args:
        workspace_id: Workspace ID
        request: FastAPI request object
        db: Database session
        current_user: Current authenticated user

    Returns:
        List of workspace members
    """
    # Ensure user has access to the workspace
    ensure_workspace_access(db, request, workspace_id)

    # Get all workspace members with user details
    members = (
        db.query(WorkspaceMember, User)
        .join(User, WorkspaceMember.user_id == User.id)
        .filter(WorkspaceMember.workspace_id == workspace_id)
        .order_by(WorkspaceMember.created_at)
        .all()
    )

    result = []
    for membership, user in members:
        result.append(
            TeamMemberResponse(
                id=str(membership.id),
                user_id=str(user.id),
                email=user.email,
                name=user.name,
                role=membership.role.value,
                created_at=membership.created_at.isoformat(),
            )
        )

    return result


@router.post("/{workspace_id}/members/invite", response_model=TeamMemberResponse)
async def invite_workspace_member(
    workspace_id: UUID,
    request_body: InviteMemberRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Invite a user to join the workspace.

    Args:
        workspace_id: Workspace ID
        request_body: Invite member request with email and role
        request: FastAPI request object
        db: Database session
        current_user: Current authenticated user

    Returns:
        Created workspace membership
    """
    # Ensure user has access to the workspace and is admin/owner
    workspace = ensure_workspace_access(db, request, workspace_id, roles=["admin", "owner"])

    # Validate role
    try:
        role = WorkspaceRole(request_body.role.lower())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role: {request_body.role}. Must be one of: owner, admin, editor, viewer",
        )

    # Don't allow inviting as owner (only existing owners can be owners)
    if role == WorkspaceRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot invite users as owner. Owners must be assigned directly.",
        )

    # Find or create user by email
    user = db.query(User).filter(User.email == request_body.email).first()

    if not user:
        # Create new user account (they'll need to authenticate later)
        user = User(
            email=request_body.email,
            name=request_body.email.split("@")[0],  # Use email prefix as default name
            auth_provider=None,  # Will be set when they authenticate
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info(f"Created new user account for {request_body.email}")

    # Check if user is already a member
    existing_membership = (
        db.query(WorkspaceMember)
        .filter(WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == user.id)
        .first()
    )

    if existing_membership:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User {request_body.email} is already a member of this workspace",
        )

    # Create workspace membership
    membership = WorkspaceMember(workspace_id=workspace_id, user_id=user.id, role=role)
    db.add(membership)
    db.commit()
    db.refresh(membership)

    logger.info(f"Invited user {request_body.email} to workspace {workspace_id} with role {role.value}")

    return TeamMemberResponse(
        id=str(membership.id),
        user_id=str(user.id),
        email=user.email,
        name=user.name,
        role=membership.role.value,
        created_at=membership.created_at.isoformat(),
    )


@router.patch("/{workspace_id}/members/{member_id}", response_model=TeamMemberResponse)
async def update_member_role(
    workspace_id: UUID,
    member_id: UUID,
    request_body: UpdateMemberRoleRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Update a workspace member's role.

    Args:
        workspace_id: Workspace ID
        member_id: Workspace member ID
        request_body: Update role request
        request: FastAPI request object
        db: Database session
        current_user: Current authenticated user

    Returns:
        Updated workspace membership
    """
    # Ensure user has access to the workspace and is admin/owner
    ensure_workspace_access(db, request, workspace_id, roles=["admin", "owner"])

    # Find the membership
    membership = (
        db.query(WorkspaceMember).filter(WorkspaceMember.id == member_id, WorkspaceMember.workspace_id == workspace_id).first()
    )

    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace member not found")

    # Don't allow changing owner role
    if membership.role == WorkspaceRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change owner role. Owners must be assigned directly.",
        )

    # Validate new role
    try:
        new_role = WorkspaceRole(request_body.role.lower())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role: {request_body.role}. Must be one of: admin, editor, viewer",
        )

    # Don't allow setting owner role via update
    if new_role == WorkspaceRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot set owner role via update. Owners must be assigned directly.",
        )

    # Update role
    membership.role = new_role
    db.commit()
    db.refresh(membership)

    # Get user details
    user = db.query(User).filter(User.id == membership.user_id).first()

    logger.info(f"Updated member {member_id} role to {new_role.value} in workspace {workspace_id}")

    return TeamMemberResponse(
        id=str(membership.id),
        user_id=str(user.id),
        email=user.email,
        name=user.name,
        role=membership.role.value,
        created_at=membership.created_at.isoformat(),
    )


@router.delete("/{workspace_id}/members/{member_id}")
async def remove_workspace_member(
    workspace_id: UUID,
    member_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Remove a member from the workspace.

    Args:
        workspace_id: Workspace ID
        member_id: Workspace member ID
        request: FastAPI request object
        db: Database session
        current_user: Current authenticated user

    Returns:
        Success response
    """
    # Ensure user has access to the workspace and is admin/owner
    ensure_workspace_access(db, request, workspace_id, roles=["admin", "owner"])

    # Find the membership
    membership = (
        db.query(WorkspaceMember).filter(WorkspaceMember.id == member_id, WorkspaceMember.workspace_id == workspace_id).first()
    )

    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace member not found")

    # Don't allow removing owners
    if membership.role == WorkspaceRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove owner from workspace. Transfer ownership first.",
        )

    # Get user details for logging
    user = db.query(User).filter(User.id == membership.user_id).first()
    user_email = user.email if user else "unknown"

    # Remove membership
    db.delete(membership)
    db.commit()

    logger.info(f"Removed member {member_id} ({user_email}) from workspace {workspace_id}")

    return {"status": "success", "message": f"Member {user_email} has been removed from the workspace"}
