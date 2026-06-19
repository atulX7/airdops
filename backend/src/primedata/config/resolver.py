"""
Configuration resolver with precedence-based resolution.

Implements resolve_effective_config with the following precedence order:
1. run_conf overrides (highest priority)
2. force_product_chunking_config
3. product manual settings
4. playbook defaults
5. global defaults (lowest priority)
"""

from typing import Any, Dict, Optional

from loguru import logger

from primedata.analysis.content_analyzer import ContentType, content_analyzer
from primedata.config.models import (
    ChunkingConfig,
    EffectiveConfig,
    PlaybookConfig,
    ResolutionTrace,
    extraction_type_to_source_quality,
)
from primedata.ingestion_pipeline.aird_stages.playbooks.loader import load_playbook_yaml

# content_type must be semantic only; "scanned" is not a content_type (it maps to source_quality)
CONTENT_TYPE_NORMALIZE_SCANNED = "general"

# Global defaults
DEFAULT_MANUAL_SETTINGS: Dict[str, Any] = {
    "chunk_size": 1000,
    "chunk_overlap": 200,
    "min_chunk_size": 100,
    "max_chunk_size": 2000,
    "chunking_strategy": "fixed_size",
}

DEFAULT_AUTO_SETTINGS: Dict[str, Any] = {
    "content_type": "general",
    "model_optimized": True,
    "confidence_threshold": 0.7,
}


def _ensure_dict(value: Any) -> Dict[str, Any]:
    """Ensure value is a dictionary."""
    return value if isinstance(value, dict) else {}


def _get_playbook_chunking_defaults(playbook_config: Optional[PlaybookConfig]) -> Dict[str, Any]:
    """Extract chunking defaults from playbook configuration."""
    if not playbook_config or not playbook_config.chunking:
        return {}

    chunking = playbook_config.chunking
    defaults = {}

    # Map playbook chunking config to our format
    # Convert tokens to characters: 1 token ≈ 4 characters (conservative estimate)
    if "max_tokens" in chunking:
        max_tokens = chunking["max_tokens"]
        defaults["chunk_size"] = max_tokens * 4
    elif "chunk_size" in chunking:
        defaults["chunk_size"] = chunking["chunk_size"]
    
    # Handle overlap: prefer hard_overlap_chars, fallback to overlap_sentences
    if "hard_overlap_chars" in chunking:
        defaults["chunk_overlap"] = chunking["hard_overlap_chars"]
    elif "overlap_sentences" in chunking:
        # Rough conversion: 1 sentence ≈ 50-100 chars, use 75 as average
        defaults["chunk_overlap"] = chunking["overlap_sentences"] * 75
    elif "chunk_overlap" in chunking:
        defaults["chunk_overlap"] = chunking["chunk_overlap"]
    
    if "strategy" in chunking:
        strategy = chunking["strategy"]
        # Map playbook strategies to our enum values
        if strategy == "sentence":
            defaults["chunking_strategy"] = "semantic"
        elif strategy == "fixed_size":
            defaults["chunking_strategy"] = "fixed_size"
        else:
            defaults["chunking_strategy"] = "fixed_size"  # Default fallback

    if "content_type" in chunking:
        defaults["content_type"] = chunking["content_type"]

    return defaults


def _get_content_type_defaults(content_type: Optional[str]) -> Dict[str, Any]:
    """Get defaults from content analyzer for a given content type."""
    if not content_type:
        return {}

    try:
        content_type_enum = ContentType(content_type)
        default_config = content_analyzer.optimal_configs.get(content_type_enum)
        if default_config:
            return {
                "chunk_size": default_config["chunk_size"],
                "chunk_overlap": default_config["chunk_overlap"],
                "min_chunk_size": default_config["min_chunk_size"],
                "max_chunk_size": default_config["max_chunk_size"],
                "chunking_strategy": default_config["strategy"].value,
            }
    except (ValueError, KeyError):
        pass

    return {}


