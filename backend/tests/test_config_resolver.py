"""
Unit tests for config resolver precedence.

Tests the resolve_effective_config function with all precedence levels.
"""

import pytest

from primedata.config.models import ChunkingConfig, EffectiveConfig
from primedata.config.resolver import resolve_effective_config


class MockProduct:
    """Mock product row for testing."""

    def __init__(self, chunking_config=None, playbook_id=None, workspace_id=None):
        self.chunking_config = chunking_config or {}
        self.playbook_id = playbook_id
        self.workspace_id = workspace_id


def test_precedence_1_run_conf_overrides():
    """Test that run_conf overrides have highest priority."""
    product = MockProduct(
        chunking_config={
            "mode": "manual",
            "manual_settings": {
                "chunk_size": 500,
                "chunk_overlap": 100,
                "chunking_strategy": "semantic",
            },
        }
    )

    run_conf = {
        "chunking_config": {
            "chunk_size": 2000,
            "chunk_overlap": 400,
        }
    }

    result = resolve_effective_config(run_conf, product)

    assert result.chunking_config.chunk_size == 2000
    assert result.chunking_config.chunk_overlap == 400
    assert result.resolution_trace.chunk_size == "run_conf"
    assert result.resolution_trace.chunk_overlap == "run_conf"
    assert result.resolution_trace.chunking_strategy == "product_manual_settings"


def test_precedence_2_force_product_chunking_config():
    """Test that force_product_chunking_config takes precedence over manual settings."""
    product = MockProduct(
        chunking_config={
            "mode": "manual",
            "manual_settings": {
                "chunk_size": 500,
                "chunk_overlap": 100,
            },
        }
    )

    run_conf = {
        "force_product_chunking_config": True,
        "chunking_config": {
            "chunk_size": 800,
        },
    }

    result = resolve_effective_config(run_conf, product)

    # force_product_chunking_config should use product_chunking, but run_conf still overrides
    assert result.chunking_config.chunk_size == 800  # run_conf still wins
    assert result.resolution_trace.chunk_size == "run_conf"


def test_precedence_3_product_manual_settings():
    """Test that product manual settings take precedence over playbook defaults."""
    product = MockProduct(
        chunking_config={
            "mode": "manual",
            "manual_settings": {
                "chunk_size": 1200,
                "chunk_overlap": 300,
                "chunking_strategy": "semantic",
            },
        },
        playbook_id="TECH",
    )

    result = resolve_effective_config({}, product)

    assert result.chunking_config.chunk_size == 1200
    assert result.chunking_config.chunk_overlap == 300
    assert result.chunking_config.chunking_strategy == "semantic"
    assert result.resolution_trace.chunk_size == "product_manual_settings"
    assert result.resolution_trace.chunk_overlap == "product_manual_settings"
    assert result.resolution_trace.chunking_strategy == "product_manual_settings"


def test_precedence_4_playbook_defaults():
    """Test that playbook defaults are used when product settings are not provided."""
    product = MockProduct(playbook_id="TECH")

    result = resolve_effective_config({}, product)

    # Should use playbook defaults or global defaults
    assert result.chunking_config.chunk_size is not None
    assert result.chunking_config.chunk_overlap is not None
    assert result.playbook_id == "TECH"
    # Trace should show playbook_defaults or global_defaults
    assert result.resolution_trace.chunk_size in ["playbook_defaults", "global_default", "content_type_defaults"]


def test_precedence_5_global_defaults():
    """Test that defaults are used when nothing else is provided.
    With empty product, content_type becomes 'general' and content_type_defaults
    (general) are applied, so trace shows content_type_defaults."""
    product = MockProduct()

    result = resolve_effective_config({}, product)

    assert result.chunking_config.chunk_size == 1000  # general default
    assert result.chunking_config.chunk_overlap == 200  # general default
    assert result.chunking_config.chunking_strategy == "fixed_size"  # general default
    assert result.resolution_trace.chunk_size == "content_type_defaults"
    assert result.resolution_trace.chunk_overlap == "content_type_defaults"
    assert result.resolution_trace.chunking_strategy == "content_type_defaults"


