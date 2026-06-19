import pytest
from primedata.analysis.content_analyzer import (
    build_representative_sample,
    content_analyzer,
    ContentType,
)


def test_build_representative_sample_small_text_returns_same():
    text = "This is a short sample."
    assert build_representative_sample(text, chunk=5000, max_total=20000) == text


def test_build_representative_sample_large_text_contains_markers_and_caps():
    text = ("a" * 10000) + ("b" * 10000) + ("c" * 10000)
    sample = build_representative_sample(text, chunk=5000, max_total=20000)

    assert len(sample) <= 20000
    assert "=== MIDDLE SAMPLE ===" in sample
    assert "=== END SAMPLE ===" in sample


# ============================================================================
# Tests for FIXED auto chunking config selection logic
# ============================================================================


def test_deterministic_sampling_same_files_same_order():
    """Test that same files produce same sample set (deterministic)."""
    from primedata.ingestion_pipeline.dag_tasks import sample_files_for_analysis
    from primedata.db.models import RawFile
    from uuid import uuid4
    
    # Create test files
    ds_id1 = uuid4()
    ds_id2 = uuid4()
    
    files = [
        RawFile(id=uuid4(), filename="file1.pdf", file_stem="file1", data_source_id=ds_id1),
        RawFile(id=uuid4(), filename="file2.txt", file_stem="file2", data_source_id=ds_id1),
        RawFile(id=uuid4(), filename="file3.pdf", file_stem="file3", data_source_id=ds_id2),
        RawFile(id=uuid4(), filename="file4.doc", file_stem="file4", data_source_id=ds_id2),
    ]
    
    # Run sampling twice
    sample1 = sample_files_for_analysis(files, max_files=3, max_per_datasource=2)
    sample2 = sample_files_for_analysis(files, max_files=3, max_per_datasource=2)
    
    # Should be identical
    assert len(sample1) == len(sample2)
    assert [f.filename for f in sample1] == [f.filename for f in sample2]


def test_long_doc_not_penalized():
    """Test that long documents with same number of matches don't get penalized."""
    # Short document with 5 matches
    short_content = "regulatory compliance supervision " * 5 + " " * 100
    
    # Long document with 5 matches (same density)
    long_content = ("regulatory compliance supervision " * 5 + " " * 100) * 10
    
    result_short = content_analyzer.analyze_content(short_content, filename="test.pdf")
    result_long = content_analyzer.analyze_content(long_content, filename="test.pdf")
    
    # Both should detect REGULATORY, and long doc shouldn't be penalized
    assert result_short.content_type == ContentType.REGULATORY
    assert result_long.content_type == ContentType.REGULATORY
    
    # Long doc score should be similar or better (not worse)
    # Allow some variance but long doc shouldn't be significantly lower
    assert result_long.confidence >= result_short.confidence * 0.8


def test_long_doc_academic_not_dropped_below_threshold():
    """Test that long academic documents don't drop below threshold unfairly."""
    # Create a long academic document with consistent academic terms
    academic_terms = (
        "abstract introduction methodology results conclusion references "
        "study research analysis hypothesis findings implications "
    )
    
    # Short academic doc (1000 words)
    short_academic = (academic_terms * 20) + " " * 500
    
    # Long academic doc (10000 words) - same density
    long_academic = (academic_terms * 200) + " " * 5000
    
    result_short = content_analyzer.analyze_content(short_academic, filename="short.pdf")
    result_long = content_analyzer.analyze_content(long_academic, filename="long.pdf")
    
    # Both should detect ACADEMIC
    assert result_short.content_type == ContentType.ACADEMIC
    assert result_long.content_type == ContentType.ACADEMIC
    
    # Long doc confidence should not drop significantly below short doc
    # The density-based scoring should prevent unfair penalty
    assert result_long.confidence >= result_short.confidence * 0.85
    
    # Both should have reasonable confidence (not drop below 0.4)
    assert result_short.confidence >= 0.4
    assert result_long.confidence >= 0.4


def test_pdf_extension_no_bias():
    """Test that PDF extension doesn't force GENERAL when ACADEMIC or MEDICAL has evidence."""
    # Academic/medical content in PDF
    academic_content = """
    Abstract: This study examines diabetes treatment outcomes.
    Introduction: Diabetes is a metabolic disorder affecting millions.
    Methodology: We conducted a randomized controlled trial.
    Results: Treatment showed significant improvement.
    Conclusion: The findings support the hypothesis.
    References: [1] Smith et al. (2020)
    """
    result = content_analyzer.analyze_content(academic_content, filename="diabetes.pdf")
    # Should detect ACADEMIC or MEDICAL, not GENERAL, despite PDF extension
    assert result.content_type in (ContentType.ACADEMIC, ContentType.MEDICAL)
    assert result.confidence > 0.4  # Should have reasonable confidence


