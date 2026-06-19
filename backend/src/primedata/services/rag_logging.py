"""
Structured logging service for RAG requests.

Logs RAG requests with all relevant context for evaluation and monitoring.
"""

import hashlib
import time
from typing import Dict, List, Optional
from uuid import UUID

from loguru import logger
from sqlalchemy.orm import Session

from primedata.db.models import RAGRequestLog


class RAGLoggingService:
    """Service for logging RAG requests."""

    @staticmethod
    def log_request(
        db: Session,
        workspace_id: UUID,
        product_id: UUID,
        user_id: Optional[UUID],
        version: int,
        query: str,
        response: Optional[str] = None,
        retrieved_chunk_ids: Optional[List[str]] = None,
        retrieved_doc_ids: Optional[List[str]] = None,
        retrieval_scores: Optional[List[float]] = None,
        filters_applied: Optional[Dict] = None,
        policy_context: Optional[Dict] = None,
        acl_applied: bool = False,
        acl_denied: bool = False,
        prompt_hash: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_tokens: Optional[int] = None,
        latency_ms: Optional[float] = None,
        sampled_for_eval: bool = False,
    ) -> RAGRequestLog:
        """
        Log a RAG request.
        
        Args:
            db: Database session
            workspace_id: Workspace ID
            product_id: Product ID
            user_id: User ID (optional)
            version: Product version
            query: Query text
            response: Generated response (optional)
            retrieved_chunk_ids: List of retrieved chunk IDs
            retrieved_doc_ids: List of retrieved document IDs
            retrieval_scores: Retrieval similarity scores
            filters_applied: Filters applied during retrieval
            policy_context: Policy context applied
            acl_applied: Whether ACL was applied
            acl_denied: Whether ACL denied the request
            prompt_hash: Hash of the prompt used
            model: LLM model used
            temperature: Temperature setting
            max_tokens: Max tokens setting
            response_tokens: Number of tokens in response
            latency_ms: Total latency in milliseconds
            sampled_for_eval: Whether this request was sampled for evaluation
            
        Returns:
            Created RAGRequestLog entry
        """
        # Generate prompt hash if not provided
        if prompt_hash is None and response:
            prompt_text = f"{query}\n{response}"
            prompt_hash = hashlib.sha256(prompt_text.encode()).hexdigest()[:64]

        log_entry = RAGRequestLog(
            workspace_id=workspace_id,
            product_id=product_id,
            user_id=user_id,
            version=version,
            query=query,
            response=response,
            retrieved_chunk_ids=retrieved_chunk_ids,
            retrieved_doc_ids=retrieved_doc_ids,
            retrieval_scores=retrieval_scores,
            filters_applied=filters_applied,
            policy_context=policy_context,
            acl_applied=acl_applied,
            acl_denied=acl_denied,
            prompt_hash=prompt_hash,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            response_tokens=response_tokens,
            latency_ms=latency_ms,
            sampled_for_eval=sampled_for_eval,
        )

        db.add(log_entry)
        db.commit()
        db.refresh(log_entry)

        logger.debug(f"Logged RAG request {log_entry.id} for product {product_id}")
        return log_entry

    @staticmethod
    def get_request_logs(
        db: Session,
        product_id: Optional[UUID] = None,
        workspace_id: Optional[UUID] = None,
        version: Optional[int] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[RAGRequestLog]:
        """Get RAG request logs with optional filters."""
        query = db.query(RAGRequestLog)

        if product_id:
            query = query.filter(RAGRequestLog.product_id == product_id)
        if workspace_id:
            query = query.filter(RAGRequestLog.workspace_id == workspace_id)
        if version is not None:
            query = query.filter(RAGRequestLog.version == version)

        return query.order_by(RAGRequestLog.timestamp.desc()).offset(offset).limit(limit).all()




