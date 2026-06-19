"""
Structured logging for AIRD pipeline stages.

Provides logging utilities that integrate with PrimeData's loguru-based logging.
"""

from typing import Any, Dict, Optional
from uuid import UUID

from loguru import logger


def get_aird_logger(
    stage_name: str,
    product_id: UUID,
    version: int,
    workspace_id: Optional[UUID] = None,
) -> Any:
    """Get a logger instance bound with AIRD stage context.

    Args:
        stage_name: Name of the pipeline stage
        product_id: Product UUID
        version: Product version number
        workspace_id: Optional workspace UUID

    Returns:
        Logger instance with context bound
    """
    context = {
        "stage": stage_name,
        "product_id": str(product_id),
        "version": version,
    }
    if workspace_id:
        context["workspace_id"] = str(workspace_id)

    return logger.bind(**context)


def setup_aird_logging():
    """Setup AIRD-specific logging configuration.

    This is called automatically when the module is imported.
    Additional AIRD-specific log handlers can be added here if needed.
    """
    # Loguru is already configured in primedata.logging_conf
    # This function can be extended if AIRD stages need special logging
    pass


# Setup logging when module is imported
setup_aird_logging()
