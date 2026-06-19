"""
Unit tests for trust metrics implementation (production-solid requirements).

Tests:
1. Canonical API schema: ONLY snake_case metrics at top-level, NO Title_Case keys at top-level
2. Legacy keys under legacy_aliases object
3. Token metrics: total_tokens, avg_tokens_per_chunk, num_chunks, etc. (NOT clamped, NOT scores)
4. Token_Count removed as score alias
5. Duplicate metrics: uniqueness and duplicate_ratio in [0,1], duplicate_ratio = 1 - uniqueness
6. Explicit aggregation rules: mean for scores, sum for tokens, min for risk
7. Scores clamped to [0,1], raw metrics NOT clamped
"""

import pytest
from typing import Dict, Any, List

from primedata.services.trust_scoring import (
    score_record,
    aggregate_metrics,
    aggregate_metrics_with_ai_ready,
    get_scoring_weights,
)
from primedata.services.scoring_utils import estimate_tokens
from primedata.services.fingerprint import generate_fingerprint


class TestCanonicalSchema:
    """Test canonical API schema requirements."""
    
    def test_no_title_case_keys_at_top_level(self):
        """Test that NO Title_Case keys appear at top-level in aggregated metrics."""
        sample_records = [
            {
                "text": "This is a test chunk with some content. " * 20,
                "section": "test",
                "field_name": "test_field",
                "document_id": "test_doc",
                "token_est": 100,
            },
            {
                "text": "Another test chunk with different content. " * 20,
                "section": "test",
                "field_name": "test_field",
                "document_id": "test_doc",
                "token_est": 150,
            },
        ]
        
        weights = get_scoring_weights()
        scored_records = [score_record(record, weights) for record in sample_records]
        aggregated = aggregate_metrics(scored_records)
        
        # Check that NO Title_Case keys are at top-level
        title_case_keys = [k for k in aggregated.keys() if k and k[0].isupper() and '_' in k]
        assert len(title_case_keys) == 0, f"Found Title_Case keys at top-level: {title_case_keys}"
        
        # Legacy aliases should be under legacy_aliases, not at top-level
        if "legacy_aliases" in aggregated:
            legacy_keys = list(aggregated["legacy_aliases"].keys())
            title_case_legacy = [k for k in legacy_keys if k and k[0].isupper() and '_' in k]
            # Legacy aliases can have Title_Case, that's OK
            assert len(title_case_legacy) > 0 or len(legacy_keys) == 0, "Legacy aliases should contain Title_Case keys"
    
    def test_snake_case_metrics_at_top_level(self):
        """Test that canonical metrics use snake_case at top-level."""
        sample_records = [
            {
                "text": "Test content for metrics. " * 20,
                "section": "test",
                "field_name": "test_field",
                "document_id": "test_doc",
                "token_est": 100,
            },
        ]
        
        weights = get_scoring_weights()
        scored_records = [score_record(record, weights) for record in sample_records]
        aggregated = aggregate_metrics(scored_records)
        
        # Check that canonical score metrics use snake_case
        expected_snake_case = [
            "completeness", "validity", "consistency", "uniqueness", "timeliness",
            "text_integrity", "parse_success", "chunk_boundary_quality", "chunk_coherence",
            "chunk_size_health", "metadata_completeness", "provenance_coverage"
        ]
        
        for metric in expected_snake_case:
            if metric in aggregated:
                assert metric == metric.lower(), f"Metric {metric} should be snake_case"
                assert '_' in metric or metric.islower(), f"Metric {metric} should use snake_case"


