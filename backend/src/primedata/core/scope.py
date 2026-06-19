"""
Workspace access control and scoping utilities.
"""

from typing import List, Optional
from uuid import UUID

from fastapi import HTTPException, Request, status
from primedata.db.models import Product, Workspace, WorkspaceMember, WorkspaceRole
from sqlalchemy.orm import Session


def allowed_workspaces(request: Request, db: Optional[Session] = None) -> List[UUID]:
    """
    Get list of workspace IDs that the current user has access to.

    Args:
        request: FastAPI request object with user state
        db: Optional database session to query actual workspace memberships

    Returns:
        List of workspace UUIDs the user can access
    """
    # CRITICAL: Ensure request is not None - this prevents security bypass
    if request is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Request object is missing. This is a server configuration error.",
        )

    if not hasattr(request.state, "user") or not request.state.user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not authenticated")

    user_id = UUID(request.state.user["sub"])

    # If database session is provided, ALWAYS query actual workspace memberships (more reliable)
    # This is the source of truth - never fall back to token workspaces when we have a DB session
    if db:
        # Always use database query when db is provided (both dev and production)
        # This ensures we're using the actual workspace memberships, not stale token data
        memberships = db.query(WorkspaceMember).filter(WorkspaceMember.user_id == user_id).all()

        # Return database results - even if empty (user has no workspace access)
        # Never fall back to token workspaces when we have a database session
        return [m.workspace_id for m in memberships]

    # Fallback: use workspaces from user token/state (only when no DB session is provided)
    # This should rarely happen in production, but is needed for some edge cases
    user_workspaces = request.state.user.get("workspaces", [])
    # Handle both string and UUID workspace IDs
    result = []
    for ws_id in user_workspaces:
        if isinstance(ws_id, str):
            try:
                result.append(UUID(ws_id))
            except ValueError:
                # Skip invalid UUID strings
                continue
        elif isinstance(ws_id, UUID):
            result.append(ws_id)
    return result


def ensure_workspace_access(db: Session, request: Request, workspace_id: UUID, roles: Optional[List[str]] = None) -> Workspace:
    """
    Ensure the current user has access to the specified workspace.

    Args:
        db: Database session
        request: FastAPI request object with user state
        workspace_id: UUID of the workspace to check access for
        roles: Optional list of required roles (if None, any role is sufficient)

    Returns:
        Workspace object if access is granted

    Raises:
        HTTPException: 403 if access is denied, 404 if workspace not found
    """
    # CRITICAL: Ensure request is not None - this prevents security bypass
    if request is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Request object is missing. This is a server configuration error.",
        )

    if not hasattr(request.state, "user") or not request.state.user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not authenticated")

    user_id = UUID(request.state.user["sub"])

    # Get workspace
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()

    if not workspace:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    # Check database membership
    membership = (
        db.query(WorkspaceMember)
        .filter(WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == user_id)
        .first()
    )

    if not membership:
        # Check if workspace is in allowed list (fallback for non-database cases)
        allowed_workspace_ids = allowed_workspaces(request, db)
        if workspace_id not in allowed_workspace_ids:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to workspace")

    # If specific roles are required, check user's role in this workspace
    if roles and membership:
        if membership.role.value not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Required role not found. Required: {roles}, Current: {membership.role.value}",
            )

    return workspace


def ensure_product_access(db: Session, request: Request, product_id: UUID) -> Product:
    """
    Ensure the current user has access to the specified product.

    Args:
        db: Database session
        request: FastAPI request object with user state
        product_id: UUID of the product to check access for

    Returns:
        Product object if access is granted

    Raises:
        HTTPException: 403 if access is denied, 404 if product not found
    """
    # CRITICAL: Ensure request is not None - this prevents security bypass
    if request is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Request object is missing. This is a server configuration error.",
        )

    if not hasattr(request.state, "user") or not request.state.user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not authenticated")

    # Get the product
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    # Check workspace access
    ensure_workspace_access(db, request, product.workspace_id)

    return product
