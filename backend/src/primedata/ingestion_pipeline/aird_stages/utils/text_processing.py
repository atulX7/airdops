"""
Text processing utilities for AIRD preprocessing.

Ports text normalization, PII redaction, and section detection from AIRD.
"""

from typing import Any, Dict, List, Optional, Tuple

import regex as re
from loguru import logger

# Regex patterns for PII detection
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}\b", re.I)
PHONE_RE = re.compile(r"(?:\+?\d[\s\-\.)/]*)?(?:\(?\d{3}\)?[\s\-\./]*)?\d{3}[\s\-\./]*\d{4}")
SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")

# Header detection patterns
TITLECASE_RE = re.compile(r"^[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+$")
ALLCAPS_RE = re.compile(r"^[A-Z0-9][A-Z0-9 &'\-]{6,}$")
NUMBERED_RE = re.compile(r"^(\d+)[\.\)]\s+(.+)$")

# Sentence splitting regex
SENT_SPLIT_RE = re.compile(r"(?<!\b[A-Z])[.!?。۔؟]+(?=\s+[A-Z0-9\"'])")


def _compile_flags(flag_str: Optional[str]) -> int:
    """Compile regex flags from string (e.g., 'MULTILINE|IGNORECASE')."""
    if not flag_str:
        return 0
    flags = 0
    for f in flag_str.split("|"):
        f = f.strip().upper()
        if f == "MULTILINE":
            flags |= re.MULTILINE
        if f == "IGNORECASE":
            flags |= re.IGNORECASE
    return flags


def normalize_wrapped_lines(text: str) -> str:
    """
    Comprehensive PDF text normalization.
    
    Fixes common PDF line-wrap artifacts:
    - De-hyphenate: 'exam-\nple' -> 'example'
    - Join wrapped lines into sentences/paragraphs using heuristics
    - Remove excessive whitespace
    - Preserve paragraph boundaries (blank lines)
    
    This is critical for PDFs which often have hard line breaks that break
    paragraph detection and chunking.
    """
    if not text:
        return ""

    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # De-hyphenate: "exam-\nple" -> "example"
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)

    # Remove excessive whitespace (but preserve newlines for paragraph detection)
    text = re.sub(r"[ \t]+", " ", text)

    # Join lines that look like hard-wrapped sentences:
    # If a line doesn't end with sentence punctuation and next line starts lowercase -> join.
    lines = [ln.strip() for ln in text.split("\n")]
    out = []
    for ln in lines:
        if not ln:
            out.append("")  # keep blank lines (para breaks)
            continue

        if not out:
            out.append(ln)
            continue

        prev = out[-1]
        if prev == "":
            out.append(ln)
            continue

        # Check if previous line ends with sentence punctuation
        prev_ends_sentence = bool(re.search(r'[.!?]["\')\]]*\s*$', prev))
        # Check if current line starts with lowercase (likely continuation)
        next_starts_lower = bool(re.match(r"^[a-z]", ln))

        # Join typical wrap: previous doesn't end sentence AND next starts lowercase
        if (not prev_ends_sentence) and next_starts_lower:
            out[-1] = prev + " " + ln
        else:
            out.append(ln)

    # Re-collapse multiple blank lines to max 2 (paragraph boundaries)
    normalized = "\n".join(out)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)

    return normalized.strip()


def redact_pii(text: str) -> str:
    """Redact PII (emails, phones, SSNs) from text."""
    t = EMAIL_RE.sub("[redacted_email]", text)
    t = PHONE_RE.sub("[redacted_phone]", t)
    t = SSN_RE.sub("[SSN]", t)
    return t


