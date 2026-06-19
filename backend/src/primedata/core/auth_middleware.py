"""
Authentication middleware for FastAPI (no-auth mode).
Always attaches a local system user.
"""

from fastapi import Request
from loguru import logger
from primedata.core.local_auth import ensure_local_user_and_workspace
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp


class AuthMiddleware(BaseHTTPMiddleware):
    """No-auth middleware that always provides a local system user."""

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        request.state.user = ensure_local_user_and_workspace()
        logger.debug(f"Using local auth bypass for route: {request.url.path}")
        return await call_next(request)
