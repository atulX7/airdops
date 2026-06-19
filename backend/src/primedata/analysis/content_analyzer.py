"""
Content analysis module for intelligent chunking configuration.

This module analyzes content to automatically determine optimal chunking strategies
based on content type, structure, and complexity.
"""

import logging
import math
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def build_representative_sample(text: str, chunk: int = 5000, max_total: int = 20000) -> str:
    """Build a representative text sample using head, middle, and tail segments."""
    if not text:
        return ""

    normalized = " ".join(text.split())
    if not normalized:
        return ""

    if len(normalized) <= max_total:
        return normalized[:max_total]

    segment_size = min(chunk, max_total // 3)
    midpoint = len(normalized) // 2
    half_segment = segment_size // 2
    middle_start = max(0, midpoint - half_segment)
    middle_end = middle_start + segment_size
    if middle_end > len(normalized):
        middle_end = len(normalized)
        middle_start = max(0, middle_end - segment_size)

    head = normalized[:segment_size]
    middle = normalized[middle_start:middle_end]
    tail = normalized[-segment_size:]

    sample = f"{head} === MIDDLE SAMPLE === {middle} === END SAMPLE === {tail}"
    return sample[:max_total]


class ContentType(str, Enum):
    """Content type enumeration."""

    LEGAL = "legal"
    MEDICAL = "medical"  # WHO/clinical, guidelines, epidemiology, treatment (RAG-optimized)
    REGULATORY = "regulatory"  # For regulatory documents (EBA, ECB, Basel, etc.)
    FINANCE_BANKING = "finance_banking"  # For banking/financial documents
    CODE = "code"
    DOCUMENTATION = "documentation"
    CONVERSATION = "conversation"
    ACADEMIC = "academic"
    TECHNICAL = "technical"
    GENERAL = "general"


class ChunkingStrategy(str, Enum):
    """Chunking strategy enumeration."""

    FIXED_SIZE = "fixed_size"
    SEMANTIC = "semantic"
    RECURSIVE = "recursive"
    SENTENCE_BOUNDARY = "sentence_boundary"
    PARAGRAPH_BOUNDARY = "paragraph_boundary"


@dataclass
class ChunkingConfig:
    """Chunking configuration data class."""

    chunk_size: int
    chunk_overlap: int
    min_chunk_size: int
    max_chunk_size: int
    strategy: ChunkingStrategy
    content_type: ContentType
    confidence: float  # 0.0 to 1.0, how confident we are in this configuration
    reasoning: str  # Human-readable explanation of why these settings were chosen
    evidence: Optional[Dict[str, Any]] = None  # Detection evidence for UI display


class ContentAnalyzer:
    """Analyzes content to determine optimal chunking configuration."""

    def __init__(self):
        # Content type detection patterns
        self.content_patterns = {
            ContentType.LEGAL: [
                r"\b(whereas|hereby|herein|hereinafter|pursuant to|in accordance with)\b",
                r"\b(agreement|contract|terms|conditions|clause|section)\b",
                r"\b(party|parties|plaintiff|defendant|court|legal)\b",
            ],
            # General medical research: guidelines, clinical studies, epidemiology, any therapeutic area
            ContentType.MEDICAL: [
                r"\b(who|world health organization)\b",
                r"\b(epidemiology|epidemiological|prevalence|incidence|morbidity|mortality)\b",
                r"\b(diagnosis|treatment|therapy|therapeutic|screening|complications|prevention)\b",
                r"\b(guideline|guidelines|health system|clinical\s+practice)\b",
                r"\b(clinical\s+trial|randomized\s+controlled|cohort\s+study|systematic\s+review|meta-?analysis)\b",
                r"\b(clinical|patient|patients|disease|symptom|symptoms|medication|pharmaceutical|drug|drugs)\b",
                r"\b(efficacy|safety|adverse\s+event|biomarker|etiology|prognosis|pathology|pathological)\b",
                r"\b(intervention|vaccine|vaccination|oncology|cardiology|neurology|infectious\s+disease)\b",
                r"\b(comorbidity|comorbidities|disorder|syndrome|diagnostic|prognostic)\b",
            ],
            ContentType.REGULATORY: [
                r"\b(supervisor|auditor|regulator|supervision|regulatory)\b",
                r"\b(eba|ecb|basel|crr|crd|ssm|pru|fca|sec)\b",  # Regulatory bodies
                r"\b(guidelines|framework|directive|regulation|compliance)\b",
                r"\b(capital|risk|governance|oversight|monitoring)\b",
                r"\b(principle|requirement|standard|provision)\b",
                r"\b(whereas|pursuant to|in accordance with|hereinafter)\b",  # Legal language in regulatory docs
            ],
            ContentType.FINANCE_BANKING: [
                r"\b(banking|financial|finance|bank|institution)\b",
                r"\b(capital|liquidity|solvency|credit|market\s+risk)\b",  # Fixed: "market risk" as two words
                r"\b(asset|liability|balance\s+sheet|income\s+statement)\b",  # Fixed: multi-word terms
                r"\b(regulation|compliance|audit|supervision)\b",
                r"\b(interest\s+rate|yield|portfolio|investment)\b",  # Fixed: "interest rate" as two words
            ],
            ContentType.CODE: [
                r"^\s*(def|class|function|import|from|if|for|while|try|except)\s+",
                r"^\s*[a-zA-Z_][a-zA-Z0-9_]*\s*[=\(]",  # Variable assignments
                r"^\s*#.*$",  # Comments
                r"^\s*//.*$",  # Comments
                r"^\s*/\*.*\*/$",  # Block comments
            ],
            ContentType.DOCUMENTATION: [
                r"^#{1,6}\s+",  # Markdown headers
                r"^\s*\*\s+",  # Bullet points
                r"^\s*\d+\.\s+",  # Numbered lists
                r"```",  # Code blocks
                r"\[.*\]\(.*\)",  # Links
            ],
            ContentType.CONVERSATION: [
                r"^\s*\d{1,2}:\d{2}\s+[AP]M\s+",  # Timestamps
                r"^\s*\[.*\]\s+",  # Speaker names
                r"^\s*<.*>\s+",  # Chat format
                r"^\s*\w+:\s+",  # Simple speaker format
            ],
            ContentType.ACADEMIC: [
                r"\b(abstract|introduction|methodology|results|conclusion|references)\b",
                r"\b(study|research|analysis|hypothesis|findings|implications)\b",
                r"^\s*\d+\.\d+\s+",  # Section numbers
                r"\[.*\]\s*\(.*\)",  # Citations
            ],
            ContentType.TECHNICAL: [
                r"\b(API|endpoint|request|response|authentication|authorization)\b",
                r"\b(database|query|table|index|schema|migration)\b",
                r"\b(algorithm|optimization|performance|scalability|architecture)\b",
                r"^\s*```\w*$",  # Code blocks
            ],
        }

        # Optimal configurations for each content type
        # All sizes are in TOKENS (not characters)
        self.optimal_configs = {
            ContentType.LEGAL: {
                "chunk_size": 1200,
                "chunk_overlap": 240,  # ~20% overlap
                "min_chunk_size": 200,
                "max_chunk_size": 2000,
                "strategy": ChunkingStrategy.SEMANTIC,
                "reasoning": "Legal documents require larger chunks to preserve context and legal meaning",
            },
            ContentType.MEDICAL: {
                "chunk_size": 800,  # 700-900 range, RAG-optimized
                "chunk_overlap": 160,  # 140-180 range, ~20%
                "min_chunk_size": 100,
                "max_chunk_size": 1200,
                "strategy": ChunkingStrategy.SEMANTIC,
                "reasoning": "Medical/clinical content uses semantic, section-aware chunking for RAG (WHO, guidelines, treatment)",
            },
            ContentType.REGULATORY: {
                "chunk_size": 1400,
                "chunk_overlap": 280,  # ~20% overlap
                "min_chunk_size": 200,
                "max_chunk_size": 2200,
                "strategy": ChunkingStrategy.SEMANTIC,
                "reasoning": "Regulatory documents require larger chunks to preserve compliance context and cross-references",
            },
            ContentType.FINANCE_BANKING: {
                "chunk_size": 1300,
                "chunk_overlap": 260,  # ~20% overlap
                "min_chunk_size": 200,
                "max_chunk_size": 2000,
                "strategy": ChunkingStrategy.SEMANTIC,
                "reasoning": "Banking documents need larger chunks to preserve financial context and relationships",
            },
            ContentType.CODE: {
                "chunk_size": 900,
                "chunk_overlap": 180,  # ~20% overlap
                "min_chunk_size": 100,
                "max_chunk_size": 1500,
                "strategy": ChunkingStrategy.RECURSIVE,
                "reasoning": "Code benefits from recursive chunking to preserve function/class boundaries",
            },
            ContentType.DOCUMENTATION: {
                "chunk_size": 800,
                "chunk_overlap": 160,  # ~20% overlap
                "min_chunk_size": 100,
                "max_chunk_size": 1500,
                "strategy": ChunkingStrategy.PARAGRAPH_BOUNDARY,
                "reasoning": "Documentation works well with paragraph-based chunking for better readability",
            },
            ContentType.CONVERSATION: {
                "chunk_size": 700,
                "chunk_overlap": 140,  # ~20% overlap
                "min_chunk_size": 50,
                "max_chunk_size": 1200,
                "strategy": ChunkingStrategy.SENTENCE_BOUNDARY,
                "reasoning": "Conversations benefit from smaller chunks at sentence boundaries",
            },
            ContentType.ACADEMIC: {
                "chunk_size": 1200,
                "chunk_overlap": 240,  # ~20% overlap
                "min_chunk_size": 150,
                "max_chunk_size": 2000,
                "strategy": ChunkingStrategy.SEMANTIC,
                "reasoning": "Academic papers need larger chunks to preserve argument structure",
            },
            ContentType.TECHNICAL: {
                "chunk_size": 800,
                "chunk_overlap": 160,  # ~20% overlap
                "min_chunk_size": 100,
                "max_chunk_size": 1500,
                "strategy": ChunkingStrategy.SEMANTIC,
                "reasoning": "Technical content benefits from semantic chunking to preserve concept boundaries",
            },
            ContentType.GENERAL: {
                "chunk_size": 1000,
                "chunk_overlap": 200,
                "min_chunk_size": 100,
                "max_chunk_size": 2000,
                "strategy": ChunkingStrategy.FIXED_SIZE,
                "reasoning": "General content uses balanced fixed-size chunking for optimal retrieval",
            },
        }

    def analyze_content(
        self, 
        content: str, 
        filename: Optional[str] = None,
        hint: Optional[str] = None,
        full_text_length: Optional[int] = None,
    ) -> ChunkingConfig:
        """
        Analyze content and return optimal chunking configuration.

        Args:
            content: The text content to analyze
            filename: Optional filename for additional context
            hint: Optional domain hint from playbook (e.g., "regulatory", "legal", "finance_banking")
            full_text_length: Optional length of the full text when analyzing a sample

        Returns:
            ChunkingConfig with optimal settings and detection evidence
        """
        if full_text_length is not None and full_text_length != len(content):
            logger.info(
                f"Analyzing content sample length: {len(content)} characters (full text: {full_text_length})"
                + (f" (hint: {hint})" if hint else "")
            )
        else:
            logger.info(f"Analyzing content: {len(content)} characters" + (f" (hint: {hint})" if hint else ""))

        # Detect content type with hint and evidence - now returns top candidates
        result = self._detect_content_type(content, filename, hint)
        content_type = result["best_type"]
        confidence = result["best_score"]
        evidence = result["evidence"]
        candidates = result["candidates"]

        # Add candidates to evidence for UI display
        evidence["top_candidates"] = candidates

        # Get base configuration for detected type
        base_config = self.optimal_configs[content_type]

        # Adjust configuration based on content characteristics
        adjusted_config = self._adjust_for_content_characteristics(content, base_config, content_type)

        # Create final configuration with evidence
        config = ChunkingConfig(
            chunk_size=adjusted_config["chunk_size"],
            chunk_overlap=adjusted_config["chunk_overlap"],
            min_chunk_size=adjusted_config["min_chunk_size"],
            max_chunk_size=adjusted_config["max_chunk_size"],
            strategy=adjusted_config["strategy"],
            content_type=content_type,
            confidence=confidence,
            reasoning=adjusted_config["reasoning"],
            evidence=evidence,
        )

        logger.info(f"Generated chunking config: {content_type} with {confidence:.2f} confidence")
        return config

    def _detect_content_type(
        self, 
        content: str, 
        filename: Optional[str] = None,
        hint: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Detect content type based on patterns and filename.
        
        FIXED VERSION: Deterministic, explainable, accurate across document types.
        
        Args:
            content: Text content to analyze
            filename: Optional filename for context
            hint: Optional domain hint from playbook
            
        Returns:
            Dict with:
            - best_type: ContentType
            - best_score: float
            - candidates: List[Dict] with top 3 candidates
            - evidence: Dict with detailed evidence
        """
        import math

        # --- Section distribution & OCR/noise metrics (for debug and decision trace) ---
        lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        section_distribution = {
            "line_count": len(lines),
            "paragraph_count": len(paragraphs),
            "word_count": len(content.split()),
            "char_count": len(content),
            "header_like_lines": sum(1 for ln in lines if re.match(r"^#{1,6}\s|\d+(?:\.\d+)*\s+[A-Z]|^[IVXLCM]+\.\s", ln)),
            "all_caps_lines": sum(1 for ln in lines if len(ln) > 2 and ln.isupper() and ln.isalpha()),
        }
        content_chars = content.replace(" ", "").replace("\n", "")
        digit_count = sum(1 for c in content_chars if c.isdigit())
        alpha_count = sum(1 for c in content_chars if c.isalpha())
        ocr_noise_metrics = {
            "digit_ratio": round(digit_count / len(content_chars), 4) if content_chars else 0.0,
            "alpha_ratio": round(alpha_count / len(content_chars), 4) if content_chars else 0.0,
            "pipe_count": content.count("|"),
            "short_lines_ratio": round(sum(1 for ln in lines if 0 < len(ln) <= 20) / len(lines), 4) if lines else 0.0,
            "mid_sentence_breaks": len(re.findall(r"[a-z]\s*\n\s*[a-z]", content)),
        }

        scores = {}
        evidence = {
            "matched_patterns": [],  # Top matched terms for UI display (FINAL type only)
            "pattern_details": {},  # Per-type pattern match details
            "hint_applied": False,
            "hint_type": None,
            "hint_bonus": 0.0,
            "hint_trigger_reason": None,
            "filename_extension": None,
            "all_scores": {},  # All type scores for comparison
            "medical_keywords_found": [],
            "medical_keyword_score": 0.0,
            "medical_matched_terms": [],  # All medical terms matched (keywords + MeSH-like + clinical)
            "medical_density": 0.0,  # Medical term count per 1k words (for tie-breaks and downweighting)
            "section_distribution": section_distribution,
            "ocr_noise_metrics": ocr_noise_metrics,
        }

        # Map hint to ContentType
        hint_to_type = {
            "regulatory": ContentType.REGULATORY,
            "finance_banking": ContentType.FINANCE_BANKING,
            "legal": ContentType.LEGAL,
            "academic": ContentType.ACADEMIC,
            "technical": ContentType.TECHNICAL,
            "medical": ContentType.MEDICAL,
        }

        # Content type specificity priority (higher = more specific).
        # Medical > academic > regulatory for domain docs; prevent technical from winning on index/table alone.
        SPECIFICITY_PRIORITY = {
            ContentType.LEGAL: 10,   # Legal terms dominate when present
            ContentType.MEDICAL: 9,
            ContentType.REGULATORY: 8,
            ContentType.FINANCE_BANKING: 7,
            ContentType.ACADEMIC: 6,
            ContentType.TECHNICAL: 5,
            ContentType.DOCUMENTATION: 4,
            ContentType.CONVERSATION: 3,
            ContentType.CODE: 2,
            ContentType.GENERAL: 1,
        }

        # Medical keywords for MEDICAL detection (first-class candidate; drive score + tie-breaks)
        # Broad medical research: any therapeutic area, not limited to diabetes/insulin
        medical_keywords = [
            "medical", "medicine", "clinical", "patient", "patients", "treatment", "therapy",
            "diagnosis", "disease", "diseases", "symptom", "symptoms", "health", "healthcare",
            "hospital", "physician", "doctor", "medication", "drug", "drugs", "pharmaceutical",
            "pharma", "trial", "trials", "study", "studies", "research", "researchers",
            "pathology", "pathological", "epidemiology", "epidemiological", "prevalence",
            "incidence", "mortality", "morbidity", "comorbidity", "comorbidities", "syndrome",
            "disorder", "condition", "conditions", "who", "screening", "complications",
            "guideline", "prevention", "health system", "efficacy", "safety", "adverse event",
            "biomarker", "etiology", "prognosis", "systematic review", "meta-analysis",
            "cohort study", "randomized", "vaccine", "vaccination", "therapeutic", "intervention",
        ]
        # MeSH-like terms (disease/condition/therapeutic terms that strongly indicate medical content)
        mesh_like_terms = [
            "diabetes", "diabetic", "insulin", "glucose", "hbA1c", "hypoglycemia", "hyperglycemia",
            "hypertension", "cardiovascular", "myocardial", "stroke", "cancer", "oncology",
            "tuberculosis", "malaria", "hiv", "hepatitis", "asthma", "copd", "chronic kidney",
            "renal", "neuropathy", "retinopathy", "nephropathy", "type 1 diabetes", "type 2 diabetes",
            "metformin", "antihypertensive", "antibiotic", "antiviral", "immunization",
            "diagnostic criteria", "differential diagnosis", "clinical presentation", "prognostic",
        ]
        # Clinical phrasing patterns (regex) – high signal for medical
        clinical_phrasing_patterns = [
            r"\bpatient(s)?\s+with\s+\w+",
            r"\bdiagnosed\s+with\b",
            r"\btreatment\s+(of|for)\s+\w+",
            r"\bclinical\s+(trial|study|evaluation|presentation)\b",
            r"\brandomized\s+(controlled|clinical)\b",
            r"\bprevalence\s+(of|rate)\b",
            r"\bincidence\s+(of|rate)\b",
            r"\bmorbidity\s+and\s+mortality\b",
            r"\bguidelines?\s+(for|on)\s+\w+",
            r"\bwho\s+(guidelines?|recommendations?)\b",
            r"\btype\s+[12]\s+diabetes\b",
            r"\bblood\s+(glucose|sugar|pressure)\b",
            r"\badverse\s+(event|effect|reaction)\b",
        ]

        # Check filename extension if available (WEAK PRIOR only)
        if filename:
            ext = Path(filename).suffix.lower()
            evidence["filename_extension"] = ext
            # Use weak priors instead of strong defaults
            if ext in [".py", ".js", ".java", ".cpp", ".c", ".go", ".rs", ".ts", ".rb", ".php"]:
                scores[ContentType.CODE] = 0.35  # Weak prior, not 0.8
            elif ext in [".md", ".rst", ".txt"]:
                scores[ContentType.DOCUMENTATION] = 0.25  # Weak prior, not 0.6
            # PDF/DOC/DOCX: NO DEFAULT SCORE - let content patterns dominate
            elif ext in [".pdf", ".doc", ".docx"]:
                # Very small neutral prior (0.05) or none at all
                pass  # Don't assign GENERAL just because it's PDF

        # Medical as first-class candidate: keywords + MeSH-like terms + clinical phrasing patterns
        content_lower = content.lower()
        word_count = len(content.split())
        medical_matched_terms = []

        found_medical_keywords = [kw for kw in medical_keywords if kw in content_lower]
        medical_matched_terms.extend(found_medical_keywords)

        for term in mesh_like_terms:
            if term in content_lower:
                medical_matched_terms.append(term)

        for pattern in clinical_phrasing_patterns:
            for m in re.finditer(pattern, content, re.IGNORECASE):
                snippet = m.group(0).strip()
                if snippet and snippet not in medical_matched_terms:
                    medical_matched_terms.append(snippet[:80])  # cap length

        evidence["medical_matched_terms"] = list(dict.fromkeys(medical_matched_terms))[:50]  # dedupe, limit 50
        medical_term_count = len(evidence["medical_matched_terms"])
        # Density = distinct medical terms per 1k words (for tie-breaks and regulatory downweighting)
        medical_density = (medical_term_count / max(word_count / 1000.0, 0.1))
        evidence["medical_density"] = round(medical_density, 3)

        if found_medical_keywords:
            evidence["medical_keywords_found"] = list(set(found_medical_keywords))[:20]
            medical_keyword_count = len(found_medical_keywords)
            medical_keyword_score = min(0.25, 0.05 + medical_keyword_count * 0.015)
            evidence["medical_keyword_score"] = round(medical_keyword_score, 3)
        else:
            evidence["medical_keyword_score"] = 0.0

        # MEDICAL first-class score: keyword score + density-based bonus (MeSH/clinical add to score)
        if medical_term_count > 0:
            if ContentType.MEDICAL not in scores:
                scores[ContentType.MEDICAL] = 0.0
            scores[ContentType.MEDICAL] += evidence["medical_keyword_score"]
            # Bonus from MeSH + clinical matches (cap so medical can reach ~0.5 from terms alone)
            mesh_clinical_bonus = min(0.25, medical_term_count * 0.015 + (medical_density * 0.02))
            scores[ContentType.MEDICAL] = min(1.0, scores[ContentType.MEDICAL] + mesh_clinical_bonus)

        # Analyze content patterns with DENSITY+THRESHOLD approach (fixes long-doc penalty)
        word_count = len(content.split())
        occurrence_cap = 8  # Saturates after enough matches
        density_cap = 1.5  # per 1k words

        for content_type, patterns in self.content_patterns.items():
            total_occurrences = 0
            pattern_details = []
            all_matched_terms = []

            for pattern in patterns:
                # Find all matches
                pattern_matches = re.findall(pattern, content, re.IGNORECASE | re.MULTILINE)
                match_count = len(pattern_matches)
                total_occurrences += match_count
                
                if match_count > 0:
                    # Extract actual matched terms
                    matched_terms = []
                    for match in pattern_matches:
                        if isinstance(match, tuple):
                            matched_terms.extend([m for m in match if m])
                        else:
                            matched_terms.append(match)
                    
                    unique_terms = list(set([t.strip() for t in matched_terms if t.strip()]))[:10]
                    all_matched_terms.extend(unique_terms)
                    
                    pattern_details.append({
                        "pattern": pattern,
                        "match_count": match_count,
                        "matched_terms": unique_terms,
                    })

            if total_occurrences > 0:
                # DENSITY+THRESHOLD scoring (prevents long-doc penalty)
                # Compute density = occurrences / max(word_count/1000, 1)
                density = total_occurrences / max(word_count / 1000.0, 1.0)
                
                # Score = 60% from occurrences (log-scaled) + 40% from density
                occurrence_score = min(1.0, math.log1p(total_occurrences) / math.log1p(occurrence_cap))
                density_score = min(1.0, density / density_cap)
                
                pattern_score = (occurrence_score * 0.6) + (density_score * 0.4)
                
                # Add minimum absolute match bonus: if we have enough matches, ensure score doesn't drop too low
                # This prevents long documents from being unfairly penalized
                min_absolute_matches = 3  # Minimum matches to get bonus
                absolute_match_bonus = 0.0
                if total_occurrences >= min_absolute_matches:
                    # Bonus scales with matches but caps at 0.15
                    absolute_match_bonus = min(0.15, (total_occurrences - min_absolute_matches) * 0.02)
                    pattern_score = min(1.0, pattern_score + absolute_match_bonus)
                
                # Average across patterns (but weight by match count)
                if content_type == ContentType.MEDICAL:
                    # MEDICAL first-class: keep keyword + MeSH/clinical bonus on top of pattern score
                    medical_bonus = evidence["medical_keyword_score"] + min(
                        0.25,
                        len(evidence.get("medical_matched_terms", [])) * 0.015
                        + evidence.get("medical_density", 0) * 0.02,
                    )
                    scores[content_type] = min(1.0, pattern_score + medical_bonus)
                else:
                    scores[content_type] = pattern_score
                evidence["pattern_details"][content_type.value] = pattern_details
                evidence["pattern_details"][content_type.value + "_occurrences"] = total_occurrences
                evidence["pattern_details"][content_type.value + "_density"] = round(density, 3)
                if absolute_match_bonus > 0:
                    evidence["pattern_details"][content_type.value + "_absolute_match_bonus"] = round(absolute_match_bonus, 3)

        # Reduce false positives from regulatory (risk/monitoring/standard) when medical density is high
        medical_density_val = evidence.get("medical_density", 0)
        if medical_density_val >= 5.0 and ContentType.REGULATORY in scores:
            old_reg = scores[ContentType.REGULATORY]
            scores[ContentType.REGULATORY] = round(old_reg * 0.6, 3)
            evidence["regulatory_downweighted"] = True
            evidence["regulatory_downweight_reason"] = f"medical_density={medical_density_val} (reduce risk/monitoring/standard false positives)"

        # Prevent INDEX/TABLE alone from pushing technical when medical evidence exists
        if evidence.get("medical_keyword_score", 0) >= 0.10 and ContentType.TECHNICAL in scores:
            old_tech = scores[ContentType.TECHNICAL]
            scores[ContentType.TECHNICAL] = round(old_tech * 0.6, 3)
            evidence["technical_downweighted"] = True
            evidence["technical_downweight_reason"] = "medical_keyword_score >= 0.10 (avoid index/table alone)"

        # Medical should outrank academic/regulatory when medical_keyword_score >= 0.10 and medical density high
        medical_score = scores.get(ContentType.MEDICAL, 0)
        if (
            evidence.get("medical_keyword_score", 0) >= 0.10
            and medical_score > 0
            and ContentType.LEGAL not in scores
        ):
            if medical_score < 0.5:
                scores[ContentType.MEDICAL] = min(1.0, medical_score + 0.12)
                evidence["medical_boost_applied"] = True

        # Store all scores for UI comparison
        evidence["all_scores"] = {k.value: round(v, 3) for k, v in scores.items()}

        # Apply hint: allow override/boost even when current_best_score >= 0.5
        # Hint must be allowed to influence decision regardless of current scores
        if hint:
            hinted_type = hint_to_type.get(hint.lower())
            if hinted_type:
                evidence["hint_type"] = hint
                
                # Check if hinted type has at least minimal evidence
                has_minimal_evidence = (
                    hinted_type in scores and scores[hinted_type] > 0
                ) or (
                    hinted_type == ContentType.ACADEMIC and evidence.get("medical_keyword_score", 0) > 0
                ) or (
                    hinted_type == ContentType.MEDICAL and evidence.get("medical_keyword_score", 0) > 0
                )
                
                # Get current best score before hint (for comparison)
                current_best_score = max(scores.values()) if scores else 0.0
                
                # Apply hint bonus if minimal evidence exists OR if hint should override
                # Hint can override even when current_best_score >= 0.5 if it has minimal evidence
                if has_minimal_evidence:
                    # Apply hint bonus
                    hint_bonus = 0.15  # Fixed bonus amount
                    if hinted_type not in scores:
                        scores[hinted_type] = 0.0
                    
                    # Record hint decision reasoning
                    hint_reasoning = []
                    if current_best_score >= 0.5:
                        hint_reasoning.append(f"current_best_score={current_best_score:.2f} >= 0.5")
                    if has_minimal_evidence:
                        hint_reasoning.append("minimal_evidence_found")
                    
                    scores[hinted_type] += hint_bonus
                    # Cap at 1.0
                    scores[hinted_type] = min(1.0, scores[hinted_type])
                    
                    evidence["hint_applied"] = True
                    evidence["hint_bonus"] = hint_bonus
                    evidence["hint_trigger_reason"] = "; ".join(hint_reasoning) if hint_reasoning else "minimal_evidence_found"
                    evidence["hint_decision_reasoning"] = (
                        f"Hint '{hint}' applied with bonus {hint_bonus:.2f} to {hinted_type.value}. "
                        f"Previous score: {scores[hinted_type] - hint_bonus:.2f}, "
                        f"New score: {scores[hinted_type]:.2f}. "
                        f"Current best before hint: {current_best_score:.2f}"
                    )
                    logger.info(
                        f"Hint '{hint}' applied with bonus {hint_bonus:.2f} to {hinted_type.value} "
                        f"(score now: {scores[hinted_type]:.2f}, previous best: {current_best_score:.2f})"
                    )
                else:
                    evidence["hint_trigger_reason"] = "no_minimal_evidence"
                    evidence["hint_decision_reasoning"] = (
                        f"Hint '{hint}' not applied: no minimal evidence for {hinted_type.value}"
                    )
                    logger.info(
                        f"Hint '{hint}' not applied: no minimal evidence for {hinted_type.value}"
                    )

        # If no specific type detected, use general
        if not scores:
            evidence["final_type"] = ContentType.GENERAL.value
            evidence["final_confidence"] = 0.3
            return {
                "best_type": ContentType.GENERAL,
                "best_score": 0.3,
                "candidates": [{"type": ContentType.GENERAL.value, "score": 0.3, "key_matches": [], "evidence_snippet": "No patterns detected"}],
                "evidence": evidence,
            }

        # Sort scores to get top candidates
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        
        # Build top 3 candidates
        candidates = []
        for content_type, score in sorted_scores[:3]:
            pattern_details = evidence["pattern_details"].get(content_type.value, [])
            key_matches = []
            for detail in pattern_details[:3]:  # Top 3 patterns
                key_matches.extend(detail.get("matched_terms", [])[:5])  # Top 5 terms per pattern
            
            candidates.append({
                "type": content_type.value,
                "score": round(score, 3),
                "key_matches": list(set(key_matches))[:15],  # Limit to 15 unique terms
                "evidence_snippet": f"{len(pattern_details)} patterns matched, {evidence['pattern_details'].get(content_type.value + '_occurrences', 0)} total occurrences"
            })

        # Determine best type with tie-breaking
        best_type, best_score = sorted_scores[0]
        epsilon = 0.02
        medical_evidence = evidence.get("medical_keyword_score", 0) >= 0.10
        medical_score_val = scores.get(ContentType.MEDICAL, 0)
        medical_density_high = evidence.get("medical_density", 0) >= 5.0

        # Tie-break: if medical >= 0.75 and within 0.05 of top score, choose medical
        if (
            len(sorted_scores) > 0
            and medical_score_val >= 0.75
            and best_type != ContentType.MEDICAL
            and abs(medical_score_val - best_score) <= 0.05
        ):
            evidence["tie_break_applied"] = True
            evidence["tie_break_reason"] = f"medical score {medical_score_val:.2f} >= 0.75 and within 0.05 of top ({best_score:.2f})"
            best_type = ContentType.MEDICAL
            best_score = medical_score_val
            logger.info(f"Tie-break: MEDICAL chosen (score {medical_score_val:.2f} >= 0.75, within 0.05 of top)")

        # Tie-break: if academic and regulatory tie at 1.0 (or very close), prefer medical/academic when medical density high
        if not evidence.get("tie_break_applied") and len(sorted_scores) >= 2 and medical_density_high:
            first_type, first_score = sorted_scores[0]
            second_type, second_score = sorted_scores[1]
            if abs(first_score - second_score) < 0.02:
                if first_type == ContentType.REGULATORY and second_type == ContentType.ACADEMIC:
                    evidence["tie_break_applied"] = True
                    evidence["tie_break_reason"] = "academic preferred over regulatory (medical density high)"
                    best_type = ContentType.ACADEMIC
                    best_score = second_score
                elif first_type == ContentType.REGULATORY and second_type == ContentType.MEDICAL:
                    evidence["tie_break_applied"] = True
                    evidence["tie_break_reason"] = "medical preferred over regulatory (medical density high)"
                    best_type = ContentType.MEDICAL
                    best_score = second_score

        # Tie-break: TECHNICAL vs MEDICAL/ACADEMIC when medical evidence exists (prevent index/table alone)
        if not evidence.get("tie_break_applied") and len(sorted_scores) > 1 and best_type == ContentType.TECHNICAL and medical_evidence:
            second_best_type, second_best_score = sorted_scores[1]
            if second_best_type in (ContentType.MEDICAL, ContentType.ACADEMIC) and abs(best_score - second_best_score) < 0.08:
                evidence["tie_break_applied"] = True
                evidence["tie_break_reason"] = f"{second_best_type.value} preferred over technical (medical evidence; avoid index/table)"
                best_type = second_best_type
                best_score = second_best_score
                logger.info(f"Tie-break: {best_type.value} chosen over TECHNICAL (medical evidence)")

        # Tie-break: scores within epsilon — prefer more specific: medical > academic > regulatory
        if not evidence.get("tie_break_applied") and len(sorted_scores) > 1:
            second_best_type, second_best_score = sorted_scores[1]
            if abs(best_score - second_best_score) < epsilon:
                if SPECIFICITY_PRIORITY.get(second_best_type, 0) > SPECIFICITY_PRIORITY.get(best_type, 0):
                    evidence["tie_break_applied"] = True
                    evidence["tie_break_reason"] = f"{second_best_type.value} is more specific than {best_type.value}"
                    best_type = second_best_type
                    best_score = second_best_score
                    logger.info(f"Tie-break: {best_type.value} chosen over {sorted_scores[0][0].value} (more specific)")
                else:
                    evidence["tie_break_applied"] = False
            else:
                evidence["tie_break_applied"] = False
        elif not evidence.get("tie_break_applied"):
            evidence["tie_break_applied"] = False

        # Calculate confidence gap
        confidence_gap = 0.0
        if len(sorted_scores) > 1:
            confidence_gap = best_score - sorted_scores[1][1]
        evidence["confidence_gap"] = round(confidence_gap, 3)
        
        final_confidence = min(best_score, 1.0)
        final_type_value = best_type.value
        
        evidence["final_type"] = final_type_value
        evidence["final_confidence"] = final_confidence

        # Keep UI terms focused - only show matched terms for FINAL type
        final_details = evidence["pattern_details"].get(final_type_value, [])
        final_terms = []
        for detail in final_details:
            final_terms.extend(detail.get("matched_terms", []))
        
        # Use dict.fromkeys to preserve order while deduplicating, then limit to 30
        evidence["matched_patterns"] = list(dict.fromkeys(final_terms))[:30]

        # Debug: full decision trace (content analyzer scores, tie-break, hinting)
        logger.info(
            "[CONTENT_ANALYZER] Decision trace: all_scores=%s, final_type=%s, tie_break_reason=%s, hint_applied=%s",
            evidence.get("all_scores"),
            final_type_value,
            evidence.get("tie_break_reason"),
            evidence.get("hint_applied"),
        )
        logger.debug(
            "[CONTENT_ANALYZER] Top 30 matched terms (final type): %s",
            evidence.get("matched_patterns", [])[:30],
        )
        logger.debug(
            "[CONTENT_ANALYZER] Section distribution: %s",
            evidence.get("section_distribution"),
        )
        logger.debug(
            "[CONTENT_ANALYZER] OCR/noise metrics: %s",
            evidence.get("ocr_noise_metrics"),
        )

        return {
            "best_type": best_type,
            "best_score": final_confidence,
            "candidates": candidates,
            "evidence": evidence,
        }

    def _adjust_for_content_characteristics(self, content: str, base_config: Dict, content_type: ContentType) -> Dict:
        """Adjust configuration based on specific content characteristics."""
        config = base_config.copy()

        # Analyze content complexity
        avg_sentence_length = self._calculate_avg_sentence_length(content)
        paragraph_count = len([p for p in content.split("\n\n") if p.strip()])
        word_count = len(content.split())

        # Adjust chunk size based on sentence length
        if avg_sentence_length > 30:  # Long sentences
            config["chunk_size"] = int(config["chunk_size"] * 1.2)
            config["chunk_overlap"] = int(config["chunk_overlap"] * 1.2)
            config["reasoning"] += " (adjusted for long sentences)"
        elif avg_sentence_length < 15:  # Short sentences
            config["chunk_size"] = int(config["chunk_size"] * 0.8)
            config["chunk_overlap"] = int(config["chunk_overlap"] * 0.8)
            config["reasoning"] += " (adjusted for short sentences)"

        # Adjust for very short content
        if word_count < 100:
            config["chunk_size"] = min(config["chunk_size"], word_count * 4)
            config["chunk_overlap"] = min(config["chunk_overlap"], config["chunk_size"] // 4)
            config["reasoning"] += " (adjusted for short content)"

        # Adjust for very long content
        elif word_count > 10000:
            config["chunk_size"] = int(config["chunk_size"] * 1.1)
            config["chunk_overlap"] = int(config["chunk_overlap"] * 1.1)
            config["reasoning"] += " (adjusted for long content)"

        # Ensure min/max constraints
        config["chunk_size"] = max(config["min_chunk_size"], min(config["chunk_size"], config["max_chunk_size"]))
        config["chunk_overlap"] = min(config["chunk_overlap"], config["chunk_size"] - 1)

        return config

    def _calculate_avg_sentence_length(self, content: str) -> float:
        """Calculate average sentence length in words."""
        sentences = re.split(r"[.!?]+", content)
        if not sentences:
            return 0.0

        total_words = sum(len(sentence.split()) for sentence in sentences if sentence.strip())
        return total_words / len([s for s in sentences if s.strip()])

    def preview_chunking(self, content: str, config: ChunkingConfig) -> Dict[str, Any]:
        """
        Preview how content would be chunked with given configuration.

        Args:
            content: Content to preview
            config: Chunking configuration to use

        Returns:
            Dictionary with preview information
        """
        chunks = self._simulate_chunking(content, config)

        return {
            "total_chunks": len(chunks),
            "avg_chunk_size": sum(len(chunk["text"]) for chunk in chunks) / len(chunks) if chunks else 0,
            "min_chunk_size": min(len(chunk["text"]) for chunk in chunks) if chunks else 0,
            "max_chunk_size": max(len(chunk["text"]) for chunk in chunks) if chunks else 0,
            "chunks": chunks[:5],  # First 5 chunks as preview
            "estimated_retrieval_quality": self._estimate_retrieval_quality(chunks, config),
        }

    def _simulate_chunking(self, content: str, config: ChunkingConfig) -> List[Dict[str, Any]]:
        """
        Simulate chunking process to preview results.
        
        FIX #3: Convert tokens to approximate characters for preview
        (matches preprocess.py convention: 1 token ≈ 4 chars)
        """
        chunks = []
        start = 0
        chunk_index = 0

        # Convert tokens to approximate characters (1 token ≈ 4 chars)
        approx_chars = int(config.chunk_size * 4)
        approx_overlap_chars = int(config.chunk_overlap * 4)

        while start < len(content):
            end = min(start + approx_chars, len(content))
            chunk_text = content[start:end]

            if not chunk_text.strip():
                break

            chunks.append(
                {
                    "chunk_index": chunk_index,
                    "text": chunk_text.strip(),
                    "start_char": start,
                    "end_char": end,
                    "size": len(chunk_text.strip()),
                }
            )

            chunk_index += 1
            step_size = max(1, approx_chars - approx_overlap_chars)
            start += step_size

            if start >= len(content):
                break

        return chunks

    def _estimate_retrieval_quality(self, chunks: List[Dict], config: ChunkingConfig) -> str:
        """Estimate retrieval quality based on chunk characteristics."""
        if not chunks:
            return "unknown"

        avg_size = sum(chunk["size"] for chunk in chunks) / len(chunks)
        size_variance = sum((chunk["size"] - avg_size) ** 2 for chunk in chunks) / len(chunks)

        # Convert config sizes from tokens to chars for comparison (1 token ≈ 4 chars)
        min_chars = config.min_chunk_size * 4
        max_chars = config.max_chunk_size * 4

        # Good quality indicators
        if min_chars <= avg_size <= max_chars and size_variance < (avg_size * 0.3) ** 2:
            return "high"
        elif min_chars * 0.8 <= avg_size <= max_chars * 1.2:
            return "medium"
        else:
            return "low"


# Global instance
content_analyzer = ContentAnalyzer()
