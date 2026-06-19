"""
Hybrid optimization orchestrator.

Combines pattern-based and LLM-based optimization intelligently.
"""

import logging as std_logging  # For Airflow compatibility
from typing import Any, Dict, Optional

from loguru import logger

# Use Python logging for Airflow compatibility
std_logger = std_logging.getLogger(__name__)

from .pattern_based import PatternBasedOptimizer


class HybridOptimizer:
    """Orchestrates pattern-based and LLM-based optimization."""

    def __init__(self):
        self.pattern_optimizer = PatternBasedOptimizer()

    def optimize(
        self,
        text: str,
        mode: str = "pattern",  # "pattern", "llm", "hybrid"
        pattern_flags: Optional[Dict[str, bool]] = None,
        llm_config: Optional[Dict[str, Any]] = None,
        quality_threshold: int = 75,
    ) -> Dict[str, Any]:
        """
        Optimize text using hybrid approach.

        Args:
            text: Input text
            mode: Optimization mode ("pattern", "llm", or "hybrid")
            pattern_flags: Flags for pattern-based optimization
            llm_config: LLM configuration dict with:
                - api_key: OpenAI API key (optional, uses env var if not provided)
                - model: Model name (default: "gpt-4-turbo-preview")
                - base_url: Optional base URL for API
            quality_threshold: Quality score threshold to trigger LLM (for hybrid mode)

        Returns:
            Dictionary with:
                - optimized_text: Optimized text
                - method_used: "pattern", "llm", or "hybrid"
                - quality_score: Estimated quality score
                - cost: Total cost (USD)
                - changes: List of changes made
                - llm_details: LLM optimization details (if LLM was used)
        """
        pattern_flags = pattern_flags or {}

        result = {
            "optimized_text": text,
            "method_used": "pattern",
            "quality_score": 0.0,
            "cost": 0.0,
            "changes": [],
            "llm_details": None,
        }

        if not text or len(text.strip()) == 0:
            return result

        # Step 1: Always apply pattern-based first (fast, free)
        logger.debug(f"Applying pattern-based optimization (mode: {mode})")
        initial_quality = self.pattern_optimizer.estimate_quality(text)  # Quality before any optimization
        optimized_text = self.pattern_optimizer.optimize(text, pattern_flags)
        quality_score = self.pattern_optimizer.estimate_quality(optimized_text)  # Quality after pattern-based

        result["optimized_text"] = optimized_text
        result["quality_score"] = quality_score
        result["method_used"] = "pattern"

        # Step 2: Apply LLM enhancement if needed
        should_use_llm = False

        if mode == "llm":
            should_use_llm = True
            logger.info(f"LLM mode: Will use LLM optimization (current quality: {quality_score:.1f}%)")
            std_logger.info(f"LLM mode: Will use LLM optimization (current quality: {quality_score:.1f}%)")
        elif mode == "hybrid" and quality_score < quality_threshold:
            should_use_llm = True
            logger.info(
                f"Hybrid mode: Quality score ({quality_score:.1f}%) below threshold "
                f"({quality_threshold}%), will use LLM enhancement"
            )
            std_logger.info(
                f"Hybrid mode: Quality score ({quality_score:.1f}%) below threshold "
                f"({quality_threshold}%), will use LLM enhancement"
            )

        if should_use_llm:
            if not llm_config:
                logger.warning(
                    f"LLM optimization requested (mode: {mode}) but no LLM config provided. "
                    "Falling back to pattern-based only."
                )
                std_logger.warning(
                    f"LLM optimization requested (mode: {mode}) but no LLM config provided. "
                    "Falling back to pattern-based only."
                )
            else:
                try:
                    from primedata.services.llm_optimization import LLMOptimizationService

                    llm_service = LLMOptimizationService(
                        api_key=llm_config.get("api_key"),
                        model=llm_config.get("model", "gpt-4-turbo-preview"),
                        base_url=llm_config.get("base_url"),
                    )

                    logger.info(f"Applying LLM optimization with model: {llm_service.model}")
                    std_logger.info(f"Applying LLM optimization with model: {llm_service.model}")
                    llm_result = llm_service.enhance_text(optimized_text)

                    if "error" not in llm_result:
                        result["optimized_text"] = llm_result["enhanced_text"]
                        result["method_used"] = "llm" if mode == "llm" else "hybrid"
                        result["cost"] = llm_result["cost_estimate"]
                        result["changes"].extend(llm_result.get("changes_made", []))
                        result["llm_details"] = {
                            "tokens_used": llm_result.get("tokens_used", 0),
                            "input_tokens": llm_result.get("input_tokens", 0),
                            "output_tokens": llm_result.get("output_tokens", 0),
                            "model": llm_service.model,
                        }

                        # Re-estimate quality after LLM enhancement
                        final_quality = self.pattern_optimizer.estimate_quality(result["optimized_text"])
                        result["quality_score"] = final_quality

                        # Calculate improvement
                        quality_improvement = final_quality - quality_score
                        logger.info(
                            f"LLM optimization completed: cost=${result['cost']:.4f}, "
                            f"quality={initial_quality:.1f}% → {quality_score:.1f}% (pattern) → {final_quality:.1f}% (LLM), "
                            f"improvement=+{quality_improvement:.1f}%"
                        )
                        std_logger.info(
                            f"✅ LLM optimization completed: cost=${result['cost']:.4f}, "
                            f"quality={initial_quality:.1f}% → {quality_score:.1f}% (pattern) → {final_quality:.1f}% (LLM), "
                            f"improvement=+{quality_improvement:.1f}%"
                        )
                    else:
                        error_msg = f"LLM optimization failed: {llm_result.get('error')}. Using pattern-based result only."
                        logger.error(error_msg)
                        std_logger.error(error_msg)

                except ImportError as e:
                    error_msg = f"LLM optimization requested but OpenAI package not available: {e}. Falling back to pattern-based only."
                    logger.error(error_msg)
                    std_logger.error(error_msg)
                except Exception as e:
                    error_msg = f"LLM optimization failed: {e}. Using pattern-based result only."
                    logger.error(error_msg, exc_info=True)
                    std_logger.error(error_msg, exc_info=True)

        return result

    def estimate_cost(
        self,
        text_length: int,
        mode: str = "pattern",
        llm_config: Optional[Dict[str, Any]] = None,
        quality_estimate: Optional[float] = None,
        quality_threshold: int = 75,
    ) -> float:
        """
        Estimate cost for optimization.

        Args:
            text_length: Length of text in characters
            mode: Optimization mode
            llm_config: LLM configuration (for cost estimation)
            quality_estimate: Estimated quality score (for hybrid mode)
            quality_threshold: Quality threshold for hybrid mode

        Returns:
            Estimated cost in USD
        """
        cost = 0.0  # Pattern-based is free

        # Estimate LLM cost if needed
        if mode == "llm":
            if llm_config:
                try:
                    from primedata.services.llm_optimization import LLMOptimizationService

                    llm_service = LLMOptimizationService(
                        api_key=llm_config.get("api_key"),
                        model=llm_config.get("model", "gpt-4-turbo-preview"),
                    )
                    cost = llm_service.estimate_cost(text_length)
                except Exception:
                    pass
        elif mode == "hybrid":
            # Only estimate LLM cost if quality is below threshold
            if quality_estimate is None:
                # Use conservative estimate (assume 50% of docs need LLM)
                if llm_config:
                    try:
                        from primedata.services.llm_optimization import LLMOptimizationService

                        llm_service = LLMOptimizationService(
                            api_key=llm_config.get("api_key"),
                            model=llm_config.get("model", "gpt-4-turbo-preview"),
                        )
                        cost = llm_service.estimate_cost(text_length) * 0.5  # 50% of docs
                    except Exception:
                        pass
            elif quality_estimate < quality_threshold and llm_config:
                try:
                    from primedata.services.llm_optimization import LLMOptimizationService

                    llm_service = LLMOptimizationService(
                        api_key=llm_config.get("api_key"),
                        model=llm_config.get("model", "gpt-4-turbo-preview"),
                    )
                    cost = llm_service.estimate_cost(text_length)
                except Exception:
                    pass

        return cost