def test_playbook_id_precedence():
    """Test playbook ID resolution precedence."""
    # Test: run_conf > detected_playbook > product > global default
    product = MockProduct(playbook_id="HEALTHCARE")

    # Case 1: run_conf wins
    result = resolve_effective_config({"playbook_id": "TECH"}, product)
    assert result.playbook_id == "TECH"
    assert result.resolution_trace.playbook_id == "run_conf"

    # Case 2: detected_playbook wins when no run_conf
    result = resolve_effective_config({}, product, detected_playbook="FINANCIAL")
    assert result.playbook_id == "FINANCIAL"
    assert result.resolution_trace.playbook_id == "detected_playbook"

    # Case 3: product wins when no run_conf or detected
    result = resolve_effective_config({}, product)
    assert result.playbook_id == "HEALTHCARE"
    assert result.resolution_trace.playbook_id == "product"

    # Case 4: global default when nothing provided
    product_no_playbook = MockProduct()
    result = resolve_effective_config({}, product_no_playbook)
    assert result.playbook_id == "TECH"  # Global default
    assert result.resolution_trace.playbook_id == "global_default"


def test_resolution_trace_completeness():
    """Test that resolution trace tracks all fields."""
    product = MockProduct(
        chunking_config={
            "manual_settings": {
                "chunk_size": 800,
                "chunk_overlap": 200,
            },
        },
        playbook_id="REGULATORY",
    )

    result = resolve_effective_config({}, product)

    # All trace fields should be set
    assert result.resolution_trace.chunk_size != ""
    assert result.resolution_trace.chunk_overlap != ""
    assert result.resolution_trace.min_chunk_size != ""
    assert result.resolution_trace.max_chunk_size != ""
    assert result.resolution_trace.chunking_strategy != ""
    assert result.resolution_trace.content_type != ""
    assert result.resolution_trace.playbook_id != ""


def test_mixed_precedence_scenario():
    """Test a realistic scenario with mixed precedence levels."""
    product = MockProduct(
        chunking_config={
            "mode": "manual",
            "manual_settings": {
                "chunk_size": 1500,
                "chunk_overlap": 300,
            },
        },
        playbook_id="FINANCIAL",
    )

    run_conf = {
        "chunking_config": {
            "chunk_size": 2000,  # Override
        },
    }

    result = resolve_effective_config(run_conf, product, detected_playbook="LEGAL")

    # chunk_size: run_conf (highest)
    assert result.chunking_config.chunk_size == 2000
    assert result.resolution_trace.chunk_size == "run_conf"

    # chunk_overlap: product_manual_settings (no run_conf override)
    assert result.chunking_config.chunk_overlap == 300
    assert result.resolution_trace.chunk_overlap == "product_manual_settings"

    # playbook_id: run_conf (but we don't have it in run_conf, so detected_playbook)
    # Actually, run_conf doesn't have playbook_id, so detected_playbook wins
    assert result.playbook_id == "LEGAL"
    assert result.resolution_trace.playbook_id == "detected_playbook"


def test_empty_configurations():
    """Test behavior with empty/minimal configurations."""
    product = MockProduct()

    result = resolve_effective_config({}, product)

    # Should fall back to global defaults
    assert isinstance(result, EffectiveConfig)
    assert isinstance(result.chunking_config, ChunkingConfig)
    assert result.chunking_config.chunk_size == 1000
    assert result.chunking_config.chunk_overlap == 200


def test_none_values_handling():
    """Test that None values don't override valid values."""
    product = MockProduct(
        chunking_config={
            "manual_settings": {
                "chunk_size": 1200,
                "chunk_overlap": 250,
            },
        }
    )

    run_conf = {
        "chunking_config": {
            "chunk_size": None,  # None should not override
            "chunk_overlap": 400,
        },
    }

    result = resolve_effective_config(run_conf, product)

    # chunk_size should come from product_manual_settings (None ignored)
    assert result.chunking_config.chunk_size == 1200
    assert result.resolution_trace.chunk_size == "product_manual_settings"

    # chunk_overlap should come from run_conf
    assert result.chunking_config.chunk_overlap == 400
    assert result.resolution_trace.chunk_overlap == "run_conf"


