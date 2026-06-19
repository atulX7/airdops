"""
ACL service for PrimeData.

Manages access control lists for fine-grained access control at product, document, and field levels.
"""

from typing import Any, Dict, List, Optional, Set
from uuid import UUID

from loguru import logger
from primedata.db.models import ACL, ACLAccessType
from sqlalchemy.orm import Session


def create_acl(
    db: Session,
    user_id: UUID,
    product_id: UUID,
    access_type: ACLAccessType,
    index_scope: Optional[str] = None,
    doc_scope: Optional[str] = None,
    field_scope: Optional[str] = None,
) -> ACL:
    """
    Create an ACL entry.

    Args:
        db: Database session
        user_id: User ID
        product_id: Product ID
        access_type: Access type (full/index/document/field)
        index_scope: Optional comma-separated index IDs
        doc_scope: Optional comma-separated document IDs
        field_scope: Optional comma-separated field names

    Returns:
        Created ACL instance
    """
    acl = ACL(
        user_id=user_id,
        product_id=product_id,
        access_type=access_type,
        index_scope=index_scope,
        doc_scope=doc_scope,
        field_scope=field_scope,
    )
    db.add(acl)
    db.commit()
    db.refresh(acl)
    logger.info(f"Created ACL: user={user_id}, product={product_id}, type={access_type}")
    return acl


def get_acls_for_user(
    db: Session,
    user_id: UUID,
    product_id: Optional[UUID] = None,
) -> List[ACL]:
    """
    Get ACLs for a user, optionally filtered by product.

    Args:
        db: Database session
        user_id: User ID
        product_id: Optional product ID filter

    Returns:
        List of ACL instances
    """
    query = db.query(ACL).filter(ACL.user_id == user_id)
    if product_id:
        query = query.filter(ACL.product_id == product_id)
    return query.all()


def get_acls_for_product(
    db: Session,
    product_id: UUID,
    user_id: Optional[UUID] = None,
) -> List[ACL]:
    """
    Get ACLs for a product, optionally filtered by user.

    Args:
        db: Database session
        product_id: Product ID
        user_id: Optional user ID filter

    Returns:
        List of ACL instances
    """
    query = db.query(ACL).filter(ACL.product_id == product_id)
    if user_id:
        query = query.filter(ACL.user_id == user_id)
    return query.all()


def delete_acls(
    db: Session,
    acl_id: Optional[UUID] = None,
    user_id: Optional[UUID] = None,
    product_id: Optional[UUID] = None,
) -> int:
    """
    Delete ACLs matching the given criteria.

    Args:
        db: Database session
        acl_id: Optional specific ACL ID
        user_id: Optional user ID filter
        product_id: Optional product ID filter

    Returns:
        Number of deleted ACLs
    """
    query = db.query(ACL)

    if acl_id:
        query = query.filter(ACL.id == acl_id)
    if user_id:
        query = query.filter(ACL.user_id == user_id)
    if product_id:
        query = query.filter(ACL.product_id == product_id)

    count = query.delete(synchronize_session=False)
    db.commit()
    logger.info(f"Deleted {count} ACLs: acl_id={acl_id}, user_id={user_id}, product_id={product_id}")
    return count


