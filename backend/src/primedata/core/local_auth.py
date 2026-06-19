"""
Local auth bootstrap for single-user desktop/local runs.
"""

from typing import Any, Dict
from uuid import UUID

from loguru import logger
from primedata.db.database import SessionLocal
from primedata.db.models import AuthProvider, User, Workspace, WorkspaceMember, WorkspaceRole


LOCAL_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
LOCAL_USER_EMAIL = "local@airdops.local"
LOCAL_USER_NAME = "Local User"
LOCAL_WORKSPACE_NAME = "Local Workspace"


def ensure_local_user_and_workspace() -> Dict[str, Any]:
    """Create the local user/workspace pair if it does not already exist."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == LOCAL_USER_ID).first()
        if not user:
            user = User(
                id=LOCAL_USER_ID,
                email=LOCAL_USER_EMAIL,
                name=LOCAL_USER_NAME,
                first_name="Local",
                last_name="User",
                auth_provider=AuthProvider.NONE,
                roles=["owner", "admin"],
                is_active=True,
                email_verified=True,
            )
            db.add(user)
            db.flush()

        membership = (
            db.query(WorkspaceMember)
            .filter(WorkspaceMember.user_id == user.id)
            .first()
        )

        if membership:
            workspace = db.query(Workspace).filter(Workspace.id == membership.workspace_id).first()
        else:
            workspace = Workspace(name=LOCAL_WORKSPACE_NAME, settings={})
            db.add(workspace)
            db.flush()
            membership = WorkspaceMember(
                workspace_id=workspace.id,
                user_id=user.id,
                role=WorkspaceRole.OWNER,
            )
            db.add(membership)

        db.commit()

        workspace_ids = [str(workspace.id)] if workspace else []
        return {
            "sub": str(user.id),
            "id": str(user.id),
            "email": user.email,
            "roles": user.roles or ["owner", "admin"],
            "workspaces": workspace_ids,
        }
    except Exception:
        db.rollback()
        logger.exception("Failed to bootstrap local auth user/workspace")
        raise
    finally:
        db.close()