def apply_normalizers(text: str, steps: Optional[List[Dict[str, Any]]]) -> str:
    """Apply regex-based normalization steps from playbook."""
    out = text
    for step in steps or []:
        pat = step.get("pattern")
        if not pat:
            logger.warning(f"Normalizer step missing 'pattern' field, skipping: {step}")
            continue

        # Handle YAML parsing issue: sometimes patterns are parsed as lists (e.g., [\u2018\u2019])
        # Convert list to string character class pattern
        if isinstance(pat, list):
            # Convert list of characters to regex character class string
            pat = "[" + "".join(str(c) for c in pat) + "]"
            logger.debug(f"Converted list pattern to string: {pat}")

        if not isinstance(pat, str):
            logger.warning(f"Normalizer pattern must be string or list, got {type(pat)}: {pat}, skipping")
            continue

        repl = step.get("replace", "")
        flag_val = step.get("flags")
        # Handle flags: can be string, None, or other types
        if isinstance(flag_val, str):
            flags = _compile_flags(flag_val)
        elif flag_val is None:
            flags = 0
        else:
            # If flags is not a string or None, log and use 0
            logger.warning(
                f"Unexpected flags type in normalizer (expected str or None, got {type(flag_val)}): {flag_val}, using 0"
            )
            flags = 0
        try:
            out = re.sub(pat, repl, out, flags=flags)
        except (re.error, TypeError) as e:
            logger.warning(
                f"Bad regex pattern in normalizer: {pat}, error: {e}, flags type: {type(flags)}, flags value: {flags}"
            )
            # ignore bad regex in config; continue
            pass
    return out


def split_pages_by_config(text: str, page_fences: Optional[List[Dict[str, Any]]]) -> List[Dict[str, int]]:
    """
    If a page fence pattern is defined, split text into {page, text} blocks.
    Otherwise produce a single page.
    """
    if not page_fences:
        return [{"page": 1, "text": text.strip()}]

    for fence in page_fences:
        flags = _compile_flags(fence.get("flags"))
        pattern = fence.get("pattern", r"^$")
        lines = text.splitlines()
        pages, curr, page = [], [], 1
        found_any_marker = False

        for line in lines:
            if re.match(pattern, line, flags=flags):
                found_any_marker = True
                if curr:
                    pages.append({"page": page, "text": "\n".join(curr).strip()})
                    curr = []
                # Try to extract page number from the marker line
                m = re.search(r"PAGE\s+(\d+)", line, flags=re.IGNORECASE)
                if m:
                    page = int(m.group(1))
                else:
                    # If no page number found, increment from last page
                    page = pages[-1]["page"] + 1 if pages else 1
                continue
            curr.append(line)

        # Add the last page if there's remaining content
        if curr:
            pages.append({"page": page, "text": "\n".join(curr).strip()})

        # If we found any markers and have multiple pages, return them
        # Also return if we have at least one page (even if only one marker was found)
        if found_any_marker and len(pages) > 0:
            return pages
        # If we found markers but only got one page, that's still valid (single-page document)
        if found_any_marker:
            return pages

    # No patterns matched, return single page
    return [{"page": 1, "text": text.strip()}]


def detect_sections_configured(
    text: str,
    header_specs: Optional[List[Dict[str, Any]]],
    aliases: Optional[Dict[str, str]],
) -> List[Tuple[str, str, str, float]]:
    """
    Use header rules from playbook to split into sections.
    Returns tuples: (title_raw, canonical_section, body_text, section_confidence)
    
    section_confidence: 0.0-1.0 indicating confidence that chunk text is within section boundaries
    - 1.0: Explicit header rule matched (high confidence)
    - 0.8: Heuristic pattern matched (numbered, TitleCase, ALLCAPS)
    - 0.5: Fallback section (no header detected, using default)
    - 0.0: Unknown/unreliable section boundary
    """
    lines = text.splitlines()
    sections, buf, title_raw = [], [], "Introduction"
    current_section_confidence = 0.5  # Track confidence of current section being built
    aliases = aliases or {}

    def flush(confidence: float = None, section_confidence: float = None, **kwargs):
        nonlocal buf, current_section_confidence
        if buf:
            # Use provided confidence (accept both 'confidence' and 'section_confidence' for compatibility)
            conf_to_use = confidence if confidence is not None else (section_confidence if section_confidence is not None else current_section_confidence)
            canon = aliases.get(title_raw, _canon_from_title(title_raw))
            sections.append((title_raw, canon, "\n".join(buf).strip(), conf_to_use))
            buf = []

    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        is_header = False
        new_section_confidence = 0.5  # Default confidence for new section
        
        # explicit header rules first (highest confidence)
        for spec in header_specs or []:
            pat = spec.get("pattern")
            flags = _compile_flags(spec.get("flags"))
            if pat and re.match(pat, line, flags=flags):
                flush()  # Flush previous section with its confidence
                title_raw = line
                current_section_confidence = 1.0  # Explicit rule match = high confidence
                is_header = True
                break
        if is_header:
            continue
        
        # fallback heuristics: numbered, TitleCase (>=2 words), ALLCAPS long (medium confidence)
        heuristic_match = False
        if NUMBERED_RE.match(line):
            heuristic_match = True
            new_section_confidence = 0.8  # Numbered pattern = good confidence
        elif TITLECASE_RE.match(line):
            heuristic_match = True
            new_section_confidence = 0.8  # TitleCase pattern = good confidence
        elif ALLCAPS_RE.match(line) and len(line.split()) >= 2:
            heuristic_match = True
            new_section_confidence = 0.8  # ALLCAPS pattern = good confidence
        
        if heuristic_match:
            flush()  # Flush previous section with its confidence
            title_raw = line
            current_section_confidence = new_section_confidence
            continue
        buf.append(line)

    # Flush final section with its confidence
    flush()
    if not sections:
        # No sections detected - return single section with low confidence
        return [("Introduction", "introduction", text.strip(), 0.0)]  # Low confidence for fallback
    return sections


