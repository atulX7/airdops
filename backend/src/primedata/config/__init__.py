"""
Configuration models and resolver for AirdOps pipeline.

This module provides Pydantic models for configuration management and
a resolver that implements precedence-based configuration resolution.
"""

from .models import (
    ChunkingConfig,
    EffectiveConfig,
    OptimizationConfig,
    PlaybookConfig,
    PolicyGates,
    ResolutionTrace,
    ScoringWeights,
)
from .resolver import resolve_effective_config

__all__ = [
    "ChunkingConfig",
    "EffectiveConfig",
    "OptimizationConfig",
    "PlaybookConfig",
    "PolicyGates",
    "ResolutionTrace",
    "ScoringWeights",
    "resolve_effective_config",
]
