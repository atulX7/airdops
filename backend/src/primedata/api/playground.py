"""
RAG Playground API endpoints for querying product-specific vector data.
"""

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from ..core.embedding_workspace import validate_embedding_config_for_workspace
from ..core.scope import ensure_product_access
from ..core.settings import get_settings
from ..core.security import get_current_user
from ..core.user_utils import get_user_id
from ..db.database import get_db
from ..db.models import Product, PipelineRun, PipelineRunStatus
from ..indexing.qdrant_client import QdrantClient
from ..storage.minio_client import MinIOClient
from ..services.reranker import rerank_candidates
from .search_utils import expand_query_terms, calculate_keyword_boost

logger = logging.getLogger(__name__)

router = APIRouter()


def get_latest_successful_pipeline_version(db, product_id) -> Optional[int]:
    """
    Get the latest successful pipeline run version for a product.
    
    This ensures we always use the most recent successfully indexed version,
    not just product.current_version which might be stale due to race conditions.
    
    Returns:
        Version number of latest successful run, or None if no successful runs exist
    """
    latest_run = (
        db.query(PipelineRun)
        .filter(
            PipelineRun.product_id == product_id,
            PipelineRun.status == PipelineRunStatus.SUCCEEDED,
        )
        .order_by(PipelineRun.version.desc())
        .first()
    )
    
    if latest_run:
        return latest_run.version
    return None


def get_current_user_from_request(request: Request) -> Dict[str, Any]:
    """Get current user from request state (set by auth middleware)."""
    if not hasattr(request.state, "user") or not request.state.user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return request.state.user


class PlaygroundQuery(BaseModel):
    product_id: str = Field(..., description="Product ID to query")
    query: str = Field(..., description="Search query text")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of results to return")
    use: Optional[str] = Field(
        default="current", description="Use 'current' for current version or 'prod' for production alias"
    )
    compat_mode: Optional[bool] = Field(
        default=False,
        description="If true, allow dimension mismatch and use collection's embedding model (for debugging)"
    )
    # Optional filtering
    filter_product_id: Optional[str] = Field(None, description="Filter by product_id (must match query product_id)")
    filter_version: Optional[int] = Field(None, description="Filter by version")
    filter_doc_scope: Optional[str] = Field(None, description="Filter by doc_scope (document_id)")
    filter_field_scope: Optional[str] = Field(None, description="Filter by field_scope (section)")


class PlaygroundResult(BaseModel):
    text: str = Field(..., description="Chunk text content")
    score: float = Field(..., description="Final score used for ordering (rerank_score if reranked, else vector_score)")
    doc_path: str = Field(..., description="Source document path")
    section: Optional[str] = Field(None, description="Document section")
    meta: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    presigned_url: Optional[str] = Field(None, description="Presigned URL for document access")
    vector_score: Optional[float] = Field(None, description="Dense retrieval similarity score from Qdrant")
    rerank_score: Optional[float] = Field(None, description="Cross-encoder rerank score (when reranking enabled)")


class PlaygroundResponse(BaseModel):
    results: List[PlaygroundResult] = Field(..., description="Search results")
    latency_ms: float = Field(..., description="Query latency in milliseconds")
    collection_name: str = Field(..., description="Qdrant collection name used")
    total_results: int = Field(..., description="Total number of results found")
    acl_applied: bool = Field(default=False, description="Whether ACL filtering was applied (M5)")
    reranker_used: bool = Field(default=False, description="Whether cross-encoder reranking was applied")


class ContextAssemblyRequest(BaseModel):
    product_id: str = Field(..., description="Product ID to assemble context for")
    top_k: int = Field(default=10, ge=1, le=50, description="Number of chunks to include")
    max_tokens: int = Field(default=1500, ge=200, le=6000, description="Approximate max tokens for assembled text")
    dedup_threshold: float = Field(
        default=0.95,
        ge=0.0,
        le=1.0,
        description="Simple similarity threshold for deduplication (exact/near-exact)",
    )
    use: Optional[str] = Field(default="current", description="Use 'current' or 'prod' version")


class ContextChunk(BaseModel):
    chunk_id: Optional[str] = None
    source_file: Optional[str] = None
    page_number: Optional[int] = None
    score: Optional[float] = None
    freshness: Optional[float] = None
    text: str


