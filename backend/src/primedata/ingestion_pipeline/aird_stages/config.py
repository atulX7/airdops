"""
AIRD configuration management for PrimeData.

Handles AIRD-specific configuration settings and playbook management.
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional

from primedata.core.settings import get_settings
from pydantic import BaseModel, Field


class AirdConfig(BaseModel):
    """AIRD pipeline configuration."""

    # Playbook settings
    default_playbook: str = Field(default="TECH", description="Default playbook ID")
    playbook_dir: Optional[str] = Field(default=None, description="Playbook directory path")

    # Storage settings
    raw_bucket: str = Field(default="primedata-raw", description="MinIO bucket for raw data")
    processed_bucket: str = Field(default="primedata-clean", description="MinIO bucket for processed data")
    artifacts_bucket: str = Field(default="primedata-exports", description="MinIO bucket for artifacts")

    # Scoring settings
    scoring_weights_path: Optional[str] = Field(default=None, description="Path to scoring weights JSON")
    default_scoring_threshold: float = Field(default=70.0, description="Default AI Trust Score threshold")

    # Policy settings (normalized to [0,1] range to match scoring system)
    policy_min_trust_score: float = Field(default=0.5, description="Minimum trust score for policy (0-1 range)")
    policy_min_secure: float = Field(default=0.9, description="Minimum secure score for policy (0-1 range)")
    policy_min_metadata_presence: float = Field(default=0.8, description="Minimum metadata presence for policy (0-1 range)")
    policy_min_kb_ready: float = Field(default=0.5, description="Minimum KB readiness for policy (0-1 range)")

    # Processing settings
    enable_deduplication: bool = Field(default=False, description="Enable MinHash deduplication")
    enable_validation: bool = Field(default=True, description="Enable validation summary generation")
    enable_pdf_reports: bool = Field(default=True, description="Enable PDF report generation")

    class Config:
        env_prefix = "AIRD_"
        case_sensitive = False


_aird_config: Optional[AirdConfig] = None


def get_aird_config() -> AirdConfig:
    """Get AIRD configuration (singleton pattern).

    Returns:
        AirdConfig instance with settings from environment and defaults
    """
    global _aird_config
    if _aird_config is None:
        settings = get_settings()

        # Determine playbook directory
        playbook_dir = os.getenv("AIRD_PLAYBOOK_DIR")
        if not playbook_dir:
            # Default to the playbooks directory in the same package
            # __file__ is at: backend/src/primedata/ingestion_pipeline/aird_stages/config.py
            # playbooks are at: backend/src/primedata/ingestion_pipeline/aird_stages/playbooks/
            default_path = Path(__file__).parent / "playbooks"
            if default_path.exists():
                playbook_dir = str(default_path)
            else:
                # Fallback to backend/config/playbooks if it exists
                fallback_path = Path(__file__).parent.parent.parent.parent / "config" / "playbooks"
                if fallback_path.exists():
                    playbook_dir = str(fallback_path)
                else:
                    playbook_dir = None

        # Determine scoring weights path
        scoring_weights_path = os.getenv("AIRD_SCORING_WEIGHTS_PATH")
        if not scoring_weights_path:
            default_path = Path(__file__).parent.parent.parent.parent / "config" / "scoring_weights.json"
            if default_path.exists():
                scoring_weights_path = str(default_path)
            else:
                scoring_weights_path = None

        _aird_config = AirdConfig(
            playbook_dir=playbook_dir,
            scoring_weights_path=scoring_weights_path,
        )

    return _aird_config


def get_playbook_path(playbook_id: str) -> Optional[Path]:
    """Get path to playbook YAML file.

    Args:
        playbook_id: Playbook identifier (e.g., "TECH", "SCANNED", "REGULATORY")

    Returns:
        Path to playbook YAML file, or None if not found
    """
    config = get_aird_config()
    if not config.playbook_dir:
        return None

    playbook_dir = Path(config.playbook_dir)
    playbook_file = playbook_dir / f"{playbook_id}.yaml"

    if playbook_file.exists():
        return playbook_file

    # Try case-insensitive search
    for yaml_file in playbook_dir.glob("*.yaml"):
        if yaml_file.stem.upper() == playbook_id.upper():
            return yaml_file

    return None