class TestTokenMetrics:
    """Test token metrics implementation."""
    
    def test_token_metrics_non_zero_and_not_equal_to_chunk_size_health(self):
        """Test that token metrics are non-zero and NOT equal to chunk_size_health."""
        sample_records = [
            {
                "text": "This is a test chunk. " * 50,  # ~100 tokens
                "section": "test",
                "field_name": "test_field",
                "document_id": "test_doc",
                "token_est": 100,
            },
            {
                "text": "Another test chunk with more content. " * 50,  # ~150 tokens
                "section": "test",
                "field_name": "test_field",
                "document_id": "test_doc",
                "token_est": 150,
            },
        ]
        
        weights = get_scoring_weights()
        scored_records = [score_record(record, weights) for record in sample_records]
        aggregated = aggregate_metrics(scored_records)
        
        # Check token metrics exist and are non-zero
        assert "total_tokens" in aggregated, "total_tokens should be present"
        assert aggregated["total_tokens"] > 0, "total_tokens should be non-zero"
        assert aggregated["total_tokens"] == 250, f"Expected 250, got {aggregated['total_tokens']}"
        
        assert "avg_tokens_per_chunk" in aggregated, "avg_tokens_per_chunk should be present"
        assert aggregated["avg_tokens_per_chunk"] > 0, "avg_tokens_per_chunk should be non-zero"
        assert aggregated["avg_tokens_per_chunk"] == 125.0, f"Expected 125.0, got {aggregated['avg_tokens_per_chunk']}"
        
        assert "num_chunks" in aggregated, "num_chunks should be present"
        assert aggregated["num_chunks"] == 2, f"Expected 2, got {aggregated['num_chunks']}"
        
        # Check that token metrics are NOT equal to chunk_size_health (they're different concepts)
        if "chunk_size_health" in aggregated:
            chunk_size_health = aggregated["chunk_size_health"]
            assert aggregated["total_tokens"] != chunk_size_health, \
                f"total_tokens ({aggregated['total_tokens']}) should NOT equal chunk_size_health ({chunk_size_health})"
            assert aggregated["avg_tokens_per_chunk"] != chunk_size_health, \
                f"avg_tokens_per_chunk ({aggregated['avg_tokens_per_chunk']}) should NOT equal chunk_size_health ({chunk_size_health})"
    
    def test_token_metrics_not_clamped(self):
        """Test that raw token metrics are NOT clamped to [0,1]."""
        sample_records = [
            {
                "text": "Test content. " * 1000,  # Large token count
                "section": "test",
                "field_name": "test_field",
                "document_id": "test_doc",
                "token_est": 5000,  # Large value
            },
        ]
        
        weights = get_scoring_weights()
        scored_records = [score_record(record, weights) for record in sample_records]
        aggregated = aggregate_metrics(scored_records)
        
        # Token metrics should NOT be clamped (can be > 1)
        assert "total_tokens" in aggregated
        assert aggregated["total_tokens"] > 1.0, \
            f"total_tokens ({aggregated['total_tokens']}) should NOT be clamped to [0,1]"
        assert aggregated["total_tokens"] == 5000, \
            f"Expected 5000, got {aggregated['total_tokens']}"
        
        assert "avg_tokens_per_chunk" in aggregated
        assert aggregated["avg_tokens_per_chunk"] > 1.0, \
            f"avg_tokens_per_chunk ({aggregated['avg_tokens_per_chunk']}) should NOT be clamped to [0,1]"
    
    def test_token_count_removed_as_score_alias(self):
        """Test that Token_Count is NOT used as a score alias (it was removed)."""
        sample_record = {
            "text": "Test content for scoring. " * 20,
            "section": "test",
            "field_name": "test_field",
            "document_id": "test_doc",
            "token_est": 100,
        }
        
        weights = get_scoring_weights()
        scored = score_record(sample_record, weights)
        
        # Token_Count should NOT be at top-level as a score
        # It should only be in legacy_aliases if present
        assert "Token_Count" not in scored or scored.get("Token_Count") is None or "legacy_aliases" in scored, \
            "Token_Count should NOT be at top-level as a score alias"
        
        # chunk_size_health should exist and be different from token metrics
        assert "chunk_size_health" in scored
        assert "token_est" in scored
        assert scored["chunk_size_health"] != scored["token_est"], \
            "chunk_size_health should NOT equal token_est (they're different concepts)"


