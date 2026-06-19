"""
LLM-based text optimization service.

This module provides LLM API integration for intelligent text enhancement.
"""

import logging as std_logging  # For Airflow compatibility
import os
from typing import Any, Dict, List, Optional

from loguru import logger

# Use Python logging for Airflow compatibility
std_logger = std_logging.getLogger(__name__)

try:
    from openai import OpenAI

    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    logger.warning("OpenAI package not available. LLM optimization will not work.")
    std_logger.warning("OpenAI package not available. LLM optimization will not work.")


class LLMOptimizationService:
    """Service for LLM-based text optimization."""

    # Model pricing (per 1K tokens, approximate)
    MODEL_PRICING = {
        "gpt-4-turbo-preview": {"input": 0.01, "output": 0.03},
        "gpt-4": {"input": 0.03, "output": 0.06},
        "gpt-3.5-turbo": {"input": 0.001, "output": 0.002},
        "gpt-4o": {"input": 0.005, "output": 0.015},
        "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    }

    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4-turbo-preview", base_url: Optional[str] = None):
        """
        Initialize LLM optimization service.

        Args:
            api_key: OpenAI API key (or use OPENAI_API_KEY env var)
            model: Model to use for optimization
            base_url: Optional base URL for API (for custom endpoints)
        """
        if not OPENAI_AVAILABLE:
            raise ImportError("OpenAI package is required for LLM optimization. Install with: pip install openai")

        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key is required. Set OPENAI_API_KEY environment variable or pass api_key parameter.")

        self.model = model
        # Set timeout to 30 seconds to prevent hanging requests
        import httpx

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=base_url,
            timeout=httpx.Timeout(30.0, connect=10.0),  # 30s timeout, 10s connect timeout
        )

        # Get pricing for model (default to gpt-4-turbo-preview if unknown)
        self.pricing = self.MODEL_PRICING.get(model, self.MODEL_PRICING["gpt-4-turbo-preview"])

    def enhance_text(self, text: str, context: Optional[str] = None, preserve_formatting: bool = True) -> Dict[str, Any]:
        """
        Use LLM to enhance text quality.

        Args:
            text: Text to enhance
            context: Optional context about the document
            preserve_formatting: Whether to preserve original formatting

        Returns:
            Dictionary with:
                - enhanced_text: Optimized text
                - changes_made: List of changes made
                - cost_estimate: Estimated cost
                - tokens_used: Tokens used (input + output)
                - input_tokens: Input tokens
                - output_tokens: Output tokens
        """
        if not text or len(text.strip()) == 0:
            return {
                "enhanced_text": text,
                "changes_made": [],
                "cost_estimate": 0.0,
                "tokens_used": 0,
                "input_tokens": 0,
                "output_tokens": 0,
            }

        # Build prompt
        prompt = self._build_optimization_prompt(text, context, preserve_formatting)

        try:
            # Call LLM API
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert at cleaning and optimizing text for AI/ML processing. "
                        "Fix OCR errors, improve text quality, and normalize formatting while "
                        "preserving all factual information and meaning. Only fix errors and formatting.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,  # Lower temperature for more consistent results
                max_tokens=min(4096, len(text) + 500),  # Allow some expansion but limit
            )

            enhanced_text = response.choices[0].message.content.strip()

            # Calculate cost
            input_tokens = response.usage.prompt_tokens
            output_tokens = response.usage.completion_tokens
            total_tokens = response.usage.total_tokens

            cost_estimate = (input_tokens / 1000) * self.pricing["input"] + (output_tokens / 1000) * self.pricing["output"]

            # Detect changes (simple comparison)
            changes_made = self._detect_changes(text, enhanced_text)

            logger.info(
                f"LLM optimization completed: {total_tokens} tokens, "
                f"cost=${cost_estimate:.4f}, changes={len(changes_made)}"
            )
            std_logger.info(
                f"✅ LLM optimization completed: {total_tokens} tokens, "
                f"cost=${cost_estimate:.4f}, changes={len(changes_made)}"
            )

            return {
                "enhanced_text": enhanced_text,
                "changes_made": changes_made,
                "cost_estimate": cost_estimate,
                "tokens_used": total_tokens,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            }

        except Exception as e:
            error_msg = f"LLM optimization failed: {e}"
            logger.error(error_msg, exc_info=True)
            std_logger.error(error_msg, exc_info=True)
            # Return original text on error
            return {
                "enhanced_text": text,
                "changes_made": [],
                "cost_estimate": 0.0,
                "tokens_used": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "error": str(e),
            }

    def estimate_cost(self, text_length: int) -> float:
        """
        Estimate cost for text optimization.

        Args:
            text_length: Length of text in characters

        Returns:
            Estimated cost in USD
        """
        # Rough estimate: 1 token ≈ 4 characters
        estimated_input_tokens = text_length / 4

        # Assume output is similar length to input (conservative estimate)
        estimated_output_tokens = estimated_input_tokens

        cost = (estimated_input_tokens / 1000) * self.pricing["input"] + (estimated_output_tokens / 1000) * self.pricing[
            "output"
        ]

        return cost

    def _build_optimization_prompt(self, text: str, context: Optional[str] = None, preserve_formatting: bool = True) -> str:
        """Build optimization prompt for LLM."""
        prompt_parts = [
            "Fix OCR errors, improve text quality, and normalize formatting in the following text.",
            "Preserve all factual information and meaning.",
            "Only fix errors and formatting issues - do not change content or add information.",
        ]

        if preserve_formatting:
            prompt_parts.append("Preserve the original structure and formatting as much as possible.")

        if context:
            prompt_parts.append(f"Context: {context}")

        prompt_parts.extend(
            [
                "",
                "Text to optimize:",
                text,
                "",
                "Enhanced text (return only the optimized text, no explanations):",
            ]
        )

        return "\n".join(prompt_parts)

    def _detect_changes(self, original: str, enhanced: str) -> List[str]:
        """
        Detect and list changes made to text.

        Simple implementation - can be enhanced later.
        """
        changes = []

        # Compare length
        if len(enhanced) != len(original):
            changes.append(f"Length changed: {len(original)} → {len(enhanced)} characters")

        # Check for common improvements
        if original.count("  ") > enhanced.count("  "):
            changes.append("Multiple spaces normalized")

        # Check for OCR error fixes
        ocr_errors_original = ["teh", "adn", "hte", "tha", "taht"]
        ocr_errors_enhanced = ["teh", "adn", "hte", "tha", "taht"]
        for error in ocr_errors_original:
            if error in original.lower() and error not in enhanced.lower():
                changes.append(f"OCR error fixed: '{error}'")

        # Simple word count comparison
        if len(enhanced.split()) != len(original.split()):
            changes.append(f"Word count changed: {len(original.split())} → {len(enhanced.split())} words")

        if not changes:
            changes.append("Minor formatting improvements")

        return changes
