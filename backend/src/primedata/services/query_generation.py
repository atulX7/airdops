"""
Synthetic query generation for RAG evaluation.

Generates realistic queries from chunks to create evaluation sets.
"""
import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


def generate_queries_for_chunk(
    chunk_text: str,
    chunk_id: str,
    query_style: str = "technical",
    num_queries: int = 3,
    min_length: int = 10,
    max_length: int = 50
) -> List[Dict[str, Any]]:
    """
    Generate synthetic queries for a chunk.
    
    Args:
        chunk_text: The chunk text
        chunk_id: The chunk ID
        query_style: Style of queries ('technical', 'academic', 'clinical', 'general', etc.)
        num_queries: Number of queries to generate
        min_length: Minimum query length
        max_length: Maximum query length
        
    Returns:
        List of query dictionaries with 'query' and 'expected_chunk_id'
    """
    if not chunk_text or len(chunk_text.strip()) < 50:
        return []
    
    # For Phase 1, use a simple template-based approach
    # In Phase 2, we can use LLM-based generation
    
    queries = []
    
    # Simple template-based generation (can be enhanced with LLM later)
    if query_style == "technical":
        queries = _generate_technical_queries(chunk_text, num_queries)
    elif query_style == "academic":
        queries = _generate_academic_queries(chunk_text, num_queries)
    elif query_style == "clinical":
        queries = _generate_clinical_queries(chunk_text, num_queries)
    else:
        queries = _generate_general_queries(chunk_text, num_queries)
    
    # Filter by length
    filtered_queries = []
    for q in queries:
        if min_length <= len(q) <= max_length:
            filtered_queries.append({
                "query": q,
                "expected_chunk_id": chunk_id,
                "query_style": query_style
            })
    
    return filtered_queries[:num_queries]


def _generate_technical_queries(chunk_text: str, num: int) -> List[str]:
    """Generate technical-style queries."""
    queries = []
    sentences = [s.strip() for s in chunk_text.split('.') if s.strip() and len(s.strip()) > 20]
    
    for sentence in sentences[:num]:
        # Extract key terms and create question
        words = sentence.split()
        if len(words) > 5:
            # Create "What is X?" or "How does X work?" style queries
            key_terms = [w for w in words if w[0].isupper() or w.lower() in ['api', 'sdk', 'cli', 'config']]
            if key_terms:
                query = f"What is {key_terms[0]}?"
            else:
                query = f"How does {words[0]} work?"
            queries.append(query)
    
    return queries


def _generate_academic_queries(chunk_text: str, num: int) -> List[str]:
    """Generate academic-style queries."""
    queries = []
    sentences = [s.strip() for s in chunk_text.split('.') if s.strip() and len(s.strip()) > 30]
    
    for sentence in sentences[:num]:
        words = sentence.split()
        if len(words) > 8:
            # Create "What are the findings on X?" style queries
            key_terms = [w for w in words if w[0].isupper()]
            if key_terms:
                query = f"What are the findings on {key_terms[0]}?"
            else:
                query = f"What does the research show about {words[3] if len(words) > 3 else words[0]}?"
            queries.append(query)
    
    return queries


def _generate_clinical_queries(chunk_text: str, num: int) -> List[str]:
    """Generate clinical-style queries."""
    queries = []
    sentences = [s.strip() for s in chunk_text.split('.') if s.strip() and len(s.strip()) > 25]
    
    for sentence in sentences[:num]:
        words = sentence.split()
        if len(words) > 6:
            # Create "What is the treatment for X?" style queries
            medical_terms = [w for w in words if w.lower() in ['patient', 'diagnosis', 'treatment', 'medication', 'dose']]
            if medical_terms:
                query = f"What is the {medical_terms[0]}?"
            else:
                query = f"What are the clinical indications?"
            queries.append(query)
    
    return queries


def _generate_general_queries(chunk_text: str, num: int) -> List[str]:
    """Generate general-style queries."""
    queries = []
    sentences = [s.strip() for s in chunk_text.split('.') if s.strip() and len(s.strip()) > 20]
    
    for sentence in sentences[:num]:
        words = sentence.split()
        if len(words) > 5:
            query = f"What is {words[0]}?"
            queries.append(query)
    
    return queries