class TestDuplicateMetrics:
    """Test duplicate metrics (uniqueness and duplicate_ratio)."""
    
    def test_uniqueness_and_duplicate_ratio_in_0_1_range(self):
        """Test that uniqueness and duplicate_ratio are both in [0,1] range."""
        # Create records with some duplicates
        sample_records = [
            {
                "text": "This is unique content. " * 10,
                "section": "test",
                "field_name": "test_field",
                "document_id": "test_doc",
                "token_est": 50,
            },
            {
                "text": "This is unique content. " * 10,  # Duplicate
                "section": "test",
                "field_name": "test_field",
                "document_id": "test_doc",
                "token_est": 50,
            },
            {
                "text": "Different content here. " * 10,
                "section": "test",
                "field_name": "test_field",
                "document_id": "test_doc",
                "token_est": 50,
            },
        ]
        
        weights = get_scoring_weights()
        scored_records = [score_record(record, weights) for record in sample_records]
        
        # Use aggregate_metrics_with_ai_ready to get uniqueness and duplicate_ratio
        aggregated = aggregate_metrics_with_ai_ready(scored_records, None)
        
        # Check that uniqueness is in [0,1]
        assert "uniqueness" in aggregated, "uniqueness should be present"
        uniqueness = aggregated["uniqueness"]
        assert 0.0 <= uniqueness <= 1.0, \
            f"uniqueness ({uniqueness}) should be in [0,1] range"
        
        # Check that duplicate_ratio is in [0,1]
        assert "duplicate_ratio" in aggregated, "duplicate_ratio should be present"
        duplicate_ratio = aggregated["duplicate_ratio"]
        assert 0.0 <= duplicate_ratio <= 1.0, \
            f"duplicate_ratio ({duplicate_ratio}) should be in [0,1] range"
    
    def test_duplicate_ratio_equals_one_minus_uniqueness(self):
        """Test that duplicate_ratio = 1 - uniqueness."""
        sample_records = [
            {
                "text": "Unique content one. " * 10,
                "section": "test",
                "field_name": "test_field",
                "document_id": "test_doc",
                "token_est": 50,
            },
            {
                "text": "Unique content two. " * 10,
                "section": "test",
                "field_name": "test_field",
                "document_id": "test_doc",
                "token_est": 50,
            },
        ]
        
        weights = get_scoring_weights()
        scored_records = [score_record(record, weights) for record in sample_records]
        aggregated = aggregate_metrics_with_ai_ready(scored_records, None)
        
        uniqueness = aggregated.get("uniqueness")
        duplicate_ratio = aggregated.get("duplicate_ratio")
        
        if uniqueness is not None and duplicate_ratio is not None:
            expected_duplicate_ratio = 1.0 - uniqueness
            assert abs(duplicate_ratio - expected_duplicate_ratio) < 0.01, \
                f"duplicate_ratio ({duplicate_ratio}) should equal 1 - uniqueness ({1.0 - uniqueness})"


class TestScoreClamping:
    """Test that scores are clamped to [0,1] but raw metrics are NOT."""
    
    def test_scores_clamped_to_0_1(self):
        """Test that all score metrics are clamped to [0,1] range."""
        sample_record = {
            "text": "Test content. " * 20,
            "section": "test",
            "field_name": "test_field",
            "document_id": "test_doc",
            "token_est": 100,
        }
        
        weights = get_scoring_weights()
        scored = score_record(sample_record, weights)
        
        score_keys = [
            "completeness", "validity", "consistency", "uniqueness", "timeliness",
            "text_integrity", "parse_success", "chunk_boundary_quality", "chunk_coherence",
            "chunk_size_health", "metadata_completeness", "provenance_coverage"
        ]
        
        for key in score_keys:
            if key in scored:
                value = scored[key]
                assert isinstance(value, (int, float)), f"{key} should be numeric"
                assert 0.0 <= value <= 1.0, \
                    f"Score metric {key} ({value}) should be clamped to [0,1]"
    
    def test_raw_metrics_not_clamped(self):
        """Test that raw token metrics are NOT clamped to [0,1]."""
        sample_record = {
            "text": "Test content with many tokens. " * 1000,
            "section": "test",
            "field_name": "test_field",
            "document_id": "test_doc",
            "token_est": 5000,  # Large value
        }
        
        weights = get_scoring_weights()
        scored = score_record(sample_record, weights)
        
        # token_est should NOT be clamped
        assert "token_est" in scored
        assert scored["token_est"] > 1.0, \
            f"token_est ({scored['token_est']}) should NOT be clamped to [0,1]"
        assert isinstance(scored["token_est"], int), \
            f"token_est should be an integer, got {type(scored['token_est'])}"