class ContextAssemblyResponse(BaseModel):
    assembled_text: str
    chunks: List[ContextChunk]
    freshness_summary: Dict[str, Optional[float]]
    deduped_count: int
    conflicts_flagged: int
    collection_name: str


@router.post("/api/v1/playground/query", response_model=PlaygroundResponse)
async def query_playground(
    query_data: PlaygroundQuery,
    request: Request,
    current_user: dict = Depends(get_current_user_from_request),
    db=Depends(get_db),
):
    """
    Query the RAG playground for a specific product.

    This endpoint performs semantic search on the product's vector data
    and returns the most relevant chunks with metadata and presigned URLs.
    """
    start_time = time.time()

    try:
        # Ensure user has access to the product
        from uuid import UUID

        product = ensure_product_access(db=db, request=request, product_id=UUID(query_data.product_id))

        if not product:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found or access denied")

        # Initialize Qdrant client first
        qdrant_client = QdrantClient()
        if not qdrant_client.is_connected():
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Vector database connection failed")

        # Determine which collection to use and which version
        version_to_use = None
        if query_data.use == "prod":
            # Check if product has a promoted version
            if not product.promoted_version:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No production version available. Please promote a version first.",
                )

            version_to_use = product.promoted_version

            # Use production alias
            collection_name = qdrant_client.get_prod_alias_collection(
                workspace_id=str(product.workspace_id), product_id=str(product.id), product_name=product.name
            )

            if not collection_name:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Production alias not found. Please promote a version first."
                )
        else:
            # Use latest successful pipeline run version (not just current_version which might be stale)
            latest_successful_version = get_latest_successful_pipeline_version(db, product.id)
            
            if not latest_successful_version or latest_successful_version <= 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No successful pipeline runs found. Please run a pipeline first to index data.",
                )

            version_to_use = latest_successful_version

            # Find collection name (checks both product name and product_id formats for backward compatibility)
            collection_name = qdrant_client.find_collection_name(
                workspace_id=str(product.workspace_id),
                product_id=str(product.id),
                version=version_to_use,
                product_name=product.name,
            )

            if not collection_name:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, 
                    detail=f"Collection not found for version {version_to_use}. Please run a pipeline first."
                )

        # Mandatory search filters: every Qdrant query must include these so results never cross workspace/product/version/collection
        workspace_id_val = str(product.workspace_id) if product.workspace_id is not None else None
        product_id_val = str(product.id)
        collection_id_val = collection_name  # must match payload collection_id stored at index time
        if not all([workspace_id_val, product_id_val, version_to_use is not None, collection_id_val]):
            missing = []
            if not workspace_id_val:
                missing.append("workspace_id")
            if not product_id_val:
                missing.append("product_id")
            if version_to_use is None:
                missing.append("version")
            if not collection_id_val:
                missing.append("collection_id")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Playground search requires mandatory filters; missing: {', '.join(missing)}.",
            )

        # Get embedding configuration for the specific version being queried
        # Priority: PipelineRun metrics > Collection dimension > Product config (with validation)
        from ..indexing.embeddings import EmbeddingGenerator
        from ..db.models import PipelineRun
        
        # Try to get embedding_config from PipelineRun for this version
        version_embedding_config = None
        pipeline_run = None
        if version_to_use:
            pipeline_run = db.query(PipelineRun).filter(
                PipelineRun.product_id == product.id,
                PipelineRun.version == version_to_use
            ).first()
            
            if pipeline_run and pipeline_run.metrics:
                # Check if embedding_config is stored in metrics
                indexing_stage = pipeline_run.metrics.get("aird_stages", {}).get("indexing", {})
                if indexing_stage:
                    # Try to get from stage metrics
                    embedding_model = indexing_stage.get("metrics", {}).get("embedding_model")
                    if embedding_model:
                        # We have the model name, need to get dimension
                        from ..core.embedding_config import get_embedding_model_config
                        model_config = get_embedding_model_config(embedding_model)
                        if model_config:
                            version_embedding_config = {
                                "embedder_name": embedding_model,
                                "embedding_dimension": model_config.dimension
                            }
                            logger.info(
                                f"Found embedding config from PipelineRun v{version_to_use}: "
                                f"{version_embedding_config['embedder_name']} ({version_embedding_config['embedding_dimension']} dims)"
                            )
        
        # Get collection info to determine actual dimension (source of truth)
        collection_info = qdrant_client.get_collection_info(collection_name)
        if not collection_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Collection {collection_name} not found or could not be accessed."
            )
        
        # Get the actual dimension from the collection (source of truth)
        # get_collection_info returns: {"config": {"vector_size": 1024, "distance": "Cosine"}}
        stored_dimension = collection_info.get("config", {}).get("vector_size")
        if not stored_dimension:
            # Fallback: try alternative paths (for backward compatibility)
            stored_dimension = collection_info.get("config", {}).get("params", {}).get("vectors", {}).get("size")
        
        if not stored_dimension:
            # Last resort: try top-level vector_size (shouldn't happen but be safe)
            stored_dimension = collection_info.get("vector_size")
        
        if not stored_dimension:
            # Log the actual structure for debugging
            logger.error(f"Collection info structure: {collection_info}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Could not determine vector dimension for collection {collection_name}. Collection info keys: {list(collection_info.keys()) if collection_info else 'None'}"
            )
        
        logger.info(f"Collection {collection_name} uses dimension {stored_dimension}")
        
        # Get current product embedding config (for comparison)
        product_embedding_config = product.embedding_config or {}
        product_model_name = product_embedding_config.get("embedder_name", "minilm")
        product_dimension = product_embedding_config.get("embedding_dimension", 384)
        
        # Determine which embedding config to use
        use_version_config = False
        embedding_config_to_use = None
        
        if version_embedding_config:
            # We have version-specific config - validate it matches collection
            version_dimension = version_embedding_config.get("embedding_dimension")
            if version_dimension == stored_dimension:
                # Perfect match - use version config
                embedding_config_to_use = version_embedding_config
                use_version_config = True
                logger.info(
                    f"✅ Using embedding config from PipelineRun v{version_to_use}: "
                    f"{embedding_config_to_use['embedder_name']} (matches collection dimension {stored_dimension})"
                )
            else:
                logger.warning(
                    f"⚠️ Version embedding config dimension ({version_dimension}) doesn't match collection ({stored_dimension}). "
                    f"Will use collection dimension to determine model."
                )
        
        # If we don't have version config or it doesn't match, determine from collection dimension
        if not embedding_config_to_use:
            # Map dimension to model (fallback - not ideal but necessary for backward compatibility)
            dimension_to_model = {
                384: "minilm",
                768: "mpnet",
                1024: "e5-large",
            }
            
            model_name = dimension_to_model.get(stored_dimension)
            
            if not model_name:
                # Unknown dimension - try to find matching model from registry
                logger.warning(f"Dimension {stored_dimension} not in standard mapping. Searching registry...")
                from ..core.embedding_config import EmbeddingModelRegistry
                registry = EmbeddingModelRegistry()
                matching_model = None
                for model_id, model_config in registry.models.items():
                    if model_config.dimension == stored_dimension:
                        matching_model = model_id
                        break
                
                if matching_model:
                    model_name = matching_model
                    logger.info(f"Found matching model for dimension {stored_dimension}: {model_name}")
                else:
                    # No matching model found
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            f"Collection '{collection_name}' uses dimension {stored_dimension}, "
                            f"but no matching embedding model found. "
                            f"Product is configured for {product_model_name} (dimension {product_dimension}). "
                            f"Please re-index the collection with a supported embedding model."
                        )
                    )
            
            embedding_config_to_use = {
                "embedder_name": model_name,
                "embedding_dimension": stored_dimension
            }
            logger.info(
                f"Using dimension-based model lookup: {model_name} (dimension {stored_dimension}) "
                f"to match collection {collection_name}"
            )
        
        # STRICT MODE: Check if product config differs from collection config
        # This prevents silent mismatches
        compat_mode = query_data.compat_mode or (query_data.use == "current")  # Allow compat mode for current version queries
        strict_mode = query_data.use == "prod" and not query_data.compat_mode  # Strict mode for production queries
        
        if strict_mode and not use_version_config:
            # Production queries should use the exact config that was used to index
            if product_dimension != stored_dimension:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Configuration mismatch: Production collection (v{version_to_use}) was indexed with "
                        f"dimension {stored_dimension} ({embedding_config_to_use['embedder_name']}), "
                        f"but product is currently configured for dimension {product_dimension} ({product_model_name}). "
                        f"To fix: Either re-index and promote a new version with the current configuration, "
                        f"or update the product configuration to match the production collection. "
                        f"Query will use {embedding_config_to_use['embedder_name']} to match the collection."
                    )
                )
        elif product_dimension != stored_dimension:
            # Log warning but allow (compat mode for current version)
            logger.warning(
                f"⚠️ Dimension mismatch: Collection uses {stored_dimension} ({embedding_config_to_use['embedder_name']}), "
                f"but product config specifies {product_dimension} ({product_model_name}). "
                f"Using collection's dimension for query compatibility."
            )

        validate_embedding_config_for_workspace(db, product.workspace_id, embedding_config_to_use)

        # Generate query embedding using the determined config
        model_name = embedding_config_to_use["embedder_name"]
        dimension = embedding_config_to_use["embedding_dimension"]
        
        logger.info(
            f"Generating query embedding using model {model_name} with dimension {dimension} "
            f"to match collection {collection_name}"
        )
        
        embedding_generator = EmbeddingGenerator(
            model_name=model_name, dimension=dimension, workspace_id=product.workspace_id, db=db
        )

        # Check which model is actually being used
        model_info = embedding_generator.get_model_info()
        logger.info(f"Query embedding model info: {model_info}")

        if model_info.get("fallback_mode"):
            logger.warning(f"⚠️ CRITICAL: Query embedding is using hash-based fallback! Search results will be poor.")
            logger.warning(
                f"Model: {model_name}, is_openai: {model_info.get('is_openai')}, fallback_mode: {model_info.get('fallback_mode')}"
            )
        else:
            logger.info(f"✅ Query embedding using {model_info.get('model_type')} model (not fallback)")

        query_embedding = embedding_generator.embed(query_data.query)
        query_dimension = len(query_embedding)
        logger.info(f"Generated query embedding with dimension {query_dimension}")
        
        # Final validation - should always match now
        if query_dimension != stored_dimension:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    f"Embedding dimension mismatch: Generated query embedding has dimension {query_dimension}, "
                    f"but collection requires {stored_dimension}. This should not happen - please report this error."
                )
            )
        
        logger.info(f"✅ Query embedding dimension ({query_dimension}) matches collection dimension ({stored_dimension})")

        # Expand query terms for keyword boosting
        query_terms = expand_query_terms(query_data.query)
        logger.debug(f"Expanded query terms: {query_terms}")

        # Mandatory filter for every search (ensures no cross-product/workspace/version/collection results)
        mandatory_filter = {
            "workspace_id": workspace_id_val,
            "product_id": product_id_val,
            "version": version_to_use,
            "collection_id": collection_id_val,
        }

        # Optional filters and ACL (merged into flat dict for Qdrant _build_filter)
        acl_applied = False
        filter_parts = []

        # Apply optional user filters
        if query_data.filter_product_id:
            if query_data.filter_product_id != str(product.id):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"filter_product_id ({query_data.filter_product_id}) must match query product_id ({product.id})"
                )
            filter_parts.append({"key": "product_id", "match": {"value": query_data.filter_product_id}})
        
        if query_data.filter_version:
            filter_parts.append({"key": "version", "match": {"value": query_data.filter_version}})
        
        if query_data.filter_doc_scope:
            filter_parts.append({"key": "doc_scope", "match": {"value": query_data.filter_doc_scope}})
        
        if query_data.filter_field_scope:
            filter_parts.append({"key": "field_scope", "match": {"value": query_data.filter_field_scope}})

        # Apply ACL filtering (M5) - using Qdrant as single source of truth
        try:
            from ..services.acl import apply_acl_filter_to_payloads, get_acls_for_user, get_allowed_chunk_ids_from_payloads

            # Get user's ACLs for this product
            user_id = get_user_id(current_user)
            user_acls = get_acls_for_user(db, user_id, product.id)

            if user_acls:
                # Get all points from Qdrant for this product/version (using scroll API)
                # Use mandatory filter so scroll is scoped to same workspace/product/version/collection
                qdrant_filter = dict(mandatory_filter)

                # Scroll through all points to get chunk metadata
                all_points = []
                offset = None
                scroll_limit = 1000  # Process in batches

                while True:
                    scroll_result = qdrant_client.scroll_points(
                        collection_name=collection_name,
                        limit=scroll_limit,
                        offset=offset,
                        filter_conditions=qdrant_filter,
                        with_payload=True,
                        with_vector=False,
                    )

                    points = scroll_result.get("points", [])
                    all_points.extend(points)

                    offset = scroll_result.get("next_page_offset")
                    if not offset or len(points) < scroll_limit:
                        break

                logger.info(f"Retrieved {len(all_points)} points from Qdrant for ACL filtering")

                # Apply ACL filter to Qdrant payloads
                allowed_payloads = apply_acl_filter_to_payloads(all_points, user_acls, product.id)
                allowed_chunk_ids = get_allowed_chunk_ids_from_payloads(allowed_payloads)

                if allowed_chunk_ids:
                    # Add ACL filter to filter_parts
                    filter_parts.append({"key": "chunk_id", "match": {"any": list(allowed_chunk_ids)}})
                    acl_applied = True
                    logger.info(f"ACL filtering applied: {len(allowed_chunk_ids)} chunks allowed")
                else:
                    # No chunks allowed - return empty results
                    logger.warning(f"ACL filtering: no chunks allowed for user {user_id}")
                    return PlaygroundResponse(
                        results=[],
                        latency_ms=(time.time() - start_time) * 1000,
                        collection_name=collection_name,
                        total_results=0,
                        acl_applied=True,
                    )
        except Exception as e:
            logger.warning(f"ACL filtering failed, proceeding without filter: {e}", exc_info=True)
            # Continue without ACL filtering if there's an error

        # Build final filter: mandatory + optional/ACL as flat dict (Qdrant _build_filter expects key -> value or key -> list)
        filter_conditions = dict(mandatory_filter)
        for part in filter_parts:
            key = part["key"]
            match = part.get("match") or {}
            if "any" in match:
                filter_conditions[key] = match["any"]
            else:
                filter_conditions[key] = match.get("value")
        logger.info(f"Applied filters (mandatory + optional): {filter_conditions}")

        # --- Reranking pipeline: dense retrieval -> optional BM25 merge -> cross-encoder rerank -> top_n ---
        settings = get_settings()
        dense_top_k = settings.DENSE_RETRIEVAL_TOP_K  # 50
        rerank_top_k = settings.RERANK_TOP_K  # 5
        use_bm25 = getattr(settings, "USE_BM25", False)
        bm25_top_k = getattr(settings, "BM25_TOP_K", 50)

        logger.info(
            "Qdrant search: collection_name=%s, final_filter=%s",
            collection_name,
            json.dumps(filter_conditions, default=str),
        )
        logger.info(f"Playground pipeline: dense_top_k={dense_top_k}, rerank_top_k={rerank_top_k}, use_bm25={use_bm25}")
        reranker_used = False
        try:
            # 1) Dense retrieval from Qdrant (top_k=50)
            search_results = qdrant_client.search_points(
                collection_name=collection_name,
                query_vector=query_embedding.tolist(),
                limit=dense_top_k,
                score_threshold=0.0,
                filter_conditions=filter_conditions,
            )
            logger.info(f"Dense retrieval: {len(search_results)} candidates")

            # 2) Optional BM25 retrieval and merge (stub: no sparse index yet)
            bm25_results = []
            if use_bm25:
                try:
                    # Placeholder: when sparse/BM25 is available on Qdrant, call it and merge by chunk_id
                    # bm25_results = qdrant_client.search_points_bm25(..., limit=bm25_top_k)
                    pass
                except Exception as e:
                    logger.debug("BM25 retrieval skipped: %s", e)
            merged_by_chunk: Dict[str, dict] = {}
            for r in search_results:
                payload = r.get("payload", {})
                chunk_id = payload.get("chunk_id") or r.get("id")
                key = str(chunk_id)
                if key not in merged_by_chunk or (r.get("score", 0) > merged_by_chunk[key].get("score", 0)):
                    merged_by_chunk[key] = {
                        "id": r.get("id"),
                        "payload": payload,
                        "score": float(r.get("score", 0.0)),
                        "text": payload.get("text", ""),
                    }
            for r in bm25_results:
                payload = r.get("payload", {})
                chunk_id = payload.get("chunk_id") or r.get("id")
                key = str(chunk_id)
                if key not in merged_by_chunk:
                    merged_by_chunk[key] = {
                        "id": r.get("id"),
                        "payload": payload,
                        "score": float(r.get("score", 0.0)),
                        "text": payload.get("text", ""),
                    }
            candidates = list(merged_by_chunk.values())
            candidates.sort(key=lambda x: x["score"], reverse=True)

            # 3) Cross-encoder rerank merged candidates, return top_n
            if candidates and rerank_top_k > 0:
                try:
                    rerank_candidates(
                        query_data.query,
                        candidates,
                        text_key="text",
                        model_name=settings.RERANKER_NAME,
                        batch_size=32,
                    )
                    reranker_used = all("rerank_score" in c for c in candidates[: min(len(candidates), rerank_top_k * 2)])
                    final_n = min(rerank_top_k, query_data.top_k) if query_data.top_k else rerank_top_k
                    candidates = candidates[: final_n]
                except Exception as e:
                    logger.warning("Reranking failed, using vector order: %s", e)
                    candidates = candidates[: max(rerank_top_k, query_data.top_k)]
            else:
                final_n = min(rerank_top_k, query_data.top_k) if query_data.top_k else max(rerank_top_k, query_data.top_k)
                candidates = candidates[: final_n]

            logger.info(f"Returning top {len(candidates)} results (reranker_used={reranker_used})")

            # Log retrieval debug
            logger.info(
                "Playground retrieval: query=%s, collection=%s, candidates=%s, reranker_used=%s",
                query_data.query[:80],
                collection_name,
                len(candidates),
                reranker_used,
            )
        except ConnectionError as e:
            logger.error(f"Qdrant connection error during search: {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Vector database connection failed: {str(e)}"
            )
        except RuntimeError as e:
            logger.error(f"Search operation failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Search failed: {str(e)}"
            )
        except Exception as e:
            logger.error(f"Unexpected error during search: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Search operation failed: {str(e)}"
            )

        # Build response: vector_score + rerank_score for UI
        minio_client = MinIOClient()
        results = []
        for c in candidates:
            payload = c.get("payload", {})
            text = payload.get("text", "")
            filename = payload.get("filename", "")
            source_file = payload.get("source_file", filename)
            chunk_index = payload.get("chunk_index", 0)
            chunk_id = payload.get("chunk_id", "")
            page = payload.get("page", 0)
            section = payload.get("section", "general")
            token_est = payload.get("token_est", 0)
            text_length = payload.get("text_length", len(text))
            is_truncated = text_length > len(text)
            vector_score = c.get("score")
            rerank_score_val = c.get("rerank_score")
            final_score = float(rerank_score_val) if rerank_score_val is not None else float(vector_score or 0.0)

            presigned_url = None
            if filename or source_file:
                try:
                    from primedata.storage.paths import clean_prefix
                    file_to_use = source_file if source_file else filename
                    if not file_to_use.startswith("ws/"):
                        clean_path_prefix = clean_prefix(
                            workspace_id=product.workspace_id, product_id=product.id, version=version_to_use
                        )
                        file_to_use = f"{clean_path_prefix}{file_to_use}"
                    presigned_url = minio_client.presign(
                        bucket="primedata-clean",
                        key=file_to_use,
                        expiry=3600,
                        inline=True,
                    )
                except Exception as e:
                    logger.debug("Presign failed for %s: %s", filename, e)
            section_label = f"{section}"
            if page:
                section_label += f" (Page {page})"
            if token_est:
                section_label += f" - {token_est} tokens"

            results.append(
                PlaygroundResult(
                    text=text,
                    score=final_score,
                    doc_path=filename or source_file,
                    section=section_label,
                    meta={
                        "chunk_id": chunk_id,
                        "chunk_index": chunk_index,
                        "filename": filename,
                        "source_file": source_file,
                        "page": page,
                        "section": section,
                        "token_est": token_est,
                        "text_length": text_length,
                        "is_truncated": is_truncated,
                        "product_id": payload.get("product_id"),
                    },
                    presigned_url=presigned_url,
                    vector_score=float(vector_score) if vector_score is not None else None,
                    rerank_score=float(rerank_score_val) if rerank_score_val is not None else None,
                )
            )

        latency_ms = (time.time() - start_time) * 1000
        return PlaygroundResponse(
            results=results,
            latency_ms=latency_ms,
            collection_name=collection_name,
            total_results=len(results),
            acl_applied=acl_applied,
            reranker_used=reranker_used,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Playground query failed: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Query failed: {str(e)}")


@router.post("/api/v1/playground/context", response_model=ContextAssemblyResponse)
async def assemble_context(
    payload: ContextAssemblyRequest,
    request: Request,
    current_user: dict = Depends(get_current_user_from_request),
    db=Depends(get_db),
):
    """
    Assemble a context window for a product by fetching chunks from Qdrant,
    deduplicating near-duplicates, ordering by source/page, and trimming to a token budget.
    """
    from uuid import UUID
    import math
    from datetime import datetime, timezone

    product = ensure_product_access(db=db, request=request, product_id=UUID(payload.product_id))
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found or access denied")

    qdrant_client = QdrantClient()
    if not qdrant_client.is_connected():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Vector database connection failed")

    # Resolve version/collection (reuse latest successful run for current)
    if payload.use == "prod":
        if not product.promoted_version:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No production version available.")
        version_to_use = product.promoted_version
        collection_name = qdrant_client.get_prod_alias_collection(
            workspace_id=str(product.workspace_id), product_id=str(product.id), product_name=product.name
        )
        if not collection_name:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Production alias not found.")
    else:
        latest_successful_version = get_latest_successful_pipeline_version(db, product.id)
        if not latest_successful_version:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No successful pipeline runs found. Please run a pipeline first to index data.",
            )
        version_to_use = latest_successful_version
        collection_name = qdrant_client.find_collection_name(
            workspace_id=str(product.workspace_id),
            product_id=str(product.id),
            version=version_to_use,
            product_name=product.name,
        )
        if not collection_name:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Collection not found for version {version_to_use}. Please run a pipeline first.",
            )

    # Fetch chunks via scroll (payload includes product_id/version/collection_id)
    collected: List[Dict[str, Any]] = []
    next_offset = None
    while len(collected) < payload.top_k and (next_offset is None or next_offset):
        scroll = qdrant_client.scroll_points(
            collection_name=collection_name,
            limit=payload.top_k * 3,  # oversample for dedup
            offset=next_offset,
            filter_conditions={
                "product_id": str(product.id),
                "version": version_to_use,
                "collection_id": collection_name,
            },
            with_payload=True,
            with_vector=False,
        )
        collected.extend(scroll.get("points", []))
        next_offset = scroll.get("next_page_offset")
        if not scroll.get("points"):
            break

    # Deduplicate simple exact/near-exact based on normalized text
    seen = set()
    selected = []
    for point in collected:
        payload_meta = point.get("payload", {}) or {}
        text = payload_meta.get("text", "")
        if not text:
            continue
        norm = re.sub(r"\s+", " ", text.strip().lower())
        if norm in seen:
            continue
        seen.add(norm)
        selected.append((point, payload_meta, text))
        if len(selected) >= payload.top_k:
            break

    # Order by source_file then page_number where available
    selected.sort(key=lambda tup: (tup[1].get("source_file") or "", tup[1].get("page_number") or 0))

    def freshness_score(meta: Dict[str, Any]) -> Optional[float]:
        ts = meta.get("created_at") or meta.get("timestamp")
        if not ts:
            return None
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00")) if isinstance(ts, str) else ts
            age_days = (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0
            # half-life 365 days
            return round(100 * math.pow(0.5, age_days / 365.0), 1)
        except Exception:
            return None

    chunks: List[ContextChunk] = []
    total_tokens = 0
    for point, meta, text in selected:
        # crude token estimate: 4 chars ~ 1 token
        est_tokens = max(1, len(text) // 4)
        if total_tokens + est_tokens > payload.max_tokens and chunks:
            break
        total_tokens += est_tokens
        f_score = freshness_score(meta)
        chunks.append(
            ContextChunk(
                chunk_id=meta.get("chunk_id"),
                source_file=meta.get("source_file"),
                page_number=meta.get("page_number") or meta.get("page"),
                score=meta.get("score"),
                freshness=f_score,
                text=text,
            )
        )

    freshness_values = [c.freshness for c in chunks if c.freshness is not None]
    freshness_summary = {
        "min": min(freshness_values) if freshness_values else None,
        "avg": round(sum(freshness_values) / len(freshness_values), 1) if freshness_values else None,
        "max": max(freshness_values) if freshness_values else None,
    }

    assembled_text = "\n\n".join(c.text for c in chunks)

    return ContextAssemblyResponse(
        assembled_text=assembled_text,
        chunks=chunks,
        freshness_summary=freshness_summary,
        deduped_count=len(collected) - len(chunks),
        conflicts_flagged=0,  # heuristic conflict detection not implemented yet
        collection_name=collection_name,
    )


@router.get("/api/v1/playground/status/{product_id}")
async def get_playground_status(
    product_id: str, request: Request, current_user: dict = Depends(get_current_user_from_request), db=Depends(get_db)
):
    """
    Get the playground status for a product (whether it's ready for queries).
    """
    try:
        # Ensure user has access to the product
        from uuid import UUID

        product = ensure_product_access(db=db, request=request, product_id=UUID(product_id))

        if not product:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found or access denied")

        # Get latest successful pipeline run version (not just current_version which might be stale)
        latest_successful_version = get_latest_successful_pipeline_version(db, product.id)
        
        if not latest_successful_version or latest_successful_version <= 0:
            return {
                "ready": False,
                "reason": "No successful pipeline runs found. Please run a pipeline first to index data.",
                "current_version": product.current_version,
                "latest_successful_version": None,
                "promoted_version": product.promoted_version,
            }

        # Check if collection exists in Qdrant
        qdrant_client = QdrantClient()
        if not qdrant_client.is_connected():
            return {
                "ready": False,
                "reason": "Vector database connection failed",
                "current_version": product.current_version,
                "latest_successful_version": latest_successful_version,
                "promoted_version": product.promoted_version,
            }

        # Find collection name (checks both product name and product_id formats for backward compatibility)
        collection_name = qdrant_client.find_collection_name(
            workspace_id=str(product.workspace_id),
            product_id=str(product.id),
            version=latest_successful_version,
            product_name=product.name,
        )

        # If find_collection_name didn't find it, try to get collection info directly
        # This handles cases where list_collections() might not be up-to-date
        if not collection_name:
            # Try both naming formats directly
            if product.name:
                sanitized_name = qdrant_client._sanitize_collection_name(product.name)
                collection_name_candidate = f"ws_{product.workspace_id}__{sanitized_name}__v_{latest_successful_version}"
                # Try to get collection info directly - if it exists, this will succeed
                collection_info = qdrant_client.get_collection_info(collection_name_candidate)
                if collection_info and collection_info.get("points_count", 0) > 0:
                    collection_name = collection_name_candidate
            
            # If still not found, try product_id format
            if not collection_name:
                collection_name_candidate = f"ws_{product.workspace_id}__prod_{product.id}__v_{latest_successful_version}"
                collection_info = qdrant_client.get_collection_info(collection_name_candidate)
                if collection_info and collection_info.get("points_count", 0) > 0:
                    collection_name = collection_name_candidate

        if not collection_name:
            return {
                "ready": False,
                "reason": f"Collection not found for version {latest_successful_version}. Please run a pipeline first.",
                "current_version": product.current_version,
                "latest_successful_version": latest_successful_version,
                "promoted_version": product.promoted_version,
            }

        # Get collection info
        collection_info = qdrant_client.get_collection_info(collection_name)
        
        # Handle case where collection_info is None (e.g., version mismatch or collection doesn't exist)
        if collection_info is None:
            logger.warning(f"Could not retrieve collection info for {collection_name}. This may indicate a Qdrant version mismatch.")
            return {
                "ready": False,
                "current_version": product.current_version,
                "latest_successful_version": latest_successful_version,
                "promoted_version": product.promoted_version,
                "collection_name": collection_name,
                "points_count": 0,
                "vectors_count": 0,
                "reason": "Could not retrieve collection information. Check Qdrant server and client version compatibility.",
            }

        # Check if collection has any points
        points_count = collection_info.get("points_count", 0)
        if points_count == 0:
            return {
                "ready": False,
                "reason": "Collection exists but has no indexed data. Please run a pipeline first.",
                "current_version": product.current_version,
                "latest_successful_version": latest_successful_version,
                "promoted_version": product.promoted_version,
                "collection_name": collection_name,
                "points_count": 0,
                "vectors_count": 0,
            }

        return {
            "ready": True,
            "current_version": product.current_version,  # Keep for backward compatibility
            "latest_successful_version": latest_successful_version,  # The version actually being used
            "promoted_version": product.promoted_version,
            "collection_name": collection_name,
            "points_count": points_count,
            "vectors_count": collection_info.get("vectors_count", 0),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Playground status check failed: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Status check failed: {str(e)}")
