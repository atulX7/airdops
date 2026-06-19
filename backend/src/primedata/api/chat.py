"""
Chat API endpoint for RAG queries with LLM generation.

Uses OpenAI API for LLM generation and evaluations.
Requires OPENAI_API_KEY to be configured.
"""

import hashlib
import os
import time
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from primedata.core.scope import ensure_product_access
from primedata.core.security import get_current_user
from primedata.core.user_utils import get_user_id
from primedata.db.database import get_db
from primedata.db.models import Product, Workspace
from primedata.indexing.qdrant_client import QdrantClient
from primedata.services.acl import get_acls_for_user, apply_acl_filter_to_payloads
from primedata.services.rag_logging import RAGLoggingService

router = APIRouter(prefix="/api/v1/chat", tags=["Chat"])


def get_current_user_from_request(request: Request) -> Dict[str, Any]:
    """Get current user from request state."""
    if not hasattr(request.state, "user") or not request.state.user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return request.state.user


class ChatRequest(BaseModel):
    """Chat request model."""

    product_id: str = Field(..., description="Product ID")
    query: str = Field(..., description="User query")
    version: Optional[int] = Field(None, description="Product version (defaults to current)")
    use: Optional[str] = Field(default="current", description="Use 'current' or 'prod' version")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of chunks to retrieve")
    temperature: Optional[float] = Field(default=0.7, ge=0.0, le=2.0, description="LLM temperature")
    max_tokens: Optional[int] = Field(default=1000, ge=1, le=4000, description="Max tokens in response")
    model: Optional[str] = Field(None, description="LLM model to use (defaults to workspace setting)")


class ChatResponse(BaseModel):
    """Chat response model."""

    response: str = Field(..., description="Generated response")
    citations: List[str] = Field(default_factory=list, description="Citation IDs")
    retrieved_chunks: List[Dict[str, Any]] = Field(default_factory=list, description="Retrieved chunks")
    model: str = Field(..., description="Model used")
    latency_ms: float = Field(..., description="Total latency in milliseconds")
    tokens_used: Optional[int] = Field(None, description="Tokens used")


class LLMClient:
    """LLM client interface."""

    def generate(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 1000,
    ) -> Dict[str, Any]:
        """
        Generate response from LLM.
        
        Returns:
            Dictionary with 'text', 'tokens_used', 'model'
        """
        raise NotImplementedError


class OpenAILLMClient(LLMClient):
    """OpenAI LLM client."""

    def __init__(self, api_key: str, model: str = "gpt-3.5-turbo"):
        try:
            from openai import OpenAI
            import httpx

            self.client = OpenAI(
                api_key=api_key,
                timeout=httpx.Timeout(30.0, connect=10.0),
            )
            self.model = model
        except ImportError:
            raise ImportError("OpenAI package required. Install with: pip install openai")

    def generate(self, prompt: str, temperature: float = 0.7, max_tokens: int = 1000) -> Dict[str, Any]:
        """Generate using OpenAI."""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return {
                "text": response.choices[0].message.content,
                "tokens_used": response.usage.total_tokens if response.usage else None,
                "model": self.model,
            }
        except Exception as e:
            logger.error(f"OpenAI generation error: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"LLM generation failed: {str(e)}")


def get_llm_client(workspace: Workspace, model: Optional[str] = None) -> LLMClient:
    """
    Get LLM client using OpenAI API.
    
    Requires OPENAI_API_KEY to be configured either in workspace settings or environment variable.
    """
    # Check for OpenAI API key
    openai_key = workspace.settings.get("openai_api_key") if workspace.settings else None
    if not openai_key:
        openai_key = os.getenv("OPENAI_API_KEY")

    if not openai_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OpenAI API key is required. Please configure OPENAI_API_KEY in workspace settings or environment variables.",
        )

    model_name = model or workspace.settings.get("chat_model", "gpt-3.5-turbo") if workspace.settings else "gpt-3.5-turbo"
    return OpenAILLMClient(api_key=openai_key, model=model_name)


def build_rag_prompt(query: str, chunks: List[Dict[str, Any]]) -> str:
    """Build RAG prompt from query and retrieved chunks."""
    context = "\n\n".join([f"[{i+1}] {chunk.get('text', '')}" for i, chunk in enumerate(chunks)])
    
    prompt = f"""You are answering a question using the provided context. You MUST cite your sources.

RULES FOR CITATIONS:
1. Every factual claim or piece of information you use from the context MUST be followed by a citation in the format [1], [2], [3], etc.
2. The citation number corresponds to the numbered chunk above (e.g., [1] refers to the first chunk, [2] to the second, etc.).
3. Place citations immediately after the information you're citing, like this: "Amazon's revenue was $574.8 billion [1]."
4. If you use information from multiple chunks, cite all of them: "The company reported strong growth [1][2]."

EXAMPLE:
Question: What was Amazon's revenue?
Answer: Amazon's total revenue in 2024 was $574.8 billion [1]. This represents significant growth compared to previous years [2].

Context:
{context}

Question: {query}

Answer (MUST include citations [1], [2], [3] etc. after every fact from the context):"""
    return prompt