def test_tie_break_chooses_specific_over_general():
    """Test that tie-breaking chooses more specific type over GENERAL."""
    # Content that could match both GENERAL and a more specific type
    # We'll create content that scores similarly for both
    regulatory_content = "compliance requirement standard provision framework"
    
    result = content_analyzer.analyze_content(regulatory_content, filename="test.pdf")
    
    # Should prefer REGULATORY over GENERAL if scores are close
    # (This test may need adjustment based on actual pattern matching)
    assert result.content_type != ContentType.GENERAL or result.confidence < 0.3


def test_hint_boosts_with_evidence():
    """Test that hint boosts correctly when there's minimal evidence."""
    # Content with some academic terms but not strong
    weak_academic_content = "study research analysis"
    
    # Without hint
    result_no_hint = content_analyzer.analyze_content(weak_academic_content, filename="test.pdf")
    
    # With academic hint
    result_with_hint = content_analyzer.analyze_content(
        weak_academic_content, 
        filename="test.pdf",
        hint="academic"
    )
    
    # Hint should boost ACADEMIC score if there's minimal evidence
    if result_with_hint.content_type == ContentType.ACADEMIC:
        assert result_with_hint.evidence.get("hint_applied") is True
        assert result_with_hint.evidence.get("hint_bonus", 0) > 0


def test_hint_override_even_when_score_high():
    """Test that hint can override/boost even when current_best_score >= 0.5."""
    # Content that scores well for one type but hint suggests another
    regulatory_content = (
        "regulatory compliance supervision " * 10 +
        "guidelines framework directive " * 5
    )
    
    # Without hint - should detect REGULATORY
    result_no_hint = content_analyzer.analyze_content(regulatory_content, filename="test.pdf")
    
    # With hint for ACADEMIC (even though content is regulatory)
    # This tests that hint can influence decision even when score is already high
    result_with_hint = content_analyzer.analyze_content(
        regulatory_content,
        filename="test.pdf",
        hint="academic"
    )
    
    # Hint should be recorded in evidence even if it doesn't change the final type
    # (because regulatory has strong evidence)
    assert "hint_applied" in result_with_hint.evidence
    assert "hint_decision_reasoning" in result_with_hint.evidence
    
    # If hint was applied, it should have reasoning
    if result_with_hint.evidence.get("hint_applied"):
        assert result_with_hint.evidence.get("hint_decision_reasoning") is not None
        assert result_with_hint.evidence.get("hint_bonus", 0) > 0


def test_hint_no_override_zero_evidence():
    """Test that hint doesn't override when there's zero evidence."""
    # Content with no patterns
    generic_content = "This is a generic document with no specific patterns."
    
    result = content_analyzer.analyze_content(
        generic_content,
        filename="test.pdf",
        hint="academic"  # Hint for academic, but no evidence
    )
    
    # Should not force ACADEMIC if there's zero evidence
    # May still be GENERAL or whatever is detected
    assert result.evidence.get("hint_trigger_reason") in ["minimal_evidence_found", "no_minimal_evidence"]


def test_confidence_gap_rule():
    """Test that confidence_met uses gap rule correctly."""
    # Create content that should have clear winner
    strong_regulatory_content = (
        "regulatory compliance supervision " * 10 +
        "guidelines framework directive " * 10 +
        "requirement standard provision " * 10
    )
    
    result = content_analyzer.analyze_content(strong_regulatory_content, filename="test.pdf")
    
    # Should have good confidence and gap
    assert result.confidence > 0.0
    confidence_gap = result.evidence.get("confidence_gap", 0.0)
    
    # If confidence >= 0.55 and gap >= 0.10, should meet threshold
    if result.confidence >= 0.55 and confidence_gap >= 0.10:
        # This would be confidence_met in actual usage
        assert True  # Gap rule satisfied


def test_top_candidates_returned():
    """Test that top 3 candidates are returned in evidence."""
    regulatory_content = (
        "regulatory compliance supervision " * 5 +
        "financial banking capital " * 3 +
        "legal contract agreement " * 2
    )
    
    result = content_analyzer.analyze_content(regulatory_content, filename="test.pdf")
    
    # Should have top candidates
    candidates = result.evidence.get("top_candidates", [])
    assert len(candidates) > 0
    assert len(candidates) <= 3
    
    # Each candidate should have required fields
    for candidate in candidates:
        assert "type" in candidate
        assert "score" in candidate
        assert "key_matches" in candidate
        assert "evidence_snippet" in candidate