def _canon_from_title(title: str) -> str:
    """Convert title to canonical section name."""
    t = re.sub(r"\s+", " ", (title or "").strip().lower())
    # a small alias map inline; playbook aliases still take precedence
    ALIASES = {
        "executive summary": "executive_summary",
        "table of contents": "table_of_contents",
        "conclusions": "conclusions",
        "conclusion": "conclusions",
        "abstract": "abstract",
        "introduction": "introduction",
        "background": "background",
    }
    if t in ALIASES:
        return ALIASES[t]
    return re.sub(r"[^a-z0-9]+", "_", t)[:40] or "section"


def normalize_encoding_artifacts(text: str) -> str:
    """
    Fix encoding artifacts like 'Â·' (middle dot), 'Â' (non-breaking space), etc.
    These occur when UTF-8 text is incorrectly decoded as Latin-1 or similar.
    
    Args:
        text: Input text with potential encoding artifacts
        
    Returns:
        Text with encoding artifacts fixed
    """
    if not text:
        return text
    
    # Common encoding artifacts and their fixes
    # These occur when UTF-8 bytes are interpreted as Latin-1
    encoding_fixes = {
        # Middle dot / bullet point artifacts
        'Â·': '·',  # UTF-8 C2 B7 (middle dot) decoded as Latin-1
        'Â¢': '¢',  # UTF-8 C2 A2 (cent sign) decoded as Latin-1
        'Â£': '£',  # UTF-8 C2 A3 (pound sign) decoded as Latin-1
        'Â¥': '¥',  # UTF-8 C2 A5 (yen sign) decoded as Latin-1
        'Â§': '§',  # UTF-8 C2 A7 (section sign) decoded as Latin-1
        'Â©': '©',  # UTF-8 C2 A9 (copyright) decoded as Latin-1
        'Â®': '®',  # UTF-8 C2 AE (registered) decoded as Latin-1
        'Â°': '°',  # UTF-8 C2 B0 (degree) decoded as Latin-1
        'Â±': '±',  # UTF-8 C2 B1 (plus-minus) decoded as Latin-1
        'Â²': '²',  # UTF-8 C2 B2 (superscript 2) decoded as Latin-1
        'Â³': '³',  # UTF-8 C2 B3 (superscript 3) decoded as Latin-1
        'Â´': '´',  # UTF-8 C2 B4 (acute accent) decoded as Latin-1
        'Âµ': 'µ',  # UTF-8 C2 B5 (micro) decoded as Latin-1
        'Â¶': '¶',  # UTF-8 C2 B6 (pilcrow) decoded as Latin-1
        'Â¹': '¹',  # UTF-8 C2 B9 (superscript 1) decoded as Latin-1
        'Âº': 'º',  # UTF-8 C2 BA (masculine ordinal) decoded as Latin-1
        'Â»': '»',  # UTF-8 C2 BB (right-pointing double angle) decoded as Latin-1
        'Â¼': '¼',  # UTF-8 C2 BC (vulgar fraction 1/4) decoded as Latin-1
        'Â½': '½',  # UTF-8 C2 BD (vulgar fraction 1/2) decoded as Latin-1
        'Â¾': '¾',  # UTF-8 C2 BE (vulgar fraction 3/4) decoded as Latin-1
        'Â¿': '¿',  # UTF-8 C2 BF (inverted question mark) decoded as Latin-1
        
        # Non-breaking space artifacts
        'Â ': ' ',  # UTF-8 C2 A0 (non-breaking space) decoded as Latin-1
        '\xa0': ' ',  # Direct non-breaking space
        
        # Em dash / en dash artifacts
        'â€"': '—',  # UTF-8 E2 80 94 (em dash) decoded as Latin-1
        'â€"': '–',  # UTF-8 E2 80 93 (en dash) decoded as Latin-1
        'â€"': '—',  # Alternative encoding
        'â€"': '–',  # Alternative encoding
        
        # Quote artifacts
        'â€™': "'",  # UTF-8 E2 80 99 (right single quotation mark) decoded as Latin-1
        'â€œ': '"',  # UTF-8 E2 80 9C (left double quotation mark) decoded as Latin-1
        'â€': '"',   # UTF-8 E2 80 9D (right double quotation mark) decoded as Latin-1
        'â€˜': "'",  # UTF-8 E2 80 98 (left single quotation mark) decoded as Latin-1
        
        # Ellipsis artifacts
        'â€¦': '...',  # UTF-8 E2 80 A6 (ellipsis) decoded as Latin-1
        
        # Other common artifacts
        'Ã¡': 'á',  # UTF-8 C3 A1 (a with acute) decoded as Latin-1
        'Ã©': 'é',  # UTF-8 C3 A9 (e with acute) decoded as Latin-1
        'Ã­': 'í',  # UTF-8 C3 AD (i with acute) decoded as Latin-1
        'Ã³': 'ó',  # UTF-8 C3 B3 (o with acute) decoded as Latin-1
        'Ãº': 'ú',  # UTF-8 C3 BA (u with acute) decoded as Latin-1
        'Ã±': 'ñ',  # UTF-8 C3 B1 (n with tilde) decoded as Latin-1
        'Ã': 'à',   # UTF-8 C3 A0 (a with grave) decoded as Latin-1
    }
    
    out = text
    for artifact, replacement in encoding_fixes.items():
        out = out.replace(artifact, replacement)
    
    return out


