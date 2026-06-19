"""
Dataset manager for evaluation datasets.

Provides CRUD operations for evaluation datasets and items.
"""

from typing import Dict, List, Optional
from uuid import UUID

from loguru import logger
from sqlalchemy.orm import Session

from primedata.db.models import EvalDataset, EvalDatasetItem, EvalDatasetStatus
from primedata.evaluation.question_types import DatasetType


class DatasetManager:
    """Manager for evaluation datasets."""

    @staticmethod
    def create_dataset(
        db: Session,
        workspace_id: UUID,
        product_id: UUID,
        name: str,
        dataset_type: str,
        description: Optional[str] = None,
        version: Optional[int] = None,
        metadata: Optional[Dict] = None,
    ) -> EvalDataset:
        """
        Create a new evaluation dataset.
        
        Args:
            db: Database session
            workspace_id: Workspace ID
            product_id: Product ID
            name: Dataset name
            dataset_type: Dataset type ('golden_qa', 'golden_retrieval', 'adversarial')
            description: Optional description
            version: Product version (None for all versions)
            metadata: Additional metadata
            
        Returns:
            Created dataset
        """
        # Validate dataset type
        try:
            DatasetType(dataset_type)
        except ValueError:
            raise ValueError(f"Invalid dataset type: {dataset_type}")

        dataset = EvalDataset(
            workspace_id=workspace_id,
            product_id=product_id,
            name=name,
            description=description,
            dataset_type=dataset_type,
            version=version,
            status=EvalDatasetStatus.DRAFT,
            extra_metadata=metadata or {},
        )

        db.add(dataset)
        db.commit()
        db.refresh(dataset)

        logger.info(f"Created evaluation dataset {dataset.id} ({dataset_type}) for product {product_id}")
        return dataset

    @staticmethod
    def get_dataset(db: Session, dataset_id: UUID) -> Optional[EvalDataset]:
        """Get dataset by ID."""
        return db.query(EvalDataset).filter(EvalDataset.id == dataset_id).first()

    @staticmethod
    def list_datasets(
        db: Session,
        workspace_id: Optional[UUID] = None,
        product_id: Optional[UUID] = None,
        dataset_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[EvalDataset]:
        """
        List datasets with optional filters.
        
        Args:
            db: Database session
            workspace_id: Filter by workspace
            product_id: Filter by product
            dataset_type: Filter by type
            status: Filter by status
            
        Returns:
            List of datasets
        """
        query = db.query(EvalDataset)

        if workspace_id:
            query = query.filter(EvalDataset.workspace_id == workspace_id)
        if product_id:
            query = query.filter(EvalDataset.product_id == product_id)
        if dataset_type:
            query = query.filter(EvalDataset.dataset_type == dataset_type)
        if status:
            try:
                status_enum = EvalDatasetStatus(status)
                query = query.filter(EvalDataset.status == status_enum)
            except ValueError:
                pass

        return query.order_by(EvalDataset.created_at.desc()).all()

    @staticmethod
    def update_dataset(
        db: Session,
        dataset_id: UUID,
        name: Optional[str] = None,
        description: Optional[str] = None,
        status: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> Optional[EvalDataset]:
        """Update dataset."""
        dataset = db.query(EvalDataset).filter(EvalDataset.id == dataset_id).first()
        if not dataset:
            return None

        if name is not None:
            dataset.name = name
        if description is not None:
            dataset.description = description
        if status is not None:
            try:
                dataset.status = EvalDatasetStatus(status)
            except ValueError:
                raise ValueError(f"Invalid status: {status}")
        if metadata is not None:
            dataset.extra_metadata = metadata

        db.commit()
        db.refresh(dataset)
        return dataset

    @staticmethod
    def delete_dataset(db: Session, dataset_id: UUID) -> bool:
        """Delete dataset and all its items."""
        dataset = db.query(EvalDataset).filter(EvalDataset.id == dataset_id).first()
        if not dataset:
            return False

        db.delete(dataset)
        db.commit()
        logger.info(f"Deleted evaluation dataset {dataset_id}")
        return True

    @staticmethod
    def add_items(
        db: Session,
        dataset_id: UUID,
        items: List[Dict],
    ) -> List[EvalDatasetItem]:
        """
        Add items to a dataset.
        
        Args:
            db: Database session
            dataset_id: Dataset ID
            items: List of item dictionaries with keys:
                - query: Required
                - expected_answer: Optional (for golden_qa)
                - expected_chunks: Optional (list of chunk IDs)
                - expected_docs: Optional (list of doc IDs)
                - question_type: Optional
                - metadata: Optional
                
        Returns:
            List of created items
        """
        dataset = db.query(EvalDataset).filter(EvalDataset.id == dataset_id).first()
        if not dataset:
            raise ValueError(f"Dataset {dataset_id} not found")

        from primedata.services.s3_content_storage import (
            get_eval_dataset_item_answer_path,
            save_text_to_s3,
        )
        
        created_items = []
        for item_data in items:
            # Create item first to get ID
            item = EvalDatasetItem(
                dataset_id=dataset_id,
                query=item_data["query"],
                expected_answer_path=None,  # Will be set after saving to S3
                expected_chunks=item_data.get("expected_chunks"),
                expected_docs=item_data.get("expected_docs"),
                question_type=item_data.get("question_type"),
                extra_metadata=item_data.get("metadata", {}),
            )
            db.add(item)
            db.flush()  # Flush to get the ID
            
            # Save expected_answer to S3 if provided
            if item_data.get("expected_answer"):
                expected_answer_path = get_eval_dataset_item_answer_path(
                    dataset.workspace_id, dataset.product_id, dataset_id, item.id
                )
                if save_text_to_s3(expected_answer_path, item_data["expected_answer"], "text/plain"):
                    item.expected_answer_path = expected_answer_path
                else:
                    logger.warning(f"Failed to save expected_answer to S3 for item {item.id}")
            
            db.flush()
            created_items.append(item)

        db.commit()
        for item in created_items:
            db.refresh(item)

        logger.info(f"Added {len(created_items)} items to dataset {dataset_id}")
        return created_items

    @staticmethod
    def list_items(
        db: Session, 
        dataset_id: UUID, 
        limit: Optional[int] = None, 
        offset: Optional[int] = None
    ) -> List[EvalDatasetItem]:
        """List items in a dataset with optional pagination."""
        query = db.query(EvalDatasetItem).filter(EvalDatasetItem.dataset_id == dataset_id)
        
        if offset is not None:
            query = query.offset(offset)
        if limit is not None:
            query = query.limit(limit)
            
        return query.all()
    
    @staticmethod
    def count_items(db: Session, dataset_id: UUID) -> int:
        """Get total count of items in a dataset."""
        return db.query(EvalDatasetItem).filter(EvalDatasetItem.dataset_id == dataset_id).count()

    @staticmethod
    def delete_item(db: Session, item_id: UUID) -> bool:
        """Delete an item."""
        item = db.query(EvalDatasetItem).filter(EvalDatasetItem.id == item_id).first()
        if not item:
            return False

        db.delete(item)
        db.commit()
        return True

