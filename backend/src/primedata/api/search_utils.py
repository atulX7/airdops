"""
Search utility functions for improving RAG playground query relevance.
Includes query expansion and keyword boosting.
"""

import re
from typing import List


def expand_query_terms(query: str) -> List[str]:
    """
    Expand query with common abbreviations and synonyms to improve search relevance.
    Returns a list of query terms (original + expansions) for keyword matching.
    
    Args:
        query: Original search query
        
    Returns:
        List of query terms including original and expansions
    """
    query_lower = query.lower()
    terms = set()
    
    # Add original query
    terms.add(query_lower)
    
    # Common abbreviation expansions
    expansions = {
        r'\baws\b': ['amazon web services', 'amazon web service'],
        r'\bceo\b': ['chief executive officer', 'chief executive'],
        r'\bcto\b': ['chief technology officer', 'chief technical officer'],
        r'\bcfo\b': ['chief financial officer'],
        r'\bcio\b': ['chief information officer'],
        r'\bapi\b': ['application programming interface'],
        r'\bsdk\b': ['software development kit'],
        r'\bui\b': ['user interface'],
        r'\bux\b': ['user experience'],
        r'\bqa\b': ['quality assurance'],
        r'\bdevops\b': ['development operations'],
    }
    
    # Medical/healthcare expansions
    medical_expansions = {
        r'\btype\s+1\b': ['type i', 'type one', 'insulin dependent', 'iddm'],
        r'\btype\s+2\b': ['type ii', 'type two', 'non-insulin dependent', 'niddm', 'adult onset'],
        r'\bdiabetes\b': ['diabetic', 'diabetes mellitus', 'dm'],
        r'\bdiabetic\b': ['diabetes', 'diabetes mellitus'],
    }
    
    # Apply expansions
    expanded_query = query_lower
    for pattern, replacements in expansions.items():
        if re.search(pattern, query_lower):
            for replacement in replacements:
                expanded_query = re.sub(pattern, replacement, expanded_query)
                terms.add(replacement)
    
    # Apply medical expansions
    for pattern, replacements in medical_expansions.items():
        if re.search(pattern, query_lower):
            for replacement in replacements:
                terms.add(replacement)
    
    # Extract important keywords (nouns, proper nouns, important terms)
    # Split by common separators and keep meaningful words
    words = re.findall(r'\b\w+\b', expanded_query)
    for word in words:
        if len(word) > 3:  # Skip very short words
            terms.add(word)
    
    return list(terms)


def calculate_keyword_boost(text: str, query_terms: List[str], original_query: str) -> float:
    """
    Calculate keyword boost score based on exact matches and term frequency.
    Returns a boost multiplier (0.0 to 0.15) to add to similarity score.
    Also applies penalties for low-content chunks (headings only, very short).
    
    Args:
        text: Document text to check
        query_terms: List of expanded query terms
        original_query: Original user query
        
    Returns:
        Boost value (can be negative for penalties, typically 0.0 to 0.15)
    """
    if not text or not query_terms:
        return 0.0
    
    text_lower = text.lower()
    original_query_lower = original_query.lower()
    text_stripped = text.strip()
    
    # Penalty for low-content chunks (headings only, very short)
    penalty = 0.0
    chunk_lines = text_stripped.split('\n')
    is_very_short = len(text_stripped) < 150
    has_few_lines = len(chunk_lines) <= 2
    # Check if mostly title case (likely a heading)
    words = text_stripped.split()
    if words:
        title_case_ratio = sum(1 for w in words if w and (w[0].isupper() or not w[0].isalpha())) / len(words)
        is_mostly_title_case = title_case_ratio > 0.8
    else:
        is_mostly_title_case = False
    
    is_likely_heading_only = is_very_short and has_few_lines and is_mostly_title_case
    
    # Apply penalty for heading-only chunks (reduce their score significantly)
    if is_likely_heading_only:
        penalty = -0.20  # Reduce score by 20% for heading-only chunks
        # If it's extremely short (< 50 chars), apply even more penalty
        if len(text_stripped) < 50:
            penalty = -0.30
    
    boost = 0.0
    max_boost = 0.15  # Maximum boost of 15% to similarity score
    
    # 1. Exact phrase match (highest boost)
    if original_query_lower in text_lower:
        boost += 0.08
    
    # 2. All important terms present (medium boost)
    important_terms = [term for term in query_terms if len(term) > 4]  # Focus on longer terms
    if important_terms:
        matches = sum(1 for term in important_terms if term in text_lower)
        term_coverage = matches / len(important_terms) if important_terms else 0
        boost += 0.05 * term_coverage
    
    # 3. Exact keyword matches (case-insensitive)
    keyword_matches = 0
    for term in query_terms:
        # Count occurrences of the term as whole word
        pattern = r'\b' + re.escape(term) + r'\b'
        matches = len(re.findall(pattern, text_lower, re.IGNORECASE))
        if matches > 0:
            keyword_matches += min(matches, 3)  # Cap at 3 matches per term
    
    if keyword_matches > 0:
        boost += min(0.02 * keyword_matches, 0.05)  # Up to 5% for keyword matches
    
    # 4. Entity/name matching (for queries like "CEO of AWS")
    # Check if query contains entity indicators and text contains those entities
    # Give higher boost for exact entity relationship matches
    
    # Check for "CEO of AWS" pattern in query
    if re.search(r'\b(?:ceo|chief executive officer)\b.*?\b(?:of|for)\b.*?\b(aws|amazon web services)\b', original_query_lower):
        # Look for exact pattern in text: "CEO Amazon Web Services" or "CEO AWS" or "chief executive officer AWS"
        if re.search(r'\b(?:ceo|chief executive officer)\b.*?\b(?:amazon web services|aws)\b', text_lower, re.IGNORECASE):
            boost += 0.10  # High boost for exact entity relationship match
        elif re.search(r'\b(?:aws|amazon web services)\b', text_lower):
            boost += 0.05  # Medium boost if AWS is mentioned
    
    # Check for "CEO of Amazon" pattern in query (different from AWS)
    elif re.search(r'\b(?:ceo|chief executive officer)\b.*?\b(?:of|for)\b.*?\bamazon\b', original_query_lower):
        if re.search(r'\b(?:ceo|chief executive officer)\b.*?\b(?:amazon\.com|amazon inc)\b', text_lower, re.IGNORECASE):
            boost += 0.08  # Boost for CEO of Amazon.com match
    
    # Apply penalty after calculating boost
    final_boost = boost + penalty
    
    # Ensure we don't go below -0.30 (maximum penalty) or above 0.15 (maximum boost)
    return max(min(final_boost, 0.15), -0.30)
