"""
AIRD indexing stage for PrimeData.

Ports AIRD FAISS indexing logic to Qdrant, with metadata tracking.
"""

import json
import hashlib
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

import numpy as np
from loguru import logger
from primedata.indexing.embeddings import EmbeddingGenerator

# Metadata is now stored in Qdrant payload - no PostgreSQL metadata tables needed
from primedata.indexing.qdrant_client import qdrant_client
from primedata.ingestion_pipeline.aird_stages.base import AirdStage, StageResult, StageStatus
from primedata.services.trust_scoring import get_scoring_weights
from primedata.services.lineage import record_lineage, record_dq_finding
from primedata.db.models import LineageType, RuleSeverity


def load_metrics_index(metrics: List[Dict[str, Any]]) -> Dict[str, Dict]:
    """
    Build lookups from metrics:
      - by_chunk[(file, chunk_id)] -> score
      - by_chunk_any[chunk_id] -> score (file-agnostic fallback)
      - by_section[(file, section)] -> score
      - by_file[file] -> max score
    """
    idx = {"by_chunk": {}, "by_chunk_any": {}, "by_section": {}, "by_file": {}}

    if not metrics:
        logger.warning("No metrics provided — scores will default to 0.0")
        return idx

    for m in metrics:
        file = m.get("file")
        score = float(m.get("AI_Trust_Score", 0.0))
        cid = m.get("chunk_id")
        sec = m.get("section")

        if file and cid:
            idx["by_chunk"][(file, cid)] = score
        if cid:
            idx["by_chunk_any"][cid] = score
        if file and sec:
            idx["by_section"][(file, sec)] = score
        if file:
            idx["by_file"][file] = max(score, idx["by_file"].get(file, 0.0))

    return idx


def lookup_score(
    metrics_idx: Dict[str, Dict],
    file_name: str,
    rec: Dict[str, Any],
    alt_files: List[str],
) -> float:
    """Find the best available score for a record using multiple fallbacks."""
    cid = rec.get("chunk_id")
    sec = rec.get("section")

    # 1) exact file+chunk
    if cid and (file_name, cid) in metrics_idx["by_chunk"]:
        return metrics_idx["by_chunk"][(file_name, cid)]

    # 2) try alternate file tags (jsonl/json/txt)
    for f in alt_files:
        if cid and (f, cid) in metrics_idx["by_chunk"]:
            return metrics_idx["by_chunk"][(f, cid)]
        if sec and (f, sec) in metrics_idx["by_section"]:
            return metrics_idx["by_section"][(f, sec)]

    # 3) chunk-only fallback
    if cid and cid in metrics_idx["by_chunk_any"]:
        return metrics_idx["by_chunk_any"][cid]

    # 4) section/file or file-only fallback
    if sec and (file_name, sec) in metrics_idx["by_section"]:
        return metrics_idx["by_section"][(file_name, sec)]

    return metrics_idx["by_file"].get(file_name, 0.0)


