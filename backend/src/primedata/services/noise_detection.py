"""
Noise detection for AI-Ready metrics.

Detects boilerplate, navigation, and legal footer content in chunks.
"""
import re
import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


def calculate_noise_ratio(
    chunk_text: str,
    noise_patterns: Optional[Dict[str, List[Dict[str, Any]]]] = None
) -> Dict[str, Any]:
    """
    Calculate noise ratio for a chunk.
    
    Args:
        chunk_text: The chunk text to analyze
        noise_patterns: Dictionary with 'boilerplate', 'navigation', 'legal_footer' patterns
                        Each pattern has 'pattern' (regex) and 'flags' (optional)
    
    Returns:
        Dict with noise ratio and breakdown
    """
    if not chunk_text:
        return {
            "noise_ratio": 0.0,
            "total_chars": 0,
            "noise_chars": 0,
            "boilerplate_chars": 0,
            "navigation_chars": 0,
            "legal_footer_chars": 0
        }
    
    if not noise_patterns:
        # Default patterns if none provided
        noise_patterns = _get_default_noise_patterns()
    
    total_chars = len(chunk_text)
    noise_chars = 0
    boilerplate_chars = 0
    navigation_chars = 0
    legal_footer_chars = 0
    
    # Track matched positions to avoid double-counting
    matched_positions = set()
    
    # Check boilerplate patterns
    if 'boilerplate' in noise_patterns:
        for pattern_config in noise_patterns['boilerplate']:
            pattern = pattern_config.get('pattern')
            flags_str = pattern_config.get('flags', '')
            
            if not pattern:
                continue
            
            flags = 0
            if 'MULTILINE' in flags_str:
                flags |= re.MULTILINE
            if 'IGNORECASE' in flags_str:
                flags |= re.IGNORECASE
            
            try:
                regex = re.compile(pattern, flags)
                for match in regex.finditer(chunk_text):
                    start, end = match.span()
                    # Only count if not already matched
                    if not any(start <= pos < end for pos in matched_positions):
                        length = end - start
                        boilerplate_chars += length
                        noise_chars += length
                        matched_positions.update(range(start, end))
            except Exception as e:
                logger.warning(f"Error in boilerplate pattern {pattern}: {e}")
    
    # Check navigation patterns
    if 'navigation' in noise_patterns:
        for pattern_config in noise_patterns.get('navigation', []):
            pattern = pattern_config.get('pattern')
            flags_str = pattern_config.get('flags', '')
            
            if not pattern:
                continue
            
            flags = 0
            if 'MULTILINE' in flags_str:
                flags |= re.MULTILINE
            if 'IGNORECASE' in flags_str:
                flags |= re.IGNORECASE
            
            try:
                regex = re.compile(pattern, flags)
                for match in regex.finditer(chunk_text):
                    start, end = match.span()
                    if not any(start <= pos < end for pos in matched_positions):
                        length = end - start
                        navigation_chars += length
                        noise_chars += length
                        matched_positions.update(range(start, end))
            except Exception as e:
                logger.warning(f"Error in navigation pattern {pattern}: {e}")
    
    # Check legal footer patterns
    if 'legal_footer' in noise_patterns:
        for pattern_config in noise_patterns.get('legal_footer', []):
            pattern = pattern_config.get('pattern')
            flags_str = pattern_config.get('flags', '')
            
            if not pattern:
                continue
            
            flags = 0
            if 'MULTILINE' in flags_str:
                flags |= re.MULTILINE
            if 'IGNORECASE' in flags_str:
                flags |= re.IGNORECASE
            
            try:
                regex = re.compile(pattern, flags)
                for match in regex.finditer(chunk_text):
                    start, end = match.span()
                    if not any(start <= pos < end for pos in matched_positions):
                        length = end - start
                        legal_footer_chars += length
                        noise_chars += length
                        matched_positions.update(range(start, end))
            except Exception as e:
                logger.warning(f"Error in legal_footer pattern {pattern}: {e}")
    
    # Calculate noise ratio
    noise_ratio = (noise_chars / total_chars * 100) if total_chars > 0 else 0.0
    
    return {
        "noise_ratio": round(noise_ratio, 2),
        "total_chars": total_chars,
        "noise_chars": noise_chars,
        "boilerplate_chars": boilerplate_chars,
        "navigation_chars": navigation_chars,
        "legal_footer_chars": legal_footer_chars
    }


def _get_default_noise_patterns() -> Dict[str, List[Dict[str, Any]]]:
    """Get default noise patterns if playbook doesn't provide them."""
    return {
        "boilerplate": [
            {
                "pattern": r"(?i)^\s*(confidential|proprietary|copyright|all rights reserved)",
                "flags": "MULTILINE"
            },
            {
                "pattern": r"(?i)^\s*page\s+\d+\s+of\s+\d+\s*$",
                "flags": "MULTILINE"
            }
        ],
        "navigation": [
            {
                "pattern": r"(?i)^\s*(table of contents|index|appendix)\s*$",
                "flags": "MULTILINE"
            }
        ],
        "legal_footer": [
            {
                "pattern": r"(?i)^\s*(this document is confidential|not for distribution)",
                "flags": "MULTILINE"
            }
        ]
    }

