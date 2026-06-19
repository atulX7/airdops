"""
Policy engine service for PrimeData.

Evaluates readiness fingerprints against policy thresholds.
"""

from typing import Any, Dict, List, Optional

from loguru import logger

# Default thresholds (normalized to [0,1] range to match scoring system)
DEFAULT_THRESHOLDS: Dict[str, float] = {
    "min_trust_score": 0.5,  # 50% in [0,1] range
    "min_secure": 0.9,  # 90% in [0,1] range
    "min_metadata_presence": 0.8,  # 80% in [0,1] range
    "min_kb_ready": 0.5,  # 50% in [0,1] range
}


def evaluate_policy(
    fingerprint: Dict[str, float],
    thresholds: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """
    Evaluate whether a readiness fingerprint satisfies policy constraints.

    Args:
        fingerprint: Readiness fingerprint dictionary with metrics
        thresholds: Optional threshold overrides

    Returns:
        Dict with:
            - policy_passed: bool
            - violations: List[str]
            - thresholds: Dict[str, float]
    """
    # Merge defaults + overrides
    th = dict(DEFAULT_THRESHOLDS)
    if thresholds:
        th.update(thresholds)

    # No fingerprint at all → automatic fail
    if not fingerprint:
        return {
            "status": "failed",
            "policy_passed": False,
            "violations": ["no_fingerprint"],
            "warnings": [],
            "thresholds": th,
        }

    violations: List[str] = []

    # Helper to get metric value from canonical schema (checks legacy_aliases if needed)
    def get_metric(fingerprint: Dict[str, Any], canonical_key: Optional[str], legacy_key: Optional[str] = None) -> float:
        """Get metric value, checking canonical key first, then legacy_aliases."""
        # Try canonical key first (if provided)
        if canonical_key and canonical_key in fingerprint:
            return float(fingerprint[canonical_key])
        # Try legacy key at top-level (backward compatibility)
        if legacy_key and legacy_key in fingerprint:
            return float(fingerprint[legacy_key])
        # Try legacy_aliases
        if "legacy_aliases" in fingerprint and isinstance(fingerprint["legacy_aliases"], dict):
            if legacy_key and legacy_key in fingerprint["legacy_aliases"]:
                return float(fingerprint["legacy_aliases"][legacy_key])
        return 0.0

    trust = get_metric(fingerprint, "ai_trust_score", "AI_Trust_Score")
    secure = get_metric(fingerprint, None, "Secure")  # Secure only exists as legacy
    metadata = get_metric(fingerprint, "metadata_completeness", "Metadata_Presence")
    kb_ready = get_metric(fingerprint, None, "KnowledgeBase_Ready")  # KB_Ready only exists as legacy

    # Overall trust
    if trust < th["min_trust_score"]:
        violations.append(f"low_trust(<{th['min_trust_score']})")

    # Security
    if secure < th["min_secure"]:
        violations.append(f"security_not_full(<{th['min_secure']})")

    # Metadata completeness
    if metadata < th["min_metadata_presence"]:
        violations.append(f"weak_metadata(<{th['min_metadata_presence']})")

    # KB / RAG readiness
    if kb_ready < th["min_kb_ready"]:
        violations.append(f"kb_not_ready(<{th['min_kb_ready']})")

    policy_passed = len(violations) == 0

    # Determine status: "passed", "failed", or "warnings" (if passed but has minor issues)
    if policy_passed:
        status = "passed"
    else:
        # Check if violations are critical (trust score or security) vs warnings
        critical_violations = [v for v in violations if "low_trust" in v or "security_not_full" in v]
        status = "failed" if critical_violations else "warnings"

    logger.info(
        f"Policy evaluation: passed={policy_passed}, status={status}, violations={len(violations)}",
        trust_score=trust,
        secure=secure,
    )

    return {
        "status": status,  # "passed", "failed", or "warnings"
        "policy_passed": policy_passed,
        "violations": violations,
        "warnings": [],  # Separate warnings from violations if needed
        "thresholds": th,
    }
