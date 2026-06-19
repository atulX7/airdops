"""
Playbook system for AIRD preprocessing.

Provides playbook routing and loading functionality.
"""

from .loader import get_playbook_dir, load_playbook_yaml
from .router import list_playbooks, refresh_index, resolve_playbook_file, route_playbook

__all__ = [
    "route_playbook",
    "list_playbooks",
    "resolve_playbook_file",
    "refresh_index",
    "load_playbook_yaml",
    "get_playbook_dir",
]