class IndexingStage(AirdStage):
    """Indexing stage that embeds chunks and stores them in Qdrant with metadata."""

    @property
    def stage_name(self) -> str:
        return "indexing"

    def get_required_artifacts(self) -> list[str]:
        """Indexing requires processed JSONL files and metrics."""
        return ["processed_jsonl", "metrics_json"]

    def execute(self, context: Dict[str, Any]) -> StageResult:
        """Execute indexing stage.

        Args:
            context: Stage execution context with:
                - storage: AirdStorageAdapter
                - processed_files: List of processed file stems
                - scoring_result: Optional result from scoring stage

        Returns:
            StageResult with indexing metrics
        """
        started_at = datetime.utcnow()
        pr = context.get("pipeline_run")
        self.pipeline_run_id = pr.id if pr is not None else None

        storage = context.get("storage")
        processed_files = context.get("processed_files", [])

        if not storage:
            return self._create_result(
                status=StageStatus.FAILED,
                metrics={},
                error="Storage adapter not found in context",
                started_at=started_at,
            )

        if not processed_files:
            # Try to get from previous stage
            preprocess_result = context.get("preprocess_result")
            if preprocess_result and preprocess_result.get("processed_file_list"):
                processed_files = preprocess_result["processed_file_list"]
            else:
                self.logger.warning("No processed files to index")
                return self._create_result(
                    status=StageStatus.SKIPPED,
                    metrics={"reason": "no_processed_files"},
                    started_at=started_at,
                )

        self.logger.info(f"Starting indexing for {len(processed_files)} files")

        # Structured log: chunking_config received (must be from resolver resolved_settings when mode=auto + force)
        chunking_config = context.get("chunking_config")
        if chunking_config and isinstance(chunking_config, dict):
            rs = chunking_config.get("resolved_settings") or {}
            self.logger.info(
                "[CHUNKING_CONFIG] indexing stage received: chunk_size=%s chunk_overlap=%s "
                "chunking_strategy=%s content_type=%s (chunks already created by preprocess using this config)",
                rs.get("chunk_size"),
                rs.get("chunk_overlap"),
                rs.get("chunking_strategy"),
                rs.get("content_type"),
            )
        else:
            self.logger.info("[CHUNKING_CONFIG] indexing stage received: chunking_config=%s", type(chunking_config).__name__ if chunking_config else None)

        # Get database from context (should be provided by get_aird_context)
        db = context.get("db")
        if not db:
            from primedata.db.database import SessionLocal

            db = SessionLocal()
            close_db = True
        else:
            close_db = False

        try:
            # Load metrics for score lookup
            metrics = storage.get_metrics_json()
            metrics_idx = load_metrics_index(metrics) if metrics else {}

            # Get embedding generator from product config or use default
            from primedata.db.models import Product

            product = db.query(Product).filter(Product.id == self.product_id).first()
            if not product:
                if close_db:
                    db.close()
                return self._create_result(
                    status=StageStatus.FAILED,
                    metrics={},
                    error=f"Product {self.product_id} not found",
                    started_at=started_at,
                )

            # Get embedding config
            embedding_config = product.embedding_config or {}
            model_name = embedding_config.get("embedder_name", "minilm")
            dimension = embedding_config.get("embedding_dimension", 384)

            # Initialize embedding generator with workspace context for API keys
            embedder = EmbeddingGenerator(model_name=model_name, dimension=dimension, workspace_id=self.workspace_id, db=db)
            actual_dimension = embedder.get_dimension()

            # Check if we're using hash-based fallback (which won't give good semantic search results)
            model_info = embedder.get_model_info()
            if model_info.get("fallback_mode"):
                self.logger.error(
                    f"CRITICAL: Embedding model {model_name} is using hash-based fallback. "
                    f"Semantic search will NOT work correctly - results will be random. "
                    f"Check that the API key is configured for OpenAI models or sentence_transformers is installed."
                )
                # Still proceed but log the issue prominently
            else:
                self.logger.info(
                    f"Embedding model {model_name} loaded successfully. "
                    f"Model type: {model_info.get('model_type', 'unknown')}, "
                    f"Dimension: {actual_dimension}"
                )

            # Create Qdrant collection name using product name for better readability
            self.logger.info(f"Product name from database: '{product.name}'")
            sanitized_product_name = qdrant_client._sanitize_collection_name(product.name)
            self.logger.info(f"Sanitized product name for collection: '{sanitized_product_name}'")
            
            # Use pipeline_run.version (pipeline_run_version, e.g., 8) instead of self.version (raw_file_version, e.g., 7)
            # This ensures the collection name matches the actual pipeline run version
            pipeline_run = context.get("pipeline_run")
            if pipeline_run and pipeline_run.version:
                collection_version = pipeline_run.version
                self.logger.info(
                    f"Using pipeline_run.version={collection_version} for collection name "
                    f"(instead of raw_file_version={self.version})"
                )
            else:
                # Fallback to self.version if pipeline_run not available (shouldn't happen, but safe)
                collection_version = self.version
                self.logger.warning(
                    f"pipeline_run not found in context, falling back to raw_file_version={self.version}. "
                    f"This may result in incorrect collection naming."
                )
            
            collection_name = f"ws_{self.workspace_id}__{sanitized_product_name}__v_{collection_version}"
            self.logger.info(f"Creating Qdrant collection: '{collection_name}'")

            if not qdrant_client.is_connected():
                return self._create_result(
                    status=StageStatus.FAILED,
                    metrics={},
                    error="Qdrant client not connected",
                    started_at=started_at,
                )

            collection_created = qdrant_client.ensure_collection(collection_name, actual_dimension)
            if not collection_created:
                if close_db:
                    db.close()
                return self._create_result(
                    status=StageStatus.FAILED,
                    metrics={},
                    error=(
                        f"Failed to create Qdrant collection '{collection_name}'. "
                        f"This usually indicates a Qdrant server resource limit issue (check 'too many open files' in Qdrant logs). "
                        f"Ensure Qdrant container has ulimits.nofile set to at least 65536."
                    ),
                    started_at=started_at,
                )

            # Process all files - collect all records first, then batch-embed
            all_records_data = []  # Store record data for batch processing
            total_chunks = 0

            # First pass: Collect all records and their metadata
            for file_stem in processed_files:
                try:
                    # Load processed JSONL
                    records = storage.get_processed_jsonl(file_stem)
                    if not records:
                        self.logger.warning(f"Processed JSONL not found for {file_stem}, skipping")
                        continue

                    processed_file = f"{file_stem}.jsonl"
                    alt_files = [processed_file, f"{file_stem}.json", f"{file_stem}.txt"]

                    # Process each record to collect data
                    for rec in records:
                        if not isinstance(rec, dict):
                            continue

                        text = rec.get("text", "")
                        if not text.strip():
                            continue

                        # Extract metadata
                        chunk_id = rec.get("chunk_id") or f"{file_stem}_{rec.get('section', 'general')}"
                        section = rec.get("section", "general")
                        field_name = rec.get("field_name", section)
                        page = rec.get("page")
                        document_id = rec.get("document_id") or rec.get("doc_scope") or file_stem
                        tags = rec.get("tags", "")

                        # Lookup score
                        score = lookup_score(metrics_idx, processed_file, rec, alt_files)

                        # Store record data for batch embedding
                        all_records_data.append(
                            {
                                "text": text,
                                "chunk_id": chunk_id,
                                "filename": processed_file,
                                "document_id": document_id,
                                "page": page,
                                "section": section,
                                "field_name": field_name,
                                "tags": tags,
                                "score": score,
                                "rec": rec,  # Store full record for metadata creation
                            }
                        )

                        total_chunks += 1

                except Exception as e:
                    self.logger.error(f"Failed to process {file_stem}: {e}", exc_info=True)
                    continue

            if not all_records_data:
                return self._create_result(
                    status=StageStatus.FAILED,
                    metrics={},
                    error="No records to index",
                    started_at=started_at,
                )

            # Log total chunks to process
            total_chunks = len(all_records_data)
            avg_chunk_length = sum(len(r["text"]) for r in all_records_data) / total_chunks if total_chunks > 0 else 0
            self.logger.info(
                f"📊 Total chunks to process: {total_chunks}, " f"average chunk length: {avg_chunk_length:.0f} characters"
            )

            # Batch embed all texts for performance (especially important for OpenAI API)
            # Adaptive batch size based on model dimension to prevent memory issues
            # Large models (>=1024 dim) need very small batches, smaller models can handle larger batches
            model_dimension = actual_dimension
            if model_dimension >= 1024:
                # For very large models like BGE Large, use very small batches to avoid timeout
                # With thousands of chunks, even small batches can take hours
                embedding_batch_size = 3  # Very large models need tiny batches to complete in reasonable time
            elif model_dimension >= 768:
                embedding_batch_size = 15  # Large models need medium batches
            else:
                embedding_batch_size = 100  # Smaller models can handle larger batches

            # Estimate processing time (rough estimate: 10-20 seconds per batch for large models)
            total_batches = (total_chunks + embedding_batch_size - 1) // embedding_batch_size
            if model_dimension >= 1024:
                estimated_minutes = total_batches * 0.5  # ~30 seconds per batch of 3 chunks
            elif model_dimension >= 768:
                estimated_minutes = total_batches * 0.3  # ~18 seconds per batch of 15 chunks
            else:
                estimated_minutes = total_batches * 0.1  # ~6 seconds per batch of 100 chunks

            self.logger.info(
                f"Generating embeddings for {total_chunks} chunks in batches of {embedding_batch_size} "
                f"(model dimension: {model_dimension}, {total_batches} batches, "
                f"estimated time: ~{estimated_minutes:.1f} minutes / ~{estimated_minutes/60:.1f} hours)..."
            )

            # Warn if processing will take a very long time
            if estimated_minutes > 60:
                self.logger.warning(
                    f"⚠️  WARNING: Embedding generation is estimated to take {estimated_minutes/60:.1f} hours. "
                    f"Consider using a faster model (e.g., minilm or e5-base) for large documents, "
                    f"or ensure the task has sufficient timeout (currently 2 hours)."
                )
            all_embeddings = []
            start_time = time.time()

            for i in range(0, len(all_records_data), embedding_batch_size):
                batch_start_time = time.time()
                batch_records = all_records_data[i : i + embedding_batch_size]
                batch_texts = [r["text"] for r in batch_records]
                batch_num = (i // embedding_batch_size) + 1
                total_batches = (len(all_records_data) + embedding_batch_size - 1) // embedding_batch_size

                # Log batch start with timing info
                elapsed = time.time() - start_time
                avg_time_per_batch = elapsed / max(batch_num - 1, 1)
                remaining_batches = total_batches - batch_num
                estimated_remaining = remaining_batches * avg_time_per_batch

                self.logger.info(
                    f"🔄 Embedding batch {batch_num}/{total_batches} ({len(batch_texts)} chunks, "
                    f"progress: {i}/{len(all_records_data)} chunks, "
                    f"elapsed: {elapsed:.1f}s, est. remaining: {estimated_remaining:.1f}s)..."
                )
                try:
                    # Use smaller internal batch size for sentence transformers to manage memory better
                    batch_embeddings = embedder.embed_batch(batch_texts, batch_size=embedding_batch_size)
                    all_embeddings.extend(batch_embeddings)
                    batch_time = time.time() - batch_start_time
                    self.logger.info(
                        f"✅ Generated {len(batch_embeddings)} embeddings for batch {batch_num}/{total_batches} "
                        f"in {batch_time:.1f}s ({batch_time/len(batch_texts):.2f}s per chunk)"
                    )
                except Exception as e:
                    self.logger.error(
                        f"Failed to generate embeddings for batch {batch_num}/{total_batches}: {e}", exc_info=True
                    )
                    # Fallback to individual embeddings for this batch
                    self.logger.warning(f"Falling back to individual embedding generation for batch {batch_num}")
                    for record_data in batch_records:
                        try:
                            embedding = embedder.embed(record_data["text"])
                            all_embeddings.append(embedding)
                        except Exception as emb_error:
                            self.logger.error(f"Failed to embed chunk {record_data['chunk_id']}: {emb_error}")
                            # Add None as placeholder - will skip this record
                            all_embeddings.append(None)

            # Second pass: Build points with embeddings
            all_points = []
            for idx, (record_data, embedding) in enumerate(zip(all_records_data, all_embeddings)):
                if embedding is None:
                    self.logger.warning(f"Skipping chunk {record_data['chunk_id']} due to embedding failure")
                    continue

                embedding_list = embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)

                # Create Qdrant point ID (use chunk_id hash for uniqueness)
                point_id_str = f"{self.product_id}_{record_data['chunk_id']}_{self.version}"
                point_id = int(hashlib.md5(point_id_str.encode()).hexdigest()[:15], 16)

                # Create Qdrant point
                # Store full text (Qdrant supports large payloads, typically up to 64KB per payload)
                max_text_length = 50000  # 50KB should be safe for Qdrant payloads
                stored_text = (
                    record_data["text"][:max_text_length]
                    if len(record_data["text"]) > max_text_length
                    else record_data["text"]
                )

                # Create Qdrant point with all metadata in payload (single source of truth)
                # All metadata is stored in Qdrant payload - no PostgreSQL metadata tables needed
                point = {
                    "id": point_id,
                    "vector": embedding_list,
                    "payload": {
                        "chunk_id": record_data["chunk_id"],
                        "filename": record_data["filename"],
                        "source_file": record_data["filename"],  # Alias for compatibility
                        "document_id": record_data["document_id"],
                        "page": record_data["page"],
                        "page_number": record_data["page"],  # Alias for compatibility
                        "section": record_data["section"],
                        "field_name": record_data["field_name"],
                        "score": record_data["score"],
                        "text": stored_text,  # cleaned text (what was embedded)
                        "text_length": len(record_data["text"]),
                        "raw_text": record_data["rec"].get("raw_text"),  # audit: original before OCR cleanup
                        "repetition_ratio": record_data["rec"].get("repetition_ratio"),
                        "ocr_noise_score": record_data["rec"].get("ocr_noise_score"),
                        "source": record_data["rec"].get("source", "internal"),
                        "audience": record_data["rec"].get("audience", "unknown"),
                        "timestamp": record_data["rec"].get("timestamp", datetime.utcnow().isoformat()),
                        "workspace_id": str(self.workspace_id),
                        "product_id": str(self.product_id),
                        # Pipeline run / collection version (must match playground + chunk-metadata filters; not raw_file_version)
                        "version": collection_version,
                        "raw_file_version": self.version,
                        "collection_id": collection_name,  # Add collection_id to payload (must match query filter)
                        "created_at": datetime.utcnow().isoformat(),  # Add created_at timestamp
                        "index_scope": str(self.product_id),
                        "doc_scope": record_data["document_id"],
                        "field_scope": record_data["field_name"],
                        "tags": record_data["tags"],
                        "extra_tags": {"tags": record_data["tags"]} if record_data["tags"] else None,  # For compatibility
                        "token_est": record_data["rec"].get("token_est", 0),
                    },
                }
                all_points.append(point)

                # Lineage: vector-level
                try:
                    record_lineage(
                        db,
                        workspace_id=self.workspace_id,
                        product_id=self.product_id,
                        pipeline_run_id=getattr(self, "pipeline_run_id", None),
                        raw_file_id=None,
                        lineage_type=LineageType.VECTOR,
                        chunk_id=record_data.get("chunk_id"),
                        vector_id=str(point_id),
                        source_file=record_data.get("filename"),
                        page_start=record_data.get("page"),
                        page_end=record_data.get("page"),
                        transformation="embedding",
                        transform_version="1.0",
                        model_name=getattr(embedder, "model_name", None) or "embedding_model",
                        model_version=getattr(embedder, "model_version", None),
                        status="succeeded",
                        details={
                            "collection": collection_name,
                            "text_length": len(record_data["text"]),
                            "score": record_data.get("score"),
                        },
                    )
                except Exception:
                    pass

            if not all_points:
                return self._create_result(
                    status=StageStatus.FAILED,
                    metrics={},
                    error="No points to index",
                    started_at=started_at,
                )

            # Upsert to Qdrant
            success = qdrant_client.upsert_points(collection_name, all_points)
            if not success:
                return self._create_result(
                    status=StageStatus.FAILED,
                    metrics={},
                    error="Failed to upsert points to Qdrant",
                    started_at=started_at,
                )

            finished_at = datetime.utcnow()

            # Calculate aggregate trust score
            scores = [p["payload"]["score"] for p in all_points]
            avg_trust_score = round(sum(scores) / len(scores), 4) if scores else 0.0

            # --- Vector Metrics Calculation ---
            vector_metrics: Dict[str, Any] = {}
            try:
                self.logger.info("Calculating vector quality metrics...")
                
                # Get expected dimension from embedding config
                expected_dim = dimension
                
                # Track vector statistics
                attempted_vectors = len(all_points)
                produced_count = len(all_points)  # All points have embeddings at this point
                fallback_vectors = 0
                dim_mismatches = 0
                nan_inf_count = 0
                valid_vectors = 0
                non_zero_vectors = 0
                norms = []
                api_requests = 0
                api_errors = 0
                
                model_info = embedder.get_model_info()
                fallback_mode = model_info.get("fallback_mode", False)
                
                # Analyze vectors for quality metrics
                for point in all_points:
                    vec = point.get("vector", [])
                    if not vec:
                        continue
                    
                    try:
                        vec_array = np.array(vec, dtype=np.float32)
                        vec_dim = len(vec)
                        
                        # Check dimension consistency
                        if vec_dim != expected_dim:
                            dim_mismatches += 1
                        
                        # Check for NaN/Inf values
                        if np.any(np.isnan(vec_array)) or np.any(np.isinf(vec_array)):
                            nan_inf_count += 1
                        else:
                            valid_vectors += 1
                        
                        # Check for non-zero vectors
                        if np.any(vec_array != 0):
                            non_zero_vectors += 1
                        
                        # Calculate L2 norm for distribution analysis
                        norm = float(np.linalg.norm(vec_array))
                        if norm > 0 and not (np.isnan(norm) or np.isinf(norm)):
                            norms.append(norm)
                    except Exception as e:
                        self.logger.warning(f"Error analyzing vector for point {point.get('id')}: {e}")
                        continue
                
                # Calculate dimension consistency (percentage of vectors with correct dimension)
                if attempted_vectors > 0:
                    dim_consistency = max(0.0, 100.0 - (dim_mismatches / attempted_vectors * 100.0))
                else:
                    dim_consistency = 0.0
                
                # Calculate embedding success rate
                success_rate = (produced_count / attempted_vectors * 100.0) if attempted_vectors > 0 else 0.0
                
                # Vector quality score components
                valid_ratio = (valid_vectors / attempted_vectors) if attempted_vectors > 0 else 0.0
                non_zero_ratio = (non_zero_vectors / attempted_vectors) if attempted_vectors > 0 else 0.0
                
                # Norm health (check for reasonable distribution - avoid outliers)
                norm_health = 1.0
                if norms and len(norms) > 1:
                    try:
                        median = float(np.median(norms))
                        mean_norm = float(np.mean(norms))
                        std_norm = float(np.std(norms)) if len(norms) > 1 else 0.0
                        
                        # Check for outliers (norms too far from median - more than 3 standard deviations)
                        if std_norm > 0:
                            outlier_count = sum(1 for n in norms if abs(n - median) > 3 * std_norm)
                            outlier_rate = outlier_count / len(norms)
                            norm_health = max(0.0, 1.0 - outlier_rate)
                        else:
                            # All norms are similar - good health
                            norm_health = 1.0
                    except Exception as e:
                        self.logger.warning(f"Error calculating norm health: {e}")
                        norm_health = 0.5  # Default to neutral
                
                # Vector Quality Score (composite: valid vectors + non-zero + norm health)
                vqs = (valid_ratio * 0.4 + non_zero_ratio * 0.3 + norm_health * 0.3) * 100.0
                vqs_pct = round(max(0.0, min(100.0, vqs)), 2)
                
                # Embedding Model Health (composite score)
                api_error_rate = (api_errors / max(api_requests, 1)) if api_requests > 0 else 0.0
                fallback_rate = (fallback_vectors / attempted_vectors) if attempted_vectors > 0 else (1.0 if fallback_mode else 0.0)
                dim_mismatch_rate = (dim_mismatches / attempted_vectors) if attempted_vectors > 0 else 0.0
                
                # Response consistency (coefficient of variation of norms)
                response_consistency = 1.0
                if norms and len(norms) > 1:
                    try:
                        mean_norm = float(np.mean(norms))
                        std_norm = float(np.std(norms))
                        cv = (std_norm / mean_norm) if mean_norm > 0 else 0.0
                        # Lower CV = more consistent = higher score
                        response_consistency = max(0.0, 1.0 - min(1.0, cv / 0.75))
                    except Exception:
                        response_consistency = 0.5
                
                # Calculate model health (weighted composite)
                if fallback_mode:
                    model_health_pct = 0.0
                else:
                    model_health = (
                        0.30 * max(0.0, 1.0 - api_error_rate) +
                        0.25 * max(0.0, 1.0 - fallback_rate) +
                        0.20 * max(0.0, 1.0 - dim_mismatch_rate) +
                        0.15 * norm_health +
                        0.10 * response_consistency
                    )
                    model_health_pct = max(0.0, min(100.0, model_health * 100.0))
                
                # Semantic Search Readiness (composite score for RAG readiness)
                semantic_readiness = (
                    0.25 * dim_consistency +
                    0.35 * vqs_pct +
                    0.25 * model_health_pct +
                    0.15 * success_rate
                )
                semantic_readiness = max(0.0, min(100.0, semantic_readiness))
                
                vector_metrics = {
                    "Embedding_Dimension_Consistency": round(dim_consistency, 2),
                    "Embedding_Success_Rate": round(success_rate, 2),
                    "Vector_Quality_Score": round(vqs_pct, 2),
                    "Embedding_Model_Health": round(model_health_pct, 2),
                    "Semantic_Search_Readiness": round(semantic_readiness, 2),
                    # Debug/support fields (not shown in UI directly)
                    "vector_metrics_details": {
                        "expected_dim": expected_dim,
                        "attempted_vectors": attempted_vectors,
                        "produced_vectors": produced_count,
                        "fallback_vectors": fallback_vectors,
                        "dim_mismatch_vectors": dim_mismatches,
                        "nan_inf_vectors": nan_inf_count,
                        "valid_ratio": round(valid_ratio, 6),
                        "non_zero_ratio": round(non_zero_ratio, 6),
                        "norm_median": round(float(np.median(norms)), 6) if norms else 0.0,
                        "norm_mean": round(float(np.mean(norms)), 6) if norms else 0.0,
                        "norm_std": round(float(np.std(norms)), 6) if norms and len(norms) > 1 else 0.0,
                        "norm_health": round(norm_health, 6),
                        "api_requests": int(api_requests),
                        "api_errors": int(api_errors),
                        "api_error_rate": round(api_error_rate, 6),
                        "fallback_mode": bool(fallback_mode),
                        "model_type": model_info.get("model_type", "unknown"),
                    },
                }
                
                self.logger.info(
                    f"Vector metrics calculated: "
                    f"Dimension Consistency={vector_metrics['Embedding_Dimension_Consistency']}%, "
                    f"Success Rate={vector_metrics['Embedding_Success_Rate']}%, "
                    f"Quality Score={vector_metrics['Vector_Quality_Score']}%, "
                    f"Model Health={vector_metrics['Embedding_Model_Health']}%, "
                    f"Semantic Readiness={vector_metrics['Semantic_Search_Readiness']}%"
                )
            except Exception as e:
                self.logger.warning(f"Vector metrics calculation failed (non-fatal): {e}", exc_info=True)
                # Continue without vector metrics

            # --- RAG Performance Metrics (self-retrieval proxy) ---
            rag_metrics: Dict[str, Any] = {}
            try:
                self.logger.info("Calculating RAG performance metrics...")
                
                # Use playbook rag_evaluation settings if provided; otherwise default
                playbook = context.get("playbook") or {}
                rag_cfg = playbook.get("rag_evaluation", {}) if isinstance(playbook, dict) else {}
                retrieval_cfg = rag_cfg.get("retrieval_settings", {}) if isinstance(rag_cfg, dict) else {}
                top_k = int(retrieval_cfg.get("top_k", 10) or 10)
                max_queries = int(retrieval_cfg.get("max_queries", 50) or 50)
                
                # Helper function to extract first sentence for query
                def _first_sentence(text: str) -> str:
                    """Extract first sentence from text for use as query."""
                    if not text:
                        return ""
                    for sep in [". ", "? ", "! "]:
                        idx = text.find(sep)
                        if idx != -1 and idx < 300:
                            return text[: idx + 1].strip()
                    return text[:250].strip()
                
                # Prepare candidates for RAG evaluation (use first sentence of chunks as queries)
                rag_eval_candidates: List[Dict[str, Any]] = []
                for point in all_points[:max_queries]:  # Limit to max_queries for performance
                    payload = point.get("payload", {})
                    chunk_text = payload.get("text", "")
                    query_text = _first_sentence(chunk_text)
                    if query_text and len(query_text) > 10:  # Minimum query length
                        rag_eval_candidates.append({
                            "point_id": point["id"],
                            "query_text": query_text,
                            "expected_chunk_id": payload.get("chunk_id"),
                        })
                
                if rag_eval_candidates:
                    hits = 0
                    ap_sum = 0.0
                    
                    self.logger.info(f"Evaluating RAG performance with {len(rag_eval_candidates)} queries (top_k={top_k})...")
                    
                    for idx, candidate in enumerate(rag_eval_candidates, 1):
                        target_id = candidate["point_id"]
                        query_text = candidate["query_text"]
                        
                        try:
                            # Embed query
                            qvec = embedder.embed(query_text)
                            qvec_list = qvec.tolist() if hasattr(qvec, "tolist") else list(qvec)
                            
                            # Search in Qdrant
                            results = qdrant_client.search_points(collection_name, qvec_list, limit=top_k)
                            
                            # Check if target chunk is in results
                            rank = None
                            for i_r, r in enumerate(results, start=1):
                                if r.get("id") == target_id:
                                    rank = i_r
                                    break
                            
                            if rank is not None:
                                hits += 1
                                # Average Precision: 1/rank (lower rank = higher precision)
                                ap_sum += 1.0 / float(rank)
                            
                            # Log progress every 10 queries
                            if idx % 10 == 0:
                                self.logger.debug(f"RAG evaluation progress: {idx}/{len(rag_eval_candidates)} queries processed")
                        except Exception as e:
                            self.logger.debug(f"RAG eval query {idx} failed: {e}")
                            continue
                    
                    qn = float(len(rag_eval_candidates))
                    recall_at_k = (hits / qn) * 100.0 if qn > 0 else 0.0
                    avg_precision_at_k = (ap_sum / qn) * 100.0 if qn > 0 else 0.0
                    # Note: For self-retrieval evaluation, coverage == recall_at_k, so we only report Retrieval_Recall_At_K
                    
                    rag_metrics = {
                        "Retrieval_Recall_At_K": round(recall_at_k, 2),
                        "Average_Precision_At_K": round(avg_precision_at_k, 2),
                        "rag_metrics_details": {
                            "top_k": top_k,
                            "queries_evaluated": int(qn),
                            "hits": hits,
                            "query_mode": "first_sentence_embed",
                        },
                    }
                    
                    self.logger.info(
                        f"RAG metrics calculated: "
                        f"Recall@K={rag_metrics['Retrieval_Recall_At_K']}%, "
                        f"Precision@K={rag_metrics['Average_Precision_At_K']}%"
                    )
            except Exception as e:
                self.logger.warning(f"RAG metric evaluation failed (non-fatal): {e}", exc_info=True)
                # Continue without RAG metrics

            # Build final metrics result
            metrics_result = {
                "collection_name": collection_name,
                "points_indexed": len(all_points),
                "avg_trust_score": avg_trust_score,
            }
            
            # Merge computed metrics (vector + rag) into stage metrics so downstream can persist them
            metrics_result.update(vector_metrics)
            metrics_result.update(rag_metrics)

            return self._create_result(
                status=StageStatus.SUCCEEDED,
                metrics=metrics_result,
                started_at=started_at,
                finished_at=finished_at,
            )

        except Exception as e:
            self.logger.error(f"Indexing failed: {e}", exc_info=True)
            return self._create_result(
                status=StageStatus.FAILED,
                metrics={},
                error=str(e),
                started_at=started_at,
            )
        finally:
            if close_db:
                db.close()