def normalize_repeated_words(text: str) -> str:
    """
    Remove repeated word runs like 'Uncontrolled diabetesUncontrolled diabetes...'
    that occur due to OCR errors or extraction issues.
    
    Args:
        text: Input text with potential repeated word runs
        
    Returns:
        Text with repeated word runs deduplicated
    """
    if not text:
        return text
    
    # Pattern: word boundary, word (2+ chars), same word immediately repeated (no space)
    # Example: "diabetesdiabetes" -> "diabetes"
    # But preserve intentional repetitions like "very very" (with space)
    pattern = r'\b([a-zA-Z]{2,})\1+\b'
    
    def deduplicate(match):
        word = match.group(1)
        # Only deduplicate if the repetition is 2+ times (to avoid false positives)
        full_match = match.group(0)
        if len(full_match) >= len(word) * 2:
            return word
        return full_match
    
    out = re.sub(pattern, deduplicate, text, flags=re.IGNORECASE)
    
    # Also handle case-insensitive repetitions: "DiabetesDIABETES" -> "Diabetes"
    pattern_case_insensitive = r'\b([a-zA-Z]{2,})(?i:\1)+\b'
    out = re.sub(pattern_case_insensitive, r'\1', out)
    
    return out


def normalize_whitespace(text: str) -> str:
    """
    Normalize whitespace: remove excessive spaces, normalize tabs, preserve paragraph boundaries.
    
    Args:
        text: Input text with potential whitespace issues
        
    Returns:
        Text with normalized whitespace
    """
    if not text:
        return text
    
    # Replace tabs with spaces
    out = text.replace('\t', ' ')
    
    # Collapse multiple spaces to single space (but preserve newlines)
    out = re.sub(r'[ \t]+', ' ', out)
    
    # Remove leading/trailing spaces on lines (but preserve blank lines)
    lines = out.split('\n')
    normalized_lines = [line.strip() if line.strip() else '' for line in lines]
    out = '\n'.join(normalized_lines)
    
    # Collapse multiple blank lines to max 2 (paragraph boundaries)
    out = re.sub(r'\n{3,}', '\n\n', out)
    
    # Remove trailing spaces before newlines
    out = re.sub(r' +\n', '\n', out)
    
    return out.strip()


