"""
Golden Q/A dataset management.

Handles creation and management of golden Q/A evaluation datasets.
"""

from typing import Dict, List, Optional
from uuid import UUID

from loguru import logger

from .dataset_manager import DatasetManager


class GoldenQADataset:
    """Manager for golden Q/A datasets."""

    @staticmethod
    def create(
        db,
        workspace_id: UUID,
        product_id: UUID,
        name: str,
        description: Optional[str] = None,
        version: Optional[int] = None,
    ):
        """Create a golden Q/A dataset."""
        return DatasetManager.create_dataset(
            db=db,
            workspace_id=workspace_id,
            product_id=product_id,
            name=name,
            dataset_type="golden_qa",
            description=description,
            version=version,
        )

    @staticmethod
    def add_qa_pairs(
        db,
        dataset_id: UUID,
        qa_pairs: List[Dict],
    ):
        """
        Add Q/A pairs to a golden Q/A dataset.
        
        Args:
            db: Database session
            dataset_id: Dataset ID
            qa_pairs: List of Q/A pair dictionaries with:
                - query: Question
                - expected_answer: Expected answer
                - expected_chunks: Optional list of expected chunk IDs
                - expected_docs: Optional list of expected doc IDs
                - question_type: Optional question type
                - metadata: Optional metadata
        """
        items = []
        for qa in qa_pairs:
            if "query" not in qa or "expected_answer" not in qa:
                raise ValueError("Q/A pair must have 'query' and 'expected_answer'")
            items.append(qa)

        return DatasetManager.add_items(db, dataset_id, items)




