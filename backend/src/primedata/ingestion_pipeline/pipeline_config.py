"""Pipeline configuration resolution helpers."""

from __future__ import annotations

from typing import Any, Dict, Optional

from primedata.analysis.content_analyzer import ContentType, content_analyzer
from primedata.config.models import extraction_type_to_source_quality

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
    return value if isinstance(value, dict) else {}


def _merge_chunking_config(
    product_config: Optional[Dict[str, Any]],
    dag_config: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    merged.update(_ensure_dict(product_config))
    for key, value in _ensure_dict(dag_config).items():
        if value is not None:
            merged[key] = value
    return merged


def _resolved_from_settings(
    manual_settings: Dict[str, Any],
    auto_settings: Dict[str, Any],
    source: str,
) -> Dict[str, Any]:
    content_type = auto_settings.get("content_type", DEFAULT_AUTO_SETTINGS["content_type"])
    default_config = content_analyzer.optimal_configs.get(
        ContentType(content_type) if content_type in ContentType._value2member_map_ else ContentType.GENERAL
    )
    if default_config:
        defaults = {
            "chunk_size": default_config["chunk_size"],
            "chunk_overlap": default_config["chunk_overlap"],
            "min_chunk_size": default_config["min_chunk_size"],
            "max_chunk_size": default_config["max_chunk_size"],
            "chunking_strategy": default_config["strategy"].value,
        }
    else:
        defaults = DEFAULT_MANUAL_SETTINGS

    return {
        "content_type": content_type,
        "source_quality": None,  # Set at effective level from product.extraction_type when available
        "chunk_size": manual_settings.get("chunk_size", defaults["chunk_size"]),
        "chunk_overlap": manual_settings.get("chunk_overlap", defaults["chunk_overlap"]),
        "min_chunk_size": manual_settings.get("min_chunk_size", defaults["min_chunk_size"]),
        "max_chunk_size": manual_settings.get("max_chunk_size", defaults["max_chunk_size"]),
        "chunking_strategy": manual_settings.get("chunking_strategy", defaults["chunking_strategy"]),
        "source": source,
    }


def _is_confident(settings: Optional[Dict[str, Any]], threshold: float) -> bool:
    if not settings or not isinstance(settings, dict):
        return False
    confidence = settings.get("confidence")
    if confidence is None:
        return True
    try:
        return float(confidence) >= threshold
    except (TypeError, ValueError):
        return True


def resolve_effective_pipeline_config(
    product: Any,
    dag_conf: Optional[Dict[str, Any]],
    pipeline_run: Any,
) -> Dict[str, Any]:
    """Resolve effective chunking config and playbook selection for a pipeline run."""
    dag_conf = dag_conf or {}

    product_chunking = _ensure_dict(getattr(product, "chunking_config", None))
    if dag_conf.get("force_product_chunking_config"):
        effective_chunking_config = product_chunking
        playbook_id = dag_conf.get("playbook_id") or getattr(product, "playbook_id", None)
        playbook_selection = _ensure_dict(getattr(product, "playbook_selection", None))
        return {
            "chunking_config": effective_chunking_config,
            "playbook_id": playbook_id,
            "playbook_selection": playbook_selection or None,
        }
    chunking_config = _merge_chunking_config(product_chunking, dag_conf.get("chunking_config"))

    manual_settings = _ensure_dict(chunking_config.get("manual_settings")) or DEFAULT_MANUAL_SETTINGS.copy()
    auto_settings = _ensure_dict(chunking_config.get("auto_settings")) or DEFAULT_AUTO_SETTINGS.copy()
    mode = chunking_config.get("mode", "auto")

    confidence_threshold = auto_settings.get("confidence_threshold", DEFAULT_AUTO_SETTINGS["confidence_threshold"])

    pipeline_metrics = _ensure_dict(getattr(pipeline_run, "metrics", None))
    pipeline_resolved = _ensure_dict(pipeline_metrics.get("chunking_config", {})).get("resolved_settings")
    product_resolved = chunking_config.get("resolved_settings")

    resolved_settings: Optional[Dict[str, Any]] = None
    resolved_source = None

    if _is_confident(pipeline_resolved, confidence_threshold):
        resolved_settings = pipeline_resolved
        resolved_source = "pipeline_run"
    elif _is_confident(product_resolved, confidence_threshold):
        resolved_settings = product_resolved
        resolved_source = "product"

    manual_provided = bool(manual_settings) and (
        manual_settings != DEFAULT_MANUAL_SETTINGS or mode == "manual"
    )

    if resolved_settings is None:
        if manual_provided:
            resolved_settings = _resolved_from_settings(manual_settings, auto_settings, "manual_settings")
            resolved_source = "manual_settings"
        elif auto_settings:
            resolved_settings = _resolved_from_settings(manual_settings, auto_settings, "auto_settings")
            resolved_source = "auto_settings"
        else:
            resolved_settings = _resolved_from_settings(DEFAULT_MANUAL_SETTINGS, DEFAULT_AUTO_SETTINGS, "defaults")
            resolved_source = "defaults"

    # Ensure source_quality in resolved_settings (native_pdf|scanned_ocr|mixed) from product.extraction_type
    if resolved_settings.get("source_quality") is None:
        resolved_settings = {
            **resolved_settings,
            "source_quality": extraction_type_to_source_quality(getattr(product, "extraction_type", None)),
        }

    effective_chunking_config = {
        **chunking_config,
        "mode": mode,
        "manual_settings": manual_settings,
        "auto_settings": auto_settings,
        "resolved_settings": {**resolved_settings, "source": resolved_source},
    }

    playbook_id = dag_conf.get("playbook_id") or getattr(product, "playbook_id", None)
    playbook_selection = _ensure_dict(getattr(product, "playbook_selection", None))

    dag_playbook_selection = _ensure_dict(dag_conf.get("playbook_selection"))
    if dag_playbook_selection.get("method") == "manual":
        playbook_selection = dag_playbook_selection
    elif dag_conf.get("playbook_id") and not playbook_selection:
        playbook_selection = {
            "playbook_id": playbook_id,
            "method": "manual",
            "reason": None,
            "detected_at": None,
        }

    return {
        "chunking_config": effective_chunking_config,
        "playbook_id": playbook_id,
        "playbook_selection": playbook_selection or None,
    }


def should_skip_vectors(product: Any) -> bool:
    return bool(product) and getattr(product, "vector_creation_enabled", True) is False


def resolve_content_hint(playbook_id: Optional[str], use_case_description: Optional[str]) -> Optional[str]:
    if use_case_description:
        text = use_case_description.lower()
        if any(term in text for term in ["regulatory", "compliance", "regulation"]):
            return "regulatory"
        if any(term in text for term in ["finance", "banking", "financial"]):
            return "finance_banking"
        if "legal" in text:
            return "legal"
        if any(term in text for term in ["medical", "clinical", "health", "who", "guideline"]):
            return "medical"
        if "academic" in text:
            return "academic"
        if "technical" in text:
            return "technical"

    if not playbook_id:
        return None

    playbook_id_lower = playbook_id.lower()
    if "regulatory" in playbook_id_lower or playbook_id_lower in ["regulatory", "reg"]:
        return "regulatory"
    if "finance" in playbook_id_lower or "banking" in playbook_id_lower or playbook_id_lower in ["finance", "banking"]:
        return "finance_banking"
    if "legal" in playbook_id_lower:
        return "legal"
    if "medical" in playbook_id_lower or "healthcare" in playbook_id_lower:
        return "medical"
    if "academic" in playbook_id_lower:
        return "academic"
    if "technical" in playbook_id_lower or playbook_id_lower == "tech":
        return "technical"

    return None