@router.post("/query", response_model=ChatResponse)
async def chat_query(
    request: ChatRequest,
    http_request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_from_request),
):
    """
    Chat endpoint for RAG queries with LLM generation.
    
    Uses OpenAI API for LLM generation. Requires OPENAI_API_KEY to be configured.
    """
    start_time = time.time()
    
    try:
        # Get product and ensure access
        product = ensure_product_access(db, http_request, UUID(request.product_id))
        if not product:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found or access denied")

        # Get workspace
        workspace = db.query(Workspace).filter(Workspace.id == product.workspace_id).first()
        if not workspace:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

        # Determine version
        version = request.version
        if version is None:
            if request.use == "prod":
                version = product.promoted_version or product.current_version
            else:
                version = product.current_version

        if version <= 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No data available. Please run a pipeline first.")

        # Initialize Qdrant client
        qdrant_client = QdrantClient()
        if not qdrant_client.is_connected():
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Vector database connection failed")

        # Get collection name
        if request.use == "prod":
            collection_name = qdrant_client.get_prod_alias_collection(
                workspace_id=str(product.workspace_id),
                product_id=str(product.id),
                product_name=product.name,
            )
            if not collection_name:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Production collection not found")
        else:
            collection_name = qdrant_client.find_collection_name(
                workspace_id=str(product.workspace_id),
                product_id=str(product.id),
                version=version,
            )
            if not collection_name:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")

        # Retrieve chunks
        from primedata.indexing.embeddings import EmbeddingGenerator

        # Get embedding model from product config
        embedding_config = product.embedding_config or {}
        model_name = embedding_config.get("embedder_name", "minilm")
        
        embedder = EmbeddingGenerator(model_name=model_name, workspace_id=product.workspace_id, db=db)
        query_embedding = embedder.embed_batch([request.query])[0]

        # Search Qdrant
        search_results = qdrant_client.search(
            collection_name=collection_name,
            query_vector=query_embedding.tolist(),
            limit=request.top_k,
        )

        # Apply ACL filtering if enabled
        user_id = get_user_id(current_user)
        acl_applied = False
        acl_denied = False
        
        # Get user ACLs for this product
        user_acls = []
        if user_id:
            user_acls = get_acls_for_user(db, user_id, product.id)
        
        # Apply ACL filtering
        if user_acls:
            # Convert search results to format expected by ACL filter
            search_points = [{"id": r.id, "payload": r.payload} for r in search_results]
            filtered_payloads = apply_acl_filter_to_payloads(search_points, user_acls, product.id)
            
            # Create a set of allowed chunk IDs for fast lookup
            allowed_chunk_ids = {p.get("chunk_id") for p in filtered_payloads if p.get("chunk_id")}
            
            # Filter search results based on allowed chunk IDs
            filtered_results = [r for r in search_results if r.payload.get("chunk_id") in allowed_chunk_ids]
            acl_applied = True
            if len(filtered_results) < len(search_results):
                acl_denied = True
        else:
            # No ACLs configured, allow all results
            filtered_results = search_results

        if not filtered_results and acl_denied:
            # All results were filtered by ACL
            response_text = "I don't have access to the information needed to answer this question."
            citations = []
            retrieved_chunks = []
        else:
            # Prepare chunks for RAG
            retrieved_chunks = []
            chunk_ids = []
            for result in filtered_results:
                chunk_data = {
                    "id": result.payload.get("chunk_id"),
                    "text": result.payload.get("text", ""),
                    "score": result.score,
                    "doc_path": result.payload.get("doc_path", ""),
                }
                retrieved_chunks.append(chunk_data)
                if chunk_data["id"]:
                    chunk_ids.append(str(chunk_data["id"]))

            # Get LLM client
            llm_client = get_llm_client(workspace, model=request.model)

            # Build prompt
            prompt = build_rag_prompt(request.query, retrieved_chunks)

            # Generate response
            generation_start = time.time()
            llm_result = llm_client.generate(
                prompt=prompt,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
            )
            generation_time = (time.time() - generation_start) * 1000

            response_text = llm_result["text"]
            citations = chunk_ids[:3]  # Use top 3 chunks as citations

        # Calculate total latency
        total_latency = (time.time() - start_time) * 1000

        # Log request
        user_uuid = UUID(current_user["id"]) if current_user.get("id") else None
        RAGLoggingService.log_request(
            db=db,
            workspace_id=product.workspace_id,
            product_id=product.id,
            user_id=user_uuid,
            version=version,
            query=request.query,
            response=response_text,
            retrieved_chunk_ids=[str(cid) for cid in chunk_ids] if chunk_ids else None,
            retrieved_doc_ids=None,  # Could extract from chunks
            retrieval_scores=[chunk["score"] for chunk in retrieved_chunks],
            acl_applied=acl_applied,
            acl_denied=acl_denied,
            model=llm_result.get("model") if 'llm_result' in locals() else None,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            response_tokens=llm_result.get("tokens_used") if 'llm_result' in locals() else None,
            latency_ms=total_latency,
        )

        return ChatResponse(
            response=response_text,
            citations=citations,
            retrieved_chunks=retrieved_chunks,
            model=llm_result.get("model", "unknown") if 'llm_result' in locals() else "none",
            latency_ms=total_latency,
            tokens_used=llm_result.get("tokens_used") if 'llm_result' in locals() else None,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat query error: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Chat query failed: {str(e)}")

