"""
Playbook router for AIRD preprocessing.

Routes documents to appropriate playbooks based on content heuristics.
"""

import re
from pathlib import Path
from typing import Dict, Optional

from loguru import logger

from .loader import get_playbook_dir, load_playbook_yaml


def _index_playbooks() -> Dict[str, Path]:
    """
    Build an in-memory index of available playbooks.

    Returns:
        dict mapping canonical lower-case name -> Path to YAML
        e.g. {'tech': /.../TECH.yaml, 'scanned': /.../SCANNED.yaml}
    """
    playbook_dir = get_playbook_dir()
    if not playbook_dir:
        return {}

    index: Dict[str, Path] = {}
    for p in playbook_dir.glob("*.yaml"):
        stem = p.stem  # e.g. "TECH"
        key = stem.strip().lower()
        index[key] = p
    return index


_PLAYBOOK_INDEX: Dict[str, Path] = _index_playbooks()


def refresh_index() -> None:
    """Rebuild the playbook index (if you add files at runtime)."""
    global _PLAYBOOK_INDEX
    _PLAYBOOK_INDEX = _index_playbooks()


def list_playbooks() -> Dict[str, Path]:
    """
    Return the current (lower-case) name -> Path mapping.
    """
    return dict(_PLAYBOOK_INDEX)


def resolve_playbook_file(playbook_id: Optional[str]) -> Optional[Path]:
    """
    Accepts 'tech', 'TECH', 'Tech', 'scanned', etc. Returns a Path to the YAML.
    Falls back to TECH.yaml (if present) or the first YAML in folder.

    Args:
        playbook_id: name/id string (case-insensitive); can be None

    Returns:
        Path to the resolved YAML file, or None if not found
    """
    if not _PLAYBOOK_INDEX:
        refresh_index()

    if not playbook_id:
        # default to TECH if available
        if "tech" in _PLAYBOOK_INDEX:
            return _PLAYBOOK_INDEX["tech"]
        # else first available yaml
        if _PLAYBOOK_INDEX:
            return next(iter(_PLAYBOOK_INDEX.values()))
        return None

    pid = str(playbook_id).strip().lower()
    if pid in _PLAYBOOK_INDEX:
        return _PLAYBOOK_INDEX[pid]

    # Try normalized matching (strip hyphens/underscores/spaces)
    pid_norm = re.sub(r"[-_ ]+", "", pid)
    for k, v in _PLAYBOOK_INDEX.items():
        if re.sub(r"[-_ ]+", "", k) == pid_norm:
            return v

    # Fallbacks
    if "tech" in _PLAYBOOK_INDEX:
        return _PLAYBOOK_INDEX["tech"]
    if _PLAYBOOK_INDEX:
        return next(iter(_PLAYBOOK_INDEX.values()))
    return None


