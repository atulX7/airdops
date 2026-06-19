"""
Playbook YAML loader for AIRD preprocessing.

Loads and parses playbook YAML files from configured directory.
"""

from pathlib import Path
from typing import Dict, Optional

import yaml
from loguru import logger
from primedata.ingestion_pipeline.aird_stages.config import get_aird_config, get_playbook_path


def get_playbook_dir() -> Optional[Path]:
    """Get the playbook directory path.

    Returns:
        Path to playbook directory, or None if not configured
    """
    config = get_aird_config()
    if not config.playbook_dir:
        return None
    return Path(config.playbook_dir)


def load_playbook_yaml(playbook_id: Optional[str], workspace_id: Optional[str] = None, db_session=None) -> Dict:
    """
    Load and parse a playbook YAML by ID (case-insensitive).
    Supports both built-in playbooks (from files) and custom playbooks (from database).

    Args:
        playbook_id: e.g., 'TECH', 'tech', 'ScAnNeD'; None allowed (uses default)
        workspace_id: Optional workspace ID for loading custom playbooks
        db_session: Optional database session for loading custom playbooks

    Returns:
        dict from YAML content

    Raises:
        FileNotFoundError: if playbook cannot be found
    """
    # Try to load custom playbook from database if workspace_id and db_session provided
    if workspace_id and db_session and playbook_id:
        try:
            from uuid import UUID

            from primedata.db.models import CustomPlaybook

            custom_playbook = (
                db_session.query(CustomPlaybook)
                .filter(
                    CustomPlaybook.playbook_id == playbook_id.upper(),
                    CustomPlaybook.workspace_id == UUID(workspace_id),
                    CustomPlaybook.is_active == True,
                )
                .first()
            )

            if custom_playbook:
                try:
                    from primedata.services.s3_content_storage import load_text_from_s3
                    yaml_content = load_text_from_s3(custom_playbook.yaml_content_path)
                    if yaml_content is None:
                        logger.error(f"Failed to load YAML content from S3 for playbook {playbook_id}")
                        # Fall through to try built-in playbook
                    else:
                        return yaml.safe_load(yaml_content)
                except yaml.YAMLError as e:
                    logger.error(f"Failed to parse custom playbook YAML for {playbook_id}: {e}")
                    # Fall through to try built-in playbook
        except Exception as e:
            logger.warning(f"Failed to load custom playbook {playbook_id}: {e}")
            # Fall through to try built-in playbook

    # Try built-in playbooks (from files)
    playbook_file = get_playbook_path(playbook_id)
    if not playbook_file:
        # Fallback: try to use default from config
        config = get_aird_config()
        if config.default_playbook:
            playbook_file = get_playbook_path(config.default_playbook)

        if not playbook_file:
            raise FileNotFoundError(f"Playbook '{playbook_id}' not found and no default available")

    try:
        with open(playbook_file, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Failed to load playbook from {playbook_file}: {e}")
        raise
