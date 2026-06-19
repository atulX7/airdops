"""
Plan limits configuration - single source of truth.

This module contains all billing plan limits in one place to avoid duplication
and ensure consistency across the application.
"""

from typing import Dict, Any

# Plan limits configuration
# -1 means unlimited
PLAN_LIMITS: Dict[str, Dict[str, Any]] = {
    "free": {
        "max_products": 3,
        "max_data_sources_per_product": 5,
        "max_pipeline_runs_per_month": 10,
        "max_evaluation_runs_per_month": 5,
        "max_raw_files_size_mb": 100,  # 100 MB total for all raw files across all data sources
        "schedule_frequency": "manual",
    },
    "pro": {
        "max_products": 25,
        "max_data_sources_per_product": 50,
        "max_pipeline_runs_per_month": 1000,
        "max_evaluation_runs_per_month": 500,
        "max_raw_files_size_mb": -1,  # Unlimited
        "schedule_frequency": "hourly",
    },
    "enterprise": {
        "max_products": -1,  # Unlimited
        "max_data_sources_per_product": -1,  # Unlimited
        "max_pipeline_runs_per_month": -1,  # Unlimited
        "max_evaluation_runs_per_month": -1,  # Unlimited
        "max_raw_files_size_mb": -1,  # Unlimited
        "schedule_frequency": "realtime",
    },
}


def get_plan_limits(plan_name: str) -> Dict[str, Any]:
    """
    Get all limits for a plan.
    
    Args:
        plan_name: Plan name (free, pro, enterprise)
    
    Returns:
        Dictionary of plan limits
    """
    return PLAN_LIMITS.get(plan_name.lower(), PLAN_LIMITS["free"])


def get_plan_limit(plan_name: str, limit_type: str) -> Any:
    """
    Get a specific limit for a plan.
    
    Args:
        plan_name: Plan name (free, pro, enterprise)
        limit_type: Type of limit (e.g., "max_products", "max_raw_files_size_mb")
    
    Returns:
        Limit value (-1 for unlimited, or number)
    """
    limits = get_plan_limits(plan_name)
    return limits.get(limit_type, -1)  # Default to unlimited if not found

