"""
Question types for RAG evaluation.

Defines the taxonomy of question types used in evaluation datasets.
"""

from enum import Enum


class QuestionType(str, Enum):
    """Question type taxonomy for RAG evaluation."""

    FACTUAL = "factual"  # Direct factual lookup questions
    SUMMARIZATION = "summarization"  # Questions requiring summarization
    POLICY = "policy"  # Policy/compliance questions
    SYNTHESIS = "synthesis"  # Multi-document synthesis questions
    ADVERSARIAL = "adversarial"  # Adversarial questions (hallucination traps, missing context)
    COMPARISON = "comparison"  # Comparison questions
    CAUSAL = "causal"  # Causal reasoning questions
    TEMPORAL = "temporal"  # Time-based questions


class DatasetType(str, Enum):
    """Evaluation dataset types."""

    GOLDEN_QA = "golden_qa"  # Golden Q/A pairs with expected answers
    GOLDEN_RETRIEVAL = "golden_retrieval"  # Golden retrieval sets (expected docs/chunks)
    ADVERSARIAL = "adversarial"  # Adversarial test cases


class MetricType(str, Enum):
    """RAG quality metric types."""

    GROUNDEDNESS = "groundedness"  # Answer supported by evidence
    RELEVANCE = "relevance"  # Context and answer relevance
    CITATION_COVERAGE = "citation_coverage"  # Citations present and correct
    REFUSAL_CORRECTNESS = "refusal_correctness"  # Correct refusal when appropriate
    HALLUCINATION_RATE = "hallucination_rate"  # Rate of unsupported claims
    ACL_LEAKAGE = "acl_leakage"  # ACL violations in responses