def test_auto_resolved_settings_with_force_flag():
    """Test that resolved_settings are used when mode=auto AND force_product_chunking_config=True AND confidence_met=True."""
    product = MockProduct(
        chunking_config={
            "mode": "auto",
            "auto_settings": {
                "content_type": "general",
                "confidence_threshold": 0.7,
            },
            "resolved_settings": {
                "content_type": "regulatory",
                "chunk_size": 1400,
                "chunk_overlap": 280,
                "min_chunk_size": 200,
                "max_chunk_size": 2200,
                "chunking_strategy": "semantic",
                "confidence": 0.75,
                "confidence_met": True,
            },
        },
        playbook_id="REGULATORY",
    )

    run_conf = {
        "force_product_chunking_config": True,
    }

    result = resolve_effective_config(run_conf, product)

    # Should use resolved_settings values, not content_type_defaults
    assert result.chunking_config.chunk_size == 1400
    assert result.chunking_config.chunk_overlap == 280
    assert result.chunking_config.min_chunk_size == 200
    assert result.chunking_config.max_chunk_size == 2200
    assert result.chunking_config.chunking_strategy == "semantic"
    assert result.chunking_config.content_type == "regulatory"
    
    # Trace should show resolved_settings as source
    assert result.resolution_trace.chunk_size == "resolved_settings"
    assert result.resolution_trace.chunk_overlap == "resolved_settings"
    assert result.resolution_trace.min_chunk_size == "resolved_settings"
    assert result.resolution_trace.max_chunk_size == "resolved_settings"
    assert result.resolution_trace.chunking_strategy == "resolved_settings"
    assert result.resolution_trace.content_type == "resolved_settings"


def test_auto_resolved_settings_low_confidence_fallback():
    """Test that resolved_settings ARE used when they contain chunk_size, even if confidence_met=False.
    Current behavior: has_chunk_size triggers use of resolved_settings for chunk_size/chunk_overlap/content_type;
    min/max_chunk_size and chunking_strategy may come from content_type_defaults when missing in resolved_settings."""
    product = MockProduct(
        chunking_config={
            "mode": "auto",
            "auto_settings": {
                "content_type": "general",
                "confidence_threshold": 0.7,
            },
            "resolved_settings": {
                "content_type": "regulatory",
                "chunk_size": 1400,
                "chunk_overlap": 280,
                "confidence": 0.5,
                "confidence_met": False,  # Low confidence
            },
        },
    )

    run_conf = {
        "force_product_chunking_config": True,
    }

    result = resolve_effective_config(run_conf, product)

    # Resolver uses resolved_settings when chunk_size is present (has_chunk_size)
    assert result.resolution_trace.chunk_size == "resolved_settings"
    assert result.resolution_trace.chunk_overlap == "resolved_settings"
    assert result.resolution_trace.content_type == "resolved_settings"
    assert result.chunking_config.chunk_size == 1400
    assert result.chunking_config.chunk_overlap == 280
    assert result.chunking_config.content_type == "regulatory"


def test_auto_resolved_settings_no_resolved_settings():
    """Test that when resolved_settings don't exist, falls back to other sources."""
    product = MockProduct(
        chunking_config={
            "mode": "auto",
            "auto_settings": {
                "content_type": "general",
            },
            # No resolved_settings
        },
    )

    run_conf = {
        "force_product_chunking_config": True,
    }

    result = resolve_effective_config(run_conf, product)

    # Should use content_type_defaults or other fallbacks
    assert result.chunking_config.chunk_size is not None
    assert result.chunking_config.chunk_overlap is not None
    # Should not trace to resolved_settings
    assert result.resolution_trace.chunk_size != "resolved_settings"


def test_force_product_chunking_uses_resolved_settings_not_auto_settings():
    """Regression: when mode=auto and force_product_chunking_config=True, indexing/preprocess must use
    chunk_size/overlap/strategy/content_type from resolved_settings, never fall back to auto_settings.
    Product has resolved_settings (medical, 800) and auto_settings (content_type=general)."""
    product = MockProduct(
        chunking_config={
            "mode": "auto",
            "auto_settings": {
                "content_type": "general",  # Must NOT be used when resolved_settings exists
                "confidence_threshold": 0.7,
            },
            "resolved_settings": {
                "content_type": "medical",
                "chunk_size": 800,
                "chunk_overlap": 160,
                "min_chunk_size": 100,
                "max_chunk_size": 1200,
                "chunking_strategy": "semantic",
                "confidence": 0.85,
                "confidence_met": True,
            },
        },
    )

    run_conf = {"force_product_chunking_config": True}

    result = resolve_effective_config(run_conf, product)

    # Must use resolved_settings, not auto_settings (content_type must be medical, not general)
    assert result.chunking_config.content_type == "medical", (
        f"Expected content_type=medical from resolved_settings, got {result.chunking_config.content_type} (auto_settings has general)"
    )
    assert result.chunking_config.chunk_size == 800
    assert result.chunking_config.chunk_overlap == 160
    assert result.chunking_config.chunking_strategy == "semantic"
    assert result.resolution_trace.chunk_size == "resolved_settings"
    assert result.resolution_trace.content_type == "resolved_settings"