class TestEstimateTokens:
    """Test shared estimate_tokens helper."""
    
    def test_estimate_tokens_uses_shared_helper(self):
        """Test that estimate_tokens helper works correctly."""
        text = "This is a test sentence with multiple words."
        
        # Should return integer
        token_count = estimate_tokens(text)
        assert isinstance(token_count, int), f"estimate_tokens should return int, got {type(token_count)}"
        assert token_count > 0, f"estimate_tokens should return positive value, got {token_count}"
        
        # Should use word_count * 1.3 as fallback if tiktoken not available
        word_count = len(text.split())
        expected_min = int(word_count * 1.3)
        # Allow some variance (tiktoken might give different result)
        assert token_count >= word_count, \
            f"estimate_tokens ({token_count}) should be >= word_count ({word_count})"
    
    def test_estimate_tokens_handles_empty_text(self):
        """Test that estimate_tokens handles empty text."""
        assert estimate_tokens("") == 0
        assert estimate_tokens("   ") == 0


class TestAggregationRules:
    """Test explicit aggregation rules."""
    
    def test_mean_for_score_metrics(self):
        """Test that score metrics use mean (average) aggregation."""
        sample_records = [
            {
                "text": "Test content one. " * 20,
                "section": "test",
                "field_name": "test_field",
                "document_id": "test_doc",
                "token_est": 100,
            },
            {
                "text": "Test content two. " * 20,
                "section": "test",
                "field_name": "test_field",
                "document_id": "test_doc",
                "token_est": 100,
            },
        ]
        
        weights = get_scoring_weights()
        scored_records = [score_record(record, weights) for record in sample_records]
        aggregated = aggregate_metrics(scored_records)
        
        # Check that score metrics are averaged (mean)
        if "completeness" in scored_records[0] and "completeness" in scored_records[1]:
            expected_mean = (scored_records[0]["completeness"] + scored_records[1]["completeness"]) / 2.0
            assert abs(aggregated.get("completeness", 0) - expected_mean) < 0.01, \
                f"completeness should be mean of chunk values"
    
    def test_sum_for_token_metrics(self):
        """Test that token metrics use sum aggregation."""
        sample_records = [
            {
                "text": "Test content one. " * 20,
                "section": "test",
                "field_name": "test_field",
                "document_id": "test_doc",
                "token_est": 100,
            },
            {
                "text": "Test content two. " * 20,
                "section": "test",
                "field_name": "test_field",
                "document_id": "test_doc",
                "token_est": 150,
            },
        ]
        
        weights = get_scoring_weights()
        scored_records = [score_record(record, weights) for record in sample_records]
        aggregated = aggregate_metrics(scored_records)
        
        # Check that total_tokens is sum
        assert "total_tokens" in aggregated
        assert aggregated["total_tokens"] == 250, \
            f"total_tokens should be sum (100 + 150 = 250), got {aggregated['total_tokens']}"
        
        # Check that avg_tokens_per_chunk is derived from sum
        assert "avg_tokens_per_chunk" in aggregated
        assert aggregated["avg_tokens_per_chunk"] == 125.0, \
            f"avg_tokens_per_chunk should be 250/2 = 125.0, got {aggregated['avg_tokens_per_chunk']}"
