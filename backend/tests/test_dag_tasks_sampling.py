"""
Tests for deterministic file sampling in dag_tasks.
"""
import pytest
from uuid import uuid4
from primedata.ingestion_pipeline.dag_tasks import sample_files_for_analysis
from primedata.db.models import RawFile


def test_deterministic_sampling_same_files_same_order():
    """Test that same files produce same sample set (deterministic)."""
    # Create test files with different datasources
    ds_id1 = uuid4()
    ds_id2 = uuid4()
    
    files = [
        RawFile(id=uuid4(), filename="file1.pdf", file_stem="file1", data_source_id=ds_id1),
        RawFile(id=uuid4(), filename="file2.txt", file_stem="file2", data_source_id=ds_id1),
        RawFile(id=uuid4(), filename="file3.pdf", file_stem="file3", data_source_id=ds_id2),
        RawFile(id=uuid4(), filename="file4.doc", file_stem="file4", data_source_id=ds_id2),
        RawFile(id=uuid4(), filename="file5.html", file_stem="file5", data_source_id=ds_id1),
    ]
    
    # Run sampling multiple times - should be identical
    sample1 = sample_files_for_analysis(files, max_files=4, max_per_datasource=2)
    sample2 = sample_files_for_analysis(files, max_files=4, max_per_datasource=2)
    sample3 = sample_files_for_analysis(files, max_files=4, max_per_datasource=2)
    
    # All should be identical
    filenames1 = [f.filename for f in sample1]
    filenames2 = [f.filename for f in sample2]
    filenames3 = [f.filename for f in sample3]
    
    assert filenames1 == filenames2 == filenames3
    assert len(sample1) <= 4  # Respect max_files


def test_deterministic_sampling_respects_max_per_datasource():
    """Test that sampling respects max_per_datasource limit."""
    ds_id1 = uuid4()
    ds_id2 = uuid4()
    
    files = [
        RawFile(id=uuid4(), filename="file1.pdf", file_stem="file1", data_source_id=ds_id1),
        RawFile(id=uuid4(), filename="file2.txt", file_stem="file2", data_source_id=ds_id1),
        RawFile(id=uuid4(), filename="file3.html", file_stem="file3", data_source_id=ds_id1),
        RawFile(id=uuid4(), filename="file4.pdf", file_stem="file4", data_source_id=ds_id2),
        RawFile(id=uuid4(), filename="file5.doc", file_stem="file5", data_source_id=ds_id2),
    ]
    
    sample = sample_files_for_analysis(files, max_files=10, max_per_datasource=2)
    
    # Count files per datasource
    files_by_ds = {}
    for f in sample:
        ds_id = str(f.data_source_id) if f.data_source_id else "None"
        files_by_ds[ds_id] = files_by_ds.get(ds_id, 0) + 1
    
    # Each datasource should have at most max_per_datasource files
    for count in files_by_ds.values():
        assert count <= 2


def test_deterministic_sampling_extension_priority():
    """Test that sampling prioritizes files by extension deterministically."""
    ds_id = uuid4()
    
    files = [
        RawFile(id=uuid4(), filename="file1.doc", file_stem="file1", data_source_id=ds_id),
        RawFile(id=uuid4(), filename="file2.pdf", file_stem="file2", data_source_id=ds_id),
        RawFile(id=uuid4(), filename="file3.txt", file_stem="file3", data_source_id=ds_id),
        RawFile(id=uuid4(), filename="file4.html", file_stem="file4", data_source_id=ds_id),
    ]
    
    sample = sample_files_for_analysis(files, max_files=2, max_per_datasource=2)
    
    # Should prioritize: pdf (5) > txt (4) > html (3) > doc (2)
    # So should pick file2.pdf and file3.txt
    filenames = [f.filename for f in sample]
    assert "file2.pdf" in filenames  # PDF has highest priority
    assert len(sample) == 2


def test_deterministic_sampling_empty_list():
    """Test that sampling handles empty list."""
    sample = sample_files_for_analysis([], max_files=5, max_per_datasource=2)
    assert sample == []


def test_deterministic_sampling_sorts_by_filename():
    """Test that files with same extension are sorted by filename."""
    ds_id = uuid4()
    
    files = [
        RawFile(id=uuid4(), filename="zebra.pdf", file_stem="zebra", data_source_id=ds_id),
        RawFile(id=uuid4(), filename="alpha.pdf", file_stem="alpha", data_source_id=ds_id),
        RawFile(id=uuid4(), filename="beta.pdf", file_stem="beta", data_source_id=ds_id),
    ]
    
    sample = sample_files_for_analysis(files, max_files=2, max_per_datasource=2)
    
    # Should be sorted alphabetically: alpha, beta, zebra
    filenames = [f.filename for f in sample]
    assert filenames == sorted(filenames[:2])  # First 2 should be alpha, beta
