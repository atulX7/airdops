"""
Answer correctness vs golden expected answer (golden QA datasets).
"""

import numpy as np
from loguru import logger

from .scoring import MetricScore


class AnswerCorrectnessMetric:
    """Compare generated answer to expected answer (embedding or lexical overlap)."""

    def __init__(self, embedding_generator=None):
        self.embedding_generator = embedding_generator

    def evaluate(
        self,
        expected_answer: str,
        answer: str,
        threshold: float = 0.75,
    ) -> MetricScore:
        exp = (expected_answer or "").strip()
        gen = (answer or "").strip()

        if not exp:
            return MetricScore(
                metric_name="answer_correctness",
                score=0.0,
                passed=False,
                details={"skipped": True, "reason": "empty_expected_answer"},
            )

        if not gen:
            return MetricScore(
                metric_name="answer_correctness",
                score=0.0,
                passed=False,
                details={"error": "empty_generated_answer"},
            )

        if self.embedding_generator:
            try:
                vecs = self.embedding_generator.embed_batch([exp, gen])
                if vecs and len(vecs) >= 2:
                    a, b = np.asarray(vecs[0]), np.asarray(vecs[1])
                    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
                    if denom > 0:
                        sim = float(np.dot(a, b) / denom)
                        score = max(0.0, min(1.0, sim))
                    else:
                        score = self._lexical_similarity(exp, gen)
                else:
                    score = self._lexical_similarity(exp, gen)
            except Exception as e:
                logger.warning(f"Embedding answer correctness failed: {e}; using lexical fallback")
                score = self._lexical_similarity(exp, gen)
        else:
            score = self._lexical_similarity(exp, gen)

        passed = score >= threshold
        return MetricScore(
            metric_name="answer_correctness",
            score=score,
            passed=passed,
            details={
                "method": "embedding_cosine" if self.embedding_generator else "lexical",
            },
        )

    def _lexical_similarity(self, a: str, b: str) -> float:
        wa = set(a.lower().split())
        wb = set(b.lower().split())
        if not wa or not wb:
            return 0.0
        inter = len(wa & wb)
        union = len(wa | wb)
        return float(inter) / float(union) if union else 0.0