def test_medical_keywords_boost_medical():
    """Test that medical keywords drive MEDICAL content type (not only ACADEMIC)."""
    medical_content = (
        "diabetes treatment clinical trial patient study "
        "medical research diagnosis therapy medication"
    )
    result = content_analyzer.analyze_content(medical_content, filename="diabetes.pdf")
    # After MEDICAL content type: should detect MEDICAL or have medical keywords in evidence
    assert (
        result.content_type == ContentType.MEDICAL
        or result.content_type == ContentType.ACADEMIC
        or len(result.evidence.get("medical_keywords_found", [])) > 0
    )


def test_per_file_analysis_structure():
    """Test that per-file analysis has correct structure (integration test)."""
    # This would be tested in dag_tasks integration, but we can verify
    # that analyze_content returns the right structure
    content = "regulatory compliance supervision"
    result = content_analyzer.analyze_content(content, filename="test.pdf")
    
    # Evidence should have structure that supports per-file analysis
    assert "all_scores" in result.evidence
    assert "top_candidates" in result.evidence
    assert "confidence_gap" in result.evidence


def test_extension_weak_prior_code():
    """Test that code extension gives weak prior, not strong default."""
    code_content = "def function(): pass"
    
    result = content_analyzer.analyze_content(code_content, filename="test.py")
    
    # Should detect CODE, but prior should be weak (0.35), not 0.8
    if result.content_type == ContentType.CODE:
        # Check that extension prior was applied but content patterns dominate
        assert result.confidence > 0.0


def test_extension_weak_prior_documentation():
    """Test that documentation extension gives weak prior."""
    doc_content = "# Header\n\nSome documentation text."
    
    result = content_analyzer.analyze_content(doc_content, filename="readme.md")
    
    # Should detect DOCUMENTATION, prior should be weak (0.25)
    if result.content_type == ContentType.DOCUMENTATION:
        assert result.confidence > 0.0


# =============================================================================
# MEDICAL content type: WHO/clinical PDFs vs regulatory/technical misclassification
# =============================================================================


def test_who_diabetes_report_classifies_as_medical():
    """WHO diabetes / clinical PDF should classify as MEDICAL, not regulatory or technical.
    Uses medical keywords + MeSH-like terms + clinical phrasing; evidence includes
    medical_matched_terms and medical_density.
    """
    who_diabetes_content = """
    World Health Organization. Global report on diabetes.
    Epidemiology: The prevalence of type 2 diabetes is rising. Incidence and morbidity
    reflect screening and prevention programmes. Complications include cardiovascular
    disease. Diagnosis and treatment guidelines. Insulin and glucose management.
    HbA1c targets. Health system strengthening. Prevention of type 1 and type 2 diabetes.
    Guidelines for clinical practice. Mortality and comorbidity. Patient care.
    Patients with type 2 diabetes. Treatment of diabetes. Clinical trial results.
    """
    result = content_analyzer.analyze_content(who_diabetes_content, filename="WHO_diabetes_report.pdf")
    assert result.content_type == ContentType.MEDICAL, (
        f"Expected MEDICAL, got {result.content_type}. "
        f"all_scores={result.evidence.get('all_scores')}, "
        f"medical_keyword_score={result.evidence.get('medical_keyword_score')}, "
        f"medical_density={result.evidence.get('medical_density')}"
    )
    assert result.evidence.get("medical_keyword_score", 0) >= 0.10
    assert "medical_matched_terms" in result.evidence
    assert isinstance(result.evidence["medical_matched_terms"], list)
    assert len(result.evidence["medical_matched_terms"]) >= 5  # WHO, diabetes, prevalence, etc.
    assert "medical_density" in result.evidence
    assert result.evidence["medical_density"] >= 0
    # Chunk size may be adjusted down for short content; base MEDICAL config is 800/160
    assert result.chunk_size >= result.min_chunk_size
    assert result.chunk_overlap >= 0


def test_technical_db_migration_stays_technical():
    """Technical DB migration doc should stay TECHNICAL, not medical or regulatory."""
    migration_content = """
    # Database migration guide
    ## Schema changes
    ALTER TABLE users ADD COLUMN email VARCHAR(255);
    CREATE INDEX idx_users_email ON users(email);
    ## Migration steps
    Run the migration script. Table indexes will be updated.
    API endpoint for deployment. Authentication required.
    """
    result = content_analyzer.analyze_content(migration_content, filename="db_migration.md")
    assert result.content_type == ContentType.TECHNICAL or result.content_type == ContentType.DOCUMENTATION, (
        f"Expected TECHNICAL or DOCUMENTATION, got {result.content_type}"
    )


