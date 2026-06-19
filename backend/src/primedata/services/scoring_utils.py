"""
Primary scoring utilities (optional).

This module provides advanced scoring using external libraries.
If these libraries are not available, the fallback scorer in trust_scoring.py will be used.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import textstat

    HAS_TEXTSTAT = True
except ImportError:
    HAS_TEXTSTAT = False

try:
    import tiktoken

    TOK = tiktoken.get_encoding("cl100k_base")
    HAS_TIKTOKEN = True
except ImportError:
    HAS_TIKTOKEN = False


def estimate_tokens(text: str) -> int:
    """
    Estimate token count for text using tiktoken if available, otherwise fallback to word_count * 1.3.
    
    This is the canonical token estimation function used across all chunk paths.
    
    Args:
        text: Input text to estimate tokens for
        
    Returns:
        Estimated token count (integer)
    """
    if not text:
        return 0
    
    if HAS_TIKTOKEN:
        try:
            return len(TOK.encode(text))
        except Exception:
            # Fallback if tiktoken fails
            pass
    
    # Fallback: word_count * 1.3 (approximation)
    word_count = len(text.split())
    return int(word_count * 1.3)

try:
    from spellchecker import SpellChecker

    spell = SpellChecker()
    HAS_SPELLCHECKER = True
except ImportError:
    HAS_SPELLCHECKER = False

# PII Detection patterns
PII_PATTERNS = [
    r"\b\d{3}[-.\s]?\d{2}[-.\s]?\d{4}\b",
    r"\b(?:\+?\d{1,3})?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}",
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
]


def detect_pii(text: str) -> bool:
    """Detect PII in text."""
    return any(re.search(p, text) for p in PII_PATTERNS)


def score_completeness(tokens) -> float:
    """
    Score extraction completeness based on token count threshold.
    
    Note: This measures extraction completeness (whether enough content was extracted),
    NOT completeness of truth or factual completeness.
    
    Returns:
        Score in [0,1] range where 1.0 = best
    """
    return 1.0 if len(tokens) > 1000 else 0.75


def score_text_integrity(words) -> float:
    """
    Score text integrity (OCR/text cleanliness) using spell checker.
    
    Measures text cleanliness (spelling errors, OCR artifacts, character encoding issues).
    NOT factual accuracy or correctness of content.
    
    Returns:
        Score in [0,1] range where 1.0 = best (clean text)
    """
    if not HAS_SPELLCHECKER:
        return 0.85  # Default if spellchecker unavailable (normalized to [0,1])
    errors = len(spell.unknown(words[:500]))
    ratio = 1.0 - (errors / max(len(words), 1))
    return max(0.0, min(ratio, 1.0))  # Normalized to [0,1]


def score_secure(text: str) -> float:
    """
    Score security (PII detection).
    
    Returns:
        Score in [0,1] range where 1.0 = no PII detected (secure)
    """
    return 0.0 if detect_pii(text) else 1.0


def score_quality(text: str) -> float:
    """
    Score quality using readability metrics and heuristics.
    
    Returns:
        Score in [0,1] range where 1.0 = best quality
    """
    if HAS_TEXTSTAT:
        # Use textstat if available
        try:
            flesch = textstat.flesch_reading_ease(text)
            # Normalize Flesch score (0-100 scale) to [0,1]
            # Flesch scores: 0-30 (very difficult), 30-50 (difficult), 50-60 (fairly difficult),
            # 60-70 (standard), 70-80 (fairly easy), 80-90 (easy), 90-100 (very easy)
            # We want to reward readable text (60-100), but not penalize technical content too much
            if flesch < 0:
                return 0.50  # Even difficult text has some quality
            elif flesch < 30:
                return 0.55
            elif flesch < 50:
                return 0.65
            elif flesch < 60:
                return 0.75
            elif flesch < 70:
                return 0.82
            elif flesch < 80:
                return 0.88
            else:
                return 0.92
        except Exception:
            # If textstat fails, fall through to heuristics
            pass

    # Fallback: Use heuristics based on sentence length and vocabulary
    if not text or len(text.strip()) < 50:
        return 0.40

    words = text.split()
    if len(words) < 20:
        return 0.55  # Short text still has some quality

    # Calculate average sentence length (heuristic for readability)
    sentences = re.split(r"[.!?]+", text)
    sentences = [s.strip() for s in sentences if s.strip()]
    if not sentences:
        return 0.60  # Default for unparseable text

    avg_sentence_len = len(words) / len(sentences)

    # For regulatory/formal content, longer sentences are acceptable
    # Ideal sentence length for readability: 15-25 words
    # But regulatory content often has 25-40 word sentences which are still acceptable
    if avg_sentence_len < 5:
        return 0.60  # Very short sentences might be fragments
    elif avg_sentence_len < 10:
        return 0.70  # Short but acceptable
    elif avg_sentence_len <= 25:
        return 0.85  # Ideal range
    elif avg_sentence_len <= 35:
        return 0.80  # Still good for formal content
    elif avg_sentence_len <= 45:
        return 0.70  # Acceptable for regulatory content
    elif avg_sentence_len <= 60:
        return 0.60  # Long but readable for formal content
    else:
        return 0.50  # Very long sentences, harder to read


def score_timeliness(timestamp: str, ref: Optional[str] = None, sla_hours: Optional[float] = None) -> Tuple[float, str]:
    """
    Score timeliness based on age vs SLA threshold.
    
    Args:
        timestamp: Timestamp string (ISO format or YYYY-MM-DD)
        ref: Optional reference date (defaults to now())
        sla_hours: Optional SLA threshold in hours (defaults to 365*24 = 8760 hours)
        
    Returns:
        Tuple of (score in [0,1], reason string) where 1.0 = freshest
    """
    try:
        # Parse timestamp (support multiple formats)
        timestamp_dt = None
        for fmt in ["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S"]:
            try:
                timestamp_dt = datetime.strptime(timestamp.split('T')[0], "%Y-%m-%d")
                break
            except (ValueError, AttributeError):
                continue
        
        if timestamp_dt is None:
            return (0.5, "timestamp_missing_or_invalid")
        
        # Use current date as reference (pipeline run date)
        if ref:
            try:
                ref_dt = datetime.strptime(ref.split('T')[0], "%Y-%m-%d")
            except (ValueError, AttributeError):
                ref_dt = datetime.utcnow()
        else:
            ref_dt = datetime.utcnow()
        
        # Calculate age in hours
        age_hours = (ref_dt - timestamp_dt).total_seconds() / 3600.0
        
        # Default SLA: 365 days = 8760 hours
        if sla_hours is None:
            sla_hours = 365.0 * 24.0
        
        # Score: newer content = higher score
        # 0 hours old = 1.0, sla_hours old = 0.0, older = 0.0
        if age_hours < 0:
            # Future dates get neutral score
            return (0.5, "timestamp_in_future")
        
        # Clamp score: 1 - (age_hours / sla_hours), clamped to [0,1]
        score = max(0.0, min(1.0 - (age_hours / sla_hours), 1.0))
        return (score, "computed")
    except Exception as e:
        return (0.5, f"timestamp_parse_error: {str(e)}")


def score_gpt_confidence(text: str) -> float:
    """
    Placeholder for GPT confidence.
    
    Returns:
        Score in [0,1] range (placeholder, currently returns 0.85)
    """
    return 0.85


def score_parse_success(text: str, min_chars: int = 50) -> float:
    """
    Score parse success: 1.0 if chunk text exists and > min_chars, else 0.0.
    
    Args:
        text: Chunk text content
        min_chars: Minimum character threshold (default 50)
        
    Returns:
        Score in [0,1] range where 1.0 = successful parse
    """
    if not text or len(text.strip()) < min_chars:
        return 0.0
    return 1.0


def score_chunk_size_health(tokens: list, domain_type: Optional[str] = None, target_window: Optional[int] = None, tolerance: Optional[int] = None) -> float:
    """
    Score chunk token length distribution vs target range.
    
    Domain-aware:
    - Regulatory/legal: ideal 500-900 tokens, preferred 600-800
    - General: ideal 600-1200 tokens, preferred 800-1100
    
    Args:
        tokens: List of tokens (or token count if int)
        domain_type: Optional domain type for threshold adjustment
        target_window: Optional target token count (overrides domain defaults)
        tolerance: Optional tolerance around target (overrides domain defaults)
        
    Returns:
        Score in [0,1] range where 1.0 = ideal chunk size
    """
    # Handle both list and int
    if isinstance(tokens, int):
        token_count = tokens
    else:
        token_count = len(tokens)
    
    # Use provided target/tolerance or domain-specific defaults
    if target_window is not None and tolerance is not None:
        min_ideal = target_window - tolerance
        max_ideal = target_window + tolerance
        min_preferred = target_window - (tolerance // 2)
        max_preferred = target_window + (tolerance // 2)
    else:
        # Domain-specific target ranges
        domain_type_lower = (domain_type or "").lower()
        if domain_type_lower in ["regulatory", "reg", "legal", "finance_banking"]:
            # Regulatory/legal content: smaller ideal range
            min_ideal = 500
            max_ideal = 900
            min_preferred = 600
            max_preferred = 800
        else:
            # General content: standard range
            min_ideal = 600
            max_ideal = 1200
            min_preferred = 800
            max_preferred = 1100
    
    # Score based on distance from preferred range
    if min_preferred <= token_count <= max_preferred:
        # In preferred range: 1.0 score
        return 1.0
    elif min_ideal <= token_count < min_preferred:
        # Below preferred but in ideal: linear decay
        ratio = (token_count - min_ideal) / (min_preferred - min_ideal)
        return 0.7 + (ratio * 0.3)  # 0.7-1.0
    elif max_preferred < token_count <= max_ideal:
        # Above preferred but in ideal: linear decay
        ratio = (max_ideal - token_count) / (max_ideal - max_preferred)
        return 0.7 + (ratio * 0.3)  # 0.7-1.0
    elif token_count < min_ideal:
        # Below ideal: exponential decay
        ratio = token_count / min_ideal
        return max(0.0, ratio * 0.7)  # 0-0.7
    else:
        # Above ideal: exponential decay
        excess = token_count - max_ideal
        penalty = min(1.0, excess / max_ideal)  # Penalty increases with excess
        return max(0.0, 0.7 * (1.0 - penalty))  # 0-0.7


def score_context_quality(text: str) -> float:
    """
    Score context quality based on text structure and information richness.
    
    Returns:
        Score in [0,1] range where 1.0 = best context quality
    """
    if not text or len(text.strip()) < 50:
        return 0.30

    # Base score for having meaningful content
    score = 0.40  # Start with a baseline - meaningful text has context
    text_lower = text.lower()
    words = text.split()

    # 1. Structure indicators (paragraphs, headings, lists) - higher weight
    has_paragraphs = "\n\n" in text or text.count("\n") > 3
    has_lists = bool(re.search(r"(?:^|\n)[\s]*[•\-\*\+]\s", text, re.MULTILINE))
    has_numbered_lists = bool(re.search(r"(?:^|\n)[\s]*\d+[\.\)]\s", text, re.MULTILINE))
    if has_paragraphs:
        score += 0.20  # Structured text has better context
    if has_lists or has_numbered_lists:
        score += 0.15

    # 2. Information density (numbers, dates, references) - important for context
    has_numbers = bool(re.search(r"\b\d+(?:[.,]\d+)?(?:%|\$|USD|EUR|million|billion)?\b", text))
    has_dates = bool(
        re.search(
            r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4}\b|\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|\b\d{4}\b",
            text_lower,
        )
    )
    has_references = bool(re.search(r"\b(?:see|refer|reference|section|chapter|page|table|figure)\s+[\d]+", text_lower))
    if has_numbers:
        score += 0.15
    if has_dates:
        score += 0.10
    if has_references:
        score += 0.10

    # 3. Contextual keywords (domain-agnostic) - shows coherent writing
    contextual_indicators = [
        "because",
        "therefore",
        "however",
        "although",
        "in addition",
        "furthermore",
        "specifically",
        "for example",
        "such as",
        "including",
        "namely",
        "in particular",
        "according to",
        "based on",
        "related to",
        "associated with",
        "compared to",
        "as a result",
        "consequently",
        "meanwhile",
        "furthermore",
        "moreover",
    ]
    context_hits = sum(1 for indicator in contextual_indicators if indicator in text_lower)
    score += min(context_hits * 0.02, 0.15)  # Max 0.15 points for contextual language

    # 4. Entity mentions (proper nouns, organizations, concepts) - shows real-world context
    has_proper_nouns = bool(re.search(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b", text))
    if has_proper_nouns:
        score += 0.10

    # 5. Length bonus - longer text typically has more context (up to a point)
    if len(words) > 100:
        score += min((len(words) - 100) / 2000.0, 0.10)  # Up to 0.10 points for longer content

    return min(score, 1.0)


def score_metadata_completeness(meta: Dict[str, Any], required_fields: Optional[List[str]] = None) -> float:
    """
    Score metadata completeness (required metadata fields populated).
    
    Args:
        meta: Metadata dictionary
        required_fields: Optional list of required field names (defaults to standard set)
        
    Returns:
        Score in [0,1] range where 1.0 = all required fields present
    """
    if required_fields is None:
        required_fields = ["source", "section", "audience", "timestamp"]
    
    if not required_fields:
        return 1.0  # No requirements = perfect score
    
    present = sum(1 for k in required_fields if k in meta and meta[k])
    return present / len(required_fields)


def score_metadata_presence(meta: Dict[str, Any]) -> float:
    """
    Score metadata presence and quality (legacy function, kept for backward compatibility).
    
    Returns:
        Score in [0,1] range where 1.0 = best metadata quality
    """
    required = ["source", "section", "audience", "timestamp"]
    present = sum(1 for k in required if k in meta and meta[k])

    base_score = present / len(required)

    # Bonus for quality metadata (non-empty, meaningful values)
    quality_bonus = 0.0

    # Section quality
    section = str(meta.get("section", "")).strip().lower()
    if section and section not in ("", "general", "unknown", "none"):
        quality_bonus += 0.10

    # Field name quality
    field_name = str(meta.get("field_name", "")).strip().lower()
    if field_name and field_name not in ("", "general", "unknown", "none"):
        quality_bonus += 0.10

    # Audience quality (not "unknown")
    audience = str(meta.get("audience", "")).strip().lower()
    if audience and audience not in ("", "unknown", "general"):
        quality_bonus += 0.10

    # Document ID presence
    if meta.get("document_id") or meta.get("doc_scope"):
        quality_bonus += 0.10

    return min(base_score + quality_bonus, 1.0)


def score_audience_intentionality(text: str, domain_type: Optional[str] = None) -> float:
    """
    Score audience intentionality based on audience signals in text.
    
    Args:
        text: Text content to analyze
        domain_type: Optional domain type (e.g., "regulatory", "finance_banking") for domain-specific scoring
        
    Returns:
        Score in [0,1] range indicating how well content targets its audience
    """
    if not text or len(text.strip()) < 20:
        return 0.0

    text_lower = text.lower()
    score = 0.0
    domain_matched = False
    
    # Domain-specific lexicons (priority when domain_type matches)
    if domain_type:
        domain_type_lower = domain_type.lower()
        
        # Regulatory domain
        if domain_type_lower in ["regulatory", "reg"]:
            regulatory_terms = [
                "supervisor", "auditor", "regulator", "supervision", "regulatory",
                "compliance officer", "risk manager", "internal audit",
                "regulatory authority", "supervisory authority", "audit committee",
                "compliance framework", "regulatory requirement", "supervisory review",
                "regulatory reporting", "audit trail", "regulatory compliance",
                "compliance", "supervisory", "audit"
            ]
            regulatory_hits = sum(1 for term in regulatory_terms if re.search(r"\b" + re.escape(term) + r"\b", text_lower))
            if regulatory_hits > 0:
                score += min(regulatory_hits * 0.20, 0.60)
                domain_matched = True
        
        # Finance/Banking domain
        elif domain_type_lower in ["finance_banking", "finance", "banking"]:
            finance_terms = [
                "bank", "banking", "financial institution", "lender", "borrower",
                "credit risk", "market risk", "liquidity risk", "operational risk",
                "capital adequacy", "solvency", "balance sheet", "income statement",
                "financial statement", "audit", "auditor", "compliance officer",
                "risk manager", "treasurer", "cfo", "financial analyst", "investor",
                "shareholder", "stakeholder", "regulatory reporting", "financial"
            ]
            finance_hits = sum(1 for term in finance_terms if re.search(r"\b" + re.escape(term) + r"\b", text_lower))
            if finance_hits > 0:
                score += min(finance_hits * 0.18, 0.60)
                domain_matched = True

    # Generic lexicons (reduced weight when domain matched to prevent saturation)
    generic_multiplier = 0.5 if domain_matched else 1.0  # Reduce generic boosts when domain matched
    
    # Healthcare audience signals
    healthcare_terms = [
        "hcp",
        "physician",
        "patient",
        "doctor",
        "nurse",
        "clinician",
        "prescriber",
        "caregiver",
        "healthcare",
    ]
    healthcare_hits = sum(1 for term in healthcare_terms if re.search(r"\b" + re.escape(term) + r"\b", text_lower))
    if healthcare_hits > 0:
        score += min(healthcare_hits * 0.25 * generic_multiplier, 0.50 * generic_multiplier)

    # Business/Executive audience signals
    business_terms = [
        "executive",
        "management",
        "stakeholder",
        "board",
        "investor",
        "shareholder",
        "revenue",
        "profit",
        "quarterly",
        "annual",
    ]
    business_hits = sum(1 for term in business_terms if re.search(r"\b" + re.escape(term) + r"\b", text_lower))
    if business_hits > 0:
        score += min(business_hits * 0.15 * generic_multiplier, 0.50 * generic_multiplier)

    # Technical/Developer audience signals
    tech_terms = [
        "developer",
        "engineer",
        "api",
        "sdk",
        "cli",
        "code",
        "implementation",
        "integration",
        "deployment",
        "architecture",
        "technical",
    ]
    tech_hits = sum(1 for term in tech_terms if re.search(r"\b" + re.escape(term) + r"\b", text_lower))
    if tech_hits > 0:
        score += min(tech_hits * 0.15 * generic_multiplier, 0.50 * generic_multiplier)

    # Operations audience signals
    ops_terms = [
        "operations",
        "monitoring",
        "maintenance",
        "support",
        "service",
        "infrastructure",
        "scalability",
        "performance",
    ]
    ops_hits = sum(1 for term in ops_terms if re.search(r"\b" + re.escape(term) + r"\b", text_lower))
    if ops_hits > 0:
        score += min(ops_hits * 0.15 * generic_multiplier, 0.50 * generic_multiplier)

    # Legal domain signals
    legal_terms = [
        "attorney", "lawyer", "counsel", "legal counsel", "compliance",
        "legal requirement", "legal framework", "jurisdiction", "litigation",
        "contract", "agreement", "legal entity", "legal obligation"
    ]
    legal_hits = sum(1 for term in legal_terms if re.search(r"\b" + re.escape(term) + r"\b", text_lower))
    if legal_hits > 0:
        score += min(legal_hits * 0.20 * generic_multiplier, 0.50 * generic_multiplier)

    # General audience signals (you, your, users, customers) - always apply
    general_signals = bool(re.search(r"\b(?:you|your|users?|customers?|readers?|audience)\b", text_lower))
    if general_signals:
        score += 0.30

    # Direct audience addressing (for, intended for, designed for) - always apply
    direct_addressing = bool(re.search(r"\b(?:for|intended\s+for|designed\s+for|targeted\s+to)\s+(?:the\s+)?\w+", text_lower))
    if direct_addressing:
        score += 0.20

    return min(score, 1.0)


def score_diversity(text: str) -> float:
    """
    Score diversity using Type-Token Ratio (TTR).
    
    TTR measures vocabulary diversity: unique words / total words.
    Higher TTR = more diverse vocabulary = better score.
    
    Returns:
        Score in [0,1] range where 1.0 = most diverse vocabulary
    """
    if not text or len(text.strip()) < 20:
        return 0.0
    
    # Extract words (lowercase, alphanumeric)
    words = re.findall(r'\b[a-z0-9]+\b', text.lower())
    if not words:
        return 0.0
    
    # Calculate Type-Token Ratio
    unique_words = len(set(words))
    total_words = len(words)
    ttr = unique_words / total_words if total_words > 0 else 0.0
    
    # Normalize TTR to [0,1] scale
    # TTR typically ranges from 0.3-0.7 for most text
    # We'll scale it: 0.3 TTR = 0.5 score, 0.7 TTR = 1.0 score
    if ttr < 0.3:
        score = (ttr / 0.3) * 0.5
    elif ttr <= 0.7:
        score = 0.5 + ((ttr - 0.3) / 0.4) * 0.5
    else:
        score = 1.0
    
    return min(1.0, max(0.0, score))


def score_audience_accessibility(meta: Dict[str, Any]) -> float:
    """
    Score audience accessibility based on detected audience and text readability.
    
    Returns:
        Score in [0,1] range where 1.0 = most accessible
    """
    audience = str(meta.get("audience", "")).strip().lower()
    text = meta.get("text", "")

    # If audience is explicitly set and not "unknown", give base score
    if audience and audience not in ("", "unknown", "general"):
        base_score = 0.70

        # Reward specific, well-defined audiences
        well_defined_audiences = ["hcp", "executive", "regulatory", "patient", "finance", "ops", "dev"]
        if audience in well_defined_audiences:
            base_score = 0.85

        # Adjust based on text readability (shorter, clearer sentences = more accessible)
        if text:
            words = text.split()
            sentences = re.split(r"[.!?]+", text)
            sentences = [s.strip() for s in sentences if s.strip()]
            if sentences:
                avg_sentence_len = len(words) / len(sentences)
                # Ideal: 10-20 words per sentence for accessibility
                if 10 <= avg_sentence_len <= 20:
                    readability_bonus = 0.15
                elif 8 <= avg_sentence_len <= 25:
                    readability_bonus = 0.10
                elif 5 <= avg_sentence_len <= 30:
                    readability_bonus = 0.05
                else:
                    readability_bonus = 0.0
                return min(base_score + readability_bonus, 1.0)

        return base_score

    # If no audience detected, check text for accessibility indicators
    if text:
        text_lower = text.lower()
        # Check for simple language indicators
        has_simple_language = bool(re.search(r"\b(simple|easy|clear|straightforward|basic)\b", text_lower))
        has_examples = bool(re.search(r"\b(?:example|for instance|such as|including)\b", text_lower))

        if has_simple_language or has_examples:
            return 0.50

    return 0.30  # Default lower score if no audience signals found


def score_kb_ready(text: str) -> float:
    """
    Score knowledge base readiness.
    
    Returns:
        Score in [0,1] range where 1.0 = ready for knowledge base
    """
    return 1.0 if len(text.split()) > 50 and "\n" in text else 0.50


def _score_completeness_with_playbook(
    record: Dict[str, Any],
    tokens: list,
    playbook: Optional[Dict[str, Any]] = None
) -> float:
    """
    Score completeness: playbook-driven if playbook present, else generic.
    
    Args:
        record: Chunk record with sections/fields
        tokens: Token list for generic completeness
        playbook: Optional playbook with required_sections/required_fields
        
    Returns:
        Score in [0,1] range
    """
    if playbook and (playbook.get("required_sections") or playbook.get("required_fields")):
        # Playbook-driven completeness
        required_sections = playbook.get("required_sections", [])
        required_fields = playbook.get("required_fields", [])
        
        # Extract sections from record
        sections = record.get("sections", [])
        if isinstance(sections, str):
            sections = [sections] if sections else []
        elif not isinstance(sections, list):
            sections = []
        
        # Extract fields from record
        fields = record.get("fields", {})
        if not isinstance(fields, dict):
            fields = {}
        
        # Count present sections
        section_ids = [s.get("id") if isinstance(s, dict) else str(s).lower() for s in sections]
        required_section_ids = [s.get("id") if isinstance(s, dict) else str(s).lower() for s in required_sections]
        present_sections = sum(1 for req_id in required_section_ids if req_id in section_ids)
        section_score = present_sections / len(required_section_ids) if required_section_ids else 1.0
        
        # Count present fields
        present_fields = sum(1 for req_field in required_fields 
                           if req_field.get("id") in fields and fields[req_field.get("id")])
        field_score = present_fields / len(required_fields) if required_fields else 1.0
        
        # Combine: 0.6*sections + 0.4*fields (configurable)
        section_weight = playbook.get("completeness_weights", {}).get("sections", 0.6)
        field_weight = playbook.get("completeness_weights", {}).get("fields", 0.4)
        total_weight = section_weight + field_weight
        if total_weight > 0:
            section_weight /= total_weight
            field_weight /= total_weight
        
        return section_weight * section_score + field_weight * field_score
    else:
        # Generic completeness (extraction completeness)
        return score_completeness(tokens)


def _score_validity_with_playbook(
    record: Dict[str, Any],
    playbook: Optional[Dict[str, Any]] = None
) -> float:
    """
    Score validity: playbook rule pass rate if playbook present, else 1.0.
    
    Args:
        record: Chunk record
        playbook: Optional playbook with validity_rules
        
    Returns:
        Score in [0,1] range
    """
    if playbook and playbook.get("validity_rules"):
        validity_rules = playbook.get("validity_rules", [])
        if not validity_rules:
            return 1.0
        
        # Evaluate validity rules (simplified - actual implementation would use rule engine)
        passed_checks = 0
        total_checks = len(validity_rules)
        
        for rule in validity_rules:
            # Simple pattern matching for now (can be extended with full rule engine)
            rule_type = rule.get("type", "")
            if rule_type == "pattern_match":
                pattern = rule.get("pattern", "")
                field = rule.get("field", "")
                value = str(record.get(field, ""))
                if pattern and re.search(pattern, value, flags=re.IGNORECASE):
                    passed_checks += 1
            elif rule_type == "required":
                field = rule.get("field", "")
                if field in record and record[field]:
                    passed_checks += 1
            else:
                # Unknown rule type, count as passed for now
                passed_checks += 1
        
        return passed_checks / total_checks if total_checks > 0 else 1.0
    else:
        # No playbook = no validity requirements = perfect score
        return 1.0


def _score_consistency_with_playbook(
    record: Dict[str, Any],
    playbook: Optional[Dict[str, Any]] = None
) -> float:
    """
    Score consistency: playbook consistency rule pass rate if playbook present, else 1.0.
    
    Args:
        record: Chunk record
        playbook: Optional playbook with consistency_rules
        
    Returns:
        Score in [0,1] range (severity-weighted if weights provided)
    """
    if playbook and playbook.get("consistency_rules"):
        consistency_rules = playbook.get("consistency_rules", [])
        if not consistency_rules:
            return 1.0
        
        # Evaluate consistency rules
        total_weight = 0.0
        weighted_passed = 0.0
        
        for rule in consistency_rules:
            severity = rule.get("severity", "medium")
            # Map severity to weight: critical=1.0, high=0.8, medium=0.5, low=0.2
            severity_weights = {"critical": 1.0, "high": 0.8, "medium": 0.5, "low": 0.2}
            weight = severity_weights.get(severity.lower(), 0.5)
            
            # Simple rule evaluation (can be extended)
            rule_type = rule.get("type", "")
            passed = False
            
            if rule_type == "value_match":
                field = rule.get("field", "")
                expected = rule.get("expected", "")
                actual = str(record.get(field, ""))
                if actual == expected:
                    passed = True
            elif rule_type == "range_check":
                field = rule.get("field", "")
                min_val = rule.get("min")
                max_val = rule.get("max")
                value = record.get(field)
                if value is not None:
                    try:
                        num_val = float(value)
                        if (min_val is None or num_val >= min_val) and (max_val is None or num_val <= max_val):
                            passed = True
                    except (ValueError, TypeError):
                        pass
            else:
                # Unknown rule type, count as passed
                passed = True
            
            total_weight += weight
            if passed:
                weighted_passed += weight
        
        return weighted_passed / total_weight if total_weight > 0 else 1.0
    else:
        # No playbook = no consistency requirements = perfect score
        return 1.0


def _score_provenance_coverage(meta: Dict[str, Any]) -> float:
    """
    Score provenance coverage: weighted checklist of provenance fields.
    
    Checks for: source checksum, pipeline run id, model/version ids, timestamps.
    
    Returns:
        Score in [0,1] range where 1.0 = complete provenance
    """
    provenance_fields = {
        "source_checksum": 0.25,
        "pipeline_run_id": 0.20,
        "model_id": 0.15,
        "model_version": 0.15,
        "timestamp": 0.15,
        "extraction_timestamp": 0.10,
    }
    
    total_weight = sum(provenance_fields.values())
    weighted_present = 0.0
    
    for field, weight in provenance_fields.items():
        if field in meta and meta[field]:
            weighted_present += weight
        # Also check common aliases
        elif field == "source_checksum" and (meta.get("checksum") or meta.get("file_hash")):
            weighted_present += weight
        elif field == "pipeline_run_id" and meta.get("pipeline_run"):
            weighted_present += weight
        elif field == "timestamp" and meta.get("created_at"):
            weighted_present += weight
    
    return weighted_present / total_weight if total_weight > 0 else 1.0


def load_weights(path: str) -> Dict[str, float]:
    """Load scoring weights from JSON file."""
    with open(path) as f:
        return json.load(f)


def score_file_data(data: Dict[str, Any], weights: Dict[str, float]) -> Dict[str, Any]:
    """
    Score a file data record using primary scoring methods.

    Args:
        data: Record with text and metadata
        weights: Scoring weights dictionary (should sum to 100)

    Returns:
        Dictionary with all metrics + AI_Trust_Score (all values 0-100)
    """
    import logging
    logger = logging.getLogger(__name__)
    
    text = data.get("text", "")
    meta = data.copy()

    # Use shared estimate_tokens helper for consistent token estimation
    token_est = data.get("token_est")
    if token_est is None:
        token_est = estimate_tokens(text)
    
    # For scoring, we need token list for some functions
    if HAS_TIKTOKEN:
        try:
            tokens = TOK.encode(text)
        except Exception:
            tokens = text.split()  # Fallback
    else:
        tokens = text.split()  # Fallback

    words = text.split()

    # Prepare meta with text for audience accessibility scoring
    meta_with_text = dict(meta)
    meta_with_text["text"] = text

    # Extract domain_type from record (check both flat and nested locations)
    domain_type = data.get("domain_type") or data.get("metadata", {}).get("domain_type")
    
    # Get playbook for playbook-driven metrics (if available)
    playbook = data.get("playbook") or {}
    playbook_id = data.get("playbook_id") or meta.get("playbook_id")
    
    # Score timeliness (returns tuple: score in [0,1], reason)
    # Get SLA from playbook if available
    sla_hours = None
    if playbook_id and playbook:
        sla_hours = playbook.get("freshness_sla_hours")
    timeliness_score, timeliness_reason = score_timeliness(meta.get("timestamp", ""), sla_hours=sla_hours)
    
    # Calculate chunk size health (domain-aware) - use token_est (int) not token list
    chunk_size_health = score_chunk_size_health(int(token_est), domain_type=domain_type)
    
    # Completeness: playbook-driven if playbook_id present, else generic
    completeness_score = _score_completeness_with_playbook(
        record=data,
        tokens=tokens,
        playbook=playbook if playbook_id else None
    )
    
    # Validity: playbook-driven if playbook_id present
    validity_score = _score_validity_with_playbook(
        record=data,
        playbook=playbook if playbook_id else None
    )
    
    # Consistency: playbook-driven if playbook_id present
    consistency_score = _score_consistency_with_playbook(
        record=data,
        playbook=playbook if playbook_id else None
    )
    
    # Uniqueness: exact + near-dup (computed at aggregate level, placeholder here)
    uniqueness_score = 1.0  # Will be computed at aggregate level
    
    # Provenance coverage
    provenance_score = _score_provenance_coverage(meta)
    
    # Text Integrity: use OCR cleanup metrics when present (repetition_ratio, ocr_noise_score), else spell-check
    repetition_ratio = data.get("repetition_ratio")
    ocr_noise_score = data.get("ocr_noise_score")
    if repetition_ratio is not None and ocr_noise_score is not None:
        # Cleanup-based: high repetition lowers score; ocr_noise_score is 0-1 (1=clean)
        integrity_from_cleanup = max(0.0, min(1.0, ocr_noise_score * (1.0 - 0.5 * float(repetition_ratio))))
        integrity_from_spell = score_text_integrity(words)
        text_integrity_score = 0.6 * integrity_from_cleanup + 0.4 * integrity_from_spell
    else:
        text_integrity_score = score_text_integrity(words)
    
    # Canonical metrics (snake_case, all in [0,1] range for scores)
    scores = {
        "completeness": completeness_score,
        "validity": validity_score,
        "consistency": consistency_score,
        "uniqueness": uniqueness_score,  # Placeholder, computed at aggregate
        "timeliness": timeliness_score,
        "text_integrity": text_integrity_score,  # From OCR cleanup metrics + spell-check when available
        "parse_success": score_parse_success(text),
        "chunk_boundary_quality": 1.0,  # Computed at aggregate level
        "chunk_coherence": 1.0,  # Computed via AI-Ready metrics
        "chunk_size_health": round(chunk_size_health, 4),
        "metadata_completeness": score_metadata_completeness(meta),
        "provenance_coverage": provenance_score,
        # Raw token metrics (NOT clamped, NOT scores)
        "token_est": int(token_est),  # Raw token count for this chunk
    }
    
    # Legacy aliases (for backward compatibility, optional)
    # NOTE: Token_Count is NOT included - it's misleading (not an alias of chunk_size_health)
    legacy_aliases = {
        "Completeness": completeness_score,
        "Secure": score_secure(text),
        "Quality": score_quality(text),
        "Chunk_Size_Health": round(chunk_size_health, 4),
        "Parse_Success": score_parse_success(text),
        "GPT_Confidence": score_gpt_confidence(text),
        "Context_Quality": score_context_quality(text),
        "Metadata_Presence": score_metadata_presence(meta),
        "Audience_Intentionality": score_audience_intentionality(text, domain_type=domain_type),  # Weight 0.0, informational only
        "Diversity": score_diversity(text),
        "Audience_Accessibility": score_audience_accessibility(meta_with_text),
        "KnowledgeBase_Ready": score_kb_ready(text),
    }
    
    # Store legacy aliases separately (optional)
    scores["legacy_aliases"] = legacy_aliases
    
    # Store timeliness reason for semantics (non-numeric, won't affect aggregation)
    scores["_timeliness_reason"] = timeliness_reason

    # Penalty adjustments
    alpha = sum(c.isalpha() for c in text) / max(len(text), 1)
    if alpha < 0.5:
        scores["Quality"] *= 0.4
        scores["text_integrity"] *= 0.7

    # Ensure all SCORE metrics are in [0,1] range (but NOT raw token metrics)
    score_keys = ["completeness", "validity", "consistency", "uniqueness", "timeliness",
                  "text_integrity", "parse_success", "chunk_boundary_quality", "chunk_coherence",
                  "chunk_size_health", "metadata_completeness", "provenance_coverage"]
    for k in score_keys:
        if k in scores and isinstance(scores[k], (int, float)):
            scores[k] = max(0.0, min(1.0, float(scores[k])))
    
    # Clamp legacy aliases (they are scores)
    if "legacy_aliases" in scores:
        for k, v in scores["legacy_aliases"].items():
            if isinstance(v, (int, float)):
                scores["legacy_aliases"][k] = max(0.0, min(1.0, float(v)))

    # Weighted aggregate: weights should sum to 1.0
    # Use only weights that exist in scores, missing metrics default to 0 with warning
    total_weight = sum(weights.values())
    if abs(total_weight - 1.0) > 0.01:  # Allow small floating point differences
        logger.warning(f"Weights sum to {total_weight}, expected 1.0. Normalizing weights.")
        # Normalize weights to sum to 1.0
        weights_normalized = {k: (v / total_weight) for k, v in weights.items()}
        weights = weights_normalized
        total_weight = 1.0
    
    weighted_sum = 0.0
    missing_metrics = []
    for weight_key, weight_value in weights.items():
        if weight_key in scores:
            # Scores are already in [0,1], weights sum to 1.0
            weighted_sum += scores[weight_key] * weight_value
        else:
            missing_metrics.append(weight_key)
            # Missing metrics default to 0 (no contribution to trust score)
    
    # Log warning once per run for missing metrics
    if missing_metrics:
        logger.warning(f"Missing metrics in scores (defaulting to 0): {missing_metrics}")
    
    # Trust score is in [0,1] range
    scores["AI_Trust_Score"] = round(weighted_sum, 4)

    return scores