def apply_enhanced_normalization(text: str) -> str:
    """
    Apply enhanced normalization patterns to improve text quality.
    More aggressive than standard normalization.
    
    Includes:
    - Encoding artifact fixes (Â·, etc.)
    - Whitespace normalization
    - Repeated word deduplication
    - Character normalization
    """
    # Check if text is already corrupted (spaces between characters) - if so, skip normalization
    # This can happen with bad PDF extraction
    if len(text) > 100:
        sample = text[:500]
        # Check if more than 30% of characters are spaces (indicating corruption)
        space_ratio = sample.count(" ") / len(sample) if len(sample) > 0 else 0
        if space_ratio > 0.3:
            logger.warning(
                "Text appears to be corrupted (excessive spaces), skipping enhanced normalization to avoid further corruption"
            )
            return text

    out = text
    
    # Step 1: Fix encoding artifacts (do this first, before other normalizations)
    out = normalize_encoding_artifacts(out)
    
    # Step 2: Normalize whitespace
    out = normalize_whitespace(out)
    
    # Step 3: Remove repeated word runs
    out = normalize_repeated_words(out)

    # Step 4: Enhanced character normalization
    # Fix common OCR errors and encoding issues
    replacements = [
        # Remove control characters except \n, \t, \r
        (r"[\x00-\x08\x0B-\x0C\x0E-\x1F]", ""),
        # Fix punctuation spacing (but be careful not to break words)
        (r" +([,.!?;:])", r"\1"),  # Remove space before punctuation
        (r"([,.!?;:])([^\s])", r"\1 \2"),  # Ensure space after punctuation (if missing)
        # Fix quote normalization (more comprehensive)
        (r"[\u2018\u2019\u2032]", "'"),  # Various single quotes to standard
        (r"[\u201C\u201D\u2033]", '"'),  # Various double quotes to standard
        (r"[\u2013\u2014\u2015]", "-"),  # Various dashes to hyphen
        # Fix ellipsis
        (r"\.{4,}", "..."),  # More than 3 dots -> ellipsis
    ]

    for pattern, replacement in replacements:
        try:
            out = re.sub(pattern, replacement, out)
        except (re.error, TypeError) as e:
            logger.warning(f"Enhanced normalization pattern failed: {pattern}, error: {e}")
            continue

    # Final cleanup
    out = out.strip()

    return out


def apply_error_correction(text: str) -> str:
    """
    Apply basic error correction to fix common typos and OCR errors.
    Uses pattern-based fixes and optionally spellchecker if available.
    """
    # Check if text is already corrupted (spaces between characters) - if so, skip error correction
    # This can happen with bad PDF extraction
    if len(text) > 100:
        sample = text[:500]
        # Check if more than 30% of characters are spaces (indicating corruption)
        space_ratio = sample.count(" ") / len(sample) if len(sample) > 0 else 0
        if space_ratio > 0.3:
            logger.warning(
                "Text appears to be corrupted (excessive spaces), skipping error correction to avoid further corruption"
            )
            return text

    try:
        from spellchecker import SpellChecker

        spell = SpellChecker()
        HAS_SPELLCHECKER = True
    except ImportError:
        HAS_SPELLCHECKER = False
        logger.debug("spellchecker library not available, using pattern-based correction only")

    out = text

    # Pattern-based fixes (don't require external libraries)
    # Only fix clear OCR errors, avoid patterns that could corrupt valid text
    pattern_fixes = [
        # Common OCR word errors (using word boundaries to avoid false positives)
        (r"\bteh\b", "the"),
        (r"\badn\b", "and"),
        (r"\btha\b", "that"),
        (r"\btaht\b", "that"),
        (r"\bhte\b", "the"),
        # Fix excessive repeated letters (4+ repeats -> 2)
        (r"([a-z])\1{3,}", r"\1\1"),
        # Fix missing space after sentence-ending punctuation (but only if next char is uppercase letter)
        (r"([.!?])([A-Z][a-z])", r"\1 \2"),
    ]

    for pattern, replacement in pattern_fixes:
        try:
            out = re.sub(pattern, replacement, out, flags=re.IGNORECASE)
        except (re.error, TypeError) as e:
            logger.warning(f"Error correction pattern failed: {pattern}, error: {e}")
            continue

    # Disable spellchecker-based correction for now - it's too risky and can corrupt valid text
    # The pattern-based fixes above are safer and sufficient for common OCR errors

    return out