def route_playbook(sample_text: Optional[str] = None, filename: Optional[str] = None) -> tuple[str, str]:
    """
    Very simple heuristic router that returns a *playbook ID string* and reason.
    Update heuristics as your classification needs grow.

    Args:
        sample_text: optional text to guide routing
        filename: optional filename to guide routing

    Returns:
        Tuple of (playbook_id, reason) e.g., ('TECH', 'default') or ('SCANNED', 'ocr_keywords')
    """
    # Always operate on the current index
    if not _PLAYBOOK_INDEX:
        refresh_index()

    def has(pb_name: str) -> bool:
        return pb_name.lower() in _PLAYBOOK_INDEX

    if not sample_text and not filename:
        # prefer TECH
        default_id = "TECH" if has("TECH") else (next(iter(_PLAYBOOK_INDEX)).upper() if _PLAYBOOK_INDEX else "TECH")
        return (default_id, "default")

    txt = (sample_text or "").lower()
    fn_lower = (filename or "").lower()

    # Playbook selection uses semantic content_type only (medical, regulatory, tech, etc.).
    # Extraction type (digital_pdf | scanned_pdf | mixed) is determined in preprocess and stored
    # as product.extraction_type; it does not drive playbook selection. SCANNED playbook may
    # still be applied internally for preprocessing when extraction_type is scanned_pdf/mixed.

    # Check for medical/healthcare indicators FIRST (before financial, as medical papers may contain financial terms)
    medical_keywords = (
        "diabetes", "diabetic", "medical", "medicine", "clinical", "patient", "patients", "treatment", "therapy",
        "diagnosis", "disease", "diseases", "symptom", "symptoms", "health", "healthcare", "hospital", "physician",
        "doctor", "medication", "drug", "drugs", "pharmaceutical", "pharma", "trial", "trials", "study", "studies",
        "research", "researchers", "type 1", "type 2", "insulin", "glucose", "blood sugar", "hba1c", "metabolic",
        "pathology", "pathological", "epidemiology", "epidemiological", "prevalence", "incidence", "mortality",
        "morbidity", "comorbidity", "comorbidities", "syndrome", "disorder", "condition", "conditions"
    )
    medical_matches = [k for k in medical_keywords if k in txt or k in fn_lower]
    # Check if medical keywords appear with high frequency (more than just incidental mentions)
    medical_keyword_count = sum(txt.count(k) + fn_lower.count(k) for k in medical_keywords)
    # Also check for medical-specific patterns
    has_medical_patterns = any(
        pattern in txt for pattern in [
            "type 1 diabetes", "type 2 diabetes", "type i diabetes", "type ii diabetes",
            "clinical trial", "randomized controlled", "case study", "cohort study",
            "patient population", "treatment group", "control group", "placebo"
        ]
    )
    
    if (medical_matches and medical_keyword_count >= 2) or has_medical_patterns:
        # Prefer MEDICAL playbook for WHO/clinical/guidelines, then ACADEMIC, then TECH
        if has("MEDICAL"):
            return ("MEDICAL", "medical_keywords")
        if has("ACADEMIC"):
            return ("ACADEMIC", "medical_research_keywords")
        if has("TECH"):
            return ("TECH", "medical_research_keywords")

    # Check for banking/finance indicators (after medical, as medical docs may have financial terms)
    # Use more specific financial terms to avoid false positives from medical papers
    banking_keywords = (
        "banking", "financial", "finance", "bank", "liquidity", "solvency", 
        "credit risk", "market risk", "balance sheet", "income statement", "interest rate",
        "basel", "crd", "crr", "eba", "ecb", "ssm", "supervision", "auditor", "supervisor",
        "capital adequacy", "regulatory capital", "tier 1", "tier 2", "risk-weighted assets"
    )
    banking_matches = [k for k in banking_keywords if k in txt or k in fn_lower]
    # Require multiple banking keywords or specific financial patterns to avoid false positives
    banking_keyword_count = sum(txt.count(k) + fn_lower.count(k) for k in banking_keywords)
    has_financial_patterns = any(
        pattern in txt for pattern in [
            "balance sheet", "income statement", "cash flow", "financial statement",
            "regulatory capital", "capital adequacy", "risk-weighted"
        ]
    )
    
    if (banking_matches and (banking_keyword_count >= 3 or has_financial_patterns)) and has("FINANCIAL"):
        return ("FINANCIAL", "banking_finance_keywords")
    
    # Check for regulatory indicators
    regulatory_keywords = (
        "label", "regulatory", "prescribing information", "safety", "fda", "ema",
        "compliance", "regulation", "guidelines", "directive", "framework", "requirement"
    )
    regulatory_matches = [k for k in regulatory_keywords if k in txt or k in fn_lower]
    if regulatory_matches and has("REGULATORY"):
        return ("REGULATORY", "regulatory_keywords")

    # Default to TECH
    default_id = "TECH" if has("TECH") else (next(iter(_PLAYBOOK_INDEX)).upper() if _PLAYBOOK_INDEX else "TECH")
    return (default_id, "default")