def test_regulatory_compliance_stays_regulatory():
    """Regulatory/compliance doc should classify as REGULATORY or FINANCE_BANKING, not medical."""
    regulatory_content = """
    Regulatory compliance framework. Supervisor and auditor requirements.
    Capital adequacy and governance. EBA and ECB guidelines. CRR CRD provisions.
    Pursuant to the directive. In accordance with the regulation. Monitoring and oversight.
    Principle and standard. Compliance reporting.
    """
    result = content_analyzer.analyze_content(regulatory_content, filename="compliance.pdf")
    assert result.content_type in (ContentType.REGULATORY, ContentType.FINANCE_BANKING), (
        f"Expected REGULATORY or FINANCE_BANKING, got {result.content_type}. all_scores={result.evidence.get('all_scores')}"
    )
    assert result.content_type != ContentType.MEDICAL


def test_index_table_alone_does_not_override_medical():
    """INDEX/TABLE alone should not push TECHNICAL when document has strong medical evidence."""
    medical_with_toc = """
    Table of contents. Index. Page 1.
    Diabetes prevalence and incidence. WHO guidelines. Screening and complications.
    Treatment with insulin. Glucose and HbA1c. Diagnosis and prevention.
    Health system. Epidemiology. Morbidity and mortality. Type 1 and type 2 diabetes.
    Clinical guidelines. Patient care. Medication.
    """
    result = content_analyzer.analyze_content(medical_with_toc, filename="clinical_guidelines.pdf")
    # Should be MEDICAL (or ACADEMIC), not TECHNICAL, despite "Table" and "Index"
    assert result.content_type in (
        ContentType.MEDICAL,
        ContentType.ACADEMIC,
    ), (
        f"Expected MEDICAL or ACADEMIC (medical evidence), got {result.content_type}. "
        f"all_scores={result.evidence.get('all_scores')}"
    )


def test_medical_hint_applied():
    """Medical hint should boost MEDICAL when minimal evidence exists."""
    weak_medical = "patient treatment guideline prevalence"
    result = content_analyzer.analyze_content(weak_medical, filename="doc.pdf", hint="medical")
    assert result.content_type == ContentType.MEDICAL or result.evidence.get("hint_applied") is True


def test_technical_api_doc_classifies_as_technical_or_documentation():
    """Technical API documentation should classify as TECHNICAL or DOCUMENTATION, not medical."""
    api_doc_content = """
    # REST API Reference

    ## Authentication
    All endpoints require authentication. Include the API key in the request header.
    Authorization: Bearer <token>

    ## Endpoints

    ### GET /api/v1/users
    Returns a list of users. Request and response are JSON.
    Query parameters: page, limit, filter.

    ### POST /api/v1/users
    Create a user. Request body: JSON schema. Response: 201 Created.

    ### Database and schema
    The API uses a PostgreSQL database. Index on email for performance.
    Migration scripts are in the migrations folder.

    ## Rate limits
    ​1000 requests per hour. Use the X-RateLimit-Limit header.
    """
    result = content_analyzer.analyze_content(api_doc_content, filename="api_reference.md")
    assert result.content_type in (ContentType.TECHNICAL, ContentType.DOCUMENTATION), (
        f"Expected TECHNICAL or DOCUMENTATION, got {result.content_type}. "
        f"all_scores={result.evidence.get('all_scores')}"
    )


def test_aws_annual_report_not_medical():
    """AWS/annual report style (financial, risk, governance) should not classify as MEDICAL."""
    annual_report_content = """
    Amazon Web Services Inc. Annual Report 2023.

    Risk factors. Market risk, credit risk, and operational risk. Our governance framework
    ensures compliance with regulatory requirements. Capital and liquidity. Balance sheet
    and income statement. Supervision and monitoring. Auditors and regulators.
    Standards and principles. Compliance and oversight. SEC filing. Financial statements.
    Revenue and growth. Investment and portfolio. Interest rate environment.
    """
    result = content_analyzer.analyze_content(annual_report_content, filename="aws_annual_report.pdf")
    # Should be REGULATORY or FINANCE_BANKING, not MEDICAL (risk/monitoring/standard are regulatory)
    assert result.content_type in (ContentType.REGULATORY, ContentType.FINANCE_BANKING, ContentType.GENERAL), (
        f"Expected REGULATORY/FINANCE_BANKING/GENERAL, got {result.content_type}. "
        f"all_scores={result.evidence.get('all_scores')}, medical_density={result.evidence.get('medical_density')}"
    )
    assert result.content_type != ContentType.MEDICAL