def resolve_effective_config(
    run_conf: Optional[Dict[str, Any]],
    product_row: Any,
    detected_playbook: Optional[str] = None,
) -> EffectiveConfig:
    """
    Resolve effective configuration with precedence-based resolution.

    Precedence order (highest to lowest):
    1. run_conf overrides
    2. force_product_chunking_config
    3. product manual settings
    4. playbook defaults
    5. global defaults

    Args:
        run_conf: Runtime configuration overrides (from DAG run config)
        product_row: Product database row/model instance
        detected_playbook: Detected playbook ID (optional)

    Returns:
        EffectiveConfig with resolved configuration and ResolutionTrace
    """
    run_conf = run_conf or {}
    trace = ResolutionTrace(
        chunk_size="",
        chunk_overlap="",
        min_chunk_size="",
        max_chunk_size="",
        chunking_strategy="",
        content_type="",
        playbook_id="",
    )

    # Extract product configuration
    product_chunking = _ensure_dict(getattr(product_row, "chunking_config", None))
    logger.info(f"[RESOLVER DEBUG] Loaded product_chunking from DB: {product_chunking}")
    product_playbook_id = getattr(product_row, "playbook_id", None)
    product_manual_settings = _ensure_dict(product_chunking.get("manual_settings"))
    product_auto_settings = _ensure_dict(product_chunking.get("auto_settings"))

    # Determine playbook ID (precedence: run_conf > detected > product)
    playbook_id = (
        run_conf.get("playbook_id")
        or detected_playbook
        or product_playbook_id
        or "TECH"  # Global default
    )
    trace.playbook_id = (
        "run_conf"
        if run_conf.get("playbook_id")
        else ("detected_playbook" if detected_playbook else ("product" if product_playbook_id else "global_default"))
    )

    # Load playbook configuration
    playbook_config: Optional[PlaybookConfig] = None
    try:
        workspace_id = getattr(product_row, "workspace_id", None)
        db_session = getattr(product_row, "__session__", None)  # Try to get session if available
        playbook_dict = load_playbook_yaml(playbook_id, str(workspace_id) if workspace_id else None, db_session)
        if playbook_dict:
            playbook_config = PlaybookConfig(**playbook_dict)
    except Exception as e:
        logger.warning(f"Failed to load playbook {playbook_id}: {e}")

    # Get playbook chunking defaults
    playbook_defaults = _get_playbook_chunking_defaults(playbook_config)

    # Get content type defaults
    content_type = product_auto_settings.get("content_type") or playbook_defaults.get("content_type") or "general"
    content_type_defaults = _get_content_type_defaults(content_type)
    trace.content_type = (
        "product_auto_settings"
        if product_auto_settings.get("content_type")
        else ("playbook" if playbook_defaults.get("content_type") else "global_default")
    )

    # source_quality default from product extraction_type (backward compat when not in resolved_settings)
    product_extraction_type = getattr(product_row, "extraction_type", None)
    default_source_quality = extraction_type_to_source_quality(product_extraction_type)

    # Start with global defaults; content_type is semantic only (medical|academic|technical|regulatory|general|documentation)
    resolved = {
        "chunk_size": DEFAULT_MANUAL_SETTINGS["chunk_size"],
        "chunk_overlap": DEFAULT_MANUAL_SETTINGS["chunk_overlap"],
        "min_chunk_size": DEFAULT_MANUAL_SETTINGS["min_chunk_size"],
        "max_chunk_size": DEFAULT_MANUAL_SETTINGS["max_chunk_size"],
        "chunking_strategy": DEFAULT_MANUAL_SETTINGS["chunking_strategy"],
        "content_type": content_type,
        "source_quality": default_source_quality,
    }

    # Apply precedence (lowest to highest, so later overrides earlier)

    # 5. Global defaults (already set above)
    trace.chunk_size = "global_default"
    trace.chunk_overlap = "global_default"
    trace.min_chunk_size = "global_default"
    trace.max_chunk_size = "global_default"
    trace.chunking_strategy = "global_default"

    # 4. Playbook defaults
    for key, value in playbook_defaults.items():
        if value is not None and key in resolved:
            resolved[key] = value
            if key == "chunk_size":
                trace.chunk_size = "playbook_defaults"
            elif key == "chunk_overlap":
                trace.chunk_overlap = "playbook_defaults"
            elif key == "min_chunk_size":
                trace.min_chunk_size = "playbook_defaults"
            elif key == "max_chunk_size":
                trace.max_chunk_size = "playbook_defaults"
            elif key == "chunking_strategy":
                trace.chunking_strategy = "playbook_defaults"

    # 4b. Content type defaults (can override playbook if more specific)
    for key, value in content_type_defaults.items():
        if value is not None and key in resolved:
            resolved[key] = value
            if key == "chunk_size":
                trace.chunk_size = "content_type_defaults"
            elif key == "chunk_overlap":
                trace.chunk_overlap = "content_type_defaults"
            elif key == "min_chunk_size":
                trace.min_chunk_size = "content_type_defaults"
            elif key == "max_chunk_size":
                trace.max_chunk_size = "content_type_defaults"
            elif key == "chunking_strategy":
                trace.chunking_strategy = "content_type_defaults"

    # 3. Product manual settings
    for key, value in product_manual_settings.items():
        if value is not None and key in resolved:
            resolved[key] = value
            if key == "chunk_size":
                trace.chunk_size = "product_manual_settings"
            elif key == "chunk_overlap":
                trace.chunk_overlap = "product_manual_settings"
            elif key == "min_chunk_size":
                trace.min_chunk_size = "product_manual_settings"
            elif key == "max_chunk_size":
                trace.max_chunk_size = "product_manual_settings"
            elif key == "chunking_strategy":
                trace.chunking_strategy = "product_manual_settings"

    # 2. force_product_chunking_config (if set in run_conf)
    # CRITICAL: Check run_conf FIRST for resolved_settings before checking database
    # This ensures we use the most up-to-date auto-detected values
    resolved_settings_from_run_conf = None
    run_conf_chunking = run_conf.get("chunking_config", {})
    if isinstance(run_conf_chunking, dict):
        run_conf_resolved = run_conf_chunking.get("resolved_settings", {})
        if isinstance(run_conf_resolved, dict) and run_conf_resolved.get("chunk_size") is not None:
            resolved_settings_from_run_conf = run_conf_resolved
            logger.info(f"[RESOLVER] Found resolved_settings in run_conf: chunk_size={run_conf_resolved.get('chunk_size')}, chunking_strategy={run_conf_resolved.get('chunking_strategy')}")
    
    logger.info(f"[RESOLVER] force_product_chunking_config check: run_conf has it = {run_conf.get('force_product_chunking_config')}")
    if run_conf.get("force_product_chunking_config"):
        # CRITICAL: If mode=auto AND resolved_settings exists with chunking parameters,
        # use resolved_settings instead of content_type_defaults
        logger.info(
            f"[RESOLVER DEBUG] force_product_chunking_config=True. "
            f"product_chunking keys: {list(product_chunking.keys()) if isinstance(product_chunking, dict) else 'N/A'}, "
            f"product_chunking type: {type(product_chunking)}, "
            f"product_chunking full: {product_chunking}"
        )
        chunking_mode = product_chunking.get("mode", "auto")
        
        # PRIORITY: Use resolved_settings from run_conf if available (most up-to-date)
        # Then fallback to database if run_conf doesn't have it
        resolved_settings = resolved_settings_from_run_conf
        
        # FALLBACK: If run_conf doesn't have valid resolved_settings, try database
        if not resolved_settings:
            resolved_settings = product_chunking.get("resolved_settings", {})
            logger.info(f"[RESOLVER DEBUG] Using resolved_settings from DB (has chunk_size={resolved_settings.get('chunk_size') if isinstance(resolved_settings, dict) else None})")
        else:
            logger.info(f"[RESOLVER DEBUG] Using resolved_settings from run_conf (has chunk_size={resolved_settings.get('chunk_size') if isinstance(resolved_settings, dict) else None})")
        
        # Ensure resolved_settings is a dict
        if not isinstance(resolved_settings, dict):
            resolved_settings = {}
        
        # Handle case where resolved_settings might be stored as a string (JSON serialization issue)
        if isinstance(resolved_settings, str):
            import json
            try:
                resolved_settings = json.loads(resolved_settings)
            except (json.JSONDecodeError, TypeError):
                resolved_settings = {}
        
        # Recalculate confidence_met and has_chunking_params AFTER fallback (if it happened)
        # This ensures we use the correct values whether from DB or run_conf fallback
        confidence_met = resolved_settings.get("confidence_met", False) if isinstance(resolved_settings, dict) else False
        
        # Check if resolved_settings has chunking parameters (indicates auto-detection was successful)
        has_chunking_params = (
            isinstance(resolved_settings, dict) 
            and resolved_settings.get("chunk_size") is not None
            and resolved_settings.get("chunking_strategy") is not None
        )
        
        # DEBUG: Log what we're checking
        logger.info(
            f"[RESOLVER DEBUG] force_product_chunking_config check: "
            f"chunking_mode={chunking_mode}, "
            f"resolved_settings_type={type(resolved_settings)}, "
            f"resolved_settings_keys={list(resolved_settings.keys()) if isinstance(resolved_settings, dict) else 'N/A'}, "
            f"chunk_size={resolved_settings.get('chunk_size') if isinstance(resolved_settings, dict) else None}, "
            f"chunking_strategy={resolved_settings.get('chunking_strategy') if isinstance(resolved_settings, dict) else None}, "
            f"confidence_met={confidence_met}, "
            f"has_chunking_params={has_chunking_params}, "
            f"product_chunking_keys={list(product_chunking.keys()) if isinstance(product_chunking, dict) else 'N/A'}"
        )
        
        # Also check if resolved_settings has the required fields but with different structure
        # (e.g., nested in another dict or with different key names)
        if not has_chunking_params and isinstance(resolved_settings, dict):
            # Check for nested structure or alternative keys
            logger.info(f"[RESOLVER DEBUG] resolved_settings doesn't have chunk_size/chunking_strategy at top level. Full structure: {resolved_settings}")
            # Try to find chunk_size/chunking_strategy in nested structures
            for key, value in resolved_settings.items():
                if isinstance(value, dict) and value.get("chunk_size") and value.get("chunking_strategy"):
                    logger.info(f"[RESOLVER DEBUG] Found nested chunking params in key '{key}': {value}")
                    resolved_settings = value
                    has_chunking_params = True
                    break
        
        logger.info(
            f"[RESOLVER DEBUG] Condition check: "
            f"chunking_mode=='auto': {chunking_mode == 'auto'}, "
            f"resolved_settings truthy: {bool(resolved_settings)}, "
            f"isinstance dict: {isinstance(resolved_settings, dict)}, "
            f"confidence_met: {confidence_met}, "
            f"has_chunking_params: {has_chunking_params}, "
            f"FINAL: {chunking_mode == 'auto' and resolved_settings and isinstance(resolved_settings, dict) and (confidence_met or has_chunking_params)}"
        )
        
        # More lenient check: if resolved_settings exists and has any chunking-related keys, use it
        # This handles cases where the structure might be slightly different
        # CRITICAL: Check if resolved_settings has chunk_size - if it does, we MUST use it
        has_chunk_size = isinstance(resolved_settings, dict) and resolved_settings.get("chunk_size") is not None
        has_chunking_strategy = isinstance(resolved_settings, dict) and resolved_settings.get("chunking_strategy") is not None
        
        should_use_resolved_settings = (
            chunking_mode == "auto" 
            and resolved_settings 
            and isinstance(resolved_settings, dict) 
            and (
                confidence_met 
                or has_chunking_params
                or has_chunk_size  # If we have chunk_size, use it
                or (resolved_settings.get("chunk_size") is not None and resolved_settings.get("content_type") is not None)
            )
        )
        
        logger.info(
            f"[RESOLVER DEBUG] Final decision: should_use_resolved_settings={should_use_resolved_settings}, "
            f"has_chunk_size={has_chunk_size}, has_chunking_strategy={has_chunking_strategy}, "
            f"resolved_settings={resolved_settings if isinstance(resolved_settings, dict) and len(str(resolved_settings)) < 500 else 'too_large_to_log'}"
        )
        
        # CRITICAL: If we have resolved_settings from run_conf with chunk_size, ALWAYS use it
        # This ensures auto-detected settings from preprocess stage are always applied
        if resolved_settings_from_run_conf and isinstance(resolved_settings_from_run_conf, dict) and resolved_settings_from_run_conf.get("chunk_size") is not None:
            logger.info(f"[RESOLVER] FORCING use of resolved_settings from run_conf (has chunk_size={resolved_settings_from_run_conf.get('chunk_size')})")
            resolved_settings = resolved_settings_from_run_conf
            should_use_resolved_settings = True
        
        if should_use_resolved_settings:
            # Use resolved_settings from auto-detection
            confidence_note = f"confidence_met={confidence_met}" if confidence_met else "has_chunking_params=True"
            logger.info(
                f"Using auto-detected resolved_settings (mode=auto, {confidence_note}): "
                f"content_type={resolved_settings.get('content_type')}, "
                f"chunk_size={resolved_settings.get('chunk_size')}, "
                f"chunking_strategy={resolved_settings.get('chunking_strategy')}"
            )
            
            # Extract values from resolved_settings
            if resolved_settings.get("chunk_size"):
                resolved["chunk_size"] = resolved_settings["chunk_size"]
                trace.chunk_size = "resolved_settings"
            if resolved_settings.get("chunk_overlap") is not None:
                resolved["chunk_overlap"] = resolved_settings["chunk_overlap"]
                trace.chunk_overlap = "resolved_settings"
            if resolved_settings.get("min_chunk_size"):
                resolved["min_chunk_size"] = resolved_settings["min_chunk_size"]
                trace.min_chunk_size = "resolved_settings"
            if resolved_settings.get("max_chunk_size"):
                resolved["max_chunk_size"] = resolved_settings["max_chunk_size"]
                trace.max_chunk_size = "resolved_settings"
            if resolved_settings.get("chunking_strategy"):
                resolved["chunking_strategy"] = resolved_settings["chunking_strategy"]
                trace.chunking_strategy = "resolved_settings"
            if resolved_settings.get("content_type"):
                ct = resolved_settings["content_type"]
                # Backward compat: "scanned" is not a content_type; treat as general
                resolved["content_type"] = (
                    CONTENT_TYPE_NORMALIZE_SCANNED if (ct and str(ct).strip().lower() == "scanned") else ct
                )
                trace.content_type = "resolved_settings"
            if resolved_settings.get("source_quality") is not None:
                resolved["source_quality"] = resolved_settings["source_quality"]
            # Else keep resolved["source_quality"] from default (product extraction_type)
        else:
            # Fallback: use product_chunking top-level fields (backward compatibility)
            logger.info(
                f"[RESOLVER DEBUG] Falling back to product_chunking top-level fields. "
                f"Reason: chunking_mode={chunking_mode}, resolved_settings={bool(resolved_settings)}, "
                f"is_dict={isinstance(resolved_settings, dict)}, confidence_met={confidence_met}, "
                f"has_chunking_params={has_chunking_params}"
            )
            for key, value in product_chunking.items():
                if value is not None and key in resolved:
                    resolved[key] = value
                    if key == "chunk_size":
                        trace.chunk_size = "force_product_chunking_config"
                    elif key == "chunk_overlap":
                        trace.chunk_overlap = "force_product_chunking_config"
                    elif key == "min_chunk_size":
                        trace.min_chunk_size = "force_product_chunking_config"
                    elif key == "max_chunk_size":
                        trace.max_chunk_size = "force_product_chunking_config"
                    elif key == "chunking_strategy":
                        trace.chunking_strategy = "force_product_chunking_config"

    # 1. run_conf overrides (highest priority)
    run_chunking = _ensure_dict(run_conf.get("chunking_config"))
    for key, value in run_chunking.items():
        if value is not None and key in resolved:
            resolved[key] = value
            if key == "chunk_size":
                trace.chunk_size = "run_conf"
            elif key == "chunk_overlap":
                trace.chunk_overlap = "run_conf"
            elif key == "min_chunk_size":
                trace.min_chunk_size = "run_conf"
            elif key == "max_chunk_size":
                trace.max_chunk_size = "run_conf"
            elif key == "chunking_strategy":
                trace.chunking_strategy = "run_conf"

    # Also check for direct overrides in run_conf
    for key in ["chunk_size", "chunk_overlap", "min_chunk_size", "max_chunk_size", "chunking_strategy"]:
        if key in run_conf and run_conf[key] is not None:
            resolved[key] = run_conf[key]
            if key == "chunk_size":
                trace.chunk_size = "run_conf"
            elif key == "chunk_overlap":
                trace.chunk_overlap = "run_conf"
            elif key == "min_chunk_size":
                trace.min_chunk_size = "run_conf"
            elif key == "max_chunk_size":
                trace.max_chunk_size = "run_conf"
            elif key == "chunking_strategy":
                trace.chunking_strategy = "run_conf"

    # Normalize content_type: never use "scanned" as content_type (it is source_quality)
    final_content_type = resolved["content_type"]
    if final_content_type and str(final_content_type).strip().lower() == "scanned":
        final_content_type = CONTENT_TYPE_NORMALIZE_SCANNED

    # Build ChunkingConfig
    chunking_config = ChunkingConfig(
        mode=product_chunking.get("mode", "auto"),
        chunk_size=resolved["chunk_size"],
        chunk_overlap=resolved["chunk_overlap"],
        min_chunk_size=resolved["min_chunk_size"],
        max_chunk_size=resolved["max_chunk_size"],
        chunking_strategy=resolved["chunking_strategy"],
        content_type=final_content_type,
        source_quality=resolved.get("source_quality"),
        confidence=product_auto_settings.get("confidence"),
    )

    # Structured log: final chunking_config used by downstream (preprocess/indexing)
    logger.info(
        "[CHUNKING_CONFIG] resolver output: stage=resolve_effective_config "
        "chunk_size=%s chunk_overlap=%s chunking_strategy=%s content_type=%s source_quality=%s "
        "trace_chunk_size=%s trace_content_type=%s",
        chunking_config.chunk_size,
        chunking_config.chunk_overlap,
        chunking_config.chunking_strategy,
        chunking_config.content_type,
        getattr(chunking_config, "source_quality", None),
        trace.chunk_size,
        trace.content_type,
    )

    return EffectiveConfig(
        chunking_config=chunking_config,
        playbook_id=playbook_id,
        playbook_config=playbook_config,
        resolution_trace=trace,
    )
