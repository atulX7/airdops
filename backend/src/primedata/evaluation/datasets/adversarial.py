"""
Adversarial dataset management.

Handles creation and management of adversarial evaluation datasets.
"""

from typing import Dict, List, Optional
from uuid import UUID

from .dataset_manager import DatasetManager


class AdversarialDataset:
    """Manager for adversarial datasets."""

    @staticmethod
    def create(
        db,
        workspace_id: UUID,
        product_id: UUID,
        name: str,
        description: Optional[str] = None,
        version: Optional[int] = None,
    ):
        """Create an adversarial dataset."""
        return DatasetManager.create_dataset(
            db=db,
            workspace_id=workspace_id,
            product_id=product_id,
            name=name,
            dataset_type="adversarial",
            description=description,
            version=version,
        )

    @staticmethod
    def add_adversarial_cases(
        db,
        dataset_id: UUID,
        adversarial_cases: List[Dict],
    ):
        """
        Add adversarial test cases to a dataset.
        
        Args:
            db: Database session
            dataset_id: Dataset ID
            adversarial_cases: List of adversarial case dictionaries with:
                - query: Query text
                - expected_refusal: Whether refusal is expected (bool)
                - expected_answer: Optional expected answer if not refusal
                - question_type: Optional question type
                - metadata: Optional metadata (e.g., trap_type: 'hallucination', 'missing_context', 'conflicting_docs', 'acl_denied')
        """
        items = []
        for case in adversarial_cases:
            if "query" not in case:
                raise ValueError("Adversarial case must have 'query'")
            items.append(case)

        return DatasetManager.add_items(db, dataset_id, items)




