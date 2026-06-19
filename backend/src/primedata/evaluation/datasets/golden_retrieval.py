"""
Golden retrieval dataset management.

Handles creation and management of golden retrieval evaluation datasets.
"""

from typing import Dict, List, Optional
from uuid import UUID

from .dataset_manager import DatasetManager


class GoldenRetrievalDataset:
    """Manager for golden retrieval datasets."""

    @staticmethod
    def create(
        db,
        workspace_id: UUID,
        product_id: UUID,
        name: str,
        description: Optional[str] = None,
        version: Optional[int] = None,
    ):
        """Create a golden retrieval dataset."""
        return DatasetManager.create_dataset(
            db=db,
            workspace_id=workspace_id,
            product_id=product_id,
            name=name,
            dataset_type="golden_retrieval",
            description=description,
            version=version,
        )

    @staticmethod
    def add_retrieval_cases(
        db,
        dataset_id: UUID,
        retrieval_cases: List[Dict],
    ):
        """
        Add retrieval cases to a golden retrieval dataset.
        
        Args:
            db: Database session
            dataset_id: Dataset ID
            retrieval_cases: List of retrieval case dictionaries with:
                - query: Query text
                - expected_chunks: List of expected chunk IDs (required)
                - expected_docs: Optional list of expected doc IDs
                - question_type: Optional question type
                - metadata: Optional metadata
        """
        items = []
        for case in retrieval_cases:
            if "query" not in case:
                raise ValueError("Retrieval case must have 'query'")
            if "expected_chunks" not in case:
                raise ValueError("Retrieval case must have 'expected_chunks'")
            items.append(case)

        return DatasetManager.add_items(db, dataset_id, items)




