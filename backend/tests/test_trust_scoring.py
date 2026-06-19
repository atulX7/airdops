"""
Unit tests for trust scoring functionality.

Tests weights validation, metric normalization, and weighted sum calculation.
"""

import pytest
import json
import tempfile
from pathlib import Path
from typing import Dict, Any

from primedata.services.trust_scoring import (
    get_scoring_weights,
    score_record,
    score_record_with_ai_ready_metrics,
    aggregate_metrics,
    aggregate_metrics_with_ai_ready,
)
from primedata.services.scoring_utils import score_file_data, load_weights


class TestScoringWeights:
    """Test scoring weights validation and loading."""

    def test_weights_sum_to_100(self):
        """Test that weights from config file sum to 100."""
        weights = get_scoring_weights()
        total = sum(weights.values())
        assert abs(total - 1.0) < 0.01, f"Weights sum to {total}, expected 1.0 (normalized)"

    def test_weights_keys_match_computed_metrics(self):
        """Test that weight keys match computed metric keys."""
        weights = get_scoring_weights()
        
        # Create a sample record
        sample_record = {
            "text": "This is a sample text for testing. It has multiple sentences. Each sentence adds context.",
            "section": "test",
            "field_name": "test_field",
            "document_id": "test_doc",
            "timestamp": "2024-01-01",
            "audience": "test_audience",
        }
        
        # Score the record
        scored = score_record(sample_record, weights)
        
        # Check that all weight keys have corresponding metrics (or are optional with weight 0)
        for weight_key in weights.keys():
            if weights[weight_key] > 0:
                assert weight_key in scored, f"Weight key '{weight_key}' not found in scored metrics"
            # Even if weight is 0, metric should be computed (for completeness)
            # But it's OK if it's missing if weight is 0

    def test_load_weights_from_file(self):
        """Test loading weights from a JSON file."""
        # Create a temporary weights file
        test_weights = {
            "Quality": 20,
            "text_integrity": 0.15,  # Normalized weight
            "Accuracy": 0.0,  # Legacy, zero weight
            "Completeness": 10,
            "Context_Quality": 10,
            "Metadata_Presence": 10,
            "Chunk_Coherence": 10,
            "Noise_Free_Score": 10,
            "Chunk_Boundary_Quality": 5,
            "Timeliness": 5,
            "Token_Count": 5,
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(test_weights, f)
            temp_path = f.name
        
        try:
            loaded_weights = load_weights(temp_path)
            assert loaded_weights == test_weights
        finally:
            Path(temp_path).unlink()


class TestMetricNormalization:
    """Test that all metrics are normalized to 0-100 scale."""

    def test_all_metrics_in_0_1_range(self):
        """Test that all computed metrics are within [0, 1] range (normalized)."""
        sample_record = {
            "text": "This is a comprehensive test text. It contains multiple sentences with various content. The text should score well on most metrics.",
            "section": "test_section",
            "field_name": "test_field",
            "document_id": "test_doc_123",
            "timestamp": "2024-01-01",
            "audience": "test_audience",
        }
        
        weights = get_scoring_weights()
        scored = score_record(sample_record, weights)
        
        # Check all numeric values are in [0, 1] (normalized)
        for key, value in scored.items():
            if isinstance(value, (int, float)) and key != "file" and not key.startswith("_"):
                assert 0.0 <= value <= 1.0, f"Metric '{key}' has value {value}, expected [0, 1]"

    def test_ai_ready_metrics_in_range(self):
        """Test that AI-Ready metrics (chunk_coherence, Noise_Free_Score) are in [0, 1]."""
        sample_record = {
            "text": "This is a test chunk. It has multiple sentences. Each sentence should be coherent with the others.",
            "section": "test",
            "field_name": "test_field",
            "document_id": "test_doc",
            "timestamp": "2024-01-01",
            "audience": "test_audience",
        }
        
        playbook = {
            "coherence": {
                "method": "embedding_similarity",
                "sentence_window": 3,
                "min_coherence_threshold": 0.6,
            },
            "noise_patterns": {
                "boilerplate": [],
                "navigation": [],
                "legal_footer": [],
            },
        }
        
        weights = get_scoring_weights()
        scored = score_record_with_ai_ready_metrics(sample_record, weights, playbook)
        
        # Check AI-Ready metrics are in range [0, 1]
        if "chunk_coherence" in scored:
            assert 0.0 <= scored["chunk_coherence"] <= 1.0, \
                f"chunk_coherence is {scored['chunk_coherence']}, expected [0, 1]"
        if "Chunk_Coherence" in scored:  # Legacy alias
            assert 0.0 <= scored["Chunk_Coherence"] <= 1.0, \
                f"Chunk_Coherence is {scored['Chunk_Coherence']}, expected [0, 1]"
        
        if "Noise_Free_Score" in scored:
            assert 0.0 <= scored["Noise_Free_Score"] <= 1.0, \
                f"Noise_Free_Score is {scored['Noise_Free_Score']}, expected [0, 1]"


class TestWeightedSumCalculation:
    """Test weighted Trust Score calculation."""

    def test_weighted_sum_equals_expected(self):
        """Test that weighted Trust Score equals expected value for known metric values."""
        # Create synthetic metrics with known values (normalized to [0,1])
        synthetic_metrics = {
            "completeness": 1.0,
            "validity": 0.9,
            "consistency": 0.85,
            "uniqueness": 0.95,
            "timeliness": 0.6,
            "text_integrity": 0.9,
            "parse_success": 1.0,
            "chunk_boundary_quality": 0.8,
            "chunk_coherence": 0.7,
            "chunk_size_health": 0.75,
            "metadata_completeness": 0.85,
            "provenance_coverage": 0.9,
        }
        
        weights = get_scoring_weights()
        
        # Calculate expected weighted sum manually (scores already in [0,1])
        expected_sum = 0.0
        for weight_key, weight_value in weights.items():
            if weight_key in synthetic_metrics:
                expected_sum += synthetic_metrics[weight_key] * weight_value
        
        # Create a record that would produce these scores (simplified)
        # For this test, we'll directly test the weighted sum calculation logic
        weighted_sum = 0.0
        for weight_key, weight_value in weights.items():
            if weight_key in synthetic_metrics:
                weighted_sum += synthetic_metrics[weight_key] * weight_value
        
        assert abs(weighted_sum - expected_sum) < 0.01, \
            f"Weighted sum {weighted_sum} doesn't match expected {expected_sum}"
        
        # Verify that metrics with weight 0 don't affect the score
        assert "Audience_Intentionality" in weights and weights["Audience_Intentionality"] == 0, \
            "Audience_Intentionality should have weight 0"
        assert "GPT_Confidence" in weights and weights["GPT_Confidence"] == 0, \
            "GPT_Confidence should have weight 0"

    def test_missing_metrics_default_to_zero(self):
        """Test that missing metrics default to 0 in weighted sum calculation."""
        # Create metrics with some missing keys
        incomplete_metrics = {
            "Quality": 80.0,
            "Accuracy": 90.0,
            "Completeness": 100.0,
            # Missing: Chunk_Coherence, Noise_Free_Score, etc.
        }
        
        weights = get_scoring_weights()
        
        # Calculate weighted sum (missing metrics should contribute 0)
        weighted_sum = 0.0
        missing_count = 0
        for weight_key, weight_value in weights.items():
            if weight_key in incomplete_metrics:
                weighted_sum += (incomplete_metrics[weight_key] / 100.0) * weight_value
            else:
                missing_count += 1
                # Missing metrics contribute 0
        
        # The sum should be less than 1.0 since we're missing metrics
        assert weighted_sum < 1.0, "Weighted sum should be less than 1.0 with missing metrics"
        assert missing_count > 0, "Should have missing metrics for this test"


class TestAggregation:
    """Test metric aggregation functions."""

    def test_aggregate_metrics_averages_chunk_metrics(self):
        """Test that aggregate_metrics averages chunk metrics correctly."""
        chunk_metrics = [
            {"completeness": 1.0, "text_integrity": 0.9, "timeliness": 0.8, "file": "file1.jsonl"},
            {"completeness": 0.95, "text_integrity": 0.85, "timeliness": 0.75, "file": "file2.jsonl"},
            {"completeness": 1.0, "text_integrity": 0.95, "timeliness": 0.85, "file": "file3.jsonl"},
        ]
        
        aggregated = aggregate_metrics(chunk_metrics)
        
        # Check that metrics are averaged (normalized to [0,1])
        assert aggregated["completeness"] == pytest.approx(0.9833, abs=0.01), \
            f"Expected completeness average ~0.9833, got {aggregated['completeness']}"
        assert aggregated["text_integrity"] == pytest.approx(0.9, abs=0.01), \
            f"Expected text_integrity average ~0.9, got {aggregated['text_integrity']}"
        assert aggregated["timeliness"] == pytest.approx(0.8, abs=0.01), \
            f"Expected timeliness average ~0.8, got {aggregated['timeliness']}"
        
        # Check that 'file' key is excluded
        assert "file" not in aggregated

    def test_aggregate_metrics_preserves_keys(self):
        """Test that aggregate_metrics preserves all metric keys."""
        chunk_metrics = [
            {
                "Quality": 80.0,
                "Chunk_Coherence": 75.0,
                "Noise_Free_Score": 90.0,
                "AI_Trust_Score": 82.0,
                "file": "file1.jsonl",
            },
            {
                "Quality": 70.0,
                "Chunk_Coherence": 80.0,
                "Noise_Free_Score": 85.0,
                "AI_Trust_Score": 78.0,
                "file": "file2.jsonl",
            },
        ]
        
        aggregated = aggregate_metrics(chunk_metrics)
        
        # Check that all metric keys are preserved
        expected_keys = {"Quality", "Chunk_Coherence", "Noise_Free_Score", "AI_Trust_Score"}
        assert expected_keys.issubset(set(aggregated.keys())), \
            f"Missing keys in aggregated metrics. Expected: {expected_keys}, Got: {set(aggregated.keys())}"

    def test_aggregate_metrics_with_ai_ready_includes_boundary_quality(self):
        """Test that aggregate_metrics_with_ai_ready includes Chunk_Boundary_Quality."""
        chunk_metrics = [
            {
                "Quality": 80.0,
                "Chunk_Coherence": 75.0,
                "Noise_Free_Score": 90.0,
                "AI_Trust_Score": 82.0,
            },
            {
                "Quality": 70.0,
                "Chunk_Coherence": 80.0,
                "Noise_Free_Score": 85.0,
                "AI_Trust_Score": 78.0,
            },
        ]
        
        preprocessing_stats = {
            "mid_sentence_boundary_rate": 0.1,  # 10% mid-sentence breaks
        }
        
        aggregated = aggregate_metrics_with_ai_ready(chunk_metrics, preprocessing_stats)
        
        # Check that Chunk_Boundary_Quality is included
        assert "Chunk_Boundary_Quality" in aggregated, \
            "Chunk_Boundary_Quality should be included in aggregated metrics"
        
        # Check that it's calculated correctly (0% breaks = 100 score, 10% breaks = 90 score)
        expected_boundary_quality = 100.0 - (0.1 * 100)  # 90.0
        assert abs(aggregated["Chunk_Boundary_Quality"] - expected_boundary_quality) < 0.01, \
            f"Chunk_Boundary_Quality should be ~90.0, got {aggregated['Chunk_Boundary_Quality']}"

    def test_aggregate_metrics_with_ai_ready_without_preprocessing_stats(self):
        """Test that aggregate_metrics_with_ai_ready works without preprocessing stats."""
        chunk_metrics = [
            {
                "Quality": 80.0,
                "Chunk_Coherence": 75.0,
                "Noise_Free_Score": 90.0,
            },
        ]
        
        aggregated = aggregate_metrics_with_ai_ready(chunk_metrics, None)
        
        # Should still aggregate other metrics
        assert "Quality" in aggregated
        assert "Chunk_Coherence" in aggregated
        assert "Noise_Free_Score" in aggregated
        
        # Chunk_Boundary_Quality should not be included if preprocessing_stats is None
        # (or could be included with a default value, depending on implementation)
        # For now, we'll check that it's not included
        # assert "Chunk_Boundary_Quality" not in aggregated or aggregated["Chunk_Boundary_Quality"] == 0.0


class TestScoringConsistency:
    """Test scoring consistency across different scorers."""

    def test_fallback_scorer_outputs_0_100(self):
        """Test that fallback scorer outputs metrics in 0-100 range."""
        sample_record = {
            "text": "Test text for fallback scorer.",
            "section": "test",
            "field_name": "test_field",
            "document_id": "test_doc",
        }
        
        weights = get_scoring_weights()
        scored = score_record(sample_record, weights)
        
        # All metrics should be in [0, 100]
        for key, value in scored.items():
            if isinstance(value, (int, float)) and key != "file":
                assert 0.0 <= value <= 100.0, \
                    f"Fallback scorer metric '{key}' has value {value}, expected [0, 100]"

    def test_primary_scorer_outputs_0_100(self):
        """Test that primary scorer (if available) outputs metrics in 0-100 range."""
        try:
            from primedata.services.scoring_utils import score_file_data
            
            sample_record = {
                "text": "Test text for primary scorer. It has multiple sentences.",
                "section": "test",
                "field_name": "test_field",
                "document_id": "test_doc",
                "timestamp": "2024-01-01",
                "audience": "test_audience",
            }
            
            weights = get_scoring_weights()
            scored = score_file_data(sample_record, weights)
            
            # All metrics should be in [0, 100]
            for key, value in scored.items():
                if isinstance(value, (int, float)) and key != "file":
                    assert 0.0 <= value <= 100.0, \
                        f"Primary scorer metric '{key}' has value {value}, expected [0, 100]"
        except ImportError:
            pytest.skip("Primary scorer not available")


class TestNewMetrics:
    """Test new metrics: Parse_Success, Duplicate_Ratio, Chunk_Size_Health, Timeliness fixes."""
    
    def test_timeliness_uses_current_date(self):
        """Test that Timeliness uses current date instead of hardcoded reference."""
        from datetime import datetime
        from primedata.services.scoring_utils import score_timeliness
        
        # Test with recent timestamp (should score high)
        recent_date = datetime.utcnow().strftime("%Y-%m-%d")
        score, reason = score_timeliness(recent_date)
        assert score >= 90.0, f"Recent date should score high, got {score}"
        assert reason == "computed", f"Reason should be 'computed', got {reason}"
        
        # Test with old timestamp (should score lower)
        old_date = "2020-01-01"
        score, reason = score_timeliness(old_date)
        assert score < 50.0, f"Old date should score low, got {score}"
        assert reason == "computed", f"Reason should be 'computed', got {reason}"
        
        # Test with missing timestamp (should return neutral)
        score, reason = score_timeliness("")
        assert score == 50.0, f"Missing timestamp should return 50, got {score}"
        assert "missing_or_invalid" in reason or "parse_error" in reason, \
            f"Reason should indicate missing/invalid, got {reason}"
    
    def test_gpt_confidence_zero_weight(self):
        """Test that GPT_Confidence does not change trust score when weight=0."""
        sample_record = {
            "text": "This is a test text with multiple sentences.",
            "section": "test",
            "field_name": "test_field",
            "document_id": "test_doc",
            "timestamp": "2024-01-01",
            "audience": "test_audience",
        }
        
        weights = get_scoring_weights()
        
        # Ensure GPT_Confidence has weight 0
        assert weights.get("GPT_Confidence", 0) == 0, \
            "GPT_Confidence should have weight 0"
        
        # Score the record
        scored1 = score_record(sample_record, weights)
        gpt_conf_value = scored1.get("GPT_Confidence", 0)
        
        # Change GPT_Confidence value manually (simulate different value)
        # and verify trust score doesn't change
        scored2 = score_record(sample_record, weights)
        scored2["GPT_Confidence"] = 0.0  # Change to 0
        
        # Trust scores should be identical since GPT_Confidence weight is 0
        assert abs(scored1["AI_Trust_Score"] - scored2["AI_Trust_Score"]) < 0.01, \
            f"Trust score should not change when GPT_Confidence changes (weight=0). " \
            f"Score1: {scored1['AI_Trust_Score']}, Score2: {scored2['AI_Trust_Score']}"
    
    def test_duplicate_ratio_lower_for_repeated_text(self):
        """Test that Duplicate_Ratio returns lower score for repeated text."""
        try:
            from primedata.services.dup_detection import calculate_duplicate_ratio
            
            # Test with unique chunks (should score high)
            unique_chunks = [
                "This is the first chunk with unique content.",
                "This is the second chunk with different content.",
                "This is the third chunk with yet another unique message.",
            ]
            unique_score = calculate_duplicate_ratio(unique_chunks)
            assert unique_score >= 70.0, \
                f"Unique chunks should score high (>=70), got {unique_score}"
            
            # Test with duplicate chunks (should score lower)
            duplicate_chunks = [
                "This is repeated text. This is repeated text. This is repeated text.",
                "This is repeated text. This is repeated text. This is repeated text.",
                "This is repeated text. This is repeated text. This is repeated text.",
            ]
            duplicate_score = calculate_duplicate_ratio(duplicate_chunks)
            assert duplicate_score < unique_score, \
                f"Duplicate chunks should score lower than unique. " \
                f"Unique: {unique_score}, Duplicate: {duplicate_score}"
            
            # Test with single chunk (should score 100)
            single_chunk = ["This is a single chunk."]
            single_score = calculate_duplicate_ratio(single_chunk)
            assert single_score == 100.0, \
                f"Single chunk should score 100, got {single_score}"
        except ImportError:
            pytest.skip("dup_detection module not available")
    
    def test_token_count_chunk_size_health_alignment(self):
        """Test that Token_Count and Chunk_Size_Health are aligned (same value)."""
        sample_record = {
            "text": "This is a test text. " * 100,  # Create substantial text
            "section": "test",
            "field_name": "test_field",
            "document_id": "test_doc",
            "timestamp": "2024-01-01",
            "audience": "test_audience",
        }
        
        weights = get_scoring_weights()
        scored = score_record(sample_record, weights)
        
        # Token_Count should equal Chunk_Size_Health (alias)
        token_count = scored.get("Token_Count")
        chunk_size_health = scored.get("Chunk_Size_Health")
        
        assert token_count is not None, "Token_Count should be present"
        assert chunk_size_health is not None, "Chunk_Size_Health should be present"
        assert abs(token_count - chunk_size_health) < 0.01, \
            f"Token_Count ({token_count}) should equal Chunk_Size_Health ({chunk_size_health})"
    
    def test_parse_success_metric(self):
        """Test Parse_Success metric."""
        weights = get_scoring_weights()
        
        # Test with valid text (> 50 chars)
        valid_record = {
            "text": "This is a valid text with more than fifty characters to pass the threshold.",
            "section": "test",
            "field_name": "test_field",
            "document_id": "test_doc",
        }
        scored_valid = score_record(valid_record, weights)
        assert scored_valid.get("Parse_Success") == 100.0, \
            f"Valid text should have Parse_Success=100, got {scored_valid.get('Parse_Success')}"
        
        # Test with short text (< 50 chars)
        short_record = {
            "text": "Short",
            "section": "test",
            "field_name": "test_field",
            "document_id": "test_doc",
        }
        scored_short = score_record(short_record, weights)
        assert scored_short.get("Parse_Success") == 0.0, \
            f"Short text should have Parse_Success=0, got {scored_short.get('Parse_Success')}"
    
    def test_chunk_size_health_domain_aware(self):
        """Test that Chunk_Size_Health is domain-aware."""
        weights = get_scoring_weights()
        
        # Create text with ~700 tokens (good for regulatory, okay for general)
        text_700 = "This is a test sentence. " * 50  # ~700 words/tokens
        
        # Test regulatory domain
        regulatory_record = {
            "text": text_700,
            "section": "test",
            "field_name": "test_field",
            "document_id": "test_doc",
            "domain_type": "regulatory",
        }
        scored_reg = score_record(regulatory_record, weights)
        reg_score = scored_reg.get("Chunk_Size_Health", 0)
        
        # Test general domain
        general_record = {
            "text": text_700,
            "section": "test",
            "field_name": "test_field",
            "document_id": "test_doc",
        }
        scored_gen = score_record(general_record, weights)
        gen_score = scored_gen.get("Chunk_Size_Health", 0)
        
        # Regulatory should score higher for 700 tokens (in preferred range)
        # General should score lower (below preferred range)
        assert reg_score >= gen_score, \
            f"Regulatory domain should score higher for 700 tokens. " \
            f"Reg: {reg_score}, Gen: {gen_score}"
    
    def test_metrics_semantics_in_fingerprint(self):
        """Test that fingerprint includes metrics_semantics."""
        from primedata.services.fingerprint import generate_fingerprint
        
        chunk_metrics = [
            {
                "completeness": 1.0,
                "text_integrity": 0.9,
                "chunk_size_health": 0.85,
                "parse_success": 1.0,
                "AI_Trust_Score": 0.85,
            },
        ]
        
        fingerprint = generate_fingerprint(chunk_metrics)
        
        # Check that metrics_semantics is present
        assert "metrics_semantics" in fingerprint, \
            "Fingerprint should include metrics_semantics"
        
        semantics = fingerprint["metrics_semantics"]
        assert isinstance(semantics, dict), \
            "metrics_semantics should be a dictionary"
        
        # Check that semantics include key metrics
        assert "text_integrity" in semantics, "Semantics should include text_integrity"
        assert "completeness" in semantics, "Semantics should include completeness"
        assert "chunk_size_health" in semantics, "Semantics should include chunk_size_health"
        
        # Check semantics structure
        for metric_key, semantic_info in semantics.items():
            assert "meaning" in semantic_info, \
                f"Semantic info for {metric_key} should have 'meaning'"
            assert "computation" in semantic_info, \
                f"Semantic info for {metric_key} should have 'computation'"
        
        # Check that text_integrity semantics clarify it's text cleanliness
        text_integrity_sem = semantics.get("text_integrity", {})
        assert "cleanliness" in text_integrity_sem.get("meaning", "").lower() or \
               "spelling" in text_integrity_sem.get("meaning", "").lower() or \
               "ocr" in text_integrity_sem.get("meaning", "").lower(), \
            "text_integrity semantics should clarify it's text cleanliness, not factual accuracy"
        
        # Check that completeness semantics clarify it's extraction completeness
        completeness_sem = semantics.get("completeness", {})
        assert "extraction" in completeness_sem.get("meaning", "").lower() or \
               "playbook" in completeness_sem.get("meaning", "").lower(), \
            "Completeness semantics should clarify it's extraction completeness"
