"""
Main evaluation harness that replays datasets through pipeline.
"""

import re
from datetime import datetime
from typing import Dict, List, Optional, Any
from uuid import UUID

import numpy as np
from loguru import logger
from sqlalchemy.orm import Session

from primedata.api.chat import build_rag_prompt, get_llm_client
from primedata.db.models import (
    ArtifactStatus,
    EvalDataset,
    EvalDatasetItem,
    EvalRun,
    PipelineArtifact,
    PipelineRun,
    PipelineRunStatus,
    Product,
    Workspace,
)
from primedata.evaluation.harness.evaluator import Evaluator
from primedata.indexing.embeddings import EmbeddingGenerator
from primedata.indexing.qdrant_client import QdrantClient
from primedata.services.s3_content_storage import load_text_from_s3


class EvaluationRunner:
    """Main evaluation harness runner."""

    def __init__(
        self,
        db: Session,
        embedding_generator: Optional[EmbeddingGenerator] = None,
        llm_client=None,
    ):
        """
        Initialize evaluation runner.
        
        Args:
            db: Database session
            embedding_generator: Embedding generator
            llm_client: LLM client
        """
        self.db = db
        self.evaluator = Evaluator(embedding_generator=embedding_generator, llm_client=llm_client)

    def _convert_numpy_types(self, obj: Any) -> Any:
        """
        Recursively convert numpy types to native Python types for JSON serialization.
        
        Args:
            obj: Object that may contain numpy types
            
        Returns:
            Object with numpy types converted to native Python types
        """
        if isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.bool_):
            return bool(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, dict):
            return {key: self._convert_numpy_types(value) for key, value in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [self._convert_numpy_types(item) for item in obj]
        else:
            return obj

    def run_evaluation(
        self,
        dataset_id: UUID,
        product_id: UUID,
        version: int,
        thresholds: Optional[Dict[str, float]] = None,
    ) -> EvalRun:
        """
        Run evaluation on a dataset.
        
        Args:
            dataset_id: Dataset ID
            product_id: Product ID
            version: Product version
            thresholds: Quality thresholds
            
        Returns:
            EvalRun with results
        """
        # Get dataset
        dataset = self.db.query(EvalDataset).filter(EvalDataset.id == dataset_id).first()
        if not dataset:
            raise ValueError(f"Dataset {dataset_id} not found")

        # Get dataset items
        items = self.db.query(EvalDatasetItem).filter(EvalDatasetItem.dataset_id == dataset_id).all()
        if not items:
            raise ValueError(f"Dataset {dataset_id} has no items")

        # Get or create eval run (should already exist when called from DAG)
        eval_run = self.db.query(EvalRun).filter(
            EvalRun.dataset_id == dataset_id,
            EvalRun.product_id == product_id,
            EvalRun.version == version,
        ).order_by(EvalRun.created_at.desc()).first()
        
        # If eval_run doesn't exist, create it (fallback for direct calls)
        if not eval_run:
            eval_run = EvalRun(
                workspace_id=dataset.workspace_id,
                product_id=product_id,
                version=version,
                dataset_id=dataset_id,
                dataset_name=dataset.name,  # Store dataset name for easy display
                pipeline_version=version,  # Store pipeline version that was evaluated
                status="running",
            )
            self.db.add(eval_run)
            self.db.commit()
            self.db.refresh(eval_run)
        else:
            # Update existing eval run to running status
            eval_run.status = "running"
            eval_run.started_at = datetime.utcnow()
            self.db.commit()

        logger.info(f"Starting evaluation run {eval_run.id} with {len(items)} items")

        # Get product and workspace for RAG system access
        product = self.db.query(Product).filter(Product.id == product_id).first()
        if not product:
            raise ValueError(f"Product {product_id} not found")
        
        workspace = self.db.query(Workspace).filter(Workspace.id == product.workspace_id).first()
        if not workspace:
            raise ValueError(f"Workspace not found")
        
        # Initialize Qdrant client
        qdrant_client = QdrantClient()
        if not qdrant_client.is_connected():
            raise ValueError("Qdrant client not connected")
        
        # Get collection name - try PipelineRun first, then fallback to pattern-based lookup
        collection_name = None
        
        # Method 1: Get from PipelineRun (primary source - enterprise-grade)
        try:
            pipeline_run = self.db.query(PipelineRun).filter(
                PipelineRun.product_id == product_id,
                PipelineRun.version == version,
                PipelineRun.status == PipelineRunStatus.SUCCEEDED
            ).first()
            
            if pipeline_run and pipeline_run.collection_name:
                collection_name = pipeline_run.collection_name
                logger.info(f"Found collection name from PipelineRun: {collection_name}")
        except Exception as e:
            logger.warning(f"Failed to get collection name from PipelineRun: {e}. Falling back to pattern-based lookup.")
        
        # Method 2: Fallback to pattern-based lookup (backward compatibility)
        if not collection_name:
            logger.info("Collection name not found in PipelineRun, trying pattern-based lookup...")
            collection_name = qdrant_client.find_collection_name(
                workspace_id=str(product.workspace_id),
                product_id=str(product.id),
                version=version,
                product_name=product.name,  # Pass product_name for proper lookup
            )
        
        if not collection_name:
            raise ValueError(f"Collection not found for product {product_id} version {version}")
        
        logger.info(f"Using collection: {collection_name}")
        
        # Get LLM client (for answer generation and LLM-as-judge)
        llm_client = None
        use_llm = True
        try:
            llm_client = get_llm_client(workspace)
            logger.info("LLM client initialized for answer generation and evaluation")
        except Exception as e:
            logger.warning(f"Failed to initialize LLM client: {e}. Will use template-based answers.")
            use_llm = False
        
        # Update evaluator with LLM client if available
        if llm_client:
            self.evaluator = Evaluator(
                embedding_generator=self.evaluator.metric_registry.embedding_generator,
                llm_client=llm_client,
            )
        
        # Process each item
        per_query_results = []
        for i, item in enumerate(items):
            try:
                logger.info(f"[{i+1}/{len(items)}] Processing query: {item.query[:100]}...")
                
                # Generate query embedding
                logger.debug(f"[{i+1}/{len(items)}] Generating query embedding...")
                query_embedding = self.evaluator.metric_registry.embedding_generator.embed_batch([item.query])[0]
                logger.debug(f"[{i+1}/{len(items)}] Query embedding generated (dimension: {len(query_embedding)})")
                
                # Search Qdrant for relevant chunks
                logger.debug(f"[{i+1}/{len(items)}] Searching Qdrant collection: {collection_name}")
                search_results = qdrant_client.search(
                    collection_name=collection_name,
                    query_vector=query_embedding.tolist(),
                    limit=10,  # Top 10 chunks (increased from 5 for better context relevance)
                )
                logger.info(f"[{i+1}/{len(items)}] Retrieved {len(search_results)} chunks from Qdrant")
                
                # Prepare retrieved chunks
                retrieved_chunks = []
                chunk_ids = []
                for result in search_results:
                    # Handle both dict format (from search_points) and object format (from direct client.search)
                    if isinstance(result, dict):
                        payload = result.get("payload", {})
                        chunk_data = {
                            "id": payload.get("chunk_id") or str(result.get("id", "")),
                            "text": payload.get("text", ""),
                            "score": result.get("score", 0.0),
                            "doc_path": payload.get("doc_path", ""),
                            "source_file": payload.get("source_file", ""),
                            "document_id": payload.get("document_id", ""),
                        }
                    else:
                        # Object format (has attributes)
                        payload = result.payload if hasattr(result, 'payload') else {}
                        chunk_data = {
                            "id": payload.get("chunk_id") if isinstance(payload, dict) else (getattr(payload, 'chunk_id', None) or str(getattr(result, 'id', ''))),
                            "text": payload.get("text", "") if isinstance(payload, dict) else getattr(payload, 'text', ''),
                            "score": getattr(result, 'score', 0.0),
                            "doc_path": payload.get("doc_path", "") if isinstance(payload, dict) else getattr(payload, 'doc_path', ''),
                            "source_file": payload.get("source_file", "") if isinstance(payload, dict) else getattr(payload, 'source_file', ''),
                            "document_id": payload.get("document_id", "") if isinstance(payload, dict) else getattr(payload, 'document_id', ''),
                        }
                    
                    retrieved_chunks.append(chunk_data)
                    if chunk_data["id"]:
                        chunk_ids.append(str(chunk_data["id"]))
                
                # Generate answer
                logger.debug(f"[{i+1}/{len(items)}] Generating answer (LLM available: {use_llm and llm_client is not None})")
                if use_llm and llm_client and retrieved_chunks:
                    # Use LLM to generate answer
                    prompt = build_rag_prompt(item.query, retrieved_chunks)
                    try:
                        llm_result = llm_client.generate(
                            prompt=prompt,
                            temperature=0.7,
                            max_tokens=1000,
                        )
                        answer = llm_result["text"]
                        citations = chunk_ids[:3]  # Top 3 chunks as citations
                        logger.debug(f"[{i+1}/{len(items)}] Generated LLM answer (length: {len(answer)} chars)")
                    except Exception as e:
                        logger.warning(f"[{i+1}/{len(items)}] LLM generation failed: {e}, using template answer")
                        answer = self._generate_template_answer(item.query, retrieved_chunks)
                        citations = chunk_ids[:3]
                elif retrieved_chunks:
                    # Use template-based answer (no LLM)
                    answer = self._generate_template_answer(item.query, retrieved_chunks)
                    citations = chunk_ids[:3]
                    logger.debug(f"[{i+1}/{len(items)}] Generated template answer (length: {len(answer)} chars)")
                else:
                    # No chunks retrieved
                    answer = "I don't have enough information to answer this question."
                    citations = []
                    logger.warning(f"[{i+1}/{len(items)}] No chunks retrieved for query")
                
                # Get expected chunk IDs and doc IDs from dataset item
                expected_chunk_ids = item.expected_chunks if item.expected_chunks else None
                expected_docs = item.expected_docs if item.expected_docs else None

                expected_answer = None
                if item.expected_answer_path:
                    expected_answer = load_text_from_s3(item.expected_answer_path)
                    if expected_answer is None:
                        logger.warning(
                            f"[{i+1}/{len(items)}] Could not load expected_answer from {item.expected_answer_path}"
                        )
                
                # Evaluate
                logger.info(f"[{i+1}/{len(items)}] Calculating metrics...")
                metrics = self.evaluator.evaluate_query(
                    query=item.query,
                    answer=answer,
                    retrieved_chunks=retrieved_chunks,
                    citations=citations,
                    expected_refusal=item.extra_metadata.get("expected_refusal", False) if item.extra_metadata else False,
                    has_evidence=bool(item.expected_chunks or retrieved_chunks),
                    expected_chunk_ids=expected_chunk_ids,
                    expected_docs=expected_docs,
                    expected_answer=expected_answer,
                    thresholds=thresholds,
                )
                
                # Log metric scores for visibility
                metric_summary = ", ".join([
                    f"{name}: {data.get('score', 0):.2f}" if isinstance(data, dict) else f"{name}: {data}"
                    for name, data in metrics.items()
                ])
                logger.info(f"[{i+1}/{len(items)}] Metrics calculated: {metric_summary}")
                
                per_query_results.append({
                    "item_id": str(item.id),
                    "query": item.query,
                    "answer": answer,
                    "retrieved_chunks_count": len(retrieved_chunks),
                    "retrieved_chunk_ids": chunk_ids,
                    "answer_method": "llm" if (use_llm and llm_client) else "template",
                    "metrics": metrics,
                })
            except Exception as e:
                logger.error(f"[{i+1}/{len(items)}] ERROR processing item {item.id}: {e}", exc_info=True)
                per_query_results.append({
                    "item_id": str(item.id),
                    "query": item.query,
                    "error": str(e),
                })

        # Calculate aggregate metrics
        logger.info("Calculating aggregate metrics across all queries...")
        aggregate_metrics = self._calculate_aggregates(per_query_results)
        logger.info(f"Aggregate metrics calculated for {len(aggregate_metrics)} metric types")

        # Prepare metrics data
        metrics_data = {
            "per_query": per_query_results,
            "aggregate": aggregate_metrics,
            "evaluation_metadata": {
                "dataset_id": str(dataset_id),
                "product_id": str(product_id),
                "version": version,
                "total_items": len(items),
                "completed_at": datetime.utcnow().isoformat() + "Z",
                "answer_method": "llm" if (use_llm and llm_client) else "template",
            }
        }

        # Convert numpy types to native Python types for JSON serialization
        metrics_data = self._convert_numpy_types(metrics_data)

        # Update eval run
        eval_run.metrics = metrics_data
        eval_run.status = "completed"
        eval_run.finished_at = datetime.utcnow()
        
        # Save metrics to S3
        try:
            from primedata.storage.minio_client import minio_client
            import json
            
            # Build S3 path with date-partitioned structure
            now = datetime.utcnow()
            s3_path = (
                f"ws/{dataset.workspace_id}/prod/{product_id}/eval/v{version}/"
                f"{now.year:04d}/{now.month:02d}/{now.day:02d}/"
                f"{eval_run.id}/metrics.json"
            )
            
            # Save metrics to S3
            bucket = "primedata-exports"
            metrics_json = json.dumps(metrics_data, default=str, indent=2)
            
            minio_client.put_bytes(
                bucket=bucket,
                key=s3_path,
                data=metrics_json.encode('utf-8'),
                content_type="application/json"
            )
            eval_run.metrics_path = s3_path
            logger.info(f"Saved evaluation metrics to S3: {s3_path}")
        except Exception as s3_error:
            logger.error(f"Failed to save metrics to S3: {s3_error}", exc_info=True)
            # Continue even if S3 save fails - metrics are still in DB
        
        self.db.commit()

        logger.info(f"Completed evaluation run {eval_run.id}")
        return eval_run

    def _calculate_aggregates(self, per_query_results: List[Dict]) -> Dict:
        """Calculate aggregate metrics from per-query results."""
        if not per_query_results:
            return {}

        # Collect all metric names dynamically
        all_metric_names = set()
        for result in per_query_results:
            if "error" not in result:
                metrics = result.get("metrics", {})
                all_metric_names.update(metrics.keys())
        
        # Initialize metric scores dictionary
        metric_scores = {name: [] for name in all_metric_names}

        for result in per_query_results:
            if "error" in result:
                continue
            metrics = result.get("metrics", {})
            for metric_name, metric_data in metrics.items():
                if isinstance(metric_data, dict):
                    score = metric_data.get("score", 0.0)
                    metric_scores[metric_name].append(score)

        aggregates = {}
        for metric_name, scores in metric_scores.items():
            if scores:
                # Convert scores to native Python floats before calculations
                native_scores = [float(score) if isinstance(score, (np.integer, np.floating)) else float(score) for score in scores]
                aggregates[metric_name] = {
                    "mean": float(sum(native_scores) / len(native_scores)),
                    "min": float(min(native_scores)),
                    "max": float(max(native_scores)),
                    "count": len(native_scores),
                }
            else:
                aggregates[metric_name] = {
                    "mean": 0.0,
                    "min": 0.0,
                    "max": 0.0,
                    "count": 0,
                }

        return aggregates
    
    def _generate_template_answer(self, query: str, retrieved_chunks: List[Dict]) -> str:
        """
        Generate answer from chunks without LLM using template-based extraction.
        Falls back to this when LLM is not available.
        """
        if not retrieved_chunks:
            return "I don't have enough information to answer this question."
        
        # Extract query keywords
        query_words = set(query.lower().split())
        
        # Find most relevant sentences from chunks
        relevant_sentences = []
        for chunk in retrieved_chunks[:3]:  # Use top 3 chunks
            chunk_text = chunk.get("text", "")
            sentences = re.split(r'[.!?]+', chunk_text)
            
            for sentence in sentences:
                sentence = sentence.strip()
                if len(sentence) < 20:  # Skip very short sentences
                    continue
                
                # Score sentence relevance
                sentence_words = set(sentence.lower().split())
                overlap = query_words.intersection(sentence_words)
                relevance = len(overlap) / len(query_words) if query_words else 0
                
                if relevance > 0.2:  # At least 20% keyword overlap
                    relevant_sentences.append((sentence, relevance))
        
        # Sort by relevance and take top sentences
        relevant_sentences.sort(key=lambda x: x[1], reverse=True)
        top_sentences = [s[0] for s in relevant_sentences[:5]]  # Top 5 sentences
        
        if top_sentences:
            # Combine into answer
            answer = " ".join(top_sentences)
            # Clean up multiple spaces
            answer = re.sub(r'\s+', ' ', answer).strip()
            return answer
        else:
            return "I don't have enough information to answer this question."