def apply_acl_filter_to_payloads(
    all_points: List[Dict[str, Any]],
    user_acls: List[ACL],
    product_id: Any,  # UUID or str
) -> List[Dict[str, Any]]:
    """
    Filter Qdrant points based on user ACLs.

    Args:
        all_points: List of Qdrant points (dicts with 'id' and 'payload')
        user_acls: User's ACLs for the product
        product_id: Product ID (UUID or str) for matching

    Returns:
        Filtered list of point payloads
    """
    if not user_acls:
        return []

    allowed = []
    allowed_chunk_ids: Set[str] = set()
    product_id_str = str(product_id)

    for point in all_points:
        payload = point.get("payload", {})
        chunk_id = payload.get("chunk_id")
        if not chunk_id:
            continue

        point_product_id = payload.get("product_id")
        document_id = payload.get("document_id") or payload.get("doc_scope")
        field_name = payload.get("field_name") or payload.get("field_scope")

        for acl in user_acls:
            # Full access - allow everything
            if acl.access_type == ACLAccessType.FULL:
                allowed.append(payload)
                allowed_chunk_ids.add(chunk_id)
                break

            # Index scope - match by product_id (index_scope is product_id in AIRD)
            if acl.access_type == ACLAccessType.INDEX:
                if acl.index_scope:
                    # index_scope can be comma-separated product IDs
                    scope_ids = [s.strip() for s in acl.index_scope.split(",")]
                    if point_product_id and (point_product_id in scope_ids or str(point_product_id) in scope_ids):
                        allowed.append(payload)
                        allowed_chunk_ids.add(chunk_id)
                        break

            # Document scope - match by document_id (from doc_scope)
            if acl.access_type == ACLAccessType.DOCUMENT:
                if acl.doc_scope and document_id:
                    # doc_scope is comma-separated document IDs
                    scope_docs = [s.strip() for s in acl.doc_scope.split(",")]
                    if document_id in scope_docs:
                        allowed.append(payload)
                        allowed_chunk_ids.add(chunk_id)
                        break

            # Field scope - match by field_name
            if acl.access_type == ACLAccessType.FIELD:
                if acl.field_scope and field_name:
                    scope_fields = [s.strip().lower() for s in acl.field_scope.split(",")]
                    field_lower = field_name.strip().lower()
                    if any(scope_field in field_lower or field_lower in scope_field for scope_field in scope_fields):
                        allowed.append(payload)
                        allowed_chunk_ids.add(chunk_id)
                        break

    # Remove duplicates by chunk_id
    seen = set()
    unique_allowed = []
    for payload in allowed:
        chunk_id = payload.get("chunk_id")
        if chunk_id and chunk_id not in seen:
            seen.add(chunk_id)
            unique_allowed.append(payload)

    return unique_allowed


def get_allowed_chunk_ids_from_payloads(payloads: List[Dict[str, Any]]) -> Set[str]:
    """
    Extract allowed chunk IDs from Qdrant payloads.

    Args:
        payloads: List of Qdrant payload dictionaries

    Returns:
        Set of chunk IDs
    """
    return {p.get("chunk_id") for p in payloads if p.get("chunk_id")}


# Legacy functions for backward compatibility (deprecated - use payload versions)
def apply_acl_filter(
    all_vectors: List[Any],  # Legacy: VectorMetadata objects
    user_acls: List[ACL],
) -> List[Any]:
    """
    Legacy function - deprecated. Use apply_acl_filter_to_payloads instead.
    This function is kept for backward compatibility but should not be used with new code.
    """
    from loguru import logger

    logger.warning("apply_acl_filter is deprecated. Use apply_acl_filter_to_payloads with Qdrant payloads.")
    # Convert VectorMetadata to payload dicts for compatibility
    payloads = []
    for v in all_vectors:
        payloads.append(
            {
                "chunk_id": v.chunk_id,
                "product_id": str(v.product_id),
                "document_id": getattr(v, "document_id", None),
                "field_name": v.field_name,
            }
        )
    return apply_acl_filter_to_payloads(
        [{"payload": p} for p in payloads], user_acls, all_vectors[0].product_id if all_vectors else None
    )


def get_allowed_chunk_ids(vectors: List[Any]) -> Set[str]:
    """
    Legacy function - deprecated. Use get_allowed_chunk_ids_from_payloads instead.
    """
    from loguru import logger

    logger.warning("get_allowed_chunk_ids is deprecated. Use get_allowed_chunk_ids_from_payloads with Qdrant payloads.")
    if not vectors:
        return set()
    # Try to extract chunk_id from VectorMetadata or payload
    chunk_ids = set()
    for v in vectors:
        if hasattr(v, "chunk_id"):
            chunk_ids.add(v.chunk_id)
        elif isinstance(v, dict):
            chunk_ids.add(v.get("chunk_id", ""))
    return chunk_ids
