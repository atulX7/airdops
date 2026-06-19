"""
Security utilities - no-auth mode.
Always returns a local system user.
"""

from typing import Any, Dict

from fastapi import Request
from loguru import logger


def get_current_user(request: Request) -> Dict[str, Any]:
    """
    Return the local system user from request state.
    AuthMiddleware already attaches it.
    """
    user = getattr(request.state, "user", None)
    if not user:
        logger.warning("get_current_user - request.state.user is missing, creating default")
        from primedata.core.local_auth import LOCAL_USER_ID, LOCAL_USER_EMAIL, LOCAL_USER_NAME
        from uuid import UUID
        user = {
            "sub": str(LOCAL_USER_ID),
            "id": str(LOCAL_USER_ID),
            "email": LOCAL_USER_EMAIL,
            "name": LOCAL_USER_NAME,
            "roles": ["owner", "admin"],
            "workspaces": [],
        }
    return user


def require_roles(required_roles):
    """No-op role checker (always passes in no-auth mode)."""
    def role_checker(user: Dict[str, Any] = None):
        return user
    return role_checker
