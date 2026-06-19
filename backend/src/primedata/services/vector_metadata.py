"""
Vector metadata service for PrimeData.

Manages chunk metadata using Qdrant as the single source of truth.
All metadata is stored in Qdrant payloads - no PostgreSQL tables needed.
"""

from typing import Any, Dict, List, Optional
from uuid import UUID

from loguru import logger
from primedata.indexing.qdrant_client import qdrant_client
from sqlalchemy.orm import Session


def create_document_metadata(
    db: Session,
    product_id: UUID,
    version: int,
    chunk_id: str,
    score: Optional[float],
    source_file: Optional[str],
    page_number: Optional[int],
    section: Optional[str],
    field_name: Optional[str],
    extra_tags: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Legacy function - metadata is now stored in Qdrant payloads.
    This function is kept for backward compatibility but does nothing.

    Args:
        db: Database session (unused)
        product_id: Product ID
        version: Version number
        chunk_id: Chunk identifier
        score: AI Trust Score for chunk
        source_file: Source file name
        page_number: Page number (if applicable)
        section: Section name
        field_name: Field name
        extra_tags: Additional tags as JSON

    Returns:
        Empty dict (metadata is in Qdrant)
    """
    logger.warning("create_document_metadata is deprecated - metadata is stored in Qdrant payloads")
    return {}


def create_vector_metadata(
    db: Session,
    product_id: UUID,
    version: int,
    collection_id: str,
    chunk_id: str,
    page_number: Optional[int],
    section: Optional[str],
    field_name: Optional[str],
    tags: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Legacy function - metadata is now stored in Qdrant payloads.
    This function is kept for backward compatibility but does nothing.

    Args:
        db: Database session (unused)
        product_id: Product ID
        version: Version number
        collection_id: Qdrant collection name
        chunk_id: Chunk identifier
        page_number: Page number (if applicable)
        section: Section name
        field_name: Field name (for ACL field_scope)
        tags: Tags as JSON

    Returns:
        Empty dict (metadata is in Qdrant)
    """
    logger.warning("create_vector_metadata is deprecated - metadata is stored in Qdrant payloads")
    return {}


def get_chunk_metadata(
    db: Session,
    product_id: UUID,
    version: Optional[int] = None,
    section: Optional[str] = None,
    field_name: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    collection_name: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Get chunk metadata for a product from Qdrant with optional filters.

    Args:
        db: Database session (unused, kept for API compatibility)
        product_id: Product ID
        version: Optional version filter
        section: Optional section filter
        field_name: Optional field name filter
        limit: Maximum number of results
        offset: Offset for pagination (Qdrant uses scroll offset)
        collection_name: Optional collection name (if not provided, will try to find it)

    Returns:
        List of chunk metadata dictionaries (from Qdrant payloads)
    """
    from primedata.db.models import Product

    # Get product to find collection name if not provided
    if not collection_name:
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            logger.error(f"Product {product_id} not found")
            return []

        version_to_use = version if version is not None else product.current_version
        collection_name = qdrant_client.find_collection_name(
            workspace_id=product.workspace_id,
            product_id=product_id,
            version=version_to_use,
            product_name=product.name,
        )

        if not collection_name:
            logger.warning(f"Collection not found for product {product_id}, version {version_to_use}")
            return []

    # Build filter conditions
    filter_conditions = {
        "product_id": str(product_id),
    }

    if version is not None:
        filter_conditions["version"] = version

    if section:
        filter_conditions["section"] = section

    if field_name:
        filter_conditions["field_name"] = field_name

    # Scroll points from Qdrant
    scroll_result = qdrant_client.scroll_points(
        collection_name=collection_name,
        limit=limit,
        offset=offset if offset > 0 else None,
        filter_conditions=filter_conditions,
        with_payload=True,
        with_vector=False,
    )

    points = scroll_result.get("points", [])

    # Convert to metadata format (compatible with old DocumentMetadata structure)
    metadata_list = []
    for point in points:
        payload = point.get("payload", {})
        metadata_list.append(
            {
                "chunk_id": payload.get("chunk_id"),
                "product_id": product_id,
                "version": payload.get("version"),
                "score": payload.get("score"),
                "source_file": payload.get("source_file") or payload.get("filename"),
                "page_number": payload.get("page_number") or payload.get("page"),
                "section": payload.get("section"),
                "field_name": payload.get("field_name"),
                "extra_tags": payload.get("extra_tags"),
                "created_at": payload.get("created_at"),
            }
        )

    return metadata_list


def get_vector_metadata_by_chunk(
    db: Session,
    product_id: UUID,
    chunk_id: str,
    version: Optional[int] = None,
    collection_name: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Get vector metadata for a specific chunk from Qdrant.

    Args:
        db: Database session (unused, kept for API compatibility)
        product_id: Product ID
        chunk_id: Chunk identifier
        version: Optional version filter
        collection_name: Optional collection name (if not provided, will try to find it)

    Returns:
        Chunk metadata dictionary (from Qdrant payload) or None
    """
    from primedata.db.models import Product

    # Get product to find collection name if not provided
    if not collection_name:
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            logger.error(f"Product {product_id} not found")
            return None

        version_to_use = version if version is not None else product.current_version
        collection_name = qdrant_client.find_collection_name(
            workspace_id=product.workspace_id,
            product_id=product_id,
            version=version_to_use,
            product_name=product.name,
        )

        if not collection_name:
            logger.warning(f"Collection not found for product {product_id}, version {version_to_use}")
            return None

    # Get point by chunk_id
    point = qdrant_client.get_point_by_chunk_id(
        collection_name=collection_name,
        chunk_id=chunk_id,
        product_id=str(product_id),
        version=version,
    )

    if not point:
        return None

    # Convert to metadata format (compatible with old VectorMetadata structure)
    payload = point.get("payload", {})
    return {
        "chunk_id": payload.get("chunk_id"),
        "product_id": product_id,
        "version": payload.get("version"),
        "collection_id": payload.get("collection_id") or collection_name,
        "page_number": payload.get("page_number") or payload.get("page"),
        "section": payload.get("section"),
        "field_name": payload.get("field_name"),
        "tags": payload.get("tags"),
        "created_at": payload.get("created_at"),
    }
