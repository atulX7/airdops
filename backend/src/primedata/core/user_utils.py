"""
User utility functions for handling user ID extraction in dev/prod modes.
"""

from typing import Any, Dict, Optional
from uuid import UUID

from .settings import get_settings


def get_user_id(current_user: Optional[Dict[str, Any]] = None) -> UUID:
    """
    Get the current user ID from authenticated user.

    Args:
        current_user: Current user dictionary from authentication (may be None)

    Returns:
        UUID of the user ID

    Raises:
        ValueError: If user ID cannot be determined
    """
    if not current_user:
        raise ValueError("No authenticated user available")

    # Try 'sub' first (JWT standard), then 'id' as fallback
    user_id_str = current_user.get("sub") or current_user.get("id")

    if not user_id_str:
        raise ValueError("User ID not found in current_user (neither 'sub' nor 'id' present)")

    try:
        return UUID(user_id_str)
    except (ValueError, TypeError) as e:
        raise ValueError(f"Invalid user ID format: {user_id_str}") from e


def get_user_id_safe(current_user: Optional[Dict[str, Any]] = None) -> Optional[UUID]:
    """
    Get the current user ID safely, returning None if not available.
    Useful for optional user tracking.

    Args:
        current_user: Current user dictionary from authentication (may be None)

    Returns:
        UUID of the user ID, or None if not available
    """
    try:
        return get_user_id(current_user)
    except (ValueError, TypeError):
        return None
